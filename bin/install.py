#!/usr/bin/env python3
"""Install the Trail framework into a consumer project.

One-shot, idempotent. Two stages, run in sequence:

  1. **Copy + seed.** Framework deliverables (`agents/`, `skills/`,
     `commands/`, `mcp/`, `*.example/`, `settings.json`) are copied
     from `<framework>/claude/` into `<consumer>/.claude/` as REAL
     files, overwriting any older copy. Consumer-owned slots
     (`config.yaml`, `credentials.yaml`, `context/`, `agent-memory/`)
     are seeded from their `.example` siblings on first install and
     preserved on every subsequent run.

  2. **Render.** When `config.yaml` + `credentials.yaml` are populated
     with real values (heuristic: not-just-example-stub, and the
     declared agent set has matching API tokens), the script also
     writes per-persona MCP wiring:

       - `<consumer>/.claude/settings.local.json` (mode 0600) — env
         block holding shared FRAMEWORK_ROOT / PLANE_BASE_URL /
         PLANE_WORKSPACE_SLUG plus per-persona PLANE_API_KEY_*. Used
         by skills and ad-hoc scripts that read these from the
         process env.

       - `<consumer>/.mcp.json` (mode 0600, gitignored) — 10 ×
         `plane-<persona>` + 10 × `plane-extras-<persona>` server
         entries with credentials inlined. Reaches the main Claude
         Code session only (subagents do NOT inherit `.mcp.json` in
         CC 2.1.119); kept anyway because `claude mcp list` against
         it is a useful diagnostic and main-loop ad-hoc Plane work
         sometimes wants it.

       - `<consumer>/.claude/agents/*.md` (mode 0600) — re-templated
         in place: every `__VAR__` placeholder in the persona's
         `mcpServers:` block is replaced with the real value. This
         is the only path that gives subagents per-persona MCP
         scope in CC 2.1.119; the `${VAR}` substitution route in
         frontmatter is broken upstream
         (anthropics/claude-code#1254).

     The first run after a fresh install typically only does stage 1
     (config + creds were just seeded as empty stubs). After the user
     has filled in `config.yaml` + `credentials.yaml`, re-running this
     script picks up stage 2 automatically.

Usage:

    bin/install.py <consumer-dir>           # idempotent, do both stages
    bin/install.py <consumer-dir> --force-seed
                                            # also overwrite context/ from
                                            # the .example. Never touches
                                            # config.yaml, credentials.yaml,
                                            # settings.local.json, or
                                            # agent-memory/.

Exits non-zero only on a fatal error (missing framework deliverables,
missing consumer dir, render configured but credentials inconsistent).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(
        "ERROR: PyYAML not installed. Install with: pip install pyyaml\n"
        "Or run via: uv run --with pyyaml bin/install.py <consumer-dir>"
    )


# Items copied unconditionally on every install. These are the framework
# deliverables — they may have been updated since the last install.
# Note: the *.example/ templates are NOT in this list. They live in the
# framework's `claude/` and are read from there by the SEEDED step below;
# the consumer's `.claude/` only ever holds the seeded REAL files
# (config.yaml, credentials.yaml, context/, agent-memory/).
DELIVERABLES = [
    "agents",
    "skills",
    "commands",
    "mcp",
    "workflows",
    "settings.json",
]

# Items seeded on first install (from a corresponding .example source)
# and then preserved on re-install. `force_eligible` controls whether
# `--force-seed` may overwrite an existing target:
#   - context/ → True (drafts are reproducible from /kickoff if needed)
#   - everything else → False (configs hold real Plane creds, memory is
#     accumulated agent state that must never be clobbered).
# Tuple: (target_name, example_source_name, kind, force_eligible)
SEEDED = [
    ("config.yaml", "config.yaml.example", "file", False),
    ("credentials.yaml", "credentials.yaml.example", "file", False),
    ("context", "context.example", "dir", True),
    ("agent-memory", "agent-memory.example", "dir", False),
]


# ---------------------------------------------------------------------------
# Stage 1 — copy + seed
# ---------------------------------------------------------------------------

def copy_deliverable(src: Path, dst: Path) -> None:
    """Copy a file or directory, overwriting any existing target."""
    if dst.exists():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def ensure_gitignore_entries(
    consumer_root: Path, entries: list[str]
) -> list[str]:
    """Idempotently append framework-required entries to the consumer's
    `.gitignore`. Returns the entries that were actually appended (may be
    empty). Creates `.gitignore` if it doesn't exist."""
    gitignore_path = consumer_root / ".gitignore"
    existing = ""
    if gitignore_path.is_file():
        existing = gitignore_path.read_text(encoding="utf-8")
    existing_lines = {ln.strip() for ln in existing.splitlines() if ln.strip()}
    to_append = [e for e in entries if e not in existing_lines]
    if not to_append:
        return []
    block = (
        "\n# Trail framework — these hold inlined Plane API\n"
        "# tokens / UI passwords / per-persona MCP server config; never commit.\n"
        + "\n".join(to_append) + "\n"
    )
    if existing and not existing.endswith("\n"):
        block = "\n" + block
    with gitignore_path.open("a", encoding="utf-8") as f:
        f.write(block)
    return to_append


