# How Trail compares to BMAD-METHOD

**TL;DR.** [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD)
("Breakthrough Method for Agile AI-Driven Development") and this
framework are philosophically close cousins — both partition AI
agents by SDLC role and run them under explicit human direction —
but they make a different load-bearing bet about **where the
collaboration bus lives**. BMAD's bus is **Git + IDE files**;
ours is **Plane**. That choice cascades into every other
difference. Pick the one whose bet matches yours.

This doc is intentionally written from our side; it tries to be
fair, not neutral. If you spot a misrepresentation, file an issue
and we'll correct it.

---

## What BMAD is, in five minutes

BMAD is an open-source framework that organises ~12–21 specialized
AI agents (Analyst, PM, Architect, Scrum Master, PO, Developer,
QA, UX, and more) around a structured SDLC workflow. Agents are
loaded into an AI-IDE (Claude Code, Cursor, others) via a single
`npx bmad-method install` command. Each agent's prompt is a
markdown file; their artefacts (PRD, architecture, stories) are
markdown files versioned in Git. The human user invokes agents
in conversation, typically inside the IDE.

V6 (current) introduces **Skills Architecture** (Anthropic-skills
aligned), **Sub Agent inclusion** (Claude-Code subagents), TOML
customization, persona consolidation into a `Developer (Amelia)`
agent for context efficiency, and a **PluginResolver** for custom
modules. The framework also ships an **Edge Case Hunter**, a
parallel review primitive, and a **Control Manifest** — a markdown
the human commits before generation begins to set explicit
guardrails.

The community is large and active: many forks, dozens of
practitioner write-ups, ~21 agents in the canonical bundle, 50+
documented workflows, and a steady release cadence.

