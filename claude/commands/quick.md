---
description: Off-Plane quick lane — implement a small, safe change in a single main-loop turn (no Story, no personas, no Plane). Git commit is the only artefact.
argument-hint: "<short description of the change, e.g. 'fix typo in CLI help' or 'bump axios to 1.7.9'>"
---

You are running `/quick` directly in the **main loop** of this Claude
Code session. `/quick` is **not a persona** — it has no Plane identity,
no token, and makes **no Plane MCP calls whatsoever**. It is the
framework's deliberate *off-Plane quick lane*: a single turn that
implements a small, safe change and commits it. The git commit is the
**only** audit artefact.

Use it only for work that is genuinely small and safe. Everything
else goes through the normal spine (`/ba`, `/re`, …). Your first job
every turn is to defend that boundary.

## Load standards (read before touching anything)

Read these in full and treat them as your constraints for this turn:

1. `.claude/context/control-manifest.md` — the project's `CM-N`
   guardrails. The *Security non-negotiables*, *Compliance / legal*,
   and *Architectural invariants* sections are the hard gate below.
2. `.claude/context/coding.md` — the code-level conventions you must
   match. Read at least one existing file near your change before
   writing.
3. `.claude/context/stack.md` — the tech stack and how to run tests.
4. **The lane's persona memory** — once the brief tells you which lane
   the change lands in (see the mapping in *Memory* below), read that
   lane's `.claude/agent-memory/<persona>/MEMORY.md`. It carries the
   conventions, fixture patterns, and gotchas prior turns locked in;
   your change must follow them, and reading it now is what lets you
   append without duplicating later.

Do **not** read `product.md`, `roadmap.md`, `security.md`,
`testing.md`, etc. — the quick lane has no product/spec phase.

## The eligibility gate (ALL must hold)

A change is quick-lane-eligible **only if every one** of these is true.
Check them out loud against USER's brief before you write a line:

1. **No security non-negotiable touched.** Nothing under
   `control-manifest.md`'s *Security non-negotiables* — no auth path,
   no authz boundary, no audit-emitting call site, no secret/PII
   handling. If any `CM-3x` could be in play → **bounce**.
2. **No new external surface.** No new public API endpoint, no new
   user-facing concept that would need documentation, no breaking
   change to an existing contract.
3. **No data/schema migration.** No DB migration, no change to a
   persisted on-disk/wire format.
4. **No new dependency** carrying a licence or supply-chain question
   (a patch/minor bump of an already-vetted dep is fine; a brand-new
   package is not).
5. **Bounded blast radius.** Local change — as a rule of thumb
   ~3 files / a single module. A tweak or a fix, not a redesign.
6. **Reversible.** A single `git revert` fully undoes it.

If **any** item fails, do **not** proceed. Say which item failed and
route USER to the right entry point:
- bug-shaped, but touches security / migration / a contract → `/ba`
  (or `/re` if a Story already frames it) so it gets SR + proper AC.
- feature-shaped / ambiguous scope → `/ba`.

## The bounce rule (safety valve)

The gate is **not** only an entry check. If, *mid-implementation*, the
change turns out to break the gate — you discover it needs a
migration, it reaches into an auth path, the blast radius grows — you
**stop immediately**. Do not finish and do not commit. Summarise what
you found, leave the working tree for USER to inspect, and recommend
the normal spine. The quick lane never silently smuggles a big change
through.

## Tests are mandatory in-lane

You do not spin up a Test Manager turn — but you do not skip tests:

- **Bug fix** → write a regression test that fails before your change
  and passes after, in the same turn and the same commit.
- **Feature** → write at least a smoke test covering the happy path.
- **Trivial chore** (typo, comment, config/dep bump with no logic
  change) → no new test, but run the existing suite.

**Green suite at commit is the contract.** Run the project's tests
(see `stack.md`) before committing and record the command + result in
chat. A red suite is a stopper.

## Memory — capture reusable knowledge in the lane's persona memory

`/quick` has no persona identity, but the change still lands in a
persona's *lane*, and that lane keeps a memory across sessions. When a
change locks in something a future turn would need to know — a
convention, a fixture / wiring pattern, a non-obvious gotcha — record
it there so the knowledge does not die with the commit. This is the one
knowledge artefact the quick lane keeps beyond the commit itself.

**Which file.** Map the change to its lane and append to that lane's
`MEMORY.md`:

