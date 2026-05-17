"""Smoke tests — no Plane connection required.

These verify the package loads, the per-persona tool prefixing works,
calls route to the right token, and the PlaneClient constructs URLs
correctly.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from plane_extras_mcp import __version__
from plane_extras_mcp.plane import (
    API_VERSION,
    DEFAULT_BASE_URL,
    PlaneClient,
    _resolve_verify,
    looks_like_uuid,
)
from plane_extras_mcp.server import (
    _persona_credentials,
    _persona_tool_prefix,
    mcp,
    register_personas_from_env,
)

# Tools registered per persona — kept in sync with server.py's
# _register_persona_tools. Order matches the source for readability.
TOOL_VERBS = (
    "list_projects",
    "list_workspace_members",
    "list_states",
    "list_labels",
    "list_modules",
    "list_work_items",
    "retrieve_work_item",
    "create_work_item",
    "update_work_item",
    "add_comment",
    "list_comments",
)

PROJECT_UUID = "11111111-2222-3333-4444-555555555555"
WORK_ITEM_UUID = "92493a08-d1f2-496f-81d0-07a9a6d6d389"


def _clear_persona_tools(personas: list[str]) -> None:
    for persona in personas:
        prefix = _persona_tool_prefix(persona)
        for verb in TOOL_VERBS:
            try:
                mcp.remove_tool(f"{prefix}__{verb}")
            except ToolError:
                pass


def _clear_plane_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("PLANE_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def two_personas_registered(monkeypatch: pytest.MonkeyPatch):
    """Register tools for two distinct personas with distinct tokens.

    Tests share the module-level ``mcp`` instance, so we tear the
    registered tools back down afterwards to keep the suite isolated.
    """
    personas = ["business-analyst", "release-manager"]
    _clear_persona_tools(personas)

    _clear_plane_env(monkeypatch)
    monkeypatch.setenv("PLANE_WORKSPACE_SLUG", "test-ws")
    monkeypatch.setenv("PLANE_BASE_URL", "https://plane.example.org")
    monkeypatch.setenv("PLANE_API_KEY_BUSINESS_ANALYST", "ba-token")
    monkeypatch.setenv("PLANE_API_KEY_RELEASE_MANAGER", "rm-token")

    register_personas_from_env()

    try:
        yield {"business-analyst": "ba-token", "release-manager": "rm-token"}
    finally:
        _clear_persona_tools(personas)


def test_package_has_version() -> None:
    assert __version__


async def test_tools_register_per_persona(two_personas_registered) -> None:
    """Every configured persona has the full tool set under its prefix."""
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    for persona in two_personas_registered:
        prefix = _persona_tool_prefix(persona)
        for verb in TOOL_VERBS:
            assert f"{prefix}__{verb}" in names, (
                f"missing tool {prefix}__{verb}"
            )


async def test_no_legacy_tool_names(two_personas_registered) -> None:
    """The previous flat names (`add_comment`, `list_comments`) and
    the removed page tools must not appear — every tool now lives
    behind a persona prefix.
    """
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    legacy = {
        "add_comment",
        "list_comments",
        "create_page",
        "list_pages",
        "retrieve_page",
        "update_page_description",
        "delete_page",
    }
    leaked = names & legacy
    assert not leaked, f"unexpected legacy tool names still registered: {leaked}"


async def test_persona_routing_uses_correct_token(
    two_personas_registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same logical call (add_comment) routes to the right Plane
    token depending on which persona's tool name was invoked.
    Captured by intercepting ``httpx.AsyncClient.request``.
    """
    captured: list[dict[str, Any]] = []

    async def fake_request(
        self: httpx.AsyncClient, method: str, url: Any, **kwargs: Any
    ) -> Any:
        captured.append(
            {
                "method": method,
                "url": str(url),
                "auth_header": self.headers.get("X-API-Key"),
                "json": kwargs.get("json"),
            }
        )
        response = MagicMock(spec=httpx.Response)
        response.status_code = 201
        response.content = b'{"id":"comment-1"}'
        response.json = lambda: {"id": "comment-1"}
        response.text = '{"id":"comment-1"}'
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    await mcp.call_tool(
        "business_analyst__add_comment",
        {
            "project_id": PROJECT_UUID,
            "work_item_id": WORK_ITEM_UUID,
            "comment_html": "<p>from BA</p>",
        },
    )
    assert captured, "no HTTP requests captured for BA"
    assert captured[-1]["auth_header"] == "ba-token", (
        f"BA call used wrong token: {captured[-1]['auth_header']}"
    )
    assert "/workspaces/test-ws/" in captured[-1]["url"]

    captured.clear()
    await mcp.call_tool(
        "release_manager__add_comment",
        {
            "project_id": PROJECT_UUID,
            "work_item_id": WORK_ITEM_UUID,
            "comment_html": "<p>from RM</p>",
        },
    )
    assert captured, "no HTTP requests captured for RM"
    assert captured[-1]["auth_header"] == "rm-token", (
        f"RM call used wrong token: {captured[-1]['auth_header']}"
    )


