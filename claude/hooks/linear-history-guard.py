#!/usr/bin/env python3
"""PreToolUse guard: integrate by rebasing, never by a merge commit.

`claude/partials/git-history.md` states the rule; this script is what
makes it hold. It reads the PreToolUse hook payload on stdin, finds the
git subcommand in the Bash command line, and denies the call when it
would write a merge commit, merge in a `git pull` it did not have to,
or force-push over published history.

What it looks at, and what it lets through:

  git merge          Denied — it writes a merge commit. Allowed with
                     `--ff-only` (writes none), `--squash` (stages the
                     change for an ordinary commit), and with the
                     in-flight verbs `--abort` / `--continue` / `--quit`.
  git pull           Denied when bare, because its default is a merge.
                     Allowed with `--rebase` or `--ff-only` — and
                     allowed bare when the repo's own `pull.rebase` is
                     set, since git then rebases anyway.
  git push --force   Denied. `--force-with-lease` is the reviewed form:
                     it refuses when the remote moved under you, which
                     is the case a bare `--force` silently destroys.

Everything else — `rebase`, `merge --ff-only`, `pull --rebase`, a
`push` without force — is not the guard's business.

How hard it holds is the consumer's call — `hooks.linear_history`
in `.claude/config.yaml`:

  deny (default)  Refuse the call and name the linear form to use.
  ask             Put it to USER as a permission prompt.
  off             No check.

Escape hatch — the one integration that genuinely needs a merge commit
(an unrelated history joined on purpose, a vendor drop) runs as:

    TRAIL_SKIP_MERGE_GUARD=1 git merge …

which is a deliberate act and visible in the transcript.

Deliberately dependency-free (no PyYAML, no `uv`): the hook fires on
Bash calls, so its start-up cost is paid often enough to matter. Fails
open on an unreadable payload, a missing config and any command it
cannot parse — a false deny on an honest integration costs more than a
missed check.
"""

import json
import os
import re
import subprocess
import sys

CONFIG = os.path.join(".claude", "config.yaml")

MODES = ("deny", "ask", "off")
DEFAULT_MODE = "deny"

# `git <subcommand>`, possibly behind global flags (`git -C dir merge`).
def subcommand_re(name):
    # `(?=\s|$)` rather than `\b`: a word boundary also matches inside
    # `git merge-base`, a read-only command no guard should touch.
    return re.compile(
        r"\bgit\b(?:\s+-\S+(?:\s+\S+)?)*\s+" + name + r"(?=\s|$)"
    )


MERGE_RE = subcommand_re("merge")
PULL_RE = subcommand_re("pull")
PUSH_RE = subcommand_re("push")

# Where one shell command ends and the next begins — so flags belonging
# to a later command in the same line are not read as this one's.
SEPARATOR_RE = re.compile(r"(?:&&|\|\||;|\||\n)")

# Merge forms that write no merge commit, plus the in-flight verbs.
MERGE_ALLOWED_RE = re.compile(
    r"(?:^|\s)--(?:ff-only|squash|abort|continue|quit|help)(?:[=\s]|$)"
)
PULL_ALLOWED_RE = re.compile(
    r"(?:^|\s)(?:--rebase(?:=\S+)?|--ff-only|--abort|--continue|--quit|--help)"
    r"(?:[=\s]|$)"
)
FORCE_RE = re.compile(r"(?:^|\s)(?:--force|-f)(?:[=\s]|$)")
LEASE_RE = re.compile(r"(?:^|\s)--force-(?:with-lease|if-includes)(?:[=\s]|$)")

# `pull.rebase` values under which a bare `git pull` already rebases.
REBASING = ("true", "1", "yes", "on", "interactive", "merges", "preserve")


def mode(root):
    """`hooks.linear_history`, defaulting for configs seeded before it."""
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
        entry = re.match(r"^\s+linear_history:\s*([a-z-]+)\s*(#.*)?$", line)
        if entry and entry.group(1) in MODES:
            return entry.group(1)
        if line.strip() and not line.startswith((" ", "\t")):
            break
    return DEFAULT_MODE


def arguments(command, pattern):
    """The argument text of the first `git <subcommand>` this pattern finds,
    cut at the next shell separator. None when the subcommand is absent."""
    match = pattern.search(command)
    if not match:
        return None
    tail = command[match.end():]
    end = SEPARATOR_RE.search(tail)
    return tail[: end.start()] if end else tail


def pull_rebases_anyway(root):
    """True when the repo's own config makes a bare `git pull` rebase."""
    try:
        result = subprocess.run(
            ["git", "-C", root, "config", "--get", "pull.rebase"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip().lower() in REBASING


def decide(setting, reason):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask" if setting == "ask" else "deny",
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
    if "TRAIL_SKIP_MERGE_GUARD" in command:
        return 0

    root = payload.get("cwd") or os.getcwd()
    setting = mode(root)
    if setting == "off":
        return 0

    merge = arguments(command, MERGE_RE)
    if merge is not None and not MERGE_ALLOWED_RE.search(merge):
        decide(
            setting,
            "This `git merge` would write a merge commit, and this project "
            "keeps the history linear: `git log --oneline` is the view most "
            "readers get, and one merge commit per branch turns it into a "
            "diagram. Rebase instead — `git rebase <target>` while on the "
            "branch, then land it with `git merge --ff-only <branch>`, which "
            "writes no merge commit. If a fast-forward is refused, the "
            "rebase is not finished yet. For the rare integration that "
            "genuinely needs a merge commit, re-run with "
            "TRAIL_SKIP_MERGE_GUARD=1 prefixed."
        )

    pull = arguments(command, PULL_RE)
    if (
        pull is not None
        and not PULL_ALLOWED_RE.search(pull)
        and not pull_rebases_anyway(root)
    ):
        decide(
            setting,
            "A bare `git pull` merges the upstream into your branch and "
            "leaves a merge commit behind. Use `git pull --rebase` (or "
            "`--ff-only` when you expect no local commits) — this project "
            "integrates by rebasing."
        )

    push = arguments(command, PUSH_RE)
    if push is not None and FORCE_RE.search(push) and not LEASE_RE.search(push):
        decide(
            setting,
            "A bare `--force` push overwrites whatever is on the remote, "
            "including commits someone else pushed while you worked. Use "
            "`--force-with-lease`, which refuses exactly that case — and "
            "only after USER has agreed to rewrite an already-pushed "
            "branch."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
