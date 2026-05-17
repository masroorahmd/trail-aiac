# The ten personas

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
| <img src="../avatars/venture-advisor.png" width="60"/>       | `venture-advisor`       | `/va` | Strategic advisor for founders; operates on a private "business" track. | Whenever you want a sounding board outside the Story workflow. |
| <img src="../avatars/business-analyst.png" width="60"/>      | `business-analyst`      | `/ba` | Turns feature ideas into Stories; writes the requirements directly into the Story body; owns backlog + priorities + product-area labels. | First step of any new Story — `/ba "I want X"`. |
| <img src="../avatars/requirements-engineer.png" width="60"/> | `requirements-engineer` | `/re` | Adds testable acceptance criteria (Gherkin) and edge cases as a comment on the Story (or passthroughs when BA's spec is already AC-quality). | After BA — `/re <STORY-ID>`. |
| <img src="../avatars/software-architect.png" width="60"/>    | `software-architect`    | `/sa` | Designs the solution and decomposes the Story into 1–4 sub-work-items in `frontend / backend / testing / documentation` modules; the architecture slice for each module lives in that sub-work-item's body. | After RE — `/sa <STORY-ID>`. |
| <img src="../avatars/security-reviewer.png" width="60"/>     | `security-reviewer`     | `/sr` | Strict, non-negotiable gate over every sub-work-item. Posts a security-review comment per child. Maintains project-level security state. | After SA — `/sr <STORY-ID>`. |
| <img src="../avatars/backend-developer.png" width="60"/>     | `backend-developer`     | `/bd` | Implements the `backend`-module sub-work-item; posts an Implementation notes comment. | After SR — `/bd <SUBTASK-ID>`. |
| <img src="../avatars/ui-developer.png" width="60"/>          | `ui-developer`          | `/ud` | Implements the `frontend`-module sub-work-item; posts an Implementation notes comment. | After SR — `/ud <SUBTASK-ID>`. |
| <img src="../avatars/test-manager.png" width="60"/>          | `test-manager`          | `/tm` | Implements the `testing`-module sub-work-item; owns test strategy and verification across the Story. | After SR — `/tm <SUBTASK-ID>`. |
| <img src="../avatars/technical-writer.png" width="60"/>      | `technical-writer`      | `/tw` | Implements the `documentation`-module sub-work-item; edits files in the project repo's docs directory. | After SR — `/tw <SUBTASK-ID>`. |
| <img src="../avatars/release-manager.png" width="60"/>       | `release-manager`       | `/rm` | Drives versioning, tagging, and release. Runs outside the Story workflow. | When you're cutting a release — `/rm`. |

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

## Where artefacts live

The framework does **not** use Plane pages. Every persona artefact
lives in either a Plane work-item **body** (written once at creation)
or a **comment**. See [`WORKFLOW.md`](WORKFLOW.md) for the full table.

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
