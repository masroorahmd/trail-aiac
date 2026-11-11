#!/usr/bin/env python3
"""PostToolUse hook: tell herdr that this session just handed work on.

A handover in Trail is a Plane write: the persona reassigns a work-item
(`update_work_item` / `create_work_item` with `assignees`). The next
persona's turn is still USER's to start, and that is a hard rule. What
USER lacks is the signal: in a herdr window with one tab per persona,
nothing shows that the RE tab now has work.

So after such a write this labels the *calling* terminal
`trail.handover=<to> <work-item ID> <unix time>`. The `trail` herdr mod
reads it, marks the receiving persona's tab in the same space, and
offers USER a click to go there (or to open that persona's tab). The
label sits on the sender, not the receiver, on purpose: no hook ever
writes to another session's terminal, and the sender's own state change
is what makes the mod look again.

The receiving persona comes from the assignee UUID, resolved through
the plane-id-cache's `members.by-email` (its local part is the persona
username). USER's own address resolves to `user`. A self-assignment, an
unknown UUID or a missing cache is no signal.

Best-effort and silent, like every herdr hook: it never blocks, never
fails the tool call, and does nothing outside herdr or with
`herdr.handover_signal: off`.
"""

import json
import os
import re
import sys
import time

import herdr_hc
from herdr_hc import config_value

CACHE = os.path.join(".claude", "cache", "plane-ids.yaml")
AGENTS_DIR = os.path.join(".claude", "agents")

SIGNAL_MODES = ("on", "off")
DEFAULT_SIGNAL_MODE = "on"

ID_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[0-9]+$")
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
MEMBER_RE = re.compile(rf"^\s+([A-Za-z0-9._%+-]+)@[^:\s]+:\s*({UUID})\s*$")
PROJECT_RE = re.compile(rf"^\s{{4}}([A-Z][A-Z0-9]{{1,9}}):\s*$")
PROJECT_ID_RE = re.compile(rf"^\s{{6}}id:\s*({UUID})\s*$")


def cache_lines(root):
    try:
        with open(os.path.join(root, CACHE), encoding="utf-8") as handle:
            return handle.read().splitlines()
    except OSError:
        return []


def members(lines):
    """UUID → local part of the member's email, from `by-email`."""
    found = {}
    inside = False
    for line in lines:
        if line.strip() == "by-email:":
            inside = True
            continue
        if not inside:
            continue
        entry = MEMBER_RE.match(line)
        if entry:
            found[entry.group(2)] = entry.group(1)
        elif line.strip():
            break
    return found


def project_identifier(lines, project_id):
    """`CRTHVN` for a project UUID, or the argument if it already is one."""
    if re.match(r"^[A-Z][A-Z0-9]{1,9}$", project_id or ""):
        return project_id
    current = None
    for line in lines:
        head = PROJECT_RE.match(line)
        if head:
            current = head.group(1)
            continue
        entry = PROJECT_ID_RE.match(line)
        if entry and current and entry.group(1) == project_id:
            return current
    return None


def response_item(response):
    """The work-item dict an MCP tool returned, however it is wrapped."""
    if isinstance(response, dict) and "content" in response:
        response = response["content"]
    if isinstance(response, list):
        for block in response:
            if isinstance(block, dict) and block.get("type") == "text":
                response = block.get("text")
                break
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return {}
    if isinstance(response, dict) and isinstance(response.get("result"), dict):
        response = response["result"]
    return response if isinstance(response, dict) else {}


def work_item_id(args, item, lines):
    """`CRTHVN-198`, from the call's own argument or from the reply."""
    given = args.get("work_item_id") or ""
    if ID_RE.match(given):
        return given
    sequence = item.get("sequence_id")
    project = project_identifier(lines, args.get("project_id"))
    if sequence and project:
        return f"{project}-{sequence}"
    return None


def personas(root):
    try:
        return {
            name[:-3]
            for name in os.listdir(os.path.join(root, AGENTS_DIR))
            if name.endswith(".md")
        }
    except OSError:
        return set()


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    args = payload.get("tool_input") or {}
    assignees = args.get("assignees") or []
    if not assignees:
        return 0

    root = payload.get("cwd") or os.getcwd()
    if config_value(
        root, "herdr", "handover_signal", SIGNAL_MODES, DEFAULT_SIGNAL_MODE
    ) == "off":
        return 0
    found = herdr_hc.terminal(root)
    if not found:
        return 0
    hc, address = found

    lines = cache_lines(root)
    names = members(lines)
    known = personas(root)
    sender = args.get("persona")
    receiver = None
    for uuid in assignees:
        name = names.get(uuid)
        if not name or name == sender:
            continue
        receiver = name if name in known else "user"
        break
    if not receiver:
        return 0

    item = work_item_id(args, response_item(payload.get("tool_response")), lines)
    if not item:
        return 0

    herdr_hc.label(
        hc, address, {"trail.handover": f"{receiver} {item} {int(time.time())}"}
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
