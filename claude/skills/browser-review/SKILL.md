---
name: browser-review
description: Drive a running app in a real browser to verify what actually shipped — choosing a driver, spending evidence cheaply, and keeping the report honest. Use whenever a persona has to look at or click through the app instead of reading its code — the UI Developer's visual verification gate, and the Test Manager's review run (interactive, or the unattended one under /autopilot).
---

# browser-review

A green suite proves the code does what its assertions say. It proves
nothing about what a person sees, and nothing about the paths no
assertion walks. Two persona behaviours close that gap by opening the
app instead of reading it:

- the **UI Developer's** visual verification gate — every route the
  change touched, loaded and looked at before handover;
- the **Test Manager's** *review run* — driving the Story's *Review
  steps (test-manager)* comment step by step, interactively while USER
  watches or unattended under `/autopilot`.

This skill is the part they share: which driver to pick, how to boot
the app without wrecking someone's dev server, how much evidence a
question actually needs, and what never to do to a browser you are
automating. Your persona prompt owns everything above that — what to
look at, what counts as a finding, and where the finding goes.

## Pick a driver — and name it before you start

The ranking depends on whether a human is watching. Work down the list
and take the first that fits; say in chat (attended) or in your report
(unattended) which one you picked. Never silently substitute one for
another: "I ran it" means nothing if the reader expected a live view
and didn't get one, or expected a real browser and got a curl.

**Attended (interactive persona turn) — fastest *watchable* first:**

1. **The project's own browser harness, run headed.** It already has
   the fixtures, the auth and a bootable server. For a review run,
   encode one test function **per numbered step**, named for it
   (`test_step_07_revoked_cert_disappears`), and run it with
   `--headed --slowmo <ms>` (or the harness equivalent). That is what
   makes a run both watchable and fast: the window shows the clicks
   while `-v` prints a live `PASSED` / `FAILED` per step, and nothing
   round-trips through a model between steps. Turn tracing and video on.
2. **A DOM / accessibility-tree browser MCP** (Playwright MCP, Chrome
   DevTools MCP) when the steps need judgement a fixed script cannot
   encode. Element refs instead of coordinates, so clicks don't miss.
3. **A screenshot-driven browser MCP** (Claude in Chrome) last. Every
   step is a full image through the model — an order of magnitude
   slower per step — so reach for it only when nothing above fits, and
   batch actions where the tool allows.

**Unattended (under `/autopilot`) — fastest *reliable* first.** Nobody
is watching, so "watchable" buys nothing and headless is simply faster:

1. **The project's own harness, headless**, one test per numbered step,
   tracing and video on so the run still leaves replayable evidence.
2. **A DOM / accessibility-tree browser MCP.**
3. **Not** a screenshot-driven, human-session-bound driver. Claude in
   Chrome needs a live browser window and per-site permission grants
   that no unattended run can supply; treat it as unavailable.

**When no driver is available at all, do not improvise and do not
pretend.** Say so plainly, report the steps as un-driven under *What
could not be verified* / *Not verified*, and let the steps stand as the
human's checklist. Missing a browser is never a reason to stop a run,
and never a reason to report a step you did not execute.

## Booting the app

- Run the *Setup* commands **verbatim** as the review steps or
  `stack.md` give them. A setup command that fails is finding zero —
  the steps are wrong or the branch does not build — and it is reported
  before anything else, not worked around.
- If you boot a server yourself: **pick a free port, never the
  project's default**, and **never kill a process already holding
  one**. A colleague or USER is very likely using it.
- Never enter credentials that were not handed to you for this run, and
  never point a run at a production or shared environment.

## One question, one piece of evidence

Before you act, decide what single observation settles the question —
then take *that* one and stop.

- **Perceive as cheaply as the question allows.** Text, the
  accessibility tree, or a scoped DOM probe answers "is the value
  right, did the row disappear, is the error shown" at a fraction of a
  screenshot's cost. Reserve screenshots for questions that are
  genuinely *visual* — layout, contrast, alignment, "does it look
  broken".
