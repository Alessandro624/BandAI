# Data Models

All models use Pydantic v2 for validation and serialization. Pipeline models are in `models/models.py`; knowledge models are in `models/knowledge.py`.

## Knowledge Models

### CompanyProfile

The single source of truth for company data. Loaded from `knowledge/company_profile.json` via `load_company_profile()`.

```python
class CompanyProfile(BaseModel):
    name: str
    vat_number: str
    ateco_codes: list[str]
    certifications: list[str]
    turnover_last_3y_eur: list[float]
    employees: int
    max_bid_value_eur: float
    past_public_contracts: list[PastContract]
    departments: dict[str, DepartmentProfile]
```

Every crew reads this at build time. The profile is injected into task descriptions (as formatted strings) and also embedded as a CrewAI `StringKnowledgeSource` for semantic retrieval.

### DepartmentProfile

Capabilities and evidence for a single department.

```python
class DepartmentProfile(BaseModel):
    capabilities: list[str]
    certifications: list[str]
    case_studies: list[str]
    kpis: dict[str, Any]
```

Keys in the `departments` dict become department names. Each department gets its own agent in the Proposal crew.

### PastContract

A previously completed public contract.

```python
class PastContract(BaseModel):
    title: str
    value_eur: float
    cpv_codes: list[str]
    year: int
    authority: str
    topics: list[str]
```

Used by the Compliance crew to demonstrate track record.

---

## Scouting Models

### RawContract

Unprocessed tender scraped from a portal. Note the `cpvCodes` alias - portal data may use camelCase.

```python
class RawContract(BaseModel):
    portal: str
    url: str
    title: str
    contract_id: str | None = None
    contracting_authority: str
    deadline: str
    value_eur: float | None = None
    cpv_codes: list[str] = Field(alias="cpvCodes")
    raw_text: str
```

### ResolvedContract

Deduplicated, canonical tender with consensus metadata. This is the output of the Resolution Agent.

```python
class ResolvedContract(BaseModel):
    canonical_contract_id: str
    title: str
    contracting_authority: str
    deadline: str
    value_eur: float | None
    cpv_codes: list[str]
    sources: list[str]
    consensus_score: float = Field(ge=0.0, le=1.0)
    canonical_url: str
```

`consensus_score` = portal_weight × (portals_that_listed / total_portals_crawled). Higher means more reliable deduplication.

---

## Compliance Models

### AdvocateAnalysis

The optimist's view. Every requirement maps to a category.

```python
class AdvocateAnalysis(BaseModel):
    requirements_met: list[str]
    requirements_potentially_met: list[str]
    risk_mitigations: list[str]
    overall_sentiment: Literal["strongly_positive", "positive", "cautiously_positive"]
    confidence_score: float = Field(ge=0.0, le=1.0)
    summary: str
```

### AuditorChallenge

The skeptic's rebuttal.

```python
class AuditorChallenge(BaseModel):
    hard_blockers: list[str]
    soft_risks: list[str]
    advocate_overestimates: list[str]
    overall_sentiment: Literal["high_risk", "medium_risk", "manageable_risk"]
    risk_score: float = Field(ge=0.0, le=1.0)
    summary: str
```

### ComplianceVerdict

The binding decision. This is the output that drives flow routing.

```python
class ComplianceVerdict(BaseModel):
    bid_decision: Literal["GO", "NO-GO", "CONDITIONAL-GO"]
    conditions: list[str] = Field(default_factory=list)
    key_risks: list[str]
    key_strengths: list[str]
    compliance_score: float = Field(ge=0.0, le=1.0)
    legal_flags: list[str] = Field(default_factory=list)
    verdict_rationale: str
```

- `bid_decision` directly maps to flow routing in `route_verdict()`.
- `conditions` is populated only for CONDITIONAL-GO. Each condition is a concrete action required before submission.
- `legal_flags` references specific D.Lgs. 36/2023 articles.
- `verdict_rationale` is written in plain Italian for the CEO (max 150 words).

---

## Proposal Models

### DepartmentBid

A department's pitch for inclusion in the proposal.

```python
class DepartmentBid(BaseModel):
    department: str
    headline_capability: str
    evidence: list[str]
    differentiators: list[str]
    suggested_section: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    evidence_quality_score: float = Field(ge=0.0, le=1.0)
    word_budget: int
```

`evidence_quality_score` is self-reported by the department agent. The auctioneer trusts it but applies it as one component of the composite score, so gaming a single dimension doesn't win.

### AuctionResult

The auctioneer's selection.

```python
class AuctionResult(BaseModel):
    winning_bids: list[DepartmentBid]
    rejected_bids: list[str]
    section_allocation: dict[str, str]
    total_word_budget: int
    rationale: str
```

`rejected_bids` entries include a rejection reason: `low_score`, `section_already_covered`, or `word_budget_exceeded`.

### FinalProposal

The complete proposal document.

```python
class FinalProposal(BaseModel):
    tender_ref: str
    executive_summary: str
    sections: dict[str, str]
    appendices: list[str] = Field(default_factory=list)
    compliance_declarations: list[str]
    word_count: int
    quality_score: float = Field(ge=0.0, le=1.0)
```

The `ProposalWriterTool` converts `sections` into a Markdown file on disk. `quality_score` is the architect's self-assessment.
