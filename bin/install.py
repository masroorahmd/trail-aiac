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

       - `<consumer>/.mcp.json` (mode 0600, gitignored) — one
         `plane` server entry. A single stdio process holds every
         persona's API token in its env block and registers every
         tool N×, prefixed by the persona's snake-case username
         (e.g. `business_analyst__list_states`). Replaces the
         pre-refactor 22-entry explosion (one upstream
         `plane-mcp-server` + one `plane-extras-mcp` per persona),
         which cost ~2 GB of RSS per Claude session.

       - `<consumer>/.claude/agents/*.md` (mode 0600) — re-templated
         in place: every `__VAR__` placeholder (`__CHAT_LANGUAGE__`,
         `__USER_NAME__`, …) is replaced with the real value, and the
         conditional USER_NAME bullet is stripped when no name was
         supplied. The persona files do not carry per-persona MCP
         tokens any more — those live exclusively in `.mcp.json`'s
         single `plane` entry.

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
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
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

# Model lanes — defaults applied when the consumer's config.yaml has no
# `model_lanes:` section (e.g. a config seeded before the knob existed).
# Substituted into persona/command files as `__MODEL_<LANE>__`
# placeholders by render_persona_files().
DEFAULT_MODEL_LANES = {
    "standard": "claude-sonnet-4-6",
    "full": "claude-fable-5",
    "codegen": "claude-opus-4-8",
}


# ---------------------------------------------------------------------------
# Install manifest — provenance + consumer-side drift detection
# ---------------------------------------------------------------------------

# Written to <consumer>/.claude/trail-manifest.yaml at the end of every
# install: which framework commit + version produced the deliverables,
# when, and a sha256 of every deliverable file as install.py left it. On
# the next run we re-hash *before* Stage 1 overwrites anything and warn
# about each file whose hash drifted from the manifest — i.e. a
# consumer-side hand-edit this run is about to clobber.
MANIFEST_NAME = "trail-manifest.yaml"

# Never hash (nor let them bloat the manifest): local dev/build cruft that
# can ride along inside a copied deliverable dir such as `claude/mcp/`.
_HASH_IGNORE_PARTS = {"__pycache__", ".venv", ".pytest_cache", ".git", ".mypy_cache"}


def _iter_deliverable_files(consumer_claude: Path):
    """Yield (relpath_str, Path) for every real deliverable file currently
    installed under <consumer>/.claude/, skipping local build cruft."""
    for name in DELIVERABLES:
        base = consumer_claude / name
        if not base.exists():
            continue
        paths = [base] if base.is_file() else sorted(base.rglob("*"))
        for p in paths:
            if not p.is_file():
                continue
            rel = p.relative_to(consumer_claude)
            if any(part in _HASH_IGNORE_PARTS for part in rel.parts):
                continue
            yield str(rel), p


def compute_deliverable_hashes(consumer_claude: Path) -> dict[str, str]:
    """sha256 of every installed deliverable file, keyed by path relative
    to <consumer>/.claude/."""
    return {
        rel: hashlib.sha256(path.read_bytes()).hexdigest()
        for rel, path in _iter_deliverable_files(consumer_claude)
    }


