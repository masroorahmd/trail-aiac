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

If any of those three is false, **stop and ask the user** instead of
calling this skill.

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
  Sub-work-items use the full spine.
- `assignee`: the next persona's workspace user, or USER for the
  Review handover.

### 2. DoD handover comment

Call the supplementary MCP (`plane-extras-mcp`) `add_comment` tool on
the same work item, posting a comment shaped exactly like:

```markdown
**Handover: <FROM-PERSONA> → <TO-PERSONA>**

<one-sentence rationale — why this is ready / what was decided>

### Definition of Done (this slice)
- [x] <criterion 1 — verifiable by the receiver>
- [x] <criterion 2>
- [x] <criterion N>

### For the receiver
- <pointer to artifacts: work-item IDs, comment IDs, file paths in the project repo>
- <known unknowns the receiver should be aware of>
```

The DoD bullets must be **verifiable by the receiver from the ticket
alone** — no reliance on shared chat memory or assumed context. Every
artifact referenced should be locatable by ID (parent Story
`<DEV-N>`, sub-work-item `<DEV-N.module>`) or by repo path
(`docs/foo.md`, `app/services/bar.py`).

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
- It does **not** create work-items. Use the official Plane MCP
  `create_work_item` for that. Note that this framework does not use
  Plane pages — every artefact lives either in a work-item body
  (written once at creation) or in a comment.