If you want a feel for it before reading on, scan
[`docs.bmad-method.org`](https://docs.bmad-method.org/) and
[`github.com/bmad-code-org/BMAD-METHOD`](https://github.com/bmad-code-org/BMAD-METHOD).

---

## Side-by-side

| Axis | BMAD-METHOD | Trail |
|---|---|---|
| **Collaboration bus** | Git + filesystem (markdown artefacts) | Plane work-items + comments |
| **Audit trail** | `git log` + per-file history | Plane comment stream + per-persona attribution |
| **State machine** | Implicit in workflow files | Explicit: `Backlog → To Do → In Progress → In Review → Done` per work-item |
| **Persona count** | ~12–21 (V6 trends toward consolidation) | 11 (BA / RE / SA / SR / BD / UD / TM / TW / RM / GM / MM) |
| **Persona identity in the bus** | All agents post into the same author identity | Per-persona Plane account + API token; every comment / state change attributed |
| **Artefact rule** | Versioned, revisable | Description-once: body written on creation, never edited; later annotations as comments |
| **Story → AC → test linkage** | Story files in `stories/`; per-AC IDs not standard | Stable `SC-N` (BA) → `AC-N`/`UF-N`/`EC-N`/`NFR-N` (RE) → cited in test code |
| **Cross-cutting guardrails** | "Control Manifest" (committed before generation) | `control-manifest.md` with `CM-N` IDs, read by BA / SR per Story |
| **Skills / Subagents** | V6 (recent) | Built-in from the start |
| **User-in-loop strictness** | Chat-driven, with phases described as "agentic implementation" | **Strict**: every turn is a `/<persona>` slash command — Anthropic-CLI ToS compliance |
| **Setup** | `npx bmad-method install` (Node.js + Python + uv) | `bin/install.py` + optional Ansible (Plane provisioning, TLS, accounts) |
| **External infra needed** | None | Plane instance (cloud or self-hosted) |
| **Workflows library** | 50+ codified workflows in v6 | 3 starter templates in `claude/workflows/` (greenfield, bug-fix, security-finding) |
| **Edge-case primitive** | Edge Case Hunter (parallel review layer) | `edge-case-hunter` subagent — spawned by RE / TM via `Agent` tool, eight-axis enumeration |
| **Chat language** | English-first | Configurable per consumer (`chat_language` in `config.yaml`); artefacts stay English |
| **Maturity** | Large active community, many forks, steady releases | Small, opinionated, handful of consumers |
| **License** | MIT | MIT |

---

## Where they converge

Both frameworks treat the LLM as a **team of specialists, not a
single generalist**. Both rely on Anthropic-native primitives:
Claude Code subagents, Skills (per `agentskills.io`), slash
commands, MCP. Both keep the human firmly in the loop — every turn
is human-initiated, no ticket-triggered autopilot. Both are
opinionated about role separation and resist "just one big agent
that does everything".

This convergence is real and recent — BMAD's V6 added Skills and
Sub Agents, which we've been using since the beginning. The
philosophical gap on **agent mechanics** has narrowed over the
last six months. The gap on **collaboration topology** has not.

---

## Where they diverge (and why)

### The bus: Git+IDE vs. Plane

BMAD's bet: the developer's IDE is the cockpit. PRDs, architecture
notes, stories, and AC live as files in the repo. Audit trail = git
log. Hand-offs happen by editing the next phase's file. This makes
onboarding cheap (`npx` and you're running) and keeps everything in
the developer's local environment.

Our bet: a **ticket system is a better bus** for multi-day,
multi-persona work involving non-engineering stakeholders. Plane
gives us a real workflow column ("Backlog / To Do / In Progress /
In Review / Done"), per-persona accounts (every action is
attributed visually), labels and modules for product-area
classification, and a UI that PMs and reviewers already know how
to read. We pay for it with a setup tax (provisioning a Plane
instance, minting per-persona API tokens, writing an Ansible
playbook to make that idempotent) — but the operational benefit of
"open the board, see exactly who owns what right now" is large in
practice.

If your team is one or two engineers and the work is mostly
short-cycle, BMAD's lighter setup wins. If you have multiple
stakeholders, multi-week Stories, or a need for the workflow to
be visible to non-engineers, the Plane bus carries its weight.

### Description-once vs. revisable

BMAD versions PRDs and stories as files; you can iterate on them
via `git diff`. Useful: the history is plain to read.

We deliberately forbid body edits. A Story body is written once
on creation and frozen. Later annotation flows through comments.
Reasoning:

- **No "which version is current?" doubt.** Downstream agents
  read the body and know it won't move under them mid-Story.
- **Re-frames are explicit events.** When BA needs to amend, they
  post a comment, never silently edit. The full history is
  always visible at the top of the work-item without diffing.
- **Plane's Yjs editor isn't friendly to API edits.** Even if we
  wanted to allow body edits, the collaborative-editor backend
  makes them unreliable.

Cost: re-frames are clunkier than `git mv old-prd.md new-prd.md`.
We accept that.

### Stable per-AC IDs

We just shipped (May 2026) a stable ID convention: BA's success
criteria carry `SC-N`, RE's Gherkin scenarios carry `AC-N`, edge
cases `EC-N`, non-functional requirements `NFR-N`, user flows
`UF-N`, and global guardrails `CM-N` (in `control-manifest.md`).
IDs are append-only and travel into test code as comments
(`# AC-3 + EC-2 — rejects empty body`).

BMAD has versioned story files but no equivalent stable
per-criterion ID — at least not as a documented convention. Tests
in BMAD-driven projects typically reference stories by file path
or feature name; granular AC traceability requires a project-local
convention.

If you're building cross-repo paired-merges (e.g. a backend repo
and a separate UI-tests repo where the JS validator must mirror
the Python one), stable IDs become load-bearing — you can pin a
specific AC across both repos without ambiguity. We learned this
the hard way; that's why we shipped the convention.

### Identity per persona

In BMAD, the agent persona is a prompt frame; the bus author of
every artefact is the human user (or whatever account commits to
git). We push identity all the way down: every persona has its own
Plane account with its own API token, and the `mcpServers:`
frontmatter in each agent prompt restricts that agent to
`plane-<persona>__*` and `plane-extras-<persona>__*` MCP tools.

Practical consequence: open the Plane board, look at a comment
chain, and you can tell at a glance whether SA decomposed the
Story or BA tried to skip RE. Without per-persona identity, every
comment looks the same — you have to read the prompt frame to
know who "spoke".

The cost: install.py has to render per-persona MCP wiring with
inlined tokens at install time. Subagents do not inherit
`.mcp.json` from the main session, so the only path to per-persona
MCP attribution for subagents is the `mcpServers:` frontmatter
field with hard-coded tokens. We do that templating; BMAD doesn't
need to because it doesn't make the bet.

### User-in-loop strictness

BMAD's vocabulary includes "agentic implementation" as a phase.
We don't allow that as a phrase. Anthropic's terms of service for
the Claude Code CLI (the harness we run inside) do not allow a
third-party harness driving CC beyond user-initiated turns. So
every persona turn is `/<persona>` issued by a human, the
ticket's `assignee` is a human's TODO list (not an auto-trigger),
and personas always end a turn by handing back to USER (no
auto-finalization).

This is a constraint we *chose to take seriously* rather than a
limitation we wish away — the result is a framework that's clean
to use inside Claude Code without licensing risk. BMAD users on
Cursor / other IDEs may not have the same constraint.

---

## What we plan to take from BMAD (and just shipped)

The first BMAD survey already produced three concrete additions
to our framework, dated 2026-05-07:

1. **`control-manifest.md`** — global non-negotiable guardrails
   with stable `CM-N` IDs, read by BA / SR per Story. Cited in
   Story bodies and AC comments where relevant. Mirrors BMAD's
   "Control Manifest" pattern, adapted to our `SC-N` / `AC-N` ID
   discipline. See [`claude/context.example/control-manifest.md`](../claude/context.example/control-manifest.md).

2. **`claude/workflows/`** — canonical persona-paths for
   recurring kinds of work. Three starter templates
   (`greenfield-feature`, `bug-fix`, `security-finding`); more
   to come as patterns settle. Mirrors BMAD's 50+ workflow library
   at a smaller, more opinionated scale. See
   [`claude/workflows/README.md`](../claude/workflows/README.md).

3. **`edge-case-hunter`** — one-shot subagent spawned by RE
   (before drafting AC) or TM (before writing tests). Walks eight
   axes (input boundaries, encoding / locale, cardinality,
   concurrency, error / timeout / partial failure, state
   transitions, hostile inputs, observability holes) and returns
   a structured trigger list. Mirrors BMAD's Edge Case Hunter
   primitive at the subagent layer. See
   [`claude/agents/edge-case-hunter.md`](../claude/agents/edge-case-hunter.md).

---

## What we won't take

- **Persona consolidation into a single Developer agent.** BMAD V6
  is consolidating Persona prompts into `Developer (Amelia)` for
  context efficiency. We deliberately keep our 11 personas
  separated — the separation is load-bearing for **per-persona
  Plane identity**, which we'd lose if a single agent posted
  under all roles. Token-efficiency is real (~2% of context per
  persona) but cheaper than giving up the bus's most useful
  property.

- **Git as the primary bus.** That's BMAD's whole bet. Adopting it
  would mean abandoning ours. Wrong direction.

- **`npx`-style install.** Operationally tempting (their setup is
  much smoother than ours), but our install is more involved
  *because* it has to mint Plane credentials and wire per-persona
  MCP tokens. Streamlining `install.py` is on the list, but
  reducing it to a single `npx`-equivalent would require giving
  up the Plane bus.

---

## When BMAD is the better choice

- Solo or small team, mostly engineers, no PM or non-engineering
  stakeholder needing visibility into the workflow.
- The work is short-cycle (hours to a couple of days per Story).
  Multi-week Stories where the workflow column visibly slows down
  the team are not the load case BMAD optimises for.
- You don't want to provision and run an external service.
  Self-hosting or paying for Plane is a non-starter.
- You're working in a non-Claude-Code IDE (Cursor, others). BMAD
  is multi-IDE; we're Claude-Code-shaped because of the ToS
  constraint above.

## When Trail is the better choice

- Multiple stakeholders need to see the workflow without reading
  git log — PMs, security reviewers, release managers, audit
  trail consumers.
- Work is multi-week or has clear hand-offs between specialists
  who pick up tickets at different times. The state column and
  per-persona assignee chip carry their weight.
- You want per-persona identity in the audit trail (compliance,
  trust posture, post-mortem readability). "Who said this and
  when, attributable to a real persona-account" is a hard
  requirement.
- You already self-host other team infrastructure and adding a
  Plane instance is incremental cost, not new ops surface.
- The framework's strict user-triggered turn model matches your
  preference (you don't want a harness running Claude Code in
  the background; you want every turn to be deliberate).

---

## Migration paths (rough sketches)

Neither framework forbids migration. If you decide one fits better
after running a project on the other:

**BMAD → ours.** Keep BMAD's PRDs and architecture markdowns as
read-only artefacts (move them under `.claude/context/`). Mint
Plane work-items for the open Stories, port `[priority]` and
`#Label` tags. Add stable `SC-N` / `AC-N` IDs as you re-frame
each Story (don't retro-fit older closed work; let it stay in
git history). Rough order-of-magnitude effort: a half-day per
active Story plus a day for the Plane setup if you don't have a
Plane instance yet.

**Ours → BMAD.** Export each Story body and AC comment to
`stories/<DEV-N>.md`. Lose the per-persona attribution; you'll
need to re-author the agent prompts in BMAD's style. Stable IDs
can stay as a project-local convention. Effort dominated by the
Plane → file-system flattening (mostly mechanical) and the agent
prompt rewrite (mostly judgement).

Most teams won't migrate. The bus choice is the load-bearing one
and rarely changes after the first month.

---

## Honest gaps in this comparison

- We have not run BMAD end-to-end on a non-trivial Story. The
  comparison is based on their public documentation, source code,
  and practitioner write-ups. Hands-on experience would sharpen
  the gap analysis on UX details — particularly *how the
  hand-offs feel* compared to our Plane reassign.
- BMAD's V6 is moving fast; specific claims may date quickly.
  Re-baseline before quoting. The `Edge Case Hunter` we cited
  is a primitive of theirs we found compelling; the rest of the
  V6 surface may have grown since.
- We are biased. We chose Plane and shipped the framework around
  it. Treat this comparison as one team's reasoning about their
  own choices, not a neutral arbiter's verdict.

---

## Sources

- [GitHub: bmad-code-org/BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD)
- [BMAD Method Docs](https://docs.bmad-method.org/)
- [DeepWiki: BMAD-METHOD](https://deepwiki.com/bmad-code-org/BMAD-METHOD)
- [Applied BMAD — Reclaiming Control in AI Development (Benny Cheung)](https://bennycheung.github.io/bmad-reclaiming-control-in-ai-dev)
- [Reenbit: The BMAD Method](https://reenbit.com/the-bmad-method-how-structured-ai-agents-turn-vibe-coding-into-production-ready-software/)
- [Vishal Mysore: What is BMAD-METHOD?](https://medium.com/@visrow/what-is-bmad-method-a-simple-guide-to-the-future-of-ai-driven-development-412274f91419)
- [Mornati: 1-Day BMAD Experiment](https://blog.mornati.net/what-is-a-developer-when-we-use-coding-agents-my-1-day-bmad-experiment)
