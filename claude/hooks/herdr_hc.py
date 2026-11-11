"""Shared helpers for the hooks that talk to herdr's runtime, `hc`.

Not a hook itself: `persona-pin.py` and `handover-signal.py` import it
(a hook runs as `python3 .claude/hooks/<name>.py`, so this directory is
on `sys.path`). Everything here is best-effort and silent. No herdr, no
`hc`, a slow core or a refused call all leave the caller's work exactly
as it was.
"""

import os
import re
import shutil
import subprocess

CONFIG = os.path.join(".claude", "config.yaml")

HERDR_MODES = ("auto", "off")
DEFAULT_HERDR_MODE = "auto"

# A label call talks to a local socket; anything slower is a core in
# trouble, and USER's prompt must not wait on it.
HC_TIMEOUT_SECONDS = 2


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


def terminal(root):
    """This session's herdr terminal and the `hc` binary, or None.

    None when the session is not in herdr, `herdr.enabled` is `off`, or
    `hc` is not on PATH.
    """
    address = os.environ.get("HC_TERMINAL_ID")
    if not address:
        return None
    mode = config_value(root, "herdr", "enabled", HERDR_MODES, DEFAULT_HERDR_MODE)
    if mode == "off":
        return None
    hc = shutil.which("hc") or shutil.which("herdr-core")
    if not hc:
        return None
    return hc, address


def label(hc, address, labels):
    """`hc label <address> k=v …`; `k=` removes a label. Never raises."""
    try:
        subprocess.run(
            [hc, "label", address, *(f"{k}={v}" for k, v in labels.items())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=HC_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return
