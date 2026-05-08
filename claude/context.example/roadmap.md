# Roadmap — agent context

> Read by: Venture Advisor (primary), Business Analyst, Release Manager.
> Maintained by: Venture Advisor.
>
> Purpose: the planned arc of the product. Agents use this to place new
> work on the timeline, to recognise when a request belongs to a later
> phase, and — when USER asks the BA to pull from the roadmap — to copy
> a Story's priority and labels straight into Plane.

## Entry format

Each roadmap item is one bullet:

```
- [priority] #Label1 #Label2 — One-line description
```

- `priority` ∈ {`urgent`, `high`, `medium`, `low`, `none`}. Maps
  one-to-one to Plane's priority field. `urgent` is reserved for
  ad-hoc emergencies and should rarely appear in the roadmap.
- `#Label1 #Label2 …` — one or more labels from the project's
  Story-label taxonomy (whatever set `plane_bootstrap` seeded for
  this project — see `doc/WORKFLOW.md` → "Story labels"). The BA
  copies these verbatim onto the Plane Story.
- Description: one sentence, imperative voice. The BA refines this
  into the final Story title.

The section (`Now` / `Next` / `Later`) is a time horizon for human
context only — it does not influence priority, which lives in the
`[priority]` tag.

## Now
<!-- Items currently being scoped or actively worked. Highest-priority
     entries here are what the BA reaches for when USER says "pull the
     next Story". -->

- [high] #Foundation #Distribution — Self-installing CLI bundling install + kickoff + Plane provisioning

## Next
<!-- Items committed for the near term, not yet started. -->

- [medium] #UI — Avatar gallery polish for the README

## Later
<!-- Themes, not commitments. Priority may be `none` until the item is
     promoted into Next. -->

- [low] #Integrations — Slack/Discord notifications for cross-agent handoffs

## Recently shipped
<!-- The last 2–3 phases or releases, with one-line summaries. Helps
     newer agents see momentum and recent decisions. -->

## Explicit non-goals (this period)
<!-- Things actively deferred. Saves rehashing in tickets. -->
