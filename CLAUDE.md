# Trail — Claude Code project context

This file is auto-loaded into every Claude Code session in this repo.
It captures the current state of the framework — not its history. For
the journey, the doc/ folder and the git log are authoritative.

## What this repo is

A spec-driven, multi-agent framework for software development with
Claude Code and Plane. Eleven named personas (General Manager, Business
Analyst, Requirements Engineer, Software Architect, Security Reviewer,
Backend Developer, UI Developer, Test Manager, Technical Writer,
Release Manager, Marketing Manager) collaborate through a shared Plane
workspace to take a feature from idea to release.

> **Branch note (masroor).** Public `main` ships a `venture-advisor`
> persona on a `BIZ` track. This branch retires VA in favour of a
> `general-manager` scoped to founder operations (Behörden, Notar,
> Recht, Steuern, Staffing, Förderung, Compliance) on a separate
> `HQ` Plane project, and adds a `marketing-manager` for the
> website (`.org` OSS narrative + `.com` enterprise sales funnel),
> brand voice, and SEO on a separate `MKT` Plane project. The
> lightweight strategy sanity-check VA used to gate ideas now lives
> in BA, which also owns `roadmap.md`. The human user triggers each agent
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
│   ├── agents/                    11 persona definitions (loaded
│   │                              into the main loop by /<persona>)
│   ├── skills/                    shared skills (ui-mockup — the
│   │                              /mock design-session contract:
│   │                              where the mock lives, its fidelity,
│   │                              the D-N decision record, and how
│   │                              BA/RE/SA/UD each read it;
│   │                              plane-handover —
│   │                              also the single home of the
│   │                              §Right-sizing rule that bounds how
│   │                              big any persona's artefact gets;
│   │                              plane-id-cache, browser-review —
│   │                              the last one carries the browser
│   │                              driver ladder + evidence discipline
│   │                              TM's review run and UD's visual gate
│   │                              both follow)
│   ├── commands/                  slash-command dispatchers
│   │                              (/gm, /ba, /re, /sa, /sr, /bd,
│   │                              /ud, /tm, /tw, /rm, /mm, /kickoff,
│   │                              /mock — pre-ticket UI design lane
│   │                              (UD builds clickable HTML mocks in
│   │                              the project's CSS; output is
│   │                              design/<slug>/ in the project repo,
│   │                              never Plane),
│   │                              /quick — off-Plane quick lane,
│   │                              /autopilot — unattended full-spine lane)
│   ├── output-styles/             system-prompt styles for the main
│   │                              loop. `plain.md` (shipped as the
│   │                              default via settings.json's
│   │                              `outputStyle`) bounds *prose volume
│   │                              and reading level* — the axis
│   │                              plane-handover's §Right-sizing does
│   │                              NOT cover, since that one bounds how
│   │                              many elements an artefact has, not
│   │                              how many words each one gets.
│   │                              Templated like agents/ and commands/
│   │                              (`__CHAT_LANGUAGE__`). Applies to
│   │                              every persona at once — so it may
│   │                              only set voice, never role or stage.
│   ├── partials/                  shared prompt text with ONE source.
│   │                              `bin/install.py` stitches a partial
│   │                              into every persona/command file that
│   │                              carries
│   │                              `<!-- TRAIL:INCLUDE <name> -->`,
│   │                              before `__VAR__` substitution. NOT a
│   │                              deliverable — nothing is copied into
│   │                              the consumer; it only sees the
│   │                              expanded text. This is the *ambient*
│   │                              surface: a rule in force every turn
│   │                              with nothing to invoke. Tenants:
│   │                              `reading` (thresholds
│   │                              from config's `reading:`),
│   │                              `git-history` (the work-item ID
│   │                              opens every commit subject, and
│   │                              integration is a rebase — never a
│   │                              merge commit), and
│   │                              `shared-context` (a write through a
│   │                              `link-shared.py` symlink lands in the
│   │                              sibling `claude-context` repo, and is
│   │                              not finished until committed and
│   │                              pushed *there* — the orchestrator does
│   │                              it under `/autopilot`).
│   │                              Cross-persona Plane mechanics still
│   │                              belong in `plane-handover`, voice and
│   │                              volume in `plain.md`.
│   ├── hooks/                     enforcement. Where a rule is
│   │                              mechanically checkable, a hook holds it
│   │                              instead of a prompt paragraph asking a
│   │                              persona to remember — the rule binds
│   │                              harder AND the prompt gets smaller,
│   │                              which is the one move that runs against
│   │                              the ratchet. Wired in `settings.json`,
│   │                              not auto-discovered — but every KNOB is
│   │                              read from `config.yaml` at run time, not
│   │                              baked into `settings.json`, because that
│   │                              file is a copied deliverable and a
│   │                              consumer's preference there would not
│   │                              survive the next install. Tenants:
│   │                              `persona-pin.py` (UserPromptSubmit) records
│   │                              which `/<persona>` USER started (one pin file
│   │                              per session, so parallel sessions each keep
│   │                              their own), derived from
│   │                              the agents/*.md file that command loads, so a
│   │                              twelfth persona needs no hook change; it also
│   │                              retitles the session after that persona — the
│   │                              username spelled out, or a lane's own word
│   │                              (`autopilot`) — through the `sessionTitle` a
│   │                              UserPromptSubmit hook may return, so two terminals
│   │                              in one repo are told apart in `/resume` and in the
│   │                              tab bar, not only in a pin file nobody reads;
│   │                              `hooks.session_title: off` leaves the harness's own
│   │                              titles alone;
│   │                              `plane-persona-guard.py`
│   │                              (PreToolUse/`mcp__plane__*`) denies a Plane
│   │                              call whose `persona` argument disagrees, at
│   │                              the strength `hooks.persona_identity` asks
│   │                              for (`strict` / `ask` / `off`). Those two are
│   │                              what replaced the persona tool-name prefix,
│   │                              which only ever looked like a guarantee. Both
│   │                              fail open on every uncertain case, because a
│   │                              false deny costs more than a missed check.
│   │                              `fork-guard.py` (PreToolUse/`Agent`|`Task`)
│   │                              covers the hole the identity guard cannot
│   │                              see: a `fork` inherits the caller's whole
│   │                              context, so one spawned in a persona run
│   │                              holds the Plane tools AND that persona's
│   │                              token, and every duplicate write it makes is
│   │                              correctly attributed to the wrong author's
│   │                              intent. Fires only on `subagent_type: fork`
│   │                              (a NAMED persona subagent is sanctioned and
│   │                              starts cold), at the strength
│   │                              `hooks.fork_in_persona_run` asks for
│   │                              (`deny` / `ask` / `off`), and deliberately
│   │                              does NOT pass the `*` pin — unattended is
│   │                              when a fork is worst.
│   │                              `commit-msg-guard.py` (PreToolUse/Bash)
│   │                              holds the commit-subject rule at the
│   │                              strength `hooks.commit_id_required` asks
│   │                              for: `plane-only` (default) denies only
│   │                              an ID buried in the body or a trailer,
│   │                              `strict` demands one on every commit,
│   │                              `off` disables it. Dependency-free
│   │                              because it runs on Bash calls; fails open
│   │                              with no config; yields to
│   │                              `TRAIL_SKIP_COMMIT_GUARD=1` for the
│   │                              commit that genuinely has no work item
│   │                              (the partial forbids inventing one).
│   │                              `linear-history-guard.py`
│   │                              (PreToolUse/Bash) is the same partial's
│   │                              other half: it denies a `git merge` that
│   │                              would write a merge commit, a bare
│   │                              `git pull` (unless the repo's own
│   │                              `pull.rebase` already rebases), and a
│   │                              `push --force` that is not
│   │                              `--force-with-lease` — at the strength
│   │                              `hooks.linear_history` asks for
│   │                              (`deny` / `ask` / `off`), yielding to
│   │                              `TRAIL_SKIP_MERGE_GUARD=1`.
│   │                              `merge --ff-only` and `--squash` pass:
│   │                              the rule is against the merge *commit*,
│   │                              not against landing a branch.
│   ├── mcp/                       multi-tenant Plane MCP server
│   │                              (Python + FastMCP). One process, ONE
│   │                              tool set for all N personas: identity
│   │                              travels in a `persona` argument, not in
│   │                              the tool name. A prefix per persona
│   │                              meant 286 tool schemas (~45k tokens) in
│   │                              every session's system prompt to serve
│   │                              the 26 one persona holds; the argument
│   │                              costs ~5.9k, and the identity is now
│   │                              actually checked (see hooks/). Listing
│   │                              tools project and shorten what they
│   │                              return, because a persona picks up with
│   │                              a FRESH context and pays the read every
│   │                              turn: `list_work_items` drops bodies,
│   │                              `list_comments` converts Plane's HTML to
│   │                              text and cuts a long comment to its head
│   │                              (thresholds from config's `reading:`).
│   │                              Both have a `retrieve_*` counterpart for
│   │                              the one item the caller actually needs —
│   │                              which is what a pickup step names anyway.
│   ├── workflows/                 canonical persona-paths for recurring
│   │                              kinds of work (greenfield-feature,
│   │                              bug-fix, security-finding). Reading
│   │                              material for the human user, not
│   │                              orchestration.
│   ├── context.example/           kickoff stubs that seed the
│   │                              consumer's context/ on first install
│   │                              (incl. control-manifest.md — the
│   │                              project's CM-N guardrails)
│   ├── agent-memory.example/      11 per-persona MEMORY.md stubs that
│   │                              seed the consumer's agent-memory/
│   ├── config.yaml.example        seeds consumer's config.yaml
│   ├── credentials.yaml.example   seeds consumer's credentials.yaml
│   └── settings.json              persona permissions
│                                  (Edit on context/* and
│                                  agent-memory/**; `Edit(path)` rules
│                                  cover every file-editing tool —
│                                  `Write(path)` rules are NOT matched
│                                  by file permission checks and make
│                                  Claude Code warn at startup).
│                                  Also carries
│                                  `enabledMcpjsonServers: ["plane"]`
│                                  — without it the project-scoped
│                                  `.mcp.json` server is gated behind a
│                                  startup prompt that is asked EVERY
│                                  start, and one dismissed prompt
│                                  leaves the whole session with no
│                                  Plane tools and nothing in `/mcp`
│                                  to reconnect.
│                                  `outputStyle: "Plain"` selects the
│                                  shipped style; a consumer overrides
│                                  it via `/config`, which writes to
│                                  settings.local.json and wins over
│                                  this file — so install.py never
│                                  stomps that choice.
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
├── bin/link-shared.py             multi-consumer linker. For setups
│                                  where one company has several consumer
│                                  repos sharing one Plane workspace and
│                                  cross-cutting product narrative.
│                                  Replaces a consumer's shared .claude/
│                                  files (config.yaml, credentials.yaml,
│                                  cross-cutting context/*.md, every
│                                  persona's agent-memory/) with symlinks
│                                  into a designated claude-context/ dir.
│                                  Per-consumer files (stack.md, coding.md,
│                                  agents/, .mcp.json, …) are never
│                                  touched. Bootstrap once from a canonical
│                                  consumer, then link N consumers
│                                  idempotently.
│
├── doc/                           public docs — see index below
├── avatars/                       11 persona PNGs + generator source
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
  Plane token and routes each call by the `persona` argument every
  tool takes.
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
  inside the server by the `persona` argument every tool takes. The
  persona's prompt says which value to pass;
  `hooks/plane-persona-guard.py` is what checks it against the
  `/<persona>` USER actually started.

## Where to find the details

| Topic | File |
|---|---|
| Install procedure (three scenarios, what install.py does) | [`doc/INSTALLATION.md`](doc/INSTALLATION.md) |
| Plane provisioning via Ansible (host pre-conditions, TLS, idempotency, secret rotation, tear-down) | [`doc/PROVISIONING.md`](doc/PROVISIONING.md) |
| The eleven personas — what each one reads, writes, and when to invoke | [`doc/PERSONAS.md`](doc/PERSONAS.md) |
| Story lifecycle, state spine, handover protocol over Plane tickets | [`doc/WORKFLOW.md`](doc/WORKFLOW.md) |
| MCP scoping, the multi-tenant `plane` server design, `persona`-argument routing + the identity guard | [`doc/MCP.md`](doc/MCP.md) |
| Plane public + internal API surface | [`doc/PLANE_API.md`](doc/PLANE_API.md) |
| Comparison vs. BMAD-METHOD (collaboration bus, identity, ID convention, what we did and didn't borrow) | [`doc/COMPARISON.md`](doc/COMPARISON.md) |

## Working conventions for Claude Code sessions in this repo

- **The framework's `claude/` is the deliverable bundle, NOT live
  subagents for THIS repo.** Running `claude` here gets a clean dev
  session, not the eleven-persona team. The personas only become live
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
- **Model IDs are config, not hard-coded.** Persona/command sources
  carry `__MODEL_STANDARD__` / `__MODEL_FULL__` / `__MODEL_CODEGEN__`
  placeholders; the lane → model mapping lives in the consumer's
  `config.yaml` (`model_lanes:`, defaults in `config.yaml.example` and
  `bin/install.py`). When a new model ships, bump the lane in config
  and re-run `install.py` — never write a concrete model ID into
  `claude/agents/*.md` or `claude/commands/*.md`. Tier policy:
  [`doc/PERSONAS.md`](doc/PERSONAS.md) → Model lanes.
- **A new persona rule pays for itself, or names what it replaces.**
  The prompts grow by ratchet: every incident adds a rule, almost
  nothing ever removes one, and a persona that reads as a compliance
  checklist starts behaving like a compliance clerk — which is how a
  comment cleanup ends up costing eight handovers. So when a change
  adds a rule to `claude/agents/*.md` or `claude/commands/*.md`, the
  commit message says one of two things: **which rule it replaces or
  narrows**, or **why the prompt is genuinely bigger than the problem
  it now covers**. Neither is a veto — it is the sentence that makes
  the growth deliberate.
  - Prefer stating a rule **once in a shared skill** over restating it
    in N personas. `plane-handover` is where cross-persona mechanics
    belong; a persona then carries a one-line pointer, not a copy.
    When a rule must be *ambient* — in force every turn, with nothing
    to invoke — it goes in `claude/partials/` and is included by
    marker. That surface is deliberately narrow: it costs tokens in
    every file it lands in, on every turn.
  - **One check, one home** (canonical: `plane-handover` → *DoD
    hygiene*). The posted DoD holds what the receiver can verify from
    the ticket; the Self-Quality Gate holds what only the author can
    attest. An item in both lists is one check and one copy of it.
  - Periodically run a **deletion pass** rather than only additions:
    duplicated checklist items, rules superseded by a later rule, and
    prose that restates a constraint already stated above it.
- **Multi-consumer setups (one company → several repos)** use
  `bin/link-shared.py` to symlink cross-cutting `.claude/` slots
  (config, credentials, product/roadmap/glossary/brand/seo/site-map/
  company/advisors/funding/compliance + every persona's agent-memory)
  to a shared `claude-context/` repo. Per-consumer slots (stack,
  coding, ui, security, testing, documentation, release, api,
  architecture; agents/; .mcp.json) stay local and are managed by
  `install.py` as before. Symlinks survive `install.py` re-runs
  because Stage 1 preserves any `.claude/`-slot whose target already
  exists (`seed_if_absent`).
