from __future__ import annotations

import json
import logging
import re

from crewai import TaskOutput  # type: ignore

log = logging.getLogger(__name__)


# JSON Array Validation


def validate_json_array(
    result: TaskOutput,
    *,
    strip_fences: bool = False,
):
    """Validate that the task output is a parseable JSON array."""
    raw = result.raw.strip()

    if strip_fences:
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return (
            False,
            "Output is not valid JSON: could not decode. Return a properly formatted JSON array (list).",
        )

    if not isinstance(parsed, list):
        return (
            False,
            "Output must be a JSON array (list), not a single object.",
        )

    return (True, raw)


# Compliance Verdict Validation


def validate_compliance_verdict(result: TaskOutput):
    """Validate that the output is a valid ComplianceVerdict."""
    try:
        verdict = result.pydantic

        if verdict.bid_decision not in ("GO", "NO-GO", "CONDITIONAL-GO"):
            return (
                False,
                f"bid_decision must be GO, NO-GO, or CONDITIONAL-GO; got '{verdict.bid_decision}'.",
            )

        if not (0.0 <= verdict.compliance_score <= 1.0):
            return (
                False,
                f"compliance_score must be between 0.0 and 1.0; got {verdict.compliance_score}.",
            )

        return (True, result)
    except Exception:
        return (False, "Could not parse output as ComplianceVerdict JSON.")
