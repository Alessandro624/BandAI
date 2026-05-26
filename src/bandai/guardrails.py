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
    """
    Validate that the task output is a parseable JSON array.

    Tries three strategies in order:

    1. Direct json.loads on the raw text (fast path).
    2. If strip_fences is set, strip markdown code fences then retry.
    3. Regex extraction ([...]) to handle verbose LLM
       output where the JSON array is embedded in explanatory text.
       This is the common case when Process.hierarchical wraps
       the Crew Manager's reasoning around the actual payload.
    """
    raw = result.raw.strip()

    if strip_fences:
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

    # Strategy 1: direct parse.
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return (True, raw)
        return (
            False,
            "Output must be a JSON array (list), not a single object.",
        )
    except json.JSONDecodeError:
        pass

    # Strategy 2: fenced JSON extraction (preferred when present).
    fenced = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", raw)
    if fenced:
        extracted = fenced.group(1)
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, list):
                return (True, extracted)
        except json.JSONDecodeError:
            pass

    # Strategy 3: find the first valid JSON array in the output.
    for candidate in re.findall(r"\[[\s\S]*?\]", raw):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return (True, candidate)
        except json.JSONDecodeError:
            continue

    return (
        False,
        "Output is not valid JSON. Return a properly formatted JSON array.",
    )


# JSON Object Validator


def validate_json_obj(
        result: TaskOutput
):
    """
    Validate that the task output is a parseable JSON object.
    """

    raw: str = result.raw

    if not raw or not raw.strip():
        return (False, "Output must not be empty")

    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw)
    raw = raw.strip()

    start = raw.find("{")
    end = raw.rfind("}")

    if start == -1 or end == -1:
        return (False, "No JSON object found in the output")

    json_str = raw[start:end+1]

    try:
        parsed = json.loads(json_str)
        return (True, raw)
    except json.JSONDecodeError as e:
        return (False, "JSON Object is not Valid")



# Compliance Verdict Validation


def validate_compliance_verdict(result: TaskOutput):
    """Validate that the output is a valid ComplianceVerdict."""
    try:
        verdict = result.pydantic
    except Exception:
        return (False, "Could not parse output as ComplianceVerdict JSON.")

    if verdict.bid_decision not in ("GO", "NO-GO", "CONDITIONAL-GO"):
        return (
            False,
            f"bid_decision must be GO, NO-GO, or CONDITIONAL-GO; " f"got '{verdict.bid_decision}'.",
        )

    if not (0.0 <= verdict.compliance_score <= 1.0):
        return (
            False,
            f"compliance_score must be between 0.0 and 1.0; " f"got {verdict.compliance_score}.",
        )

    return (True, result)