- **A resolving selector is not a visible element.** It proves the node
  exists, not that a human can see or read it. When the expectation is
  visual, the screenshot **is** the right evidence — not an addition to
  the probe.
- **Check the capture is what you think it is.** A full-viewport
  screenshot that silently returns the top-left fraction at HiDPI looks
  like a badly zoomed page — enough to make you "fix" a layout that was
  fine. Confirm the image covers the region you meant before drawing
  any conclusion from it.
- **Believe the page over the probe.** When a probe returns an empty or
  surprising result, look at the page before you accept it. A scoped
  DOM query has reported an element absent from a page that visibly
  carries it.
- **Belt-and-braces is not rigour.** A probe followed by a confirming
  screenshot, or a screenshot followed by a confirming probe, is the
  same answer bought twice.

## Measure what the eye cannot

Contrast ratios get **computed**, never inferred — parity with a
shipped sibling proves nothing if the sibling is itself below AA. Same
for overflow (`scrollWidth > clientWidth`) and element geometry. And
attribute a page-level overflow before claiming it is yours: remove
your element, re-measure, compare. Measurements complement the
screenshot; they never replace it.

## Never trigger a native dialog

`alert` / `confirm` / `prompt` and browser modals freeze the automation
channel — no further command gets through, and the session is lost, not
merely delayed. Avoid the controls that raise them. If a step genuinely
requires one: attended, stop and ask USER to dismiss it by hand, then
resume; unattended, do not trigger it at all — record the step as
blocked on a native dialog.

## Destructive actions

Deleting data, sending mail, charging anything, or writing to a shared
or production system:

- **Attended** — ask USER first, naming what the action will do and to
  which environment, and wait for an explicit go.
- **Unattended** — never execute it. There is no one to ask, so the
  step is `SKIPPED (destructive — needs USER)` and it goes in the
  report's *Not verified* section. An unattended run that deletes
  something to satisfy a checklist is the worst outcome this rule
  exists to prevent.

## The free finding channel: console and network

Every route you load hands you two signals for free. Collect them and
read them at the end of each route or step:

- **Console** — uncaught exceptions, unhandled rejections, React/Vue
  warnings, CSP violations, 404s on assets.
- **Network** — any 4xx or 5xx the page fired, and requests that hang.

**Any of these is a finding on its own**, even when no step asserted it
and every step passed. A page that renders correctly while throwing on
every keystroke is broken, and this is the channel that sees it. Filter
noise that the project already tolerates (say so when you filter), and
attribute the rest like any other finding. Where the driver cannot
expose console or network (a harness assertion, a text-only probe), say
so rather than reporting a clean sweep you never took.

## Evidence, and where it lands

- Prefer the artefact directory the harness already writes to
  (`test-results/`, `playwright-report/`, …) — it is normally
  gitignored already. If you have to invent a path, use
  `.claude/review-runs/<WORK-ITEM-ID>/`.
- **Evidence is never committed.** Traces, videos and screenshots are
  run output, not deliverables; under `/autopilot`, say in your verdict
  `NOTES` where they landed so the orchestrator can keep them out of
  the commit.
- **A spec you wrote *is* a deliverable.** When you encoded the review
  steps as a test file, that file stays in the tree, gets committed
  with the change, and is named in your report — a review run that
  leaves a replayable spec behind pays for itself the second time it is
  needed.

## Never retry for a greener result

A check that fails and then passes on a retry is **flaky**, and flaky
is a finding: record it as `FAIL (flaky: passed on attempt N)` with
both observations. Repetition is legitimate in exactly one place —
after a failure, to narrow the repro — and it is bounded: stop the
moment you can state the trigger, or after a handful of attempts, and
write down what you tried. You never re-run a completed run to get a
better number, and you never route around a failure to make a later
check pass.
