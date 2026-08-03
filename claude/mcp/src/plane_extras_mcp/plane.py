"""Async client for the subset of Plane endpoints this MCP needs.

Speaks Plane's public REST surface (`/api/v1/`, X-API-Key auth) only.
Used for comments and the workspace-scoped work-item lookup.

We previously also reached into Plane's internal app API (session-
cookie auth) to manage pages, because Plane v1.3.0 doesn't expose
pages on the public REST surface. The framework no longer uses pages
— every artefact lives in a work-item body or a comment — so the
internal-app fallback is gone, along with the PLANE_UI_USERNAME /
PLANE_UI_PASSWORD env vars it required.

Transient failures are absorbed here rather than handed to the caller:
a Plane restart, a maintenance window, or a reverse proxy answering
502/503 while the app container comes back is retried with exponential
backoff. What survives the retries is raised as `PlaneUnavailableError`
with a message that says *outage*, so the agent stops rewriting its
arguments and tells the user instead.

Env vars:
- `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`, `PLANE_BASE_URL` — required.
- `PLANE_VERIFY_SSL`, `PLANE_CA_BUNDLE` — optional TLS controls.
- `PLANE_CONNECT_TIMEOUT`, `PLANE_READ_TIMEOUT` — optional timeouts.
- `PLANE_MAX_ATTEMPTS`, `PLANE_RETRY_BUDGET` — optional retry limits.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_VERSION = "v1"
DEFAULT_BASE_URL = "https://api.plane.so"

# Split from the previous flat 30s: a Plane that is down refuses the
# connection fast, so waiting 30s to find that out only lengthens the
# outage. Reads keep the longer budget — a cold Plane answers slowly.
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 30.0

# Retry envelope. The budget is the real ceiling: a refused connection
# or a bodiless proxy 502 fails in milliseconds, so an attempt count
# alone would give up after a few seconds — the observed Plane
# maintenance windows ran 12s and 32s. The budget sits below Claude
# Code's own MCP tool timeout so the caller sees our diagnostic rather
# than a bare timeout; the attempt count is only a runaway guard for
# failures that return slowly.
DEFAULT_MAX_ATTEMPTS = 10
DEFAULT_RETRY_BUDGET = 45.0
_BACKOFF_BASE = 0.5
_BACKOFF_CAP = 8.0

# Methods with no side effect: always safe to repeat.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def looks_like_uuid(value: str) -> bool:
    """True if `value` is a canonical UUID string (8-4-4-4-12 hex)."""
    return bool(_UUID_RE.match(value))


def _resolve_verify() -> str | bool:
    """Resolve the httpx `verify` argument from env vars.

    `PLANE_CA_BUNDLE` (path to a CA cert file) takes precedence over
    `PLANE_VERIFY_SSL`. If neither is set, verification is enabled
    against the system trust store.
    """
    ca_bundle = os.environ.get("PLANE_CA_BUNDLE")
    if ca_bundle:
        return ca_bundle
    flag = os.environ.get("PLANE_VERIFY_SSL", "").strip().lower()
    if flag in ("false", "0", "no", "off"):
        return False
    return True


def _env_float(name: str, default: float) -> float:
    """Read a positive float from the environment, else `default`.

    A malformed or non-positive value falls back rather than raising —
    a typo in the consumer's `.mcp.json` must not stop the server from
    starting.
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("plane-mcp: ignoring non-numeric %s=%r", name, raw)
        return default
    if value <= 0:
        logger.warning("plane-mcp: ignoring non-positive %s=%r", name, raw)
        return default
    return value


def _looks_like_gateway_error(response: httpx.Response) -> bool:
    """True if the error response came from a reverse proxy, not Plane.

    Caddy/nginx answer an unreachable upstream with an empty body or an
    HTML error page; Plane itself always answers JSON. An error that
    never reached the app is one no write could have been applied by,
    which is what makes it safe to repeat a POST/PATCH against.
    """
    content_type = response.headers.get("content-type", "")
    if "json" in content_type.lower():
        return False
    return not response.content or b"<" in response.content[:64]


