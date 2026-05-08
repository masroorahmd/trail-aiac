---
name: plane-id-cache
description: Resolve Plane project / state / label / assignee / module UUIDs from a local cache file (`.claude/cache/plane-ids.yaml`) instead of round-tripping through MCP listing tools every turn. Read the cache before any `list_projects` / `list_states` / `list_labels` / `list_workspace_members` MCP call — these UUIDs are stable per deployment. Refresh by running the bundled `refresh.py` script when a needed name is missing.
---

# plane-id-cache

Plane's UUIDs for projects, workflow states, labels, workspace members,
and modules are **stable per deployment**: they are written once when
the workspace is provisioned and almost never change. Fetching them
from MCP every persona turn is a round-trip tax.

This skill caches them in `.claude/cache/plane-ids.yaml` and tells
every persona to consult that file *before* calling any Plane MCP
listing tool.

## What gets cached

```yaml
generated_at: 2026-05-01T15:42:33+00:00
plane:
  base_url: https://plane.example.com
  workspace:
    slug: example
    id: <uuid>
  projects:
    DEV:
      id: <uuid>
      name: Development
      states:
        Backlog:    <uuid>
        Todo:       <uuid>
        "In Progress": <uuid>
        "In Review": <uuid>
        Done:       <uuid>
        Cancelled:  <uuid>
      labels:
        Security:    <uuid>
        Foundation:  <uuid>
        # … one entry per label that exists in the project
      modules:
        backend:       <uuid>
        frontend:      <uuid>
        testing:       <uuid>
        documentation: <uuid>
    BIZ:
      id: <uuid>
      # … same shape
  members:
    by-persona:
      business-analyst:      <uuid>
      requirements-engineer: <uuid>
      # … by deriving "<persona-name>@<config:plane.email-domain>"
    by-email:
      business-analyst@example.com:  <uuid>
      # … every workspace member with email + UUID
```

## When to read it (every persona, every turn)

Whenever a persona needs to set or filter on `state`, `assignee`,
`labels`, `parent_project`, or `module` in a Plane MCP call:

1. Read `.claude/cache/plane-ids.yaml`.
2. Look up the human name (e.g. `Backlog`, `Security`,
   `requirements-engineer`) under the matching section.
3. Use the resolved UUID directly in the MCP call. Do **not** call
   `list_states` / `list_labels` / `list_workspace_members` /
   `list_projects` first.

If the file is missing, or the human name you need is not in it, fall
back to refreshing the cache (next section). Never silently substitute
a mistyped name with an MCP listing call — refresh, then retry.

## When to refresh

Refresh whenever:

- The cache file does not exist (first run after install).
- A name you need is missing from the cache.
- The user announces a new label / state / member was added in the
  Plane UI.
- An MCP write fails with a "no such state / label / member" error.

Refresh command:

```bash
uv run --no-project --with httpx --with pyyaml \
  python3 .claude/skills/plane-id-cache/refresh.py
```

The script reads `.claude/config.yaml` (workspace, projects) and
`.claude/credentials.yaml` (any persona's PAT — read-only resolver
work, no attribution concern). It queries the public REST API for
projects, states, labels, modules, and workspace members, then
overwrites `.claude/cache/plane-ids.yaml`.

Refresh is idempotent and cheap (≈10 HTTP calls). Re-run as often as
useful.

## Output of `refresh.py`

The script prints a one-line summary on success:

```
plane-ids: 2 projects, 12 labels (DEV), 6 states (DEV), 10 members → .claude/cache/plane-ids.yaml
```

Non-zero exit on failure with a single line naming the missing config
or the failing endpoint. Surface that line to USER; do not retry
blindly.

## Stopping conditions

- **Cache missing AND refresh fails**: stop and report to USER. The
  persona cannot do attributed Plane writes without the IDs; let
  USER fix the upstream issue (creds, network, Plane reachable)
  before continuing.
- **Name still missing after a fresh refresh**: the entity does not
  exist in Plane yet (e.g. a label that USER intends to create but
  hasn't). Stop and ask USER whether to create it (which is USER's
  call — personas do not add labels / states / members on their own).

## What this skill does NOT do

- It does not write to Plane. The cache is read-only context; the
  refresh script only **reads** from Plane's public REST.
- It does not invalidate itself on a schedule. UUIDs are stable;
  staleness only matters when a name is added / removed in Plane.
  Refresh is event-driven, not periodic.
- It does not handle pages. Pages live behind the internal app API
  with session-cookie auth — see `plane-page-read` for that lane.
- It does not cache work-item IDs (DEV-N → UUID). Work-items churn
  too fast for a static cache to be useful; resolve those via the
  MCP `retrieve_work_item_by_identifier` tool as they come up.

## Where the cache file lives in git

`.claude/cache/plane-ids.yaml` is per-deployment and not meaningful
to track in git. Add `.claude/cache/` to the consumer's `.gitignore`
on first refresh; the script will print a hint if it detects the
path is currently tracked.