def seed_if_absent(
    src: Path, dst: Path, kind: str, force: bool, log: list[str]
) -> bool:
    """Copy src→dst only if dst doesn't exist OR force is True.

    Returns True if the target was freshly seeded (i.e. the consumer-
    owned slot did not exist before this install). False otherwise —
    either preserved or re-seeded over an existing target."""
    if dst.exists() and not force:
        log.append(f"  preserved {dst.name} (exists)")
        return False
    fresh_seed = not dst.exists()
    if dst.exists() and force:
        if kind == "dir":
            shutil.rmtree(dst)
        else:
            dst.unlink()
        log.append(f"  re-seeded {dst.name} (--force-seed)")
    else:
        log.append(f"  seeded {dst.name}")
    if kind == "dir":
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return fresh_seed


# ---------------------------------------------------------------------------
# Stage 2 — render per-persona MCP wiring
# ---------------------------------------------------------------------------

def persona_env_prefix(username: str) -> str:
    """`business-analyst` → `BUSINESS_ANALYST`."""
    return username.upper().replace("-", "_")


def looks_unfilled(value) -> bool:
    """Treat empty strings, None, and the obvious example-stub markers
    as not-yet-populated. The example templates use `example.com`
    domains, the literal placeholder `plane_api_...` for tokens, and
    leave `password:` fields empty."""
    if value is None:
        return True
    s = str(value).strip()
    if not s:
        return True
    if s.startswith("plane_api_..."):
        return True
    return False


def render_ready(consumer_claude: Path) -> tuple[bool, list[str]]:
    """Quick sniff: can we render now, or does the user still need to
    fill in config.yaml / credentials.yaml? Returns (ready, reasons).
    `ready` is True only when we have a non-stub plane.base-url, a
    workspace, at least one agent declared, and an API token for
    every declared agent. `reasons` documents what's missing for the
    user-facing log when we skip render."""
    config_path = consumer_claude / "config.yaml"
    creds_path = consumer_claude / "credentials.yaml"
    reasons: list[str] = []
    if not config_path.is_file():
        reasons.append(f"{config_path} missing")
        return False, reasons
    if not creds_path.is_file():
        reasons.append(f"{creds_path} missing")
        return False, reasons

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    creds = yaml.safe_load(creds_path.read_text(encoding="utf-8")) or {}
    plane_cfg = config.get("plane") or {}
    base_url = plane_cfg.get("base-url")
    workspace = plane_cfg.get("workspace")
    if looks_unfilled(base_url) or "example.com" in (str(base_url) or ""):
        reasons.append("config.yaml: plane.base-url not set (still points at example.com)")
    if looks_unfilled(workspace) or workspace == "example":
        reasons.append("config.yaml: plane.workspace not set")
    agents = config.get("agents") or {}
    if not agents:
        reasons.append("config.yaml: no agents declared")

    plane_creds = creds.get("plane") or {}
    api_tokens = plane_creds.get("agent-tokens") or {}
    for username in agents:
        if looks_unfilled(api_tokens.get(username)):
            reasons.append(
                f"credentials.yaml: plane.agent-tokens.{username} not set"
            )
    return (not reasons), reasons


