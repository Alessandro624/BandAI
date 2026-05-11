# Configuration Architecture

## Overview

BandAI configuration is split between Python configuration and YAML-based CrewAI prompt/task configuration.

The main configuration files are located under:

```text
src/bandai/config/
```

This directory currently contains:

```text
config.py
agents_scout.yaml
tasks_scout.yaml
agents_compliance.yaml
tasks_compliance.yaml
agents_proposal.yaml
tasks_proposal.yaml
```

## `config.py`

`src/bandai/config/config.py` contains runtime configuration used by the Python orchestration code and crews.

It currently handles:

- environment variable loading
- LLM provider and model configuration
- procurement portal definitions
- portal reliability weights
- review iteration limits
- implicit `NO-GO` keywords
- temporary company profile data

## Environment Variables

The project loads environment variables using:

```python
load_dotenv()
```

The main environment variables are:

| Variable | Purpose |
|---|---|
| `PROVIDER_BASE_URL` | Base URL for the LLM provider |
| `API_KEY` | Provider API key |
| `MAIN_MODEL` | Main model for reasoning-heavy tasks |
| `MAIN_TEMPERATURE` | Temperature for the main model |
| `MAIN_MAX_TOKENS` | Max tokens for the main model |
| `FAST_MODEL` | Lightweight model for parallel/fast tasks |
| `FAST_TEMPERATURE` | Temperature for the fast model |
| `FAST_MAX_TOKENS` | Max tokens for the fast model |
| `DEFAULT_PORTAL_WEIGHT` | Fallback reliability score for unknown portals |
| `MAX_REVIEW_ITERATIONS` | Maximum human review iterations for conditional opportunities |

## LLM Configuration

The `get_llm()` function creates a CrewAI `LLM` object.

It supports two model profiles:

- main model: used for reasoning-heavy tasks
- fast model: used for cheaper/faster parallel agents

Example usage:

```python
get_llm(fast=False)
get_llm(fast=True)
```

The fast model is used by agents such as portal crawlers or department representatives where lower latency and cost may be preferred.

The main model is used for reasoning-heavy tasks such as resolution, compliance decisions, and proposal synthesis.

## Procurement Portals

Procurement portals are defined in:

```python
BANDI_PORTALS
```

Each portal entry currently contains:

- `name`
- `base_url`
- `reliability`
- `country_filter`

Current configured portals include:

- ANAC / Simog
- TED (EU)
- MePA
- Sardegna CAT

These portals are used by `ScoutCrew` to create crawler agents dynamically.

## Portal Weights

Portal reliability weights are derived from `BANDI_PORTALS`:

```python
PORTAL_WEIGHTS
```

If a portal does not have an explicit reliability value, the system falls back to:

```text
DEFAULT_PORTAL_WEIGHT
```

The default portal weight is constrained to the range `0.0` to `1.0`. If the configured value is outside this range, it falls back to `0.5`.

## Review Iterations

The maximum number of human review iterations is configured through:

```text
MAX_REVIEW_ITERATIONS
```

This value is used during the compliance phase when a contract receives a `CONDITIONAL-GO` verdict.

Its purpose is to prevent infinite review loops.

## Implicit NO-GO Keywords

`IMPLICIT_NO_GO_KEYWORDS` contains Italian and English phrases used to detect when a user is implicitly abandoning an opportunity.

Examples include:

- `non abbiamo`
- `non possiamo`
- `impossibile`
- `rinunciamo`
- `we can't`
- `give up`

These keywords are checked before making additional LLM calls during human review.

## Company Profile

`CompanyProfile` currently stores temporary company data directly in Python.

It includes:

- company name
- VAT number
- ATECO codes
- certifications
- turnover history
- employee count
- departments
- past public contracts
- maximum bid value

This data is used by compliance and proposal crews to reason about company eligibility and capabilities.

## Current Limitations

- Company profile data is still hardcoded in `config.py`.
- Procurement portals are hardcoded in Python instead of external configuration.
- Environment variable validation is minimal.
- Some defaults are provider-specific.
- Sensitive values depend on the local `.env` file and should never be committed.
- There is no structured schema yet for company profiles or department profiles.
- Configuration is split between `.env`, Python constants, and YAML files.

## Future Improvements

Potential improvements include:

- Move company profile data into `knowledge/`.
- Add structured `CompanyProfile` and `DepartmentProfile` Pydantic models.
- Move procurement portal definitions into a YAML or JSON config file.
- Validate required environment variables at startup.
- Add clear provider/model examples without forcing one provider.
- Add configuration tests.
- Support multiple provider profiles.
- Make `Company Onboarding Crew` generate or update company knowledge automatically.

## YAML Agent and Task Configuration

Crew-specific prompts and task definitions are stored in YAML files.

Scout configuration:

```text
agents_scout.yaml
tasks_scout.yaml
```

Compliance configuration:

```text
agents_compliance.yaml
tasks_compliance.yaml
```

Proposal configuration:

```text
agents_proposal.yaml
tasks_proposal.yaml
```

These files define agent roles, goals, backstories, task descriptions, and expected outputs.

Keeping these values in YAML makes prompt engineering easier without changing Python orchestration code.

## Relationship with Other Architecture Docs

This configuration layer supports:

- `main_pipeline.md`: runtime behavior and CLI execution
- `crews.md`: crew construction and task orchestration
- `models.md`: structured data exchanged across phases
- `tools.md`: tools used by agents inside crews