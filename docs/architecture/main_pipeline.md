# Main Pipeline Architecture

## Overview

`src/bandai/main.py` is the main orchestration entrypoint for the BandAI procurement pipeline.

The pipeline coordinates the high-level execution flow across three main phases:

1. tender scouting
2. compliance analysis
3. proposal generation

The implementation currently uses CrewAI crews directly. Future versions may introduce CrewAI Flows for more explicit state management and orchestration.

## Execution Modes

The pipeline currently supports three execution modes:

- `full`: runs scouting, compliance analysis, and proposal generation.
- `scout`: runs only the tender scouting phase.
- `propose`: runs compliance and proposal generation for a manually provided contract id.

Example commands:

```bash
uv run bandai --mode full
uv run bandai --mode scout
uv run bandai --mode propose --contract <CONTRACT_ID>
uv run bandai --dry-run
```

`--dry-run` validates the CLI entrypoint without making LLM calls.

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

The scouting phase is responsible for discovering potentially relevant tender opportunities from configured procurement portals.

### 2. Compliance Phase

Function: `run_compliance()`

Responsibilities:

- Convert each contract into a readable summary.
- Build and run the `ComplianceCrew`.
- Evaluate each opportunity as `GO`, `NO-GO`, or `CONDITIONAL-GO`.
- Ask for human input when a contract is conditionally acceptable.
- Save compliance outputs to `output/02_compliance_*.json`.
- Save `NO-GO` contracts requiring review to `output/02_no_go_review_required.json`.

Output:

- `list[tuple[dict, ComplianceVerdict]]` containing approved contracts and their verdicts.

The compliance phase is responsible for filtering opportunities before proposal generation. It protects the system from generating proposals for contracts that are not eligible, too risky, or blocked by missing requirements.

### 3. Proposal Generation Phase

Function: `run_proposals()`

Responsibilities:

- Build and run the `ProposalCrew` for approved contracts.
- Generate structured proposal outputs.
- Save proposal files to `output/03_proposal_*.json`.

Output:

- `list[FinalProposal]`.

The proposal phase only runs for contracts that pass compliance as `GO` or remain acceptable as `CONDITIONAL-GO`.

## Entry Points

### `run()`

Main project entrypoint exposed as:

```bash
uv run bandai
```

Supported commands:

```bash
uv run bandai --mode full
uv run bandai --mode scout
uv run bandai --mode propose --contract <CONTRACT_ID>
uv run bandai --dry-run
```

`run()` parses CLI arguments, selects the requested execution mode, runs the required pipeline phases, and prints a summary at the end.

### `train()`

Wrapper around the CrewAI training command.

Example:

```bash
uv run train -n 5 -f training.json
```

This forwards arguments to:

```bash
crewai train
```

### `replay()`

Wrapper around the CrewAI replay command.

Example:

```bash
uv run replay -t <task_id>
```

This forwards arguments to:

```bash
crewai replay
```

### `test()`

Wrapper around the CrewAI test command.

Example:

```bash
uv run test -n 5 -m gpt-4o-mini
```

This forwards arguments to:

```bash
crewai test
```

> Note: `train`, `replay`, and `test` may call LLM providers depending on the CrewAI command and arguments used. Use `--help` to inspect options without running a full execution.

### `run_with_trigger()`

Compatibility entrypoint for future trigger-based execution.

Currently, this function delegates to:

```python
run()
```

In the future, it may be extended to accept webhook payloads, API events, scheduled jobs, or other external triggers.

## Human-in-the-loop Review

The compliance phase supports a human review loop for contracts classified as `CONDITIONAL-GO`.

When this happens, the pipeline asks the user for additional information, such as:

- missing certifications
- partner or subcontractor availability
- already acquired documents
- clarifications about technical or legal requirements

The review loop can end in three main ways:

