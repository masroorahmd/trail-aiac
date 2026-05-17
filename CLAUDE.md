# Trail — Claude Code project context

This file is auto-loaded into every Claude Code session in this repo.
It captures the current state of the framework — not its history. For
the journey, the doc/ folder and the git log are authoritative.

## What this repo is

A spec-driven, multi-agent framework for software development with
Claude Code and Plane. Ten named personas (Venture Advisor, Business
Analyst, Requirements Engineer, Software Architect, Security Reviewer,
Backend Developer, UI Developer, Test Manager, Technical Writer,
Release Manager) collaborate through a shared Plane workspace to take
a feature from idea to release. The human user triggers each agent
turn — never the ticket system — and agents hand work off by
reassigning tickets and walking them through a fixed state spine.

The framework is delivered to a *consumer project* via
`bin/install.py`, which copies the persona prompts, skills, slash
commands, and supplementary MCP into `<consumer>/.claude/` and renders
per-persona MCP wiring with inlined Plane credentials. The consumer
keeps its own `.claude/context/`, `.claude/agent-memory/`,
`.claude/config.yaml`, and `.claude/credentials.yaml` — those survive
every re-install.

## Repo layout

```
trail-aiac/
├── CLAUDE.md                      this file
├── README.md                      public face for GitHub
├── claude/                        the framework deliverable bundle.
│   │                              `bin/install.py` copies these into
│   │                              `<consumer>/.claude/` as REAL files.
│   ├── agents/                    10 persona definitions (loaded
│   │                              into the main loop by /<persona>)
│   ├── skills/                    shared skills (plane-handover)
│   ├── commands/                  slash-command dispatchers
│   │                              (/va, /ba, /re, /sa, /sr, /bd,
│   │                              /ud, /tm, /tw, /rm, /kickoff)
│   ├── mcp/                       multi-tenant Plane MCP server
│   │                              (Python + FastMCP). One process,
│   │                              one tool set × N personas, persona
│   │                              prefix on every tool name.
│   ├── workflows/                 canonical persona-paths for recurring
│   │                              kinds of work (greenfield-feature,
│   │                              bug-fix, security-finding). Reading
│   │                              material for the human user, not
│   │                              orchestration.
│   ├── context.example/           13 kickoff stubs that seed the
│   │                              consumer's context/ on first install
│   │                              (incl. control-manifest.md — the
│   │                              project's CM-N guardrails)
│   ├── agent-memory.example/      10 per-persona MEMORY.md stubs that
│   │                              seed the consumer's agent-memory/
│   ├── config.yaml.example        seeds consumer's config.yaml
│   ├── credentials.yaml.example   seeds consumer's credentials.yaml
│   └── settings.json              persona permissions
│                                  (Write/Edit on context/* and
│                                  agent-memory/**)
│
├── ansible/                       Plane provisioning (optional)
│   ├── plane.yml                 turn-key playbook
│   ├── inventory.yml.example     |
│   ├── host_vars/plane.yml.example
│   ├── vault/secrets.example.yml |
│   ├── group_vars/               framework-wide and host-group defaults
│   └── roles/                    plane_secrets, plane, plane_admin,
│                                 plane_users, plane_projects,
│                                 plane_bootstrap, caddy
│
├── bin/install.py                 single-shot installer; idempotent.
│                                  Stage 1: copy + seed. Stage 2 (when
│                                  config + credentials are populated):
│                                  render settings.local.json, .mcp.json
│                                  (one `plane` entry whose env carries
│                                  every persona's PLANE_API_KEY_*),
│                                  and re-template the consumer's
│                                  agents/*.md placeholders (mode 0600).
│
├── doc/                           public docs — see index below
├── avatars/                       10 persona PNGs + generator source
└── .claude/                       Claude Code state for THIS repo's
                                   dev sessions only.
                                   Holds the install-helper agent +
                                   its /trail-install-helper slash command;
                                   NOT a framework deliverable.
```

## Key constraints

- **Language**: English everywhere for *artefacts* — README, doc/,
  agent prompts, code, code comments, commits, Plane work-item bodies
  and comments, and any file under `.claude/context/` or
  `.claude/agent-memory/`. The framework is aimed at an international
  GitHub audience. *Chat language* between USER and a persona is
  configurable per consumer via `chat_language` in
  `<consumer>/.claude/config.yaml` (default: English) — the only
  thing that varies between deployments.
