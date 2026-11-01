"""Which kind of request was this, and how did it end? Worked out from what the agent did,
not by asking the model a second time. The analytics (Day 3) store these two labels."""

from dataclasses import dataclass

# A request that used several tools counts as the first of these it touched.
TYPE_PRIORITY = [
    "off_topic", "transfer", "add", "remove", "restore", "assign",
    "missing_student", "duplicate", "search", "show",
]

# Every request_type classify() can return: the ones above, plus these two (no tool, or only confirm/cancel)
ALL_REQUEST_TYPES = (*TYPE_PRIORITY, "confirmation", "other")

OUTCOMES = ("resolved", "permission_denied", "needs_clarification", "out_of_scope", "error")


@dataclass(frozen=True)
class ToolRecord:
    """One tool call made during a request."""

    name: str
    request_type: str  # show, search, add, remove, ... (see the tools)
    kind: str  # the ToolOutcome kind: ok, conflict, permission_denied, ...
    is_error: bool
    duration_ms: int = 0


def classify(records: list[ToolRecord], final_text: str, llm_failed: bool = False) -> tuple[str, str]:
    """Returns (request_type, outcome)."""
    types = {r.request_type for r in records}
    request_type = next((t for t in TYPE_PRIORITY if t in types), None)
    if request_type is None:
        request_type = "confirmation" if "confirm" in types else "other"

    kinds = [r.kind for r in records]
    # A proposal ends with "Confirm?" and is not a clarification; any other question to the user is.
    made_progress = any(k in ("pending_confirmation", "confirmed", "cancelled") for k in kinds)
    asks_a_question = final_text.rstrip().endswith("?") and not made_progress

    if llm_failed or "error" in kinds:
        outcome = "error"
    elif "permission_denied" in kinds:
        outcome = "permission_denied"
    elif "out_of_scope" in kinds:
        outcome = "out_of_scope"
    elif (records and records[-1].is_error) or asks_a_question:
        # A problem the user has to help with (namesake, unknown class, "which Amir?").
        outcome = "needs_clarification"
    else:
        outcome = "resolved"
    return request_type, outcome
