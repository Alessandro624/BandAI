from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, PropertyMock

if "crewai" not in sys.modules:
    _crewai = types.ModuleType("crewai")
    _crewai.TaskOutput = MagicMock(name="TaskOutput")
    sys.modules["crewai"] = _crewai
else:
    if not hasattr(sys.modules["crewai"], "TaskOutput"):
        sys.modules["crewai"].TaskOutput = MagicMock(name="TaskOutput")

from bandai.guardrails import validate_json_array, validate_compliance_verdict  # noqa: E402


def _make_task_output(raw: str) -> MagicMock:
    """Create a mock TaskOutput with a given raw string."""
    out = MagicMock()
    out.raw = raw
    return out


class TestValidateJsonArray:
    """Tests for validate_json_array()."""

    def test_valid_array(self) -> None:
        result = _make_task_output('[{"id": 1}]')
        ok, msg = validate_json_array(result)
        assert ok is True

    def test_empty_array(self) -> None:
        result = _make_task_output("[]")
        ok, msg = validate_json_array(result)
        assert ok is True

    def test_with_markdown_fences(self) -> None:
        result = _make_task_output('```json\n[{"id": 1}]\n```')
        ok, msg = validate_json_array(result, strip_fences=True)
        assert ok is True

    def test_fences_extracted_by_regex_fallback(self) -> None:
        result = _make_task_output('```json\n[{"id": 1}]\n```')
        ok, msg = validate_json_array(result, strip_fences=False)
        assert ok is True
        assert msg.startswith("[")
        assert msg.endswith("]")

    def test_plain_text_rejected(self) -> None:
        result = _make_task_output("Here is my analysis...")
        ok, msg = validate_json_array(result)
        assert ok is False
        assert "JSON array" in msg

    def test_single_object_rejected(self) -> None:
        result = _make_task_output('{"id": 1}')
        ok, msg = validate_json_array(result)
        assert ok is False
        assert "JSON array (list)" in msg

    def test_invalid_json_rejected(self) -> None:
        result = _make_task_output("[not, valid, json")
        ok, msg = validate_json_array(result)
        assert ok is False
        assert "not valid JSON" in msg

    def test_array_embedded_in_verbose_text(self) -> None:
        raw = "To answer the prompt, we need to call the crawler tool.\n\n" "Here is the result:\n\n" "```json\n" '[{"id": 1, "title": "Test"}]\n' "```\n"
        result = _make_task_output(raw)
        ok, msg = validate_json_array(result)
        assert ok is True

    def test_array_embedded_without_fences(self) -> None:
        raw = "The final answer is:\n\n" '[{"canonical_contract_id": "001", "title": "Tender"}]'
        result = _make_task_output(raw)
        ok, msg = validate_json_array(result)
        assert ok is True

    def test_strip_fences_returns_clean_json(self) -> None:
        result = _make_task_output('```json\n[{"id": 1}]\n```')
        ok, msg = validate_json_array(result, strip_fences=True)
        assert ok is True
        assert "```" not in msg


class TestValidateComplianceVerdict:
    """Tests for validate_compliance_verdict()."""

    def _make_verdict_output(self, **overrides) -> MagicMock:
        verdict_data = {
            "bid_decision": "GO",
            "key_risks": [],
            "key_strengths": ["Strong team"],
            "compliance_score": 0.85,
            "verdict_rationale": "Good match.",
            "conditions": [],
            "legal_flags": [],
        }
        verdict_data.update(overrides)

        mock_verdict = MagicMock()
        mock_verdict.bid_decision = verdict_data["bid_decision"]
        mock_verdict.compliance_score = verdict_data["compliance_score"]

        out = MagicMock()
        out.pydantic = mock_verdict
        return out

    def test_valid_go(self) -> None:
        result = self._make_verdict_output()
        ok, msg = validate_compliance_verdict(result)
        assert ok is True

    def test_valid_no_go(self) -> None:
        result = self._make_verdict_output(bid_decision="NO-GO")
        ok, msg = validate_compliance_verdict(result)
        assert ok is True

    def test_valid_conditional_go(self) -> None:
        result = self._make_verdict_output(bid_decision="CONDITIONAL-GO")
        ok, msg = validate_compliance_verdict(result)
        assert ok is True

    def test_invalid_decision(self) -> None:
        result = self._make_verdict_output(bid_decision="MAYBE")
        ok, msg = validate_compliance_verdict(result)
        assert ok is False
        assert "bid_decision" in msg

    def test_score_too_high(self) -> None:
        result = self._make_verdict_output(compliance_score=1.5)
        ok, msg = validate_compliance_verdict(result)
        assert ok is False
        assert "compliance_score" in msg

    def test_score_too_low(self) -> None:
        result = self._make_verdict_output(compliance_score=-0.1)
        ok, msg = validate_compliance_verdict(result)
        assert ok is False
        assert "compliance_score" in msg

    def test_unparseable_output(self) -> None:
        out = MagicMock()
        type(out).pydantic = PropertyMock(side_effect=Exception("bad"))
        ok, msg = validate_compliance_verdict(out)
        assert ok is False
        assert "Could not parse" in msg
