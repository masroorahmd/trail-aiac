# MCP integration

One multi-tenant MCP server reaches Plane on behalf of every persona.
It launches once per Claude Code session via the consumer's
`.mcp.json`, holds every persona's API token inside its own env
block, and registers **one** tool set. Every tool takes a `persona`
argument; the persona prompt says which value to pass, the server
picks the token from it, and a PreToolUse hook checks it against the
`/<persona>` USER actually started. Every comment and state change
therefore still lands in Plane attributed to the agent that performed
it.

## Server in play

| Server | Where from | Used for | Auth |
|---|---|---|---|
| `plane` | `claude/mcp/` in this repo (Python + FastMCP) | The full Plane tool surface the persona team uses — projects, work items (CRUD subset), states / labels, modules (list + work-item membership), cycles (sprints, full CRUD + work-item membership + transfer), relations (list + add), workspace members, comments. 26 tools, each taking a `persona` argument that selects whose token authors the call. | `X-API-Key` against `/api/v1/` |

> Earlier versions ran two servers per persona — upstream
> `makeplane/plane-mcp-server` (via `uvx`) plus a supplementary
> `plane-extras-mcp` for the comments gap. With eleven personas that
> meant ~24 stdio processes per Claude session and ~2 GB of RSS.
> The current single-process server folds in the upstream subset
> the persona prompts actually call and drops the upstream
> dependency. The internal package is still named
> `plane-extras-mcp` for historical reasons — it is no longer
> "extras".

> An even earlier version of the supplementary server also exposed
> page CRUD via Plane's internal app API (session-cookie auth),
> because Plane v1.3.0 does not expose pages on the public REST
> surface. The framework no longer uses Plane pages — every persona
> artefact lives in a work-item *body* (written once at creation) or
> in a *comment* — so the page tools and the session-cookie auth
> path were removed.

## Why `plane` sometimes isn't there at all

`plane` is a *project-scoped* server: it lives in the consumer's
`.mcp.json`, not in the user-level config. Claude Code gates those
behind a startup prompt — *"New MCP server found in this project:
plane → Use this MCP server"* — and dismissing it answers **no** for
the entire session. The refusal is not recorded, so the prompt returns
next start; the symptom is a session where every persona is suddenly
Plane-blind and `/mcp` does not list `plane` at all. Nothing to
reconnect: a session enumerates its MCP servers once, at startup, so
`/mcp reconnect` and `/mcp enable` can only act on servers that were
loaded. That session cannot be repaired — it has to be restarted.

`claude/settings.json` therefore ships `enabledMcpjsonServers:
["plane"]`, which persists the approval and skips the prompt entirely.
If a consumer predates that, re-run `bin/install.py` against it.

Distinguish this from an outage: no `plane` tools *offered at all* is
the approval gate, whereas tools that exist but fail is Plane itself
being down (see *When Plane goes away mid-run* below).

## How personas write artefacts

The framework's data model on Plane:

