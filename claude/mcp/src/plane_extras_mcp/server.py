"""FastMCP server exposing every Plane tool the persona team needs.

Multi-tenant by design: one stdio process serves all configured
personas. At startup the server scans the environment for
``PLANE_API_KEY_<PERSONA_PREFIX>`` variables and registers every tool
N×, prefixed by the persona's snake-case username — e.g.
``business_analyst__list_states`` for ``business-analyst``. Each
registered tool closes over its persona's credentials, so the call
lands in Plane authored by that persona regardless of which model
session invoked it.

This replaces the previous one-process-per-persona layout, which
spawned ~22 stdio MCP servers per Claude session (upstream
``plane-mcp-server`` + ``plane-extras-mcp``, both ×N personas) and
consumed ~2 GB of RSS. The tool surface here is the union of the
upstream ``plane-mcp-server`` operations the persona prompts actually
reference (projects, work-items CRUD subset, states/labels/modules,
workspace members) and the comments coverage that originally lived
here as the "extras" gap. The upstream server is no longer launched.
"""

from __future__ import annotations

import os
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from .plane import DEFAULT_BASE_URL, PlaneClient

mcp = FastMCP("plane")


_PERSONA_ENV_RE = re.compile(r"^PLANE_API_KEY_([A-Z][A-Z0-9_]*)$")


def _persona_credentials() -> dict[str, dict[str, str]]:
    """Read per-persona credentials from the environment.

    Matches ``PLANE_API_KEY_<PERSONA_PREFIX>`` and pairs each token
    with the shared ``PLANE_BASE_URL`` + ``PLANE_WORKSPACE_SLUG``. The
    returned key is the canonical hyphen-separated username (e.g.
    ``business-analyst``); the upper-snake env prefix is the form
    ``bin/install.py`` emits via ``persona_env_prefix``.
    """
    workspace = os.environ.get("PLANE_WORKSPACE_SLUG")
    if not workspace:
        return {}
    base_url = os.environ.get("PLANE_BASE_URL") or DEFAULT_BASE_URL
    creds: dict[str, dict[str, str]] = {}
    for key, value in os.environ.items():
        match = _PERSONA_ENV_RE.match(key)
        if not match or not value:
            continue
        persona = match.group(1).lower().replace("_", "-")
        creds[persona] = {
            "api_key": value,
            "base_url": base_url,
            "workspace_slug": workspace,
        }
    return creds


def _persona_tool_prefix(persona: str) -> str:
    """``business-analyst`` → ``business_analyst`` (MCP tool name prefix)."""
    return persona.replace("-", "_")


