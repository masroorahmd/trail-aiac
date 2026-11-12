#!/usr/bin/env python3
"""Install, update or remove Trail's herdr-app mod (`herdr/mods/trail`).

The mod belongs on the computer that shows the herdr window. That is
usually the one the consumer repos live on, and then `bin/install.py`
calls this for you. When the window runs elsewhere, run this once from
the framework checkout and point it at that computer:

    python3 bin/herdr_mod.py                 # this computer
    python3 bin/herdr_mod.py --ssh laptop    # the window's computer
    python3 bin/herdr_mod.py --uninstall [--ssh laptop]

Standard library only, so it runs wherever `python3` does. With
`--ssh` it sends its own source plus the mod's files to `ssh HOST
python3 -`; nothing needs to be installed there first.

Safe to re-run. It records what it installed in
`mods/trail/.trail-install.json` (hidden, so herdr ignores it) and:

- installs into an empty slot,
- updates only files that are still exactly as it left them; a mod
  someone edited, or a different mod already named `trail`, is left
  alone unless `--force`,
- runs `herdr-app check` when herdr-app is on PATH, and puts the
  previous files back if the new ones fail it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MOD_NAME = "trail"
RECORD = ".trail-install.json"
# main.js last: herdr reloads a mod on save, so its entry point should
# land after the modules it imports.
ENTRY = "main.js"
REMOTE_FLAG = "--trail-remote"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def app_home(explicit: str | None = None) -> Path | None:
    """The herdr-app home, or None when herdr-app never ran here."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("HERDR_APP_HOME")
    if env:
        return Path(env).expanduser()
    home = Path.home() / ".config" / "herdr-app"
    return home if home.is_dir() else None


def generated(rel: Path) -> bool:
    """Files herdr itself writes into a mod folder (or hidden ones)."""
    return (
        any(p.startswith(".") or p == "node_modules" for p in rel.parts)
        or rel.name == "jsconfig.json"
        or rel.name.endswith(".d.ts")
        # herdr's catalog files: they describe the mod, they are not it.
        or rel.as_posix() in ("RECIPE.md", "preview.png")
    )


def bundle(source: Path) -> dict[str, bytes]:
    """The mod's own files, relative path → bytes."""
    files = {}
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        if path.is_file() and not generated(rel):
            files[rel.as_posix()] = path.read_bytes()
    return files


def herdr_app() -> str | None:
    found = shutil.which("herdr-app")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "herdr-app"
    return str(local) if local.exists() else None


