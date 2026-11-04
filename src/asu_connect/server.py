"""
ASU Connect MCP server entry point.

Start with:
    python -m asu_connect.server

Or via the fastmcp CLI:
    fastmcp run src/asu_connect/server.py
"""
from __future__ import annotations

import sys

from fastmcp import FastMCP

# ── Server instance ────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="asu-connect",
    instructions=(
        "ASU Connect gives you accurate, source-cited information about Arizona State University "
        "programs, transfer credit estimates, and non-degree class options. "
        "Use estimate_transfer_credits to evaluate transfer credits, "
        "find_programs to search degree programs, and "
        "check_nondegree_options to find individual classes a student can take now. "
        "All figures are estimates from mock data — advise students to verify with an ASU advisor."
    ),
)

# ── Register tools (importing the modules causes the @mcp.tool decorators to fire)
from asu_connect.tools import estimate_transfer_credits  # noqa: E402, F401
from asu_connect.tools import find_programs              # noqa: E402, F401
from asu_connect.tools import check_nondegree_options    # noqa: E402, F401

if __name__ == "__main__":
    print("ASU Connect MCP server starting…", file=sys.stderr)
    mcp.run()
