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
    PlaneError,
    PlaneUnavailableError,
    _env_float,
    _resolve_verify,
    _status_is_retryable,
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
    "list_module_work_items",
    "add_work_items_to_module",
    "remove_work_item_from_module",
    "list_work_items",
    "retrieve_work_item",
    "create_work_item",
    "update_work_item",
    "add_comment",
    "list_comments",
    "list_cycles",
    "retrieve_cycle",
    "create_cycle",
    "update_cycle",
    "delete_cycle",
    "list_cycle_work_items",
    "add_work_items_to_cycle",
    "remove_work_item_from_cycle",
    "transfer_cycle_work_items",
    "list_relations",
    "add_relation",
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


async def test_add_work_items_to_cycle_sends_issues_list(
    two_personas_registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cycle-issues POST must carry ``{"issues": [<uuid>]}`` and
    route under the invoking persona's token. UUIDs short-circuit the
    identifier lookup, so the only request captured is the POST itself.
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
        response.content = b"{}"
        response.json = lambda: {}
        response.text = "{}"
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    cycle_uuid = "abcdabcd-1111-2222-3333-abcdabcdabcd"
    await mcp.call_tool(
        "business_analyst__add_work_items_to_cycle",
        {
            "project_id": PROJECT_UUID,
            "cycle_id": cycle_uuid,
            "work_item_ids": [WORK_ITEM_UUID],
        },
    )
    assert captured, "no HTTP request captured"
    post = captured[-1]
    assert post["method"] == "POST"
    assert post["auth_header"] == "ba-token"
    assert f"/cycles/{cycle_uuid}/cycle-issues/" in post["url"]
    assert post["json"] == {"issues": [WORK_ITEM_UUID]}


async def test_add_work_items_to_module_sends_issues_list(
    two_personas_registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The module-issues POST must carry ``{"issues": [<uuid>]}`` and
    route under the invoking persona's token — the mechanism the SA uses
    to set a child's Plane Module (``create_work_item`` has no module
    field). UUIDs short-circuit the identifier lookup.
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
        response.content = b"{}"
        response.json = lambda: {}
        response.text = "{}"
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    module_uuid = "feedface-1111-2222-3333-feedfacefeed"
    await mcp.call_tool(
        "business_analyst__add_work_items_to_module",
        {
            "project_id": PROJECT_UUID,
            "module_id": module_uuid,
            "work_item_ids": [WORK_ITEM_UUID],
        },
    )
    assert captured, "no HTTP request captured"
    post = captured[-1]
    assert post["method"] == "POST"
    assert post["auth_header"] == "ba-token"
    assert f"/modules/{module_uuid}/module-issues/" in post["url"]
    assert post["json"] == {"issues": [WORK_ITEM_UUID]}


async def test_create_cycle_omits_unset_dates(
    two_personas_registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name-only cycle create must not send null start/end dates —
    Plane rejects one date without the other."""
    captured: list[dict[str, Any]] = []

    async def fake_request(
        self: httpx.AsyncClient, method: str, url: Any, **kwargs: Any
    ) -> Any:
        captured.append({"method": method, "json": kwargs.get("json")})
        response = MagicMock(spec=httpx.Response)
        response.status_code = 201
        response.content = b'{"id":"cycle-1"}'
        response.json = lambda: {"id": "cycle-1"}
        response.text = '{"id":"cycle-1"}'
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    await mcp.call_tool(
        "business_analyst__create_cycle",
        {"project_id": PROJECT_UUID, "name": "Sprint 1"},
    )
    post = [c for c in captured if c["method"] == "POST"][-1]
    assert post["json"] == {"name": "Sprint 1"}


async def test_list_work_items_strips_descriptions_by_default(
    two_personas_registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Body fields are dropped from list responses unless explicitly
    requested — a 100-item page of full HTML bodies exceeds 2 MB and
    blows the caller's context window.
    """
    item = {
        "id": WORK_ITEM_UUID,
        "name": "Some story",
        "description_html": "<p>huge body</p>",
        "description_stripped": "huge body",
        "state": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    }

    async def fake_request(
        self: httpx.AsyncClient, method: str, url: Any, **kwargs: Any
    ) -> Any:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.content = b"[...]"
        response.json = lambda: [dict(item)]
        response.text = "[...]"
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    result = await mcp.call_tool(
        "business_analyst__list_work_items", {"project_id": PROJECT_UUID}
    )
    flat = str(result)
    assert "Some story" in flat
    assert "description_html" not in flat
    assert "huge body" not in flat

    result = await mcp.call_tool(
        "business_analyst__list_work_items",
        {"project_id": PROJECT_UUID, "include_description": True},
    )
    assert "huge body" in str(result)


async def test_add_to_module_survives_list_shaped_response(
    two_personas_registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: Plane answers the module-issues POST with a *list*
    of membership links. The tool used to declare a dict output schema
    and fail validation AFTER the successful write (the "DictModel"
    false negative that made the SA post bogus manual-step warnings).
    The tool must return its own dict summary instead.
    """

    async def fake_request(
        self: httpx.AsyncClient, method: str, url: Any, **kwargs: Any
    ) -> Any:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 201
        response.content = b'[{"id":"link-1"}]'
        response.json = lambda: [{"id": "link-1"}]
        response.text = '[{"id":"link-1"}]'
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    module_uuid = "feedface-1111-2222-3333-feedfacefeed"
    result = await mcp.call_tool(
        "business_analyst__add_work_items_to_module",
        {
            "project_id": PROJECT_UUID,
            "module_id": module_uuid,
            "work_item_ids": [WORK_ITEM_UUID],
        },
    )
    flat = str(result)
    assert "added" in flat and WORK_ITEM_UUID in flat

    cycle_uuid = "abcdabcd-1111-2222-3333-abcdabcdabcd"
    result = await mcp.call_tool(
        "business_analyst__add_work_items_to_cycle",
        {
            "project_id": PROJECT_UUID,
            "cycle_id": cycle_uuid,
            "work_item_ids": [WORK_ITEM_UUID],
        },
    )
    flat = str(result)
    assert "added" in flat and WORK_ITEM_UUID in flat


async def test_add_relation_posts_relation_contract(
    two_personas_registered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``add_relation`` must POST ``{"relation_type", "issues"}`` to the
    work item's ``relations/`` collection — the contract verified
    against Plane's public REST surface.
    """
    captured: list[dict[str, Any]] = []

    async def fake_request(
        self: httpx.AsyncClient, method: str, url: Any, **kwargs: Any
    ) -> Any:
        captured.append(
            {"method": method, "url": str(url), "json": kwargs.get("json")}
        )
        response = MagicMock(spec=httpx.Response)
        response.status_code = 201
        response.content = b"{}"
        response.json = lambda: {}
        response.text = "{}"
        return response

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    other_uuid = "abcdabcd-9999-8888-7777-abcdabcdabcd"
    result = await mcp.call_tool(
        "business_analyst__add_relation",
        {
            "project_id": PROJECT_UUID,
            "work_item_id": WORK_ITEM_UUID,
            "relation_type": "blocked_by",
            "related_work_item_ids": [other_uuid],
        },
    )
    post = captured[-1]
    assert post["method"] == "POST"
    assert f"/work-items/{WORK_ITEM_UUID}/relations/" in post["url"]
    assert post["json"] == {"relation_type": "blocked_by", "issues": [other_uuid]}
    assert "blocked_by" in str(result)


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
        client._pat_url("projects/p/modules/m/module-issues/")
        == f"{base}/projects/p/modules/m/module-issues/"
    )
    assert (
        client._pat_url("projects/p/work-items/")
        == f"{base}/projects/p/work-items/"
    )
    assert client._pat_url("projects/p/cycles/") == f"{base}/projects/p/cycles/"
    assert (
        client._pat_url("projects/p/cycles/c/cycle-issues/")
        == f"{base}/projects/p/cycles/c/cycle-issues/"
    )
    assert (
        client._pat_url("projects/p/cycles/c/transfer-issues/")
        == f"{base}/projects/p/cycles/c/transfer-issues/"
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


# ---------------------------------------------------------------------
# Transient-failure handling
#
# Modelled on the 2026-08-02 Plane maintenance window, where a reverse
# proxy answered every call with a bodiless 502 for ~30s and each tool
# call failed hard, leaving the agent to retry blindly.
# ---------------------------------------------------------------------


def _response(
    status_code: int,
    *,
    method: str = "GET",
    content: bytes = b"",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=content,
        headers=headers,
        request=httpx.Request(method, "https://plane.example.org/x"),
    )


GATEWAY_502 = {"status_code": 502, "content": b""}
APP_JSON = {"content-type": "application/json"}


@pytest.fixture
def instant_backoff(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Collapse the backoff to zero and record what would have been slept."""
    import plane_extras_mcp.plane as plane_mod

    slept: list[float] = []

    def fake_delay(attempt: int) -> float:
        slept.append(float(attempt))
        return 0.0

    monkeypatch.setattr(plane_mod, "_backoff_delay", fake_delay)
    return slept


def _client() -> PlaneClient:
    return PlaneClient(
        api_key="tok",
        workspace_slug="test-ws",
        base_url="https://plane.example.org",
    )


def _queue_responses(
    monkeypatch: pytest.MonkeyPatch, responses: list[Any]
) -> list[str]:
    """Serve `responses` in order; each entry is a Response or an
    exception to raise. Returns the list that records call methods.
    """
    calls: list[str] = []
    queue = list(responses)

    async def fake_request(
        self: httpx.AsyncClient, method: str, url: Any, **kwargs: Any
    ) -> httpx.Response:
        calls.append(method)
        item = queue.pop(0) if queue else responses[-1]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    return calls


async def test_transient_502_is_retried_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, instant_backoff: list[float]
) -> None:
    """The exact failure from the maintenance window: two bodiless 502s
    followed by recovery must look like a plain success to the caller.
    """
    ok = _response(200, content=b'{"id":"wi-1"}', headers=APP_JSON)
    calls = _queue_responses(
        monkeypatch,
        [_response(**GATEWAY_502), _response(**GATEWAY_502), ok],
    )
    async with _client() as client:
        result = await client._pat_request("GET", "projects/")
    assert result == {"id": "wi-1"}
    assert len(calls) == 3, f"expected 3 attempts, got {len(calls)}"


async def test_persistent_outage_raises_actionable_error(
    monkeypatch: pytest.MonkeyPatch, instant_backoff: list[float]
) -> None:
    """An outage that outlasts the retries must name itself as an
    outage — the old bodiless "Plane API error 502:" told the agent
    nothing and it started mutating its arguments.
    """
    calls = _queue_responses(monkeypatch, [_response(**GATEWAY_502)])
    client = _client()
    client.max_attempts = 4
    async with client:
        with pytest.raises(PlaneUnavailableError) as exc_info:
            await client._pat_request("GET", "projects/")
    assert len(calls) == 4
    message = str(exc_info.value)
    assert "unreachable or restarting" in message
    assert "not a malformed request" in message
    assert exc_info.value.status_code == 502
    assert exc_info.value.attempts == 4


async def test_client_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch, instant_backoff: list[float]
) -> None:
    """A 400/404 is the caller's fault and stays a single hard failure —
    retrying it would only slow the agent down.
    """
    for status in (400, 403, 404):
        calls = _queue_responses(
            monkeypatch,
            [_response(status, content=b'{"error":"nope"}', headers=APP_JSON)],
        )
        async with _client() as client:
            with pytest.raises(PlaneError) as exc_info:
                await client._pat_request("GET", "projects/")
        assert not isinstance(exc_info.value, PlaneUnavailableError)
        assert exc_info.value.status_code == status
        assert len(calls) == 1, f"status {status} was retried"


async def test_write_retried_when_request_never_reached_plane(
    monkeypatch: pytest.MonkeyPatch, instant_backoff: list[float]
) -> None:
    """A bodiless 502 comes from the proxy, so no comment was written —
    repeating the POST cannot duplicate anything.
    """
    ok = _response(201, content=b'{"id":"c-1"}', headers=APP_JSON)
    calls = _queue_responses(
        monkeypatch, [_response(**GATEWAY_502), ok]
    )
    async with _client() as client:
        result = await client._pat_request(
            "POST", "projects/p/work-items/w/comments/", json={"x": 1}
        )
    assert result == {"id": "c-1"}
    assert calls == ["POST", "POST"]


async def test_write_not_retried_when_plane_itself_errored(
    monkeypatch: pytest.MonkeyPatch, instant_backoff: list[float]
) -> None:
    """A JSON 500 means Plane processed the request and may have
    applied it — repeating the POST risks a duplicate comment.
    """
    calls = _queue_responses(
        monkeypatch,
        [_response(500, content=b'{"error":"boom"}', headers=APP_JSON)],
    )
    async with _client() as client:
        with pytest.raises(PlaneError) as exc_info:
            await client._pat_request(
                "POST", "projects/p/work-items/w/comments/", json={"x": 1}
            )
    assert not isinstance(exc_info.value, PlaneUnavailableError)
    assert len(calls) == 1


async def test_connect_failure_is_retried_for_writes(
    monkeypatch: pytest.MonkeyPatch, instant_backoff: list[float]
) -> None:
    """Plane down between calls: the connection never opened, so the
    write provably did not land and the POST may be repeated.
    """
    ok = _response(201, content=b'{"id":"c-1"}', headers=APP_JSON)
    calls = _queue_responses(
        monkeypatch, [httpx.ConnectError("connection refused"), ok]
    )
    async with _client() as client:
        result = await client._pat_request("POST", "x/", json={"a": 1})
    assert result == {"id": "c-1"}
    assert len(calls) == 2


async def test_read_failure_on_write_reports_unknown_outcome(
    monkeypatch: pytest.MonkeyPatch, instant_backoff: list[float]
) -> None:
    """The connection opened and then broke mid-flight: whether Plane
    applied the write is unknowable, so the error says so instead of
    silently repeating it.
    """
    calls = _queue_responses(
        monkeypatch, [httpx.ReadTimeout("read timed out")]
    )
    async with _client() as client:
        with pytest.raises(PlaneUnavailableError) as exc_info:
            await client._pat_request("POST", "x/", json={"a": 1})
    assert len(calls) == 1, "an ambiguous write must not be repeated"
    assert exc_info.value.outcome_unknown
    assert "may or may not have been applied" in str(exc_info.value)


async def test_read_failure_on_get_is_retried(
    monkeypatch: pytest.MonkeyPatch, instant_backoff: list[float]
) -> None:
    """The same mid-flight break on a GET has no side effect to protect."""
    ok = _response(200, content=b"[]", headers=APP_JSON)
    calls = _queue_responses(
        monkeypatch, [httpx.ReadTimeout("read timed out"), ok]
    )
    async with _client() as client:
        assert await client._pat_request("GET", "projects/") == []
    assert len(calls) == 2


async def test_retry_budget_ends_the_loop_before_max_attempts(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool call must not block indefinitely just because attempts
    remain — the time budget is the ceiling the caller feels.
    """
    import plane_extras_mcp.plane as plane_mod

    monkeypatch.setattr(plane_mod, "_backoff_delay", lambda attempt: 30.0)
    calls = _queue_responses(monkeypatch, [_response(**GATEWAY_502)])
    client = _client()
    client.max_attempts = 10
    client.retry_budget = 1.0
    async with client:
        with pytest.raises(PlaneUnavailableError):
            await client._pat_request("GET", "projects/")
    assert len(calls) == 1, "a delay overrunning the budget must not be slept"


async def test_budget_not_attempt_count_outlasts_a_fast_outage(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bodiless 502 fails in milliseconds, so a small attempt count
    would give up seconds into an outage that lasts half a minute. The
    time budget has to be what decides when to stop.
    """
    import plane_extras_mcp.plane as plane_mod

    monkeypatch.setattr(plane_mod, "_backoff_delay", lambda attempt: 0.02)
    calls = _queue_responses(monkeypatch, [_response(**GATEWAY_502)])
    client = _client()
    client.max_attempts = 1000
    client.retry_budget = 0.3
    async with client:
        with pytest.raises(PlaneUnavailableError):
            await client._pat_request("GET", "projects/")
    assert len(calls) > 10, (
        f"gave up after {len(calls)} attempts — the budget was not the ceiling"
    )


async def test_retry_after_header_is_honoured(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A throttled call waits the interval Plane asked for, capped."""
    import plane_extras_mcp.plane as plane_mod

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(plane_mod.asyncio, "sleep", fake_sleep)
    ok = _response(200, content=b"[]", headers=APP_JSON)
    _queue_responses(
        monkeypatch,
        [_response(429, headers={"retry-after": "2"}), ok],
    )
    async with _client() as client:
        assert await client._pat_request("GET", "projects/") == []
    assert slept == [2.0], f"expected a 2s wait, slept {slept}"


def test_status_retry_policy_distinguishes_gateway_from_app() -> None:
    """The pivot the whole policy rests on: who produced the error."""
    gateway = _response(502)
    app = _response(502, content=b'{"detail":"x"}', headers=APP_JSON)
    assert _status_is_retryable(502, "POST", gateway)
    assert not _status_is_retryable(502, "POST", app)
    assert _status_is_retryable(502, "GET", app)
    assert _status_is_retryable(503, "POST", gateway)
    assert _status_is_retryable(429, "POST", app)
    assert not _status_is_retryable(504, "POST", gateway)
    assert _status_is_retryable(504, "GET", gateway)
    assert not _status_is_retryable(404, "GET", app)


def test_env_float_falls_back_on_garbage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in the consumer's .mcp.json must not stop the server."""
    monkeypatch.setenv("PLANE_RETRY_BUDGET", "not-a-number")
    assert _env_float("PLANE_RETRY_BUDGET", 45.0) == 45.0
    monkeypatch.setenv("PLANE_RETRY_BUDGET", "-5")
    assert _env_float("PLANE_RETRY_BUDGET", 45.0) == 45.0
    monkeypatch.setenv("PLANE_RETRY_BUDGET", "12.5")
    assert _env_float("PLANE_RETRY_BUDGET", 45.0) == 12.5
