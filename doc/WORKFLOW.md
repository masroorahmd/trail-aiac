# Workflow — agent collaboration via Plane

> **Purpose**: how the ten Trail personas collaborate through
> Plane work-items to take a feature from idea to release. Source of truth for
> the ticket-level workflow; CLAUDE.md references it. Persona prompts encode
> this workflow per agent.
>
> **Audience**: humans operating the framework, and the framework author
> when authoring persona prompts. Personas read their own prompt, not
> this doc.

## Model in one paragraph

A piece of work is a **Story** (Plane parent work-item). The Story
carries the requirements directly in its **body**, written once by
the BA. Acceptance criteria are added by the RE as a **comment** on
the Story (or omitted, when RE passthroughs). The Software Architect
decomposes the Story into **1–4 sub-work-items** (Plane's
parent-child mechanic), each placed in a single phase **module**;
each sub-work-item's **body** carries the architecture slice for
that module. Implementors take one sub-work-item each, write code,
and post **Implementation notes** as comments. The human **user is
the dispatcher** throughout: every persona invocation is
user-triggered via a `/<persona>` slash command, and Plane's
`assignee` field functions as the user's TODO list, not an automated
trigger.

## Where artefacts live (no Plane pages)

The framework does **not** use Plane pages. Plane v1.3.0's pages
sit on the internal app API behind a Yjs/Tiptap collaborative
editor that does not reliably absorb API-side updates, which made
the previous page-based design fragile. Everything now lives in
**work-item bodies** (written once at creation) and **comments**:

| Artefact | Location | Notes |
|---|---|---|
| Hypothesis (VA) | BIZ work-item *body* | Optional embedded Lean Canvas; no separate page |
| Story requirements (BA) | Story work-item *body* | Problem / Target users / Success criteria / In scope / Out of scope |
| Acceptance Criteria (RE) | Comment on the Story work-item | Or omitted if RE passthroughs |
| Architecture per module slice (SA) | Each sub-work-item's *body* | Module / AC scenarios covered / Approach / Components / Trade-offs / Notes for SR |
| Security review (SR) | Comment on each implementor sub-work-item | Findings + No-concerns checks + cross-cutting context |
| Implementation notes (BD/UD/TM/TW) | Comment on the implementor's own sub-work-item | Files touched, deviations, test results, SR findings addressed |
| User-facing docs (TW) | Files in the project repo's docs directory | Not in Plane |
| Release notes (RM) | `CHANGELOG.md` in the project repo | Plus a comment on a release-tracker work-item |
| Per-persona handover DoDs | Comment on the work-item being handed off | Posted via the `plane-handover` skill |

**Description-once is the rule for every persona.** A work-item body
is written when it's created, and never edited afterwards. Later
annotations and handovers travel as comments.

## Two Plane axes — modules and labels

The framework uses Plane's modules and labels for two orthogonal
purposes:

### Phase modules (4, fixed by the framework)

Sub-work-items go into exactly one of these modules:

| Module | Owner during implementation |
|---|---|
| `frontend` | UI Developer |
| `backend` | Backend Developer |
| `testing` | Test Manager |
| `documentation` | Technical Writer |

Modules are Plane-native objects created once per project at kickoff.
Each sub-work-item is assigned to exactly one module, identifying the
implementor.

There is **no** module for Requirements, Architecture, or Security
Review. Those activities happen on the parent Story (as a body and
comments) or on the sub-work-items as comments — not as separate
sub-work-items.

### Story labels (project-configurable taxonomy)

Stories carry one or more labels classifying the *product area* — what
kind of work this is, independent of how it's executed. Labels are
project-specific; the framework does not prescribe a list. The kickoff
script seeds the project's label set.

The framework ships two reference label sets — pick one per project
in `host_vars/plane.yml` (or supply an inline list):

- **Development track** (`plane_bootstrap_labels_dev`):
  `Housekeeping`, `Security`, `UI`, `Foundation`, `Lifecycle`,
  `Services`, `Operations`, `Integrations`, `Enterprise`,
  `Distribution`, `Notifications`, `Configuration`. Designed for the
  engineering project where 9/10 personas execute.
- **Business track** (`plane_bootstrap_labels_business`):
  `Strategy`, `Go-to-Market`, `Pricing`, `Community`, `Discovery`.
  Designed for the founder/Venture-Advisor track where work is
  classified by business outcome rather than engineering surface.

