"""Reusable deterministic fixtures for mocked BandAI flow tests."""

from __future__ import annotations

from copy import deepcopy

from bandai.models import ComplianceVerdict, FinalProposal


_SAMPLE_CONTRACT = {
    "canonical_contract_id": "BANDI-2026-001",
    "title": "Digital procurement platform modernization",
    "contracting_authority": "Comune di Test",
    "deadline": "2026-07-15",
    "value_eur": 125000.0,
    "cpv_codes": ["72200000"],
    "sources": ["https://example.test/tenders/1"],
    "consensus_score": 0.94,
    "canonical_url": "https://example.test/tenders/1",
}


def sample_contract(**overrides: object) -> dict:
    """Return a copy of a representative resolved contract."""
    contract = deepcopy(_SAMPLE_CONTRACT)
    contract.update(overrides)
    return contract


def go_verdict() -> ComplianceVerdict:
    """Return a deterministic GO verdict."""
    return ComplianceVerdict(
        bid_decision="GO",
        conditions=[],
        key_risks=["Delivery timeline must be monitored."],
        key_strengths=["Relevant public-sector software delivery experience."],
        compliance_score=0.91,
        legal_flags=[],
        verdict_rationale="The company meets the core technical and administrative requirements.",
    )


def no_go_verdict() -> ComplianceVerdict:
    """Return a deterministic NO-GO verdict."""
    return ComplianceVerdict(
        bid_decision="NO-GO",
        conditions=[],
        key_risks=["Mandatory ISO 27001 certification is missing."],
        key_strengths=["Some experience in comparable software projects."],
        compliance_score=0.31,
        legal_flags=["Missing mandatory certification"],
        verdict_rationale="A mandatory certification blocker prevents a compliant bid.",
    )


def conditional_go_verdict() -> ComplianceVerdict:
    """Return a deterministic CONDITIONAL-GO verdict."""
    return ComplianceVerdict(
        bid_decision="CONDITIONAL-GO",
        conditions=["Confirm availability of ISO 27001 partner before submission."],
        key_risks=["Eligibility depends on partner documentation."],
        key_strengths=["Strong technical match for the tender scope."],
        compliance_score=0.72,
        legal_flags=["Partner documentation required"],
        verdict_rationale="The opportunity is viable only if the missing partner evidence is resolved.",
    )


def sample_proposal(tender_ref: str = "BANDI-2026-001") -> FinalProposal:
    """Return a deterministic final proposal."""
    return FinalProposal(
        tender_ref=tender_ref,
        executive_summary="A concise, compliant modernization proposal.",
        sections={
            "Technical approach": "Use a phased delivery model with measurable milestones.",
            "Governance": "Weekly steering checkpoints and risk tracking.",
        },
        appendices=["Project references", "Delivery timeline"],
        compliance_declarations=["The bidder accepts all mandatory tender clauses."],
        word_count=840,
        quality_score=0.88,
    )
