"""
Tool: estimate_transfer_credits

Shows how a student's own courses line up with ASU transfer rules.

Who provides what
-----------------
- The STUDENT provides their course history (transcript or course list with institution,
  credits and grades). ASU has no transcript data until the student shares it, so this
  tool never invents courses, credits, grades or a credit breakdown.
- The CONNECTOR provides ASU data only: transfer cap, grade rules, remedial rule,
  course equivalencies and degree total.

Behavior
--------
1. Courses provided   -> each course is checked against ASU rules and equivalencies.
2. Only a credit total -> the tool says it cannot break credits down, shares the ASU rules
                          that apply anyway (cap, degree total) and asks for the courses.
3. Nothing provided   -> the tool asks for a transcript or course list.

Rules come from ASU's public admission website:
  https://admission.asu.edu/apply/transfer/transferring-credits
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypedDict

from asu_connect.app import mcp
from asu_connect.middleware import ValidationError, check_rate_limit, log_call, validate_input
from asu_connect.response import clarify, err, ok

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_RULES_FILE = _DATA_DIR / "transfer_rules.json"
_EQUIV_FILE = _DATA_DIR / "course_equivalencies.json"

_COURSE_FORMAT = (
    "For each course: institution, course code, title, credits, and grade "
    "(e.g. 'Mesa Community College, ENG 101, English Composition, 3 credits, A')."
)


class CourseInput(TypedDict, total=False):
    """One course from the student's own transcript or course list."""
    institution: str  # where the student took it, e.g. "Mesa Community College"
    code: str         # course code as shown on the transcript, e.g. "ENG 101"
    title: str        # course title, e.g. "English Composition"
    credits: float    # semester credits earned, e.g. 3
    grade: str        # letter grade as shown, e.g. "B+", "P", "W"


