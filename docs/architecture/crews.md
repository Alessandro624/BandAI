# Crew Architecture

## Overview

BandAI uses specialized CrewAI crews to split the procurement workflow into focused responsibilities.

The current pipeline uses three main crews:

- `ScoutCrew`
- `ComplianceCrew`
- `ProposalCrew`

These crews are orchestrated by `src/bandai/main.py`.

Each crew loads its agent and task definitions from YAML files under:

```text
src/bandai/config/
```

This keeps prompt/task configuration separate from Python orchestration logic.

## Crew Summary

| Crew | File | Main responsibility |
|---|---|---|
| `ScoutCrew` | `src/bandai/crews/scout_crew.py` | Discover, enrich, deduplicate, and filter tender opportunities |
| `ComplianceCrew` | `src/bandai/crews/compliance_crew.py` | Evaluate eligibility, risks, and bid/no-bid decisions |
| `ProposalCrew` | `src/bandai/crews/proposal_crew.py` | Generate proposal content for approved opportunities |

## Shared Patterns

All crews follow a similar structure:

1. Load YAML configuration files.
2. Build CrewAI `Agent` objects.
3. Build CrewAI `Task` objects.
4. Connect task context dependencies.
5. Return a `Crew` instance and the final task whose output is consumed by the pipeline.

The current implementation uses `Process.sequential` for crew execution, while some tasks are configured with `async_execution=True` to allow parallel work inside the sequential crew process.

## `ScoutCrew`

File:

```text
src/bandai/crews/scout_crew.py
```

### Purpose

`ScoutCrew` discovers and resolves Italian public tender opportunities.

It builds crawler agents dynamically, one per configured procurement portal. This is useful because the list of portals is configuration-driven rather than hardcoded into a fixed set of CrewAI-decorated methods.

### Configuration files

`ScoutCrew` loads:

```text
agents_scout.yaml
tasks_scout.yaml
```

### Main inputs

- user scouting preferences
- configured procurement portals
- company ATECO codes
- portal reliability weights

The configured portals come from `BANDI_PORTALS`, and portal ranking uses `PORTAL_WEIGHTS` plus `_DEFAULT_PORTAL_WEIGHT`.

### Agents and tasks

#### 1. Crawler agents

For each portal in `BANDI_PORTALS`, the crew creates one crawler agent.

Each crawler agent uses:

- `TenderCrawlerTool`
- `ContractDetailTool`
- fast LLM configuration via `get_llm(fast=True)`

Each crawler task runs with:

```python
async_execution=True
```

This allows portal crawling tasks to run in parallel.

#### 2. Resolution agent

The resolution agent receives all crawler task outputs as context.

Its role is to resolve duplicate or overlapping tender notices and produce normalized contract information.

It uses:

- `ContractDetailTool`
- main LLM configuration via `get_llm(fast=False)`
- `output_pydantic=list[ResolvedContract]`

#### 3. Preference filter agent

The preference filter agent applies user preferences to the resolved opportunities.

It receives `resolution_task` as context and is configured with:

```python
human_input=True
```

This means the task can pause for user review/confirmation.

### Output

The final relevant output for the main pipeline is the resolution task output, expected as:

```python
list[ResolvedContract]
```

In `main.py`, this output is parsed and converted into contract dictionaries for the compliance phase.

### Interaction flow

```text
Configured procurement portals
    ↓
Crawler agents, one per portal
    ↓
Crawler tasks, async
    ↓
Resolution agent
    ↓
ResolvedContract list
    ↓
Preference filter agent
    ↓
Filtered tender opportunities
```

## `ComplianceCrew`

File:

```text
src/bandai/crews/compliance_crew.py
```

### Purpose

`ComplianceCrew` evaluates whether a discovered contract should be pursued.

It implements a structured debate pattern:

1. an advocate highlights reasons to bid,
2. an auditor challenges assumptions and risks,
3. a compliance officer synthesizes the final verdict.

### Configuration files

`ComplianceCrew` loads:

```text
agents_compliance.yaml
tasks_compliance.yaml
```

### Main inputs

- contract summary
- company name
- company certifications
- turnover history
- past public contracts

Company data comes from `COMPANY`.

### Agents and tasks

#### 1. Advocate

The advocate looks for positive evidence and arguments in favor of bidding.

It uses:

- `ComplianceCheckerTool`
- main LLM configuration via `get_llm()`
- output model: `AdvocateAnalysis`

#### 2. Auditor

The auditor reviews the opportunity critically.

It receives the advocate task as context:

```python
context=[advocate_task]
```

It uses:

- `ComplianceCheckerTool`
- main LLM configuration via `get_llm()`
- output model: `AuditorChallenge`

#### 3. Compliance officer

