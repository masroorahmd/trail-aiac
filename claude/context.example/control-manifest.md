# Control Manifest — non-negotiable guardrails

> Read by: Business Analyst (primary), Requirements Engineer, Software
> Architect, Security Reviewer, Test Manager — in full; Backend and UI
> Developer read *§Simplicity budget* and *§Architectural invariants*
> only, because those two bind a diff. Maintained by: USER directly
> (in chat with BA), or BA on USER's explicit request.
>
> Purpose: the constraints that apply to **every** Story without needing
> to be re-stated. When BA scopes a Story, every CM-N here is implicitly
> in *Out of scope* if violated, or in *Success criteria* if required.
> RE inherits these into the AC; SR uses them as a non-negotiable gate.
>
> If a Story conflicts with a CM-N, BA does NOT silently relax the
> constraint — they stop and ask USER whether to amend the manifest
> (and if so, dated under *Amendments* below) or reject the Story.

## ID convention

- Each guardrail gets a stable `CM-N` ID, append-only across the
  project's life. Once `CM-3` is allocated, you do not renumber.
- Removed guardrails stay in place as `~~CM-3~~ (removed
  YYYY-MM-DD — reason)` so prior Story comments that cite them
  remain readable.
- Cite the ID in any persona artefact that hangs on a guardrail
  (`AC-2 enforces CM-1`, `OOS-1 — CM-4 (no telemetry)`).

## Hard product constraints
<!-- The shape of the product itself — what it never is, never does,
     never targets. Examples (delete and replace with real ones):
     - CM-1: Self-hosted only. No SaaS variant, no managed cloud.
       _Rationale_: customer-segment trust requirement.
     - CM-2: Air-gapped supported, internet-facing forbidden.
       _Rationale_: security posture; inbound-from-public is a
       misconfiguration, not a deployment variant.
     - CM-3: No telemetry, no phone-home, no opt-in usage stats.
       _Rationale_: hard policy, not default. -->

## Compliance / legal
<!-- Legal frame agents must respect. Examples:
     - CM-10: GDPR — no PII in audit logs; counts not values.
     - CM-11: License = PolyForm Shield (provisional). All third-party
       contributions inventoried. No CLA gating until BIZ-N resolves.
     - CM-12: Trademark for "ProductName" filed in DE/EU before public
       launch (BIZ-N tracks). -->

## Quality floors
<!-- Minimum bars below which a Story cannot ship. Examples:
     - CM-20: Accessibility — WCAG 2.1 AA on every user-visible
       surface. UI Stories that lower this are rejected.
     - CM-21: Performance — pX latency budget on hot paths
       (define X, threshold, measurement method).
     - CM-22: Test coverage — every AC scenario is discharged by a
       named mechanism: a covering test, a structural guarantee that
       runs unattended and fails loudly (CI lint, type/schema/DB
       constraint), or explicit subsumption. Where a guarantee closes
       the whole class, it is preferred over enumerating instances.
       No merge with a red suite. -->

## Security non-negotiables
<!-- Things SR will hard-block on regardless of the Story's framing.
     Examples:
     - CM-30: No secrets, no auth tokens, no PII in logs or in cert/
       audit messages. PII canary regex sweep on every audit-emitting
       path.
     - CM-31: Auth events (login, role change, mfa enroll/revoke)
       always emit a structured audit record.
     - CM-32: Pre-launch security review by an external party for
       any release crossing the public-launch line. -->

## Architectural invariants
<!-- Cross-cutting design rules that survive Stories. Examples:
     - CM-40: Description-once on Plane work-item bodies — body
       written on creation, never edited; later annotation as
       comments.
     - CM-41: Structured typed errors via RFC 7807 across every API
       and web route.
     - CM-42: Single source of truth for cert/profile validation —
       Python matrix is canonical, JS validator mirrors it via
       shared fixture corpus, no drift. -->

## Out-of-scope corridor
<!-- Things this project **never** touches, kept here so BA does not
     spend cycles re-litigating them on each new idea. Examples:
     - CM-50: No mobile-native apps (web-only).
     - CM-51: No multi-tenant cloud deployment.
     - CM-52: No internal A/B framework (kill on every detection). -->

