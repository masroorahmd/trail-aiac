# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-08

Initial public release of the Trail framework: ten
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
