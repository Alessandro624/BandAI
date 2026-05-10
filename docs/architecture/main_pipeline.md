# Main Pipeline Architecture

## Overview

`src/bandai/main.py` is the main orchestration entrypoint for the BandAI procurement pipeline.

The pipeline currently supports three execution modes:

- `full`: runs scouting, compliance analysis, and proposal generation.
- `scout`: runs only the tender scouting phase.
- `propose`: runs compliance and proposal generation for a manually provided contract id.

## Pipeline Phases

### 1. Scouting Phase

Function: `run_scouting()`

Responsibilities:

- Ask the user for scouting preferences.
- Build and run the `ScoutCrew`.
- Parse the scouting output into contract dictionaries.
- Save discovered contracts to `output/01_scout_results.json`.

Output:

- `list[dict]` representing discovered contracts.

### 2. Compliance Phase

Function: `run_compliance()`

Responsibilities:

- Convert each contract into a readable summary.
- Build and run the `ComplianceCrew`.
- Handle `GO`, `NO-GO`, and `CONDITIONAL-GO` decisions.
- Ask for human input when a contract is conditionally acceptable.
- Save compliance outputs to `output/02_compliance_*.json`.
- Save NO-GO contracts requiring review to `output/02_no_go_review_required.json`.

Output:

- `list[tuple[dict, ComplianceVerdict]]` containing approved contracts and their verdicts.

### 3. Proposal Generation Phase

Function: `run_proposals()`

Responsibilities:

- Build and run the `ProposalCrew` for approved contracts.
- Generate structured proposal outputs.
- Save proposal files to `output/03_proposal_*.json`.

Output:

- `list[FinalProposal]`.

## Entry Points

### `run()`

Main project entrypoint exposed as:

```bash
uv run bandai