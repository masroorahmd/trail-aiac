#!/usr/bin/env python3
"""PreToolUse guard: a Plane call is authored by the persona in role.

Every Plane tool takes a `persona` argument that decides which API
token — and therefore which Plane account — authors the call. The tool
names used to carry that identity instead
(`business_analyst__add_comment`), one full tool set per persona, which
cost 286 tool schemas in every session's system prompt to express a
constraint no code ever checked: nothing stopped the main loop calling
another persona's tool, the prompt merely asked it not to.

This checks it. `persona-pin.py` records which `/<persona>` command
USER started; a Plane call whose `persona` argument disagrees is denied.
That is a stronger guarantee than the prefix gave, in ~4k tokens
instead of ~45k.

How hard it holds is the consumer's call —
`hooks.persona_identity` in `.claude/config.yaml`:

  strict (default)  Deny the mismatch. The persona contract says a role
                    ends when USER starts a different `/<persona>`, so a
                    call under another name is a bug in every case the
                    guard can actually see.
  ask               Put the mismatch to USER as a permission prompt.
  off               No check.

Fails open in every uncertain case — no pin, no config, a session with
no `/<persona>` yet, a lane that runs several personas (`/autopilot`,
`/quick`, `/kickoff` pin `*`). A missed check costs a wrongly-attributed
comment; a false deny stops work USER asked for, and the second is the
worse trade in a guard that runs on every Plane call.

Deliberately dependency-free (no PyYAML, no `uv`): it fires on every
Plane tool call, so its start-up cost is paid often enough to matter.
"""

import json
import os
import re
import sys

CONFIG = os.path.join(".claude", "config.yaml")
PIN_DIR = os.path.join(".claude", "cache", "persona")

SAFE_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

TOOL_PREFIX = "mcp__plane__"
ANY = "*"

MODES = ("strict", "ask", "off")
DEFAULT_MODE = "strict"


def mode(root):
    """`hooks.persona_identity`, defaulting for configs seeded before it."""
    try:
        with open(os.path.join(root, CONFIG), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return DEFAULT_MODE

    inside = False
    for line in lines:
        if re.match(r"^hooks:\s*(#.*)?$", line):
            inside = True
            continue
        if not inside:
            continue
        entry = re.match(r"^\s+persona_identity:\s*([a-z-]+)\s*(#.*)?$", line)
        if entry and entry.group(1) in MODES:
            return entry.group(1)
        if line.strip() and not line.startswith((" ", "\t")):
            break
    return DEFAULT_MODE


def pinned_persona(root, session_id):
    """The persona USER started in *this* session, or None.

    Each session has its own pin file, so a second Claude session in the
    same repo neither weakens this one's check nor inherits its role.
    None means "no constraint known" — a session that has not run a
    `/<persona>` yet, or an unreadable pin.
    """
    if not SAFE_SESSION_RE.match(session_id or ""):
        return None
    path = os.path.join(root, PIN_DIR, f"{session_id}.json")
    try:
        with open(path, encoding="utf-8") as handle:
            pin = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(pin, dict):
        return None
    persona = pin.get("persona")
    return persona if isinstance(persona, str) and persona else None


def normalise(value):
    return (value or "").strip().lower().replace("_", "-")


def decide(decision, reason):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if not (payload.get("tool_name") or "").startswith(TOOL_PREFIX):
        return 0

    root = payload.get("cwd") or os.getcwd()
    setting = mode(root)
    if setting == "off":
        return 0

    pinned = pinned_persona(root, payload.get("session_id") or "")
    if pinned is None or pinned == ANY:
        return 0

    called = normalise((payload.get("tool_input") or {}).get("persona"))
    if not called or called == normalise(pinned):
        return 0

    verb = (payload.get("tool_name") or "")[len(TOOL_PREFIX):] or "this call"
    reason = (
        f"`{verb}` was called as **{called}**, but USER started "
        f"**{pinned}** — so Plane would record the write under the wrong "
        "account, and every downstream persona would read it as that "
        f"persona's work. Pass persona=\"{pinned}\". If the work really "
        f"belongs to {called}, that is a handover: finish this turn and "
        f"let USER run the {called} command."
    )
    decide("deny" if setting == "strict" else "ask", reason)

    return 0


if __name__ == "__main__":
    sys.exit(main())