def _load(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _norm_code(code: str | None) -> str:
    return re.sub(r"\s+", "", (code or "").upper())


def _course_number(code: str) -> int | None:
    match = re.search(r"(\d{2,3})", code or "")
    return int(match.group(1)) if match else None


def _parse_credits(value: Any) -> float | None:
    try:
        credits = float(value)
    except (TypeError, ValueError):
        return None
    return credits if 0 < credits <= 12 else None


def _fmt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


def _find_institution(name: str | None, equivalencies: dict[str, Any]) -> dict[str, Any] | None:
    key = _norm(name)
    if not key:
        return None
    for inst in equivalencies["institutions"]:
        if key == _norm(inst["name"]) or key in inst.get("aliases", []):
            return inst
    return None


def _cap_rules(rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "community_college_max_credits": rules["institution_types"]["community_college"]["max_total_transfer_credits"],
        "four_year_university_max_credits": "no cap",
        "minimum_grade": rules["eligibility_rules"]["minimum_grade"],
        "remedial_courses_transfer": rules["eligibility_rules"]["remedial_courses_transfer"],
        "degree_total_credits": rules["degree_total_credits"],
    }


def _ask_for_courses(
    rules: dict[str, Any],
    credits_completed: int | None,
    institution_type: str | None,
) -> dict[str, Any]:
    """No course list: say what can't be known, share ASU-only facts, ask for the courses."""
    asu_rules = _cap_rules(rules)
    inst = rules["institution_types"].get(institution_type or "")

    if credits_completed:
        question = (
            f"Can you share your transcript or a list of the courses behind your "
            f"{credits_completed} credits? I can't break your credits down from a total alone."
        )
        if inst and inst["max_total_transfer_credits"] is not None:
            asu_rules["upper_limit_for_your_credits"] = min(credits_completed, inst["max_total_transfer_credits"])
            asu_rules["upper_limit_note"] = (
                "This is the most ASU's cap allows, not an estimate of how many will apply. "
                "That depends on each course."
            )
    else:
        question = "Can you share your transcript or a list of the courses you've completed?"

    log_call("estimate_transfer_credits", "course_history_needed")
    return clarify(
        question=question,
        why=(
            "ASU has no record of your courses until you share them. Whether a credit transfers "
            "depends on the specific course, its grade and where you took it, so a total can't be "
            "split into transferable and non-transferable credits."
        ),
        options=[
            "Paste or upload your unofficial transcript",
            "List your courses. " + _COURSE_FORMAT,
            "Look up courses yourself in the ASU Transfer Guide: transferguide.apps.asu.edu",
        ],
        asu_rules=asu_rules,
        source=rules["source_url"],
    )


def _classify(
    course: dict[str, Any],
    rules: dict[str, Any],
    equivalencies: dict[str, Any],
) -> tuple[str, str, str | None]:
    """Return (category, reason, asu_equivalent) for one course using ASU rules only."""
    elig = rules["eligibility_rules"]
    grade = (course.get("grade") or "").strip().upper()
    code = course.get("code") or ""

    if grade in elig["below_minimum_grades"]:
        return "not_transferable", f"Grade {grade} is below ASU's minimum of {elig['minimum_grade']}.", None
    if grade in elig["not_completed_grades"]:
        return "not_transferable", f"Grade {grade} means the course wasn't completed for credit.", None

    number = _course_number(code)
    if number is not None and number < elig["remedial_course_number_below"]:
        return "not_transferable", "Courses numbered below 100 are remedial and don't transfer.", None

    if grade in elig["pass_fail_grades"]:
        return (
            "needs_advisor_review",
            "Pass grades transfer only if your school confirms P equals C- or better.",
            None,
        )

    inst = _find_institution(course.get("institution"), equivalencies)
    if inst is None:
        return (
            "needs_transfer_guide_lookup",
            "No ASU equivalency on file for this institution yet. Look it up in the Transfer Guide.",
            None,
        )
    for row in inst["equivalencies"]:
        if _norm_code(row["code"]) == _norm_code(code):
            if row["category"] == "general_elective":
                return "general_elective", "Transfers as elective credit with no specific ASU equivalent.", None
            return "direct_equivalency", f"Listed ASU equivalent: {row['asu_equivalent']}.", row["asu_equivalent"]
    return (
        "needs_transfer_guide_lookup",
        "No ASU equivalency on file for this course yet. Look it up in the Transfer Guide.",
        None,
    )


@mcp.tool()
def estimate_transfer_credits(
    courses: list[CourseInput] | None = None,
    institution_type: str | None = None,
    credits_completed: int | None = None,
    client_id: str = "anonymous",
) -> dict[str, Any]:
    """
    Check a student's own courses against ASU transfer rules.

    BEFORE CALLING: look through the conversation for the student's course history
    (a transcript, a pasted course list, or courses they mentioned). If you have it,
    pass every course in `courses`. Use only what the student provided: never invent,
    guess or fill in courses, credits or grades.

    If the student has only given a credit total, call with `credits_completed` only.
    The tool will explain that a total can't be broken down and return a question
    asking for their courses. Relay that question to the student.

    ASU data (transfer cap, grade rules, course equivalencies, degree total) comes
    from this tool. Final credit applicability is decided by the student's ASU college
    after admission.

    Args:
        courses: The student's courses, each with institution, code, title, credits and grade
                 exactly as they appear on the student's transcript or list.
        institution_type: "community_college" (2-year) or "four_year_university". Sets ASU's cap.
        credits_completed: Total credits the student says they have, if they gave one.
        client_id: Optional non-personal identifier for rate limiting.

    Returns:
        With courses: each course's ASU result (listed equivalent, needs lookup, needs review,
        or not transferable, with the reason), credit totals, the cap, and remaining-credit range.
        Without courses: a question asking for the course history, plus ASU rules that apply anyway.
    """
    # ── Validate inputs ──────────────────────────────────────────────────────
    try:
        validate_input({"institution_type": institution_type, "client_id": client_id})
        for course in courses or []:
            if not isinstance(course, dict):
                raise ValidationError("Each course must be an object with institution, code, title, credits and grade.")
            validate_input(dict(course))
        if credits_completed is not None and not 0 <= int(credits_completed) <= 400:
            raise ValidationError("The field 'credits_completed' must be between 0 and 400.")
        check_rate_limit(client_id)
    except (ValidationError, TypeError, ValueError) as exc:
        log_call("estimate_transfer_credits", "validation_error")
        return err(str(exc), "Check your input and try again.")

    rules = _load(_RULES_FILE)

    # ── No course history: ask for it rather than inventing a breakdown ───────
    if not courses:
        return _ask_for_courses(rules, credits_completed, institution_type)

    # ── Institution type sets the cap: ask if missing ─────────────────────────
    inst_rules = rules["institution_types"].get(institution_type or "")
    if inst_rules is None:
        log_call("estimate_transfer_credits", "clarification_needed")
        return clarify(
            question="Did you earn these credits at a community college or a four-year university?",
            why=(
                "ASU accepts up to 64 credits from community colleges and has no cap for "
                "four-year universities, so the answer changes how many credits can count."
            ),
            options=[
                "community_college: 2-year college or junior college",
                "four_year_university: 4-year college or university",
            ],
            asu_rules=_cap_rules(rules),
            source=rules["source_url"],
        )

    equivalencies = _load(_EQUIV_FILE)

    # ── Check each course the student provided ────────────────────────────────
    results: list[dict[str, Any]] = []
    incomplete: list[str] = []
    counted_keys: set[tuple[str, str]] = set()
    totals = {
        "direct_equivalency": 0.0,
        "general_elective": 0.0,
        "needs_transfer_guide_lookup": 0.0,
        "needs_advisor_review": 0.0,
        "not_transferable": 0.0,
    }

    for course in courses:
        label = course.get("code") or course.get("title") or "A course"
        credits = _parse_credits(course.get("credits"))
        missing = [f for f in ("institution", "code", "grade") if not str(course.get(f) or "").strip()]
        if credits is None:
            missing.append("credits")
        if missing:
            incomplete.append(f"{label} (missing {', '.join(missing)})")
            continue

        key = (_norm(course.get("institution")), _norm_code(course.get("code")))
        if key in counted_keys:
            category, reason, equivalent = (
                "not_transferable",
                "Repeat of a course already passed. ASU uses only the first passing attempt.",
                None,
            )
        else:
            category, reason, equivalent = _classify(course, rules, equivalencies)
            if category != "not_transferable":
                counted_keys.add(key)

        totals[category] += credits
        results.append({
            "course": f"{course.get('code')} {course.get('title') or ''}".strip(),
            "institution": course.get("institution"),
            "credits": credits,
            "grade": course.get("grade"),
            "asu_result": category,
            "asu_equivalent": equivalent,
            "reason": reason,
        })

    if not results:
        log_call("estimate_transfer_credits", "course_details_needed")
        return clarify(
            question=f"Can you add the missing details for these courses: {'; '.join(incomplete)}?",
            why="Each course needs its institution, code, credits and grade before ASU's rules can be applied.",
            options=["Add the missing details. " + _COURSE_FORMAT, "Paste or upload your unofficial transcript"],
            asu_rules=_cap_rules(rules),
            source=rules["source_url"],
        )

    # ── Totals, cap and remaining-credit range ────────────────────────────────
    confirmed = totals["direct_equivalency"] + totals["general_elective"]
    pending = totals["needs_transfer_guide_lookup"] + totals["needs_advisor_review"]
    not_transferable = totals["not_transferable"]
    submitted = sum(r["credits"] for r in results)

    cap = inst_rules["max_total_transfer_credits"]
    counted_confirmed = min(confirmed, cap) if cap is not None else confirmed
    counted_best_case = min(confirmed + pending, cap) if cap is not None else confirmed + pending
    over_cap = max(0.0, confirmed + pending - cap) if cap is not None else 0.0

    degree_total = rules["degree_total_credits"]
    remaining_best = max(0.0, degree_total - counted_best_case)
    remaining_worst = max(0.0, degree_total - counted_confirmed)

    flags: list[str] = []
    if credits_completed is not None and abs(credits_completed - submitted) >= 1:
        flags.append(
            f"You mentioned {credits_completed} credits, but the courses listed add up to "
            f"{_fmt(submitted)}. Add any missing courses for a complete picture."
        )
    if over_cap > 0:
        flags.append(
            f"ASU accepts up to {cap} community-college credits, so up to {_fmt(over_cap)} "
            f"of your credits may not count even if they qualify."
        )
    if incomplete:
        flags.append(f"Not included yet because details are missing: {'; '.join(incomplete)}.")
    if equivalencies.get("status") == "sample":
        flags.append("Equivalencies come from a sample table, not the live ASU Transfer Guide.")

    if remaining_best == remaining_worst:
        remaining_text = f"you'd have about {_fmt(remaining_worst)} credits left"
    else:
        remaining_text = f"you'd have {_fmt(remaining_best)} to {_fmt(remaining_worst)} credits left"

    log_call("estimate_transfer_credits", "ok")
    return ok(
        bottom_line=(
            f"{_fmt(confirmed)} of your {_fmt(submitted)} listed credits have an ASU equivalent on file, "
            f"{_fmt(pending)} need a lookup or review, and {_fmt(not_transferable)} won't transfer."
        ),
        summary=(
            f"Depending on the credits still to be checked, {remaining_text} of a "
            f"{degree_total}-credit degree. Your ASU college confirms how each course applies after admission."
        ),
        data={
            "courses": results,
            "credit_totals": {
                "listed_asu_equivalent": confirmed,
                "needs_lookup_or_review": pending,
                "not_transferable": not_transferable,
                "credits_listed": submitted,
            },
            "credits_counted_range": {"confirmed_only": counted_confirmed, "if_all_pending_count": counted_best_case},
            "credits_remaining_range": {"if_all_pending_count": remaining_best, "confirmed_only": remaining_worst},
            "degree_total_credits": degree_total,
            "institution_type": inst_rules["label"],
            "transfer_cap": cap,
            "course_history_source": "provided by student",
            "equivalency_data_status": equivalencies.get("status", "unknown"),
            "flags": flags,
        },
        source=rules["source_url"],
        next_steps=[
            "Look up each course marked needs_transfer_guide_lookup at transferguide.apps.asu.edu.",
            "Use MyPath2ASU at admission.asu.edu/apply/transfer/MyPath2ASU to map credits to your major.",
            "Contact an ASU admissions advisor at admission.asu.edu/contact for an official evaluation.",
        ],
        data_version=rules["data_version"],
        clarification_needed=(
            f"Can you add the missing details for: {'; '.join(incomplete)}?" if incomplete else None
        ),
    )
