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

## Three Plane axes — modules, labels, and cycles

The framework uses Plane's modules, labels, and cycles for three
orthogonal purposes — *who* implements a slice (module), *what kind*
of work it is (label), and *when* it is scheduled to ship (cycle):

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
  Designed for the founder/Business-Analyst track where work is
  classified by business outcome rather than engineering surface.

The Business Analyst applies one or more of the relevant set's labels
to each Story it creates. Labels can be added or retired over the
project's lifetime without changing the workflow.

### Sprints (Plane cycles, BA-owned)

A **cycle** is Plane's sprint primitive: a named, dated window
(`start_date` … `end_date`) that work items are assigned to. Cycles
are the *when* axis — orthogonal to both module (*who*) and label
(*what*). They are **optional**: a project that ships continuously can
ignore them entirely and the Story spine above is unchanged.

The **Business Analyst owns the sprint cadence** — and only the BA.
Cycles live on the dev project (`config.yaml: plane.projects.dev`).
The BA creates each sprint, schedules its window, pulls triaged
Stories into it, and at sprint's end transfers whatever is unfinished
into the next cycle. No other persona creates, edits, or deletes a
cycle; implementors and reviewers may *read* cycle membership (e.g. to
see which sprint a Story belongs to) but never mutate it. Full CRUD is
exposed over Plane's public REST — see the BA persona prompt
(*Sprint / cycle management*) for the conventions (one active cycle at
a time, English cycle names, both dates set together).

Conventions:

- **One active cycle at a time** on the dev project. Overlapping live
  sprints are not used.
- **A Story joins a cycle as a whole.** Sub-work-items inherit their
  scheduling from the parent Story; the BA assigns the *Story* to the
  cycle, not individual children.
- **Cycle assignment is independent of state and assignee.** Putting a
  Story in the current sprint does not move it along the state spine or
  change who is assigned — it is purely a scheduling signal.
- **Description-once does not apply to cycles.** Cycles are mutable
  scheduling containers (reschedule the window, add/remove members,
  transfer unfinished work); the rule governs work-item *bodies*, not
  cycles.

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

## The quick lane (off-Plane)

`/quick` is a deliberate exception to everything above. For a small,
safe change — a trivial chore, a local bug fix, a small
single-surface feature — the full spine costs more than the change is
worth. The quick lane collapses it into a **single main-loop turn that
leaves no Plane footprint**: no Story, no sub-work-items, no state
spine, no assignee chain, no handover comments. The **git commit is
the only audit artefact**, carrying a `Trail-Lane: quick (<class>)`
trailer so `git log --grep='Trail-Lane: quick'` reconstructs everything
that bypassed Plane.

It is *not* a persona: no Plane identity, no token, no MCP calls. It
is gated, not a free pass:

- **Eligibility gate (all must hold):** no `control-manifest.md`
  *Security non-negotiable* touched; no new external surface; no
  data/schema migration; no new dependency with a licence question;
  bounded blast radius (~≤3 files / one module); reversible by a
  single `git revert`. Any failure routes USER to `/ba` (or `/re`).
- **Bounce rule:** the gate is re-checked *during* implementation. If
  the change grows past it, `/quick` stops without committing and sends
  USER to the normal spine. Security work never gets routed around SR
  by going off-Plane.
- **Tests are mandatory in-lane** (regression test for a fix, smoke
  test for a feature) even though no Test Manager turn runs; the suite
  must be green at commit.
- **Lane memory is kept.** Though it has no persona identity, the
  change lands in a persona's *lane* (UI→`ui-developer`,
  backend→`backend-developer`, tests→`test-manager`,
  docs→`technical-writer`). When the change locks in something reusable
  — a convention, a fixture pattern, a gotcha — `/quick` reads and
  appends to that lane's `agent-memory/<persona>/MEMORY.md`, tagged
  `[quick]`, and commits the note in the same commit. Trivial changes
  (typo, dep bump) write nothing. This is the one cross-session
  artefact the quick lane keeps beyond the commit; it is not a gate
  item and never blocks the commit.

See [`../claude/workflows/quick-lane.md`](../claude/workflows/quick-lane.md)
for the full path and triggers. The quick lane does **not** run the
Story lifecycle, so the ticket-lifecycle and description-once rules
above simply do not apply to it.

## The autopilot lane (unattended spine, lean by default)

`/autopilot DEV-N` is the opposite trade from the quick lane. Where
`/quick` *shrinks* the process for a tiny change, autopilot keeps the
spine but removes the human from between its stages. One
human-initiated turn (USER types `/autopilot DEV-N`) drives a single
already-framed Story all the way to a closed ticket — RE → SA → SR →
BD/UD → TM → TW → commit → RM → merge — without stopping to ask USER
anything. That chain is the *maximum* path: in **lean-lane mode** (the
default) the orchestrator uses judgement to trim the ceremony a small
Story doesn't need (see below). On a clean run it ends with the feature
branch merged into the default branch and deleted; on a STOP it hands
back with the branch intact.

It does not weaken the user-triggered rule (see *Why the human is the
dispatcher*): USER still triggers exactly one turn, and nothing in
Plane drives Claude Code. Autopilot just collapses the N handover turns
USER would otherwise type into one supervised-by-design run.

How it stays safe and auditable:

- **Orchestrator owns control flow + git, nothing else.** `/autopilot`
  is not a persona — no Plane identity, no token, no MCP calls. It
  spawns each spine persona as a **subagent under that persona's own
  `plane__<persona>__*` identity**, so Plane attribution stays exactly
  as in the interactive flow. The orchestrator only reads each
  subagent's `AUTOPILOT-VERDICT` and decides PROCEED / STOP / REPAIR,
  and it owns all git — the feature branch, the parallel implementors'
  isolated worktrees, the commits, the push, and the final merge/delete
  (personas never touch git).
