#!/usr/bin/env python3
"""PreToolUse rewrite: a persona reads a command's summary, not its stream.

The multi-tenant MCP server already does this for Plane — `list_*`
drops bodies, a long comment is cut to its head — because a persona
picks up with a fresh context and pays every read on every turn. The
other stream a persona reads on every turn is what a Bash call prints:
a test run, `git log`, a package install, a build. Nothing in the
framework shortened those. This hook hands the command to `rtk`
(https://github.com/rtk-ai/rtk), which rewrites `pytest -q` to
`rtk pytest -q` before it runs: failures stay, passing tests collapse to
a count, progress bars and ANSI go, and a failed command keeps its full
output behind `rtk recall <id>` so nothing has to be re-run to see it.

It reads the PreToolUse payload on stdin and, when the command is one
rtk knows, prints the `updatedInput` rtk proposes. It changes no
persona prompt: the rewrite is invisible to the model, which is the
point — this is the one token saving that costs no prompt tokens.

How it holds is the consumer's call — `hooks.bash_output_trim` in
`.claude/config.yaml`:

  on (default)  Rewrite every Bash command rtk has a filter for.
  off           No rewrite.

Fails open on every uncertain case — no `rtk` on PATH, a payload it
cannot read, rtk exiting non-zero or hanging — because a hook that
blocks a Bash call over a missing optional binary costs more than the
tokens it would have saved. It does nothing rtk's own hook would not
do, so a consumer who also ran `rtk init -g` gets one rewrite, not two:
rtk leaves an already-prefixed command alone.

The framework's own Bash guards (commit-msg-guard, linear-history-guard)
run on the same event and see the original command; both also match
the rewritten form (`rtk git merge …` is still `git merge`), so a
rewrite cannot slip a merge commit or a buried work-item ID past them.

Deliberately dependency-free (no PyYAML, no `uv`): it fires on every
Bash call.
"""

import json
import os
import re
import shutil
import subprocess
import sys

CONFIG = os.path.join(".claude", "config.yaml")

MODES = ("on", "off")
DEFAULT_MODE = "on"

# The hook must answer well inside the 10 s settings.json gives it;
# rtk's rewrite is a lookup, not a run, and takes milliseconds.
RTK_TIMEOUT = 5


def mode(root):
    """`hooks.bash_output_trim`, defaulting for configs seeded before it."""
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
        entry = re.match(r"^\s+bash_output_trim:\s*([a-z]+)\s*(#.*)?$", line)
        if entry and entry.group(1) in MODES:
            return entry.group(1)
        if line.strip() and not line.startswith((" ", "\t")):
            break
    return DEFAULT_MODE


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return 0

    if not ((payload.get("tool_input") or {}).get("command") or "").strip():
        return 0

    rtk = shutil.which("rtk")
    if rtk is None:
        return 0

    if mode(payload.get("cwd") or os.getcwd()) == "off":
        return 0

    env = dict(os.environ)
    # rtk warns on stderr when it finds no hook of its own in
    # ~/.claude/settings.json. This IS the hook; the warning is noise.
    env["RTK_SUPPRESS_HOOK_WARNING"] = "1"
    try:
        result = subprocess.run(
            [rtk, "hook", "claude"],
            input=raw,
            capture_output=True,
            text=True,
            env=env,
            timeout=RTK_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if result.returncode != 0:
        return 0

    out = result.stdout.strip()
    if not out:
        return 0
    # Only forward what Claude Code will understand as a rewrite. Anything
    # else rtk might print is not a decision this hook wants to make.
    try:
        decision = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return 0
    if "updatedInput" not in (decision.get("hookSpecificOutput") or {}):
        return 0

    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