def framework_commit(framework_root: Path) -> str | None:
    """git HEAD of the framework repo, or None if it isn't a git checkout
    / git isn't available."""
    try:
        out = subprocess.run(
            ["git", "-C", str(framework_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def framework_version(framework_claude: Path) -> str | None:
    """The framework's declared version, read from its
    `config.yaml.example` `framework.version` — previously a dead field,
    now recorded in the manifest. None if absent/unreadable."""
    example = framework_claude / "config.yaml.example"
    if not example.is_file():
        return None
    try:
        data = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    version = (data.get("framework") or {}).get("version")
    return str(version) if version is not None else None


def load_manifest(consumer_claude: Path) -> dict:
    """Prior install manifest, or {} on a first install / unreadable file."""
    path = consumer_claude / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def detect_drift(consumer_claude: Path, manifest: dict) -> list[str]:
    """Deliverable files whose current on-disk hash differs from what the
    manifest recorded at the last install — consumer-side hand-edits a
    fresh copy is about to overwrite. Only files present in both the
    manifest and on disk are compared; new/removed files aren't drift."""
    recorded = (manifest or {}).get("files") or {}
    if not recorded:
        return []
    drifted = [
        rel
        for rel, path in _iter_deliverable_files(consumer_claude)
        if rel in recorded
        and hashlib.sha256(path.read_bytes()).hexdigest() != recorded[rel]
    ]
    return sorted(drifted)


def write_manifest(
    consumer_claude: Path,
    framework_root: Path,
    framework_claude: Path,
    installed_at: str,
) -> Path:
    """Record framework provenance + per-file hashes of the deliverables
    as this run left them, for the next run's drift check."""
    manifest = {
        "framework": {
            "version": framework_version(framework_claude),
            "commit": framework_commit(framework_root),
        },
        "installed_at": installed_at,
        "files": compute_deliverable_hashes(consumer_claude),
    }
    header = (
        "# Auto-generated by bin/install.py — do not edit by hand.\n"
        "# Records which framework commit/version produced the installed\n"
        "# deliverables and a sha256 of each, so a re-install can warn\n"
        "# before overwriting any consumer-side hand-edit.\n"
    )
    path = consumer_claude / MANIFEST_NAME
    path.write_text(
        header + yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8"
    )
    return path


# ---------------------------------------------------------------------------
# Stage 1 — copy + seed
# ---------------------------------------------------------------------------

# Local dev/build cruft that must never be shipped into a consumer when a
# deliverable dir (notably `claude/mcp/`) is copied wholesale.
_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".venv", ".pytest_cache", ".mypy_cache",
    "*.egg-info", "*:Zone.Identifier",
)


def copy_deliverable(src: Path, dst: Path) -> None:
    """Copy a file or directory, overwriting any existing target. Local
    build cruft (`.venv/`, `__pycache__/`, …) is filtered out."""
    if dst.exists():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if src.is_dir():
        shutil.copytree(src, dst, ignore=_COPY_IGNORE)
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
        "# tokens / UI passwords / multi-tenant MCP wiring; never commit.\n"
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

    # Model lanes: consumer config overrides the framework defaults
    # lane-by-lane. Each lane becomes a MODEL_<LANE> env entry and an
    # `__MODEL_<LANE>__` placeholder substitution in persona/command
    # files (agent frontmatter `model:` for subagents, `/model …`
    # reminders in the /sa and /sr dispatchers).
    model_lanes = {**DEFAULT_MODEL_LANES, **(config.get("model_lanes") or {})}
    for lane, model_id in model_lanes.items():
        env[f"MODEL_{persona_env_prefix(str(lane))}"] = str(model_id)

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

    plane_mcp_dir = framework_root / "claude" / "mcp"
    # Single multi-tenant MCP server entry. The server reads
    # PLANE_API_KEY_<PERSONA_PREFIX> from its env block at startup,
    # registers every tool N×, prefixed by persona snake. Per-persona
    # tokens MUST be inlined here because stdio MCP servers do not
    # inherit the consumer's settings.local.json env automatically.
    plane_env: dict[str, str] = {
        "PLANE_BASE_URL": base_url,
        "PLANE_WORKSPACE_SLUG": workspace,
    }
    for username in agents:
        prefix = persona_env_prefix(username)
        plane_env[f"PLANE_API_KEY_{prefix}"] = env[f"PLANE_API_KEY_{prefix}"]

    mcp_servers: dict = {
        "plane": {
            "command": "uv",
            "args": ["run", "--directory", str(plane_mcp_dir), "plane-extras-mcp"],
            "env": plane_env,
        }
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
    `<consumer>/.claude/agents/*.md` AND `<consumer>/.claude/commands/*.md`
    with the corresponding value from `env_map`. (Commands carry the
    same placeholders — `/quick` references CHAT_LANGUAGE and the
    user's name.) Files without placeholders are left untouched.
    Returns the list of paths actually rewritten. Rewrites are mode 0600.

    Conditional blocks: any text wrapped between `<!-- USER_NAME_LINE -->`
    and `<!-- /USER_NAME_LINE -->` markers is kept (with markers
    stripped) when `USER_NAME` is non-empty, and removed wholesale when
    it is empty — so consumers who didn't set `user_name` in
    `config.yaml` don't see an awkward bullet referring to a blank
    placeholder.
    """
    render_targets: list[Path] = []
    for subdir in ("agents", "commands"):
        d = consumer_claude / subdir
        if d.is_dir():
            render_targets.extend(sorted(d.glob("*.md")))
    if not render_targets:
        return []
    user_name = env_map.get("USER_NAME", "")
    written: list[Path] = []
    for persona_path in render_targets:
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

    installed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Drift check — compare the deliverables as they stand now (from the
    # previous install) against the manifest we wrote then, and warn
    # BEFORE Stage 1 overwrites any consumer-side hand-edit.
    prior_manifest = load_manifest(consumer_claude)
    drifted = detect_drift(consumer_claude, prior_manifest)
    if drifted:
        prev = prior_manifest.get("framework") or {}
        prev_commit = prev.get("commit") or "unknown"
        print("WARNING: consumer-side edits detected in framework deliverables.")
        print("These differ from the last install and will be OVERWRITTEN:")
        for rel in drifted:
            print(f"  ! {rel}")
        print(
            f"(last install: commit "
            f"{prev_commit[:12] if prev_commit != 'unknown' else prev_commit}"
            f", {prior_manifest.get('installed_at', 'unknown time')})"
        )
        print("Framework deliverables are not meant to be hand-edited — make")
        print("such changes in the framework repo. Proceeding to overwrite.")
        print()

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
        manifest_path = write_manifest(
            consumer_claude, framework_root, framework_claude, installed_at
        )
        print()
        print(f"Wrote install manifest {manifest_path.name} (framework provenance + file hashes).")
        return 0

    print("Rendering per-persona MCP wiring (settings.local.json + .mcp.json + agents/*.md + commands/*.md) …")
    rc = render_settings(framework_root, consumer_root, consumer_claude)
    if rc != 0:
        return rc

    manifest_path = write_manifest(
        consumer_claude, framework_root, framework_claude, installed_at
    )
    print(f"  wrote {manifest_path.name} (framework provenance + file hashes)")

    print()
    print("Done. Next:")
    print(f"  cd {consumer_root} && claude")
    print(f"  > /kickoff   (one-time bootstrap of .claude/context/*.md from the project)")
    print(f"  > /ba ...    (start your first Story)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
