from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl

import datetime as dt

### -----------------------------------------------------------------------------------
###
###     Discovery - Tender Overview Models
###
### -----------------------------------------------------------------------------------

AccessMode = Literal['api', 'html']
Status = Literal['success', 'error', 'partial']

class TenderOverview(BaseModel):
    """
    Output Template for the Discovery Agent.
    It contains an Information overview of the different available Tenders on a Portal.
    """
    title: Optional[str] = Field(
        default = None, 
        description = "Tender title (if available) from Terders' lists"
    )
    url: HttpUrl | str = Field(description = "Direct (complete or relative) URL page/endpoint for reaching tenders Information")
    
    portal: str = Field(description = "Orginal Portal's Name (i.e. ANAC, TED, MePA)")

    access_mode: AccessMode = Field(
        default = 'html',
        description = "Extration Access Mode"
    )

    metadata: Optional[dict] = Field(
        default = None,
        description = "Avaible Data during the Discovery Process (i.e. CIG, deadline)"
    )

    discovery_datetime: dt.datetime = Field(
        default_factory = dt.datetime.now,
        description = "Timestamp of first discovery of the tender"
    )


class DiscoveryResult(BaseModel):
    """
    It contains a list of discovered tenders on a portal by a Discovery Agent.
    """

    tenders: list[TenderOverview]
    portal: str
    status: Status = 'success'
    error: Optional[str] = None

    @property
    def tenders_count(self):
        return len(self.tenders)


### -----------------------------------------------------------------------------------
###
###     Extractor Agents - Tender Complete Information Models 
###
### -----------------------------------------------------------------------------------

class ContractingAuthority(BaseModel):
    """
    Contracting Authority Information of a Tender
    """

    name: str
    tax_code: Optional[str] = None
    pec: Optional[str] = None
    rup: Optional[str] = None
    

class TenderInfo(BaseModel):
    """
    Output Template for the Extractor Agent.
    It contains all the Information Available of a Tender in a structured way.
    """

    ## Identifiers
    cig: Optional[str] = Field(default = None, description = "Identification Bid Code")
    cup: Optional[str] = Field(default = None, description = "Unified Project Code")
    title: str
    url: HttpUrl

    ## Classification
    cpv: Optional[list[str]] = Field(
        default = None,
        description = "CPV Codes list (i.e. ['72000000', '48000000'])"
    )
    contract_type: Optional[str] = Field(
        default = None,
        description = "Services / Supplies / Construction Work"
    )

    ## Contracting Authority
    contracting_authority: Optional[ContractingAuthority] = None

    ## Economical Value
    base_amount: Optional[float] = Field(default = None, description = "Base auction amount  in Euros")
    max_amount: Optional[float] = Field(default = None, description = "Maximum value, including renewals")
    # award_criterion: Optional[str] = Field(
    #     default = None,
    #     description = "OEPV (quality + price) or OPB (price only)"
    # )

    ## Date Information
    publication_date: Optional[dt.date] = None
    deadline: Optional[dt.datetime] = Field(
        default = None,
        description="Bid submission deadline"
    )
    contract_duration_months: Optional[int] = None

    ## Requirements (as Text)
    # financial_requirements: Optional[str] = None
    # techincal_requirements: Optional[str] = None

    ## Documentation
    url_docs: Optional[list[HttpUrl]] = Field(
        default = None,
        description = "Links to tender documents, specifications, and PDF attachments"
    )

    ## Extraction Meta Data
    portal: str
    extraction_date: dt.datetime = Field(default_factory = dt.datetime.now)
    status: Status = Field(
        default = 'success',
        description = "'success', 'partial' (for missing fields), 'error'"
    )
    error: Optional[str] = None



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