The Business Analyst applies one or more of the relevant set's labels
to each Story it creates. Labels can be added or retired over the
project's lifetime without changing the workflow.

## Workflow diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                            USER                                  │
│        (dispatcher, reviewer, closes every ticket)               │
└──────┬───────────────────────────────────────────────────────────┘
       │ chat (/ba)
       ▼
   ┌─────────┐
   │   BA    │   creates Story (parent ticket) in `Backlog`,
   └────┬────┘   writes requirements into the Story body once.
                 Applies one or more product-area labels
                 (copied from roadmap entry if pulled from roadmap;
                 priority likewise copied from `[priority]` tag).
                 parent.assignee = RE
        │
        │ USER triages: state Backlog → To Do, then triggers RE (/re)
        ▼
   ┌─────────┐
   │   RE    │   reads Story body. Either:
   └────┬────┘   • posts an AC comment on the Story
                   (Gherkin scenarios + edge cases + NFRs)
                 • or passthroughs (BA's spec is already AC-quality)
                 On first pickup: state To Do → In Progress.
                 parent.assignee = SA
        │
        │ USER triggers SA (/sa)
        ▼
   ┌─────────┐
   │   SA    │   reads Story body + RE's AC comment, then
   └────┬────┘   creates 1–4 sub-work-items as children. Each
                 sub-work-item's body = the architecture slice
                 for one module {frontend|backend|testing|
                 documentation}. Each sub-work-item.assignee = SR.
                 parent.assignee = SR
        │
        │ USER triggers SR (/sr)
        ▼
   ┌─────────┐
   │   SR    │   discusses threat picture with USER in chat,
   └────┬────┘   then posts one security-review comment per
                 sub-work-item. sub-work-item.assignee = USER
                 parent.assignee = USER
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                       USER                              │
│  reads SR comments, edits/curates them, then            │
│  dispatches each sub-work-item to its implementor       │
│  (one per module):                                      │
│    module=frontend     → UD  (/ud)                      │
│    module=backend      → BD  (/bd)                      │
│    module=testing      → TM  (/tm)                      │
│    module=documentation→ TW  (/tw)                      │
└─┬────────┬─────────┬─────────┬──────────────────────────┘
  │        │         │         │
  │  USER triggers each implementor (sequential or parallel)
  ▼        ▼         ▼         ▼
 ┌───┐   ┌───┐    ┌───┐     ┌───┐
 │UD │   │BD │    │TM │     │TW │
 └─┬─┘   └─┬─┘    └─┬─┘     └─┬─┘
   │       │        │         │
   │  each writes code + posts an Implementation notes
   │  comment on its sub-work-item.
   │  state → In Review,  assignee = USER
   └───────┴────┬───┴─────────┘
                ▼
       ┌─────────────────┐
       │      USER       │
       │  reviews/tests  │
       │  ┌──────────┐   │
       │  │ rework?  │   │
       │  └──────────┘   │
       │   ↓no    ↓yes   │
       │  close   re-assign + comment + retrigger
       └────┬────────────┘
            │ when all sub-work-items closed
            ▼
       ┌─────────────────┐
       │      USER       │
       │  closes Story   │
       └─────────────────┘
```

## Walkthrough

1. **USER ↔ BA chat.** USER discusses an idea with the Business Analyst
   (`/ba <brief>`) until they agree on a Story. BA creates the parent
   work-item in state `Backlog`, writes the full requirements
   (Problem / Target users / Success criteria / In scope / Out of
   scope) into the Story body in one `create_work_item` call, applies
   one or more product-area labels, sets the priority (from the
   roadmap entry if pulled from roadmap, otherwise `none`), and sets
   `parent.assignee = RE`. The Story stays in `Backlog` until USER
   decides it should be worked.

2. **USER triages and triggers RE.** USER reviews the new Story,
   moves its state from `Backlog` to `To Do` when ready, and
   triggers the Requirements Engineer (`/re DEV-N`). RE chats with
   USER; on first pickup, RE moves the Story state from `To Do` to
   `In Progress`. When USER signs off, RE posts a comment on the
   Story containing the Acceptance Criteria (Gherkin scenarios +
   edge cases + non-functional requirements). The Story body is
   never modified — description-once is the rule. RE then sets
   `parent.assignee = SA`.

   **RE may passthrough.** When BA's `Success criteria` are already
   behavioural and testable as written, no edge cases are
   non-obvious, no NFRs are implied, and the vocabulary is
   glossary-consistent, RE creates no AC comment and posts a
   passthrough handover comment instead (see RE persona prompt,
   *Variant B*). BA's Story body acts as the canonical spec. State
   transition and SA reassignment are unchanged. SA records the
   passthrough on each sub-work-item body under *Trade-offs*.

   **USER may skip RE entirely.** If BA's framing is already
   sufficient and USER prefers no RE round, USER reassigns the Story
   directly from BA to SA (and moves it from `Backlog` to `To Do` →
   `In Progress` themselves). SA's *Pickup* path tolerates this —
   it uses BA's Story body as the AC and notes the RE-skip on each
   sub-work-item body's *Trade-offs* section.

3. **USER triggers SA.** USER and the Software Architect chat
   (`/sa DEV-N`). SA creates **1–4 sub-work-items** as Plane
   children of the Story, each placed in exactly one of the modules
   `{frontend|backend|testing|documentation}`. Each sub-work-item's
   body carries that module's architecture slice — Module / AC
   scenarios covered / Approach / Components / Data Models / API
   Endpoints / Trade-offs / Notes for Security Reviewer. Bodies are
   written once at creation. SA sets each sub-work-item's
   `assignee = SR`. Skippable phases are simply not created — no
   sub-work-item in the `frontend` module means no frontend work.
   SA posts the handover comment on the parent Story.

4. **USER triggers SR.** The Security Reviewer (`/sr DEV-N`) reads
   each sub-work-item plus the AC comment on the parent, discusses
   the threat picture with USER in chat, then posts one
   security-review comment per sub-work-item (findings or "no
   concerns" + the *No-concerns checks* list). SR sets every
   sub-work-item's `assignee = USER` and the parent's
   `assignee = USER`. SR does **not** dispatch directly to
   implementors — that branch is the user's call.

5. **USER reviews SR's comments**, edits or curates them, and
   dispatches each sub-work-item to the matching implementor by
   setting its assignee — one per module:

   - `frontend` → UI Developer (`/ud`)
   - `backend` → Backend Developer (`/bd`)
   - `testing` → Test Manager (`/tm`)
   - `documentation` → Technical Writer (`/tw`)

6. **USER triggers each implementor**, either sequentially or in
   parallel. Each implementor works on its own sub-work-item only,
   writes code (or doc edits in the project repo), and posts a
   single Implementation notes **comment** on its own sub-work-item.
   The sub-work-item body is never edited — description-once.

7. **Each implementor finishes** by setting their sub-work-item's
   `state = In Review` and `assignee = USER`.

8. **USER reviews / tests** each sub-work-item:
   - **Happy**: USER closes the sub-work-item (`state = Done`).
   - **Rework**: USER comments on the ticket, sets
     `assignee = <relevant implementor>`, and retriggers them. Or
     handles it directly in chat with no ticket round-trip.

9. **When all sub-work-items are closed**, USER closes the Story.

## Slash commands and the main loop

Each persona is invoked via a slash command — `/va`, `/ba`, `/re`,
`/sa`, `/sr`, `/bd`, `/ud`, `/tm`, `/tw`, `/rm`. The slash command
puts the **main loop** into the persona's role for this and any
follow-up turns; it does **not** spawn a Claude Code subagent. The
main loop reads the persona's prompt file (`.claude/agents/<name>.md`)
and the persona's `MEMORY.md` to take on the role, and stays in
that role until USER says "done" / "exit", or starts a different
slash command.

This design choice trades the hard MCP-scope barrier of subagents
(which can only see their own MCP servers) for a soft barrier
(persona prompt instructs main loop to use only its own MCP tools).
The benefit is conversational continuity: pre-write chat with USER
spans many turns, and the main loop carries that context throughout
without the cold-start each subagent invocation otherwise causes.

## Ticket lifecycles

### Parent (Story ticket)

- **State**:
  - `Backlog` on creation by BA. The Story stays in `Backlog` —
    regardless of who is assigned — until USER triages it.
  - `To Do` once USER decides the Story should be worked. This is
    USER's "go" signal; agents do not move tickets into `To Do`.
  - `In Progress` once the Requirements Engineer picks it up for the
    first time. Stays there through SA decomposition and the entire
    sub-work-item phase.
  - `Done` only when USER closes it (after every sub-work-item is
    closed).
- **Assignee**: chains naturally during the early phase
  (BA → RE → SA → SR → USER). After SR's review, the parent assignee
  stays USER through the implementor phase.
- **Priority**: copied from the roadmap entry if BA pulled the Story
  from the roadmap; otherwise `none` (USER may set it during triage).
- **Body**: written once by BA. Never edited.

### Sub-work-items (one per implementation phase)

- **Created** by Software Architect, with the architecture slice as
  the body.
- **State**: full 5-state spine matters here.
  - `Backlog` on creation (Plane default is fine).
  - `Todo` after USER's dispatch to the implementor.
  - `In Progress` once the implementor starts working.
  - `In Review` once the implementor is done, with `assignee = USER`.
  - `Done` only after USER explicit close.
- **Assignee chain**: SR (initial) → USER (after SR's review) →
  implementor (after USER dispatch) → USER (when implementor done) →
  closed.
- **Body**: written once by SA. Never edited; implementation notes
  are comments.
- **USER closes everything.** Agents never close any ticket — neither
  their own sub-work-item nor the Story.

## Rules and conventions

- **Description-once.** Every work-item body is written exactly once
  (at creation). Later annotations are comments. *Narrow Backlog
  carve-out:* a Story body still in `Backlog` with zero downstream
  artefacts (no RE AC comment, no SA decomposition, no implementation
  work) may be directly edited by BA under USER instruction — paired
  with a supersedence comment that names exactly which bullet of the
  prior handover is revoked. The moment any downstream artefact
  exists, the carve-out closes and comments-only stays the rule.
- **One module per sub-work-item.** Multi-module assignment is not
  supported — use separate sub-work-items if a phase splits.
- **One or more product-area labels per Story.** Plane allows
  multi-label, the framework does not enforce a cap. A Story can be
  both `Foundation` and `Security`, for instance.
- **Sub-work-item creation is SA-only.** No other persona creates
  children. (Exception is human emergency: the user can create children
  manually if needed.)
- **Any persona may originate a Story.** BA is the default, but any
  persona that surfaces a concrete issue during chat-mode
  investigation (SR finding a structural risk, SA spotting an
  architectural debt, TM noticing missing coverage) may originate a
  new Plane Story directly, with USER's explicit confirmation. Routing
  by shape: *bug-shaped* (clear fix path, clear AC) → assign to RE;
  *feature-shaped* (new convention, new artefact, ambiguous scope) →
  assign to BA. The originating persona writes the body, applies
  labels, and hands off via the `plane-handover` skill. Don't
  reflex-bounce scoping work back to BA when the framing is already
  bug-shaped and ready to decompose.
- **No module for Requirements, Architecture, or Security Review.**
  Those activities live at the body / comment level.
- **USER closes every ticket.** Personas move tickets to `In Review`
  with `assignee = USER`; USER decides Done vs. rework.
- **Triggering is always user-initiated.** Assignee changes do not
  auto-invoke any persona — they are signals on the user's TODO list.
- **No "Open questions" leak into bodies or comments.** Every
  uncertainty is resolved in chat with USER *before* the body /
  comment is written.

## Out of scope here

- **Release Manager** runs **outside** this Story-level workflow,
  triggered directly by USER (e.g. "tag a release", "draft changelog").
  Release Manager does not consume Stories or sub-work-items.
- **Venture Advisor** operates on a private "business" track separate
  from Story execution.

## Why the human is the dispatcher

Anthropic's terms of service do not allow a third-party harness
operating Claude Code beyond user-initiated turns. So:

- No Plane webhook or polling auto-invokes a persona. Every persona
  turn starts because the user runs a slash command.
- Plane's `assignee` field is the user's TODO list. The user may
  process it in any order — sequential, parallel, or skipped.
- The asymmetry where Software Architect → Security Reviewer is a
  direct assignee handoff but Security Reviewer → implementors goes
  through USER is intentional: SR's findings might re-route the work,
  and USER curates that decision before fanning out to multiple
  implementors.