1. The user presses Enter and leaves the verdict unchanged.
2. The user provides abandonment or negative language, triggering an implicit `NO-GO`.
3. The maximum review iteration limit is reached and the contract is forced to `NO-GO`.

The maximum number of review iterations is controlled by:

```text
MAX_REVIEW_ITERATIONS
```

Abandonment or negative intent is detected through configured implicit `NO-GO` keywords.

## Agent and Crew Interaction

The main pipeline does not directly implement agent behavior. Instead, it coordinates specialized crews.

| Phase | Crew | Main responsibility |
|---|---|---|
| Scouting | `ScoutCrew` | Discover and resolve relevant tender opportunities |
| Compliance | `ComplianceCrew` | Evaluate eligibility, risks, and bid/no-bid decisions |
| Proposal generation | `ProposalCrew` | Generate structured proposal content for approved opportunities |

The orchestration flow is:

```text
User preferences
    ↓
run_scouting()
    ↓
ScoutCrew
    ↓
Resolved contracts
    ↓
run_compliance()
    ↓
ComplianceCrew
    ↓
GO / NO-GO / CONDITIONAL-GO verdicts
    ↓
run_proposals()
    ↓
ProposalCrew
    ↓
FinalProposal outputs
```

## Data Flow

The main data objects used by the pipeline are:

| Object | Source | Used by |
|---|---|---|
| `dict` contract candidates | `ScoutCrew` output | compliance phase |
| `ComplianceVerdict` | `ComplianceCrew` output | proposal phase and summary |
| `FinalProposal` | `ProposalCrew` output | output serialization |

Current pipeline handoff is still partly dictionary-based. Future improvements should replace manual dictionaries with stronger typed models wherever possible.

## Output Files

Runtime outputs are written under:

```text
output/
```

Current output examples:

```text
01_scout_results.json
02_compliance_<index>_<contract_id>.json
02_no_go_review_required.json
03_proposal_<index>_<contract_id>.json
```

These files are generated artifacts and should generally not be committed unless explicitly needed for examples or tests.

## Error Handling and Logging

The pipeline uses Python logging through the `bandai` logger.

The main entrypoint logs:

- selected execution mode
- dry-run status
- phase start and completion
- number of discovered contracts
- number of approved contracts
- number of generated proposals
- pipeline failures with traceback information

Dry-run mode can be used to validate the CLI entrypoint without making LLM calls:

```bash
uv run bandai --dry-run
```

## Configuration Dependencies

The main pipeline depends on configuration defined outside `main.py`, including:

- LLM provider settings
- model names
- review iteration limits
- implicit `NO-GO` keywords
- crew configuration files
- procurement portal configuration

Relevant configuration areas include:

```text
src/bandai/config/config.py
src/bandai/config/agents_scout.yaml
src/bandai/config/tasks_scout.yaml
src/bandai/config/agents_compliance.yaml
src/bandai/config/tasks_compliance.yaml
src/bandai/config/agents_proposal.yaml
src/bandai/config/tasks_proposal.yaml
```

## Current Limitations

The current implementation is intentionally simple and still evolving.

Known limitations:

- Pipeline orchestration currently lives directly in `main.py`.
- Crew-specific behavior is implemented in `src/bandai/crews/`.
- Tool implementations are still partially mocked.
- Company profile and department information are still partially hardcoded in configuration.
- The project currently uses crews directly; CrewAI Flows may be introduced later for more explicit state management.
- Full pipeline execution requires a configured LLM provider and sufficient provider credits.
- Intermediate data passing is still partly dictionary-based.

## Future Improvements

Potential improvements for this area include:

- Move pipeline orchestration into a dedicated workflow or flow module.
- Introduce CrewAI Flows for stateful multi-step execution.
- Replace manual dictionary-based contract passing with stronger typed models.
- Improve persistence of intermediate pipeline state.
- Add automated tests for dry-run, CLI parsing, and output serialization.
- Add documentation diagrams for crew interactions.
- Add structured documentation for each crew, agent, task, and tool.