"""
Shared FastMCP application instance.

Imported by all tool modules so they register on the same instance
regardless of how the server is launched (python -m, fastmcp run, or import).
"""
from __future__ import annotations

from fastmcp import FastMCP

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
