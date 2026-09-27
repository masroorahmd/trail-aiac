---
description: Look up one Plane work-item and print its status card — identifier, description, state, assignee(s), and any children with their state and assignee. Read-only; does not change the persona in role.
argument-hint: "<work-item identifier, e.g. DEV-7> [full]"
---

<!-- TRAIL:KEEPS-ROLE -->

`/ticket` is a **read-only lookup**, not a persona and not a lane. It
makes exactly one Plane call and writes nothing — no comment, no
transition, no file. If a persona was in role before this command, it
still is afterwards; carry on in that role on USER's next turn.

## The call

Call `work_item_overview` once, with:

- `identifier` — the work-item ID in `$ARGUMENTS` (e.g. `DEV-7`).
  No ID given → ask USER for one and stop.
- `description_chars` — `0` if `$ARGUMENTS` contains `full`, else
  leave the default.
- `persona` — the persona in role in this session, if there is one
  (the plane-persona-guard denies any other name). With none in role,
  pick by the ID's project prefix from `.claude/config.yaml`
  `plane.projects`: the `hq` project → `general-manager`, the `mkt`
  project → `marketing-manager`, anything else → `business-analyst`.
  If Plane answers 403/404 and no persona is in role, retry once with
  the persona whose track owns that project, then report.

Do not follow up with `retrieve_work_item`, `list_comments` or other
reads unless USER asks — the card is the whole answer.

## The output

Print in **__CHAT_LANGUAGE__**, in this order and nothing else:

```
**<IDENTIFIER>** — <name>
**Status:** <state>  ·  **Assignee:** <names, or "—">

<description, as returned; if description_truncated, end with
"… (<shown>/<full_length> chars — `/ticket <ID> full` for all)">

**Children (<n>):**
| ID | Name | Status | Assignee |
|---|---|---|---|
| … |
```

Leave out the children block when there are none. Do not summarise,
interpret, or suggest next steps unless USER asks.