def _status_is_retryable(status_code: int, method: str, response: httpx.Response) -> bool:
    """Decide whether an error status is worth another attempt.

    Repeating a GET is free. Repeating a POST is only free when we can
    tell the request never reached Plane, so unsafe methods retry on a
    rejection (429 — throttled before any work) or a gateway-level
    failure, but never on a 500/504 the app itself may have partly
    processed.
    """
    if status_code == 429:
        return True
    if status_code == 503:
        return True
    if status_code == 502:
        return method.upper() in SAFE_METHODS or _looks_like_gateway_error(
            response
        )
    if status_code in (500, 504):
        return method.upper() in SAFE_METHODS
    return False


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Honour a numeric `Retry-After` header, capped so a hostile or
    mistaken value cannot pin a tool call open for minutes.
    """
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return min(float(raw), _BACKOFF_CAP)
    except ValueError:
        return None


def _backoff_delay(attempt: int) -> float:
    """Equal-jitter exponential backoff for `attempt` (1-based).

    Half the window is fixed and half is random: the fixed half keeps
    the retries spreading out, the random half keeps several personas
    hitting a recovering Plane from re-colliding on every round.
    """
    window = min(_BACKOFF_CAP, _BACKOFF_BASE * (2 ** (attempt - 1)))
    return window / 2 + random.uniform(0, window / 2)


class PlaneError(RuntimeError):
    """Raised when Plane returns an error status (>=400)."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"Plane API error {status_code}: {body[:500]}")
        self.status_code = status_code
        self.body = body


class PlaneUnavailableError(PlaneError):
    """Raised when Plane stayed unreachable across every retry.

    Distinct from `PlaneError` because the remedy is different: the
    call was well-formed and will work unchanged once Plane is back.
    The message says so explicitly — an agent that reads only
    "Plane API error 502:" starts mutating its arguments, which is
    what a maintenance window used to trigger.
    """

    def __init__(
        self,
        *,
        method: str,
        url: str,
        attempts: int,
        elapsed: float,
        cause: str,
        status_code: int = 0,
        body: str = "",
        outcome_unknown: bool = False,
    ) -> None:
        detail = (
            f"Plane is unreachable or restarting: {method} {url} failed "
            f"with {cause} after {attempts} attempt(s) over {elapsed:.1f}s. "
            "This is an infrastructure outage, not a malformed request — "
            "the identical call will succeed once Plane is back. Do not "
            "change the arguments and do not retry in a loop; report the "
            "outage to the user and stop."
        )
        if outcome_unknown:
            detail += (
                " The request may or may not have been applied — re-read "
                "the work item before repeating it."
            )
        RuntimeError.__init__(self, detail)
        self.status_code = status_code
        self.body = body
        self.attempts = attempts
        self.elapsed = elapsed
        self.outcome_unknown = outcome_unknown


