# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

This span covers the evolution from the initial **ten-persona,
page-based, per-persona-MCP** design (0.1.0) to the current
**eleven-persona, main-loop, single-MCP** architecture.

### Added

- **General Manager + Marketing Manager personas** (eleven personas
  total). The General Manager runs founder operations — Behörden, Notar,
  Recht, Steuern, Staffing, Förderung, Compliance — on a dedicated `HQ`
  Plane project; the Marketing Manager owns the website (`.org` OSS
  narrative + `.com` enterprise funnel), brand voice, and SEO on a
  dedicated `MKT` Plane project. (`claude/agents/general-manager.md`,
  `claude/agents/marketing-manager.md`, `claude/commands/{gm,mm}.md`,
  avatars, `claude/config.yaml.example`, Ansible persona list)
- **`/quick` lane** — an off-Plane fast lane for small, safe changes
  that skips the full Story spine, each change tagged `Trail-Lane:
  quick`. (`claude/commands/quick.md`)
- **`/autopilot` lane** — an unattended, human-initiated run that drives
  a framed Story (or each sub-Story of a parent work-item) through the
  whole engineering spine to a merged branch, with no human between the
  stages. The parallel implementors each run in an isolated `git
  worktree` off the feature branch; the orchestrator owns all git and,
  on a clean `COMPLETED` run, merges the feature branch into the default
  branch (`--no-ff`) and deletes the branch + worktrees (on `STOP` the
  branch is left intact). **Lean-lane discretion** lets the orchestrator
  right-size the ceremony — skipping RE/SA/SR/TM/TW/RM when they add no
  value and collapsing/swapping the BD/UD implementors when the
  cross-over work is small — each choice logged as a `SKIP-N` decision
  and guarded by hard floors (RE intake, SA decomposition, TM
  runtime-surface, SR security). Personas never touch git.
  (`claude/commands/autopilot.md`,
  `claude/agents/{backend,ui}-developer.md`, `doc/WORKFLOW.md`,
  `claude/config.yaml.example`)
- **Configurable model lanes** — persona/command sources carry
  `__MODEL_STANDARD__` / `__MODEL_FULL__` / `__MODEL_CODEGEN__`
  placeholders resolved at install time from the consumer's
  `config.yaml` (`model_lanes:`), so the lane→model mapping is config,
  not hard-coded. (`claude/config.yaml.example`, `bin/install.py`)

### Changed