- **Assume-and-log, not ask.** Each persona, under the `AUTOPILOT-MODE`
  token, flips from "ask USER" to "pick the most reasonable assumption
  and record it as a numbered `AS-N` entry in an *Autopilot assumptions*
  comment". The assumption ledger is what USER reviews after the fact
  instead of being interrupted up front — every assumption is on the
  ticket, attributed to the persona that made it.
- **The narrow lane, with gates that stop it.** Autopilot is for rare,
  low-risk, already-framed tickets. RE is the first gate (no testable
  AC, or the Story exceeds `autopilot.max_risk_lane` → stop); **SR is
  the hard gate** (any blocker/high finding → stop, never self-cleared);
  implementors bounce like `/quick` if the change reaches a security
  non-negotiable or a migration; TM↔implementor repair-loops a fixable
  red suite up to `max_repair_iterations`, then stops. **Stopping is a
  success** — it means the change reached the edge of what may be done
  unattended and handed the wheel back, working tree and branch intact.
- **Lean-lane discretion — right-size the ceremony (default on).** The
  full spine is the maximum path, not a fixed liturgy: on a small,
  low-risk Story, running every persona burns tokens on handovers that
  carry no content. Under `autopilot.lean_lane: true` (the default) the
  orchestrator may (a) **skip RE, SA, SR, TM, TW, or RM** when they add
  no value for the Story — a Story already framed as crisp, testable AC
  needs no Requirements Engineer to re-state it, a single-slice change
  with one obvious module needs no Software Architect to decompose it (the
  Story itself becomes the single work-item the one implementor and TM
  work directly, no sub-work-items), a pure-logic refactor needs no
  Security Reviewer, a docs- or config-only change with no runtime surface
  needs no Test Manager, an internal-only change no Technical Writer, a
  Story with no release ceremony no Release Manager; and (b) **collapse
  or swap
  the BD/UD implementors** when the cross-over work is small — one agent
  covers both slices (no worktree), or a two-line backend tweak routes
  entirely to `ui-developer` and vice versa. Five hard floors keep it
  honest: **RE always runs whenever the Story is not already testable AC
  or framing it might expose a risk-lane question** (a migration, a new
  external contract or dependency, a security non-negotiable — when in
  doubt, it runs, since RE is autopilot's first risk gate); **SA always
  runs whenever the change spans more than one module or discipline or
  needs a non-trivial decomposition** (when in doubt, it runs, since SA is
  a risk gate too — it STOPs when a clean decomposition demands something
  outside the lane); **TM always runs whenever the change has any runtime
  surface** (only a docs/comment/non-behavioural-config change with
  nothing to test may skip the quality gate — when in doubt, it runs);
  **SR always runs whenever the change touches a `CM-N`
  security non-negotiable** (auth/authz, secrets/crypto,
  externally-controlled input, PII, a new dependency, a network/permission
  boundary — when in doubt, it runs); and **skipping RE or RM leaves the
  Plane Story in a non-terminal state** (`To Do` for a skipped RE,
  typically `In Review` for a skipped RM) because the orchestrator has no
  token to move it — flagged as a loose end in the summary, while the git
  merge still runs. Every skip
  and merge is logged as a numbered
  `SKIP-N` decision — the orchestrator's analogue of a persona's `AS-N`
  assumptions — and surfaced in full in the terminal summary, so nothing
  is trimmed silently. Set `autopilot.lean_lane: false` to force the
  full spine on every run (compliance-heavy projects).
- **Git is the orchestrator's.** The two parallel implementors each run
  in their own throwaway `git worktree` (the one stage where two agents
  would otherwise share a tree); the orchestrator commits and merges
  each back into the feature branch. Every autopilot commit carries a
  `Trail-Lane: autopilot (<DEV-N>)` trailer — the mirror of
  `Trail-Lane: quick`, so `git log --grep='Trail-Lane: autopilot'`
  lists every unattended change. On a **clean COMPLETED run** (all gates
  green) the orchestrator merges the feature branch into the default
  branch with `--no-ff`, pushes it, and deletes the feature branch +
  worktrees — the deliberate end of the unattended lane. If that merge
  or push can't land (conflict, branch protection), it stops with the
  branch intact for a human. It never uses `--force`, and on **STOP** it
  never merges or deletes — the branch stays for USER to inspect.

Gated off by default: `/autopilot` refuses to run unless
`autopilot.enabled: true` in `config.yaml`. See
[`../claude/workflows/autopilot.md`](../claude/workflows/autopilot.md)
for the full path, the `AUTOPILOT-VERDICT` protocol, and the per-persona
STOP conditions.

## Out of scope here

- **Release Manager** runs **outside** this Story-level workflow,
  triggered directly by USER (e.g. "tag a release", "draft changelog").
  Release Manager does not consume Stories or sub-work-items.
- **General Manager** *(masroor branch)* runs on a separate `HQ`
  Plane project for founder operations (Behörden, Notar, Recht,
  Steuern, Staffing, Förderung, Compliance). Independent of the
  Story workflow — no upstream/downstream persona handover.

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

`/autopilot` is consistent with this, not an exception to it: it is a
single user-initiated turn that runs many persona stages internally as
subagents. No ticket triggers it, no harness polls Plane — USER typed
the command. The difference from the normal flow is only *where* the
human sits: ahead of the run (choosing to autopilot a low-risk ticket
and reviewing the assumption ledger after) rather than between every
stage. The moment a stage hits its STOP condition, the wheel is handed
straight back to USER.
