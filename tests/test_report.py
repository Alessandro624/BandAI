from __future__ import annotations

import json
from pathlib import Path

from bandai.report import build_report_data, generate_report_html, write_report


def test_build_report_data_collects_pipeline_outputs(tmp_path: Path) -> None:
    contract = {
        "canonical_contract_id": "363340-2026",
        "title": "Italy - Research services",
        "contracting_authority": "European Commission",
        "deadline": "2026-07-03T12:00:59",
        "value_eur": 1100000.0,
        "cpv_codes": ["73110000"],
        "sources": ["TED"],
        "consensus_score": 0.9,
        "canonical_url": "https://ted.europa.eu/en/notice/-/detail/363340-2026",
    }
    verdict = {
        "bid_decision": "GO",
        "conditions": [],
        "key_risks": [],
        "key_strengths": ["Relevant research experience"],
        "compliance_score": 0.95,
        "legal_flags": ["D.Lgs. 36/2023"],
        "verdict_rationale": "Ready to bid.",
    }
    proposal = {
        "tender_ref": "363340-2026",
        "executive_summary": "Executive summary",
        "sections": {"Approach": "Research approach"},
        "appendices": [],
        "compliance_declarations": ["Declaration"],
        "word_count": 1200,
        "quality_score": 0.91,
    }

    (tmp_path / "01_scout_results.json").write_text(json.dumps({"contracts": [contract]}), encoding="utf-8")
    (tmp_path / "02_compliance_01_363340-2026.json").write_text(
        json.dumps({"contract": contract, "verdict": verdict}),
        encoding="utf-8",
    )
    (tmp_path / "03_proposal_01_363340-2026.json").write_text(json.dumps(proposal), encoding="utf-8")

    data = build_report_data(tmp_path)

    assert data["summary"]["contracts"] == 1
    assert data["summary"]["go"] == 1
    assert data["summary"]["proposals"] == 1
    assert data["contracts"][0]["canonical_contract_id"] == "363340-2026"


def test_build_report_data_hides_stale_no_go_when_contract_is_approved(tmp_path: Path) -> None:
    contract = {"canonical_contract_id": "363340-2026", "title": "Research services"}
    verdict = {"bid_decision": "GO", "compliance_score": 0.95, "key_strengths": [], "key_risks": []}
    stale_no_go = {
        "contract": {"contract_id": "363340-2026", "title": "Research services"},
        "verdict": {"bid_decision": "NO-GO", "compliance_score": 0.55},
    }

    (tmp_path / "01_scout_results.json").write_text(json.dumps({"contracts": [contract]}), encoding="utf-8")
    (tmp_path / "02_compliance_01_363340-2026.json").write_text(
        json.dumps({"contract": contract, "verdict": verdict}),
        encoding="utf-8",
    )
    (tmp_path / "02_no_go_review_required.json").write_text(
        json.dumps({"no_go_contracts": [stale_no_go], "total": 1}),
        encoding="utf-8",
    )

    data = build_report_data(tmp_path)

    assert data["summary"]["go"] == 1
    assert data["summary"]["no_go"] == 0
    assert data["no_go"] == []


def test_generate_report_html_contains_stakeholder_sections(tmp_path: Path) -> None:
    data = {
        "summary": {"contracts": 1, "go": 1, "conditional": 0, "no_go": 0, "proposals": 1},
        "contracts": [{"canonical_contract_id": "363340-2026", "title": "Research services"}],
        "compliance": [
            {
                "contract": {"canonical_contract_id": "363340-2026", "title": "Research services"},
                "verdict": {"bid_decision": "GO", "compliance_score": 0.95, "key_strengths": [], "key_risks": []},
                "source_file": "02_compliance_01_363340-2026.json",
            }
        ],
        "no_go": [],
        "proposals": [{"tender_ref": "363340-2026", "quality_score": 0.91, "word_count": 1200, "sections": {}}],
        "generated_at": "2026-05-28 10:00",
    }

    html = generate_report_html(data)

    assert "BandAI Report" in html
    assert "Research services" in html
    assert "theme-toggle" in html
    assert "GO" in html


def test_write_report_creates_html_file(tmp_path: Path) -> None:
    (tmp_path / "01_scout_results.json").write_text(json.dumps({"contracts": []}), encoding="utf-8")

    path = write_report(output_dir=tmp_path)

    assert path == tmp_path / "report.html"
    assert path.exists()
    assert "BandAI Report" in path.read_text(encoding="utf-8")
