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
Eleven verbs per persona:

| Verb | Endpoint |
|---|---|
| `list_projects` | `GET  /api/v1/workspaces/{slug}/projects/` |
| `list_workspace_members` | `GET  /api/v1/workspaces/{slug}/members/` |
| `list_states` | `GET  /api/v1/workspaces/{slug}/projects/{p}/states/` |
| `list_labels` | `GET  /api/v1/workspaces/{slug}/projects/{p}/labels/` |
| `list_modules` | `GET  /api/v1/workspaces/{slug}/projects/{p}/modules/` |
| `list_work_items` | `GET  /api/v1/workspaces/{slug}/projects/{p}/work-items/` |
| `retrieve_work_item` | `GET  /api/v1/workspaces/{slug}/projects/{p}/work-items/{id}/` |
| `create_work_item` | `POST /api/v1/workspaces/{slug}/projects/{p}/work-items/` |
| `update_work_item` | `PATCH /api/v1/workspaces/{slug}/projects/{p}/work-items/{id}/` |
| `add_comment` | `POST /api/v1/workspaces/{slug}/projects/{p}/work-items/{id}/comments/` |
| `list_comments` | `GET  /api/v1/workspaces/{slug}/projects/{p}/work-items/{id}/comments/` |

Tools that take a `work_item_id` accept either the UUID or the
human-readable identifier (e.g. `INT-1`); the client resolves
identifiers automatically via the workspace-scoped lookup
`GET /workspaces/{slug}/work-items/{identifier}/`.

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
