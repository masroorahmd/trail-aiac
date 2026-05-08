#!/usr/bin/env python3
"""Link a consumer's .claude/ to a shared context repo (claude-context/).

For multi-consumer setups (one company, several repos sharing one Plane
workspace + product narrative). The shared dir holds the cross-cutting
artefacts; each consumer's `.claude/` symlinks to them.

Two modes:

  Bootstrap (one-time, from a canonical consumer):
      bin/link-shared.py --shared <shared> --bootstrap-from <consumer>

      Copies the consumer's shared files into <shared>. Refuses if
      <shared> already has a divergent copy (use --force to overwrite).

  Link (per consumer, idempotent):
      bin/link-shared.py <consumer> --shared <shared>

      Replaces the consumer's shared files with symlinks pointing into
      <shared>. Per-consumer files (stack.md, coding.md, …) are never
      touched. Refuses to clobber a target whose content differs from
      the shared version (use --force to overwrite local content).

What's shared:
    .claude/config.yaml
    .claude/credentials.yaml
    .claude/context/{product, roadmap, glossary, brand, seo, site-map,
                     company, advisors, funding, compliance}.md
    .claude/agent-memory/<persona>/   (whole dir per persona, all 11)

What stays per-consumer:
    .claude/context/{architecture, stack, coding, security, testing,
                     ui, documentation, release, api}.md
    .claude/agents/, commands/, skills/, mcp/, settings.json,
    settings.local.json   (managed by bin/install.py)
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

# Files at the root of <consumer>/.claude/ that are shared workspace-wide.
ROOT_FILES = [
    "config.yaml",
    "credentials.yaml",
]

# Cross-cutting context files (BA / MM / GM owned). The remaining
# context files (architecture, stack, coding, …) stay per-consumer.
CONTEXT_FILES = [
    "product.md",
    "roadmap.md",
    "glossary.md",
    "brand.md",
    "seo.md",
    "site-map.md",
    "company.md",
    "advisors.md",
    "funding.md",
    "compliance.md",
]

# Every persona's memory is shared so cross-repo lessons carry through
# (UI-Developer's frontend-stack learnings on one consumer help on the
# next, BA's strategic decisions propagate across all consumer repos
# in the same group).
PERSONAS = [
    "general-manager",
    "business-analyst",
    "requirements-engineer",
    "software-architect",
    "security-reviewer",
    "backend-developer",
    "ui-developer",
    "test-manager",
    "technical-writer",
    "release-manager",
    "marketing-manager",
]


def files_differ(a: Path, b: Path) -> bool:
    return not filecmp.cmp(a, b, shallow=False)


def dirs_differ(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return True
    for sub in cmp.common_dirs:
        if dirs_differ(a / sub, b / sub):
            return True
    return False


# ---------------------------------------------------------------------------
# Bootstrap — one-time copy from a canonical consumer into the shared dir.
# ---------------------------------------------------------------------------

def bootstrap(consumer: Path, shared: Path, force: bool, dry_run: bool) -> int:
    consumer_claude = consumer / ".claude"
    if not consumer_claude.is_dir():
        sys.exit(f"ERROR: {consumer_claude} not found — run bin/install.py first")

    if not dry_run:
        shared.mkdir(parents=True, exist_ok=True)
        (shared / "context").mkdir(exist_ok=True)
        (shared / "agent-memory").mkdir(exist_ok=True)

    actions: list[str] = []
    conflicts: list[Path] = []

    def copy_file(src: Path, dst: Path, label: str) -> None:
        if not src.is_file():
            actions.append(f"  skip   {label} (not in consumer)")
            return
        if dst.exists():
            if not files_differ(src, dst):
                actions.append(f"  same   {label}")
                return
            if not force:
                conflicts.append(dst)
                return
        if dry_run:
            actions.append(f"  would copy   {label}")
            return
        shutil.copy2(src, dst)
        actions.append(f"  copied {label}")

    def copy_dir(src: Path, dst: Path, label: str) -> None:
        if not src.is_dir():
            actions.append(f"  skip   {label} (not in consumer)")
            return
        if dst.exists():
            if not dirs_differ(src, dst):
                actions.append(f"  same   {label}")
                return
            if not force:
                conflicts.append(dst)
                return
        if dry_run:
            actions.append(f"  would copy   {label}")
            return
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        actions.append(f"  copied {label}")

    for name in ROOT_FILES:
        copy_file(consumer_claude / name, shared / name, name)

    for name in CONTEXT_FILES:
        copy_file(
            consumer_claude / "context" / name,
            shared / "context" / name,
            f"context/{name}",
        )

    for persona in PERSONAS:
        copy_dir(
            consumer_claude / "agent-memory" / persona,
            shared / "agent-memory" / persona,
            f"agent-memory/{persona}/",
        )

    print(f"Bootstrap {consumer_claude} → {shared}")
    if dry_run:
        print("(dry-run)")
    print()
    for line in actions:
        print(line)

    if conflicts:
        print()
        print(f"ERROR: {len(conflicts)} target(s) in shared differ from consumer:")
        for path in conflicts:
            print(f"  - {path}")
        print()
        print("Pick one:")
        print("  - resolve manually (sync the divergent files), or")
        print("  - re-run with --force to overwrite shared with consumer's copy.")
        return 1

    return 0


# ---------------------------------------------------------------------------
# Link — idempotent, per-consumer.
# ---------------------------------------------------------------------------

def link(consumer: Path, shared: Path, force: bool, dry_run: bool) -> int:
    consumer_claude = consumer / ".claude"
    if not consumer_claude.is_dir():
        sys.exit(f"ERROR: {consumer_claude} not found — run bin/install.py first")
    if not shared.is_dir():
        sys.exit(
            f"ERROR: shared dir {shared} not found — "
            f"run with --bootstrap-from <consumer> first"
        )

    actions: list[str] = []
    conflicts: list[Path] = []
    linked = preserved = 0

    def link_path(src: Path, dst: Path, label: str, is_dir: bool) -> None:
        nonlocal linked, preserved
        if not src.exists():
            actions.append(f"  skip   {label} (not in shared)")
            return
        # Already correctly linked?
        if dst.is_symlink():
            try:
                if dst.resolve() == src.resolve():
                    actions.append(f"  ok     {label}")
                    preserved += 1
                    return
            except (FileNotFoundError, OSError):
                pass  # broken symlink — fall through to re-link
        # Real file/dir — only safe to replace if content matches
        if dst.exists() and not dst.is_symlink():
            if is_dir and dst.is_dir() and src.is_dir() and not dirs_differ(src, dst):
                pass  # identical directory tree → safe to replace
            elif not is_dir and dst.is_file() and src.is_file() and not files_differ(src, dst):
                pass  # identical file → safe to replace
            elif not force:
                conflicts.append(dst)
                return
        if dry_run:
            actions.append(f"  would link   {label}")
            return
        # Remove existing target, then symlink
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        elif dst.is_dir():
            shutil.rmtree(dst)
        dst.symlink_to(src.resolve())
        actions.append(f"  linked {label}")
        linked += 1

    for name in ROOT_FILES:
        link_path(shared / name, consumer_claude / name, name, is_dir=False)

    for name in CONTEXT_FILES:
        link_path(
            shared / "context" / name,
            consumer_claude / "context" / name,
            f"context/{name}",
            is_dir=False,
        )

    for persona in PERSONAS:
        link_path(
            shared / "agent-memory" / persona,
            consumer_claude / "agent-memory" / persona,
            f"agent-memory/{persona}/",
            is_dir=True,
        )

    print(f"Link {consumer_claude} → {shared}")
    if dry_run:
        print("(dry-run)")
    print()
    for line in actions:
        print(line)

    if conflicts:
        print()
        print(f"ERROR: {len(conflicts)} target(s) differ from shared:")
        for path in conflicts:
            print(f"  - {path}")
        print()
        print("Pick one:")
        print("  - sync the divergence (compare & merge, then re-run), or")
        print("  - re-run with --force to clobber the consumer's local copy.")
        return 1

    print()
    print(f"Linked: {linked}, preserved: {preserved}, conflicts: {len(conflicts)}")
    return 0


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Symlink shared parts of a consumer's .claude/ to a shared "
            "context repo. Run --bootstrap-from once to seed the shared "
            "dir; then run with a positional consumer path per repo."
        ),
    )
    parser.add_argument(
        "consumer", nargs="?",
        help="Path to the consumer project. Required for link mode; "
             "ignored when --bootstrap-from is given.",
    )
    parser.add_argument(
        "--shared", required=True,
        help="Path to the shared claude-context/ repo.",
    )
    parser.add_argument(
        "--bootstrap-from", metavar="CONSUMER",
        help="Bootstrap mode: copy shared files from this consumer into "
             "--shared. One-time operation per shared dir.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite divergent content on either side.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would happen, don't touch the filesystem.",
    )
    args = parser.parse_args()

    shared = Path(args.shared).resolve()

    if args.bootstrap_from:
        return bootstrap(
            Path(args.bootstrap_from).resolve(),
            shared,
            args.force,
            args.dry_run,
        )

    if not args.consumer:
        parser.error("consumer path is required (or use --bootstrap-from)")
    return link(
        Path(args.consumer).resolve(),
        shared,
        args.force,
        args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
