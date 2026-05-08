"""Async client for the subset of Plane endpoints this MCP needs.

Speaks Plane's public REST surface (`/api/v1/`, X-API-Key auth) only.
Used for comments and the workspace-scoped work-item lookup.

We previously also reached into Plane's internal app API (session-
cookie auth) to manage pages, because Plane v1.3.0 doesn't expose
pages on the public REST surface. The framework no longer uses pages
— every artefact lives in a work-item body or a comment — so the
internal-app fallback is gone, along with the PLANE_UI_USERNAME /
PLANE_UI_PASSWORD env vars it required.

Env vars:
- `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`, `PLANE_BASE_URL` — required.
- `PLANE_VERIFY_SSL`, `PLANE_CA_BUNDLE` — optional TLS controls.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

API_VERSION = "v1"
DEFAULT_BASE_URL = "https://api.plane.so"

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


class PlaneError(RuntimeError):
    """Raised when Plane returns an error status (>=400)."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"Plane API error {status_code}: {body[:500]}")
        self.status_code = status_code
        self.body = body


class PlaneClient:
    """Async client for Plane's public REST surface (X-API-Key auth)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        workspace_slug: str | None = None,
        base_url: str | None = None,
        verify: str | bool | None = None,
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
        self._pat_client: httpx.AsyncClient | None = None

    @property
    def pat_client(self) -> httpx.AsyncClient:
        if self._pat_client is None:
            self._pat_client = httpx.AsyncClient(
                headers={"X-API-Key": self.api_key},
                timeout=30.0,
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
        self, method: str, path: str, *, json: Any = None
    ) -> Any:
        response = await self.pat_client.request(
            method, self._pat_url(path), json=json
        )
        if response.status_code >= 400:
            raise PlaneError(response.status_code, response.text)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

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
