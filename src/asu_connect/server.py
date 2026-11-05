"""
ASU Connect MCP server entry point.

Start with:
    python -m asu_connect.server

Or via the fastmcp CLI:
    fastmcp run src/asu_connect/server.py
"""
from __future__ import annotations

import sys

# Import the shared mcp instance first — tool modules register on it
from asu_connect.app import mcp  # noqa: F401

# Import tool modules so their @mcp.tool() decorators fire against the shared instance
import asu_connect.tools.estimate_transfer_credits  # noqa: F401
import asu_connect.tools.find_programs              # noqa: F401
import asu_connect.tools.check_nondegree_options    # noqa: F401

if __name__ == "__main__":
    print("ASU Connect MCP server starting…", file=sys.stderr)
    mcp.run()
