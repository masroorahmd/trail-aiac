# plane-extras-mcp

A supplementary MCP server for [Plane](https://plane.so/), exposing the
work-item comment tools that the official
[`makeplane/plane-mcp-server`](https://github.com/makeplane/plane-mcp-server)
does not currently provide.

Built for the [Trail](../) framework but framework-agnostic
— anyone running an MCP client against Plane can use it.

## What it exposes

| Tool | Endpoint |
|---|---|
| `add_comment` | `POST /api/v1/.../work-items/{id}/comments/` |
| `list_comments` | `GET  /api/v1/.../work-items/{id}/comments/` |

Both tools accept either a work-item UUID or its human-readable
identifier (e.g. `INT-1`); the client resolves identifiers
automatically via `GET /workspaces/{slug}/work-items/{identifier}/`.

> Earlier versions of this MCP also exposed page CRUD via Plane's
> internal app API (session-cookie auth), because Plane v1.3.0 does
> not expose pages on the public REST surface. The framework no
> longer uses Plane pages — every persona artefact lives in a
> work-item body or a comment — so the page tools and the
> session-cookie auth path were removed. Reverting that change is a
> small diff, should pages return to the workflow.

## Auth model

Public REST only: `X-API-Key` header against `/api/v1/`. No
session-cookie auth, no UI credentials needed.

## Env vars

| Var | Required | Notes |
|---|---|---|
| `PLANE_API_KEY` | yes | Personal Access Token (workspace-scoped) |
| `PLANE_WORKSPACE_SLUG` | yes | |
| `PLANE_BASE_URL` | yes (defaults to plane.so cloud) | |
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

The server speaks MCP over stdio. From a Claude Code persona's
`mcpServers:` config (in the consumer's `.mcp.json` or persona
frontmatter):

```yaml
mcpServers:
  - plane-extras:
      type: stdio
      command: plane-extras-mcp
      env:
        PLANE_API_KEY: <persona's PAT>
        PLANE_WORKSPACE_SLUG: <your workspace slug>
        PLANE_BASE_URL: <self-hosted URL, omit for cloud>
```

Or, without the console script:

```yaml
mcpServers:
  - plane-extras:
      type: stdio
      command: python
      args: ["-m", "plane_extras_mcp"]
```

## Test

Smoke tests need no Plane connection:

    pip install -e ".[test]"
    pytest tests/test_smoke.py

Integration tests need a live Plane instance. Copy `.env.test.example`
to `.env.test` and fill in real values, then run the suite:

    pytest tests/

## Why this exists

The official Plane MCP server covers projects, work items, cycles,
modules, and initiatives — but not work-item comments. The
Trail framework's persona handovers all live in
comments, so this small server fills that gap. If upstream Plane
adds comment tools, this server can be retired.

## License

MIT.
