from __future__ import annotations

import json
import logging
import re

from crewai import TaskOutput  # type: ignore

from bandai.utils import extract_json_array_text

log = logging.getLogger(__name__)

_PLACEHOLDER_VALUES = {"string", "code1", "code2", "code3", "code4", "code5", "code6"}


def _contains_placeholder(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in _PLACEHOLDER_VALUES
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    return False


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
        if isinstance(parsed, dict) and {"name", "parameters"}.issubset(parsed):
            return (
                False,
                "Do not return tool-call JSON with 'name' and 'parameters'. "
                "Use the Markdown you received, extract the tender fields, and "
                "return ONLY a JSON array of objects.",
            )
        try:
            extracted = extract_json_array_text(raw)
            return (True, extracted)
        except ValueError:
            pass
        return (
            False,
            "Output must be a JSON array (list), not a single object.",
        )
    except json.JSONDecodeError:
        pass

    # Strategy 2: find the first complete JSON array in the output.
    try:
        extracted = extract_json_array_text(raw)
        parsed = json.loads(extracted)
        if isinstance(parsed, list):
            return (True, extracted)
    except (ValueError, json.JSONDecodeError):
        pass

    return (
        False,
        "Output is not valid JSON. Return a properly formatted JSON array.",
    )


def validate_resolved_contract_array(
    result: TaskOutput,
    *,
    strip_fences: bool = False,
):
    """Validate a ResolvedContract JSON array and reject unusable null records."""
    ok, payload = validate_json_array(result, strip_fences=strip_fences)
    if not ok:
        return (ok, payload)

    try:
        contracts = json.loads(payload)
    except json.JSONDecodeError:
        return (False, "Output is not valid JSON. Return a properly formatted JSON array.")

    required_non_null = (
        "canonical_contract_id",
        "title",
        "contracting_authority",
        "deadline",
        "cpv_codes",
        "sources",
        "consensus_score",
        "canonical_url",
    )
    for index, contract in enumerate(contracts, start=1):
        if not isinstance(contract, dict):
            return (False, f"Item {index} must be a JSON object.")

        missing = [
            field
            for field in required_non_null
            if contract.get(field) is None
        ]
        if missing:
            return (
                False,
                "ResolvedContract fields cannot be null except value_eur. "
                f"Item {index} has null/missing fields: {', '.join(missing)}. "
                "Map TenderInfo fields as follows: canonical_contract_id=cig "
                "or cup or url; contracting_authority=contracting_authority.name; "
                "value_eur=max_amount or base_amount; cpv_codes=cpv or []; "
                "sources=[portal and/or url]; consensus_score=portal reliability weight.",
            )

        if _contains_placeholder(contract):
            return (
                False,
                f"Item {index} contains placeholder/example values such as 'string' or 'code1'. "
                "Use only real values extracted from TenderInfo context; if unavailable use the configured fallback values.",
            )
        if not isinstance(contract.get("cpv_codes"), list):
            return (False, f"Item {index} field cpv_codes must be a list, never null.")
        if isinstance(contract.get("contracting_authority"), dict):
            return (
                False,
                f"Item {index} field contracting_authority must be a string, not an object. "
                "Use contracting_authority.name from TenderInfo.",
            )
        if not isinstance(contract.get("contracting_authority"), str):
            return (False, f"Item {index} field contracting_authority must be a string.")
        if not isinstance(contract.get("sources"), list) or not contract["sources"]:
            return (False, f"Item {index} field sources must be a non-empty list.")
        if not isinstance(contract.get("consensus_score"), (int, float)):
            return (False, f"Item {index} field consensus_score must be a number.")

    return (True, payload)


def validate_tender_info_array(
    result: TaskOutput,
    *,
    strip_fences: bool = False,
):
    """Validate that the extractor returned TenderInfo objects, not prose."""
    ok, payload = validate_json_array(result, strip_fences=strip_fences)
    if not ok:
        return (
            False,
            f"{payload} Do not describe your extraction steps. Return ONLY the final JSON array.",
        )

    try:
        tenders = json.loads(payload)
    except json.JSONDecodeError:
        return (False, "Output is not valid JSON. Return a properly formatted JSON array.")

    required_non_null = ("title", "url", "portal", "status")
    for index, tender in enumerate(tenders, start=1):
        if not isinstance(tender, dict):
            return (False, f"Item {index} must be a TenderInfo JSON object.")

        missing = [
            field
            for field in required_non_null
            if tender.get(field) is None
        ]
        if missing:
            return (
                False,
                f"Item {index} is missing required TenderInfo fields: {', '.join(missing)}. "
                "Return ONLY a JSON array of TenderInfo objects; no reasoning text.",
            )

        cpv = tender.get("cpv")
        if cpv is not None and not isinstance(cpv, list):
            return (False, f"Item {index} field cpv must be a list or null.")

        authority = tender.get("contracting_authority")
        if authority is not None and not isinstance(authority, dict):
            return (False, f"Item {index} field contracting_authority must be an object or null.")

    return (True, payload)


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
