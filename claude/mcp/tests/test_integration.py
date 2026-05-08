"""Integration tests — require a live Plane instance.

Loads `mcp/.env.test` (gitignored). The whole suite is skipped if the
required env vars are missing or still placeholders.

Cleanup policy:
- Comments are deleted by the tests that create them.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import AsyncIterator

import pytest
from dotenv import load_dotenv

from plane_extras_mcp.plane import PlaneClient, PlaneError

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env.test"
load_dotenv(_ENV_FILE)

_REQUIRED = (
    "PLANE_API_KEY",
    "PLANE_WORKSPACE_SLUG",
    "PLANE_BASE_URL",
    "PLANE_TEST_PROJECT_ID",
    "PLANE_TEST_ISSUE_ID",
)
_PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"

_missing = [v for v in _REQUIRED if not os.environ.get(v)]
_placeholders = [
    v for v in ("PLANE_TEST_PROJECT_ID", "PLANE_TEST_ISSUE_ID")
    if os.environ.get(v) == _PLACEHOLDER_UUID
]
_skip_reason = (
    f"missing env vars: {_missing}" if _missing
    else f"placeholder UUIDs still in .env.test: {_placeholders}"
    if _placeholders
    else None
)
pytestmark = pytest.mark.skipif(
    _skip_reason is not None, reason=_skip_reason or ""
)


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


@pytest.fixture
async def client() -> AsyncIterator[PlaneClient]:
    async with PlaneClient() as c:
        yield c


@pytest.fixture
def project_id() -> str:
    return os.environ["PLANE_TEST_PROJECT_ID"]


@pytest.fixture
def work_item_id() -> str:
    return os.environ["PLANE_TEST_ISSUE_ID"]


# ----- comments (public REST, X-API-Key) -----


async def test_add_list_delete_comment(
    client: PlaneClient, project_id: str, work_item_id: str
) -> None:
    body = f"<p>integration-test comment {_stamp()}</p>"
    created = await client.add_comment(
        project_id, work_item_id, comment_html=body
    )
    comment_id = created["id"]

    try:
        comments = await client.list_comments(project_id, work_item_id)
        assert any(c["id"] == comment_id for c in comments), (
            f"new comment {comment_id} not found in list"
        )
    finally:
        await client.delete_comment(project_id, work_item_id, comment_id)


async def test_plane_error_carries_status(
    client: PlaneClient, project_id: str
) -> None:
    """Sanity check: error responses surface as PlaneError with status.

    Uses an obviously-invalid identifier so the work-item lookup itself
    fails before any project-scoped call is made.
    """
    with pytest.raises(PlaneError) as exc_info:
        await client.list_comments(project_id, "BOGUS-999999")
    # Plane returns 403 for non-existent identifiers; some versions/
    # endpoints return 400 or 404.
    assert 400 <= exc_info.value.status_code < 500
