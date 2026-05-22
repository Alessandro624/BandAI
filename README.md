# BandAI 🏛️🤖

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/Alessandro624/BandAI/actions/workflows/tests.yml/badge.svg)](https://github.com/Alessandro624/BandAI/actions/workflows/tests.yml)
[![CrewAI](https://img.shields.io/badge/CrewAI-Multi--Agent-orange.svg)](https://github.com/joaomdmoura/crewAI)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Turning bureaucracy into competitive intelligence.**

BandAI is a multi-agent decision intelligence platform designed to automate the discovery, evaluation, and proposal generation for Italian public tenders (*bandi pubblici*). Built on top of [CrewAI](https://github.com/joaomdmoura/crewAI), BandAI helps SMEs overcome the bureaucratic friction of public procurement.

---

## 🛑 The Problem

Italian SMEs consistently fail to participate in public tenders due to:

* **Fragmented Discovery:** Tenders are scattered across hundreds of municipal and national portals.
* **Bureaucratic Friction:** Opaque requirements, dense legal jargon, and strict compliance metrics.
* **High Cost of Bidding:** Assembling a compliant technical and administrative response requires expensive cross-functional collaboration.

## 💡 The Solution

BandAI orchestrates a specialized crew of AI agents in a strict, deterministic pipeline. By utilizing adversarial debate for legal compliance and auction-based mechanisms for document synthesis, BandAI ensures that companies only bid on viable tenders and produce mathematically compliant, evidence-backed proposals.

---

## 🏗️ Multi-Agent Architecture

BandAI runs a deterministic three-phase pipeline orchestrated by a CrewAI Flow. Each phase is a separate Crew with specialized agents, guardrails, and structured Pydantic outputs.

### Phase 1 - Scout

Crawls configured procurement portals in parallel, deduplicates results via weighted consensus polling, and filters by user preferences. Output: a ranked list of `ResolvedContract` objects with canonical metadata.

Agents: Portal-specific Crawlers, Resolution Arbiter, Preference Filter.

### Phase 2 - Compliance

Runs an adversarial debate between an Advocate (optimistic bid manager) and an Auditor (former ANAC inspector). A Compliance Officer synthesizes both into a binding verdict: **GO**, **NO-GO**, or **CONDITIONAL-GO**. CONDITIONAL-GO triggers a human review loop with configurable iteration limits.

Agents: Advocate, Auditor, Compliance Officer, Re-evaluator.

### Phase 3 - Proposal

Each company department submits a bid for inclusion. An Auctioneer applies a fixed composite scoring formula to select the best-evidenced content within a word budget. A Proposal Architect writes the final Italian *offerta tecnica*.

Agents: Department Representatives, Auctioneer, Proposal Architect.

---

## 📚 Architecture Documentation

Full technical docs are in `docs/` - start with [docs/README.md](docs/README.md) for the index.

Quick links:

| Doc | What it covers |
| ----- | --------------- |
| [Main Pipeline](docs/architecture/main_pipeline.md) | Flow state machine, modes, transitions, outputs |
| [Crews](docs/architecture/crews.md) | All three crews: agents, tasks, build signatures |
| [Data Models](docs/architecture/models.md) | 11 Pydantic models with field-level reference |
| [Tools](docs/architecture/tools.md) | 4 custom tools, input schemas, current status |
| [Configuration](docs/architecture/configuration.md) | Env vars, providers, portals, validation |
| [Characters](docs/guides/characters.md) | Agent personas, roles, behavioral traits |
| [Flow State Machine](docs/reference/flow_state_machine.md) | Every transition mapped with routing logic |
| [Knowledge System](docs/reference/knowledge_system.md) | StringKnowledgeSource, chunking, RAG pipeline |
| [CLI Reference](docs/reference/cli_reference.md) | `bandai`, `bandai --dry-run`, `run_with_trigger`, CrewAI utilities |
| [Testing](docs/testing.md) | Test strategy, layers, commands, mocking, fixtures |

---

## Project Structure

```text
BandAI/
├── src/bandai/
│   ├── main.py              # Thin entry point, CLI parsing, config validation
│   ├── flow.py              # CrewAI Flow - full pipeline orchestration
│   ├── crews/
│   │   ├── scout_crew.py    # Tender discovery + deduplication
│   │   ├── compliance_crew.py  # Advocate/Auditor debate + verdict
│   │   └── proposal_crew.py    # Department auction + proposal writing
│   ├── models/
│   │   ├── models.py        # 8 pipeline Pydantic models
│   │   └── knowledge.py     # 3 knowledge models: CompanyProfile, DepartmentProfile, PastContract
│   ├── config/
│   │   ├── __init__.py     # Re-exports all config symbols
│   │   ├── _constants.py   # PROVIDERS, LLMProfile, ProviderProfile, NO-GO keywords
│   │   ├── _env.py         # EnvOverrides, get_active_provider, get_api_key
│   │   ├── llm.py          # get_llm (lru_cached)
│   │   ├── embedder.py     # OpenRouterEmbeddingFunction, get_embedder (lru_cached)
│   │   ├── memory.py       # get_memory
│   │   ├── validation.py   # validate_config
│   │   ├── portals.py      # Portal YAML loader, weight computation
│   │   └── *.yaml          # Agent and task definitions per crew
│   ├── tools/
│   │   └── crawler_tools.py # 4 custom CrewAI tools
│   └── knowledge_sources.py # StringKnowledgeSource factory
├── knowledge/
│   └── company_profile.json # Single source of truth for company data
├── tests/
│   └── test_*.py            # 109 tests across 30 test classes
├── docs/                    # Full technical documentation
├── AGENTS.md                # CrewAI coding reference for AI assistants
├── pyproject.toml           # v0.4.0, crewai[tools]==1.14.4, project scripts
└── .env                     # API keys (not committed)
```

---

## 🚀 Getting Started

### Prerequisites

* Python 3.11-3.13
* UV package manager (`pip install uv`)
* API key for an LLM provider (OpenRouter recommended)

### Installation

```bash
git clone <repo-url> && cd BandAI
crewai install
```

### Configuration

Create `.env` in the project root with your LLM provider credentials:

```bash
# LLM Provider (openrouter, anthropic, openai, ollama)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxx

# Optional: override models and parameters
MAIN_MODEL=anthropic/claude-sonnet-4-20250514      # reasoning-heavy tasks
FAST_MODEL=openai/gpt-4o-mini                     # parallel tasks
PROVIDER_BASE_URL=http://localhost:11434          # for local servers

# Optional: configure embedder for RAG/memory
EMBEDDER_PROVIDER=ollama
EMBEDDER_MODEL=mxbai-embed-large
EMBEDDER_BASE_URL=http://localhost:11434

# Optional: disable memory
DISABLE_MEMORY=true
```

Edit `knowledge/company_profile.json` with your company data (name, VAT, certifications, turnover, departments, past contracts). The profile is validated at startup - missing fields produce clear error messages.

**Full configuration guide:** See [docs/architecture/configuration.md](docs/architecture/configuration.md).

### Running

```bash
# Full pipeline (scout + compliance + proposal)
bandai

# Scout only - discover tenders, print results
bandai --mode scout

# Propose for a known contract (skip scouting)
bandai --mode propose --contract GD-2026-00123

# Validate config without LLM calls
bandai --dry-run
```

The same runtime is also exposed as `run_with_trigger` for webhook or API-driven execution.

### Tests

```bash
# Full non-LLM test suite (recommended for PRs and pre-demo)
uv run pytest -q -m "not llm"

# Or run with verbose output
uv run pytest tests/ -v

# Or via the project script
uv run pytest_unit
```

109 tests covering config validation, providers, portals, knowledge models, pipeline models, knowledge sources, flow structure, utility functions, guardrail validation callbacks, embedder configuration, memory, and mocked integration flow. See [docs/testing.md](docs/testing.md) for the full test strategy and CrewAI mocking approach.

---

## Key Features

* **Deterministic flow** - CrewAI Flow with `@start`, `@listen`, `@router`. No ambiguity in execution order.
* **Adversarial compliance** - Advocate vs. Auditor debate produces balanced GO/NO-GO decisions.
* **Human-in-the-loop** - Preference input at start, conditional review during compliance.
* **Departmental auction** - Fixed composite scoring (relevance 50%, evidence 35%, coverage 15%) selects best proposal content.
* **Structured outputs** - All agent outputs are Pydantic models with guardrails. No unstructured text in the pipeline.
* **Multi-provider LLM** - OpenRouter, Anthropic, OpenAI, Ollama. Switch via one env var.
* **Knowledge system** - Company profile embedded via `StringKnowledgeSource` for semantic RAG retrieval.
* **Memory** - Crew-level `memory=get_memory()` for cross-session learning.

---
