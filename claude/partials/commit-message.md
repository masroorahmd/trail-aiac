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
