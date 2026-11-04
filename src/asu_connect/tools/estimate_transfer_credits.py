"""
Tool: estimate_transfer_credits

Estimates how many community-college or university credits will transfer to an ASU degree.
All figures are derived from versioned mock data — never generated or guessed.
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

    Args:
        institution_type: Where the student earned their credits.
                          Use "community_college" for 2-year colleges,
                          or "four_year_university" for 4-year institutions.
        credits_completed: Total number of credits the student has completed.
        courses: Optional list of individual courses. Each item should have
                 "code" (e.g. "ENG 101"), "title", and "grade" (e.g. "A", "B+").
        client_id: Optional identifier for rate-limiting (does not need to be personal).

    Returns:
        Estimated applied, elective, and non-transferable credit counts,
        plus how many credits remain toward a 120-credit degree.
        Always includes a source URL and a disclaimer.
    """
    # ── Validate inputs ──────────────────────────────────────────────────────
    try:
        validate_input({
            "institution_type": institution_type,
            "client_id": client_id,
        })
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

    # ── Estimate credits ─────────────────────────────────────────────────────
    est = institution_data["estimation_rules"]
    max_transfer = institution_data["max_total_transfer_credits"]
    transferable = min(credits_completed, max_transfer)

    applied = math.floor(transferable * est["applied_fraction"])
    elective = math.floor(transferable * est["elective_fraction"])
    not_transferable = credits_completed - transferable + math.ceil(
        transferable * est["not_transferable_fraction"]
    )
    # Reconcile so applied + elective ≤ transferable
    applied = min(applied, institution_data["max_applied_credits"])
    degree_credits = rules["degree_total_credits"]
    credits_remaining = max(0, degree_credits - applied - elective)

    log_call("estimate_transfer_credits", "ok")
    return ok(
        bottom_line=(
            f"You need {credits_remaining} more credits to finish your degree — "
            f"{applied + elective} of your {transferable} transferable credits apply to ASU."
        ),
        summary=(
            f"Based on your {institution_data['label']} credits, you can transfer up to "
            f"{applied + elective} credits to ASU, with about {credits_remaining} credits "
            f"remaining toward a {degree_credits}-credit degree."
        ),
        data={
            "credits_submitted": credits_completed,
            "credits_transferable": transferable,
            "applied_credits": applied,
            "elective_credits": elective,
            "not_transferable_credits": not_transferable,
            "credits_remaining": credits_remaining,
            "degree_total_credits": degree_credits,
            "institution_type": institution_data["label"],
            "max_applied_credits": institution_data["max_applied_credits"],
        },
        source=rules["source_url"],
        next_steps=[
            "Visit transfercredit.asu.edu to look up your specific courses in the transfer guide.",
            "Contact an ASU admissions advisor to get an official credit evaluation.",
            "Apply for admission at admission.asu.edu once you know your transfer standing.",
        ],
        data_version=rules["data_version"],
    )
