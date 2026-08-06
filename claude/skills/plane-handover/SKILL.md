---
name: plane-handover
description: Hand a Plane work item from the current persona to the next phase by combining a state transition, an assignee change, and a Definition-of-Done checklist comment in one consistent flow. Use whenever a persona finishes its slice of work on a ticket and the next persona must pick it up.
---

# plane-handover

Every cross-agent handover in this framework follows the same three-step
pattern. This skill encodes it once so every persona executes it
identically and the receiving persona always finds a verifiable
checklist instead of a handwritten "over to you".

## When to invoke

A persona invokes this skill when, and only when:

1. Its assigned slice of the work is complete (or it has consciously
   decided to bounce the ticket back — see *Kill criteria* in the persona
   prompt).
2. The next persona is unambiguously identified — either by the workflow
   (BA → RE → SA → SR direct chain) or by user dispatch (e.g. SR
   returning sub-work-items to USER).
3. A Definition-of-Done checklist exists for the slice that just
   finished. Without one, the receiver has nothing to verify against.
4. The persona's most recent end-of-turn menu (see the *End-of-turn
   menu* rule in every persona's Operating mode) offered
   `★ commit & hand over` as a ready row with **zero `not yet` rows
   present**, and USER explicitly accepted that row this turn
   (bare `ok` / `go` / `weiter`, the row number, or unambiguous
   prose to the same effect). A USER `ok` on a turn whose menu
   still carried any `not yet` row does NOT satisfy this — close
   or explicitly defer those gaps (logged in a comment), post a
   fresh menu, then commit on the next `ok`. The point of this
   gate is to make premature handovers structurally impossible.

If any of those four is false, **stop and ask the user** instead of
calling this skill.

## Before your first write: how Plane stores what you send

Two properties of the Plane API decide whether a handover is readable
or permanently broken. Both have burned personas across consumer
projects repeatedly, so read them once and apply them to *every*
`add_comment` and `create_work_item` call, not just to handovers.

**1. `comment_html` and `description_html` take REAL HTML.**
What you pass is rendered as markup, not as text.

- Send real tags: `<p>`, `<strong>`, `<ul><li>`, `<code>`, `<h3>`.
- Do **not** send Markdown. `**bold**` and `- item` are stored as
  literal asterisks and hyphens; Plane does not convert them.
- Do **not** entity-escape your own tags. `&lt;p&gt;` stores the
  entities and the comment displays `<p>` as visible text. This is
  the more common failure, because it looks like caution.
- Entity-escape **only** characters that must appear *as characters*
  in the rendered output — e.g. demonstrating `a &lt; b` or an XML
  snippet inside a `<code>` block.
- `<![CDATA[…]]>` does not work; it renders as literal text.

**1b. `description_html` is sanitized on write; `comment_html` is not.**
Since Plane v1.4.0 a work-item body passes through an HTML sanitizer
before it is stored, so the value you read back is *not* byte-identical
to the value you sent. Two normalizations happen to well-formed input:
the body is wrapped in a `<div>…</div>`, and `<a>` tags gain
`rel="noopener noreferrer"`. Comments skip the sanitizer entirely and
are still stored exactly as sent.

Every tag this skill tells you to use — `<p>`, `<strong>`, `<em>`,
`<code>`, `<pre>`, `<h3>`, `<ul>`, `<ol>`, `<li>`, `<a>`, `<table>` —
survives unchanged, as do entity escapes like `&lt;`. What the
sanitizer drops is script, event-handler attributes, and non-`http(s)`
/ `mailto` / `tel` link protocols, none of which belong in a handover.

The consequence that matters: **a `<div>` wrapper in the echo is not
corruption.** Do not "repair" it. Because a body is written once and
never edited (see the *Description-once* rule), a persona that reads
the echo, mistakes the wrapper for a mangled write, and creates a
replacement work item has produced a duplicate it cannot take back.

**2. There is no comment edit and no comment delete.** The persona
toolsets expose `add_comment` and nothing else. A mis-encoded comment
is **permanent** — the only repair is a second comment that opens by
superseding the first, and a human deleting the original in the Plane
UI. So: get the encoding right on the first call, then **read the
returned `comment_html` back**. If the echo contains `&lt;p&gt;`-style
escaping, you double-encoded — repost immediately with a one-line
supersede note rather than leaving it.

On a batch of work-items, post/create **one** first, inspect the echo,
and only then create the rest. Recovering a batch of mis-encoded
bodies is far more expensive than one extra round-trip.

## What the skill does

Three Plane API calls, in this order:

### 1. State transition + reassignment

Call the official Plane MCP `update_work_item` tool with both fields in
one request:

- `state`: the next ticket state in the spine
  (`Backlog → To Do → In Progress → In Review → Done`).
  Parent Stories: **BA leaves the new Story in `Backlog`**; USER
  triages it to `To Do`; **RE moves it to `In Progress` on first
  pickup** and the parent stays there through SA decomposition and
  the entire sub-work-item phase; USER closes it as `Done`. Agents
  never close tickets and never move a parent into `To Do`.
  Sub-work-items use the full spine. **Same-session carve-out:**
  when USER's slash-command (`/re`, `/sa`, `/bd`, …) directly
  triggers a persona to pick up a work-item in the same chat
  session — i.e. USER's invocation *is* the triage signal — that
  persona may skip `To Do` and go `Backlog → In Progress` in one
  transition. Record the skip explicitly in the DoD handover
  comment so the audit trail explains why `To Do` was bypassed.
