# Coding — agent context

> Read by: Backend Developer, UI Developer, Test Manager. Maintained by:
> Software Architect (with developer agents proposing changes).
>
> Purpose: code style and conventions. Agents apply these when writing or
> reviewing code so that diffs stay homogeneous.

## Formatting
<!-- Formatter + config. Indent style, line length, trailing commas. -->

## Naming
<!-- Files, modules, functions, types, constants. -->

## Comments & docstrings
<!-- When to comment, what to omit, docstring style. -->

The rules below are framework-level and apply from day one — the
developer personas read AC and finding comments off Plane work-items,
so the pull toward citing them in code is constant and starts with the
first Story. Add project-specific style (docstring format, when a
comment is warranted at all) around them.

- **A work-item reference is a provenance suffix, never the payload.**
  Delete every `<PREFIX>-N` token from a comment and it must still
  read as a complete reason. `# PROJ-64 SR F3` states nothing;
  `# the cert is canonical — the config field is bookkeeping and is
  never read back for authorization (PROJ-64 SR F3)` states the rule
  *and* keeps the trail.
- **Sub-IDs are private vocabulary.** `AC-8`, `SR F3`, `EC-7`, `R-012`
  and friends resolve only inside your Plane instance. Anyone reading
  the repository without Plane access — an outside contributor, a
  future maintainer, an auditor — cannot follow them, and unlike a
  commit hash the repository does not preserve what they point at.
  Cite them, but never lean on them.
- **No ticket archaeology.** `pre-PROJ-110`, "used to reject", "was
  flipped 400→422" describe a diff, and git already holds the diff.
  The one legitimate case is code that *still today* handles an older
  shape (wire compatibility, data written by earlier versions) —
  there, describe the shape being tolerated and why, not the ticket
  that introduced the tolerance.
- **Normative claims need an enforceable anchor.** Work-item
  references are unenforced: nothing notices when a later Story
  invalidates the rule a comment asserts. Where a comment states a
  rule derived from an external norm (an RFC, a regulation, a vendor
  contract), cite that norm — it is stable and checkable — and let the
  work-item ID ride along behind it as history.

## Error handling
<!-- Exceptions vs. results, where to catch, how to log. -->

## Logging
<!-- Levels, structured fields, what *not* to log. -->

## Patterns to prefer / avoid
<!-- Project-specific dos and don'ts that aren't enforceable by lint. -->