class PlaneClient:
    """Async client for Plane's public REST surface (X-API-Key auth)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        workspace_slug: str | None = None,
        base_url: str | None = None,
        verify: str | bool | None = None,
        max_attempts: int | None = None,
        retry_budget: float | None = None,
    ) -> None:
        self.api_key = api_key or os.environ["PLANE_API_KEY"]
        self.workspace_slug = (
            workspace_slug or os.environ["PLANE_WORKSPACE_SLUG"]
        )
        resolved_base = base_url or os.environ.get(
            "PLANE_BASE_URL", DEFAULT_BASE_URL
        )
        self.base_url = resolved_base.rstrip("/")
        self.verify = verify if verify is not None else _resolve_verify()
        self.max_attempts = max_attempts or int(
            _env_float("PLANE_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)
        )
        self.retry_budget = retry_budget or _env_float(
            "PLANE_RETRY_BUDGET", DEFAULT_RETRY_BUDGET
        )
        self._pat_client: httpx.AsyncClient | None = None

    @property
    def pat_client(self) -> httpx.AsyncClient:
        if self._pat_client is None:
            self._pat_client = httpx.AsyncClient(
                headers={"X-API-Key": self.api_key},
                timeout=httpx.Timeout(
                    connect=_env_float(
                        "PLANE_CONNECT_TIMEOUT", DEFAULT_CONNECT_TIMEOUT
                    ),
                    read=_env_float(
                        "PLANE_READ_TIMEOUT", DEFAULT_READ_TIMEOUT
                    ),
                    write=DEFAULT_READ_TIMEOUT,
                    pool=DEFAULT_CONNECT_TIMEOUT,
                ),
                verify=self.verify,
            )
        return self._pat_client

    async def aclose(self) -> None:
        if self._pat_client is not None:
            await self._pat_client.aclose()
            self._pat_client = None

    async def __aenter__(self) -> "PlaneClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    @staticmethod
    def _unwrap_list(payload: Any) -> list[dict[str, Any]]:
        # Plane list endpoints can return either a bare list or a paginated
        # dict with a `results` key. Normalise to a list.
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
        if isinstance(payload, list):
            return payload
        return []

    # =====================================================================
    # public REST (/api/v1/, X-API-Key) — comments and work-item lookup
    # =====================================================================

    def _pat_url(self, path: str) -> str:
        return (
            f"{self.base_url}/api/{API_VERSION}"
            f"/workspaces/{self.workspace_slug}/{path.lstrip('/')}"
        )

    async def _pat_request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Issue one Plane request, retrying transient failures.

        Retries are bounded twice over — by `max_attempts` and by
        `retry_budget` — and a delay that would overrun the budget ends
        the loop instead of being truncated, so a tool call cannot
        block longer than the budget plus one request.
        """
        url = self._pat_url(path)
        started = time.monotonic()
        deadline = started + self.retry_budget
        is_safe = method.upper() in SAFE_METHODS

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = await self.pat_client.request(
                    method, url, json=json, params=params
                )
            except httpx.HTTPError as exc:
                # A failure to establish the connection is proof no
                # write landed; anything later (read/protocol) leaves
                # the outcome genuinely unknown, so unsafe methods stop
                # and say so rather than risk a duplicate comment.
                connect_phase = isinstance(
                    exc, (httpx.ConnectError, httpx.ConnectTimeout,
                          httpx.PoolTimeout)
                )
                cause = f"{type(exc).__name__}: {exc}"
                delay = _backoff_delay(attempt)
                if (
                    not (connect_phase or is_safe)
                    or attempt == self.max_attempts
                    or time.monotonic() + delay > deadline
                ):
                    raise PlaneUnavailableError(
                        method=method,
                        url=url,
                        attempts=attempt,
                        elapsed=time.monotonic() - started,
                        cause=cause,
                        outcome_unknown=not (connect_phase or is_safe),
                    ) from exc
                self._log_retry(method, url, cause, attempt, delay)
                await asyncio.sleep(delay)
                continue

            if response.status_code >= 400:
                if not _status_is_retryable(
                    response.status_code, method, response
                ):
                    raise PlaneError(response.status_code, response.text)
                delay = _retry_after_seconds(response) or _backoff_delay(
                    attempt
                )
                if (
                    attempt == self.max_attempts
                    or time.monotonic() + delay > deadline
                ):
                    raise PlaneUnavailableError(
                        method=method,
                        url=url,
                        attempts=attempt,
                        elapsed=time.monotonic() - started,
                        cause=f"HTTP {response.status_code}",
                        status_code=response.status_code,
                        body=response.text,
                    )
                self._log_retry(
                    method,
                    url,
                    f"HTTP {response.status_code}",
                    attempt,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if attempt > 1:
                logger.warning(
                    "plane-mcp: %s %s recovered on attempt %d after %.1fs",
                    method,
                    url,
                    attempt,
                    time.monotonic() - started,
                )
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

        # Unreachable: every path out of the loop returns or raises.
        raise AssertionError("retry loop exited without a result")

    def _log_retry(
        self, method: str, url: str, cause: str, attempt: int, delay: float
    ) -> None:
        """Announce a retry on stderr.

        Claude Code captures an MCP server's stderr into its own
        per-server log, so this is what turns a silent outage into
        something diagnosable after the fact.
        """
        logger.warning(
            "plane-mcp: %s %s failed with %s (attempt %d/%d), retrying in %.1fs",
            method,
            url,
            cause,
            attempt,
            self.max_attempts,
            delay,
        )

    async def resolve_work_item(self, work_item_ref: str) -> str:
        """Return the work-item UUID. Accepts either a UUID (returned
        unchanged) or a human-readable identifier like ``INT-1``, in which
        case it is looked up via the workspace-scoped endpoint
        ``GET /workspaces/{slug}/work-items/{identifier}/``.
        """
        if looks_like_uuid(work_item_ref):
            return work_item_ref
        result = await self._pat_request(
            "GET", f"work-items/{work_item_ref}/"
        )
        return result["id"]

    # ----- projects + workspace members -----

    async def list_projects(self) -> list[dict[str, Any]]:
        """List all projects in the workspace."""
        return self._unwrap_list(await self._pat_request("GET", "projects/"))

    async def list_workspace_members(self) -> list[dict[str, Any]]:
        """List members of the workspace (used for assignee/author lookups)."""
        return self._unwrap_list(await self._pat_request("GET", "members/"))

    # ----- per-project metadata -----

    async def list_states(self, project_id: str) -> list[dict[str, Any]]:
        """List workflow states defined on a project."""
        return self._unwrap_list(
            await self._pat_request("GET", f"projects/{project_id}/states/")
        )

    async def list_labels(self, project_id: str) -> list[dict[str, Any]]:
        """List labels defined on a project."""
        return self._unwrap_list(
            await self._pat_request("GET", f"projects/{project_id}/labels/")
        )

    async def list_modules(self, project_id: str) -> list[dict[str, Any]]:
        """List modules defined on a project."""
        return self._unwrap_list(
            await self._pat_request("GET", f"projects/{project_id}/modules/")
        )

    # ----- work items -----

    async def list_work_items(
        self,
        project_id: str,
        *,
        state: str | None = None,
        assignees: str | None = None,
        labels: str | None = None,
        priority: str | None = None,
        per_page: int | None = None,
        cursor: str | None = None,
        expand: str | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """List work items in a project. Filters are passed as query
        params; multi-value filters (assignees, labels) are
        comma-separated UUID lists, matching Plane's REST surface.
        """
        params: dict[str, Any] = {
            k: v
            for k, v in {
                "state": state,
                "assignees": assignees,
                "labels": labels,
                "priority": priority,
                "per_page": per_page,
                "cursor": cursor,
                "expand": expand,
                "order_by": order_by,
            }.items()
            if v is not None
        }
        return self._unwrap_list(
            await self._pat_request(
                "GET",
                f"projects/{project_id}/work-items/",
                params=params or None,
            )
        )

    async def retrieve_work_item(
        self, project_id: str, work_item_ref: str
    ) -> dict[str, Any]:
        """Retrieve a single work item (full body + relations).
        ``work_item_ref`` accepts UUID or human identifier (e.g. ``INT-1``).
        """
        wid = await self.resolve_work_item(work_item_ref)
        return await self._pat_request(
            "GET", f"projects/{project_id}/work-items/{wid}/"
        )

    async def create_work_item(
        self,
        project_id: str,
        *,
        name: str,
        description_html: str | None = None,
        state: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
        parent: str | None = None,
        start_date: str | None = None,
        target_date: str | None = None,
        estimate_point: str | None = None,
    ) -> dict[str, Any]:
        """Create a work item in a project. ``parent`` accepts UUID or
        identifier; resolved to UUID before the request.
        """
        body = await self._work_item_payload(
            parent=parent,
            name=name,
            description_html=description_html,
            state=state,
            assignees=assignees,
            labels=labels,
            priority=priority,
            start_date=start_date,
            target_date=target_date,
            estimate_point=estimate_point,
        )
        return await self._pat_request(
            "POST",
            f"projects/{project_id}/work-items/",
            json=body,
        )

    async def update_work_item(
        self,
        project_id: str,
        work_item_ref: str,
        *,
        name: str | None = None,
        description_html: str | None = None,
        state: str | None = None,
        assignees: list[str] | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
        parent: str | None = None,
        start_date: str | None = None,
        target_date: str | None = None,
        estimate_point: str | None = None,
    ) -> dict[str, Any]:
        """Patch a work item. Only non-None fields are sent so callers
        can transition state without nulling other fields.
        ``work_item_ref`` accepts UUID or identifier.
        """
        wid = await self.resolve_work_item(work_item_ref)
        body = await self._work_item_payload(
            parent=parent,
            name=name,
            description_html=description_html,
            state=state,
            assignees=assignees,
            labels=labels,
            priority=priority,
            start_date=start_date,
            target_date=target_date,
            estimate_point=estimate_point,
        )
        return await self._pat_request(
            "PATCH",
            f"projects/{project_id}/work-items/{wid}/",
            json=body,
        )

    async def _work_item_payload(
        self, *, parent: str | None, **fields: Any
    ) -> dict[str, Any]:
        body: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        if parent is not None:
            body["parent"] = await self.resolve_work_item(parent)
        return body

    async def add_comment(
        self,
        project_id: str,
        work_item_ref: str,
        *,
        comment_html: str,
        access: str | None = None,
    ) -> dict[str, Any]:
        wid = await self.resolve_work_item(work_item_ref)
        body: dict[str, Any] = {"comment_html": comment_html}
        if access is not None:
            body["access"] = access
        return await self._pat_request(
            "POST",
            f"projects/{project_id}/work-items/{wid}/comments/",
            json=body,
        )

    async def list_comments(
        self, project_id: str, work_item_ref: str
    ) -> list[dict[str, Any]]:
        wid = await self.resolve_work_item(work_item_ref)
        return self._unwrap_list(
            await self._pat_request(
                "GET",
                f"projects/{project_id}/work-items/{wid}/comments/",
            )
        )

    async def delete_comment(
        self, project_id: str, work_item_ref: str, comment_id: str
    ) -> None:
        # Used by integration tests for cleanup. Not exposed as a tool —
        # agents should not delete each other's comments.
        wid = await self.resolve_work_item(work_item_ref)
        await self._pat_request(
            "DELETE",
            f"projects/{project_id}/work-items/{wid}/comments/{comment_id}/",
        )

    # ----- cycles (sprints) -----

    async def list_cycles(self, project_id: str) -> list[dict[str, Any]]:
        """List cycles (sprints) defined on a project."""
        return self._unwrap_list(
            await self._pat_request("GET", f"projects/{project_id}/cycles/")
        )

    async def retrieve_cycle(
        self, project_id: str, cycle_id: str
    ) -> dict[str, Any]:
        """Retrieve a single cycle by UUID (full metadata + progress)."""
        return await self._pat_request(
            "GET", f"projects/{project_id}/cycles/{cycle_id}/"
        )

    async def create_cycle(
        self,
        project_id: str,
        *,
        name: str,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Create a cycle. ``start_date`` / ``end_date`` are ISO
        ``YYYY-MM-DD``; Plane requires both dates together or neither.
        """
        body = {
            k: v
            for k, v in {
                "name": name,
                "description": description,
                "start_date": start_date,
                "end_date": end_date,
            }.items()
            if v is not None
        }
        return await self._pat_request(
            "POST", f"projects/{project_id}/cycles/", json=body
        )

    async def update_cycle(
        self,
        project_id: str,
        cycle_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Patch a cycle. Only non-None fields are sent, so a date-only
        reschedule does not blank the name.
        """
        body = {
            k: v
            for k, v in {
                "name": name,
                "description": description,
                "start_date": start_date,
                "end_date": end_date,
            }.items()
            if v is not None
        }
        return await self._pat_request(
            "PATCH", f"projects/{project_id}/cycles/{cycle_id}/", json=body
        )

    async def delete_cycle(self, project_id: str, cycle_id: str) -> None:
        """Delete a cycle. The work items it held are not deleted — they
        only leave the cycle. Irreversible; prefer transferring unfinished
        items to another cycle first.
        """
        await self._pat_request(
            "DELETE", f"projects/{project_id}/cycles/{cycle_id}/"
        )

    async def list_cycle_work_items(
        self, project_id: str, cycle_id: str
    ) -> list[dict[str, Any]]:
        """List the work items assigned to a cycle."""
        return self._unwrap_list(
            await self._pat_request(
                "GET",
                f"projects/{project_id}/cycles/{cycle_id}/cycle-issues/",
            )
        )

    async def add_work_items_to_cycle(
        self, project_id: str, cycle_id: str, work_item_refs: list[str]
    ) -> dict[str, Any]:
        """Add one or more work items to a cycle. Each ref accepts a UUID
        or human identifier (e.g. ``DEV-12``); resolved to UUIDs before
        the request. A work item lives in at most one cycle — adding it to
        a new cycle moves it.
        """
        issue_ids = [await self.resolve_work_item(r) for r in work_item_refs]
        return await self._pat_request(
            "POST",
            f"projects/{project_id}/cycles/{cycle_id}/cycle-issues/",
            json={"issues": issue_ids},
        )

    async def remove_work_item_from_cycle(
        self, project_id: str, cycle_id: str, work_item_ref: str
    ) -> None:
        """Remove a single work item from a cycle. ``work_item_ref``
        accepts a UUID or human identifier. The work item itself is not
        deleted.
        """
        wid = await self.resolve_work_item(work_item_ref)
        await self._pat_request(
            "DELETE",
            f"projects/{project_id}/cycles/{cycle_id}/cycle-issues/{wid}/",
        )

    async def transfer_cycle_work_items(
        self, project_id: str, cycle_id: str, new_cycle_id: str
    ) -> dict[str, Any]:
        """Transfer the *incomplete* work items of one cycle into another
        — Plane's "carry unfinished work into the next sprint" action.
        ``new_cycle_id`` is the destination cycle's UUID.
        """
        return await self._pat_request(
            "POST",
            f"projects/{project_id}/cycles/{cycle_id}/transfer-issues/",
            json={"new_cycle_id": new_cycle_id},
        )

    # ----- relations (blocked_by / blocking / duplicate / relates_to) -----
    #
    # Verified against Plane's public REST surface: the per-work-item
    # ``relations/`` collection supports GET and POST only (POST body:
    # ``{"relation_type": ..., "issues": [uuids]}``). There is no public
    # removal endpoint — deleting a relation stays a manual UI step.

    async def list_relations(
        self, project_id: str, work_item_ref: str
    ) -> dict[str, Any]:
        """Return the work item's relations grouped by type
        (``blocking`` / ``blocked_by`` / ``duplicate`` / ``relates_to``
        / ``start_*`` / ``finish_*``). ``work_item_ref`` accepts UUID
        or identifier.
        """
        wid = await self.resolve_work_item(work_item_ref)
        return await self._pat_request(
            "GET", f"projects/{project_id}/work-items/{wid}/relations/"
        )

    async def add_relation(
        self,
        project_id: str,
        work_item_ref: str,
        *,
        relation_type: str,
        related_work_item_refs: list[str],
    ) -> dict[str, Any]:
        """Add a relation from one work item to one or more others.
        ``relation_type`` is one of Plane's types (``blocked_by``,
        ``blocking``, ``duplicate``, ``relates_to``, ...); an invalid
        value is rejected by Plane with the list of valid choices.
        All refs accept UUID or identifier.
        """
        wid = await self.resolve_work_item(work_item_ref)
        related = [
            await self.resolve_work_item(r) for r in related_work_item_refs
        ]
        await self._pat_request(
            "POST",
            f"projects/{project_id}/work-items/{wid}/relations/",
            json={"relation_type": relation_type, "issues": related},
        )
        # Plane's POST response shape varies across versions; return a
        # summary we construct ourselves so callers get a stable shape.
        return {
            "work_item": wid,
            "relation_type": relation_type,
            "related": related,
        }

    # ----- modules (membership) -----
    #
    # Modules are created by humans (or Ansible), not by personas — the
    # team only assigns work items to an existing module. Unlike a cycle
    # (the *when* axis, at most one per item), a work item may belong to
    # several modules (the *who* axis), so adding to one module does not
    # remove it from another.

    async def list_module_work_items(
        self, project_id: str, module_id: str
    ) -> list[dict[str, Any]]:
        """List the work items assigned to a module."""
        return self._unwrap_list(
            await self._pat_request(
                "GET",
                f"projects/{project_id}/modules/{module_id}/module-issues/",
            )
        )

    async def add_work_items_to_module(
        self, project_id: str, module_id: str, work_item_refs: list[str]
    ) -> dict[str, Any]:
        """Add one or more work items to a module. Each ref accepts a UUID
        or human identifier (e.g. ``DEV-12``); resolved to UUIDs before
        the request. A work item may belong to several modules at once —
        adding it here leaves its other module memberships intact.
        """
        issue_ids = [await self.resolve_work_item(r) for r in work_item_refs]
        return await self._pat_request(
            "POST",
            f"projects/{project_id}/modules/{module_id}/module-issues/",
            json={"issues": issue_ids},
        )

    async def remove_work_item_from_module(
        self, project_id: str, module_id: str, work_item_ref: str
    ) -> None:
        """Remove a single work item from a module. ``work_item_ref``
        accepts a UUID or human identifier. The work item itself is not
        deleted, and its other module memberships are untouched.
        """
        wid = await self.resolve_work_item(work_item_ref)
        await self._pat_request(
            "DELETE",
            f"projects/{project_id}/modules/{module_id}/module-issues/{wid}/",
        )
