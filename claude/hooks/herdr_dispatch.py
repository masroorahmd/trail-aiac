"""Start the receiving persona's turn in its own herdr tab.

Imported by `handover-signal.py` when `herdr.handover_dispatch` is `on`.
Not a hook itself.

The idea: a space holds one tab per persona (`BA`, `RE`, `SA`, … and
the lanes, `AUTO`). When a persona reassigns a work-item to another
persona, that persona's tab starts working on it — the same as if USER
had switched there and typed `/<cmd> <ID>`.

How a turn gets into the tab depends on what the tab holds:

- a Claude Code session, idle: the command is typed with `hc keys`.
  `hc send` is no use here: it wraps the text in `<hc>` tags, and a
  slash command inside tags is just text, so no persona is pinned.
- a plain shell (the tab exists, its session ended): `claude "<cmd>"`
  is typed into it, the same launch the `trail` mod's click does.
- a session that is working or blocked: left alone. Typing into it
  would either queue behind or answer its dialog. The handover label
  still shows the toast, so USER sees it.
- no such tab: a new terminal in the sender's space, which herdr turns
  into a tab and the `trail` mod names after the persona.

Only a *persona* hands over. A lane (`/autopilot`, whose stages carry
`trail.lane`) walks its own spine and must not fan out sideways, so a
sender without a persona label of its own is no sender here.

Best-effort and silent: any failure leaves the handover exactly as it
was before this existed — a label and a toast, and USER's click.
"""

import json
import os
import re
import subprocess
import time

COMMANDS_DIR = os.path.join(".claude", "commands")
AGENT_REF_RE = re.compile(r"\.claude/agents/([a-z][a-z0-9-]*)\.md")
KEEPS_ROLE_MARKER = "<!-- TRAIL:KEEPS-ROLE -->"

HC_TIMEOUT_SECONDS = 5
SHELLS = ("bash", "zsh", "fish", "sh", "dash", "nu")

# One handover reaches the hook more than once when a persona creates
# and then updates the item. The same receiver and item inside this
# window is one handover.
DEDUPE_SECONDS = 120


def commands_by_persona(root):
    """`business-analyst` → `ba`, from the command files themselves.

    The same derivation `persona-pin.py` makes the other way round: a
    command that loads exactly one persona is that persona's dispatcher.
    """
    found = {}
    directory = os.path.join(root, COMMANDS_DIR)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return found
    for name in names:
        if not name.endswith(".md"):
            continue
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        if KEEPS_ROLE_MARKER in text:
            continue
        refs = set(AGENT_REF_RE.findall(text))
        if len(refs) == 1:
            found.setdefault(refs.pop(), name[:-3])
    return found


def _hc(hc, *args):
    """Run `hc … --json`; the decoded reply, or None. Never raises."""
    try:
        done = subprocess.run(
            [hc, *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=HC_TIMEOUT_SECONDS,
            check=False,
        )
        if done.returncode != 0:
            return None
        return json.loads(done.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _get(hc, address):
    return _hc(hc, "get", address, "--json")


def _tab_of(where):
    """The tab name in herdr's `<space> / <tab>` label, lower-cased."""
    return where.rsplit(" / ", 1)[-1].strip().lower() if " / " in where else ""


def _space_of(where):
    return where.rsplit(" / ", 1)[0] if " / " in where else None


def find_target(hc, sender, receiver, cmd):
    """The receiver's terminal in the sender's space, or None.

    A terminal matches by what Trail labelled it (`trail.persona`) or,
    for a tab whose session ended, by the tab's name (`RE`).
    """
    labels = sender.get("labels") or {}
    space_id = labels.get("herdr.space")
    space_name = _space_of(labels.get("where", ""))
    listing = _hc(hc, "ls", "--json")
    if not space_id or not listing:
        return None
    for row in listing.get("terminals", []):
        if row.get("state") != "live" or row.get("address") == sender.get("address"):
            continue
        if _space_of(row.get("where", "")) != space_name:
            continue
        info = _get(hc, row["address"])
        if not info:
            continue
        theirs = info.get("labels") or {}
        if theirs.get("herdr.space") != space_id:
            continue
        if (
            theirs.get("trail.persona") in (receiver, cmd)
            or _tab_of(theirs.get("where", "")) in (cmd, receiver)
        ):
            return info
    return None


def _recent(labels, item):
    mark = (labels.get("trail.dispatched") or "").split()
    if len(mark) != 2 or mark[0] != item:
        return False
    try:
        return time.time() - int(mark[1]) < DEDUPE_SECONDS
    except ValueError:
        return False


def _type_command(hc, address, cmd, item):
    """`/re CRTHVN-198` as keystrokes: no `<hc>` wrapper, so it runs."""
    keys = ["/", *cmd, "space", *item, "enter"]
    return _hc(hc, "keys", address, *keys) is not None


def dispatch(hc, sender_address, receiver, item, root):
    """Start `receiver`'s turn on `item`. Returns what it did, or None."""
    sender = _get(hc, sender_address)
    if not sender:
        return None
    sender_labels = sender.get("labels") or {}
    commands = commands_by_persona(root)
    if sender_labels.get("trail.lane") or sender_labels.get("trail.persona") not in commands:
        return None
    cmd = commands.get(receiver)
    if not cmd or not sender_labels.get("herdr.space"):
        return None

    target = find_target(hc, sender, receiver, cmd)
    stamp = f"{item} {int(time.time())}"

    if target is None:
        started = _hc(
            hc,
            "run",
            "--bg",
            "--keep",
            "--no-parent",
            "--cwd",
            sender.get("cwd") or root,
            "--label",
            f"herdr.space={sender_labels['herdr.space']}",
            "--label",
            f"trail.dispatched={stamp}",
            "--json",
            "--",
            "claude",
            f"/{cmd} {item}",
        )
        return "opened" if started else None

    labels = target.get("labels") or {}
    if _recent(labels, item):
        return "duplicate"
    address = target["address"]
    state = (target.get("status") or {}).get("state")
    foreground = (target.get("foreground") or {}).get("name", "")

    if (target.get("status") or {}).get("app") == "claude-code":
        if state != "idle":
            return "busy"
        ok = _type_command(hc, address, cmd, item)
    elif foreground in SHELLS:
        ok = _hc(hc, "send", address, f'claude "/{cmd} {item}"') is not None
    else:
        return "busy"

    if not ok:
        return None
    _hc(hc, "label", address, f"trail.dispatched={stamp}")
    return "started"