The compliance officer reads both the advocate and auditor outputs.

It receives both previous tasks as context:

```python
context=[advocate_task, auditor_task]
```

It produces the final compliance decision using:

```python
output_pydantic=ComplianceVerdict
```

### Output

The primary output is:

```python
ComplianceVerdict
```

The verdict includes:

- bid decision: `GO`, `NO-GO`, or `CONDITIONAL-GO`
- conditions
- key risks
- key strengths
- compliance score
- legal flags
- rationale

### Human review

`ComplianceCrew` also provides `build_review()` for cases where the main pipeline needs to re-evaluate a `CONDITIONAL-GO` contract after human input.

The review crew contains a single reviewer agent configured from:

```text
human_input_review_agent
human_review_task
```

It receives:

- original verdict JSON
- human note
- current iteration
- maximum review iteration count

It outputs a new `ComplianceVerdict`.

### Interaction flow

```text
Contract summary
    ↓
Advocate agent
    ↓
AdvocateAnalysis
    ↓
Auditor agent
    ↓
AuditorChallenge
    ↓
Compliance officer
    ↓
ComplianceVerdict
```

For human review:

```text
Original ComplianceVerdict
    +
Human clarification note
    ↓
Human input review agent
    ↓
Updated ComplianceVerdict
```

## `ProposalCrew`

File:

```text
src/bandai/crews/proposal_crew.py
```

### Purpose

`ProposalCrew` generates proposal content for contracts approved by the compliance phase.

It uses an internal auction-like pattern where department representatives compete to propose relevant capabilities, evidence, differentiators, and section contributions.

### Configuration files

`ProposalCrew` loads:

```text
agents_proposal.yaml
tasks_proposal.yaml
```

### Main inputs

- contract summary
- company name
- department profiles
- total word limit

### Department profiles

The current implementation defines department profiles directly in `proposal_crew.py`.

Current departments include:

- Cloud Infrastructure
- Cybersecurity
- Software Development
- Customer Support & SLA Management
- Project Management Office

Each department profile can include:

- capabilities
- certifications
- case studies
- KPIs

This is currently hardcoded and should eventually move into a company knowledge base or onboarding-generated profile.

### Agents and tasks

#### 1. Department representative agents

For each department in `DEPARTMENT_PROFILES`, the crew creates a department representative agent.

Each representative uses:

```python
get_llm(fast=True)
```

Each department bid task runs with:

```python
async_execution=True
```

Each task outputs:

```python
DepartmentBid
```

#### 2. Auctioneer

The auctioneer receives all department bid tasks as context:

```python
context=dept_bid_tasks
```

It chooses the strongest department contributions and produces:

```python
AuctionResult
```

#### 3. Proposal architect

The proposal architect receives the auction result as context:

```python
context=[auction_task]
```

It uses:

- `ProposalWriterTool`
- main LLM configuration via `get_llm()`

It produces:

```python
FinalProposal
```

### Output

The primary output is:

```python
FinalProposal
```

The proposal includes:

- tender reference
- executive summary
- proposal sections
- appendices
- compliance declarations
- word count
- quality score

### Interaction flow

```text
Approved contract summary
    ↓
Department representatives, async
    ↓
DepartmentBid outputs
    ↓
Auctioneer
    ↓
AuctionResult
    ↓
Proposal architect
    ↓
FinalProposal
```

## Cross-Crew Data Flow

The full workflow across crews is:

```text
User preferences
    ↓
ScoutCrew
    ↓
ResolvedContract opportunities
    ↓
main.py parses/resolves contract dictionaries
    ↓
ComplianceCrew
    ↓
ComplianceVerdict
    ↓
GO / CONDITIONAL-GO contracts
    ↓
ProposalCrew
    ↓
FinalProposal
```

## Current Limitations

- Some tools used by the crews are still mock implementations.
- Department profiles are currently hardcoded in `proposal_crew.py`.
- Company profile data is still partially hardcoded in configuration.
- Some handoffs still use dictionaries instead of fully typed Pydantic models.
- Crew configuration is split across Python and YAML, so prompt changes require careful coordination.
- Full execution requires a configured LLM provider and sufficient credits.
- The project currently uses direct crew orchestration rather than CrewAI Flows.

## Future Improvements

Potential improvements include:

- Add a `CompanyOnboardingCrew`.
- Move department profiles into the `knowledge/` directory.
- Improve YAML prompts with stricter structured inputs and outputs.
- Add validation tests for each crew.
- Add integration tests for cross-crew handoffs.
- Replace dictionary handoffs with typed models.
- Add diagrams for crew-level interactions.
- Evaluate whether CrewAI Flows would make the sequential pipeline more explicit and easier to test.