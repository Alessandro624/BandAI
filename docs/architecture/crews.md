# Crews

BandAI has three crews, they all use `memory=get_memory()` for cross-session learning and unified embedder configuration.

## ScoutCrew

**File:** `crews/scout_crew.py`
**Config:** `config/agents_scout.yaml`, `config/tasks_scout.yaml`

Discovers and deduplicates Italian public tenders across multiple procurement portals. The number of crawler agents is dynamic - one per portal defined in `config/portals.yaml`.

### Agents

| Agent | LLM | Tools | Notes |
| ------------------------ | ------- | -------------------------------- | ------------------------------ |
| Crawler Agent (×N) | fast | TenderCrawlerTool, ContractDetailTool | One per portal, async |
| Resolution Agent | main | ContractDetailTool | `inject_date=True` |
| Preference Filter | main | - | `human_input=True` |

### Task Chain

```text
crawl_task (×N, async) -> resolution_task -> preference_filter_task
```

1. **crawl_task** - Each crawler searches one portal for tenders matching Italian ICT/cloud CPV codes. Returns `RawContract` JSON arrays.
2. **resolution_task** - Deduplicates across portals using Contract ID matching and +/-5% value tolerance. Applies weighted consensus polling using portal reliability scores. Returns `ResolvedContract` JSON array ranked by `value_eur` descending. Guardrail: output must be a raw JSON array starting with `[`.
3. **preference_filter_task** - Filters and re-ranks based on user preferences. Adds `fit_reason` to each entry. Guardrail: strips markdown fences, validates JSON array format.

### Build Signature

```python
crew, final_task = ScoutCrew().build(user_preferences="...")
crew.kickoff()
data = final_task.output.raw  # JSON string
```

`build()` returns a `(Crew, Task)` tuple. The task is `preference_filter_task`, not the intermediate resolution task.

---

## ComplianceCrew

**File:** `crews/compliance_crew.py`
**Config:** `config/agents_compliance.yaml`, `config/tasks_compliance.yaml`

Runs a structured advocate/auditor debate to produce a bid verdict for a single contract. Two modes: initial assessment (`build()`) and human review re-evaluation (`build_review()`).

### Agents (Initial Assessment)

| Agent              | LLM   | Tools                 | Notes                          |
|--------------------|-------|-----------------------|--------------------------------|
| Advocate           | main  | ComplianceCheckerTool | Optimistic bid manager         |
| Auditor            | main  | ComplianceCheckerTool | Former ANAC inspector          |
| Compliance Officer | main  | -                     | `reasoning=True` for synthesis |

### Task Chain (Initial)

```text
advocate_task -> auditor_task -> verdict_task
```

1. **advocate_task** - Maps every tender requirement to MEETS / POTENTIALLY MEETS / DOES NOT MEET. Proposes mitigations for borderline items. Returns `AdvocateAnalysis`.
2. **auditor_task** - Challenges the advocate's claims point-by-point. Identifies hard blockers vs. soft risks. Returns `AuditorChallenge`.
3. **verdict_task** - Synthesizes both analyses into a binding `ComplianceVerdict`: GO, NO-GO, or CONDITIONAL-GO. Lists D.Lgs. 36/2023 articles in `legal_flags`. Guardrail: validates `bid_decision` enum and `compliance_score` range.

### Agents (Human Review)

| Agent              | LLM   | Notes                     |
|--------------------|-------|---------------------------|
| Re-evaluator       | main  | `inject_date=True`        |

### Task Chain (Review)

```text
human_review_task (standalone)
```

Receives the original CONDITIONAL-GO verdict plus the human's natural language note. Performs a three-step analysis: intent check (detect abandonment), condition mapping, and verdict update. Returns an updated `ComplianceVerdict`.

### Build Signatures

```python
# Initial assessment
crew, verdict_task = ComplianceCrew().build(contract_summary="...")
crew.kickoff()
verdict: ComplianceVerdict = verdict_task.output.pydantic

# Human review
review_crew, review_task = ComplianceCrew().build_review(
    contract_summary="...",
    original_verdict=verdict,
    human_note="we got the ISO cert last week",
    iteration=1,
)
review_crew.kickoff()
updated: ComplianceVerdict = review_task.output.pydantic
```

---

## ProposalCrew

**File:** `crews/proposal_crew.py`
**Config:** `config/agents_proposal.yaml`, `config/tasks_proposal.yaml`

Generates a complete Italian *offerta tecnica* via an internal departmental auction. The number of department agents is dynamic - one per department in the company profile, capped at `MAX_DEPARTMENTS = 15`.

### Agents

| Agent              | LLM   | Tools                | Notes                          |
|--------------------|-------|----------------------|--------------------------------|
| Department Rep (×N)| fast  | -                    | One per department, async      |
| Auctioneer         | main  | -                    | `reasoning=True` for scoring   |
| Proposal Architect | main  | ProposalWriterTool   | Writes final Markdown document |

### Task Chain

```text
dept_bid_task (×N, async) -> auction_task -> proposal_task
```

1. **dept_bid_task** - Each department submits a `DepartmentBid` with relevance score, evidence quality score, word budget request, and suggested section. Honest scoring is enforced because the auctioneer penalises inflated values.
2. **auction_task** - Applies a fixed composite scoring formula:

```text
composite = (relevance_score × 0.50) + (evidence_quality_score × 0.35) + (section_coverage_bonus × 0.15)
```

Selects bids greedily by rank, deconflicts duplicate sections, and scales word budgets proportionally if total exceeds the limit. Returns `AuctionResult`.
3. **proposal_task** - Writes the full proposal in Italian using only the auctioneer-approved content. Sections follow standard PA structure. Includes compliance declarations. Returns `FinalProposal`. The `ProposalWriterTool` writes a Markdown file to `output/`.

### Build Signature

```python
crew, proposal_task = ProposalCrew().build(
    contract_summary="...",
    total_word_limit=3000,
    manager_instructions="Use exact agent role names when delegating work. Do not invent or abbreviate role names.",
)
crew.kickoff()
proposal: FinalProposal = proposal_task.output.pydantic
```

---

## Shared Configuration

Every crew applies these settings to all agents:

| Setting | Value | Purpose |
| -------------------------- | ------- | -------------------------------------- |
| `max_retry_limit` | 2 | Retry on LLM errors |
| `respect_context_window` | True | Auto-summarize when tokens exceed |
| `memory` (crew-level) | `get_memory()` | Cross-session learning with unified LLM and embedder from env |
| `knowledge_sources` | company profile JSON | Semantic embedding of company data |
| `process` | sequential / hierarchical | Proposal uses `hierarchical` for true async parallelism; Scout and Compliance use `sequential` for strict ordering |
| `allow_delegation` | False (all agents) | Prevents agents from delegating tasks to each other |
