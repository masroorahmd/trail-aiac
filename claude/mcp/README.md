# plane-extras-mcp

A multi-tenant MCP server for [Plane](https://plane.so/), built for
the [Trail](../) framework but framework-agnostic — anyone running an
MCP client against Plane with multiple identities can use it.

> The package is still called `plane-extras-mcp` for historical
> reasons. It started life as a small supplementary server covering
> the comment-tools gap in the official
> [`makeplane/plane-mcp-server`](https://github.com/makeplane/plane-mcp-server);
> it now subsumes the upstream surface the Trail personas use,
> across N identities in a single process. Rename to follow.

## What it exposes

One stdio process registers every Plane operation N×, prefixed by
each configured persona's snake-case username — e.g. for
`business-analyst` and `release-manager` you get
`business_analyst__list_states`, `release_manager__list_states`, etc.
Twenty verbs per persona:

| Verb | Endpoint |
|---|---|
| `list_projects` | `GET  /api/v1/workspaces/{slug}/projects/` |
| `list_workspace_members` | `GET  /api/v1/workspaces/{slug}/members/` |
| `list_states` | `GET  /api/v1/workspaces/{slug}/projects/{p}/states/` |
| `list_labels` | `GET  /api/v1/workspaces/{slug}/projects/{p}/labels/` |
| `list_modules` | `GET  /api/v1/workspaces/{slug}/projects/{p}/modules/` |
| `list_module_work_items` | `GET  /api/v1/workspaces/{slug}/projects/{p}/modules/{m}/module-issues/` |
| `add_work_items_to_module` | `POST /api/v1/workspaces/{slug}/projects/{p}/modules/{m}/module-issues/` |
| `remove_work_item_from_module` | `DELETE /api/v1/workspaces/{slug}/projects/{p}/modules/{m}/module-issues/{id}/` |
| `list_work_items` | `GET  /api/v1/workspaces/{slug}/projects/{p}/work-items/` |
| `retrieve_work_item` | `GET  /api/v1/workspaces/{slug}/projects/{p}/work-items/{id}/` |
| `create_work_item` | `POST /api/v1/workspaces/{slug}/projects/{p}/work-items/` |
| `update_work_item` | `PATCH /api/v1/workspaces/{slug}/projects/{p}/work-items/{id}/` |
| `add_comment` | `POST /api/v1/workspaces/{slug}/projects/{p}/work-items/{id}/comments/` |
| `list_comments` | `GET  /api/v1/workspaces/{slug}/projects/{p}/work-items/{id}/comments/` |
| `list_cycles` | `GET  /api/v1/workspaces/{slug}/projects/{p}/cycles/` |
| `retrieve_cycle` | `GET  /api/v1/workspaces/{slug}/projects/{p}/cycles/{c}/` |
| `create_cycle` | `POST /api/v1/workspaces/{slug}/projects/{p}/cycles/` |
| `update_cycle` | `PATCH /api/v1/workspaces/{slug}/projects/{p}/cycles/{c}/` |
| `delete_cycle` | `DELETE /api/v1/workspaces/{slug}/projects/{p}/cycles/{c}/` |
| `list_cycle_work_items` | `GET  /api/v1/workspaces/{slug}/projects/{p}/cycles/{c}/cycle-issues/` |
| `add_work_items_to_cycle` | `POST /api/v1/workspaces/{slug}/projects/{p}/cycles/{c}/cycle-issues/` |
| `remove_work_item_from_cycle` | `DELETE /api/v1/workspaces/{slug}/projects/{p}/cycles/{c}/cycle-issues/{id}/` |
| `transfer_cycle_work_items` | `POST /api/v1/workspaces/{slug}/projects/{p}/cycles/{c}/transfer-issues/` |

Tools that take a `work_item_id` accept either the UUID or the
human-readable identifier (e.g. `INT-1`); the client resolves
identifiers automatically via the workspace-scoped lookup
`GET /workspaces/{slug}/work-items/{identifier}/`. A `cycle_id` is
always a UUID — cycles have no human-readable identifier. The cycle
add/remove tools resolve their `work_item_id`(s) the same way as the
work-item tools. A `module_id` is likewise always a UUID; the module
membership tools resolve their `work_item_id`(s) identically. Modules
themselves are created by `plane_bootstrap` / humans, not by personas,
so only membership (not module CRUD) is exposed. A work item may belong
to several modules at once — `add_work_items_to_module` leaves existing
module memberships intact.

> Earlier versions also exposed page CRUD via Plane's internal app
> API (session-cookie auth), because Plane v1.3.0 does not expose
> pages on the public REST surface. The framework no longer uses
> Plane pages — every persona artefact lives in a work-item body or
> a comment — so the page tools and the session-cookie auth path
> were removed.

## Auth model

Public REST only: `X-API-Key` header against `/api/v1/`. No
session-cookie auth, no UI credentials needed. Per-persona tokens
are kept inside one process and selected by the prefix on each
incoming tool call.

## Env vars

| Var | Required | Notes |
|---|---|---|
| `PLANE_WORKSPACE_SLUG` | yes | Shared by every persona |
| `PLANE_API_KEY_<PERSONA_PREFIX>` | ≥1 | One per persona, e.g. `PLANE_API_KEY_BUSINESS_ANALYST`. The server scans for these at startup and registers tools for each match. Personas without a key are silently skipped. |
| `PLANE_BASE_URL` | optional (defaults to plane.so cloud) | |
| `PLANE_VERIFY_SSL` | optional | `false` to disable TLS verification |
| `PLANE_CA_BUNDLE` | optional | Path to a CA cert; takes precedence over `PLANE_VERIFY_SSL` |
| `PLANE_CONNECT_TIMEOUT` | optional | Seconds to wait for the TCP/TLS handshake (default `10`) |
| `PLANE_READ_TIMEOUT` | optional | Seconds to wait for a response (default `30`) |
| `PLANE_MAX_ATTEMPTS` | optional | Runaway guard on tries per call (default `10`) |
| `PLANE_RETRY_BUDGET` | optional | Seconds one call may spend retrying (default `45`) |

## Surviving a Plane restart

A self-hosted Plane goes away for a minute during an upgrade, a
container restart, or a backup window. Without help, every persona
tool call fails instantly and the agent — which cannot tell an outage
from a bad request — starts rewriting its arguments.

So transient failures are retried inside the client, with equal-jitter
exponential backoff (0.5s doubling to a cap of 8s). `PLANE_RETRY_BUDGET`
is the real ceiling — a refused connection or a bodiless proxy 502
fails in milliseconds, so an attempt count alone would give up after a
few seconds, and the maintenance window this was built for ran 32s.
`PLANE_MAX_ATTEMPTS` is only a runaway guard. The budget sits below
the MCP client's own tool timeout, so a caller gets our diagnostic
rather than a bare timeout.

What counts as retryable depends on whether repeating the call could
duplicate a write:

| Failure | `GET` | `POST` / `PATCH` / `DELETE` |
|---|---|---|
| Connection refused / timed out | retry | retry — the request never reached Plane |
| `429 Too Many Requests` | retry (honours `Retry-After`) | retry — throttled before any work |
| `502` / `503` with an empty or HTML body | retry | retry — the proxy answered, Plane never saw it |
| `502` with a JSON body | retry | fail — Plane answered, so it processed the request |
| `500`, `504` | retry | fail — the write may have partly landed |
| Connection broke mid-response | retry | fail, flagged "may or may not have been applied" |
| `400` / `403` / `404` | fail immediately | fail immediately |

A call that exhausts its retries raises `PlaneUnavailableError`, whose
message names the outage explicitly and tells the agent not to touch
its arguments. Every retry is logged to stderr, which MCP clients
capture into their per-server log — an outage that used to leave only
`Plane API error 502:` now leaves a trail.

## Install

With [uv](https://docs.astral.sh/uv/) (recommended):

    uv pip install -e .

Or with stock pip + venv:

    python -m venv .venv
    . .venv/bin/activate
    pip install -e .

## Run

The server speaks MCP over stdio. From a Claude Code consumer's
`.mcp.json`:

```json
{
  "mcpServers": {
    "plane": {
      "command": "uv",
      "args": ["run", "--directory", "<framework-root>/claude/mcp", "plane-extras-mcp"],
      "env": {
        "PLANE_BASE_URL": "https://plane.example.org",
        "PLANE_WORKSPACE_SLUG": "your-workspace",
        "PLANE_API_KEY_BUSINESS_ANALYST": "<BA token>",
        "PLANE_API_KEY_RELEASE_MANAGER": "<RM token>"
      }
    }
  }
}
```

`bin/install.py` renders this entry automatically from the consumer's
`config.yaml` (declared agents) and `credentials.yaml` (per-agent
tokens). On startup the server refuses to run if no
`PLANE_API_KEY_*` vars are found — a zero-tool server would silently
mask the misconfiguration.

## Test

Smoke tests need no Plane connection — they cover URL construction,
tool registration per persona, and that an `add_comment` call routes
to the right token:

    pip install -e ".[test]"
    pytest tests/test_smoke.py

Integration tests need a live Plane instance. Copy `.env.test.example`
to `.env.test` and fill in real values, then run the suite:

    pytest tests/

## License

MIT.
