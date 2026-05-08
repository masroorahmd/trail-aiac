"""Smoke tests — no Plane connection required.

These verify the package loads, the supplementary tools register with
FastMCP, and the PlaneClient constructs URLs correctly.
"""

from __future__ import annotations

import pytest

from plane_extras_mcp import __version__
from plane_extras_mcp.plane import (
    API_VERSION,
    DEFAULT_BASE_URL,
    PlaneClient,
    _resolve_verify,
    looks_like_uuid,
)
from plane_extras_mcp.server import mcp

EXPECTED_TOOLS = {
    "add_comment",
    "list_comments",
}


def test_package_has_version() -> None:
    assert __version__


async def test_expected_tools_registered() -> None:
    tools = await mcp.list_tools()
    actual = {t.name for t in tools}
    assert EXPECTED_TOOLS.issubset(actual), (
        f"missing tools: {EXPECTED_TOOLS - actual}"
    )


async def test_no_unexpected_tools_registered() -> None:
    """Pages were removed; verify they're not registered any more."""
    tools = await mcp.list_tools()
    actual = {t.name for t in tools}
    forbidden = {
        "create_page", "list_pages", "retrieve_page",
        "update_page_description", "delete_page",
    }
    leaked = actual & forbidden
    assert not leaked, f"page tools still registered: {leaked}"


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