- `assignee`: the next persona's workspace user, or USER for the
  Review handover.

**Do not trust the PATCH echo.** `update_work_item` can answer
HTTP 200 while its response body still carries the *old* state. The
write usually landed anyway — but the echo is not evidence of it.
Whenever the transition itself is the thing you are about to report
(a handover, a close, a state you assert in a comment), confirm it
with an independent `retrieve_work_item` call and report *that*
reading. Never re-issue the PATCH on the strength of a stale echo; you
will not learn anything new and you may fight a transition that
already succeeded.

**An outage is not a bad request.** If a Plane tool answers *"Plane is
unreachable or restarting"*, the MCP has already retried it with
backoff for ~45s — the call was well-formed and the instance is down
(upgrade, restart, backup window). Do not vary the arguments, do not
call it again in a loop, and do not fabricate the handover as though
it landed. Tell USER Plane is unavailable, say which step is pending,
and stop; the same call will work unchanged once Plane is back. If the
error adds *"may or may not have been applied"*, a write broke
mid-flight: `retrieve_work_item` (or `list_comments`) first to see
whether it landed, and only then decide whether to repeat it.

### 2. DoD handover comment

Call the `plane` MCP server's `<persona_snake>__add_comment` tool on
the same work item, posting a comment shaped exactly like this — and
note that this is the **wire format**, real HTML, not a Markdown
sketch of one:

```html
<p><strong>Handover: &lt;FROM-PERSONA&gt; → &lt;TO-PERSONA&gt;</strong></p>

<p>&lt;one-sentence rationale — why this is ready / what was decided&gt;</p>

<h3>Definition of Done (this slice)</h3>
<ul>
  <li>[x] &lt;criterion 1 — verifiable by the receiver&gt;</li>
  <li>[x] &lt;criterion 2&gt;</li>
  <li>[x] &lt;criterion N&gt;</li>
</ul>

<h3>For the receiver</h3>
<ul>
  <li>&lt;pointer to artifacts: work-item IDs, comment IDs, file paths in the project repo&gt;</li>
  <li>&lt;known unknowns the receiver should be aware of&gt;</li>
</ul>
```

The `&lt;…&gt;` above are the *placeholders* — angle brackets that
must render as visible characters, which is exactly the case where
entity-escaping is correct. Your actual content replaces them and
carries no escaping. Every other template in the persona prompts
follows the same convention: the fence shows the **structure**, and it
goes on the wire as HTML.

The DoD bullets must be **verifiable by the receiver from the ticket
alone** — no reliance on shared chat memory or assumed context. Every
artifact referenced should be locatable by ID (parent Story
`<DEV-N>`, sub-work-item `<DEV-N.module>`) or by repo path
(`docs/foo.md`, `app/services/bar.py`).

**Cite upstream by ID. Never restate its reasoning.** If BA wrote why
`OOS-1` is forbidden, or SR wrote why a finding is medium, the receiver
reads it *there*. Write `OOS-1 stands` or `see SR's F2` — not a
paragraph reproducing the argument. A reason already written down once
in this ticket is a reference, not content, and reproducing it makes
the ticket longer without making it truer.

There is exactly one exception, and it is the point of the handover:
when you **disagree** with upstream reasoning, or measured it and found
it stale or wrong, say so in full. That is new information. Agreement
is a citation; disagreement is prose.

This rule exists because of a measured failure mode — three personas in
a row each re-reporting the same rotted line number, the same forbidden
remedy, the same "do not relitigate" list, in a ticket where each of
those facts was true exactly once. Report a fact at the first persona
that established it. Afterwards it is `see RE's note`.

### 3. Update agent memory

Append a one-line entry to the calling persona's `MEMORY.md` under
*Cross-agent handovers (recent)*:

```markdown
- YYYY-MM-DD <TICKET-ID> → <to-persona>: <one-line summary>
```

Date must be ISO (YYYY-MM-DD), not relative.

## Stopping conditions

- If `update_work_item` fails (e.g. invalid state for the project's
  workflow), do not retry blindly. Stop, report the failure to the
  user, and ask whether to adjust the ticket workflow or the
  transition target.
- If the next persona is `USER`, the comment's "For the receiver"
  section must include a *concrete next action* — not "please
  review", but "decide whether to merge spec X or re-scope to Y".
  USER handovers without an actionable ask are the failure mode this
  framework exists to prevent.

## What this skill does NOT do

- It does **not** create the DoD checklist. The persona authored that
  before calling this skill.
- It does **not** close tickets. Per the workflow model, agents never
  set state to `Done` — neither parent nor sub-work-items. USER
  closes.
- It does **not** create work-items. Use your own
  `plane__<persona_snake>__create_work_item` for that. Note that
  this framework does not use Plane pages — every artefact lives
  either in a work-item body (written once at creation) or in a
  comment.
