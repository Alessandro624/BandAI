# Data Models Architecture

## Overview

BandAI uses Pydantic models to define structured data exchanged between crews, tasks, and pipeline phases.

The models are defined in:

```text
src/bandai/models/models.py
```

These models help make agent outputs more predictable and easier to validate.

## Model Groups

The current models can be grouped into four areas:

| Area | Models |
|---|---|
| Contract discovery | `RawContract`, `ResolvedContract` |
| Compliance analysis | `AdvocateAnalysis`, `AuditorChallenge`, `ComplianceVerdict` |
| Proposal auction | `DepartmentBid`, `AuctionResult` |
| Final proposal | `FinalProposal` |

## Contract Discovery Models

### `RawContract`

Represents an initial tender notice found by crawler tools or procurement portals.

Main fields:

- `portal`: source portal name
- `url`: tender URL
- `title`: tender title
- `contract_id`: optional source-specific contract identifier
- `contracting_authority`: public authority issuing the tender
- `deadline`: submission deadline
- `value_eur`: optional tender value in EUR
- `cpv_codes`: list of CPV codes
- `raw_text`: raw extracted tender text

Used by:

- crawler tools
- scouting phase
- tender discovery workflows

### `ResolvedContract`

Represents a normalized and deduplicated tender opportunity.

Main fields:

- `canonical_contract_id`
- `title`
- `contracting_authority`
- `deadline`
- `value_eur`
- `cpv_codes`
- `sources`
- `consensus_score`
- `canonical_url`

`consensus_score` is constrained between `0.0` and `1.0`.

Used by:

- `ScoutCrew`
- `run_scouting()`
- compliance phase input

## Compliance Models

### `AdvocateAnalysis`

Represents the positive/bid-supporting analysis produced by the advocate agent.

Main fields:

- `requirements_met`
- `requirements_potentially_met`
- `risk_mitigations`
- `overall_sentiment`
- `confidence_score`
- `summary`

`confidence_score` is constrained between `0.0` and `1.0`.

Allowed sentiment values:

```text
strongly_positive
positive
cautiously_positive
```

### `AuditorChallenge`

Represents the critical/risk-focused analysis produced by the auditor agent.

Main fields:

- `hard_blockers`
- `soft_risks`
- `advocate_overestimates`
- `overall_sentiment`
- `risk_score`
- `summary`

`risk_score` is constrained between `0.0` and `1.0`.

Allowed sentiment values:

```text
high_risk
medium_risk
manageable_risk
```

### `ComplianceVerdict`

Represents the final bid/no-bid decision for a contract.

Main fields:

- `bid_decision`
- `conditions`
- `key_risks`
- `key_strengths`
- `compliance_score`
- `legal_flags`
- `verdict_rationale`

Allowed bid decisions:

```text
GO
NO-GO
CONDITIONAL-GO
```

`compliance_score` is constrained between `0.0` and `1.0`.

Used by:

- `ComplianceCrew`
- human review loop
- proposal phase filtering
- pipeline summary output

## Proposal Auction Models

### `DepartmentBid`

Represents a department-level contribution proposal.

Main fields:

- `department`
- `headline_capability`
- `evidence`
- `differentiators`
- `suggested_section`
- `relevance_score`
- `evidence_quality_score`
- `word_budget`

Both `relevance_score` and `evidence_quality_score` are constrained between `0.0` and `1.0`.

Used by:

- department representative agents in `ProposalCrew`
- auctioneer task

### `AuctionResult`

Represents the auctioneer's decision after evaluating all department bids.

Main fields:

- `winning_bids`
- `rejected_bids`
- `section_allocation`
- `total_word_budget`
- `rationale`

Used by:

- auctioneer agent
- proposal architect agent

## Final Proposal Model

### `FinalProposal`

Represents the final structured proposal output.

Main fields:

- `tender_ref`
- `executive_summary`
- `sections`
- `appendices`
- `compliance_declarations`
- `word_count`
- `quality_score`

`quality_score` is constrained between `0.0` and `1.0`.

Used by:

- `ProposalCrew`
- `run_proposals()`
- output serialization to `output/03_proposal_*.json`

## Cross-Phase Data Flow

```text
RawContract
    ↓
ResolvedContract
    ↓
ComplianceVerdict
    ↓
DepartmentBid
    ↓
AuctionResult
    ↓
FinalProposal
```

In practice, some handoffs are still dictionary-based in `main.py`, but the target architecture should increasingly rely on these typed models.

## Validation Rules

The models currently enforce:

- score values between `0.0` and `1.0`
- restricted decision values through `Literal`
- default empty lists for optional collections such as `conditions`, `legal_flags`, and `appendices`

## Current Limitations

- Some dates are stored as plain strings instead of typed date fields.
- Some URLs are stored as plain strings instead of URL-validated types.
- Some cross-phase handoffs still use dictionaries.
- `RawContract.cpv_codes` currently uses the alias `cpvCodes`, while other parts of the system may refer to `cpv_codes`.
- `word_budget` and `word_count` do not yet enforce non-negative constraints.
- The models do not yet include company profile or department profile schemas.

## Future Improvements

Potential improvements include:

- Add date validation for tender deadlines.
- Add URL validation for tender and source URLs.
- Add non-negative constraints for budgets and word counts.
- Add company profile and department profile models.
- Standardize CPV field naming across tools, prompts, and models.
- Replace dictionary handoffs in `main.py` with typed model instances.
- Add unit tests for model validation.