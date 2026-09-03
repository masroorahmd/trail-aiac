#!/usr/bin/env python3
"""UserPromptSubmit hook: record which persona USER just started.

`/bd DEV-7` puts the main loop into the backend-developer role. Nothing
in the session state says so afterwards — the role lives in the prompt,
where a hook cannot see it. This writes it down, so
`plane-persona-guard.py` has something to check a Plane call against.

The mapping is *derived*, never hard-coded: the hook reads
`.claude/commands/<name>.md` and takes the persona from the
`.claude/agents/<persona>.md` file that command tells the main loop to
load. A command that names exactly one persona pins it; one that names
none or several (`/autopilot`, `/kickoff`, `/quick` — the lanes that
legitimately act under more than one identity) pins `*`, which the
guard reads as "any". Add a twelfth persona and this keeps working.

A prompt with no leading slash command leaves the pin untouched: a
persona stays in role for follow-up turns, which is exactly what the
`/<persona>` contract promises.

It also renames the session after the persona it just pinned. Claude
Code takes a `sessionTitle` in a `UserPromptSubmit` hook's output and
the terminal tab title follows it, so `/ba` in one terminal and `/tm`
in another read `business-analyst` and `test-manager` in `/resume` and
in the tab bar — the same problem the per-session pin exists for, on
the surface USER looks at. `hooks.session_title: off` turns it off.

One pin file per session, named by session id. Two Claude sessions in
one repo — `/ba` in one terminal, `/tm` in another — are a normal way
to work here, and a single shared file would give the check to
whichever session submitted a prompt last and silently drop it for the
other. Separate files also mean no two sessions ever write the same
path, so there is no lost update to lose.
"""

import json
import os
import re
import sys
import time

PIN_DIR = os.path.join(".claude", "cache", "persona")
CONFIG = os.path.join(".claude", "config.yaml")

# Session ids come from the harness, but they name a file, so they are
# treated as untrusted input.
SAFE_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# A pin outlives its session by design — a persona stays in role across
# turns — but not forever. Sessions end without telling us, and the
# directory is the only thing that would grow.
PIN_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

# A slash command at the very start of the prompt — that is the only
# position that starts a persona.
COMMAND_RE = re.compile(r"^\s*/([a-z][a-z0-9-]*)\b")

# `.claude/agents/<persona>.md` as the command file spells it.
AGENT_REF_RE = re.compile(r"\.claude/agents/([a-z][a-z0-9-]*)\.md")

ANY = "*"

TITLE_MODES = ("on", "off")
DEFAULT_TITLE_MODE = "on"


def persona_for(root, command):
    """The persona `/`+command puts the main loop into, or `*`.

    `*` covers both "this command drives several personas" and "no idea
    what this command is" — the guard treats it as no constraint, which
    is the right answer for a command the framework did not ship.
    """
    path = os.path.join(root, ".claude", "commands", f"{command}.md")
    try:
        with open(path, encoding="utf-8") as handle:
            referenced = set(AGENT_REF_RE.findall(handle.read()))
    except OSError:
        return ANY
    return referenced.pop() if len(referenced) == 1 else ANY


def title_mode(root):
    """`hooks.session_title`, defaulting for configs seeded before it."""
    try:
        with open(os.path.join(root, CONFIG), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return DEFAULT_TITLE_MODE

    inside = False
    for line in lines:
        if re.match(r"^hooks:\s*(#.*)?$", line):
            inside = True
            continue
        if not inside:
            continue
        entry = re.match(r"^\s+session_title:\s*([a-z]+)\s*(#.*)?$", line)
        if entry and entry.group(1) in TITLE_MODES:
            return entry.group(1)
        if line.strip() and not line.startswith((" ", "\t")):
            break
    return DEFAULT_TITLE_MODE


def rename(pin, root):
    """Retitle the session `business-analyst`, or `autopilot` for a lane.

    The persona's own username, spelled out — the name the framework
    uses everywhere else. A lane that runs under more than one identity
    has no single persona to name, so it keeps its command word. Same
    distinction the pin already makes, so nothing new is maintained
    here. No project in the title: the harness already shows the cwd.
    """
    if title_mode(root) == "off":
        return
    persona = pin["persona"]
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "sessionTitle": pin["command"] if persona == ANY else persona,
            }
        },
        sys.stdout,
    )


def prune(directory):
    """Drop pins whose session is long gone. Best-effort, never fatal."""
    try:
        cutoff = time.time() - PIN_MAX_AGE_SECONDS
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                continue
    except OSError:
        return


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    match = COMMAND_RE.match(payload.get("prompt") or "")
    if not match:
        return 0

    session = payload.get("session_id") or ""
    if not SAFE_SESSION_RE.match(session):
        # Nothing to key the pin on — the guard will fail open.
        return 0

    root = payload.get("cwd") or os.getcwd()
    command = match.group(1)
    pin = {"persona": persona_for(root, command), "command": command}

    try:
        directory = os.path.join(root, PIN_DIR)
        os.makedirs(directory, exist_ok=True)
        prune(directory)
        with open(
            os.path.join(directory, f"{session}.json"), "w", encoding="utf-8"
        ) as out:
            json.dump(pin, out)
    except OSError:
        # A pin we cannot write is a check that will not fire. That is
        # the acceptable half of the failure; blocking USER's prompt
        # over it is not.
        pass

    rename(pin, root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
