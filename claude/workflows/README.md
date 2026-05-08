# Workflows

Canonical persona-paths for recurring kinds of work. Each file
describes a typical sequence — which personas to invoke in which
order, what to skip, what's different from the default greenfield
spine.

Workflows are **descriptive, not prescriptive**. They are reading
material for the human user — pattern reminders so you don't
re-derive the choreography for every new Story. Every turn is still
explicit (`/<persona>`); the workflow file just tells you which
turns make sense in this kind of work.

## When to look here

- USER is new to the framework and wants to see how a category of
  work normally flows.
- USER is about to start a Story and isn't sure whether the default
  greenfield path applies (e.g. "is this a bug-fix or a feature?",
  "should SA decompose, or skip straight to one implementor?").
- A persona is unsure how aggressively to consolidate slices for an
  unusual ticket (e.g. RE wondering whether passthrough is
  appropriate; SA wondering whether to skip the testing sub-work-item).

## Available workflows

| File | When to use |
|---|---|
| [`greenfield-feature.md`](greenfield-feature.md) | A genuinely new feature with at least one user-visible surface. Default spine. |
| [`bug-fix.md`](bug-fix.md) | A regression or bug in shipped code. Lighter spine — often skips BA/SA decomposition. |
| [`security-finding.md`](security-finding.md) | SR finds something in already-shipped code that must be remediated. Cross-cuts existing Stories. |

## Adding a workflow

A workflow file earns its place when the default greenfield spine
gives consistently wrong guidance for that kind of work. Format
(see existing files for shape):

```markdown
# Workflow: <name>

**Trigger:** <one sentence — when USER picks this path>

## Persona path
1. /<persona> — <what they do; what's different from default>
2. ...

## Skip / consolidate
- <persona X is typically skipped because…>

## Notable deviations
- <constraints, common pitfalls, why the default doesn't fit>

## Example trigger
> /<entry-persona> "<canonical phrasing>"
```

Keep them short. A workflow that runs longer than two screens is
either over-specified or trying to be a tutorial — split or trim.
