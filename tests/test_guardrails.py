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

from bandai.guardrails import (  # noqa: E402
    validate_compliance_verdict,
    validate_json_array,
    validate_resolved_contract_array,
    validate_tender_info_array,
)


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

    def test_nested_array_is_not_truncated(self) -> None:
        result = _make_task_output(
            'Final answer:\n[{"canonical_contract_id": "001", "cpv_codes": ["72000000"]}]'
        )
        ok, msg = validate_json_array(result)
        assert ok is True
        assert msg == '[{"canonical_contract_id": "001", "cpv_codes": ["72000000"]}]'

    def test_known_wrapper_object_is_normalized_to_array(self) -> None:
        result = _make_task_output(
            '{"tenders": [{"title": "Tender", "cpv_codes": ["72000000"]}], "portal": "TED"}'
        )
        ok, msg = validate_json_array(result)
        assert ok is True
        assert msg == '[{"title": "Tender", "cpv_codes": ["72000000"]}]'

    def test_tool_call_envelope_is_rejected_with_specific_message(self) -> None:
        result = _make_task_output(
            '{"name": "parse_markdown", "parameters": {"markdown": "## CIG 123"}}'
        )
        ok, msg = validate_json_array(result)
        assert ok is False
        assert "Do not return tool-call JSON" in msg


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


class TestValidateResolvedContractArray:
    """Tests for validate_resolved_contract_array()."""

    def test_rejects_null_required_fields(self) -> None:
        result = _make_task_output(
            '[{"canonical_contract_id":"66516400","title":null,'
            '"contracting_authority":null,"deadline":null,"value_eur":null,'
            '"cpv_codes":null,"sources":[],"consensus_score":null,"canonical_url":""}]'
        )
        ok, msg = validate_resolved_contract_array(result)
        assert ok is False
        assert "ResolvedContract fields cannot be null" in msg

    def test_accepts_valid_resolved_contract(self) -> None:
        result = _make_task_output(
            '[{"canonical_contract_id":"66516400","title":"Tender",'
            '"contracting_authority":"BandAI","deadline":"2026-06-24T23:59:00",'
            '"value_eur":1500000.0,"cpv_codes":["72000000"],'
            '"sources":["TED","https://ted.europa.eu/notice"],'
            '"consensus_score":0.9,"canonical_url":"https://ted.europa.eu/notice"}]'
        )
        ok, msg = validate_resolved_contract_array(result)
        assert ok is True

    def test_rejects_placeholder_values(self) -> None:
        result = _make_task_output(
            '[{"canonical_contract_id":"TED:123","title":"string",'
            '"contracting_authority":{"name":"string","tax_code":"string"},'
            '"deadline":"2023-02-01T23:59:59Z","value_eur":null,'
            '"cpv_codes":["code1","code2"],"sources":["TED"],'
            '"consensus_score":0.9,"canonical_url":"https://ted.europa.eu/notice"}]'
        )
        ok, msg = validate_resolved_contract_array(result)
        assert ok is False
        assert "placeholder" in msg


class TestValidateTenderInfoArray:
    """Tests for validate_tender_info_array()."""

    def test_rejects_prose_output(self) -> None:
        result = _make_task_output("We have loaded all three tenders. Now we need to extract fields.")
        ok, msg = validate_tender_info_array(result)
        assert ok is False
        assert "Do not describe your extraction steps" in msg

    def test_does_not_treat_nested_cpv_as_top_level_payload(self) -> None:
        result = _make_task_output('Partial prose before malformed output {"cpv": ["66516400"]}')
        ok, msg = validate_tender_info_array(result)
        assert ok is False
        assert "properly formatted JSON array" in msg

    def test_accepts_valid_tender_info(self) -> None:
        result = _make_task_output(
            '[{"cig":null,"cup":null,"title":"Tender","url":"https://ted.europa.eu/notice",'
            '"cpv":["66516400"],"contract_type":"Services",'
            '"contracting_authority":{"name":"Cogeser S.p.A.","tax_code":"08317570151"},'
            '"base_amount":520000.0,"max_amount":null,"publication_date":"2026-05-27",'
            '"deadline":null,"contract_duration_months":null,"url_docs":[],'
            '"portal":"TED","status":"partial","error":null}]'
        )
        ok, msg = validate_tender_info_array(result)
        assert ok is True
