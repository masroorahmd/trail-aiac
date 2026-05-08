---
description: Set up the twelve context documents every agent reads. Drafts each from your README and project files, asks short questions only when needed, and writes them under .claude/context/. Plan ~20 minutes; re-running preserves anything already filled in.
argument-hint: "[--force-overwrite]"
---

You are running `/kickoff` directly in the **main loop** of this Claude
Code session. Do **NOT** delegate to a subagent — `/kickoff` is a
human-in-the-loop walkthrough: the run flows continuously from the
first context file to the last, and the user is only pulled in when a
file has a material gap that questions can close. Subagent delegation
would lose that interactivity.

`$ARGUMENTS` may contain `--force-overwrite`. If present, overwrite
existing context files without asking. Otherwise, **never overwrite a
context file that already has substantive content** — abort that
file and report it as preserved.

## What "substantive" means

A context file is *stub* (and therefore safe to draft) if its body
contains only HTML comments (`<!-- ... -->`) and section headings —
i.e. no real prose, no real bullet content. Anything else is
*substantive*: leave it alone unless `--force-overwrite`.

## Phase 1 — Discover the project (silent)

Use Read/Glob/Grep liberally in the CWD; do not print contents to
chat. Phase 2 drafts from what you find here, so a shallow scan
forces inventions later. Scan systematically across these
categories:

**Identity.** `README.md` (primary), `LICENSE`, top-level `*.md`
(`CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`,
`ARCHITECTURE.md`, `ROADMAP.md`, `CODE_OF_CONDUCT.md`).

**Existing agent-facing detail.** If `CLAUDE.md` exists at the
project root, treat it as a top-tier evidence source on par with
`README.md` — it is the project's project-wide, agent-facing detail
surface and typically encodes non-obvious patterns, invariants, and
house rules. Read it fully.

**Stack & tooling.** Whichever package manifests + lockfiles exist,
plus their `[tool.*]` (or equivalent) sections:
- Python: `pyproject.toml`, `requirements*.txt`, `uv.lock`,
  `poetry.lock`, `.python-version`.
- JS/TS: `package.json`, `package-lock.json` / `pnpm-lock.yaml` /
  `yarn.lock`, `tsconfig.json`, `.nvmrc`.
- Rust: `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`.
- Go: `go.mod`, `go.sum`.
- Ruby: `Gemfile`, `Gemfile.lock`, `.ruby-version`.
- JVM: `pom.xml`, `build.gradle*`, `gradle/libs.versions.toml`.
- .NET: `*.csproj`, `*.sln`, `Directory.Build.props`,
  `global.json`.

Lint / format / type configs: `.ruff.toml`, `mypy.ini`, `.eslintrc*`,
`.prettierrc*`, `tsconfig.json`, `rustfmt.toml`, `clippy.toml`,
`.rubocop.yml`, `.golangci.yml`, `checkstyle.xml`, `.editorconfig`.

Polyglot signals: `.tool-versions` (asdf / mise), `Dockerfile*`,
`compose.yml`, `helm/`, `k8s/`.

**Testing & CI.** Test directories (`tests/`, `test/`, `__tests__/`,
`spec/`). Test config (`pytest.ini`, `tox.ini`, `jest.config.*`,
`vitest.config.*`, `phpunit.xml`, `.rspec`, `karma.conf.*`,
`Cargo.toml [dev-dependencies]`). CI workflows
(`.github/workflows/*.yml`, `.gitlab-ci.yml`, `Jenkinsfile`,
`azure-pipelines.yml`, `.circleci/config.yml`) — these reveal the
*actual* PR gates the project enforces.

**Architecture & API.** Source tree (`src/`, `app/`, `lib/`,
`packages/`, `cmd/`, `internal/`, `pkg/`). API contracts
(`openapi.{json,yaml}`, `*.proto`, GraphQL schemas, framework
router/controller files). Decision records (`docs/adr/`,
`docs/decisions/`).

**Docs & release.** `docs/` plus its config (`mkdocs.yml`,
`conf.py` for Sphinx, `docusaurus.config.*`, `book.toml`,
`antora.yml`). `CHANGELOG.md` + `git log --tags
--simplify-by-decoration` for release history. Release-automation
configs (`.github/release.yml`, `release-please-config.json`,
`semantic-release` config).

