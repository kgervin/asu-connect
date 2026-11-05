"""
Tool: find_programs

Searches ASU online degree programs by keyword, modality, and schedule.
All data comes from the versioned programs.json data file — no generated figures.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from asu_connect.middleware import ValidationError, check_rate_limit, log_call, validate_input
from asu_connect.response import clarify, err, ok
from asu_connect.server import mcp

_DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "programs.json"


def _load_programs() -> dict[str, Any]:
    with open(_DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def find_programs(
    goal: str,
    modality: str | None = "online",
    schedule: str | None = None,
    max_results: int = 5,
    client_id: str = "anonymous",
) -> dict[str, Any]:
    """
    Search ASU degree programs that match a student's goal, preferred modality, and schedule.

    Use this tool when a student asks which degree programs are available at ASU,
    wants to filter by online vs. in-person, or wants to compare programs by cost and duration.

    Args:
        goal: A free-text description of what the student wants to study or do.
              Examples: "construction management", "data analytics", "business leadership".
        modality: How the student wants to attend. Use "online" for fully online programs,
                  "in_person" for on-campus, or leave blank to see all options.
        schedule: "part_time" or "full_time". Leave blank to see both.
        max_results: Maximum number of programs to return (1–10, default 5).
        client_id: Optional identifier for rate-limiting.

    Returns:
        A list of matching ASU programs with name, degree type, total credits,
        estimated duration, cost per credit, and a link to the program page.
    """
    # ── Personalisation: ask if goal is too vague to match confidently ────────
    if not goal or not goal.strip():
        log_call("find_programs", "clarification_needed")
        return clarify(
            question="What would you like to study or do with your degree?",
            why="A degree goal helps narrow down the right ASU program for you. Without it, I'd return every program we have.",
            options=[
                "Construction management",
                "Business or organizational leadership",
                "Data analytics or technology",
                "Psychology or behavioral science",
                "Communications or media",
                "Something else — describe it in a few words",
            ],
        )

    # ── Validate inputs ──────────────────────────────────────────────────────
    try:
        validate_input({"goal": goal, "client_id": client_id})
        if modality is not None:
            validate_input({"modality": modality})
        if schedule is not None:
            validate_input({"schedule": schedule})
        max_results = max(1, min(int(max_results), 10))
        check_rate_limit(client_id)
    except ValidationError as exc:
        log_call("find_programs", "validation_error")
        return err(str(exc), "Check your input and try again.")

    # ── Load and filter ──────────────────────────────────────────────────────
    catalog = _load_programs()
    programs = catalog["programs"]
    keyword = goal.lower().strip()

    results = []
    for program in programs:
        # Modality filter
        if modality and program.get("modality") != modality:
            continue
        # Schedule filter
        if schedule and schedule not in program.get("schedule", []):
            continue
        # Keyword match against name and tags (case-insensitive substring)
        searchable = " ".join([program["name"].lower()] + [t.lower() for t in program.get("tags", [])])
        if keyword and keyword not in searchable:
            # Try matching any individual word of the goal
            if not any(word in searchable for word in keyword.split() if len(word) > 2):
                continue
        results.append(program)
        if len(results) >= max_results:
            break

    if not results:
        log_call("find_programs", "clarification_needed")
        return clarify(
            question=f"No programs matched '{goal}'. Can you describe your goal differently?",
            why="A broader or differently worded goal may match more programs. For example, 'construction' instead of 'civil construction'.",
            options=[
                "Try a broader term — e.g. 'management' instead of 'construction project management'",
                "Remove the schedule or modality filter to see all programs",
                "Browse all programs at asuonline.asu.edu",
                "Contact an ASU advisor at admission.asu.edu/contact",
            ],
        )

    # Build output records (most important facts first — Netflix pattern)
    output_programs = []
    for p in results:
        total_cost = p["total_credits"] * p["cost_per_credit_usd"]
        output_programs.append({
            "name": p["name"],
            "degree_type": p["degree_type"],
            "total_credits": p["total_credits"],
            "cost_per_credit_usd": p["cost_per_credit_usd"],
            "estimated_total_cost_usd": total_cost,
            "typical_duration_years": p["typical_duration_years"],
            "typical_duration_part_time_years": p["typical_duration_part_time_years"],
            "modality": p["modality"],
            "source_url": p["source_url"],
        })

    log_call("find_programs", "ok")
    best = output_programs[0]
    return ok(
        bottom_line=(
            f"Your best match is {best['name']} — {best['total_credits']} credits online "
            f"at ${best['cost_per_credit_usd']}/credit (${best['estimated_total_cost_usd']:,} total)."
        ),
        summary=(
            f"Found {len(output_programs)} ASU program(s) matching '{goal}'. "
            f"The closest match is {best['name']} ({best['degree_type']}, "
            f"{best['total_credits']} credits, ${best['cost_per_credit_usd']}/credit)."
        ),
        data={"programs": output_programs},
        source=catalog["source_url"],
        next_steps=[
            f"Visit {output_programs[0]['source_url']} to explore the top match in detail.",
            "Use estimate_transfer_credits to see how your existing credits apply.",
            "Contact an ASU advisor at admission.asu.edu to confirm program fit.",
        ],
        data_version=catalog["data_version"],
    )