def _register_persona_tools(persona: str, creds: dict[str, str]) -> None:
    """Define and register every Plane tool for one persona.

    The inner functions close over ``creds``; each call to this helper
    produces a fresh scope, so the closures route to the correct token
    for their persona.
    """
    prefix = _persona_tool_prefix(persona)

    def _client() -> PlaneClient:
        return PlaneClient(
            api_key=creds["api_key"],
            workspace_slug=creds["workspace_slug"],
            base_url=creds["base_url"],
        )

    # ----- workspace-scoped lookups -----

    @mcp.tool(name=f"{prefix}__list_projects")
    async def list_projects() -> list[dict[str, Any]]:
        """List projects in the workspace."""
        async with _client() as c:
            return await c.list_projects()

    @mcp.tool(name=f"{prefix}__list_workspace_members")
    async def list_workspace_members() -> list[dict[str, Any]]:
        """List members of the workspace (for assignee + author lookups)."""
        async with _client() as c:
            return await c.list_workspace_members()

    # ----- per-project metadata -----

    @mcp.tool(name=f"{prefix}__list_states")
    async def list_states(project_id: str) -> list[dict[str, Any]]:
        """List workflow states defined on a project."""
        async with _client() as c:
            return await c.list_states(project_id)

    @mcp.tool(name=f"{prefix}__list_labels")
    async def list_labels(project_id: str) -> list[dict[str, Any]]:
        """List labels defined on a project."""
        async with _client() as c:
            return await c.list_labels(project_id)

    @mcp.tool(name=f"{prefix}__list_modules")
    async def list_modules(project_id: str) -> list[dict[str, Any]]:
        """List modules defined on a project."""
        async with _client() as c:
            return await c.list_modules(project_id)

    # ----- work items -----

    @mcp.tool(name=f"{prefix}__list_work_items")
    async def list_work_items(
        project_id: str,
        state: str | None = None,
        assignees: str | None = None,
        labels: str | None = None,
        priority: str | None = None,
        per_page: int | None = None,
        cursor: str | None = None,
        expand: str | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """List work items in a project. Filters become query params;
        ``assignees`` and ``labels`` are comma-separated UUID strings.
        """
        async with _client() as c:
            return await c.list_work_items(
                project_id,
                state=state,
                assignees=assignees,
                labels=labels,
                priority=priority,
                per_page=per_page,
                cursor=cursor,
                expand=expand,
                order_by=order_by,
            )

    @mcp.tool(name=f"{prefix}__retrieve_work_item")
    async def retrieve_work_item(
        project_id: str, work_item_id: str
    ) -> dict[str, Any]:
        """Retrieve a work item. ``work_item_id`` accepts UUID or
        human-readable identifier (e.g. ``INT-1``).
        """
        async with _client() as c:
            return await c.retrieve_work_item(project_id, work_item_id)

    @mcp.tool(name=f"{prefix}__create_work_item")
    async def create_work_item(
        project_id: str,
        name: str,
        description_html: str | None = None,
        state: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
        parent: str | None = None,
        start_date: str | None = None,
        target_date: str | None = None,
        estimate_point: str | None = None,
    ) -> dict[str, Any]:
        """Create a work item. ``parent`` accepts UUID or identifier."""
        async with _client() as c:
            return await c.create_work_item(
                project_id,
                name=name,
                description_html=description_html,
                state=state,
                assignees=assignees,
                labels=labels,
                priority=priority,
                parent=parent,
                start_date=start_date,
                target_date=target_date,
                estimate_point=estimate_point,
            )

    @mcp.tool(name=f"{prefix}__update_work_item")
    async def update_work_item(
        project_id: str,
        work_item_id: str,
        name: str | None = None,
        description_html: str | None = None,
        state: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
        parent: str | None = None,
        start_date: str | None = None,
        target_date: str | None = None,
        estimate_point: str | None = None,
    ) -> dict[str, Any]:
        """Patch a work item — state transitions, handovers, etc. Only
        non-None fields are sent. ``work_item_id`` accepts UUID or
        identifier.
        """
        async with _client() as c:
            return await c.update_work_item(
                project_id,
                work_item_id,
                name=name,
                description_html=description_html,
                state=state,
                assignees=assignees,
                labels=labels,
                priority=priority,
                parent=parent,
                start_date=start_date,
                target_date=target_date,
                estimate_point=estimate_point,
            )

    # ----- comments -----

    @mcp.tool(name=f"{prefix}__add_comment")
    async def add_comment(
        project_id: str,
        work_item_id: str,
        comment_html: str,
        access: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment to a work item. ``work_item_id`` accepts UUID
        or identifier. ``access`` is optional and only honoured by
        newer Plane versions (``internal`` / ``external``).
        """
        async with _client() as c:
            return await c.add_comment(
                project_id,
                work_item_id,
                comment_html=comment_html,
                access=access,
            )

    @mcp.tool(name=f"{prefix}__list_comments")
    async def list_comments(
        project_id: str, work_item_id: str
    ) -> list[dict[str, Any]]:
        """List comments on a work item, in Plane's native order.
        ``work_item_id`` accepts UUID or identifier.
        """
        async with _client() as c:
            return await c.list_comments(project_id, work_item_id)


def register_personas_from_env() -> dict[str, dict[str, str]]:
    """Register tools for every persona found in the environment.

    Returns the credential map that was applied, so callers can decide
    whether to start the server (non-empty) or abort with a clear
    message (empty). Kept as a function rather than a module-level
    side effect so tests can drive it deterministically with
    ``monkeypatch.setenv``.
    """
    creds_by_persona = _persona_credentials()
    for persona, creds in creds_by_persona.items():
        _register_persona_tools(persona, creds)
    return creds_by_persona


def main() -> None:
    """Entry point for ``python -m plane_extras_mcp`` and the
    ``plane-extras-mcp`` console script. Refuses to start if no
    persona credentials were found — that means ``bin/install.py``
    hasn't been run yet against this consumer, and a server with zero
    tools would silently mask the misconfiguration.
    """
    if not register_personas_from_env():
        raise SystemExit(
            "plane-extras-mcp: no PLANE_API_KEY_<PERSONA> env vars found. "
            "Run `bin/install.py` against the consumer project so the "
            "rendered settings.local.json carries the per-persona tokens."
        )
    mcp.run()


if __name__ == "__main__":
    main()
