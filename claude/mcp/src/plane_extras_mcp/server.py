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

import logging
import os
import re
import sys
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


_DESCRIPTION_FIELDS = (
    "description_html",
    "description_binary",
    "description_stripped",
    "description",
)


def _strip_descriptions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop body fields from list responses.

    Work-item bodies routinely run 10–80 KB of HTML each; a 100-item
    list page can exceed 2 MB, which blows the caller's context for a
    listing it only needed ids/names/states from. Listing tools strip
    bodies by default; ``retrieve_work_item`` returns the full body.
    """
    return [
        {k: v for k, v in item.items() if k not in _DESCRIPTION_FIELDS}
        for item in items
    ]


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
        include_description: bool = False,
    ) -> list[dict[str, Any]]:
        """List work items in a project. Filters become query params;
        ``assignees`` and ``labels`` are comma-separated UUID strings.
        Body fields are omitted by default (a 100-item page otherwise
        exceeds 2 MB); set ``include_description=true`` only when you
        truly need every body, else use ``retrieve_work_item``.
        """
        async with _client() as c:
            items = await c.list_work_items(
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
        return items if include_description else _strip_descriptions(items)

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

    # ----- cycles (sprints) -----

    @mcp.tool(name=f"{prefix}__list_cycles")
    async def list_cycles(project_id: str) -> list[dict[str, Any]]:
        """List cycles (sprints) defined on a project."""
        async with _client() as c:
            return await c.list_cycles(project_id)

    @mcp.tool(name=f"{prefix}__retrieve_cycle")
    async def retrieve_cycle(
        project_id: str, cycle_id: str
    ) -> dict[str, Any]:
        """Retrieve one cycle by UUID (metadata + progress counters)."""
        async with _client() as c:
            return await c.retrieve_cycle(project_id, cycle_id)

    @mcp.tool(name=f"{prefix}__create_cycle")
    async def create_cycle(
        project_id: str,
        name: str,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a cycle. ``start_date`` / ``end_date`` are ISO
        ``YYYY-MM-DD``; Plane requires both dates together or neither.
        """
        async with _client() as c:
            return await c.create_cycle(
                project_id,
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date,
            )

    @mcp.tool(name=f"{prefix}__update_cycle")
    async def update_cycle(
        project_id: str,
        cycle_id: str,
        name: str | None = None,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Patch a cycle. Only non-None fields are sent, so a date-only
        reschedule leaves the name untouched.
        """
        async with _client() as c:
            return await c.update_cycle(
                project_id,
                cycle_id,
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date,
            )

    @mcp.tool(name=f"{prefix}__delete_cycle")
    async def delete_cycle(project_id: str, cycle_id: str) -> dict[str, Any]:
        """Delete a cycle. The work items it held are not deleted — they
        only leave the cycle. Irreversible; prefer transferring unfinished
        items to another cycle first.
        """
        async with _client() as c:
            await c.delete_cycle(project_id, cycle_id)
            return {"deleted": cycle_id}

    @mcp.tool(name=f"{prefix}__list_cycle_work_items")
    async def list_cycle_work_items(
        project_id: str, cycle_id: str, include_description: bool = False
    ) -> list[dict[str, Any]]:
        """List the work items assigned to a cycle. Body fields are
        omitted by default; use ``retrieve_work_item`` for full bodies.
        """
        async with _client() as c:
            items = await c.list_cycle_work_items(project_id, cycle_id)
        return items if include_description else _strip_descriptions(items)

    @mcp.tool(name=f"{prefix}__add_work_items_to_cycle")
    async def add_work_items_to_cycle(
        project_id: str, cycle_id: str, work_item_ids: list[str]
    ) -> dict[str, Any]:
        """Add one or more work items to a cycle. Each entry of
        ``work_item_ids`` accepts a UUID or human identifier (e.g.
        ``DEV-12``). A work item lives in at most one cycle — adding it
        to a new cycle moves it.
        """
        async with _client() as c:
            await c.add_work_items_to_cycle(
                project_id, cycle_id, work_item_ids
            )
        # Plane answers this POST with a list of membership links, which
        # used to fail the declared dict output schema AFTER a successful
        # write (the "DictModel validation error" false negative). Return
        # a summary we construct ourselves instead.
        return {"added": work_item_ids, "cycle_id": cycle_id}

    @mcp.tool(name=f"{prefix}__remove_work_item_from_cycle")
    async def remove_work_item_from_cycle(
        project_id: str, cycle_id: str, work_item_id: str
    ) -> dict[str, Any]:
        """Remove a single work item from a cycle. ``work_item_id``
        accepts a UUID or human identifier. The work item is not deleted.
        """
        async with _client() as c:
            await c.remove_work_item_from_cycle(
                project_id, cycle_id, work_item_id
            )
            return {"removed": work_item_id, "cycle": cycle_id}

    @mcp.tool(name=f"{prefix}__transfer_cycle_work_items")
    async def transfer_cycle_work_items(
        project_id: str, cycle_id: str, new_cycle_id: str
    ) -> dict[str, Any]:
        """Transfer the *incomplete* work items of one cycle into another
        — Plane's "carry unfinished work into the next sprint" action.
        ``new_cycle_id`` is the destination cycle's UUID.
        """
        async with _client() as c:
            return await c.transfer_cycle_work_items(
                project_id, cycle_id, new_cycle_id
            )

    # ----- modules (membership) -----

    @mcp.tool(name=f"{prefix}__list_module_work_items")
    async def list_module_work_items(
        project_id: str, module_id: str, include_description: bool = False
    ) -> list[dict[str, Any]]:
        """List the work items assigned to a module. Body fields are
        omitted by default; use ``retrieve_work_item`` for full bodies.
        """
        async with _client() as c:
            items = await c.list_module_work_items(project_id, module_id)
        return items if include_description else _strip_descriptions(items)

    @mcp.tool(name=f"{prefix}__add_work_items_to_module")
    async def add_work_items_to_module(
        project_id: str, module_id: str, work_item_ids: list[str]
    ) -> dict[str, Any]:
        """Add one or more work items to a module. Each entry of
        ``work_item_ids`` accepts a UUID or human identifier (e.g.
        ``DEV-12``). A work item may belong to several modules at once —
        adding it here leaves its other module memberships intact.
        """
        async with _client() as c:
            await c.add_work_items_to_module(
                project_id, module_id, work_item_ids
            )
        # See add_work_items_to_cycle: Plane answers with a list; return
        # a self-constructed summary so the dict output schema holds.
        return {"added": work_item_ids, "module_id": module_id}

    @mcp.tool(name=f"{prefix}__remove_work_item_from_module")
    async def remove_work_item_from_module(
        project_id: str, module_id: str, work_item_id: str
    ) -> dict[str, Any]:
        """Remove a single work item from a module. ``work_item_id``
        accepts a UUID or human identifier. The work item itself is not
        deleted, and its other module memberships are untouched.
        """
        async with _client() as c:
            await c.remove_work_item_from_module(
                project_id, module_id, work_item_id
            )
            return {"removed": work_item_id, "module": module_id}

    # ----- relations (blocked_by / blocking / duplicate / relates_to) -----

    @mcp.tool(name=f"{prefix}__list_relations")
    async def list_relations(
        project_id: str, work_item_id: str
    ) -> dict[str, Any]:
        """List a work item's relations, grouped by type (``blocking``,
        ``blocked_by``, ``duplicate``, ``relates_to``, ``start_*``,
        ``finish_*``). ``work_item_id`` accepts UUID or identifier.
        """
        async with _client() as c:
            return await c.list_relations(project_id, work_item_id)

    @mcp.tool(name=f"{prefix}__add_relation")
    async def add_relation(
        project_id: str,
        work_item_id: str,
        relation_type: str,
        related_work_item_ids: list[str],
    ) -> dict[str, Any]:
        """Relate a work item to one or more others — e.g.
        ``relation_type="blocked_by"`` to record a dependency that
        previously required a manual Plane-UI step. All ids accept UUID
        or identifier. Note: Plane's public API has no relation
        *removal* endpoint — undoing a relation stays a manual UI step,
        so add relations deliberately.
        """
        async with _client() as c:
            return await c.add_relation(
                project_id,
                work_item_id,
                relation_type=relation_type,
                related_work_item_refs=related_work_item_ids,
            )


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
    # stdout is the MCP protocol channel, so diagnostics go to stderr —
    # which the MCP client captures into its own per-server log. A
    # no-op if the host application already configured logging.
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(message)s",
    )
    if not register_personas_from_env():
        raise SystemExit(
            "plane-extras-mcp: no PLANE_API_KEY_<PERSONA> env vars found. "
            "Run `bin/install.py` against the consumer project so the "
            "rendered settings.local.json carries the per-persona tokens."
        )
    mcp.run()


if __name__ == "__main__":
    main()
