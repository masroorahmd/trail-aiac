# Workflow: security finding (post-ship)

**Trigger:** SR finds a security issue in already-shipped code,
either during a routine audit or while reviewing an unrelated
Story's slices. The issue is not localized to one Story — the
remediation may cross several.

When the finding surfaces *during* an in-flight Story (i.e. SR
flags it as part of `/sr review DEV-N`), follow the greenfield
workflow's SR step. This workflow is for post-ship findings only.

## Persona path

1. **SR posts the finding to the most-relevant Plane Story or
   directly into a new SR-authored Story** in the dev project.
   The body shape: what was found, where (file path / call site),
   the violated `CM-N` from `control-manifest.md` (or the missing
   one — see *Notable deviations*), the blast radius, and the
   recommended fix shape. SR does not implement.

2. **`/ba reframe DEV-N`** (when SR opened the Story) or
   **`/ba <SR-finding brief>`** (when there's no Story yet) — BA
   converts SR's finding into a remediation Story. Body's *Problem*
   section names the finding plainly: what's broken, who's at risk,
   why-now. *Success criteria* state the remediated end-state.

3. **`/re refine DEV-N`** — RE writes the AC. Two scenarios are
   structurally load-bearing:
   - **The exploit** (`AC-1`): Given the vulnerable state, When
     the attacker action fires, Then the system *currently* leaks
     X / accepts Y / fails to enforce Z. This becomes the
     would-fail-before test that anchors the regression guard.
   - **The fix** (`AC-2`): Given the same state, When the same
     action fires, Then the system rejects / blocks / audits.
   Edge cases focus on near-misses: variants of the exploit, the
   defense-in-depth surfaces (Pydantic validation, middleware,
   handler).

4. **`/sa decompose DEV-N`** — SA decomposes against the
   remediation shape. Security fixes often span backend +
   testing only; UI rarely changes. The testing sub-work-item
   gets explicit framing as *exploit-anchored regression guard*.

5. **`/sr review DEV-N`** — SR re-reviews their own finding
   against the AC and SA's slices. Confirms the fix shape addresses
   the root cause, not just the surface symptom.

6. **`/bd implement DEV-N+1`** — BD implements the fix. Production
   code carries a one-line comment citing the Story ID *only if*
   the fix is non-obvious from the change itself — otherwise the
   commit message + PR description hold the why.

7. **`/tm test DEV-N+2`** — TM writes the exploit-anchored test
   first (must fail without BD's fix), then the regression-guard.
   Both reference `AC-1` / `AC-2` by ID. PII canary discipline
   from `CM-30` applies if the fix touches audit logging.

8. **`/rm release`** — RM cuts a release. For high-severity
   findings, the release line is a coordinated security release
   (CVE if applicable, advisory in the changelog).

## Skip / consolidate

- **TW typically minimal.** A line in the security advisory and
  changelog. The doc-only sub-work-item is often inlined into RM's
  release work.
- **UD usually skipped.** Most server-side security findings
  don't surface on the UI.

## Notable deviations from the default

- **Pre-disclosure discipline.** If the finding is exploitable in
  the wild and the project has a published security policy with a
  disclosure window, USER may keep the Story body terse during the
  embargo — concrete file paths + call sites stay in private
  comments until disclosure date. The Plane work-item is still the
  single source of truth, but body text is sanitized.
- **Manifest amendment is common.** A finding often surfaces a gap
  in `control-manifest.md` — there was no `CM-N` covering the
  invariant that was violated. After remediation, BA appends to the
  manifest's *Amendments* section with a new `CM-N` and the dated
  reason. This closes the loop: the next Story that would have
  re-introduced the bug is rejected at framing time.
- **TM's exploit-anchored test is non-negotiable.** Without it, the
  regression guard does not actually guard against the original bug
  — it guards against *some* bug. The exploit test is the audit
  signal that the fix addresses the finding.

## Example trigger

```
> /sr "Found while reviewing DEV-66 slices: web routes that depend on require_auth_web emit anonymous audit records under load, even when the user is signed in. Repro path / blast radius / recommended fix shape posted as comment on a fresh dev-project Story."
```
