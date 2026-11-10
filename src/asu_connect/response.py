"""
Standard response envelope for all ASU Connect tools.

Design frameworks applied here:
  - BLUF             : bottom_line states the conclusion in one sentence before anything else
  - Apple HIG tone   : plain English, active voice, ≤ 20-word disclaimer
  - Netflix content  : most important fact first, action-first next_steps
  - Nielsen #9       : errors always include a suggestion — never a dead end
"""
from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class ToolResponse(TypedDict):
    """Successful tool response envelope."""
    bottom_line: str                        # BLUF: one-sentence conclusion — the answer, up front
    summary: str                            # 1-2 sentence supporting context (Apple HIG)
    data: dict[str, Any]                    # structured result — most important fact first (Netflix)
    source: str                             # public URL of authoritative data source
    disclaimer: str                         # ≤ 20 words, active voice (Apple HIG + PRD Accessibility)
    next_steps: list[str]                   # action-first ordered list e.g. "Visit …", "Contact …" (Netflix)
    data_version: str                       # version string from the data file
    clarification_needed: str | None        # if set, a single question that would improve the answer


class ClarificationResponse(TypedDict):
    """Returned when key inputs are too ambiguous to give a confident answer (Nielsen #6)."""
    clarification_needed: str   # the single most important question to ask the student
    why: str                    # plain-English reason — what changes based on the answer
    options: list[str]          # suggested answer choices the student can pick from
    asu_rules: NotRequired[dict[str, Any]]  # ASU facts that apply even without the missing info
    source: NotRequired[str]                # public URL for those ASU facts


class ErrorResponse(TypedDict):
    """Error envelope — always gives the student somewhere to go (Nielsen #9)."""
    error: str            # what happened, plain English
    suggestion: str       # what to do next, action-first
    contact_url: str      # ASU advisor / help URL


ADVISOR_URL = "https://admission.asu.edu/contact"
STANDARD_DISCLAIMER = "This is an estimate. Verify the details with an ASU advisor before making any decisions."


def ok(bottom_line: str, summary: str, data: dict[str, Any], source: str, next_steps: list[str], data_version: str, clarification_needed: str | None = None) -> ToolResponse:
    """Build a successful response using the standard envelope (BLUF first)."""
    return ToolResponse(
        bottom_line=bottom_line,
        summary=summary,
        data=data,
        source=source,
        disclaimer=STANDARD_DISCLAIMER,
        next_steps=next_steps,
        data_version=data_version,
        clarification_needed=clarification_needed,
    )


def clarify(
    question: str,
    why: str,
    options: list[str],
    asu_rules: dict[str, Any] | None = None,
    source: str | None = None,
) -> ClarificationResponse:
    """Return a clarification request when the answer would materially differ based on missing info.

    asu_rules carries ASU-side facts that are true regardless of the missing input
    (e.g. a transfer cap), so the agent can share them while it asks.
    """
    resp = ClarificationResponse(
        clarification_needed=question,
        why=why,
        options=options,
    )
    if asu_rules is not None:
        resp["asu_rules"] = asu_rules
    if source is not None:
        resp["source"] = source
    return resp


def err(error: str, suggestion: str, contact_url: str = ADVISOR_URL) -> ErrorResponse:
    """Build an error response that never leaves the student without a path forward."""
    return ErrorResponse(
        error=error,
        suggestion=suggestion,
        contact_url=contact_url,
    )
