"""
Tool: check_nondegree_options

Finds ASU non-degree (open enrollment) classes a student can take next term
without applying for full admission. Returns itemized tuition and registration steps.
All data comes from the versioned nondegree_options.json file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from asu_connect.middleware import ValidationError, check_rate_limit, log_call, validate_input
from asu_connect.response import clarify, err, ok
from asu_connect.server import mcp

_DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "nondegree_options.json"


def _load_courses() -> dict[str, Any]:
    with open(_DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def check_nondegree_options(
    course_interest: str,
    term: str = "Spring 2027",
    client_id: str = "anonymous",
) -> dict[str, Any]:
    """
    Find ASU classes a student can take right now without applying for a full degree.

    Use this tool when a student wants to try a course before committing to a degree,
    needs to know the exact cost of a class, or wants step-by-step registration instructions.

    Args:
        course_interest: What the student wants to study.
                         Examples: "construction management", "data analytics", "business".
        term: The term they want to enroll in. Examples: "Spring 2027", "Fall 2027".
              Defaults to "Spring 2027".
        client_id: Optional identifier for rate-limiting.

    Returns:
        A list of open classes matching the interest and term, with itemized tuition,
        available seats, total cost, and step-by-step registration instructions.
    """
    # ── Personalisation: ask if course interest is too vague ─────────────────
    if not course_interest or not course_interest.strip():
        log_call("check_nondegree_options", "clarification_needed")
        return clarify(
            question="What subject are you interested in taking a class in?",
            why="Knowing your subject area helps me find open classes with available seats and show you the exact cost.",
            options=[
                "Construction management",
                "Business or management",
                "Data or technology",
                "Something else — describe it in a few words",
            ],
        )

    # ── Validate inputs ──────────────────────────────────────────────────────
    try:
        validate_input({"course_interest": course_interest, "term": term, "client_id": client_id})
        check_rate_limit(client_id)
    except ValidationError as exc:
        log_call("check_nondegree_options", "validation_error")
        return err(str(exc), "Check your input and try again.")

    # ── Load and filter ──────────────────────────────────────────────────────
    catalog = _load_courses()
    keyword = course_interest.lower().strip()
    term_lower = term.lower().strip()

    matches = []
    for course in catalog["courses"]:
        # Term filter
        offered = [t.lower() for t in course.get("terms_offered", [])]
        if term_lower not in offered:
            continue
        # Seats filter
        if course.get("open_seats", 0) <= 0:
            continue
        # Keyword match against title and tags
        searchable = " ".join(
            [course["title"].lower(), course.get("description", "").lower()]
            + [t.lower() for t in course.get("tags", [])]
        )
        if keyword and keyword not in searchable:
            if not any(word in searchable for word in keyword.split() if len(word) > 2):
                continue
        matches.append(course)

    if not matches:
        log_call("check_nondegree_options", "clarification_needed")
        return clarify(
            question=f"No open classes matched '{course_interest}' for {term}. Would a different term or subject work?",
            why="Class availability and open seats change each term. Trying a different term or a broader subject may find options.",
            options=[
                "Try a different term — e.g. 'Fall 2027' or 'Summer 2027'",
                "Try a broader subject — e.g. 'management' instead of a specific topic",
                "Browse all non-degree courses at nondegree.asu.edu",
                "Contact ASU non-degree enrollment at nondegree.asu.edu/contact",
            ],
        )

    # Build output records with itemized cost (most important facts first)
    output_courses = []
    for c in matches:
        tuition_total = c["credits"] * c["tuition_per_credit_usd"]
        fees_total = sum(c["fees"].values())
        total_cost = tuition_total + fees_total
        output_courses.append({
            "course_code": c["course_code"],
            "title": c["title"],
            "credits": c["credits"],
            "term": term,
            "open_seats": c["open_seats"],
            "tuition_per_credit_usd": c["tuition_per_credit_usd"],
            "tuition_total_usd": tuition_total,
            "fees_itemized": c["fees"],
            "fees_total_usd": fees_total,
            "total_cost_usd": total_cost,
            "registration_steps": c["registration_steps"],
            "source_url": c["source_url"],
        })

    log_call("check_nondegree_options", "ok")
    best = output_courses[0]
    return ok(
        bottom_line=(
            f"You can start {best['title']} ({best['course_code']}) this {term} "
            f"for ${best['total_cost_usd']:.0f} — no application required, {best['open_seats']} seats open."
        ),
        summary=(
            f"Found {len(output_courses)} non-degree class(es) matching '{course_interest}' "
            f"for {term}. {best['title']} ({best['course_code']}) has {best['open_seats']} "
            f"seats open and costs ${best['total_cost_usd']:.0f} total."
        ),
        data={"courses": output_courses},
        source=catalog["source_url"],
        next_steps=[
            f"Visit {best['source_url']} for full course details.",
            f"Follow the {len(best['registration_steps'])}-step registration process listed above.",
            "Contact ASU non-degree enrollment at nondegree.asu.edu/contact if you have questions.",
        ],
        data_version=catalog["data_version"],
    )
