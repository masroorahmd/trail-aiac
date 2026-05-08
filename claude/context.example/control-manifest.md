# Control Manifest — non-negotiable guardrails

> Read by: Business Analyst (primary), Requirements Engineer, Software
> Architect, Security Reviewer, Test Manager. Maintained by: USER
> directly (in chat with BA), or BA on USER's explicit request.
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
     - CM-22: Test coverage — every AC scenario has a covering
       test; no merge with red suite. -->

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

## Amendments
<!-- When USER amends the manifest mid-project, log the change here
     with the date, the CM-N affected, and the reason. Pattern:

     - 2026-MM-DD CM-7: tightened from "X" to "Y" — driven by
       Story DEV-N where the gap surfaced.

     This log is the project's record of "things the team used to be
     willing to do, and isn't anymore". Useful for onboarding new
     contributors and for audit recall. -->
