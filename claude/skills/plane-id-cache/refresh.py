"""Refresh the local Plane-ID cache used by all personas.

Reads `.claude/config.yaml` and `.claude/credentials.yaml`, then queries
Plane's public REST API for the stable UUIDs personas need every turn:
projects, workflow states, labels, modules, and workspace members.
Writes the result to `.claude/cache/plane-ids.yaml`.

Read-only against Plane. No attribution concern — uses any available
persona PAT (the first one that resolves).

Run via:
    uv run --no-project --with httpx --with pyyaml \
        python3 .claude/skills/plane-id-cache/refresh.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml


def _find_dotclaude(start: Path) -> Path | None:
    cur = start.resolve()
    for _ in range(8):
        candidate = cur / ".claude"
        if candidate.is_dir():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        print(f"!! could not parse {path}: {e}", file=sys.stderr)
        sys.exit(2)


def _verify_arg() -> bool | str:
    val = os.environ.get("PLANE_VERIFY_SSL", "true")
    if val.lower() in ("false", "0", "no"):
        return False
    if val.lower() in ("true", "1", "yes"):
        return True
    return val  # path to CA bundle


def _pick_token(creds: dict) -> tuple[str, str]:
    """Return (persona-name, PAT). Prefer personas with broad project
    visibility — VA is scoped to the business track and 403s on the dev
    project, so try BA first, then fall back to any other available."""
    plane = creds.get("plane") or {}
    tokens = plane.get("agent-tokens") or {}
    # Preference order: broad-read personas first, VA last.
    preferred = [
        "business-analyst",
        "requirements-engineer",
        "software-architect",
        "backend-developer",
        "ui-developer",
        "test-manager",
        "security-reviewer",
        "release-manager",
        "technical-writer",
        "venture-advisor",
    ]
    for name in preferred:
        tok = tokens.get(name)
        if tok and isinstance(tok, str) and tok.startswith("plane_api_"):
            return name, tok
    # Fallback to any token in any order.
    for name, tok in tokens.items():
        if tok and isinstance(tok, str) and tok.startswith("plane_api_"):
            return name, tok
    print(
        "!! no persona PAT found in .claude/credentials.yaml under "
        "plane.agent-tokens.* — fill at least one before refreshing.",
        file=sys.stderr,
    )
    sys.exit(2)


def _unwrap(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("results") or []
    return []


def _get(client: httpx.Client, path: str) -> Any:
    r = client.get(path)
    if r.status_code != 200:
        print(f"!! GET {path} → {r.status_code}: {r.text[:200]}", file=sys.stderr)
        sys.exit(3)
    return r.json()


def main() -> None:
    dot = _find_dotclaude(Path.cwd())
    if not dot:
        print("!! no .claude/ directory found upward from cwd", file=sys.stderr)
        sys.exit(2)

    config = _read_yaml(dot / "config.yaml")
    creds = _read_yaml(dot / "credentials.yaml")

    plane_cfg = config.get("plane") or {}
    base_url = (plane_cfg.get("base-url") or plane_cfg.get("base_url") or "").rstrip("/")
    workspace = plane_cfg.get("workspace")
    if not base_url or not workspace:
        print(
            "!! .claude/config.yaml is missing plane.base-url or plane.workspace",
            file=sys.stderr,
        )
        sys.exit(2)

    persona, token = _pick_token(creds)
    client = httpx.Client(
        base_url=base_url,
        headers={"X-API-Key": token, "Content-Type": "application/json"},
        verify=_verify_arg(),
        timeout=30.0,
    )

    out: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "plane": {
            "base_url": base_url,
            "workspace_slug": workspace,
            "projects": {},
            "members": {"by-email": {}, "by-persona": {}},
        },
    }

    # Workspace members. Plane's PAT is workspace-scoped already, so a
    # workspace-id lookup is unnecessary for everything personas do.
    members = _unwrap(_get(client, f"/api/v1/workspaces/{workspace}/members/"))
    email_to_id: dict[str, str] = {}
    for m in members:
        # Plane's member object can be either {member: {...}} or flat.
        obj = m.get("member") if isinstance(m.get("member"), dict) else m
        email = obj.get("email")
        uid = obj.get("id") or m.get("id")
        if email and uid:
            email_to_id[email] = uid
    out["plane"]["members"]["by-email"] = dict(sorted(email_to_id.items()))

    # Persona → UUID via config.yaml's agents.<persona>.email.
    agents_cfg = config.get("agents") or {}
    persona_to_id: dict[str, str] = {}
    for pname, meta in agents_cfg.items():
        if not isinstance(meta, dict):
            continue
        pemail = meta.get("email")
        if pemail and pemail in email_to_id:
            persona_to_id[pname] = email_to_id[pemail]
    out["plane"]["members"]["by-persona"] = dict(sorted(persona_to_id.items()))

    # Projects, states, labels, modules.
    projects = _unwrap(_get(client, f"/api/v1/workspaces/{workspace}/projects/"))
    proj_summary: list[str] = []
    for p in projects:
        ident = p.get("identifier")
        pid = p.get("id")
        if not ident or not pid:
            continue
        states = _unwrap(_get(client, f"/api/v1/workspaces/{workspace}/projects/{pid}/states/"))
        labels = _unwrap(_get(client, f"/api/v1/workspaces/{workspace}/projects/{pid}/labels/"))
        # Modules endpoint may 404 if the project has none — that's OK.
        try:
            modules_raw = _get(client, f"/api/v1/workspaces/{workspace}/projects/{pid}/modules/")
            modules = _unwrap(modules_raw)
        except SystemExit:
            modules = []

        out["plane"]["projects"][ident] = {
            "id": pid,
            "name": p.get("name"),
            "states": dict(sorted((s.get("name"), s.get("id")) for s in states if s.get("name") and s.get("id"))),
            "labels": dict(sorted((l.get("name"), l.get("id")) for l in labels if l.get("name") and l.get("id"))),
            "modules": dict(sorted((m.get("name"), m.get("id")) for m in modules if m.get("name") and m.get("id"))),
        }
        proj_summary.append(
            f"{ident}({len(states)}s/{len(labels)}l/{len(modules)}m)"
        )

    cache_dir = dot / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "plane-ids.yaml"
    cache_path.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))

    print(
        f"plane-ids: {len(projects)} projects [{' '.join(proj_summary)}], "
        f"{len(persona_to_id)} personas, {len(email_to_id)} members "
        f"→ {cache_path.relative_to(Path.cwd())}"
    )
    client.close()


if __name__ == "__main__":
    main()