## Risk lanes
<!-- OPTIONAL — delete this section to run every Story at full depth.
     When present, BA routes each Story into a lane (recorded in the
     Story body's `## Lane` section), RE inverts its passthrough bias
     on standard- and light-lane Stories, SR may use its compact
     review mode, and a `light` Story skips stages outright.
     The escalation triggers are the safety valve: ANY trigger → full,
     regardless of labels, decided by whoever spots it. Examples:

     - CM-60: Lane policy. Default `full`. `standard` only when the
       Story is read-only / presentation-surface AND no CM-61 trigger
       fires. `light` only when CM-64 additionally holds. Label
       heuristic: #Security #Foundation → always full; #UI
       #Housekeeping → standard-eligible; #Housekeeping and #Chore
       that touch one module → light-eligible.
     - CM-61: Escalation triggers (any one → full). Each fires on
       INTRODUCING, CHANGING or NEWLY EXPOSING the thing named — not
       on reading or exercising it through a path the Story leaves
       unchanged: new/changed HTTP endpoint or auth boundary; newly
       reachable unauthenticated surface; crypto or key material
       introduced/changed/newly exposed; new subprocess invocation or
       changed arguments; new dependency (a patch/minor bump of a
       pinned one is not a trigger); changed persistent data layout or
       config schema; new/changed logging-event field or new
       PII-adjacent output. A genuinely borderline case IS a trigger.
       Keep this list precise: a trigger phrased as "anything touching
       X" fires on every Story in a codebase about X, and the lane
       stops carrying information.
     - CM-62: Lane semantics, and depth per slice. At Story level,
       `standard` = RE passthrough-expected + SA contract-only slice
       bodies; the path is unchanged, only the prose shrinks.
       `light` = the one lane that shortens the PATH: RE passthrough
       + SA skipped (no children — the Story itself is the
       work-item) + TW only on a real user-facing doc surface + RM
       ceremony trimmed. Every trimmed stage is logged as a SKIP-N in
       the handover comment. SR's review depth is decided PER CHILD
       from that child's own slice, not from the Story lane: a child
       firing no trigger may be reviewed compactly even on a `full`
       Story, and a child firing one gets full format even on a
       `standard` Story. Compact never skips a child, never omits the
       threat picture, never shortens a finding.
     - CM-63: What no lane may buy. SR always runs on a CM-3x
       surface (as a diff pass when there are no children); TM always
       runs where there is a runtime surface; the RM hand-back to
       USER always runs; and the Story is never skipped — taking work
       off the spine entirely is /quick's gate, not a lane's.
     - CM-64: `light` eligibility, on top of `standard`'s bar (all
       three): one module / one discipline; no design decision left
       (no new component, contract, data shape or dependency to
       choose); result checkable from the Story body alone. One
       uncertainty → `standard` at best. -->

## Simplicity budget
<!-- OPTIONAL — delete this section to leave solution size to each
     persona's own right-sizing judgement (the `plane-handover` skill,
     §Right-sizing). When present, these are project policy and outrank
     that judgement in both directions: a persona pushing against one
     cites the CM-N and asks USER rather than deciding alone. Unlike
     §Risk lanes, this section says nothing about which personas run —
     it bounds what they are allowed to *build*. Examples (delete and
     replace with real ones):

     - CM-70: A new runtime dependency needs USER's explicit approval,
       named in the Story before SA hands over. Dev-only and test-only
       dependencies do not.
     - CM-71: No abstraction below three real call sites. Interfaces,
       base classes, factories, wrappers and generic helpers arrive
       when the third caller does, not in anticipation of it.
     - CM-72: No new config key without a named operator who would
       change it and a stated default. A knob nobody turns is a branch
       everybody has to test.
     - CM-73: One Story ships one version. Phases the team can already
       see are `OOS-N` on this Story — not extra `SC-N`, not a fifth
       sub-work-item.
     - CM-74: Defensive code needs a reachable input. Guards, retries,
       fallbacks and try/except around code that cannot throw are
       written when an `AC-N`, an `EC-N` or an SR finding names the
       failure, not on principle. This never overrides a `CM-3x`.

     Note the asymmetry these encode on purpose: a lane or a review
     depth breaks toward MORE when the team is unsure, because the cost
     of under-scrutiny is a defect. Size breaks toward LESS, because
     the cost of over-building is paid by every Story after this one. -->

## Amendments
<!-- When USER amends the manifest mid-project, log the change here
     with the date, the CM-N affected, and the reason. Pattern:

     - 2026-MM-DD CM-7: tightened from "X" to "Y" — driven by
       Story DEV-N where the gap surfaced.

     This log is the project's record of "things the team used to be
     willing to do, and isn't anymore". Useful for onboarding new
     contributors and for audit recall. -->