| Artefact | Where it lives |
|---|---|
| Founder operations (GM) | HQ-project work-item *body*, written once at creation, plus optional comments for later annotation |
| Marketing / brand / SEO (MM) | MKT-project work-item *body*, written once at creation, plus optional comments for later annotation |
| Story requirements (BA) | Dev-project Story work-item *body*, written once at creation |
| Acceptance Criteria (RE) | *Comment* on the Story work-item (or omitted, when RE passthroughs because BA's spec is already AC-quality) |
| Architecture per module slice (SA) | Each sub-work-item's *body*, written once at creation |
| Security review per child (SR) | *Comment* on each implementor sub-work-item |
| Implementation notes (BD/UD/TM/TW) | *Comment* on the implementor's own sub-work-item |
| User-facing docs (TW) | Files in the project's existing docs directory (`docs/`, `README.md`, etc.) — not in Plane |
| Release notes (RM) | `CHANGELOG.md` in the project repo + comment on a release-tracker work-item |
| Per-persona handover DoDs | *Comment* on the work-item being handed off (via the `plane-handover` skill) |
| Upstream notes (BD / UD / SR / TM) | *Comment* on the parent Story — feedback to SA / RE's retro |
| Retro (SA / RE) | *Comment* on the parent Story, plus `MEMORY.md` + the persona's own context file |

Description-once is the rule for every persona: a body is written
when the work-item is created and never edited afterwards. Later
annotations and handovers travel as comments. The one carve-out — BA
rewriting a Story body for as long as SA has not decomposed it — is in
[`WORKFLOW.md`](WORKFLOW.md) § *Rules and conventions*.

## Per-persona MCP scope

Each persona acts in Plane with its own API token, but those tokens
live inside a single `plane` MCP entry in the consumer's `.mcp.json`
(rendered by `bin/install.py` from the inputs in `config.yaml` +
`credentials.yaml`). The entry's `env:` block carries one
`PLANE_API_KEY_<PERSONA_PREFIX>` per declared persona; the server
reads them at startup, builds a `{persona → PlaneClient}` map, and
registers **one** tool set. Every tool takes a `persona` argument
naming who is calling; the server looks the token up from that
argument, so the call lands in Plane under the right account
regardless of which slash command invoked it.

The identity used to live in the tool *name* instead —
`business_analyst__list_states`, `release_manager__add_comment` —
which meant registering all 26 tools once per persona. Measured on the
eleven-persona set: **286 tools, 179 KB of JSON schema, ~45k tokens**,
sitting in the system prompt of every session on every turn so that
one persona could reach the 26 it actually holds. One tool set is 26
tools and ~5.9k tokens. The prefix bought nothing in exchange: the
main loop saw every persona's tools either way, and nothing but the
prompt asked it to stay in its own lane.

**Identity separation is now a hook, not a naming convention.**
`.claude/hooks/persona-pin.py` (UserPromptSubmit) records which
`/<persona>` command USER started — derived from the
`.claude/agents/<persona>.md` file that command loads, so a twelfth
persona needs no hook change. `.claude/hooks/plane-persona-guard.py`
(PreToolUse on `mcp__plane__*`) denies a Plane call whose `persona`
argument disagrees with it. Strength is the consumer's call via
`hooks.persona_identity` (`strict` / `ask` / `off`); every uncertain
case passes — a session that has not run a `/<persona>` yet, a
multi-persona lane (`/autopilot`, `/quick`, `/kickoff` pin `*`) —
because a missed check costs one wrongly-attributed comment and a
false deny stops work USER asked for.

The pin lives at `.claude/cache/persona/<session-id>.json`, one file
per Claude session. Running `/ba` in one terminal and `/tm` in another
against the same repo is a normal way to work here, so the sessions
must not share a pin: a single file would hand the check to whichever
session submitted a prompt last and silently drop it for the other.
Per-session files also mean two sessions never write the same path.
Stale pins are pruned after seven days.

> A previous design used Claude Code subagents with per-subagent
> `mcpServers:` frontmatter to enforce identity separation at the
> MCP layer. We moved to a main-loop / role-switch model because
> subagents start cold on every invocation and lose conversational
> context between turns, which broke the multi-turn discussion
> phases each persona depends on. The trade — a persona reaching for
> another persona's identity — is what the guard hook now covers.

## Non-Plane MCP servers (browser automation)

Two persona behaviours want a browser: the UI Developer's visual
verification gate, and the Test Manager's browser-driven *review run*
(`/tm run review steps for <STORY-ID>` interactively, and spine step 6
under `/autopilot` — see [`WORKFLOW.md`](WORKFLOW.md)). Neither is
wired by this framework.

Both follow the [`browser-review`](../claude/skills/browser-review/SKILL.md)
skill's driver ladder. **Attended**, it ranks by *watchability*: the
project's own browser harness run headed first — an order of magnitude
faster per step than a screenshot-driven MCP, and just as watchable —
then a DOM/accessibility-tree MCP (Playwright MCP, Chrome DevTools
MCP), then a screenshot-driven one (Claude in Chrome). **Unattended**
it ranks by reliability instead: the same harness headless, then a
DOM/accessibility-tree MCP, and a screenshot-driven,
human-session-bound driver **not at all** — Claude in Chrome needs a
live window and per-site permission grants that an autopilot run cannot
supply. The persona always names the driver it picked, because the
fallback costs USER the live view; with no driver at all it reports the
steps as un-driven rather than improvising, and the run continues.

The practical consequence for a project that wants autopilot's review
run to do real work: **wire a Playwright/Chrome-DevTools MCP at user
scope, or keep an e2e harness in the repo.** Without either, step 6
degrades to an honest "not driven" every run.

**Configure such a server at user or local scope, never project
scope.** `bin/install.py` regenerates the consumer's `.mcp.json` from
scratch on every run, with the single `plane` entry as its only
content — a browser entry added there is silently dropped at the next
install. `claude mcp add --scope user …` (or the extension's own
wiring) survives.

These servers carry no Plane identity, so neither the `persona`
argument nor the guard hook reaches them; the persona prompts say so
explicitly where the behaviour is expected.

## Handover semantics

A persona walks a work-item forward via `plane__update_work_item`
(state transition + assignee change) and writes cross-agent notes via
`plane__add_comment`, both carrying its own `persona`. The `plane-handover` skill
encodes the consistent pattern: state transition + assignee change +
DoD comment, in that order. See [`WORKFLOW.md`](WORKFLOW.md) for the
full state spine.

### Dependencies (`blocked_by`)

A handover moves one ticket forward; a *dependency* says a ticket may
not move at all yet. Every persona can record one with
`plane__add_relation` on the **blocked** item
(`relation_type="blocked_by"`, `related_work_item_ids` naming what it
waits for), and read the current picture with `list_relations`. Plane
writes the inverse `blocking` side itself.

Three properties shape how the personas are told to use it:

- **No removal endpoint.** Plane's public API exposes `GET` and `POST`
  on a work item's `relations/` collection and nothing else, so
  undoing a relation — or a duplicate add — is a manual step by a
  human in the Plane UI. The prompts therefore require a
  `list_relations` read first and treat every add as permanent.
- **`blocked_by` only.** Plane accepts `blocking`, `duplicate`,
  `relates_to` and the date types as well; the framework sanctions
  just the one that changes what a persona does next. The others are
  reachable but nothing instructs a persona to write them.
- **It carries the fact, not the reason.** The relation says *this
  waits for `DEV-42`*. Why it is held and what clears it stays in the
  comment, and the held ticket still keeps `Backlog` with no assignee
  — the relation is a signal to the human reading the board, not a
  trigger, since nothing in Plane starts a persona turn.

The canonical use is the Security Reviewer holding one child of a
decomposition until a sibling's blocker finding is fixed; the rule
itself lives once in the
[`plane-handover`](../claude/skills/plane-handover/SKILL.md) skill,
*Blocked-by*.

## HTML body / comment authoring (gotchas)

Plane stores work-item bodies and comments as HTML, exposed through
`description_html` and `comment_html` on the MCP tools. These traps
have re-burned multiple personas across consumer projects:

- **Markdown is not converted.** `**bold**` and `- item` are stored
  as literal asterisks and hyphens. The templates in the persona
  prompts show the *structure* of a comment, not its wire format;
  what goes on the wire is HTML.
- **CDATA does not work.** `<![CDATA[...]]>` wrappers render as
  literal text inside the body or comment — they are not interpreted.
  To embed `<` and `>` characters (e.g. demonstrating XML or shell
  redirection inside a `<code>` block), use HTML entities `&lt;` and
  `&gt;`.
- **Don't double-encode.** Once a payload is in an HTML context, raw
  tags work — `<strong>foo</strong>` renders bold, not as four
  visible angle-bracket characters. Entity-encoding tags inside an
  already-HTML payload (`&lt;strong&gt;`) makes them render as
  literal text. Conversely, content destined for `_html` fields
  passes through verbatim, so any `<` `>` that should be displayed
  *as characters* must be entity-encoded by the persona itself.

Rule of thumb: every `_html` MCP field accepts raw HTML; if a
character is special to HTML, encode it before sending.

**The one thing the server does fix.** Double-encoding was the single
most frequent write defect across consumer projects, and its repair
cost was out of all proportion to the slip — a permanent comment, or a
body written twice. So `create_work_item`, `update_work_item` and
`add_comment` run `_repair_double_encoded_html` on the payload *before*
the HTTP call: a value carrying two or more entity-escaped tags and no
real tag at all is unescaped once, and the tool result gains a
`trail_encoding_note` telling the persona what Plane stored is already
correct and must not be resent. The signature is deliberately narrow —
`a &lt; b`, an XML snippet inside a `<code>` block, or a lone
`&lt;title&gt;` in prose all carry a real tag or too few escaped ones
and pass through byte-identical. One unescape pass is the exact inverse
of one escape pass, so `&amp;rarr;` returns as `&rarr;`; deeper
encodings hide the marker behind `&amp;lt;` and are not guessed at,
because a second blind pass would corrupt an innocent `a &amp; b`.
Nothing else is sanitised — Markdown in particular cannot be, since
`**bold**` is indistinguishable from asterisks the author meant.

**Why this matters more than a normal typo: comments are
write-once.** No persona toolset exposes a comment edit or delete
verb — `add_comment` is the whole surface. A mis-encoded comment is
therefore permanent noise on the ticket; the only remedy is a second
comment that opens by superseding the first, plus a human deleting
the original in the Plane UI. With escaping now caught pre-write, the
echo check personas run is aimed at what the server cannot fix:
literal asterisks or `- ` bullets in the returned `comment_html` mean
Markdown, and a supersede comment is the only way out. They still
write **one** item of a batch first and check its echo before creating
the rest.

Work-item *bodies* have the same one-shot property for a different
reason: the framework's description-once rule means a body is written
at creation and never edited. A mangled body is the more expensive of
the two failures, because the only ways out are both bad — leave the
ticket unreadable, or write the body a second time and leave a
modification timestamp that reads downstream as a silent content
revision. That is why the guard sits in front of `create_work_item`
and not only in the prompts. If a body does reach Plane mangled
anyway, the sanctioned repair is exactly one `update_work_item` with
byte-identical intended content plus a comment naming it an encoding
repair — never a replacement work item.

## Stale PATCH echoes

`update_work_item` can answer HTTP 200 while the response body still
carries the work-item's *previous* state. The write itself has
normally landed — the echo simply isn't evidence of it. Personas are
instructed to confirm any transition they are about to *report* (a
handover, a close) with an independent `retrieve_work_item` call and
to report that reading, rather than re-issuing the PATCH against a
stale echo.

## When Plane goes away mid-run

A self-hosted Plane disappears for a minute now and then — an upgrade,
a container restart, a backup window. The reverse proxy answers 502
with an empty body while it is gone, and to an agent that is
indistinguishable from a malformed request: the failure mode is a
persona that starts editing its own arguments to "fix" an outage.

The MCP absorbs this rather than passing it up. Transient failures are
retried inside the client with exponential backoff, bounded by
`PLANE_RETRY_BUDGET` (default 45s, deliberately below Claude Code's
MCP tool timeout — a 502 fails in milliseconds, so only a time budget
can outlast a real outage). Reads are
always retried; writes only when the failure proves Plane never
processed the request — a bodiless proxy 502, a refused connection, a
429. A write whose fate is genuinely unknown fails with an explicit
"may or may not have been applied — re-read before repeating" so the
persona verifies instead of guessing.

What survives the retries surfaces as an error that names itself an
outage and tells the persona to report it and stop. Retries are logged
to stderr, which Claude Code captures into
`~/.cache/claude-cli-nodejs/<consumer>/mcp-logs-plane/` — that is the
place to look after the fact. Details and the full retry matrix:
[`claude/mcp/README.md`](../claude/mcp/README.md).

## TLS / private-CA hosts

The MCP reads system CA bundles via Python's `truststore`, plus the
optional `PLANE_CA_BUNDLE` env var (path to a CA cert file). For
homelab installs behind a private PKI Caddy, see the
*Private-CA Plane* note in [`INSTALLATION.md`](INSTALLATION.md).
