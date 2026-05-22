from __future__ import annotations

import json
import pytest

from bandai.utils import (
    extract_json_array,
    is_implicit_no_go,
    load_yaml_config,
    contract_to_summary,
)


class TestExtractJsonArray:
    """Tests for extract_json_array()."""

    def test_valid_array(self) -> None:
        raw = '[{"a": 1}, {"b": 2}]'
        result = extract_json_array(raw)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_array_with_surrounding_text(self) -> None:
        raw = 'Here is the result:\n[{"id": 1}]\nDone.'
        result = extract_json_array(raw)
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_multiline_array(self) -> None:
        raw = '[\n  {"a": 1},\n  {"b": 2}\n]'
        result = extract_json_array(raw)
        assert len(result) == 2

    def test_no_array_raises(self) -> None:
        with pytest.raises(ValueError, match="No JSON array"):
            extract_json_array("no array here")

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            extract_json_array("[not valid json")

    def test_empty_array(self) -> None:
        result = extract_json_array("[]")
        assert result == []


class TestIsImplicitNoGo:
    """Tests for is_implicit_no_go()."""

    def test_italian_no_go(self) -> None:
        assert is_implicit_no_go("Non abbiamo i requisiti")
        assert is_implicit_no_go("impossibile completare")
        assert is_implicit_no_go("rinunciamo a questo bando")

    def test_english_no_go(self) -> None:
        assert is_implicit_no_go("we can't meet the deadline")
        assert is_implicit_no_go("we don't have the certification")

    def test_positive_intent(self) -> None:
        assert not is_implicit_no_go("We have all certifications")
        assert not is_implicit_no_go("Posiamo procedere con la documentazione")

    def test_empty_string(self) -> None:
        assert not is_implicit_no_go("")
        assert not is_implicit_no_go("   ")

    def test_case_insensitive(self) -> None:
        assert is_implicit_no_go("IMPOSSIBILE")
        assert is_implicit_no_go("Non Abbiamo")


class TestContractToSummary:
    """Tests for contract_to_summary()."""

    def test_full_contract(self) -> None:
        c = {
            "title": "Test Tender",
            "canonical_contract_id": "TC-001",
            "contracting_authority": "Comune di Roma",
            "value_eur": 150000,
            "deadline": "2025-12-31",
            "cpv_codes": ["72000000", "72212517"],
            "canonical_url": "https://example.com/tender/1",
        }
        summary = contract_to_summary(c)
        assert "Test Tender" in summary
        assert "TC-001" in summary
        assert "Comune di Roma" in summary
        assert "150,000" in summary

    def test_missing_fields(self) -> None:
        c = {"title": "Minimal"}
        summary = contract_to_summary(c)
        assert "Minimal" in summary
        assert "N/A" in summary


class TestLoadYamlConfig:
    """Tests for load_yaml_config()."""

    def test_load_existing_yaml(self) -> None:
        data = load_yaml_config("portals.yaml")
        assert "portals" in data
        assert isinstance(data["portals"], list)

    def test_missing_yaml_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_yaml_config("nonexistent_file.yaml")

    def test_caching(self) -> None:
        # Two calls should return the same object
        a = load_yaml_config("portals.yaml")
        b = load_yaml_config("portals.yaml")
        assert a is b

    def test_cache_bypass(self) -> None:
        a = load_yaml_config("portals.yaml", use_cache=True)
        b = load_yaml_config("portals.yaml", use_cache=False)
        # Same content, different objects
        assert a == b
