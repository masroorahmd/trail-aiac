#!/usr/bin/env python3
"""PreToolUse guard: the work-item ID must open every commit subject.

`claude/partials/commit-message.md` states the rule; this script is what
makes it hold. It reads the PreToolUse hook payload on stdin, finds the
commit message inside a `git commit` command line, and denies the tool
call when the subject does not start with a work-item ID belonging to
one of the Plane projects this consumer is configured for.

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

FALLBACK_PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")


def project_prefixes(root):
    """Plane project identifiers from the consumer's config.yaml.

    A hand-rolled scan of the `projects:` block rather than a YAML parse —
    the block is machine-seeded and two levels deep, and the parse is not
    worth a dependency on a hook this hot. Returns an empty set when the
    config is missing or unreadable, which the caller treats as "accept
    any well-formed identifier".
    """
    path = os.path.join(root, CONFIG)
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return set()

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


def extract_subject(command):
    """The commit subject line, or None when it cannot be determined."""
    tail = command[GIT_COMMIT_RE.search(command).end():]

    heredoc = HEREDOC_RE.search(tail)
    if heredoc:
        rest = tail[heredoc.end():].split("\n")[1:]
        return rest[0] if rest else None

    message = MESSAGE_RE.search(tail)
    if message:
        value = next(g for g in message.groups() if g is not None)
        return value.replace('\\"', '"').split("\n")[0]

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

    subject = extract_subject(command)
    if subject is None:
        return 0

    subject = subject.strip()
    if not subject:
        return 0

    prefixes = project_prefixes(payload.get("cwd") or os.getcwd())

    token = subject.split(maxsplit=1)[0]
    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)-(\d+)", token)
    if match:
        prefix = match.group(1).upper()
        if not prefixes or prefix in prefixes:
            if len(subject.split(maxsplit=1)) < 2:
                deny(
                    f"The commit subject is only the work-item ID ({token}) "
                    "with no summary after it. Write "
                    f"`{token} <what the change does>`."
                )
            return 0
        known = ", ".join(sorted(prefixes))
        deny(
            f"`{token}` is not a work-item ID of this project. The Plane "
            f"projects configured here are: {known}. Use the ID of the item "
            "the work was done for, and never invent one."
        )

    known = ", ".join(sorted(prefixes)) if prefixes else "the project's Plane projects"
    deny(
        "The commit subject must open with the work-item ID the work was "
        f"done for — `<ID> {subject[:40]}…`, where <ID> belongs to {known} "
        "(the /quick lane uses item 0 of the dev project). `git log "
        "--oneline`, blame and the release notes are the only views most "
        "readers get, and the ID is their one bridge back to the acceptance "
        "criteria. If this change genuinely belongs to no work item, do not "
        "invent an ID — re-run the command with TRAIL_SKIP_COMMIT_GUARD=1 "
        "prefixed."
    )


if __name__ == "__main__":
    sys.exit(main())
