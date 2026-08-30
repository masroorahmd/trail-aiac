#!/usr/bin/env python3
"""PreToolUse guard: no `fork` subagent while a persona is in role.

A named persona subagent — `Agent(subagent_type='software-architect',
…)` — is sanctioned and several personas recommend it for a one-shot
cross-lane lookup. A **fork** is a different animal: it inherits the
caller's full context, which under `/<persona>` includes the Plane
tools and the persona's own API token. It can therefore create
work-items, post comments and reassign tickets under an identity it
was never handed, and it does so in a branch of the conversation the
persona never reads.

That has happened. A fork spawned inside a Plane-write run created a
duplicate set of children under the architect's name; the recovery was
Cancel (never delete), remove-from-module, reassign, a reconciliation
comment, and a parent-filtered `list_work_items` to verify the final
child set.

`plane-persona-guard.py` cannot see this. The fork carries the *same*
persona the pin names, so the `persona` argument agrees and every
duplicate write is correctly attributed — to the wrong author's
intent.

How hard it holds is the consumer's call —
`hooks.fork_in_persona_run` in `.claude/config.yaml`:

  deny (default)  Refuse the spawn and say what to use instead.
  ask             Put it to USER as a permission prompt.
  off             No check.

One deliberate divergence from its sibling guard: that one fails open
on the `*` pin the multi-persona lanes set (`/autopilot`, `/quick`,
`/kickoff`), because it cannot know which of several personas is
speaking. This one does not, because it does not need to — under
`/autopilot` a fork is *more* dangerous, not less, since nobody is
watching the branch it opens. Any pin at all is enough to fire.

Fails open on everything else: no pin, no config, an unreadable
payload, a session that has not run a `/<persona>` yet.

Deliberately dependency-free (no PyYAML, no `uv`), matching its
sibling: it runs on every subagent spawn.
"""

import json
import os
import re
import sys

CONFIG = os.path.join(".claude", "config.yaml")
PIN_DIR = os.path.join(".claude", "cache", "persona")

SAFE_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

SPAWN_TOOLS = ("Agent", "Task")
FORK = "fork"

MODES = ("deny", "ask", "off")
DEFAULT_MODE = "deny"


def mode(root):
    """`hooks.fork_in_persona_run`, defaulting for configs seeded before it."""
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
        entry = re.match(r"^\s+fork_in_persona_run:\s*([a-z-]+)\s*(#.*)?$", line)
        if entry and entry.group(1) in MODES:
            return entry.group(1)
        if line.strip() and not line.startswith((" ", "\t")):
            break
    return DEFAULT_MODE


def pinned_persona(root, session_id):
    """The persona USER started in *this* session, or None.

    `*` counts: the multi-persona lanes still hold Plane tools, and an
    unattended fork is the worse case, not the safer one.
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

    if (payload.get("tool_name") or "") not in SPAWN_TOOLS:
        return 0

    if normalise((payload.get("tool_input") or {}).get("subagent_type")) != FORK:
        return 0

    root = payload.get("cwd") or os.getcwd()
    setting = mode(root)
    if setting == "off":
        return 0

    pinned = pinned_persona(root, payload.get("session_id") or "")
    if pinned is None:
        return 0

    who = "a persona" if pinned == "*" else f"**{pinned}**"
    reason = (
        f"A `fork` inherits this turn's whole context, and {who} is in "
        "role — so the fork gets the Plane tools and the persona's API "
        "token, and can create work-items, post comments and reassign "
        "tickets under an identity nobody handed it. That has already "
        "cost one duplicate child set and a manual reconciliation. "
        "For a cross-lane lookup, spawn a NAMED persona instead — "
        "`Agent(subagent_type='software-architect', prompt='…')` — "
        "which starts fresh and cannot write as you. If the work is "
        "genuinely yours, do it in this turn."
    )
    decide("deny" if setting == "deny" else "ask", reason)

    return 0


if __name__ == "__main__":
    sys.exit(main())
