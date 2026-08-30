"""FastMCP server exposing every Plane tool the persona team needs.

Multi-tenant by design: one stdio process serves all configured
personas. At startup the server scans the environment for
``PLANE_API_KEY_<PERSONA_PREFIX>`` variables and registers **one** tool
set — every tool takes a ``persona`` argument naming whose turn it is,
and the call lands in Plane authored by that persona regardless of
which model session invoked it.

The identity used to live in the tool *name*
(``business_analyst__list_states``), which meant registering all 26
tools once per persona: 286 tools whose schemas measured 179 KB
(~45k tokens) in the system prompt of every session, on every turn, so
that one persona could reach the 26 it actually holds. Moving the
identity into an argument leaves 26 tools and ~4k tokens. What the
prefix appeared to guarantee — a persona cannot reach another
persona's tools — was never enforced by anything but the prompt asking
it to; ``.claude/hooks/plane-persona-guard.py`` now checks the argument
against the persona USER actually started, which is a check the tool
name could not perform.

This also replaces the older one-process-per-persona layout, which
spawned ~22 stdio MCP servers per Claude session (upstream
``plane-mcp-server`` + ``plane-extras-mcp``, both xN personas) and
consumed ~2 GB of RSS. The tool surface here is the union of the
upstream ``plane-mcp-server`` operations the persona prompts actually
reference (projects, work-items CRUD subset, states/labels/modules,
workspace members) and the comments coverage that originally lived
here as the "extras" gap. The upstream server is no longer launched.
"""

from __future__ import annotations

import html
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


# Comment fields a persona ever reads. Plane returns ~15 more (workspace,
# project, issue, external_id, updated_by, …) that are pure overhead in a
# reader's context, plus `comment_json` — the Tiptap document the editor
# round-trips. Measured on a real 9-comment thread: the metadata is 8% of
# the payload and the text 90%, so the projection alone is not the win.
_COMMENT_KEEP_FIELDS = ("id", "created_at")

_COMMENT_BODY_FIELDS = ("comment_html", "comment_stripped", "comment")

# How much of a long comment `list_comments` shows before pointing at
# `retrieve_comment`. `comment_full_bytes` is the "short enough to send
# whole" line; anything above it is cut to `comment_head_bytes`. Trail's
# comment convention puts the author and the kind of artefact on the first
# line ("Security review (security-reviewer)"), so a head of a few hundred
# bytes is enough to pick the one comment a pickup step actually names.
# bin/install.py renders both from the consumer's `reading:` config.
_COMMENT_FULL_BYTES = int(os.environ.get("PLANE_COMMENT_FULL_BYTES") or 2000)
_COMMENT_HEAD_BYTES = int(os.environ.get("PLANE_COMMENT_HEAD_BYTES") or 600)