> The patterns above are illustrative — if the project uses a
> stack not named here (Elixir, Haskell, Swift, Crystal, Scala, …),
> apply the same principle: find the file the stack stores the
> decision in, and read it. The categories are universal; the
> patterns are not.

Build a one-paragraph mental model of *what is built, for whom, in
which stack, at what stage*. Hold it — Phase 2 grounds every draft
in this. If `README.md` is missing or too thin to support drafting,
**stop and ask one numbered question**: "I cannot infer the product
from the project. Please paste a 2–3 sentence brief or point me at a
doc, then re-run /kickoff."

## Phase 2 — Draft each context file (interactive)

### Evidence-first drafting

The project's actual configuration is authoritative. For each file,
ask: *"Does the project answer this itself?"* If yes, extract the
answer — do **not** overwrite it with a sensible default.

Worked examples (illustrative across stacks; apply the same form to
whatever you find):

- `stack.md` runtime version → `.python-version` /
  `requires-python` / `.nvmrc` / `engines` in `package.json` /
  `rust-toolchain.toml` / `go` directive in `go.mod` — **not**
  "X.Y is current".
- `coding.md` line-length → `[tool.ruff].line-length` /
  `.eslintrc:rules['max-len']` / `.editorconfig` `max_line_length` /
  `rustfmt.toml` `max_width` — **not** "100 is reasonable".
- `testing.md` runner → presence of `pytest.ini` /
  `jest.config.*` / `Cargo.toml [dev-dependencies]` /
  `phpunit.xml` — **not** "pytest is the standard".
- `release.md` cadence → `git log --tags --simplify-by-decoration`
  + `CHANGELOG.md` history — **not** "on-demand is fine for now".

The principle is general: find the file the stack stores the
decision in, and read it. The bullets above are illustrative, not
exhaustive.

Fall back to a default ONLY when the project is silent on the
topic. When you do, mark the affected line in the written file with
`<!-- Default chosen at kickoff; adjust to your team's convention. -->`
so inventions are visible at review time.

### Defer to CLAUDE.md, do not duplicate it

