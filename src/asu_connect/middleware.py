"""
Shared middleware: input validation, call logging, and rate limiting.

Security / governance requirements from the PRD:
  - Invalid inputs (wrong types, oversized text, injection attempts) are rejected with a helpful error.
  - Every call is logged: tool name, timestamp, result status — inputs are NOT logged (privacy).
  - Rate limit per client: 20 calls per minute (in-memory, resets on server restart).
"""
from __future__ import annotations

import logging
import re
import sys
import time
from collections import defaultdict
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────
MAX_FIELD_LENGTH = 500          # characters per string field
RATE_LIMIT_PER_MINUTE = 20      # max calls per client per 60-second window

# Patterns that indicate prompt injection or shell injection attempts
_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(previous|above|all)\s+instructions"
    r"|<script"
    r"|javascript:"
    r"|\bexec\s*\("
    r"|--\s*$"           # SQL comment
    r"|;\s*drop\s+table" # SQL drop
    r")",
    re.IGNORECASE,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [ASU-Connect] %(levelname)s %(message)s",
)
_log = logging.getLogger("asu_connect")

# ── Rate limiter state ────────────────────────────────────────────────────────
# { client_id: [(call_timestamp, ...), ...] }
_call_times: dict[str, list[float]] = defaultdict(list)


# ── Public API ────────────────────────────────────────────────────────────────

class ValidationError(ValueError):
    """Raised when an input fails validation. Message is safe to return to the caller."""


def validate_input(data: dict[str, Any]) -> None:
    """
    Validate all string fields in *data*.

    Raises ValidationError with a plain-English message on:
      - Non-string value where a string is expected (type check is shallow)
      - Any string field exceeding MAX_FIELD_LENGTH characters
      - Any string field matching a known injection pattern
    """
    for field, value in data.items():
        if not isinstance(value, (str, int, float, bool, list, type(None))):
            raise ValidationError(
                f"The field '{field}' has an unexpected type. Please check your input."
            )
        if isinstance(value, str):
            if len(value) > MAX_FIELD_LENGTH:
                raise ValidationError(
                    f"The field '{field}' is too long (max {MAX_FIELD_LENGTH} characters)."
                )
            if _INJECTION_PATTERNS.search(value):
                raise ValidationError(
                    f"The field '{field}' contains characters that are not allowed."
                )
        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    validate_input(item)  # recurse into course objects etc.
                elif isinstance(item, str):
                    if len(item) > MAX_FIELD_LENGTH:
                        raise ValidationError(
                            f"Item {i} in '{field}' is too long (max {MAX_FIELD_LENGTH} characters)."
                        )
                    if _INJECTION_PATTERNS.search(item):
                        raise ValidationError(
                            f"Item {i} in '{field}' contains characters that are not allowed."
                        )


def log_call(tool_name: str, result_status: str) -> None:
    """
    Log a tool call to stderr.

    Intentionally logs ONLY tool name, timestamp, and result status.
    Input values are never logged to protect student privacy (PRD requirement).
    """
    _log.info("tool=%s status=%s", tool_name, result_status)


def check_rate_limit(client_id: str) -> None:
    """
    Enforce a rolling 60-second rate limit per client.

    Raises ValidationError if the client has exceeded RATE_LIMIT_PER_MINUTE calls
    in the last 60 seconds.
    """
    now = time.monotonic()
    window_start = now - 60.0
    times = _call_times[client_id]
    # Drop calls outside the window
    _call_times[client_id] = [t for t in times if t >= window_start]
    if len(_call_times[client_id]) >= RATE_LIMIT_PER_MINUTE:
        raise ValidationError(
            f"You've made too many requests in the last minute. "
            f"Please wait a moment and try again."
        )
    _call_times[client_id].append(now)
