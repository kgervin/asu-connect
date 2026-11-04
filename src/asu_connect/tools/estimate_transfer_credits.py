"""
Tool: estimate_transfer_credits

Estimates how community-college or university credits transfer to an ASU degree.
Rules derived from ASU's public admission website:
  https://admission.asu.edu/apply/transfer/transferring-credits

Key real-world constraints reflected here:
  - Community colleges: max 64 lower-division semester hours accepted
  - Four-year universities: unlimited
  - Remedial/developmental courses do not transfer
  - Grade of C- or better required
  - Individual course applicability is determined by the college of your major
    AFTER admission — this tool provides an estimate with four categories:
      1. direct_equivalency  — confirmed ASU equivalent via Transfer Guide
      2. general_elective    — transfers as credit, no specific ASU equivalent
      3. requires_evaluation — may transfer; needs advisor review
      4. not_transferable    — does not transfer
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from asu_connect.middleware import ValidationError, check_rate_limit, log_call, validate_input
from asu_connect.response import ADVISOR_URL, err, ok
from asu_connect.server import mcp

_DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "transfer_rules.json"


def _load_rules() -> dict[str, Any]:
    with open(_DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def estimate_transfer_credits(
    institution_type: str,
    credits_completed: int,
    courses: list[dict[str, str]] | None = None,
    client_id: str = "anonymous",
) -> dict[str, Any]:
    """
    Estimate how many of a student's transfer credits will apply toward an ASU degree.

    Use this tool when a student wants to know how their existing college credits
    will count at ASU — for example, a community-college transfer student asking
    how many credits they still need to graduate.

    Important: ASU's college of your major makes the final determination on how
    credits apply to your specific degree. This tool provides an estimate across
    four categories: direct equivalency, general elective, requires evaluation,
    and not transferable.

    Args:
        institution_type: Where the student earned their credits.
                          Use "community_college" for 2-year colleges,
                          or "four_year_university" for 4-year institutions.
        credits_completed: Total number of credits the student has completed.
        courses: Optional list of individual courses. Each item should have
                 "code" (e.g. "ENG 101"), "title", and "grade" (e.g. "A", "B+").
                 Courses with grades below C- are flagged as not transferable.
        client_id: Optional identifier for rate-limiting (does not need to be personal).

    Returns:
        Estimated credit breakdown across four ASU transfer categories,
        the 64-credit community-college cap if applicable, credits remaining,
        and what requires individual advisor evaluation.
        Always includes a source URL and a disclaimer.
    """
    # ── Validate inputs ──────────────────────────────────────────────────────
    try:
        validate_input({"institution_type": institution_type, "client_id": client_id})
        if courses:
            for course in courses:
                validate_input(course)
        check_rate_limit(client_id)
    except ValidationError as exc:
        log_call("estimate_transfer_credits", "validation_error")
        return err(str(exc), "Check your input and try again.")

    # ── Load data ────────────────────────────────────────────────────────────
    rules = _load_rules()
    institution_data = rules["institution_types"].get(institution_type)

    if institution_data is None:
        log_call("estimate_transfer_credits", "not_found")
        supported = ", ".join(rules["institution_types"].keys())
        return err(
            f"Institution type '{institution_type}' was not found in our records.",
            f"Try one of: {supported}. Or contact an ASU advisor for a full evaluation.",
            ADVISOR_URL,
        )

    # ── Apply credit cap (64 hrs for community college) ──────────────────────
    max_transfer = institution_data["max_total_transfer_credits"]  # None = unlimited
    capped = max_transfer is not None
    transferable = min(credits_completed, max_transfer) if capped else credits_completed
    capped_credits = credits_completed - transferable  # credits lost to the cap

    # ── Identify courses below C- from optional list ─────────────────────────
    below_grade_courses: list[str] = []
    _failing_grades = {"d+", "d", "d-", "f", "w", "wf", "i"}
    if courses:
        for c in courses:
            grade = c.get("grade", "").strip().lower()
            if grade in _failing_grades:
                below_grade_courses.append(c.get("code", c.get("title", "unknown")))

    # ── Estimate categories ───────────────────────────────────────────────────
    est = institution_data["estimation_rules"]
    direct = math.floor(transferable * est["direct_equivalency_fraction"])
    elective = math.floor(transferable * est["general_elective_fraction"])
    needs_eval = math.floor(transferable * est["requires_evaluation_fraction"])
    not_transferable = transferable - direct - elective - needs_eval  # remainder

    degree_credits = rules["degree_total_credits"]
    # Only direct equivalency and elective count toward remaining credits
    credits_applied = direct + elective
    credits_remaining = max(0, degree_credits - credits_applied)

    # ── Build flags ───────────────────────────────────────────────────────────
    flags: list[str] = []
    if below_grade_courses:
        flags.append(
            f"Heads up: {len(below_grade_courses)} course(s) appear below C- "
            f"({', '.join(below_grade_courses)}) and will not transfer to ASU."
        )
    if capped_credits > 0:
        flags.append(
            f"ASU's 64-credit community-college cap means {capped_credits} of your "
            f"credits cannot be accepted as lower-division transfer credit."
        )
    if needs_eval > 0:
        flags.append(
            f"About {needs_eval} credits will need individual evaluation by your college "
            f"advisor — these may include older coursework or non-standard credit units."
        )

    log_call("estimate_transfer_credits", "ok")
    return ok(
        bottom_line=(
            f"You need {credits_remaining} more credits to finish your degree — "
            f"about {credits_applied} of your {transferable} transferable credits apply to ASU, "
            f"and {needs_eval} more need individual advisor evaluation."
        ),
        summary=(
            f"Based on your {institution_data['label']} credits, roughly {direct} credits "
            f"have direct ASU equivalents, {elective} count as general electives, "
            f"{needs_eval} need evaluation, and {not_transferable} are not transferable. "
            f"Your college advisor makes the final call after admission."
        ),
        data={
            "credits_submitted": credits_completed,
            "credits_accepted_under_cap": transferable,
            "credits_lost_to_cap": capped_credits,
            "estimated_breakdown": {
                "direct_equivalency": direct,
                "general_elective": elective,
                "requires_individual_evaluation": needs_eval,
                "not_transferable": not_transferable,
            },
            "credits_applied_toward_degree": credits_applied,
            "credits_remaining": credits_remaining,
            "degree_total_credits": degree_credits,
            "institution_type": institution_data["label"],
            "community_college_cap": max_transfer,
            "individual_evaluation_required": institution_data["individual_evaluation_required"],
            "evaluation_note": institution_data["evaluation_note"],
            "flags": flags,
            "courses_below_grade": below_grade_courses,
        },
        source=rules["source_url"],
        next_steps=[
            "Look up your specific courses at transferguide.apps.asu.edu to confirm direct equivalencies.",
            "Use MyPath2ASU at admission.asu.edu/apply/transfer/MyPath2ASU to map credits to your major.",
            "Contact an ASU admissions advisor at admission.asu.edu/contact for an official evaluation.",
            "Apply for admission at admission.asu.edu — your college advisor finalises credit applicability after admission.",
        ],
        data_version=rules["data_version"],
    )
