## Commit messages — the work-item ID leads the subject

Whenever a git commit carries work that belongs to a Plane work-item,
that item's ID is the **first token of the subject line**, verbatim:

```
<PREFIX>-412 Give the operator a way to revoke a certificate
```

`git log --oneline`, a blame trail and a release note are the only
views of the history most readers ever get, and the ID is their single
bridge from a diff back to the acceptance criteria, the design and the
findings that justify it. An ID that lives only in the body or only in
a trailer is absent from every one of those views. Prefix the item the
work was done **for** — the sub-work-item for one implementor's slice,
the Story where the Story is the unit being committed. When one commit
discharges several items, the driving ID leads the subject and the rest
ride a `Refs:` trailer.

Everything else the repo's convention prescribes — a type/scope prefix,
sign-off, co-author and lane trailers — is kept, and anything that used
to open the subject now follows the ID. No work-item, no prefix: never
invent, guess or infer an ID, and never repeat it later in the subject.

## History stays linear — rebase, never a merge commit

Those same three views are also the reason the graph stays a line. One
merge commit per branch turns `git log --oneline` into a diagram, and a
reader chasing a regression then spends their attention on topology
instead of on changes.

- **Integrate upstream by rebasing.** `git pull --rebase`, or
  `git rebase <default-branch>` — never a bare `git pull` with its
  default merge, and never `git merge <default-branch>` into your own
  branch.
- **Land a branch as a fast-forward.** Rebase it onto the default
  branch, then `git merge --ff-only <branch>`, which writes no merge
  commit. A refused fast-forward means the rebase is not finished — it
  is never a reason to reach for `--no-ff`.
- **Rewriting commits that are already pushed needs USER's say-so.**
  A rebase there makes the next push a `--force-with-lease`, so ask
  before rebasing such a branch, and never use a bare `--force`.
- **A conflict you cannot settle from the diff ends the rebase.**
  `git rebase --abort` puts the tree back exactly as it was; then ask
  USER. Never guess through a conflict, and never fall back to a merge
  because the rebase got hard.
