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
`/<persona>` contract promises. So does a command whose file carries
`<!-- TRAIL:KEEPS-ROLE -->` — a read-only lookup like `/ticket` that a
persona in role may run mid-story. Pinning `*` for it would silently
switch the identity check off for the rest of that persona's turns.

It also renames the session after the persona it just pinned. Claude
Code takes a `sessionTitle` in a `UserPromptSubmit` hook's output and
the terminal tab title follows it, so `/ba` in one terminal and `/tm`
in another read `business-analyst` and `test-manager` in `/resume` and
in the tab bar — the same problem the per-session pin exists for, on
the surface USER looks at. `hooks.session_title: off` turns it off.

Inside a herdr terminal (`HC_TERMINAL_ID` set, `hc` on PATH) it also
labels that terminal `trail.persona=<persona>` and
`trail.ticket=<work-item ID>`, so `hc ls`, `hc events --label …` and
herdr mods can tell persona sessions apart by what they are, not by
tab name. `herdr.enabled: off` turns it off; outside herdr it does
nothing.

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
import shutil
import subprocess
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

# A command that runs alongside whatever role is in force.
KEEPS_ROLE_MARKER = "<!-- TRAIL:KEEPS-ROLE -->"

ANY = "*"

TITLE_MODES = ("on", "off")
DEFAULT_TITLE_MODE = "on"

HERDR_MODES = ("auto", "off")
DEFAULT_HERDR_MODE = "auto"

# The work-item the command was started on: `/re CRTHVN-198 …`.
TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-[0-9]+)\b")

# A label call talks to a local socket; anything slower is a core in
# trouble, and USER's prompt must not wait on it.
HC_TIMEOUT_SECONDS = 2


def persona_for(root, command):
    """The persona `/`+command puts the main loop into, `*`, or None.

    `*` covers both "this command drives several personas" and "no idea
    what this command is" — the guard treats it as no constraint, which
    is the right answer for a command the framework did not ship. None
    means the command keeps whatever role is in force: leave the pin.
    """
    path = os.path.join(root, ".claude", "commands", f"{command}.md")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return ANY
    if KEEPS_ROLE_MARKER in text:
        return None
    referenced = set(AGENT_REF_RE.findall(text))
    return referenced.pop() if len(referenced) == 1 else ANY


def config_value(root, block, key, allowed, default):
    """`<block>.<key>` from config.yaml, or the default.

    A line scan, not a YAML parser: hooks stay dependency-free, and a
    config seeded before the key existed simply gets the default.
    """
    try:
        with open(os.path.join(root, CONFIG), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return default

    head = re.compile(rf"^{re.escape(block)}:\s*(#.*)?$")
    item = re.compile(rf"^\s+{re.escape(key)}:\s*([a-z]+)\s*(#.*)?$")
    inside = False
    for line in lines:
        if head.match(line):
            inside = True
            continue
        if not inside:
            continue
        entry = item.match(line)
        if entry and entry.group(1) in allowed:
            return entry.group(1)
        if line.strip() and not line.startswith((" ", "\t")):
            break
    return default


def title_mode(root):
    """`hooks.session_title`, defaulting for configs seeded before it."""
    return config_value(
        root, "hooks", "session_title", TITLE_MODES, DEFAULT_TITLE_MODE
    )


def label_terminal(pin, prompt, root):
    """Label this herdr terminal with the persona and work-item.

    Best-effort and silent: no herdr, no `hc`, a slow core or a refused
    call all leave USER's prompt exactly as it was. The ticket label is
    cleared when the command names none, so a terminal that moved on
    from a Story never keeps advertising it.
    """
    terminal = os.environ.get("HC_TERMINAL_ID")
    if not terminal:
        return
    if config_value(
        root, "herdr", "enabled", HERDR_MODES, DEFAULT_HERDR_MODE
    ) == "off":
        return
    hc = shutil.which("hc") or shutil.which("herdr-core")
    if not hc:
        return

    persona = pin["command"] if pin["persona"] == ANY else pin["persona"]
    ticket = TICKET_RE.search(prompt)
    try:
        subprocess.run(
            [
                hc,
                "label",
                terminal,
                f"trail.persona={persona}",
                f"trail.ticket={ticket.group(1) if ticket else ''}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=HC_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return


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

    prompt = payload.get("prompt") or ""
    match = COMMAND_RE.match(prompt)
    if not match:
        return 0

    session = payload.get("session_id") or ""
    if not SAFE_SESSION_RE.match(session):
        # Nothing to key the pin on — the guard will fail open.
        return 0

    root = payload.get("cwd") or os.getcwd()
    command = match.group(1)
    persona = persona_for(root, command)
    if persona is None:
        return 0
    pin = {"persona": persona, "command": command}

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

    label_terminal(pin, prompt, root)
    rename(pin, root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