def check(target: Path) -> tuple[bool | None, str]:
    """`herdr-app check`: True / False, or None when it is not here."""
    binary = herdr_app()
    if not binary:
        return None, "herdr-app not on PATH; not checked"
    try:
        r = subprocess.run(
            [binary, "check", str(target)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"herdr-app check did not run: {exc}"
    out = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, out[0] if out else ""


def write(target: Path, rel: str, data: bytes) -> None:
    path = target / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def install(home: Path, files: dict[str, bytes], version: str, force: bool) -> tuple[int, str]:
    """Install or update. Returns (exit code, one-line outcome)."""
    target = home / "mods" / MOD_NAME
    record_path = target / RECORD
    record = {}
    if record_path.exists():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except ValueError:
            record = {}
    recorded = record.get("files") or {}

    current = {}
    if target.is_dir():
        current = {
            rel: (target / rel).read_bytes()
            for rel in bundle(target)
        }

    wanted = {rel: sha(data) for rel, data in files.items()}
    if current and not force:
        if recorded:
            edited = [r for r, h in recorded.items() if r in current and sha(current[r]) != h]
            if edited:
                return 1, (f"{target}: edited since the last install ({', '.join(edited)}); "
                           "left alone. Re-run with --force to replace it.")
        elif {r: sha(d) for r, d in current.items()} != wanted:
            return 1, (f"{target}: a mod named '{MOD_NAME}' is already there and is not "
                       "one this script installed; left alone. Re-run with --force to replace it.")

    if current and {r: sha(d) for r, d in current.items() if r in wanted} == wanted \
            and record.get("version") == version and set(recorded) == set(wanted):
        return 0, f"{target}: up to date ({version})"

    previous = dict(current)
    order = sorted(files, key=lambda r: (r == ENTRY, r))
    for rel in order:
        write(target, rel, files[rel])
    for rel in recorded:
        if rel not in files and (target / rel).exists():
            (target / rel).unlink()

    ok, detail = check(target)
    if ok is False:
        for rel in files:
            if rel in previous:
                write(target, rel, previous[rel])
            else:
                (target / rel).unlink(missing_ok=True)
        if not previous:
            shutil.rmtree(target, ignore_errors=True)
        return 1, f"{target}: herdr-app check failed, previous version kept: {detail}"

    write(target, RECORD, json.dumps(
        {"version": version, "files": wanted}, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n")
    verb = "updated" if previous else "installed"
    note = "" if ok else f" ({detail})"
    return 0, f"{target}: {verb} ({version}){note}"


def uninstall(home: Path, force: bool) -> tuple[int, str]:
    target = home / "mods" / MOD_NAME
    record_path = target / RECORD
    if not target.exists():
        return 0, f"{target}: not installed"
    if not record_path.exists() and not force:
        return 1, f"{target}: not installed by this script; left alone (--force removes it)"
    if not force:
        recorded = json.loads(record_path.read_text(encoding="utf-8")).get("files") or {}
        edited = [r for r, h in recorded.items()
                  if (target / r).exists() and sha((target / r).read_bytes()) != h]
        if edited:
            return 1, f"{target}: edited since install ({', '.join(edited)}); left alone (--force removes it)"
    shutil.rmtree(target)
    return 0, f"{target}: removed"


def run(payload: dict) -> int:
    """The part that runs on the window's computer, locally or over ssh."""
    home = app_home(payload.get("app_home"))
    if home is None:
        print("herdr-app home not found (~/.config/herdr-app). Open herdr once, "
              "or pass --app-home.", file=sys.stderr)
        return 1
    if payload.get("uninstall"):
        code, line = uninstall(home, payload.get("force", False))
    else:
        files = {r: base64.b64decode(d) for r, d in payload["files"].items()}
        code, line = install(home, files, payload["version"], payload.get("force", False))
    print(line, file=sys.stderr if code else sys.stdout)
    return code


def framework_root() -> Path:
    return Path(__file__).resolve().parent.parent


def version(root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def payload_for(root: Path, args) -> dict:
    files = bundle(root / "herdr" / "mods" / MOD_NAME)
    return {
        "files": {r: base64.b64encode(d).decode("ascii") for r, d in files.items()},
        "version": version(root),
        "app_home": args.app_home,
        "force": args.force,
        "uninstall": args.uninstall,
    }


def over_ssh(host: str, payload: dict) -> int:
    """Run `run(payload)` on HOST with nothing but its python3."""
    source = Path(__file__).read_text(encoding="utf-8")
    program = (
        source
        + "\n\nimport sys as _s\n"
        + f"_s.exit(run(__import__('json').loads({json.dumps(json.dumps(payload))})))\n"
    )
    try:
        r = subprocess.run(
            ["ssh", host, "python3", "-", REMOTE_FLAG], input=program, text=True
        )
    except OSError as exc:
        print(f"ssh did not run: {exc}", file=sys.stderr)
        return 1
    if r.returncode == 127:
        print(f"{host}: python3 not found there.", file=sys.stderr)
    return r.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install, update or remove Trail's herdr-app mod."
    )
    parser.add_argument("--ssh", metavar="HOST", help="install on the window's computer over ssh")
    parser.add_argument("--app-home", help="herdr-app home (default: $HERDR_APP_HOME or ~/.config/herdr-app)")
    parser.add_argument("--force", action="store_true", help="replace an edited or foreign 'trail' mod")
    parser.add_argument("--uninstall", action="store_true", help="remove the mod")
    args = parser.parse_args()

    payload = payload_for(framework_root(), args)
    if args.ssh:
        return over_ssh(args.ssh, payload)
    return run(payload)


# Sent over ssh, this file runs as `python3 - --trail-remote` with a
# payload appended; the flag keeps the CLI from starting there as well.
if __name__ == "__main__" and REMOTE_FLAG not in sys.argv:
    sys.exit(main())
