---
name: ui-mockup
description: Run a pre-ticket design session with USER — build clickable HTML mocks in the project's own CSS, settle the screens, states and flow at the picture instead of in prose, and freeze the result as a numbered decision record the Story is then written against. Use under the `/mock` lane (UI Developer, no Plane, no production code), and read it again at implementation time when a Story names a `design/<slug>/` folder.
---

# ui-mockup

The spine from BA to SR is prose about the *what*. The first artefact
a human can actually look at used to be shipped code — which is why
layout, wording and flow got decided by whoever implemented them, and
why USER's first chance to disagree arrived at `In Review`, when
disagreeing costs a rework round.

This skill moves that decision to the front. USER and the UI Developer
build the screens as **static HTML in the project's real CSS**, walk
them in a browser, and argue about them while changing them is free.
What comes out is not a picture — it is a **numbered decision record**
that BA writes the Story against, RE derives criteria from, SA slices
around, and UD is later measured against.

**The session touches Plane not at all.** No work-item, no comment, no
state. It happens before a ticket exists, and its whole output is
files in the project repo.

## Where the mock lives

`design/<slug>/` at the **repo root** — git-tracked, and deliberately
not under `.claude/`, which some consumers gitignore whole. SA and UD
read this folder weeks later; it has to travel with the code.

`<slug>` is short kebab-case naming the feature, not the ticket:
`design/smtp-settings/`, `design/invite-flow/`. The folder predates
the Story, so it is never named after one — `DESIGN.md` records the
Story ID once BA has created it.

```
design/<slug>/
├── DESIGN.md                  the decision record — the actual deliverable
├── index.html                 click-through: every screen/state, one link each
├── <screen>--<state>.html     one file per screen × state
└── assets/                    only if the mock genuinely needs one
```

`index.html` is what USER opens. Every link carries a one-line label
saying which question that screen answers, so the walk has an order.

### `DESIGN.md`

```markdown
# <Feature> — design record

**Status**: draft | agreed (YYYY-MM-DD)
**Story**: <DEV-N, filled in after BA creates it — or "not yet filed">

## Problem
<one paragraph: what USER is trying to make possible>

## Screens
- `<screen>` — <what it is for>

## States
<the full matrix, one line each: screen × state. Empty, loading,
error, permission-denied, long content, narrow viewport. A state
listed here and not mocked says so, with the reason.>

## Flow
<how a user moves between the screens; where the flow branches>

## Decisions
**D-1**: <the decision, stated so it can be checked against a
rendered page> — <why, in one line>
**D-2**: …

## Rejected
**R-1**: <what we tried and dropped> — <why>

## Open
<questions the mock did not settle and who owns them — or "none">

## Rules for ui.md
<every decision above that is a project-wide convention rather than
a one-off for this feature. UD copies these into
`.claude/context/ui.md` at freeze; this section is the shortlist,
not a second home.>
```

**`D-N` is an ID like `SC-N` and `AC-N`.** It is what makes the mock
citable: BA's body points at it, SA's slice quotes it, UD's handover
reports against it. A decision without a `D-N` is a conversation, not
a contract.

## Fidelity — the project's real CSS, or the mock lies

Build the mocks against the project's actual stylesheet, tokens and
component classes. Read at least one shipped template in the same area
first and name the pattern you are reusing.

- **No new design system, no new dependency, not even in a mock.** The
  same rule as implementation — a mock that introduces one has already
  made a decision that is SA's.
- **A component the mock needs and the project does not have** is a
  `D-N` with the cost named. That is exactly the fact SA needs before
  slicing, and the fact that gets lost when the mock is a picture.
- **Static only.** Hard-coded content, no build step, no fetch, no
  framework runtime. Fake a state by writing the markup of that state,
  not by scripting the transition.
- The markup is meant to be **liftable**: at implementation time UD
  should be able to take it into the real template rather than rebuild
  it from a screenshot.

## The session loop

1. **Read before drawing.** `.claude/context/ui.md` (the conventions
   already locked in), `.claude/context/product.md`, and one or two
   real screens in the area. Say in chat which existing pattern the
   mock will extend.

