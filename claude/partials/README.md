# Partials — shared prompt text with one source

A partial is a block of prompt text that belongs in many persona and
command files at once. It is written **once** here and stitched into
every consumer copy by `bin/install.py` at render time (Stage 2), so
the framework carries one source instead of N drifting copies.

## How it works

A persona or command source under `claude/agents/` or
`claude/commands/` carries a marker on its own line:

```
<!-- TRAIL:INCLUDE reading -->
```

At render time `install.py` replaces that line with the contents of
`claude/partials/reading.md`, and only then substitutes the
usual `__VAR__` placeholders — so a partial may carry placeholders of
its own (`__LARGE_FILE_LINES__`, `__CHAT_LANGUAGE__`, …). An unknown
partial name is a fatal install error, not a silent no-op.

Partials are **not** a deliverable: nothing is copied into the
consumer's `.claude/partials/`. The consumer only ever sees the
expanded text inside its rendered `agents/*.md` and `commands/*.md`.

## When a rule belongs here, and when it does not

- A rule the *receiver* can act on from a ticket, or any cross-persona
  Plane mechanic → the `plane-handover` skill, invoked on demand.
- A rule about voice, prose volume, or reading level → the `plain.md`
  output style, which reaches every persona but is scoped to how they
  write, never to what they do.
- A rule that must be **ambient** — in force for every persona on every
  turn, with nothing to invoke and nothing to remember → a partial.

That third case is narrow on purpose. A partial costs prompt tokens in
every file it lands in, on every turn, so it earns its place only when
the cost of the persona *not* knowing the rule is paid every turn too —
or when the rule binds an artefact that has no invocation point at all.

Current tenants:

| Partial | Lands in | Why ambient |
|---|---|---|
| `reading` | 13 personas, `/kickoff`, `/quick`, `/mock` | Every turn that opens a file — how much of one to read, and how many to ask for at once. |
| `commit-message` | 11 personas, `/quick`, `/mock`, `/autopilot` | A commit has no skill to invoke and no receiver to check it; the message is written once and is then history. |
| `shared-context` | 11 personas, `/kickoff`, `/quick`, `/autopilot` | A write through a symlink lands in a second repo on any turn, and nothing in this repo's `git status` will ever remind the persona that it did. |
