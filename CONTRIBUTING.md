# Contributing

Thanks for your interest in Trail. This is an early
public release — issues, PRs, and design feedback are all welcome.

## Bug reports and feature requests

Please open an issue. For bugs, please include:

- Your Plane version (visible under *Workspace Settings → About* or
  in `god-mode`).
- Your Claude Code version (`claude --version`).
- The shortest reproduction you can manage.
- Whether you ran a fresh install via `/trail-install-helper` or
  drove the install manually.

## Development setup

The framework is structured as deliverables under `claude/`
(personas, skills, slash commands, supplementary MCP) and an Ansible
playbook under `ansible/` that provisions a turn-key Plane stack.

The high-level loop:

1. Edit `claude/agents/<name>.md`, `claude/skills/<name>/SKILL.md`,
   `claude/commands/<name>.md`, or `claude/mcp/` source.
2. Re-run `bin/install.py <test-consumer>` to push your changes into
   a sibling test project and re-render the per-persona MCP wiring.
3. Open Claude Code in the consumer (`cd <test-consumer> && claude`)
   and exercise the persona via its slash command.

For the supplementary MCP, the test suite under `claude/mcp/tests/`
includes both unit and integration tests; the integration tests want
a live Plane instance reachable via the env vars documented in
`claude/mcp/README.md`.

## Working conventions

- **Anthropic-native primitives first** — Claude Code subagents,
  Skills per the agentskills.io spec, slash commands, MCP. Bring in
  third-party only when there's a clear win.
- **English for everything UI-facing** — READMEs, agent prompts,
  code identifiers, commit messages. The framework is aimed at an
  international audience.
- **No deployment specifics in committed files** — hostnames, IP
  addresses, real Plane URLs, real tokens, real passwords belong in
  gitignored configs (`ansible/{inventory,host_vars,vault}/`,
  the consumer's `.claude/{config,credentials}.yaml`), never in
  the framework deliverables.
- **Persona prompts are deployment-agnostic** — reference agents by
  username (e.g. `business-analyst`); identity fields (full-name,
  email, token) resolve at install time from the consumer's own
  `config.yaml` + `credentials.yaml`.

## Pull requests

- One conceptual change per PR.
- Update the relevant docs under `doc/` when behaviour changes.
- Persona prompt changes: include a short rationale in the PR
  description. The templates are tightly tuned and small wording
  changes can shift agent behaviour noticeably.
- The maintainer updates `CHANGELOG.md` on release — you don't need
  to edit it in your PR.

## Scope

Some things are explicitly **out of scope** for this framework:

- Drivers for ticket systems other than Plane. JIRA/Confluence are
  ruled out over Atlassian's AI/usage terms; supporting other
  trackers would add a translation layer that shouldn't live in the
  same codebase.
- Auto-triggering agent turns from ticket events. Anthropic's terms
  of service for the Claude Code CLI do not allow a third-party
  harness driving CC beyond user-initiated turns; the human is the
  dispatcher by design.
- Runtime orchestration frameworks (LangGraph, CrewAI, etc.). The
  framework deliberately uses Anthropic-native primitives only.

PRs in those directions will be politely declined.