- **Anthropic-native primitives first**: Claude Code subagents, Skills
  per the agentskills.io spec, slash commands, MCP. Third-party
  frameworks only when they add clear value.
- **No deployment specifics in git**: hostnames, IP addresses, real
  Plane URLs, real tokens, real passwords never appear in committed
  files. They live in gitignored `ansible/{inventory,host_vars,vault}/`,
  the consumer's `.claude/{config,credentials}.yaml`, and assistant
  memory.
- **Ticket system is Plane** (cloud or self-hosted). JIRA/Confluence
  ruled out over Atlassian's AI/usage terms. MCP via a single
  multi-tenant server in `claude/mcp/` that holds every persona's
  Plane token and routes calls by tool-name prefix
  (`business_analyst__list_states`, `release_manager__add_comment`, …).
- **No Plane pages.** Every persona artefact lives either in a
  work-item *body* (written once at creation) or in a *comment*.
  Plane v1.3.0's pages sit on the internal app API behind a
  Yjs/Tiptap collaborative editor that does not reliably absorb
  API-side updates, which made earlier page-based designs fragile.
- **Description-once.** A work-item body is written when the
  work-item is created and never edited afterwards. Later
  annotations and handovers travel as comments.
- **User-triggered, not ticket-triggered**. Anthropic's terms of
  service for the Claude Code CLI do not allow a third-party harness
  driving CC beyond user-initiated turns. So Plane's `assignee` field
  is the user's TODO list, not an auto-trigger; every persona turn is
  a slash command the human issues.
- **Personas run in the main loop, not as subagents.** Each
  `/<persona>` slash command puts the main loop into the persona's
  role for this and any follow-up turns, until USER says "done" /
  "exit" or starts a different `/<persona>`. Identity separation in
  Plane is preserved by per-persona API tokens — all collected in the
  single `plane` MCP server's env block in `.mcp.json` — and routed
  inside the server by the persona-prefixed tool name. The persona's
  prompt explicitly constrains it to only its own
  `plane__<persona_snake>__*` tools.

## Where to find the details

| Topic | File |
|---|---|
| Install procedure (three scenarios, what install.py does) | [`doc/INSTALLATION.md`](doc/INSTALLATION.md) |
| Plane provisioning via Ansible (host pre-conditions, TLS, idempotency, secret rotation, tear-down) | [`doc/PROVISIONING.md`](doc/PROVISIONING.md) |
| The ten personas — what each one reads, writes, and when to invoke | [`doc/PERSONAS.md`](doc/PERSONAS.md) |
| Story lifecycle, state spine, handover protocol over Plane tickets | [`doc/WORKFLOW.md`](doc/WORKFLOW.md) |
| MCP scoping, the multi-tenant `plane` server design, tool-name prefix convention | [`doc/MCP.md`](doc/MCP.md) |
| Plane public + internal API surface | [`doc/PLANE_API.md`](doc/PLANE_API.md) |
| Comparison vs. BMAD-METHOD (collaboration bus, identity, ID convention, what we did and didn't borrow) | [`doc/COMPARISON.md`](doc/COMPARISON.md) |

## Working conventions for Claude Code sessions in this repo

- **The framework's `claude/` is the deliverable bundle, NOT live
  subagents for THIS repo.** Running `claude` here gets a clean dev
  session, not the ten-persona team. The personas only become live
  subagents in a *consumer* project after `bin/install.py`.
- **Don't dogfood the framework into this repo's `.claude/`.** The only
  agent that lives in `.claude/agents/` here is `install-helper` — a
  meta-agent that walks an end-user through installing the framework
  into a consumer project, dispatched via `/trail-install-helper`.
- **Keep persona prompts deployment-agnostic.** Reference agents by
  username (e.g. `business-analyst`); identity fields (full-name,
  email, token) are resolved at runtime from the consumer's
  `config.yaml` + `credentials.yaml` via `bin/install.py`'s render.
- **Don't commit homelab or deployment specifics.** If homelab context
  is needed during development, it lives in the user's local
  gitignored configs or in private assistant memory — never in
  committed files.
- **Edit `claude/agents/*.md` and `claude/commands/*.md` for framework
  changes**, not the rendered copies under any consumer's `.claude/`.
  The consumer's copies are regenerated by `install.py`.
