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


def _get(client: httpx.Client, path: str, *, soft: bool = False) -> Any:
    r = client.get(path)
    if r.status_code != 200:
        msg = f"!! GET {path} → {r.status_code}: {r.text[:200]}"
        if soft:
            print(msg, file=sys.stderr)
            return None
        print(msg, file=sys.stderr)
        sys.exit(3)
    return r.json()


def _all_tokens(creds: dict) -> list[tuple[str, str]]:
    """All persona PATs, primary first, for per-project failover —
    no single persona is a member of every project (e.g. HQ is
    GM-only), so project-scoped endpoints may 403 for the primary."""
    plane = creds.get("plane") or {}
    tokens = plane.get("agent-tokens") or {}
    primary, _ = _pick_token(creds)
    names = [primary] + [n for n in tokens if n != primary]
    return [
        (n, tokens[n])
        for n in names
        if isinstance(tokens.get(n), str) and tokens[n].startswith("plane_api_")
    ]


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

    def _mk_client(tok: str) -> httpx.Client:
        return httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": tok, "Content-Type": "application/json"},
            verify=_verify_arg(),
            timeout=30.0,
        )

    client = _mk_client(token)
    fallback_clients: list[tuple[str, httpx.Client]] = [
        (n, _mk_client(t)) for n, t in _all_tokens(creds) if t != token
    ]

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
        # The workspace project list includes projects the primary
        # persona is NOT a member of; their per-project endpoints 403.
        # Try the primary first, then every other PAT; skip if none fits.
        states_raw = None
        pclient = client
        for cand_name, cand_client in [(persona, client)] + fallback_clients:
            states_raw = _get(
                cand_client,
                f"/api/v1/workspaces/{workspace}/projects/{pid}/states/",
                soft=True,
            )
            if states_raw is not None:
                pclient = cand_client
                if cand_name != persona:
                    print(
                        f"   {ident}: read via {cand_name} "
                        f"(primary {persona} lacks access)",
                        file=sys.stderr,
                    )
                break
        if states_raw is None:
            print(f"!! {ident}: no persona PAT has access — skipped", file=sys.stderr)
            continue
        states = _unwrap(states_raw)
        labels = _unwrap(
            _get(pclient, f"/api/v1/workspaces/{workspace}/projects/{pid}/labels/", soft=True)
            or []
        )
        # Modules endpoint may 404 if the project has none — that's OK.
        modules_raw = _get(
            pclient, f"/api/v1/workspaces/{workspace}/projects/{pid}/modules/", soft=True
        )
        modules = _unwrap(modules_raw) if modules_raw is not None else []

        # Cycles (sprints) churn faster than the rest — a new one each
        # sprint — but caching name→id still saves the BA a round-trip
        # when resolving "the current sprint". Endpoint may 404 if the
        # project has none.
        cycles_raw = _get(
            pclient, f"/api/v1/workspaces/{workspace}/projects/{pid}/cycles/", soft=True
        )
        cycles = _unwrap(cycles_raw) if cycles_raw is not None else []

        out["plane"]["projects"][ident] = {
            "id": pid,
            "name": p.get("name"),
            "states": dict(sorted((s.get("name"), s.get("id")) for s in states if s.get("name") and s.get("id"))),
            "labels": dict(sorted((l.get("name"), l.get("id")) for l in labels if l.get("name") and l.get("id"))),
            "modules": dict(sorted((m.get("name"), m.get("id")) for m in modules if m.get("name") and m.get("id"))),
            "cycles": dict(sorted((c.get("name"), c.get("id")) for c in cycles if c.get("name") and c.get("id"))),
        }
        proj_summary.append(
            f"{ident}({len(states)}s/{len(labels)}l/{len(modules)}m/{len(cycles)}c)"
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
