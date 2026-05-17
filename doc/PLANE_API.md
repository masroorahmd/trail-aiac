# Plane API & MCP — research notes for Phase 3

> **Research date**: 2026-04-25.
> **Scope**: surface what's available, what's missing, and what that
> means for Phase 3 (Plane integration) of Trail. All
> claims here should be re-verified before each major Phase-3 design
> commit — Plane's API and MCP both move quickly.
>
> **Update 2026-05-17 (multi-tenant MCP)**: the upstream
> `makeplane/plane-mcp-server` is no longer used. The framework now
> ships a single multi-tenant MCP server (`claude/mcp/`) that holds
> every persona's API token in one process and prefixes tool names
> by persona. See [`MCP.md`](MCP.md) for the current architecture —
> the sections below remain useful as background on the public REST
> surface but no longer describe how Trail talks to Plane at runtime.
>
> **Update 2026-04-30 (page-free workflow)**: the framework no longer
> uses Plane pages. Every persona artefact lives in a work-item body
> (written once at creation) or in a comment — see
> [`WORKFLOW.md`](WORKFLOW.md) for the current data model. The
> page-related sections below are kept as historical reference about
> what Plane v1.3.0 offered. Earlier `plane-extras-mcp` versions
> exposed page CRUD via the internal app API; that path was removed.
>
> **Update 2026-04-25 (post-implementation spike)**: the original
> research below assumed pages would land via the documented public
> REST. In practice, Plane v1.3.0 Community does **not** expose pages
> on `/api/v1/`. The implementation falls back to Plane's *internal*
> app API (`/api/`, session-cookie auth) — see the
> [Internal app API section](#internal-app-api-used-for-pages-in-v130)
> below. Pages now have full CRUD (including PATCH and archive+DELETE),
> better than the original research suggested. *(Superseded by the
> 2026-04-30 update above — the framework no longer uses these
> endpoints.)*

## Headline findings

1. **Plane already ships an official MCP server**
   ([github.com/makeplane/plane-mcp-server](https://github.com/makeplane/plane-mcp-server),
   MIT, Python + FastMCP). It exposes 55+ tools and covers most of what
   we planned to build in Phase 3. **Our Phase-3 scope shrinks
   dramatically — we no longer need to wrap the REST API ourselves for
   the common case.**
2. **The MCP server has two critical gaps** for our workflow: no tools
   for **comments** and no tools for **pages** (create/list/link). The
   underlying REST API supports comments fully and pages partially.
3. **Pages have no UPDATE endpoint** in the REST API as of 2026-04-25
   (open feature requests:
   [#7319](https://github.com/makeplane/plane/issues/7319),
   [#8598](https://github.com/makeplane/plane/issues/8598)). Pages can
   be **created and read** but not edited. Implication: agents must
   treat pages as append-only artefacts — produce a new page rather
   than mutate an existing one.
4. **Per-persona token isolation works mechanically.** The official
   MCP server's stdio transport reads `PLANE_API_KEY` from the
   environment, so each persona's `mcpServers:` entry can pass its own
   token via inline env config. Phase-2 constraint #4 is satisfied
   without effort on our side.
5. **Self-hosted = cloud, modulo base URL.** Plane targets 100%
   feature parity between cloud and self-hosted; same endpoints, same
   verbs, same response shapes. Self-hosted only differs in the
   `PLANE_BASE_URL` env var.

## REST API basics

Source: [developers.plane.so/api-reference/introduction](https://developers.plane.so/api-reference/introduction).

| Aspect | Value |
|---|---|
| Base URL (cloud) | `https://api.plane.so/` |
| Base URL (self-hosted) | `https://<your-domain>/` (set via `PLANE_BASE_URL`) |
| Versioning | `/api/v1/...` |
| Auth header (PAT) | `X-API-Key: <token>` |
| Auth header (OAuth) | `Authorization: Bearer <access-token>` |
| Body format | `application/json` |
| Pagination | cursor-based: `per_page` (≤100), `cursor`; response carries `next_cursor`, `prev_cursor`, `next_page_results`, `prev_page_results`, `count`, `total_pages`, `total_results`, `results` |
| Rate limit | **60 requests/minute per client**; response headers `X-RateLimit-Remaining`, `X-RateLimit-Reset` (UTC epoch seconds) |
| Status codes | 200/201 success, 204 success-no-content, 400, 401, 404, 429, 5xx |
| `expand` parameter | optional, includes related resources inline to avoid extra round-trips |

### Rate-limit implication
60 req/min × 10 personas = 600 req/min in worst case, but our design is
user-triggered and serial (one persona active at a time), so we should
stay well below. Worth keeping in mind when Phase 4 wires bulk
operations (e.g. listing all open tickets across projects).

### PAT provisioning
A user generates a Personal Access Token via Profile → Personal Access
Tokens → Add. The token is per-Plane-user, so per-agent isolation
requires one Plane user account per persona. Operators are expected to
provision these ten accounts at kickoff (manually or via their own
config-management of choice — out of scope for this framework repo).

## Resource inventory (REST)

Source: [developers.plane.so/api-reference/project/overview](https://developers.plane.so/api-reference/project/overview).

| Resource | Verbs | Notes |
|---|---|---|
| Projects | POST, GET, PATCH, DELETE | also `get_project_features`, `update_project_features`, worklog summary |
| Project Labels | POST, GET, PATCH, DELETE | |
| Work Items (issues) | POST, GET, PATCH, DELETE, search | |
| Work Item States | POST, GET, PATCH, DELETE | states are per-project — we'll define our standard set per consumer project |
| Work Item Labels | POST, GET, PATCH, DELETE | |
| Work Item Types | POST, GET, PATCH, DELETE | |
| Work Item Links | POST, GET, PATCH, DELETE | external URL links on a work item |
| Work Item Activity | GET | read-only audit log |
| **Work Item Comments** | POST, GET, PATCH, DELETE | **gap in MCP — needs supplementary** |
| Work Item Attachments | GET, POST (upload), PATCH, DELETE | |
| **Work Item Page Links** | POST, GET, DELETE | **the mechanism to attach a Page to an issue — gap in MCP** |
| Cycles | POST, GET, PATCH, DELETE, with add/transfer/remove items | |
| Modules | POST, GET, PATCH, DELETE, with add/remove items | |
| **Pages** | POST, GET (workspace & project), list — **NO PATCH/DELETE** | append-only at API level; gap in MCP |
| Epics | POST, GET, PATCH, DELETE | |
| Initiatives | POST, GET, PATCH, DELETE | |
| Milestones | POST, GET, PATCH, DELETE | |
| Teamspaces | POST, GET, PATCH, DELETE, member/project mgmt | |
| Custom Properties / Values / Options | POST, GET, PATCH, DELETE | |
| Estimates | POST, GET, PATCH, DELETE | |
| Worklogs / Time Tracking | POST, GET, PATCH, DELETE | |
| Intake Issues | POST, GET, PATCH, DELETE | |
| Customers + Properties + Requests | POST, GET, PATCH, DELETE | |
| Assets | POST, GET, PATCH, DELETE | |
| Stickies | POST, GET, PATCH, DELETE | |
| Workspace Features | GET, PATCH | |
| Workspace Invitations | POST, GET, PATCH, DELETE | |
| Members | GET (workspace/project), POST, PATCH, DELETE | |
| User (`/me`) | GET | |

## Plane's official MCP server

Source: [github.com/makeplane/plane-mcp-server](https://github.com/makeplane/plane-mcp-server),
[developers.plane.so/dev-tools/mcp-server](https://developers.plane.so/dev-tools/mcp-server).

| Aspect | Value |
|---|---|
| Repo | `makeplane/plane-mcp-server` |
| Implementation | Python + FastMCP (the Node.js version is **deprecated**) |
| License | MIT |
| Transports | stdio, HTTP (OAuth or PAT), SSE (legacy) |
| Stdio env vars | `PLANE_API_KEY` (req), `PLANE_WORKSPACE_SLUG` (req), `PLANE_BASE_URL` (opt, defaults to cloud) |

### Tool coverage (55+ tools, by category)

| Category | Tools | Coverage notes |
|---|---|---|
| Projects (8) | list/create/retrieve/update/delete + worklog summary, members, features (get/update) | full |
| Work Items (6) | list/create/retrieve/retrieve-by-identifier/update/delete/search | full |
| Cycles (10+) | full CRUD + add/remove/transfer/list items + archive/unarchive | full |
| Modules (10+) | full CRUD + add/remove/list items + archive/unarchive | full |
| Initiatives (5) | full CRUD | full |
| Intake Work Items (5) | full CRUD | full |
| Work Item Properties (5) | full CRUD | full |
| Users (1) | `get_me` | minimal |

### Gaps in the MCP server (vs. our Phase-2 workflow design)

| Workflow need | MCP support | REST support | Mitigation |
|---|---|---|---|
| Add a comment to a ticket (cross-agent handover note) | **missing** | full | supplementary MCP tool wrapping `POST /work-items/{id}/comments/` |
| List comments on a ticket | **missing** | full | supplementary MCP tool wrapping `GET /work-items/{id}/comments/` |
| Create a Plane Page (long-form artefact) | **missing** | partial (POST exists) | supplementary MCP tool wrapping `POST /projects/{id}/pages/` |
| Update an existing Page | **missing** | **missing** in REST | **design change**: pages are append-only — agents create a new revision page rather than edit. Open issues #7319 / #8598 may close this gap eventually |
| Link a Page to an issue | **missing** | full (Work Item Page Links) | supplementary MCP tool wrapping `POST /work-items/{id}/page-links/` |
| Set assignee | full (`update_work_item`) | full | use Plane MCP as-is |
| Transition state | full (`update_work_item`) | full | use Plane MCP as-is |

## Internal app API (used for pages in v1.3.0)

The empirical spike (`mcp/scripts/diagnose_plane.py` and
`mcp/scripts/diagnose_plane_ui.py`) showed that v1.3.0 Community does
not expose pages on `/api/v1/`. Plane's frontend reaches them through a
different surface — the **internal app API** mounted at `/api/`. This
surface uses **session-cookie auth** (no PAT support) and is what we
use for pages.

Discovered from Plane's source (apps/api/plane/app/urls/page.py) and
verified against the live instance:

| Operation | Method + path under `/api/workspaces/{slug}/...` |
|---|---|
| List pages | `GET projects/{pid}/pages/` |
| Create page | `POST projects/{pid}/pages/` |
| Retrieve page | `GET projects/{pid}/pages/{page_id}/` |
| Update page metadata | `PATCH projects/{pid}/pages/{page_id}/` |
| Update page description (content) | `PATCH projects/{pid}/pages/{page_id}/description/` |
| Archive | `POST projects/{pid}/pages/{page_id}/archive/` |
| Unarchive | `DELETE projects/{pid}/pages/{page_id}/archive/` |
| Delete | requires archive first, then `DELETE projects/{pid}/pages/{page_id}/` |
| Versions | `GET projects/{pid}/pages/{page_id}/versions/` |
| Lock / unlock | `POST` / `DELETE` on `lock/` |
| Duplicate | `projects/{pid}/pages/{page_id}/duplicate/` |

### Auth flow

1. `GET /auth/get-csrf-token/` — picks up a CSRF cookie + token in body.
2. `POST /auth/sign-in/` form-encoded with `email` + `password`,
   `X-CSRFToken` header set. Returns 302 + `session-id` cookie.
3. Subsequent calls reuse the `session-id` cookie. CSRF token must be
   present on state-changing requests (`X-CSRFToken` header).

### Page-link gap remains

Plane v1.3.0 has no API to link a page to a work item — both the public
REST and the internal app API return 404 on the `/page-links/`
endpoints. **Convention as a workaround**: name pages with the
work-item identifier as a prefix (e.g. `INT-1 — Architecture`) and
post a comment on the work item containing the page's user-facing URL
(`{base}/{slug}/projects/{pid}/pages/{page_id}`). Both halves are
mechanical. The supplementary MCP enriches every page-tool return with
a `_ui_url` field so this URL is at the agent's fingertips.

## Implications for Phase 3 design (resolved)

The original plan ("wrap the public REST") was preserved for comments,
augmented with the internal app API for pages. Final shape:

1. **Use the official Plane MCP server** for projects, work items,
   cycles, modules, initiatives. Each persona declares it inline in
   `mcpServers:` with its own `PLANE_API_KEY`.
2. **Supplementary MCP** (`mcp/`, `plane-extras-mcp` v0.2.0): seven
   tools split across two auth flows.
   - *Public REST (`X-API-Key`)*: `add_comment`, `list_comments`.
   - *Internal app API (session cookie)*: `create_page`, `list_pages`,
     `retrieve_page`, `update_page_description`, `delete_page`.
3. **Pages are full CRUD**, not append-only. The original "append-only"
   constraint was based on the public REST and is reversed by the
   internal app API. Agents may revise pages directly.
4. **Page-to-work-item linking** is by naming convention + a comment
   carrying `_ui_url`. No API endpoint exists for it in v1.3.0.
5. **Per-persona credential isolation is mechanical**: each persona's
   `mcpServers:` block carries its own `PLANE_API_KEY`,
   `PLANE_UI_USERNAME`, `PLANE_UI_PASSWORD`. UI creds are more
   sensitive than a PAT (full account access) — provision a dedicated
   bot account where possible.
6. **Accepted tradeoff**: dependency on Plane's internal API. Not
   versioned, not documented, can break with any Plane release.
   Mitigated by integration tests against a live Plane instance.

## Open questions to resolve in Phase 3 kickoff

- **Workspace slug**: where does the consumer project's workspace slug
  live? Probably `.claude/config.yaml` (gitignored, deployment-specific).
- **Token storage**: per-persona PATs already live in
  `.claude/credentials.yaml` (Phase 1). Phase 3 wires these into each
  persona's `mcpServers:` env block.
- **State workflow naming**: Plane states are per-project. Either we
  document the required state names (Backlog → To Do → In Progress → In
  Review → Done) and let the user create them in Plane manually at
  kickoff, or we add a kickoff script that creates them via the API.
- **Phase taxonomy inside "In Progress"**: our workflow model defines
  Requirements → Architecture → Security → Backend Impl → Frontend Impl
  → Testing as sub-phases. Plane has no nested-state concept. Options:
  (a) encode in a custom property on the work item, (b) use labels,
  (c) flatten into top-level states. Decide in Phase 3.
- **Tracking the upstream gap**: subscribe to issues #7319 and #8598;
  if Plane ships Page UPDATE + MCP tools for comments/pages, our
  supplementary server can shrink or disappear.

## Sources

- [Plane API Documentation — introduction](https://developers.plane.so/api-reference/introduction)
- [Plane API Reference — project overview](https://developers.plane.so/api-reference/project/overview)
- [Plane MCP Server — developer docs](https://developers.plane.so/dev-tools/mcp-server)
- [makeplane/plane-mcp-server — GitHub](https://github.com/makeplane/plane-mcp-server)
- [Issue #7319 — Add API endpoints for creating and editing Pages](https://github.com/makeplane/plane/issues/7319)
- [Issue #8598 — Add Page update API endpoints and MCP tools](https://github.com/makeplane/plane/issues/8598)
- [Plane self-hosting — editions and versions](https://developers.plane.so/self-hosting/editions-and-versions)
