"""FastMCP server exposing supplementary Plane tools.

Covers the gap between Plane's official MCP server (projects, work
items, cycles, modules, initiatives) and the operations the
Trail agent workflow needs: comments on work items.

All tools use Plane's public REST surface with X-API-Key auth. The
framework does not use Plane pages; every persona artefact lives in
a work-item body or a comment.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .plane import PlaneClient

mcp = FastMCP("plane-extras")


# ----- comments -----


@mcp.tool()
async def add_comment(
    project_id: str,
    work_item_id: str,
    comment_html: str,
    access: str | None = None,
) -> dict[str, Any]:
    """Add a comment to a Plane work item.

    Args:
        project_id: UUID of the project containing the work item.
        work_item_id: Either the work item's UUID or its human-readable
            identifier as shown in the Plane UI (e.g. ``INT-1``).
        comment_html: Comment body, HTML-formatted.
        access: Optional. Newer Plane versions accept ``"internal"`` /
            ``"external"``; older versions reject the field. Omit to
            use Plane's default.
    """
    async with PlaneClient() as client:
        return await client.add_comment(
            project_id,
            work_item_id,
            comment_html=comment_html,
            access=access,
        )


@mcp.tool()
async def list_comments(
    project_id: str, work_item_id: str
) -> list[dict[str, Any]]:
    """List comments on a Plane work item, in the order Plane returns them.

    `work_item_id` accepts either the UUID or the human-readable
    identifier (e.g. ``INT-1``).
    """
    async with PlaneClient() as client:
        return await client.list_comments(project_id, work_item_id)


def main() -> None:
    """Entry point for `python -m plane_extras_mcp` and the
    `plane-extras-mcp` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