When `CLAUDE.md` already documents a pattern, invariant, or house
rule in detail, the corresponding `.claude/context/<file>.md` should
*summarise and reference* it (e.g. *"per CLAUDE.md '\<section\>',
…"*) rather than restate it verbatim. The two surfaces are
complementary, not redundant: `CLAUDE.md` is the project-wide,
agent-facing *detail*; `.claude/context/*.md` are *per-role
summaries*. They must agree on facts.

### File ownership

The 12 files live under `.claude/context/` and have these owners
(visible in each file's `> Read by / Maintained by` header):

| File | Maintained by | First-pass draftable from project source? |
|---|---|---|
| `product.md`       | Business Analyst       | Yes — README is usually enough. |
| `roadmap.md`       | Business Analyst       | Maybe — needs user input on phases / dates. |
| `glossary.md`      | Business Analyst       | Yes — domain terms from README. |
| `stack.md`         | Software Architect     | Yes — pyproject/package metadata. |
| `architecture.md`  | Software Architect     | Maybe — needs user input on bounded contexts / external systems. |
| `api.md`           | Software Architect     | Skip if no API exists yet. |
| `coding.md`        | Software Architect     | Mostly user input — house style / lints. |
| `security.md`      | Security Reviewer      | User input — threat model, auth posture. |
| `testing.md`       | Test Manager           | Yes — observe test layout if present. |
| `ui.md`            | UI Developer           | Skip if no UI exists yet. |
| `documentation.md` | Technical Writer       | User input — docs strategy. |
| `release.md`       | Release Manager        | User input — versioning + cadence. |

For **each** file in this order: `product → glossary → stack → testing →
roadmap → architecture → api → ui → coding → security → documentation →
release`. The order goes from "most draftable from source" to "most user
input required" — by the time you hit the user-input-heavy ones, you
will have built shared context with the user that sharpens their answers.

For each file:

1. **Read the existing stub** at `.claude/context/<name>.md`. If it has
   substantive content (per the definition above) and `$ARGUMENTS` does
   NOT contain `--force-overwrite`, mark it `preserved` and move on to
   the next file.
2. **Compose silently.** Hold the file content in your reasoning — do
   NOT print it to chat. Honor the file's existing section structure —
   only replace the `<!-- ... -->` markers with real prose / bullets.
   Use *plain prose* unless the existing template uses bullet sections.
   Stay specific to THIS project — no generic platitudes. The Write
   tool call (step 4) is the moment the content first materialises;
   the user reads it by opening the file, not by scrolling chat.
3. **Decide** how to proceed with this file:
   - **Source + clarity sufficient** → write the file directly. Do NOT
     show a preview, do NOT ask "shall I write this?". This is the
     default path when the README + project metadata + already-written
     context files give you enough.
   - **A couple of pointed questions would close the gap** → ask up to
     **3 numbered questions** and WAIT for answers. Then apply them to
     the draft and continue. Reserve this branch for material gaps,
     not for confirming style choices.
   - **The project simply does not have the signal yet** (e.g.
     `api.md` for a project with no API, `ui.md` with no UI,
     `glossary.md` for a brand-new project with no domain terms) →
     write a *minimal stub*: keep the section structure, replace each
     `<!-- ... -->` with `<!-- TODO: fill in once <concrete trigger> -->`
     where `<concrete trigger>` names what has to exist before this
     file makes sense. Mark this file as `stub (insufficient signal)`
     in the final report.
4. **Write the file** with the Write tool.
5. **Confirm in one line** which file was written (e.g.
   `wrote product.md`). No preview, no recap, no progress summary.
6. **Immediately continue with the next file.** Do not pause, do not
   ask "continue?", do not check in mid-run. The walk-through is one
   continuous flow from `product.md` through `release.md`; the only
   things that interrupt it are step-3 questions, an explicit
   `--force-overwrite` collision, or the user typing "skip" / "stop".

If at any point the user types "skip", move to the next file and mark
the current one `skipped (user request)`. If the user types "stop",
end /kickoff after the current file is written (if any).

### Forbidden patterns (per file)

If you catch yourself producing any of these, you have a bug — stop
and call the Write tool with the composed content instead:

- "Here's my proposed content for `<file>.md`: …" followed by the
  file body in chat.
- "Shall I write it as-is?" / "Does this look right?" / "Any
  corrections before I write?" — even when paired with a self-
  acknowledgement like "no gaps here".
- A markdown rendering of the file content next to the confirmation
  line ("wrote `<file>.md`. Here's what's in it: …").
- Asking the user to choose between drafted variants when the source
  material is sufficient — pick one and write it.

The per-file output budget is fixed:

- **Material-gap branch**: one numbered-question block, then wait.
- **Sufficient-signal branch**: zero chat output until step 5.
- **Insufficient-signal branch**: zero chat output until step 5.
- **Step 5**: exactly one confirmation line — file name and status,
  nothing more.

Anything outside that budget is a violation of the silent-write
contract.

## Phase 3 — Final report

Print a single summary table:

```
| File             | Status                              |
|------------------|-------------------------------------|
| product.md       | filled                              |
| glossary.md      | filled                              |
| stack.md         | filled                              |
| ...              | ...                                 |
```

Status values: `filled`, `preserved (already populated)`,
`stub (insufficient signal)`, `skipped (user request)`.

Then print three lines of next-step guidance:

```
Next: cd <consumer> && claude
      > /ba "<your first feature brief>"
The Business Analyst will read product.md / roadmap.md / glossary.md
and turn your brief into a Plane Story.
```

## Hard rules

- **No subagent delegation.** Stay in the main loop. The user is in the
  conversation with you.
- **Read-only on the project source.** You may use Read/Glob/Grep on
  the consumer's source files; do NOT Edit/Write anything outside
  `.claude/context/`.
- **Do not touch** `.claude/agent-memory/`, `.claude/credentials.yaml`,
  `.claude/config.yaml`, `.claude/settings*.json`. Those are out of
  scope for kickoff.
- **One file at a time, sequential writes.** No batch writes, no
  parallel Write calls. Finish file N (write + one-line confirm)
  before reading or composing file N+1. But also: NO pause between
  files — the next file starts in the same agent turn.
- **Per-file output budget.** Outside step-3 question blocks, the
  ONLY chat output for a file is the single confirmation line in
  step 5. No previews, no recaps, no "shall I write this?" prompts.
  See *Forbidden patterns* under Phase 2 for the full list.
- **Preserve `> Read by / Maintained by / Purpose` headers verbatim.**
  These tell future agents who owns the file.