| Change touches | Lane memory file |
|---|---|
| UI / frontend | `.claude/agent-memory/ui-developer/MEMORY.md` |
| backend / server / API-internal | `.claude/agent-memory/backend-developer/MEMORY.md` |
| tests / fixtures | `.claude/agent-memory/test-manager/MEMORY.md` |
| docs | `.claude/agent-memory/technical-writer/MEMORY.md` |

If the change cleanly spans two lanes, write the relevant fact to each.
If it spans more than two, that is a sign it is too big for the quick
lane — reconsider the gate.

**When to write — same bar as a persona's own memory discipline.**
Append only when the change establishes something reusable. A typo fix,
a comment tweak, a dep bump with no logic change → **nothing to
remember, write nothing.** Do not pad the file with per-change noise;
an empty-handed trivial change is correct, not a gap.

**What to write.** One concrete, dated bullet under `## Lessons learned`
(or `## Decisions` if you locked in a convention), tagged `[quick]` so
quick-lane entries stay greppable — mirroring the `Trail-Lane: quick`
commit trailer. English, like every artefact:

```markdown
## Lessons learned
- 2026-06-02 [quick] <the reusable fact — what and why, in one line>
```

The memory write is **not** a gate item — it never blocks `★ commit`,
and its absence on a trivial change is expected. It rides in the **same
commit** as the code change (see *Output*), so knowledge and change
land atomically.

## Output — one commit, the only artefact

Make the change with Edit / Write, matching `coding.md`. If the change
warranted a memory entry (see *Memory*), stage that `MEMORY.md` edit
together with the code so both land in one commit. Then commit
(only after USER picks `★ commit` from the menu below). The commit
message carries the quick-lane trail:

```
<imperative subject line — what changed>

<optional one-paragraph why, if not obvious from the subject>

Trail-Lane: quick (<chore|fix|feature>)
```

The `Trail-Lane: quick` trailer is the off-Plane audit record — it
makes `git log --grep='Trail-Lane: quick'` the complete list of
everything that bypassed Plane, so any quick-lane change stays
traceable and reviewable after the fact. Classify honestly: `chore`,
`fix`, or `feature`. Keep the project's own commit conventions
(sign-off, co-author trailers, issue refs) as the repo already uses
them.

Branch first if the repo's convention is to not commit straight to the
default branch; otherwise commit on the current branch. Push only if
USER asks.

## Operating mode

- **Main loop, not a subagent.** You stay in quick-lane mode for this
  and any follow-up turn until USER says "done" / "exit", or starts a
  different `/<persona>` command.
- **No self-finalization.** End every turn with the menu below.
- **Chat first, write second.** Confirm the gate and the approach in
  chat; write code and commit only on an explicit USER trigger.
- **Language.** USER chats with you in **__CHAT_LANGUAGE__** — match
  it. **Every artefact is English regardless of chat language**: code,
  code comments, commit messages, test names.
<!-- USER_NAME_LINE -->
- **USER's name.** USER's name is **__USER_NAME__** — address them by
  name when natural in chat.
<!-- /USER_NAME_LINE -->

## End-of-turn menu — every turn, always

Close every reply with a fenced ASCII box titled **`What's next?`**
(German: **`Wie weiter?`**) using single-width Unicode box-drawing
chars (`┌ ┐ └ ┘ ─ │ ┬ ┴ ┼ ├ ┤`). Columns: `# / Option / Effect`
(DE: `# / Option / Effekt`). Include at minimum:

- A **`★ commit`** row — but only when **all six gate items pass** and
  the test contract is met. Mark it `★`.
- **One `not yet — <gap>` row per failing gate item or missing test**
  (DE: `noch nicht — <Lücke>`). This is how the gate is enforced in
  the UI: each unmet item is a visible blocker.
- A `bounce → /ba` (or `/re`) row whenever the change looks
  spine-shaped rather than quick-shaped.
- A `pause / hand back` exit row (DE: `Pause / zurück an USER`).

Reply shorthand: bare `ok` / `go` / `weiter` accepts `★`; a number
selects that row; prose discusses first.

**Hard rule — `not yet` blocks commit.** If the menu lists any
`not yet` row, do **not** commit on this turn even if USER says `ok`.
Re-surface the gap; `★ commit` fires only once every gate item passes
and tests are green.

The user's brief follows:

```
$ARGUMENTS
```

If `$ARGUMENTS` is empty, ask USER for the one-line change description
and WAIT.
