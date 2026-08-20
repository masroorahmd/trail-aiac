#!/usr/bin/env python3
"""PreToolUse guard: the work-item ID must open every commit subject.

`claude/partials/commit-message.md` states the rule; this script is what
makes it hold. It reads the PreToolUse hook payload on stdin, finds the
commit message inside a `git commit` command line, and denies the tool
call when the work-item ID is not the first token of the subject.

How hard it holds is the consumer's call — `hooks.commit_id_required`
in `.claude/config.yaml`:

  plane-only (default)  Deny only when the message names a work-item ID
                        that is not leading the subject. A commit that
                        names no ID at all passes, because `/quick` is
                        the framework's off-Plane lane and is told never
                        to invent one. This is the observed failure mode:
                        the persona has the ticket and buries the ID in
                        the body or a trailer.
  strict                Every commit subject must open with an ID.
  off                   No check.

Deliberately dependency-free (no PyYAML, no `uv`): the hook fires on
Bash calls, so its start-up cost is paid often enough to matter.

Escape hatch — a commit that genuinely belongs to no work item (the
partial forbids inventing one) runs as:

    TRAIL_SKIP_COMMIT_GUARD=1 git commit -m "..."

which is a deliberate act and visible in the transcript, unlike a made-up
ID, which is invisible and wrong forever.
"""

import json
import os
import re
import sys

CONFIG = os.path.join(".claude", "config.yaml")

# `git commit`, possibly behind global flags (`git -C dir commit`).
GIT_COMMIT_RE = re.compile(r"\bgit\b(?:\s+-\S+(?:\s+\S+)?)*\s+commit\b")

# Flags that supply a message we cannot see, or reuse an existing one.
# Nothing to validate — let them through.
OPAQUE_FLAGS_RE = re.compile(
    r"(?:^|\s)(?:-F|--file|-C|--reuse-message|-c|--reedit-message"
    r"|--fixup|--squash|--no-edit)(?:[=\s]|$)"
)

# A `<<EOF` / `<<-'EOF'` heredoc opener; the subject is the line after it.
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

# -m / --message with a single-quoted, double-quoted or bare argument.
MESSAGE_RE = re.compile(
    r"(?:^|\s)(?:-m|--message)(?:=|\s+)"
    r"(?:'([^']*)'|\"((?:[^\"\\]|\\.)*)\"|(\S+))"
)

# A work-item ID anywhere in the message — used to tell "no ticket" from
# "ticket named, but buried in the body".
ID_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9]*)-(\d+)\b")


MODES = ("plane-only", "strict", "off")
DEFAULT_MODE = "plane-only"


def config_lines(root):
    try:
        with open(os.path.join(root, CONFIG), encoding="utf-8") as handle:
            return handle.read().splitlines()
    except OSError:
        return []


def mode(lines):
    """`hooks.commit_id_required`, defaulting for configs seeded before it."""
    inside = False
    for line in lines:
        if re.match(r"^hooks:\s*(#.*)?$", line):
            inside = True
            continue
        if not inside:
            continue
        entry = re.match(r"^\s+commit_id_required:\s*([a-z-]+)\s*(#.*)?$", line)
        if entry and entry.group(1) in MODES:
            return entry.group(1)
        if line.strip() and not line.startswith((" ", "\t")):
            break
    return DEFAULT_MODE


def project_prefixes(lines):
    """Plane project identifiers from the consumer's config.yaml.

    A hand-rolled scan of the `projects:` block rather than a YAML parse —
    the block is machine-seeded and two levels deep, and the parse is not
    worth a dependency on a hook this hot. Returns an empty set when the
    config is missing or unreadable, which the caller treats as "accept
    any well-formed identifier".
    """
    prefixes = set()
    inside = False
    for line in lines:
        if re.match(r"^\s+projects:\s*(#.*)?$", line):
            inside = True
            continue
        if not inside:
            continue
        entry = re.match(r"^\s+\w+:\s*([A-Za-z][A-Za-z0-9]*)\s*(#.*)?$", line)
        if entry:
            prefixes.add(entry.group(1).upper())
        elif line.strip() and not line.startswith((" ", "\t")):
            break
    return prefixes


def extract_message(command):
    """The full commit message, or None when it cannot be determined."""
    tail = command[GIT_COMMIT_RE.search(command).end():]

    heredoc = HEREDOC_RE.search(tail)
    if heredoc:
        body = tail[heredoc.end():].split("\n")[1:]
        delimiter = heredoc.group(2)
        for index, line in enumerate(body):
            if line.strip() == delimiter:
                return "\n".join(body[:index])
        return "\n".join(body)

    message = MESSAGE_RE.search(tail)
    if message:
        value = next(g for g in message.groups() if g is not None)
        return value.replace('\\"', '"')

    return None


def deny(reason):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def id_token(text, prefixes):
    """The first `<PREFIX>-<n>` in `text` that belongs to this deployment.

    Requires the real identifiers: without them `utf-8` and `v1-2` read as
    work-item IDs, and a false deny on an honest commit costs more than a
    missed one. No config, no buried-ID check.
    """
    if not prefixes:
        return None
    for candidate in ID_RE.finditer(text):
        if candidate.group(1).upper() in prefixes:
            return candidate.group(0)
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not GIT_COMMIT_RE.search(command):
        return 0
    if OPAQUE_FLAGS_RE.search(command):
        return 0
    if "TRAIL_SKIP_COMMIT_GUARD" in command:
        return 0

    lines = config_lines(payload.get("cwd") or os.getcwd())
    setting = mode(lines)
    if setting == "off":
        return 0

    message = extract_message(command)
    if message is None:
        return 0
    subject = message.strip().split("\n")[0].strip()
    if not subject:
        return 0

    prefixes = project_prefixes(lines)
    known = ", ".join(sorted(prefixes)) if prefixes else "this project"

    head = subject.split(maxsplit=1)
    leading = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)-(\d+)", head[0])

    if leading:
        if prefixes and leading.group(1).upper() not in prefixes:
            deny(
                f"`{head[0]}` is not a work-item ID of this project. The "
                f"Plane projects configured here are: {known}. Use the ID of "
                "the item the work was done for, and never invent one."
            )
        if len(head) < 2:
            deny(
                f"The commit subject is only the work-item ID ({head[0]}) "
                "with no summary after it. Write "
                f"`{head[0]} <what the change does>`."
            )
        return 0

    buried = id_token(message, prefixes)
    if buried:
        deny(
            f"`{buried}` appears in the commit message but not where a "
            "reader will find it. The work-item ID is the FIRST token of "
            f"the subject line: `{buried} {subject[:44]}`. `git log "
            "--oneline`, blame and the release notes are the only views "
            "most readers ever get, and an ID that lives only in the body "
            "or a trailer is absent from every one of them."
        )

    if setting == "strict":
        deny(
            "The commit subject must open with the work-item ID the work "
            f"was done for — `<ID> {subject[:44]}`, where <ID> belongs to "
            f"{known}. If this change genuinely belongs to no work item, do "
            "not invent an ID: re-run the command with "
            "TRAIL_SKIP_COMMIT_GUARD=1 prefixed. (This project runs "
            "`hooks.commit_id_required: strict`.)"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
