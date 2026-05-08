# Workflow: bug fix

**Trigger:** A regression or defect in already-shipped code. The
behaviour is wrong, not missing — there is no new feature surface
to design.

## Persona path

1. **`/ba <bug description>`** — BA scopes the bug into a Plane
   Story. The body shape stays the same as a feature (Problem /
   Target users / Success criteria / In scope / Out of scope) but
   *Success criteria* are usually one or two `SC-N` items
   describing the correct behaviour, and *In scope* explicitly
   names the failing path.

2. **`/re refine DEV-N`** — RE writes the AC. Bug fixes typically
   produce 2–4 Gherkin scenarios:
   - The reproduction (`AC-1`: Given the bug repro state, When the
     trigger fires, Then the symptom appears) — captures the
     regression.
   - The fix (`AC-2`: Given the same state, When the trigger fires,
     Then the *correct* outcome).
   - One or two regression-guard scenarios for the closest
     neighbours that share the failing code path.
   *Edge cases* are the high-value section here — what *almost*
   triggered the bug but didn't.

3. **`/sa decompose DEV-N`** — Often a single sub-work-item plus a
   testing slice. SA may inline the documentation update into the
   implementor slice (no separate TW work) when the user-facing
   change is a one-line release-notes entry.

4. **`/sr review DEV-N`** — SR is *not* skipped on bug fixes,
   especially when the bug touched an auth path, an audit-emitting
   call site, or anything cited under `control-manifest.md`'s
   *Security non-negotiables*. Quick is fine; absent is not.

5. **`/bd implement` or `/ud implement`** — Single implementor on
   most bug fixes. Implementation notes call out the root cause,
   not just the change.

6. **`/tm test`** — TM writes the regression-guard tests. The
   reproduction scenario from `AC-1` becomes a *would-fail-before*
   test; the fix scenario becomes a *passes-after* test. Together
   they prevent the bug from coming back.

## Skip / consolidate

- **TW often skipped.** Most bug fixes need only a one-line
  changelog entry, which RM picks up.
- **SA may be very thin.** When the cause is obvious and the fix
  is local, SA can produce a single sub-work-item with a
  paragraph-level architecture note — no full module spread.

## Notable deviations from the default

- **AC scenarios are repro-driven, not feature-driven.** Resist the
  urge to list the bug under *Out of scope* and write only the
  fix scenario — without the repro AC, the regression-guard test
  has no anchor.
- **Negative-path tests are load-bearing.** Bug fixes are where
  exclusion testing earns its keep. TM's *Negative-path test for
  every exclusion criterion* rule is hard here.
- **Cite the issue number / parent ticket if the bug came from a
  user report.** Story body's Problem section names the report so
  future readers can trace the chain back.

## Example trigger

```
> /ba "BUG: Issue list shows revoked certificates in the count when the dashboard 'Active' tile is clicked, even though the detail page filters them out"
```
