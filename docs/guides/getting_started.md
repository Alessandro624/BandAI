# Getting Started

## Prerequisites

- Python 3.11 through 3.13
- UV package manager (`pip install uv`)
- API key for your chosen LLM provider

## Installation

```bash
# Clone the repository
git clone <repo-url> && cd BandAI

# Install dependencies
crewai install
```

`crewai install` resolves dependencies from `pyproject.toml`, generates `uv.lock`, and sets up the virtual environment. The project depends on `crewai[tools]==1.14.4`, `pyyaml`, and `python-dotenv`.

For development extras (pytest, coverage):

```bash
uv pip install -e ".[dev]"
```

## Configuration

### 1. Set API key

Create a `.env` file in the project root:

```bash
# Pick ONE provider
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxx

# Or direct Anthropic
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
```

### 2. Company profile

Edit `knowledge/company_profile.json` with your company data. The template includes:

- Basic info: name, VAT, ATECO codes
- Certifications (ISO, AgID, etc.)
- Financial data: turnover last 3 years, employee count, max bid value
- Past public contracts with CPV codes and authorities
- Department profiles: capabilities, certifications, case studies, KPIs

The profile is loaded and validated at startup. Missing or invalid data triggers a clear error message.

### 3. Portal configuration

Edit `config/portals.yaml` to add or remove procurement portals. The default set includes ANAC/Simog, TED, MePA, and Sardegna CAT. Add new portals by appending entries - the Scout crew picks them up automatically.

## Running

### Full pipeline

```bash
crewai run
# or
bandai --mode full
```

Prompts for preferences via stdin, then runs all three phases: scouting, compliance, proposals.

### Scout only

```bash
bandai --mode scout
```

Discovers tenders and prints results. No compliance or proposal generation.

### Propose for a known contract

```bash
bandai --mode propose --contract GD-2026-00123
```

Skips scouting. Loads the contract with the given ID from `output/01_scout_results.json` and runs compliance + proposal phases.

### Dry run

```bash
bandai --dry-run
```

Validates configuration without making any LLM calls. Useful for checking that API keys, knowledge files, and portal configs are all correct.

## Outputs

All generated artifacts land in `output/`:

```text
output/
├── 01_scout_results.json
├── 02_compliance_01_GD-2026-00123.json
├── 02_no_go_review_required.json
├── 03_proposal_01_GD-2026-00123.json
└── proposal_output.md
```

## Running Tests

```bash
pytest tests/ -v
# or
uv run pytest_unit
```

109 tests covering config validation, provider profiles, portal loading, knowledge models, pipeline models, knowledge sources, flow structure, utility functions, guardrail validation callbacks, and embedder configuration.

## CLI Reference

| Command                 | Description                                   |
|-------------------------|-----------------------------------------------|
| `bandai`                | Run full pipeline                             |
| `bandai --mode scout`   | Scout-only mode                               |
| `bandai --mode propose --contract ID` | Propose mode for known contract |
| `bandai --dry-run`      | Validate config without LLM calls             |
| `crewai test`           | Run CrewAI evaluation (2 iterations)          |
| `crewai train -n 5`     | Train crew with 5 iterations                  |
| `crewai replay -t ID`   | Replay a specific task execution              |
| `crewai flow plot`      | Generate flow diagram HTML                    |
| `crewai reset-memories` | Clear all stored memories                     |
