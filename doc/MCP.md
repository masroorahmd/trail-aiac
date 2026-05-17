# MCP integration

One multi-tenant MCP server reaches Plane on behalf of every persona.
It launches once per Claude Code session via the consumer's
`.mcp.json`, holds every persona's API token inside its own env
block, and registers every tool N× — once per persona, prefixed by
the persona's snake-case username. The persona prompt picks the
right prefix; the server picks the right token. Every comment and
state change therefore still lands in Plane attributed to the agent
that performed it.

## Server in play

| Server | Where from | Used for | Auth |
|---|---|---|---|
| `plane` | `claude/mcp/` in this repo (Python + FastMCP) | The full Plane tool surface the persona team uses — projects, work items (CRUD subset), states / labels / modules, workspace members, comments. Tool names are prefixed by persona: `business_analyst__list_states`, `release_manager__add_comment`, … | `X-API-Key` against `/api/v1/` |

> Earlier versions ran two servers per persona — upstream
> `makeplane/plane-mcp-server` (via `uvx`) plus a supplementary
> `plane-extras-mcp` for the comments gap. With ten personas that
> meant ~22 stdio processes per Claude session and ~2 GB of RSS.
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

## How personas write artefacts

The framework's data model on Plane:

| Artefact | Where it lives |
|---|---|
| Hypothesis framing (VA) | BIZ work-item *body*, written once at creation, plus optional comments for later annotation |
| Story requirements (BA) | Dev-project Story work-item *body*, written once at creation |
| Acceptance Criteria (RE) | *Comment* on the Story work-item (or omitted, when RE passthroughs because BA's spec is already AC-quality) |
| Architecture per module slice (SA) | Each sub-work-item's *body*, written once at creation |
| Security review per child (SR) | *Comment* on each implementor sub-work-item |
| Implementation notes (BD/UD/TM/TW) | *Comment* on the implementor's own sub-work-item |
| User-facing docs (TW) | Files in the project's existing docs directory (`docs/`, `README.md`, etc.) — not in Plane |
| Release notes (RM) | `CHANGELOG.md` in the project repo + comment on a release-tracker work-item |
| Per-persona handover DoDs | *Comment* on the work-item being handed off (via the `plane-handover` skill) |

Description-once is the rule for every persona: a body is written
when the work-item is created and never edited afterwards. Later
annotations and handovers travel as comments.

## Per-persona MCP scope

Each persona acts in Plane with its own API token, but those tokens
live inside a single `plane` MCP entry in the consumer's `.mcp.json`
(rendered by `bin/install.py` from the inputs in `config.yaml` +
`credentials.yaml`). The entry's `env:` block carries one
`PLANE_API_KEY_<PERSONA_PREFIX>` per declared persona; the server
reads them at startup, builds a `{persona → PlaneClient}` map, and
registers every tool N× with the persona's snake-case username as a
prefix — `business_analyst__list_states`,
`release_manager__add_comment`, and so on. Each registered tool is
a closure over its persona's client, so the call lands in Plane
under the right token regardless of which slash command invoked it.

When a slash command (`/va`, `/ba`, …) puts the main loop into a
persona's role, the main loop sees every persona's tools. The
persona prompt explicitly constrains it: *"use only
`plane__<persona_snake>__*` tools so every API call is attributed to
the &lt;persona&gt; user in Plane."* Identity separation is therefore
prompt-discipline rather than a hard MCP-scope barrier.

> A previous design used Claude Code subagents with per-subagent
> `mcpServers:` frontmatter to enforce identity separation at the
> MCP layer. We moved to a main-loop / role-switch model because
> subagents start cold on every invocation and lose conversational
> context between turns, which broke the multi-turn discussion
> phases each persona depends on. The trade is real: a persona can
> in principle reach for another persona's tool prefix. Persona
> prompts close that gap with explicit "use only your own"
> instructions.

## Handover semantics

A persona walks a work-item forward via its own
`plane__<persona_snake>__update_work_item` (state transition +
assignee change) and writes cross-agent notes via
`plane__<persona_snake>__add_comment`. The `plane-handover` skill
encodes the consistent pattern: state transition + assignee change +
DoD comment, in that order. See [`WORKFLOW.md`](WORKFLOW.md) for the
full state spine.

## HTML body / comment authoring (gotchas)

Plane stores work-item bodies and comments as HTML, exposed through
`description_html` and `comment_html` on the MCP tools. Two traps
have re-burned multiple personas across consumer projects:

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
  *as characters* must be entity-encoded by the persona itself —
  the MCP layer doesn't sanitise.

Rule of thumb: every `_html` MCP field accepts raw HTML; if a
character is special to HTML, encode it before sending.

## TLS / private-CA hosts

The MCP reads system CA bundles via Python's `truststore`, plus the
optional `PLANE_CA_BUNDLE` env var (path to a CA cert file). For
homelab installs behind a private PKI Caddy, see the
*Private-CA Plane* note in [`INSTALLATION.md`](INSTALLATION.md).
