# MCP integration

Two MCP servers reach Plane: the official upstream and a small
supplementary one shipped with this framework. Both are launched
once per persona via the consumer's `.mcp.json`, each carrying its
own API token, so every comment and state change in Plane is
attributed to the agent that performed it.

## Servers in play

| Server | Where from | Used for | Auth |
|---|---|---|---|
| `plane-mcp-server` | `makeplane/plane-mcp-server` (PyPI, `uvx plane-mcp-server`) | Projects, work items (incl. body, assignee, state transitions), cycles, modules, initiatives. ~55 tools. | `X-API-Key` against `/api/v1/` |
| `plane-extras-mcp` | `claude/mcp/` in this repo (Python + FastMCP) | Work-item comments (add, list) and identifier→UUID resolution. 2 tools. | `X-API-Key` against `/api/v1/` |

> Earlier versions of `plane-extras-mcp` also exposed page CRUD via
> Plane's internal app API (session-cookie auth), because Plane v1.3.0
> does not expose pages on the public REST surface. The framework no
> longer uses Plane pages — every persona artefact lives in a work-
> item *body* (written once at creation) or in a *comment* — so the
> page tools and the session-cookie auth path were removed.

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

Each persona acts in Plane with its own API token. In the consumer's
`.mcp.json` (rendered by `bin/install.py` from the inputs in
`config.yaml` + `credentials.yaml`) there is one entry per persona
per server — `plane-venture-advisor`, `plane-extras-venture-advisor`,
`plane-business-analyst`, etc. — twenty entries in total for a
ten-persona deployment.

When a slash command (`/va`, `/ba`, …) puts the main loop into a
persona's role, the main loop sees all twenty servers. The persona
prompt explicitly constrains it: *"use only `plane-<name>__*` and
`plane-extras-<name>__*` tools so every API call is attributed to
the <name> user in Plane."* Identity separation is therefore
prompt-discipline rather than a hard MCP-scope barrier.

> A previous design used Claude Code subagents with per-subagent
> `mcpServers:` frontmatter to enforce identity separation at the
> MCP layer. We moved to a main-loop / role-switch model because
> subagents start cold on every invocation and lose conversational
> context between turns, which broke the multi-turn discussion
> phases each persona depends on. The trade is real: a persona can
> in principle reach for another persona's MCP server. Persona
> prompts close that gap with explicit "use only your own"
> instructions.

## Handover semantics

A persona walks a work-item forward via the official Plane MCP's
`update_work_item` (state transition + assignee change) and writes
cross-agent notes via `plane-extras-<persona>__add_comment`. The
`plane-handover` skill encodes the consistent pattern: state
transition + assignee change + DoD comment, in that order. See
[`WORKFLOW.md`](WORKFLOW.md) for the full state spine.

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

Both MCPs read system CA bundles via Python's `truststore`, plus the
optional `PLANE_CA_BUNDLE` env var (path to a CA cert file). For
homelab installs behind a private PKI Caddy, see the
*Private-CA Plane* note in [`INSTALLATION.md`](INSTALLATION.md).
