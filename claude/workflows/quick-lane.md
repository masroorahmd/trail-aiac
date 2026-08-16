# Workflow: quick lane

**Trigger:** A change whose risk is bounded enough that it does not
justify a Plane Story — a trivial chore, a local bug fix, a small
single-surface feature, or a **mechanical sweep** that repeats one edit
shape across many files. The full spine's ceremony (BA → RE → SA → SR →
implementor → TM → TW → RM) would cost more than the change is worth.

The lane's boundary is **risk, not size**. A twenty-file sweep that a
grep can enumerate and re-verify is in; a two-file change to an auth
path is out.

This is the framework's one **off-Plane** path. Where every other
workflow builds its artefacts in Plane, the quick lane creates nothing
there — the git commit is the audit trail. Its only Plane touch is
closing out a ticket USER already had (see *The hand-back*).

## Persona path

There is none. `/quick` is **not a persona** — no Plane identity and no
token of its own. It is a single main-loop turn:

1. **`/quick <change>`** — checks the eligibility gate, implements the
   change against `coding.md`, writes the mandated test, runs the
   suite, records any reusable knowledge in the lane's memory (see
   below), and commits with a `Trail-Lane: quick (<class>)` trailer.
2. **The hand-back**, *only* if USER named a work-item — the ticket
   goes `In Review`, assigned to USER, with one comment.

That's the whole path. No Story, no sub-work-items, no state spine, no
assignee chain.

## The eligibility gate (all must hold)

`/quick` proceeds only if **every** item is true:

1. No `control-manifest.md` *Security non-negotiable* touched (auth,
   authz, audit-emitting paths, secrets/PII).
2. No new external surface (public API endpoint, user-facing concept
   needing docs, breaking change).
3. No data/schema migration.
4. No new dependency with a licence/supply-chain question.
5. Bounded **risk** — either a local change (~≤3 files / one module; a
   tweak, not a redesign) **or** a mechanical sweep: one edit shape,
   no logic change, sites enumerable *and* re-verifiable by a single
   command. Any site needing its own judgement call breaks the sweep.
6. Reversible by a single `git revert`.

Any failure → the lane refuses and routes USER to `/ba` (or `/re` if a
Story already frames it).

## Tests (not skipped, just not a TM turn)

- Bug fix → regression test (fails before, passes after) in the same
  commit.
- Feature → smoke test for the happy path.
- Trivial chore → no new test, but the existing suite must stay green.
- Mechanical sweep → no per-site tests; the enumerating command from
  gate item 5, re-run and returning zero, is the evidence. Where the
  defect class should stay closed, that command is left behind as a
  lint / CI guard and *is* the coverage.

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

## The hand-back (only with a work-item)

No ID from USER → **no Plane call at all**, and the lane ends at the
commit. With an ID, `/quick` closes the loop on that ticket:

1. **Read it first**, while checking the gate — a scope that does not
   match the brief, an Epic or a Story with children, or a ticket
   already `Done` each stop the hand-back and go back to USER.
2. **After the commit** (never before): one `update_work_item` to
   `In Review` + `assignee = USER`, straight from whatever state it was
   in — USER's `/quick` invocation *is* the triage signal — then a
   `retrieve_work_item` to confirm, because the PATCH echo is not
   evidence. Never `Done`; USER closes.
3. **One comment**: DoD (what changed, the commit SHA + branch, the
   test evidence) and a concrete next action for USER.

Identity is **borrowed**, not owned: `/quick` has no token, so it uses
the three tools (`retrieve_work_item`, `update_work_item`,
`add_comment`) of the persona whose *lane* the change landed in — the
same UI/backend/tests/docs mapping the lane memory uses — and the
comment states that the quick lane acted. It never creates a work-item
and never uses a second persona's tools.

If Plane is unreachable the commit **stands**; the transition is
reported to USER as pending, never rolled back.

## The bounce rule

The gate is re-checked *during* implementation, not only at entry. If
the change grows past the gate mid-flight (needs a migration, reaches
an auth path, blast radius expands), `/quick` **stops** — it does not
commit — summarises the finding, and sends USER to the normal spine.

## Notable deviations from the default

- **Creates no Plane work.** This is the only workflow that files no
  work-item and walks no state spine. The trade-off is speed for a
  defined class of low-risk work; the gate + bounce rule keep it
  honest.
- **The commit *is* the spec, the review, and the record.** Write a
  commit message that a future reader can reconstruct the change from.
  `git log --grep='Trail-Lane: quick'` is the quick-lane audit log.
  When USER names a work-item, that ID opens the subject line, repeats
  in a `Refs: <PROJ>-123` trailer, and the ticket gets the hand-back
  above. No ID given, no prefix, no trailer, no Plane call; `/quick`
  never invents one.
- **Not for anything security-shaped.** The moment a change touches a
  `CM-3x` non-negotiable it leaves the quick lane — SR is never skipped
  by routing around Plane.

## Example trigger

```
> /quick "fix typo in the --help output of the export command: 'recieve' → 'receive'"
> /quick "bump axios from 1.7.2 to 1.7.9 (patch, already-vetted dep)"
> /quick "BUG: dashboard 'Active' count includes archived items; filter them in the count query like the detail view already does"
> /quick "strip internal ticket IDs (PROJ-123) out of user-facing helper text across the templates; grep enumerates the sites"
> /quick "DEV-51: drop the debug banner from the export footer"
```

The last one is the only shape that reaches Plane: `DEV-51` ends the
turn `In Review`, assigned to USER. The first three leave no trace
outside git.