2. **Enumerate screens × states *before* the first file.** Write the
   matrix into `DESIGN.md`'s *States* section and show it to USER.
   This step is not decoration: the cells nobody names are where both
   the layout bugs and the missing business rules live, and naming
   them here is what later lets RE turn each one into an `AC-N`.

3. **Mock the smallest set that answers the open questions.** Not
   every cell of the matrix needs a file — the ones where USER's
   answer is not obvious do. Cells you deliberately skip are listed
   with the reason.

4. **Boot it and hand USER the URL.** Serve `design/<slug>/` on a
   **free port** via the `browser-review` skill's rules (never the
   project's default port, never kill a process holding one). USER
   walks the click-through themselves — this is the whole point of the
   lane, so do not substitute your own screenshots for their eyes.
   Your own browser pass still applies to what you built: contrast
   computed not inferred, and the capture verified to cover what you
   are judging from.

5. **Every correction lands in exactly one of three places.** The mock
   file (it was a drawing mistake), a `D-N` in *Decisions* (it was a
   choice), or *Rules for ui.md* (it is a convention that outlives
   this feature). A correction that lands nowhere is the failure this
   lane exists to prevent — you will rediscover it at `In Review`.

6. **Iterate until USER says the mock is the thing they want.** Round
   count is USER's call, not yours. What ends the session is USER's
   acceptance, never your judgement that it is good enough.

7. **Freeze.** `Status: agreed (YYYY-MM-DD)`, *Open* emptied or each
   entry given an owner, *Rules for ui.md* copied into
   `.claude/context/ui.md`, and the folder committed. Then hand to BA.

## Handing over to BA

The session ends with a short block in chat that USER carries into
`/ba` — the mock lane writes nothing to Plane, so this is the seam:

```text
Design session complete — design/<slug>/

- Problem: <one line>
- Screens: <list>
- Decisions: D-1 … D-n (see DESIGN.md)
- Behaviour the mock pinned down: <the D-N entries that are rules,
  not looks — these are what RE turns into AC scenarios>
- Still open for BA/RE: <list, or "none">
- New component / dependency the design implies: <named, or "none">
```

BA's Story body then carries a `## Design` section naming the folder
and the `D-N` range. From there the folder is on the ticket, and
every downstream persona can find it.

## How the folder is read downstream

- **RE** reads `DESIGN.md`'s *States* and *Decisions* — the behaviour —
  and turns each state into an `AC-N` scenario. RE does **not** read
  the HTML: layout is not RE's lane, and the matrix is the part that
  carries testable behaviour.
- **SA** treats the folder as settled for the frontend slice. The
  slice body cites `D-N` instead of re-deciding layout, and any new
  component the design implies is named under *Expected shape*.
- **UD** opens the mock before writing code, and diffs the built page
  against it at the visual gate. Every deviation is named in the
  Implementation notes with its reason — a deviation is allowed, a
  silent one is not.

## Drift after the Story exists

The mock is a repo file, not a Plane body, so **description-once does
not apply to it** and it stays current. When implementation changes
the agreed design:

1. Update the mock file and the affected `D-N`.
2. Add a `**Superseded**: D-N — <what changed and why>` line under
   *Decisions*.
3. Say it in the Implementation notes comment on the sub-work-item.

The rule is that the folder never disagrees with what shipped. A stale
mock is worse than none: the next Story is designed against it.

## Right-sizing

Every screen, state and `D-N` traces to a question USER actually
raised, or it does not go in the folder. A mock set that renders every
theoretical permutation costs the same review attention as the code
would have, which defeats the purpose of moving the decision earlier.
Ties about *risk* break toward mocking the extra state; ties about
*volume* break toward fewer files. Full rule: the `plane-handover`
skill, *Right-sizing*.

## What this lane is not

- **Not an implementation lane.** No production code, no test, no
  commit outside `design/<slug>/`. The moment the session wants to
  touch the real template, it is over — freeze and go to `/ba`.
- **Not a substitute for acceptance criteria.** The mock pins the
  picture and the states; RE still writes the criteria TM tests
  against.
- **Not the place for an architecture decision.** If settling the
  design requires choosing a backend contract, a data model or a new
  dependency, that is SA's. Record it as *Open* with SA named, and
  keep going on what does not depend on it.
