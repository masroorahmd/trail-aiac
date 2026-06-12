# Workflow: autopilot (unattended full spine)

**Trigger:** A rare, low-risk, **already-framed** Story that USER wants
taken all the way to a closed ticket without sitting between every
stage. USER types `/autopilot DEV-N` once; the whole engineering spine
runs unattended.

This is the mirror image of the [quick lane](quick-lane.md). The quick
lane *shrinks the process* for a tiny change. Autopilot *keeps the
whole process* (RE → SA → SR → BD/UD → TM → TW → commit/push → RM) but
removes the human from between its stages — every persona makes and
**logs** reasonable assumptions instead of asking, and an orchestrator
threads them together.

It does **not** break the user-triggered rule: USER triggered exactly
one turn, and nothing in Plane drives Claude Code. Autopilot only
collapses the N handover turns USER would otherwise type into one
supervised-by-design run.

## What `/autopilot` is (and is not)

- **Not a persona.** No Plane identity, no token, no MCP calls — like
  `/quick`. It is the **orchestrator**.
- It owns exactly three things: **control flow** (which persona runs
  next; PROCEED / STOP / REPAIR), **git** (feature branch, commit,
  push), and **the terminal summary** to USER.
- Every spine persona runs as a **subagent under its own
  `plane__<persona>__*` identity**, so Plane attribution is identical
  to the interactive flow. The orchestrator never reads or writes Plane
  — it reads each subagent's `AUTOPILOT-VERDICT` block and decides.

## Pre-flight gate (before any subagent is spawned)

1. `autopilot.enabled: true` in `config.yaml` — else refuse.
2. Exactly one Story ID in the argument (the only question autopilot
   may ask USER is "which ticket?" when it's missing).
3. `control-manifest.md` + `stack.md` loaded (guardrails + how to test
   + default branch).
4. Clean working tree; create feature branch
   `autopilot/<DEV-N>-<slug>` off the default branch.

## The persona path

Each persona is spawned with the **Autopilot contract** (the
`AUTOPILOT-MODE` token + the assumption-ledger and verdict rules), then
the persona file, the ticket, and the upstream handover.

1. **requirements-engineer** — `To Do → In Progress`, posts AC (or
   passthrough). **First risk gate**: no testable AC under a reasonable
   assumption, or the Story exceeds `max_risk_lane` → STOP.
2. **software-architect** — decomposes into the applicable
   `backend / frontend / testing / documentation` sub-work-items. STOP
   if a clean decomposition needs something outside the lane.
3. **security-reviewer** — **hard gate**: any `blocker`/`high` finding
   → STOP (never self-cleared). Clean or `low`/`info` only → PROCEED.
4. **implementors (parallel)** — `backend-developer` and/or
   `ui-developer`, spawned concurrently, one per code sub-work-item.
   Each implements, runs the suite, posts Implementation notes, moves
   its item to `In Review`. Bounce rule (as `/quick`) → STOP.
5. **test-manager** — writes/extends tests, runs the full suite.
   - green → PROCEED.
   - fixable red → **REPAIR**: orchestrator re-spawns the named
     implementor with TM's failure detail, then TM again, up to
     `max_repair_iterations`; still red after that → STOP.
   - un-runnable / non-fixable → STOP.
6. **technical-writer** — only if SA created a documentation
   sub-work-item. Writes docs; does not stop unless a product decision
   surfaces.
7. **commit + push (orchestrator)** — stage the tree, commit with a
   `Trail-Lane: autopilot (<DEV-N>)` trailer, push the **feature
   branch** (never default, never `--force`; push failure is recorded,
   not fatal).
8. **release-manager** — performs the project's close/release step.
   Honours its own tag-push human gate — STOP rather than push a tag.

## The `AUTOPILOT-VERDICT` protocol

Every subagent ends its turn with:

```
AUTOPILOT-VERDICT: PROCEED | STOP | REPAIR
STATE: <Plane state left>
ITEMS: <work-item IDs created/moved>
ASSUMPTIONS: <count of AS-N logged>
STOP-REASON: <one line — only on STOP>
NEXT: <next persona, or "human" on STOP, or implementor on REPAIR>
NOTES: <one line for the next stage>
```

`REPAIR` is the Test Manager's alone. No parseable verdict is treated
as STOP.

## The assumption ledger (autopilot's audit artefact in Plane)

Where an interactive persona would ask USER, the autopilot persona
picks the most reasonable assumption and records it as a numbered
`AS-N` entry in one **Autopilot assumptions (<persona>)** comment on
the work-item:

```
**Autopilot assumptions (requirements-engineer)**
- AS-1: Treated "fast" in SC-2 as p95 < 300ms — the project's existing NFR baseline.
- AS-2: Exported CSV uses the user's locale date format — matches the dashboard.
```

No silent assumptions. The orchestrator's terminal summary gathers
every `AS-N` from every persona into one list — that is what USER
reviews **after** the run instead of being interrupted **during** it.

## Stopping is a success

Autopilot is the **narrow** lane. The instant a stage returns STOP (or
the repair loop exhausts, or a subagent aborts), the spine halts: no
later stages, no commit of a half-built change, working tree and
feature branch left intact for USER. The Plane items stay where the
last persona left them, with its explanatory comment. The terminal
summary reports `OUTCOME: STOPPED`, the stage, and the reason, and
recommends which `/<persona>` to resume with. Reaching the edge of the
lane and handing back is the design working, not failing.

## Git is the orchestrator's

Personas never touch git under autopilot — they edit the working tree
and write to Plane only. The orchestrator branches, commits (with the
`Trail-Lane: autopilot` trailer, so
`git log --grep='Trail-Lane: autopilot'` is the full unattended-change
log), and pushes the feature branch. To undo a completed run: revert
the commit, delete the branch.

## Example trigger

```
> /autopilot CRTHVN-83
> /autopilot DEV-42
```

Reach for it only on tickets you would be comfortable reviewing **after**
they ship to a feature branch — small, well-specified, security-neutral
work. Anything else: run the normal spine, or let autopilot start and
hand it back the moment a gate trips.