- **Plane pinned to Community v1.4.0** (was v1.3.0). Upstream v1.4.0
  closes a large batch of coordinated security advisories — cross-
  workspace IDORs on project/member/estimate/asset endpoints, bot
  service accounts accepting interactive logins, API keys still valid
  for deactivated accounts, unverified OAuth provider emails, and
  unbounded magic-code retries — so self-hosted instances should take
  it. The vendored compose gains the two new upstream knobs
  `WEBHOOK_ALLOWED_IPS` / `WEBHOOK_ALLOWED_HOSTS` (both empty, matching
  upstream's default); no service-level changes. Upgrade path is
  `ansible-playbook backup.yml && ansible-playbook plane.yml --tags
  plane` — Django applies 164 migrations forward, and rolling back to
  v1.3.0 requires a `pg_restore` from the backup, not just a tag flip.
  (`ansible/roles/plane/defaults/main.yml`,
  `ansible/roles/plane/templates/compose.yaml.j2`)
- **`ansible.cfg` stdout callback un-broke.** `stdout_callback = yaml`
  selected `community.general.yaml`, removed in community.general
  12.0.0 — every `ansible-playbook` run aborted before its first task.
  Replaced with the built-in `default` callback plus
  `result_format = yaml`, the supported equivalent. (`ansible/ansible.cfg`)
- **Personas run in the main loop, not as subagents.** Each
  `/<persona>` slash command puts the main Claude Code loop into that
  role for this and any follow-up turns, until USER exits or switches
  persona. Identity separation in Plane is preserved by per-persona API
  tokens routed inside the MCP server by the persona-prefixed tool name.
- **Per-persona Plane MCP servers collapsed into one multi-tenant
  process.** A single `plane` MCP server now holds every persona's token
  and routes calls by the persona-prefixed tool name
  (`business_analyst__list_states`, `release_manager__add_comment`, …),
  replacing the earlier one-server-per-persona wiring.

### Removed

- **The Venture Advisor persona and its `/va` command**, superseded by
  the General Manager (`/gm`). The lightweight strategy sanity-check VA
  used to gate ideas now lives in the Business Analyst's prompt, and the
  `BIZ` track is replaced by the `HQ` (founder-ops) and `MKT`
  (marketing) tracks.
- **Plane pages and the `write-spec-page` skill.** Plane v1.3.0's pages
  sit on an internal Yjs/Tiptap collaborative-editor API that does not
  reliably absorb API-side writes, so the framework no longer uses pages
  — every persona artefact now lives in a work-item *body* (written once
  at creation) or a *comment*. The page-oriented `plane-extras-mcp`
  tools (`create_page`, `list_pages`, `retrieve_page`,
  `update_page_description`, `delete_page`) were dropped accordingly;
  the MCP now covers the comments gap only.

## [0.1.0] — 2026-05-08

> **Historical snapshot, superseded by [Unreleased].** The persona set
> (ten, including a Venture Advisor), the subagent execution model, the
> per-persona MCP topology, and the Plane-pages artefact model described
> below have all since changed. This entry is preserved as the initial
> tagged state; see [Unreleased] for what replaced each piece. (The
> `v0.1.0` tag was never cut as a public release.)

Initial tagged state of the Trail framework: ten
Claude Code subagent personas (Venture Advisor, Business Analyst,
Requirements Engineer, Software Architect, Security Reviewer, Backend
Developer, UI Developer, Test Manager, Technical Writer, Release
Manager) collaborating through a Plane workspace.

### Added

- **Ten persona subagents** (`claude/agents/*.md`) with hard-coded
  context allowlists, per-persona MCP scoping, DoD-checklist handover
  via the `plane-handover` skill, self-quality-gate inline checklists,
  cross-persona quick-lookup, kill criteria after three failed
  iterations, and stop-on-ambiguity HITL gating.
- **Slash-command dispatchers** for every persona (`/va`, `/ba`,
  `/re`, `/sa`, `/sr`, `/bd`, `/ud`, `/tm`, `/tw`, `/rm`) plus
  `/kickoff` for a one-time bootstrap of the consumer's
  `.claude/context/*.md` files from its source.
- **Two shared skills**: `plane-handover` (DoD checklist + state
  transition + assignee change in one shot), `write-spec-page`
  (consistent page-naming convention `<TICKET-ID> — <topic>` with
  the page's `_ui_url` posted as a comment on the ticket).
- **Supplementary MCP** `plane-extras-mcp` (Python + FastMCP) with
  seven tools — `add_comment`, `list_comments`, `create_page`,
  `list_pages`, `retrieve_page`, `update_page_description`,
  `delete_page` — covering the gaps that Plane's official MCP server
  does not expose. Dual auth: public REST (`X-API-Key`) for comments,
  internal app API (session cookie via `/auth/sign-in/`) for pages.
- **Idempotent installer** `bin/install.py` with two stages: copy +
  seed of consumer-owned slots, then per-persona MCP wiring render
  (writes `settings.local.json`, `<consumer>/.mcp.json`, and
  re-templates `<consumer>/.claude/agents/*.md` with inlined Plane
  tokens at mode 0600).
- **Install-helper meta-agent** (`.claude/agents/install-helper.md`)
  dispatched via `/trail-install-helper` — walks the user through three
  install scenarios (greenfield with Ansible / existing Plane without
  agents / existing Plane with agents already provisioned). Persists
  advisory state to `~/.cache/trail-install-helper/` so a mid-install
  re-spawn picks up where the previous left off.
- **Turn-key Ansible playbook** (`ansible/plane.yml`) provisioning
  Plane Community v1.3.0 onto an SSH-reachable host: workspace,
  ten agent accounts (with avatars + notification opt-out), projects,
  phase modules, story labels, ticket states, per-agent API tokens.
  Seven idempotent roles plus a Caddy site-block snippet. Host
  pre-conditions (docker, the `web` external network, apt-installed
  Caddy) are auto-installed when missing on Debian / Ubuntu /
  Raspberry Pi OS.
- **Public docs** under `doc/`: `INSTALLATION.md` (manual reference
  for the install-helper), `PROVISIONING.md` (full Ansible details),
  `PERSONAS.md` (ten agents + handover model), `WORKFLOW.md` (Story
  lifecycle and state spine), `MCP.md` (per-persona scoping +
  page-naming convention), `PLANE_API.md` (Plane API surface notes).

### Known limitations

- Tested only against Plane Community v1.3.0. The page tools depend
  on Plane's internal app API, which may change between releases.
- Per-persona MCP wiring uses inlined tokens because Claude Code's
  `${VAR}` substitution in subagent-frontmatter `env:` is currently
  unreliable upstream
  ([anthropics/claude-code#1254](https://github.com/anthropics/claude-code/issues/1254)).
  Once #1254 lands stably we can switch back to `${VAR}` and drop the
  templating step in `install.py`.
- Subagents do not inherit the main Claude Code session's MCP
  servers from project-level `.mcp.json` in CC 2.1.119; the
  framework works around this via subagent-frontmatter
  `mcpServers:`. The `.mcp.json` is still emitted for `claude mcp
  list` diagnostics.

[0.1.0]: https://github.com/mahmadhuebsch/trail-aiac/releases/tag/v0.1.0