_BLOCK_END_RE = re.compile(r"(?i)</(p|div|li|h[1-6]|tr|blockquote|pre)>")
_LIST_ITEM_RE = re.compile(r"(?i)<li[^>]*>")
_HEADING_RE = re.compile(r"(?i)<h([1-6])[^>]*>")
_BREAK_RE = re.compile(r"(?i)<br\s*/?>")
_DROP_ELEMENT_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(value: str | None) -> str:
    """Plane's stored comment HTML as the plain text an agent reads.

    Not a general HTML renderer: it keeps the structure that carries
    meaning in a handover comment — paragraph and list breaks, heading
    level — and drops everything else. `comment_stripped` would be the
    obvious field to read instead, but Plane leaves it empty on a
    self-hosted 1.3.0 deployment, so the markup is where the text lives.
    """
    if not value:
        return ""
    text = _DROP_ELEMENT_RE.sub("", value)
    text = _BREAK_RE.sub("\n", text)
    text = _HEADING_RE.sub(lambda m: "\n" + "#" * int(m.group(1)) + " ", text)
    text = _LIST_ITEM_RE.sub("- ", text)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _ANY_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _condense_comments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project and shorten a comment listing.

    Same contract `_strip_descriptions` gives work-item listings, and the
    same reason: a pickup step names ONE comment ("read SR's findings"),
    but the only way to reach it is a listing that returns every comment
    whole. On a real thread that is ~20k tokens to read ~2.6k worth — paid
    on every persona turn, because a handover starts with a fresh context.

    A body over the threshold is cut to its head and marked truncated;
    `retrieve_comment` fetches that one in full.
    """
    condensed = []
    for item in items:
        kept: dict[str, Any] = {
            k: v for k, v in item.items() if k in _COMMENT_KEEP_FIELDS
        }
        body = next(
            (item[f] for f in _COMMENT_BODY_FIELDS if item.get(f)), None
        )
        text = _html_to_text(body)
        if len(text) > _COMMENT_FULL_BYTES:
            kept["comment"] = text[:_COMMENT_HEAD_BYTES]
            kept["truncated"] = True
            kept["full_length"] = len(text)
            kept["note"] = (
                "Head only. Call retrieve_comment with this id for the "
                "full text — do not act on the excerpt alone."
            )
        else:
            kept["comment"] = text
        condensed.append(kept)
    return condensed


_ESCAPED_TAG_RE = re.compile(r"&lt;/?[A-Za-z][A-Za-z0-9]*(?:\s[^&<>]*?)?/?&gt;")
_REAL_TAG_RE = re.compile(r"<[A-Za-z/]")

ENCODING_REPAIR_NOTE = (
    "Your HTML arrived entity-escaped (&lt;p&gt; instead of <p>) and was "
    "unescaped before the write, so what Plane stored is correct markup — "
    "do NOT resend or supersede this. Pass real tags next time."
)


def _repair_double_encoded_html(value: str | None) -> tuple[str | None, bool]:
    """Undo a wholly entity-escaped HTML payload before it reaches Plane.

    The single most common persona slip is sending ``&lt;p&gt;…`` instead
    of ``<p>…`` — it looks like caution, and Plane stores the entities and
    renders the tags as visible text. Comments cannot be edited or deleted,
    and a work-item body is written once and never touched again, so the
    only repairs available downstream are a supersede comment or a second
    write of the same body — which is exactly the duplicate-timestamp mess
    this guard exists to prevent. Catching it here means the bad value
    never lands.

    The signature is narrow on purpose: two or more escaped tags and no
    real tag at all. Content that *deliberately* shows markup as text —
    ``a &lt; b``, an XML snippet inside a ``<code>`` block, a lone
    ``&lt;title&gt;`` in prose — carries a real tag around it, or too few
    escaped ones, and is left alone.

    One unescape pass is the exact inverse of one escape pass, so entities
    the author meant to survive stay escaped: ``&amp;rarr;`` comes back as
    ``&rarr;``, which is what Plane renders as →. Deeper encodings hide the
    ``&lt;`` marker behind ``&amp;lt;`` and are deliberately *not* guessed
    at — a second blind pass would corrupt an innocent ``a &amp; b``.

    Returns the value to send plus whether anything was changed.
    """
    if not value or _REAL_TAG_RE.search(value):
        return value, False
    if len(_ESCAPED_TAG_RE.findall(value)) < 2:
        return value, False
    return html.unescape(value), True


def _note_repair(result: dict[str, Any], repaired: bool) -> dict[str, Any]:
    """Tell the caller its payload was fixed, so it does not "fix" it again."""
    if repaired and isinstance(result, dict):
        result = {**result, "trail_encoding_note": ENCODING_REPAIR_NOTE}
    return result


def _note_relations(
    result: dict[str, Any],
    refs: list[str],
    asked: str,
) -> dict[str, Any]:
    """Say which pairs the write left alone, in the caller's own ids.

    Plane answers a duplicate `add_relation` with success, so a persona
    that reports from the response reports a dependency the board does
    not carry. The client hands us the pairs it found already related
    (UUIDs, in the order the refs were passed); this names them back as
    `DEV-42` rather than as a UUID nobody typed.
    """
    if not isinstance(result, dict) or "already_related" not in result:
        return result
    held = result.pop("already_related")
    if held is None:
        result["trail_relation_note"] = (
            "The pre-write relation read failed, so it is unknown whether "
            "any of these pairs was already related. Plane does not replace "
            "an existing relation and reports success either way — confirm "
            "with list_relations before you report this dependency."
        )
        return result
    by_uuid = dict(zip(result.get("related") or [], refs))
    stale = [
        f"{by_uuid.get(uuid, uuid)} was already {kind} and stayed {kind}"
        for uuid, kind in held.items()
    ]
    result["trail_relation_note"] = (
        "Plane does not replace an existing relation: "
        + "; ".join(stale)
        + f". Nothing was stored as {asked} for those. The response above "
        "reports what was asked for, not what is on the board — a human "
        "must change it in the Plane UI."
    )
    return result


_PERSONA_NOTE = (
    "\n\n``persona`` is the username of the persona making the call — the "
    "one whose `/<persona>` command is running (e.g. "
    "``backend-developer``). It decides which Plane token authors the "
    "call, so it is your own name, never the receiver's."
)


def _tool(fn):
    """Register one tool under its plain function name.

    Appends the ``persona`` note to the docstring here rather than in 26
    docstrings: the tools differ in what they do, not in what that
    argument means.
    """
    fn.__doc__ = (fn.__doc__ or "").rstrip() + _PERSONA_NOTE
    return mcp.tool(name=fn.__name__)(fn)


def _register_tools(creds_by_persona: dict[str, dict[str, str]]) -> None:
    """Define and register the tool set once, for every persona at once.

    ``persona`` is a *parameter*, not a name prefix. The earlier layout
    registered all 26 tools per configured persona — 286 tools, whose
    JSON schemas measured 179 KB (~45k tokens) in the system prompt of
    every session, on every turn, to serve one persona holding 26 of
    them. The identity that a prefix used to carry now travels in the
    argument, and `.claude/hooks/plane-persona-guard.py` is what holds
    it: the argument is checked against the persona USER actually
    started, which a tool name never was.
    """
    known = ", ".join(sorted(creds_by_persona))

    def _client(persona: str) -> PlaneClient:
        key = (persona or "").strip().lower().replace("_", "-")
        creds = creds_by_persona.get(key)
        if creds is None:
            raise ValueError(
                f"unknown persona {persona!r}. Pass the username of the "
                f"persona whose turn this is, exactly as spelled here: "
                f"{known}."
            )
        return PlaneClient(
            api_key=creds["api_key"],
            workspace_slug=creds["workspace_slug"],
            base_url=creds["base_url"],
        )

    # ----- workspace-scoped lookups -----

    @_tool
    async def list_projects(persona: str) -> list[dict[str, Any]]:
        """List projects in the workspace."""
        async with _client(persona) as c:
            return await c.list_projects()

    @_tool
    async def list_workspace_members(persona: str) -> list[dict[str, Any]]:
        """List members of the workspace (for assignee + author lookups)."""
        async with _client(persona) as c:
            return await c.list_workspace_members()

    # ----- per-project metadata -----

    @_tool
    async def list_states(persona: str, project_id: str) -> list[dict[str, Any]]:
        """List workflow states defined on a project."""
        async with _client(persona) as c:
            return await c.list_states(project_id)

    @_tool
    async def list_labels(persona: str, project_id: str) -> list[dict[str, Any]]:
        """List labels defined on a project."""
        async with _client(persona) as c:
            return await c.list_labels(project_id)

    @_tool
    async def list_modules(persona: str, project_id: str) -> list[dict[str, Any]]:
        """List modules defined on a project."""
        async with _client(persona) as c:
            return await c.list_modules(project_id)

    # ----- work items -----

    @_tool
    async def list_work_items(
        persona: str,
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
        async with _client(persona) as c:
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

    @_tool
    async def retrieve_work_item(
        persona: str,
        project_id: str, work_item_id: str, expand: str | None = None
    ) -> dict[str, Any]:
        """Retrieve a work item. ``work_item_id`` accepts UUID or
        human-readable identifier (e.g. ``INT-1``).

        ``expand`` is a comma-separated list — pass
        ``"state,labels,assignees"`` to get those as objects instead of
        bare ids or null. That is the call to make when you need to
        CONFIRM a write: a create or update response can serialise
        ``assignees`` as ``[]`` on an assignment that landed, and an
        unassigned ticket is on nobody's list.
        """
        async with _client(persona) as c:
            return await c.retrieve_work_item(
                project_id, work_item_id, expand=expand
            )

    @_tool
    async def create_work_item(
        persona: str,
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
        """Create a work item. ``parent`` accepts UUID or identifier.
        ``description_html`` takes real HTML; an entity-escaped body is
        unescaped before the write rather than stored as visible markup.
        """
        description_html, repaired = _repair_double_encoded_html(description_html)
        async with _client(persona) as c:
            result = await c.create_work_item(
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
        return _note_repair(result, repaired)

    @_tool
    async def update_work_item(
        persona: str,
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
        identifier. An entity-escaped ``description_html`` is unescaped
        before the write.
        """
        description_html, repaired = _repair_double_encoded_html(description_html)
        async with _client(persona) as c:
            result = await c.update_work_item(
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
        return _note_repair(result, repaired)

    # ----- comments -----

    @_tool
    async def add_comment(
        persona: str,
        project_id: str,
        work_item_id: str,
        comment_html: str,
        access: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment to a work item. ``work_item_id`` accepts UUID
        or identifier. ``comment_html`` takes real HTML; an entity-escaped
        comment is unescaped before the write, because comments cannot be
        edited or deleted afterwards. ``access`` is optional and only
        honoured by newer Plane versions (``internal`` / ``external``).
        """
        comment_html, repaired = _repair_double_encoded_html(comment_html)
        async with _client(persona) as c:
            result = await c.add_comment(
                project_id,
                work_item_id,
                comment_html=comment_html,
                access=access,
            )
        return _note_repair(result, repaired)

    @_tool
    async def list_comments(
        persona: str,
        project_id: str, work_item_id: str
    ) -> list[dict[str, Any]]:
        """List comments on a work item, in Plane's native order.

        Bodies come back as plain text, and a long one is cut to its head
        and flagged ``truncated`` — the first line carries the author and
        the kind of artefact, which is what a pickup step selects on. Use
        ``retrieve_comment`` for the full text of the one you need.
        ``work_item_id`` accepts UUID or identifier.
        """
        async with _client(persona) as c:
            return _condense_comments(
                await c.list_comments(project_id, work_item_id)
            )

    @_tool
    async def retrieve_comment(
        persona: str,
        project_id: str, work_item_id: str, comment_id: str
    ) -> dict[str, Any]:
        """Retrieve one comment in full, as plain text.

        The counterpart to ``list_comments``: read the listing, pick the
        comment your pickup step names, fetch it here.
        """
        async with _client(persona) as c:
            result = await c.retrieve_comment(
                project_id, work_item_id, comment_id
            )
        body = next(
            (result[f] for f in _COMMENT_BODY_FIELDS if result.get(f)), None
        )
        return {
            **{k: v for k, v in result.items() if k in _COMMENT_KEEP_FIELDS},
            "comment": _html_to_text(body),
        }

    # ----- cycles (sprints) -----

    @_tool
    async def list_cycles(persona: str, project_id: str) -> list[dict[str, Any]]:
        """List cycles (sprints) defined on a project."""
        async with _client(persona) as c:
            return await c.list_cycles(project_id)

    @_tool
    async def retrieve_cycle(
        persona: str,
        project_id: str, cycle_id: str
    ) -> dict[str, Any]:
        """Retrieve one cycle by UUID (metadata + progress counters)."""
        async with _client(persona) as c:
            return await c.retrieve_cycle(project_id, cycle_id)

    @_tool
    async def create_cycle(
        persona: str,
        project_id: str,
        name: str,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a cycle. ``start_date`` / ``end_date`` are ISO
        ``YYYY-MM-DD``; Plane requires both dates together or neither.
        """
        async with _client(persona) as c:
            return await c.create_cycle(
                project_id,
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date,
            )

    @_tool
    async def update_cycle(
        persona: str,
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
        async with _client(persona) as c:
            return await c.update_cycle(
                project_id,
                cycle_id,
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date,
            )

    @_tool
    async def delete_cycle(persona: str, project_id: str, cycle_id: str) -> dict[str, Any]:
        """Delete a cycle. The work items it held are not deleted — they
        only leave the cycle. Irreversible; prefer transferring unfinished
        items to another cycle first.
        """
        async with _client(persona) as c:
            await c.delete_cycle(project_id, cycle_id)
            return {"deleted": cycle_id}

    @_tool
    async def list_cycle_work_items(
        persona: str,
        project_id: str, cycle_id: str, include_description: bool = False
    ) -> list[dict[str, Any]]:
        """List the work items assigned to a cycle. Body fields are
        omitted by default; use ``retrieve_work_item`` for full bodies.
        """
        async with _client(persona) as c:
            items = await c.list_cycle_work_items(project_id, cycle_id)
        return items if include_description else _strip_descriptions(items)

    @_tool
    async def add_work_items_to_cycle(
        persona: str,
        project_id: str, cycle_id: str, work_item_ids: list[str]
    ) -> dict[str, Any]:
        """Add one or more work items to a cycle. Each entry of
        ``work_item_ids`` accepts a UUID or human identifier (e.g.
        ``DEV-12``). A work item lives in at most one cycle — adding it
        to a new cycle moves it.
        """
        async with _client(persona) as c:
            await c.add_work_items_to_cycle(
                project_id, cycle_id, work_item_ids
            )
        # Plane answers this POST with a list of membership links, which
        # used to fail the declared dict output schema AFTER a successful
        # write (the "DictModel validation error" false negative). Return
        # a summary we construct ourselves instead.
        return {"added": work_item_ids, "cycle_id": cycle_id}

    @_tool
    async def remove_work_item_from_cycle(
        persona: str,
        project_id: str, cycle_id: str, work_item_id: str
    ) -> dict[str, Any]:
        """Remove a single work item from a cycle. ``work_item_id``
        accepts a UUID or human identifier. The work item is not deleted.
        """
        async with _client(persona) as c:
            await c.remove_work_item_from_cycle(
                project_id, cycle_id, work_item_id
            )
            return {"removed": work_item_id, "cycle": cycle_id}

    @_tool
    async def transfer_cycle_work_items(
        persona: str,
        project_id: str, cycle_id: str, new_cycle_id: str
    ) -> dict[str, Any]:
        """Transfer the *incomplete* work items of one cycle into another
        — Plane's "carry unfinished work into the next sprint" action.
        ``new_cycle_id`` is the destination cycle's UUID.
        """
        async with _client(persona) as c:
            return await c.transfer_cycle_work_items(
                project_id, cycle_id, new_cycle_id
            )

    # ----- modules (membership) -----

    @_tool
    async def list_module_work_items(
        persona: str,
        project_id: str, module_id: str, include_description: bool = False
    ) -> list[dict[str, Any]]:
        """List the work items assigned to a module. Body fields are
        omitted by default; use ``retrieve_work_item`` for full bodies.
        """
        async with _client(persona) as c:
            items = await c.list_module_work_items(project_id, module_id)
        return items if include_description else _strip_descriptions(items)

    @_tool
    async def add_work_items_to_module(
        persona: str,
        project_id: str, module_id: str, work_item_ids: list[str]
    ) -> dict[str, Any]:
        """Add one or more work items to a module. Each entry of
        ``work_item_ids`` accepts a UUID or human identifier (e.g.
        ``DEV-12``). A work item may belong to several modules at once —
        adding it here leaves its other module memberships intact.
        """
        async with _client(persona) as c:
            await c.add_work_items_to_module(
                project_id, module_id, work_item_ids
            )
        # See add_work_items_to_cycle: Plane answers with a list; return
        # a self-constructed summary so the dict output schema holds.
        return {"added": work_item_ids, "module_id": module_id}

    @_tool
    async def remove_work_item_from_module(
        persona: str,
        project_id: str, module_id: str, work_item_id: str
    ) -> dict[str, Any]:
        """Remove a single work item from a module. ``work_item_id``
        accepts a UUID or human identifier. The work item itself is not
        deleted, and its other module memberships are untouched.
        """
        async with _client(persona) as c:
            await c.remove_work_item_from_module(
                project_id, module_id, work_item_id
            )
            return {"removed": work_item_id, "module": module_id}

    # ----- relations (blocked_by / blocking / duplicate / relates_to) -----

    @_tool
    async def list_relations(
        persona: str,
        project_id: str, work_item_id: str
    ) -> dict[str, Any]:
        """List a work item's relations, grouped by type (``blocking``,
        ``blocked_by``, ``duplicate``, ``relates_to``, ``start_*``,
        ``finish_*``). ``work_item_id`` accepts UUID or identifier.
        """
        async with _client(persona) as c:
            return await c.list_relations(project_id, work_item_id)

    @_tool
    async def add_relation(
        persona: str,
        project_id: str,
        work_item_id: str,
        relation_type: str,
        related_work_item_ids: list[str],
    ) -> dict[str, Any]:
        """Relate a work item to one or more others — e.g.
        ``relation_type="blocked_by"`` to record a dependency that
        previously required a manual Plane-UI step. All ids accept UUID
        or identifier.

        Two things Plane will not do for you. It has no relation
        *removal* endpoint, so undoing one stays a manual UI step. And
        it does not REPLACE an existing relation: a pair that already
        carries one absorbs this call silently, with no error and a
        response that still names the type you asked for. That case
        comes back as ``trail_relation_note`` — report what the note
        says, never the type in the response.
        """
        async with _client(persona) as c:
            result = await c.add_relation(
                project_id,
                work_item_id,
                relation_type=relation_type,
                related_work_item_refs=related_work_item_ids,
            )
        return _note_relations(result, related_work_item_ids, relation_type)


def register_personas_from_env() -> dict[str, dict[str, str]]:
    """Register the tool set against every persona found in the environment.

    Returns the credential map that was applied, so callers can decide
    whether to start the server (non-empty) or abort with a clear
    message (empty). Kept as a function rather than a module-level
    side effect so tests can drive it deterministically with
    ``monkeypatch.setenv``.
    """
    creds_by_persona = _persona_credentials()
    if creds_by_persona:
        _register_tools(creds_by_persona)
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
