# The eleven personas

> **Note (masroor branch).** This branch retires the Venture Advisor
> in favour of a `general-manager` persona scoped to founder
> operations (Behörden, Notar, Recht, Steuern, Staffing, Förderung,
> Compliance) on a separate `HQ` Plane project, and adds a
> `marketing-manager` for the website (`.org` OSS narrative +
> `.com` enterprise funnel), brand voice, and SEO on a separate
> `MKT` Plane project. The lightweight strategy sanity-check that
> VA used to gate ideas now lives in the Business Analyst's prompt;
> the BA also takes over `roadmap.md` ownership. The table below
> reflects this branch's persona set.


Each persona is a role the **main loop** Claude Code session takes on
when you invoke its slash command — own identity in Plane (per-persona
API token), own context-file allowlist, own quality gate. The
framework ships persona definitions as `claude/agents/<username>.md`
and slash-command dispatchers under `claude/commands/`;
`bin/install.py` copies both into the consumer's `.claude/`. When you
type a slash command, the main loop reads the persona's prompt + its
`MEMORY.md` and acts as that persona for this and any follow-up turns,
until you say "done" / "exit" or start a different `/<persona>`
command.

| Avatar | Username | Slash | Role | When you invoke |
|---|---|---|---|---|
| <img src="../avatars/general-manager.png" width="60"/>       | `general-manager`       | `/gm` | Operative GmbH-Begleitung: Behörden, Notar, Recht, Steuern, Staffing, Förderung, Verträge, Compliance-Fristen. Eigenes Plane-Projekt `HQ`. | Whenever you face an operational, organisational, legal, financial, or staffing matter — `/gm "<thema>"`. |
| <img src="../avatars/business-analyst.png" width="60"/>      | `business-analyst`      | `/ba` | Turns feature ideas into Stories; writes the requirements directly into the Story body; owns backlog + priorities + product-area labels; owns `roadmap.md`; owns the sprint cadence (Plane cycles — create/schedule sprints, pull Stories in, carry unfinished work forward). | First step of any new Story — `/ba "I want X"`; also `/ba "plan the next sprint"`. |
| <img src="../avatars/requirements-engineer.png" width="60"/> | `requirements-engineer` | `/re` | Adds testable acceptance criteria (Gherkin) and edge cases as a comment on the Story (or passthroughs when BA's spec is already AC-quality). | After BA — `/re <STORY-ID>`. |
| <img src="../avatars/software-architect.png" width="60"/>    | `software-architect`    | `/sa` | Designs the solution and decomposes the Story into 1–4 sub-work-items in `frontend / backend / testing / documentation` modules; the architecture slice for each module lives in that sub-work-item's body. | After RE — `/sa <STORY-ID>`. |
| <img src="../avatars/security-reviewer.png" width="60"/>     | `security-reviewer`     | `/sr` | Strict, non-negotiable gate over every sub-work-item. Posts a security-review comment per child. Maintains project-level security state. | After SA — `/sr <STORY-ID>`. |
| <img src="../avatars/backend-developer.png" width="60"/>     | `backend-developer`     | `/bd` | Implements the `backend`-module sub-work-item; posts an Implementation notes comment. | After SR — `/bd <SUBTASK-ID>`. |
| <img src="../avatars/ui-developer.png" width="60"/>          | `ui-developer`          | `/ud` | Implements the `frontend`-module sub-work-item; visually verifies **every** route the change touched in a browser before handing back, and enumerates them in the Implementation notes. | After SR — `/ud <SUBTASK-ID>`. |
| <img src="../avatars/test-manager.png" width="60"/>          | `test-manager`          | `/tm` | Implements the `testing`-module sub-work-item; owns test strategy and verification across the Story; posts the Story's **Review steps** comment on every hand to `In Review`. On demand drives those steps in a live browser, filing a *Rework request* on each owning persona's sub-work-item. | After SR — `/tm <SUBTASK-ID>`. To drive them: `/tm run review steps for <STORY-ID>`. |
| <img src="../avatars/technical-writer.png" width="60"/>      | `technical-writer`      | `/tw` | Implements the `documentation`-module sub-work-item; edits files in the project repo's docs directory. | After SR — `/tw <SUBTASK-ID>`. |
| <img src="../avatars/release-manager.png" width="60"/>       | `release-manager`       | `/rm` | Drives versioning, tagging, and release. Runs outside the Story workflow. | When you're cutting a release — `/rm`. |
| <img src="../avatars/marketing-manager.png" width="60"/>     | `marketing-manager`     | `/mm` | Owns the website(s) — positioning, IA, copy, CTAs, brand voice, SEO across `.org` (OSS narrative) and `.com` (enterprise funnel). Edits text-only content directly; hands site code (layout, components, build) to UI Developer via Plane Story on the `MKT` project. Co-owns `.org` documentation prose with Technical Writer. | When you scope a website / brand / SEO initiative — `/mm "<brief>"`. |

## Handover model

Direct agent-to-agent assignee handoffs along the early spine:

```
BA  →  RE  →  SA  →  SR  ⇒  USER  →  {UD | BD | TM | TW}  ⇒  USER closes
```

The `⇒` arrows are the asymmetry: SR returns each sub-work-item to
USER, who reads SR's review comments, edits/curates them, then
dispatches to the right implementor. Implementors send their work to
`In Review` with `assignee = USER`, who closes. **Personas never close
tickets** — neither parent nor sub-work-items.

Full state spine and walkthrough: [`WORKFLOW.md`](WORKFLOW.md).

## Model lanes

Personas and subagents run on one of three model lanes. The lane →
model mapping lives in the consumer's `.claude/config.yaml` under
`model_lanes:`; `bin/install.py` renders it into the persona and
command files (the framework sources carry `__MODEL_STANDARD__` /
`__MODEL_FULL__` / `__MODEL_CODEGEN__` placeholders).

| Lane | Default | Who runs on it |
|---|---|---|
| `standard` | `claude-sonnet-4-6` | Routine persona turns: GM, BA, RE, BD, UD, TM, TW, RM, MM. |
| `full` | `claude-fable-5` | High-stakes, long-horizon reasoning: `/sa` design, `/sr` threat review, and the `edge-case-hunter` subagent. |
| `codegen` | `claude-opus-4-8` | Volume code-writing subagents: `ui-test-writer`. |

Main-loop personas cannot switch models programmatically — the `/sa`
and `/sr` dispatchers carry a reminder to run `/model <full-lane
model>` before the turn and to switch back afterwards. Subagent
frontmatter (`edge-case-hunter`, `ui-test-writer`) is honoured by
Claude Code automatically. When a new model ships, bump the lane in
`config.yaml` and re-run `bin/install.py` — no framework edit
required.

## Where artefacts live

The framework does **not** use Plane pages. Every persona artefact
lives in either a Plane work-item **body** (written once at creation)
or a **comment**. See [`WORKFLOW.md`](WORKFLOW.md) for the full table.

Both are effectively **write-once**: bodies by the description-once
rule, comments because the Plane API exposes no edit or delete verb.
Personas are told to check the echoed `comment_html` after posting and
to repost with a supersede note if it came back double-encoded — see
[`MCP.md`](MCP.md) § *HTML body / comment authoring*.

On the filesystem side, a persona's `.claude/context/*.md` and
`.claude/agent-memory/**` are ordinary files in a single-consumer
install, but **symlinks into a shared `claude-context` repo** in a
multi-consumer setup linked by `bin/link-shared.py`. `Edit` refuses a
symlink, so every persona is instructed to resolve the path and edit
the target — and to treat a write there as landing in a *second*
repository's working tree, which it never commits.

## Persona file anatomy

Every `claude/agents/<persona>.md` follows the same template:

- **Persona one-liner** + tone/character note.
- **Operating mode** block (read first): main-loop role, no
  self-finalisation, MCP-tool discipline (only the persona's own
  `plane__<persona_snake>__*` tools), chat-first /
  write-on-USER-trigger, no Plane pages.
- **Hard-coded context-read list** (which `.claude/context/*.md`
  files this persona reads). Each persona names its allowlist
  explicitly.
- The single multi-tenant `plane` MCP server (one process for the
  whole session) registers every tool once per persona, prefixed by
  the persona's snake-case username. Each persona's prompt restricts
  it to its own prefix (see [`MCP.md`](MCP.md)).
- **Trigger conditions** (`description:` line).
- **Pickup** — what the persona does on entry: read the work-item
  body, the AC comment (if any), the implementor comments (where
  relevant), and any SR findings.
- **Outputs** — structured body / comment shapes.
- **DoD-checklist handover** via the shared `plane-handover` skill.
- **Self-Quality-Gate** — inline checklist the persona runs on its
  own output before signing off, including a top-line check that
  every Plane read/write was triggered by an explicit USER ask.
- **Stop-on-ambiguity** — chat-first discipline: every uncertainty is
  resolved live with USER *before* writing a body or comment. No
  "Open questions" sections leak into Plane.
- **Cross-persona quick lookup** — `Agent(subagent_type='...')`
  one-shot subagent for a single factual question across lanes.
- **Kill criteria** — after 3 failed iterations within a phase, the
  ticket is bounced back to USER with a note.
- **Memory discipline** — what counts as memory-worthy vs. ephemeral
  conversation context. Each persona has its own
  `agent-memory/<persona>/MEMORY.md`.
- **What you do NOT do** — the forbidden list.

## Project taxonomy

Each Story carries one or more **product-area labels** (independent
of how it's executed). The framework ships two reference sets and the
kickoff script seeds whichever the project picks (or an inline custom
list). The two shipped sets:

- **Development track**: `Housekeeping`, `Security`, `UI`,
  `Foundation`, `Lifecycle`, `Services`, `Operations`, `Integrations`,
  `Enterprise`, `Distribution`, `Notifications`, `Configuration`.
- **Business track**: `Strategy`, `Go-to-Market`, `Pricing`,
  `Community`, `Discovery`.
- **Marketing track** *(masroor branch — MKT project)*: two-dimensional
  — at least one **track** label (`OSS` for `.org`, `EE` for `.com`)
  plus at least one **content-area** label (`Landing`, `Hero`,
  `Pricing`, `Blog`, `Docs`, `Nav`, `SEO`, `Brand`, `Campaign`).
