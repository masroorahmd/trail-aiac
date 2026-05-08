#!/usr/bin/env python
"""Diagnostic: probe several Plane URL patterns to find what works.

Prints HTTP status code per probe — no response bodies, no secrets.
Reads `.env.test` from the parent directory. Use this when integration
tests fail with 404s to find out which URL convention the target Plane
instance uses.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
import truststore
from dotenv import load_dotenv

truststore.inject_into_ssl()
load_dotenv(Path(__file__).resolve().parent.parent / ".env.test")

REQUIRED = (
    "PLANE_BASE_URL",
    "PLANE_WORKSPACE_SLUG",
    "PLANE_API_KEY",
    "PLANE_TEST_PROJECT_ID",
    "PLANE_TEST_ISSUE_ID",
)
missing = [v for v in REQUIRED if not os.environ.get(v)]
if missing:
    sys.exit(f"missing env vars: {missing}")

base = os.environ["PLANE_BASE_URL"].rstrip("/")
slug = os.environ["PLANE_WORKSPACE_SLUG"]
key = os.environ["PLANE_API_KEY"]
pid = os.environ["PLANE_TEST_PROJECT_ID"]
iid = os.environ["PLANE_TEST_ISSUE_ID"]


def url(path: str) -> str:
    return f"{base}/api/v1/workspaces/{slug}{path}"


PROBES = [
    ("workspace projects (list)", "GET", url("/projects/")),
    ("project detail", "GET", url(f"/projects/{pid}/")),
    ("issues list (legacy URL)", "GET", url(f"/projects/{pid}/issues/")),
    ("work-items list (new URL)", "GET", url(f"/projects/{pid}/work-items/")),
    ("issue detail", "GET", url(f"/projects/{pid}/issues/{iid}/")),
    ("work-item detail", "GET", url(f"/projects/{pid}/work-items/{iid}/")),
    (
        "issue comments (legacy)",
        "GET",
        url(f"/projects/{pid}/issues/{iid}/comments/"),
    ),
    (
        "work-item comments (new)",
        "GET",
        url(f"/projects/{pid}/work-items/{iid}/comments/"),
    ),
    ("project pages", "GET", url(f"/projects/{pid}/pages/")),
    ("workspace pages", "GET", url("/pages/")),
    ("project wiki-pages (alt)", "GET", url(f"/projects/{pid}/wiki/pages/")),
    (
        "issue page-links (legacy)",
        "GET",
        url(f"/projects/{pid}/issues/{iid}/page-links/"),
    ),
    (
        "work-item page-links (new)",
        "GET",
        url(f"/projects/{pid}/work-items/{iid}/page-links/"),
    ),
    ("instance info", "GET", f"{base}/api/v1/instances/"),
    ("current user", "GET", f"{base}/api/v1/users/me/"),
]


async def main() -> None:
    headers = {"X-API-Key": key}
    async with httpx.AsyncClient(headers=headers, timeout=15.0) as c:
        print("URL probes (status codes only):")
        for name, method, full in PROBES:
            try:
                r = await c.request(method, full)
                print(f"  [{r.status_code}] {name}")
            except Exception as e:
                print(f"  [ERR] {name}: {type(e).__name__}: {e}")

        # Probe identifier-based endpoints if we can derive one.
        print("\nIdentifier-based probes:")
        r_proj = await c.get(url(f"/projects/{pid}/"))
        proj_ident = (
            r_proj.json().get("identifier") if r_proj.status_code == 200 else None
        )
        r = await c.get(url(f"/projects/{pid}/work-items/"))
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                first = results[0]
                seq = first.get("sequence_id")
                if proj_ident and seq is not None:
                    ident = f"{proj_ident}-{seq}"
                    print(f"  derived identifier: {ident}")
                    ident_probes = [
                        (
                            "work-item by identifier (workspace-scoped)",
                            f"{base}/api/v1/workspaces/{slug}/work-items/{ident}/",
                        ),
                        (
                            "work-item by identifier (project-scoped)",
                            url(f"/projects/{pid}/work-items/{ident}/"),
                        ),
                        (
                            "comments via identifier (workspace-scoped)",
                            f"{base}/api/v1/workspaces/{slug}/work-items/{ident}/comments/",
                        ),
                        (
                            "comments via identifier (project-scoped)",
                            url(f"/projects/{pid}/work-items/{ident}/comments/"),
                        ),
                    ]
                    for name, full in ident_probes:
                        try:
                            r2 = await c.get(full)
                            print(f"  [{r2.status_code}] {name}")
                        except Exception as e:
                            print(f"  [ERR] {name}: {type(e).__name__}")

                    # Resolve to UUID via the workspace-scoped lookup,
                    # then re-probe project-scoped endpoints with the
                    # *real* UUID.
                    r_resolve = await c.get(
                        f"{base}/api/v1/workspaces/{slug}/work-items/{ident}/"
                    )
                    if r_resolve.status_code == 200:
                        real_uuid = r_resolve.json().get("id")
                        print(f"\n  resolved {ident} → {real_uuid}")
                        with_uuid = [
                            (
                                "work-item detail (real UUID)",
                                url(f"/projects/{pid}/work-items/{real_uuid}/"),
                            ),
                            (
                                "comments list (real UUID)",
                                url(
                                    f"/projects/{pid}/work-items/"
                                    f"{real_uuid}/comments/"
                                ),
                            ),
                            (
                                "page-links list (real UUID)",
                                url(
                                    f"/projects/{pid}/work-items/"
                                    f"{real_uuid}/page-links/"
                                ),
                            ),
                            (
                                "issues comments list (real UUID, legacy)",
                                url(
                                    f"/projects/{pid}/issues/"
                                    f"{real_uuid}/comments/"
                                ),
                            ),
                        ]
                        for name, full in with_uuid:
                            try:
                                r3 = await c.get(full)
                                print(f"  [{r3.status_code}] {name}")
                            except Exception as e:
                                print(f"  [ERR] {name}: {type(e).__name__}")
                else:
                    print(
                        "  (could not derive identifier — fields missing "
                        f"in work-item payload; keys: "
                        f"{sorted(first.keys())})"
                    )
            else:
                print("  (no work items to derive identifier from)")

        # Show a few real work-item UUIDs in the test project, so the
        # operator can verify / replace PLANE_TEST_ISSUE_ID without
        # leaving the terminal. Titles are NOT printed.
        print("\nFirst few work-item UUIDs in the test project:")
        r = await c.get(url(f"/projects/{pid}/work-items/"))
        if r.status_code == 200:
            items = r.json().get("results", [])[:5]
            if not items:
                print("  (no work items yet)")
            for it in items:
                print(f"  {it.get('id')}")
        else:
            print(f"  (could not list: status {r.status_code})")

        # Project features — useful to see whether Pages is enabled.
        print("\nProject features:")
        r = await c.get(url(f"/projects/{pid}/features/"))
        if r.status_code == 200:
            for k, v in sorted(r.json().items()):
                print(f"  {k}: {v}")
        else:
            print(f"  (could not fetch: status {r.status_code})")


asyncio.run(main())