def render_settings(
    framework_root: Path, consumer_root: Path, consumer_claude: Path
) -> int:
    """Strict render. Reads config.yaml + credentials.yaml, writes
    settings.local.json + .mcp.json + re-templates persona files.
    Caller should only invoke this when render_ready() returned True;
    we still validate defensively and exit non-zero on anything
    inconsistent."""
    config_path = consumer_claude / "config.yaml"
    creds_path = consumer_claude / "credentials.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    creds = yaml.safe_load(creds_path.read_text(encoding="utf-8")) or {}

    plane_cfg = config.get("plane") or {}
    base_url = plane_cfg.get("base-url")
    workspace = plane_cfg.get("workspace")
    if not base_url or not workspace:
        sys.exit(
            f"ERROR: {config_path} missing plane.base-url or plane.workspace"
        )

    env: dict[str, str] = {
        "FRAMEWORK_ROOT": str(framework_root),
        "PLANE_BASE_URL": base_url,
        "PLANE_WORKSPACE_SLUG": workspace,
        # USER↔persona chat language. Substituted into each persona's
        # `## Operating mode → Language` bullet. Artefacts (code, Plane
        # bodies, commits, …) stay English regardless — that rule is
        # hard-coded into the persona prompts.
        "CHAT_LANGUAGE": str(config.get("chat_language") or "English"),
        # USER's preferred first name. Substituted into each persona's
        # `## Operating mode → USER's name` bullet. When empty, the
        # entire bullet (wrapped between `<!-- USER_NAME_LINE -->` and
        # `<!-- /USER_NAME_LINE -->` markers in the source prompt) is
        # stripped at render time so agents don't trip on an empty
        # placeholder.
        "USER_NAME": str(config.get("user_name") or "").strip(),
    }

    agents = config.get("agents") or {}
    if not agents:
        sys.exit(f"ERROR: {config_path} declares no agents")

    plane_creds = creds.get("plane") or {}
    api_tokens = plane_creds.get("agent-tokens") or {}

    missing: list[str] = []
    for username in agents:
        prefix = persona_env_prefix(username)
        token = api_tokens.get(username)
        if not token:
            missing.append(f"{username}: no api token in credentials.yaml")
            continue
        env[f"PLANE_API_KEY_{prefix}"] = token

    if missing:
        print("ERROR: missing credentials for one or more agents:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    plane_extras_dir = framework_root / "claude" / "mcp"
    mcp_servers: dict = {}
    for username in agents:
        prefix = persona_env_prefix(username)
        api_token = env[f"PLANE_API_KEY_{prefix}"]

        mcp_servers[f"plane-{username}"] = {
            "command": "uvx",
            "args": ["plane-mcp-server"],
            "env": {
                "PLANE_API_KEY": api_token,
                "PLANE_BASE_URL": base_url,
                "PLANE_WORKSPACE_SLUG": workspace,
            },
        }
        mcp_servers[f"plane-extras-{username}"] = {
            "command": "uv",
            "args": ["run", "--directory", str(plane_extras_dir), "plane-extras-mcp"],
            "env": {
                "PLANE_API_KEY": api_token,
                "PLANE_BASE_URL": base_url,
                "PLANE_WORKSPACE_SLUG": workspace,
            },
        }

    settings_local_path = consumer_claude / "settings.local.json"
    mcp_json_path = consumer_root / ".mcp.json"

    settings_local = {"env": dict(sorted(env.items()))}
    mcp_json = {"mcpServers": dict(sorted(mcp_servers.items()))}

    settings_local_path.write_text(
        json.dumps(settings_local, indent=2) + "\n", encoding="utf-8"
    )
    settings_local_path.chmod(0o600)
    mcp_json_path.write_text(
        json.dumps(mcp_json, indent=2) + "\n", encoding="utf-8"
    )
    mcp_json_path.chmod(0o600)

    rendered_personas = render_persona_files(consumer_claude, env)

    print(f"  wrote {settings_local_path} (mode 0600)")
    print(f"  wrote {mcp_json_path} (mode 0600)")
    for path in rendered_personas:
        print(f"  rendered {path.name} (mode 0600)")
    return 0


USER_NAME_BLOCK_RE = re.compile(
    r"<!-- USER_NAME_LINE -->\n.*?\n<!-- /USER_NAME_LINE -->\n",
    re.DOTALL,
)


def render_persona_files(consumer_claude: Path, env_map: dict[str, str]) -> list[Path]:
    """Substitute `__VAR__` placeholders in each
    `<consumer>/.claude/agents/*.md` with the corresponding value from
    `env_map`. Files without placeholders are left untouched. Returns
    the list of paths actually rewritten. Rewrites are mode 0600.

    Conditional blocks: any text wrapped between `<!-- USER_NAME_LINE -->`
    and `<!-- /USER_NAME_LINE -->` markers is kept (with markers
    stripped) when `USER_NAME` is non-empty, and removed wholesale when
    it is empty — so consumers who didn't set `user_name` in
    `config.yaml` don't see an awkward bullet referring to a blank
    placeholder.
    """
    agents_dir = consumer_claude / "agents"
    if not agents_dir.is_dir():
        return []
    user_name = env_map.get("USER_NAME", "")
    written: list[Path] = []
    for persona_path in sorted(agents_dir.glob("*.md")):
        original = persona_path.read_text(encoding="utf-8")
        substituted = original
        if user_name:
            substituted = substituted.replace("<!-- USER_NAME_LINE -->\n", "")
            substituted = substituted.replace("<!-- /USER_NAME_LINE -->\n", "")
        else:
            substituted = USER_NAME_BLOCK_RE.sub("", substituted)
        for var_name, value in env_map.items():
            substituted = substituted.replace(f"__{var_name}__", value)
        if substituted != original:
            persona_path.write_text(substituted, encoding="utf-8")
            persona_path.chmod(0o600)
            written.append(persona_path)
    return written


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the Trail framework into a consumer project."
    )
    parser.add_argument(
        "consumer_dir",
        help="Path to the consumer project directory (must already exist).",
    )
    parser.add_argument(
        "--force-seed",
        action="store_true",
        help="Also overwrite consumer-owned context/ from the .example "
             "sources. Does NOT touch config.yaml, credentials.yaml, "
             "agent-memory/, or settings.local.json.",
    )
    args = parser.parse_args()

    framework_root = Path(__file__).resolve().parent.parent
    framework_claude = framework_root / "claude"
    consumer_root = Path(args.consumer_dir).resolve()
    consumer_claude = consumer_root / ".claude"

    if not framework_claude.is_dir():
        sys.exit(f"ERROR: framework deliverables not found at {framework_claude}")
    if not consumer_root.is_dir():
        sys.exit(
            f"ERROR: consumer dir does not exist: {consumer_root}\n"
            f"Create it first (`mkdir {consumer_root}`)."
        )
    # Defensive: refuse to install into the framework's own root by accident.
    if consumer_root == framework_root:
        sys.exit(
            "ERROR: refusing to install into the framework's own repo root. "
            "Pick a sibling/sub directory instead."
        )

    if consumer_claude.is_symlink():
        print(f"removing stale symlink: {consumer_claude}", file=sys.stderr)
        consumer_claude.unlink()

    consumer_claude.mkdir(exist_ok=True)

    # Stage 1 — copy deliverables, seed consumer-owned slots.
    log_deliv: list[str] = []
    for name in DELIVERABLES:
        src = framework_claude / name
        if not src.exists():
            log_deliv.append(f"  MISSING in framework, skipped: {name}")
            continue
        dst = consumer_claude / name
        copy_deliverable(src, dst)
        log_deliv.append(f"  copied {name}")

    log_seed: list[str] = []
    fresh_seeds: set[str] = set()
    for target_name, example_name, kind, force_eligible in SEEDED:
        src = framework_claude / example_name
        if not src.exists():
            log_seed.append(f"  MISSING source {example_name} in framework — cannot seed {target_name}")
            continue
        dst = consumer_claude / target_name
        force_this = args.force_seed and force_eligible
        is_fresh = seed_if_absent(src, dst, kind, force_this, log_seed)
        if is_fresh:
            fresh_seeds.add(target_name)

    gitignore_added = ensure_gitignore_entries(
        consumer_root, [".mcp.json", ".claude/agents/"]
    )

    print(f"Installed framework into {consumer_claude}")
    print()
    print("Deliverables (overwritten on every install):")
    for line in log_deliv:
        print(line)
    print()
    print("Consumer-owned (seeded once, preserved on re-install):")
    for line in log_seed:
        print(line)
    print()
    if gitignore_added:
        print(f"Added to {consumer_root}/.gitignore: {', '.join(gitignore_added)}")
    else:
        print(f"{consumer_root}/.gitignore already covers .mcp.json + .claude/agents/")
    print()

    # Stage 2 — render MCP wiring iff config + credentials look populated.
    ready, reasons = render_ready(consumer_claude)
    if not ready:
        print("Skipping MCP render — config or credentials not yet populated:")
        for r in reasons:
            print(f"  - {r}")
        print()
        print("Next steps:")
        print(f"  1. Edit {consumer_claude}/config.yaml")
        print(f"     (set plane.base-url, plane.workspace, agents.*.email)")
        print(f"  2. Edit {consumer_claude}/credentials.yaml")
        print(f"     (paste per-agent API tokens)")
        print(f"  3. Re-run: {framework_root}/bin/install.py {consumer_root}")
        print(f"     (this time it will render MCP wiring + settings.local.json + .mcp.json)")
        print(f"  4. cd {consumer_root} && claude")
        print(f"     > /kickoff   (one-time bootstrap of .claude/context/*.md from the project)")
        print(f"     > /ba ...    (start your first Story)")
        return 0

    print("Rendering per-persona MCP wiring (settings.local.json + .mcp.json + agents/*.md) …")
    rc = render_settings(framework_root, consumer_root, consumer_claude)
    if rc != 0:
        return rc

    print()
    print("Done. Next:")
    print(f"  cd {consumer_root} && claude")
    print(f"  > /kickoff   (one-time bootstrap of .claude/context/*.md from the project)")
    print(f"  > /ba ...    (start your first Story)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
