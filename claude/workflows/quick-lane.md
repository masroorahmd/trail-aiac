# Workflow: quick lane

**Trigger:** A small, safe change that does not justify a Plane Story
— a trivial chore, a local bug fix, or a small single-surface feature.
The full spine's ceremony (BA → RE → SA → SR → implementor → TM → TW →
RM) would cost more than the change is worth.

This is the framework's one **off-Plane** path. Where every other
workflow records artefacts in Plane work-items and comments, the quick
lane records **nothing in Plane** — the git commit is the sole audit
trail.

## Persona path

There is none. `/quick` is **not a persona** — no Plane identity, no
token, no MCP calls. It is a single main-loop turn:

1. **`/quick <change>`** — checks the eligibility gate, implements the
   change against `coding.md`, writes the mandated test, runs the
   suite, records any reusable knowledge in the lane's memory (see
   below), and commits with a `Trail-Lane: quick (<class>)` trailer.

That's the whole path. No Story, no sub-work-items, no state spine, no
assignee chain, no handover comments.

## The eligibility gate (all must hold)

`/quick` proceeds only if **every** item is true:

1. No `control-manifest.md` *Security non-negotiable* touched (auth,
   authz, audit-emitting paths, secrets/PII).
2. No new external surface (public API endpoint, user-facing concept
   needing docs, breaking change).
3. No data/schema migration.
4. No new dependency with a licence/supply-chain question.
5. Bounded blast radius (~≤3 files / one module; a tweak, not a
   redesign).
6. Reversible by a single `git revert`.

Any failure → the lane refuses and routes USER to `/ba` (or `/re` if a
Story already frames it).

## Tests (not skipped, just not a TM turn)

- Bug fix → regression test (fails before, passes after) in the same
  commit.
- Feature → smoke test for the happy path.
- Trivial chore → no new test, but the existing suite must stay green.

Green suite at commit is the contract.

## Lane memory (the one cross-session artefact)

`/quick` has no persona, but the change lands in a persona's *lane*:
UI→`ui-developer`, backend→`backend-developer`, tests→`test-manager`,
docs→`technical-writer`. When the change locks in something a future
turn needs — a convention, a fixture pattern, a non-obvious gotcha —
the lane reads and appends to its
`agent-memory/<persona>/MEMORY.md`, one dated bullet tagged `[quick]`,
committed in the same commit. Trivial changes (typo, dep bump) record
nothing. The memory write is never a gate item and never blocks the
commit — it is knowledge upkeep, not an audit step.

## The bounce rule

The gate is re-checked *during* implementation, not only at entry. If
the change grows past the gate mid-flight (needs a migration, reaches
an auth path, blast radius expands), `/quick` **stops** — it does not
commit — summarises the finding, and sends USER to the normal spine.

## Notable deviations from the default

- **No Plane footprint at all.** This is the only workflow that leaves
  no work-item, no comment, no state transition. The trade-off is
  speed for a defined class of low-risk work; the gate + bounce rule
  are what keep it honest.
- **The commit *is* the spec, the review, and the record.** Write a
  commit message that a future reader can reconstruct the change from.
  `git log --grep='Trail-Lane: quick'` is the quick-lane audit log.
- **Not for anything security-shaped.** The moment a change touches a
  `CM-3x` non-negotiable it leaves the quick lane — SR is never skipped
  by routing around Plane.

## Example trigger

```
> /quick "fix typo in the --help output of the export command: 'recieve' → 'receive'"
> /quick "bump axios from 1.7.2 to 1.7.9 (patch, already-vetted dep)"
> /quick "BUG: dashboard 'Active' count includes archived items; filter them in the count query like the detail view already does"
```
