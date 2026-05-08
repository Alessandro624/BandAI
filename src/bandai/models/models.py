from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class RawContract(BaseModel):
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
    canonical_contract_id: str
    title: str
    contracting_authority: str
    deadline: str
    value_eur: float | None
    cpv_codes: list[str]
    sources: list[str]
    consensus_score: float = Field(..., ge=0.0, le=1.0)
    canonical_url: str


class AdvocateAnalysis(BaseModel):
    requirements_met: list[str]
    requirements_potentially_met: list[str]
    risk_mitigations: list[str]
    overall_sentiment: Literal["strongly_positive", "positive", "cautiously_positive"]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    summary: str


class AuditorChallenge(BaseModel):
    hard_blockers: list[str]
    soft_risks: list[str]
    advocate_overestimates: list[str]
    overall_sentiment: Literal["high_risk", "medium_risk", "manageable_risk"]
    risk_score: float = Field(..., ge=0.0, le=1.0)
    summary: str


class ComplianceVerdict(BaseModel):
    bid_decision: Literal["GO", "NO-GO", "CONDITIONAL-GO"]
    conditions: list[str] = Field(default_factory=list)
    key_risks: list[str]
    key_strengths: list[str]
    compliance_score: float = Field(..., ge=0.0, le=1.0)
    legal_flags: list[str] = Field(default_factory=list)
    verdict_rationale: str


class DepartmentBid(BaseModel):
    department: str
    headline_capability: str
    evidence: list[str]
    differentiators: list[str]
    suggested_section: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    evidence_quality_score: float = Field(
        ..., ge=0.0, le=1.0, description=("1.0 = verifiable certs + signed case studies + quantified KPIs; 0.5 = partial evidence; 0.0 = unsubstanciated claims only")
    )
    word_budget: int


class AuctionResult(BaseModel):
    winning_bids: list[DepartmentBid]
    rejected_bids: list[str]
    section_allocation: dict[str, str]
    total_word_budget: int
    rationale: str


class FinalProposal(BaseModel):
    tender_ref: str
    executive_summary: str
    sections: dict[str, str]
    appendices: list[str] = Field(default_factory=list)
    compliance_declarations: list[str]
    word_count: int
    quality_score: float = Field(..., ge=0.0, le=1.0)