async def test_update_work_item_only_sends_provided_fields(
    two_personas_registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PATCH must only carry the fields the caller actually set — a
    state-only handover must not blank out assignees/labels.
    """
    captured: list[dict[str, Any]] = []

    async def fake_request(
        self: httpx.AsyncClient, method: str, url: Any, **kwargs: Any
    ) -> Any:
        captured.append({"method": method, "json": kwargs.get("json")})
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.content = b'{"id":"wi-1"}'
        response.json = lambda: {"id": "wi-1"}
        response.text = '{"id":"wi-1"}'
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    target_state = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    await mcp.call_tool(
        "business_analyst__update_work_item",
        {
            "project_id": PROJECT_UUID,
            "work_item_id": WORK_ITEM_UUID,
            "state": target_state,
        },
    )
    patch_calls = [c for c in captured if c["method"] == "PATCH"]
    assert patch_calls, "no PATCH issued"
    body = patch_calls[-1]["json"]
    assert body == {"state": target_state}, (
        f"PATCH body should carry state only; got {body}"
    )


def test_register_personas_empty_when_no_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No PLANE_WORKSPACE_SLUG → no personas registered, even when
    API keys are present."""
    _clear_plane_env(monkeypatch)
    monkeypatch.setenv("PLANE_API_KEY_BUSINESS_ANALYST", "ba-token")
    assert _persona_credentials() == {}


def test_register_personas_skips_blank_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank API tokens are ignored — install.py emits unfilled
    placeholders as empty strings during stage 1."""
    _clear_plane_env(monkeypatch)
    monkeypatch.setenv("PLANE_WORKSPACE_SLUG", "ws")
    monkeypatch.setenv("PLANE_API_KEY_BUSINESS_ANALYST", "")
    monkeypatch.setenv("PLANE_API_KEY_RELEASE_MANAGER", "rm-token")
    creds = _persona_credentials()
    assert set(creds) == {"release-manager"}


def test_persona_tool_prefix_converts_hyphens() -> None:
    assert _persona_tool_prefix("business-analyst") == "business_analyst"
    assert _persona_tool_prefix("technical-writer") == "technical_writer"
    assert _persona_tool_prefix("ba") == "ba"


# ---------------------------------------------------------------------------
# PlaneClient unit tests — preserved from the pre-refactor suite.

def test_plane_client_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PLANE_API_KEY", raising=False)
    monkeypatch.delenv("PLANE_WORKSPACE_SLUG", raising=False)
    with pytest.raises(KeyError):
        PlaneClient()


def test_pat_url_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLANE_API_KEY", "test-key")
    monkeypatch.setenv("PLANE_WORKSPACE_SLUG", "test-ws")
    monkeypatch.setenv("PLANE_BASE_URL", "https://plane.example.org/")
    client = PlaneClient()
    assert client.base_url == "https://plane.example.org"
    url = client._pat_url("projects/abc/work-items/def/comments/")
    assert url == (
        f"https://plane.example.org/api/{API_VERSION}/workspaces/test-ws/"
        "projects/abc/work-items/def/comments/"
    )


def test_pat_url_new_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoints added for the multi-tenant refactor must hit the
    same workspace-scoped REST surface."""
    monkeypatch.setenv("PLANE_API_KEY", "test-key")
    monkeypatch.setenv("PLANE_WORKSPACE_SLUG", "ws")
    monkeypatch.setenv("PLANE_BASE_URL", "https://plane.example.org")
    client = PlaneClient()
    base = f"https://plane.example.org/api/{API_VERSION}/workspaces/ws"
    assert client._pat_url("projects/") == f"{base}/projects/"
    assert client._pat_url("members/") == f"{base}/members/"
    assert client._pat_url("projects/p/states/") == f"{base}/projects/p/states/"
    assert client._pat_url("projects/p/labels/") == f"{base}/projects/p/labels/"
    assert client._pat_url("projects/p/modules/") == f"{base}/projects/p/modules/"
    assert (
        client._pat_url("projects/p/work-items/")
        == f"{base}/projects/p/work-items/"
    )


def test_plane_client_default_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLANE_API_KEY", "test-key")
    monkeypatch.setenv("PLANE_WORKSPACE_SLUG", "test-ws")
    monkeypatch.delenv("PLANE_BASE_URL", raising=False)
    client = PlaneClient()
    assert client.base_url == DEFAULT_BASE_URL


def test_unwrap_list_handles_paginated_dict() -> None:
    payload = {"results": [{"id": 1}], "count": 1}
    assert PlaneClient._unwrap_list(payload) == [{"id": 1}]


def test_unwrap_list_handles_bare_list() -> None:
    payload = [{"id": 1}]
    assert PlaneClient._unwrap_list(payload) == [{"id": 1}]


def test_unwrap_list_handles_empty_or_none() -> None:
    assert PlaneClient._unwrap_list(None) == []
    assert PlaneClient._unwrap_list({}) == []


def test_resolve_verify_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLANE_CA_BUNDLE", raising=False)
    monkeypatch.delenv("PLANE_VERIFY_SSL", raising=False)
    assert _resolve_verify() is True


def test_resolve_verify_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLANE_CA_BUNDLE", raising=False)
    for value in ("false", "FALSE", "0", "no", "off"):
        monkeypatch.setenv("PLANE_VERIFY_SSL", value)
        assert _resolve_verify() is False, f"failed for value={value!r}"


def test_resolve_verify_ca_bundle_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLANE_CA_BUNDLE", "/etc/ssl/certs/custom-ca.pem")
    monkeypatch.setenv("PLANE_VERIFY_SSL", "false")
    assert _resolve_verify() == "/etc/ssl/certs/custom-ca.pem"


def test_looks_like_uuid_recognises_canonical_form() -> None:
    assert looks_like_uuid("92493a08-d1f2-496f-81d0-07a9a6d6d389")
    assert looks_like_uuid("92493A08-D1F2-496F-81D0-07A9A6D6D389")


def test_looks_like_uuid_rejects_identifier_form() -> None:
    assert not looks_like_uuid("INT-1")
    assert not looks_like_uuid("INT-42")
    assert not looks_like_uuid("LONGNAME-123")
    assert not looks_like_uuid("")
    assert not looks_like_uuid("not-a-uuid-at-all")
