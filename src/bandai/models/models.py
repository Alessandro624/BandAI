from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

# Scouting Models


class RawContract(BaseModel):
    """Unprocessed tender notice as scraped from a portal."""

    portal: str
    url: str
    title: str
    contract_id: str | None = None
    contracting_authority: str
    deadline: str
    value_eur: float | None = None
    cpv_codes: list[str] = Field(default_factory=list, alias="cpvCodes")
    raw_text: str


class ResolvedContract(BaseModel):
    """Deduplicated, canonical tender record with consensus metadata."""

    canonical_contract_id: str
    title: str
    contracting_authority: str
    deadline: str
    value_eur: float | None
    cpv_codes: list[str]
    sources: list[str]
    consensus_score: float = Field(..., ge=0.0, le=1.0)
    canonical_url: str


# Compliance Models


class AdvocateAnalysis(BaseModel):
    """Optimistic assessment of the company's ability to meet tender requirements."""

    requirements_met: list[str]
    requirements_potentially_met: list[str]
    risk_mitigations: list[str]
    overall_sentiment: Literal["strongly_positive", "positive", "cautiously_positive"]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    summary: str


class AuditorChallenge(BaseModel):
    """Skeptical rebuttal of the Advocate's analysis, identifying risks."""

    hard_blockers: list[str]
    soft_risks: list[str]
    advocate_overestimates: list[str]
    overall_sentiment: Literal["high_risk", "medium_risk", "manageable_risk"]
    risk_score: float = Field(..., ge=0.0, le=1.0)
    summary: str


class ComplianceVerdict(BaseModel):
    """Final bid/no-bid decision with structured rationale."""

    bid_decision: Literal["GO", "NO-GO", "CONDITIONAL-GO"]
    conditions: list[str] = Field(default_factory=list)
    key_risks: list[str]
    key_strengths: list[str]
    compliance_score: float = Field(..., ge=0.0, le=1.0)
    legal_flags: list[str] = Field(default_factory=list)
    verdict_rationale: str


# Proposal Models


class DepartmentBid(BaseModel):
    """A department's bid for inclusion in the proposal."""

    department: str
    headline_capability: str
    evidence: list[str]
    differentiators: list[str]
    suggested_section: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    evidence_quality_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=("1.0 = verifiable certs + signed case studies + quantified KPIs; " "0.5 = partial evidence; 0.0 = unsubstantiated claims only"),
    )
    word_budget: int


class AuctionResult(BaseModel):
    """Outcome of the departmental auction, selecting winning bids."""

    winning_bids: list[DepartmentBid]
    rejected_bids: list[str]
    section_allocation: dict[str, str]
    total_word_budget: int
    rationale: str


class FinalProposal(BaseModel):
    """Complete proposal document ready for submission."""

    tender_ref: str
    executive_summary: str
    sections: dict[str, str]
    appendices: list[str] = Field(default_factory=list)
    compliance_declarations: list[str]
    word_count: int
    quality_score: float = Field(..., ge=0.0, le=1.0)
