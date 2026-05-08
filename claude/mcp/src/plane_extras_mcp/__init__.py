"""Supplementary MCP server for Plane.

Exposes the work-item comments, pages, and page-link tools that the
official Plane MCP server (makeplane/plane-mcp-server) does not yet
provide.
"""

import truststore

# Make Python's ssl module honor the host's system trust store. Without
# this, httpx falls back to certifi's bundle and ignores any private CA
# the operator has imported into the system. Idempotent and process-local.
truststore.inject_into_ssl()

__version__ = "0.2.0"
