# Workflow: greenfield feature

**Trigger:** USER has a new feature idea touching at least one
user-visible surface. No existing Story or sub-work-item covers it.

This is the default. Every other workflow is a deviation from this.

## Persona path

1. **`/ba <brief>`** — BA scopes the idea against `control-manifest.md`
   and the roadmap, drafts the parent Story body
   (Problem / Target users / Success criteria / In scope / Out of scope
   with stable `SC-N` / `IS-N` / `OOS-N` IDs). Story enters Plane in
   state `Backlog`, assignee = `requirements-engineer`.

2. **USER triages.** When ready to work, USER moves the Story
   `Backlog → To Do`.

3. **`/re refine DEV-N`** — RE moves the Story `To Do → In Progress`,
   posts the AC comment with stable `AC-N` / `UF-N` / `EC-N` / `NFR-N`
   IDs (or passthroughs when BA's spec is already AC-quality). RE may
   spawn `edge-case-hunter` via the `Agent` tool to enumerate edge
   cases before drafting. Hands off to SA.

4. **`/sa decompose DEV-N`** — SA decomposes the Story into 1–4
   sub-work-items in `backend / frontend / testing / documentation`
   modules. Each sub-work-item body carries that module's architecture
   slice. Sub-work-items enter Plane in state `Todo`, assignees =
   the relevant implementor / TM / TW.

5. **`/sr review DEV-N`** — SR posts findings as comments on the
   relevant sub-work-items. Hard-block findings cite the violated
   `CM-N` from the control-manifest.

6. **Implementors work in parallel.** USER dispatches each
   sub-work-item:
   - `/bd implement DEV-N+1` (backend slice)
   - `/ud implement DEV-N+2` (frontend slice)
   Each moves their sub-work-item `Todo → In Progress` on pickup,
   posts Implementation notes on completion, sets state `In Review`,
   assignee = USER (or TM for the testing slice).

7. **`/tm test DEV-N+3`** — TM picks up the testing sub-work-item.
   Per the persona's *UI-test scope* check, TM explicitly assesses
   whether AC scenarios touch user-visible surfaces and surfaces
   the decision before drafting tests. May spawn `ui-test-writer`
   workers in parallel for non-trivial UI surfaces.

8. **`/tw document DEV-N+4`** — TW updates user-facing docs
   (README, changelog, CLI help, in-app onboarding).

9. **`/rm release`** — RM cuts the release once all sub-work-items
   are in `In Review` and USER has signed off.

## Skip / consolidate

- **No frontend?** SA omits the UI sub-work-item; UD never invoked.
- **No new docs?** SA omits the documentation sub-work-item; TW
  never invoked. Most internal-only refactors skip TW.
- **Trivial scope?** SA can decompose into a single combined
  sub-work-item (one implementor handles backend+frontend), but
  this is the exception — separation usually pays for itself in
  parallel-pickup speed.

## Notable deviations from the default

- **RE passthrough.** When BA's `Success criteria` are already
  behavioural and testable, RE posts a passthrough handover instead
  of a fresh AC comment. Downstream personas reference BA's `SC-N`
  directly. See RE persona — *Variant B*.
- **Skipping RE entirely.** USER can reassign the parent Story
  directly from BA to SA when BA's framing is already complete;
  state moves `Backlog → To Do → In Progress` with SA on pickup.

## Example trigger

```
> /ba "Users want a CSV export of their issue list, filterable by status and assignee, with a download link in their dashboard"
```
