# Configuration

## Environment Variables

| Variable | Default | Required | Description |
| ------------------------- | ---------------- | ---------- | ------------------------------------------ |
| `LLM_PROVIDER` | `openrouter` | No | Provider profile name |
| `OPENROUTER_API_KEY` | - | Yes* | OpenRouter API key |
| `ANTHROPIC_API_KEY` | - | Yes* | Anthropic API key |
| `OPENAI_API_KEY` | - | Yes* | OpenAI API key |
| `API_KEY` | - | No | Generic fallback key |
| `MAX_REVIEW_ITERATIONS` | `5` | No | Max human review cycles for CONDITIONAL-GO |
| `DEFAULT_PORTAL_WEIGHT` | `0.5` | No | Weight for unlisted portals [0.0, 1.0] |

| `MAIN_MODEL` | provider/model or model name | No | Override main model for reasoning-heavy agents (e.g. `anthropic/claude-sonnet-4-20250514` or `llama3`). |
| `MAIN_TEMPERATURE` | `0.3` | No | Override temperature for main model |
| `MAIN_MAX_TOKENS` | `4096` | No | Override max tokens for main model |
| `FAST_MODEL` | provider/model or model name | No | Override fast model for parallel tasks (e.g. `openai/gpt-4o-mini`). |
| `FAST_TEMPERATURE` | `0.3` | No | Override temperature for fast model |
| `FAST_MAX_TOKENS` | `4096` | No | Override max tokens for fast model |
| `PROVIDER_BASE_URL` | provider default | No | Override provider base URL (useful for local/self-hosted endpoints) |

| `EMBEDDER_PROVIDER` | - | No | Optional embedder provider for RAG/memory (e.g. `ollama`, `openai`, `openrouter`). If unset, no custom embedder is used. |
| `EMBEDDER_MODEL` | provider/model or model name | No | Embedder model (e.g. `mxbai-embed-large` or `openai/text-embedding-3-large`). |
| `EMBEDDER_BASE_URL` | - | No | Base URL for embedder provider (override for local servers). |
| `EMBEDDER_API_KEY` | - | No | API key for embedder provider |

| `DISABLE_MEMORY` | `false` | No | Disable memory |

*Required for the corresponding provider. Only one provider's key needs to be set.

Key resolution order: `{PROVIDER}_API_KEY` -> `API_KEY` -> error.

## LLM Providers

Four built-in provider profiles in `config/_constants.py`:

| Provider | Main Model | Fast Model | Use Case |
| ------------- | ------------------------------------ | --------------------------------- | ------------------- |
| `openrouter` | `anthropic/claude-sonnet-4-20250514` | `openai/gpt-4o-mini` | Multi-provider routing |
| `anthropic` | `claude-sonnet-4-20250514` | `claude-haiku-3-5-20241022` | Direct Anthropic |
| `openai` | `gpt-4o` | `gpt-4o-mini` | Direct OpenAI |
| `ollama` | `llama3` | `llama3` | Local, no API key |

Each profile has a `main` slot (for reasoning-heavy agents: Compliance Officer, Auctioneer, Resolution Agent) and a `fast` slot (for parallel/scalable agents: Crawlers, Department Reps).

Temperature and max tokens have sensible defaults in the provider profiles (typically `0.3` and `4096`).

Environment overrides
: You can override model, temperature and max tokens at runtime using environment variables. Set `MAIN_MODEL`, `MAIN_TEMPERATURE`, and `MAIN_MAX_TOKENS` to change the reasoning model; set `FAST_MODEL`, `FAST_TEMPERATURE`, and `FAST_MAX_TOKENS` to change the fast model. Each `*_MODEL` may be either a bare model name (e.g. `llama3`) or a provider-prefixed identifier `provider/model` (e.g. `openai/text-embedding-3-large`). If a provider prefix is present the code uses it as-is; otherwise the configured `LLM_PROVIDER` is applied as the prefix.

### Adding a Custom Provider

```python
from bandai.config import ProviderProfile, LLMProfile, PROVIDERS

PROVIDERS["groq"] = ProviderProfile(
    name="groq",
    description="Groq - fast inference",
    base_url="https://api.groq.com/openai/v1",
    main=LLMProfile(model="llama-3.3-70b-versatile"),
    fast=LLMProfile(model="llama-3.1-8b-instant"),
    env_key="GROQ_API_KEY",
)
```

Then set `LLM_PROVIDER=groq` in `.env`.

## Memory Configuration (RAG / Knowledge)

BandAI uses CrewAI's unified memory system with optional embedder support for RAG and long-term knowledge persistence. Memory is automatically configured in all crews via `get_memory()` helper.

**Configuration variables:**

- `EMBEDDER_PROVIDER`: provider name (e.g. `ollama`, `openai`, `openrouter`). If unset, memory system uses no custom embedder.
- `EMBEDDER_MODEL`: model name or provider/model string (e.g. `mxbai-embed-large`, `openai/text-embedding-3-large`, or `nvidia/llama-nemotron-embed-vl-1b-v2:free`).
- `EMBEDDER_BASE_URL`: optional base URL for embedder provider (useful for local/self-hosted servers).
- `EMBEDDER_API_KEY`: optional API key for embedder provider.

**Implementation:**

The runtime helper `bandai.config.get_memory()` centralizes memory configuration:

- Uses `get_llm(fast=True)` for memory LLM (faster than main model)
- Reads embedder config from environment via `get_embedder()`
- Returns a fully-configured `Memory` object compatible with `Crew(memory=...)`

```python
from bandai.config import get_memory
from crewai import Crew

crew = Crew(
    agents=[...],
    tasks=[...],
    memory=get_memory(),  # Automatically handles both LLM and embedder config
)
```

This pattern ensures all crews use consistent LLM and embedder settings from environment variables.

### OpenRouter Embedding

When `EMBEDDER_PROVIDER=openrouter`, BandAI uses a custom `OpenRouterEmbeddingFunction` in `config/embedder.py` that calls the OpenRouter API directly via `requests` (not the OpenAI SDK). It auto-detects vision-language (VL) models by checking for keywords (`vl`, `vision`, `vila`, `nemo-vl`) in the model name and adjusts the request payload format accordingly. Default model: `nvidia/llama-nemotron-embed-vl-1b-v2:free`.

When switching embedder providers (e.g. from `ollama` to `openrouter`), clear stored memories to avoid dimension mismatches:

```bash
crewai reset-memories -a
```

## Portal Configuration

Defined in `config/portals.yaml`. Each entry specifies a procurement portal for the Scout crew to crawl.

```yaml
portals:
  - name: "ANAC / Simog"
    base_url: "https://www.anticorruzione.it/-/bandi-di-gara"
    reliability: 1.00          # Weight for consensus polling

  - name: "TED (EU)"
    base_url: "https://www.ted.europa.eu/en/search/result"
    reliability: 0.90
    country_filter: "IT"       # Optional ISO country filter
```

- `name` - Identifier used in agent roles and weight tables.
- `base_url` - Portal entry URL.
- `reliability` - Float in [0.0, 1.0]. Higher = more authoritative. ANAC is the canonical source for Italian contracts (1.00). TED is the EU-wide source (0.90).
- `country_filter` - Optional. Restricts results to a country code.

Portals are loaded at import time into `BANDI_PORTALS` (a `list[PortalConfig]`). Portal weights are computed into `PORTAL_WEIGHTS` dict for the Resolution Agent's consensus polling.

## Startup Validation

`validate_config()` runs at startup and checks:

1. `LLM_PROVIDER` references a known profile.
2. API key is set and not a placeholder.
3. `knowledge/company_profile.json` exists.
4. `config/portals.yaml` exists.

Any failure prints a clear error message and exits with code 1.

## Implicit NO-GO Keywords

A keyword list in `utils.py` (`NO_GO_KEYWORDS`) that triggers an immediate NO-GO verdict during human review without an LLM call. Catches abandonment language in Italian and English:

- Italian: "non abbiamo", "impossibile", "rinunciamo", "lasciamo perdere", "fermiamo", "ritiriamo"
- English: "we don't have", "we can't", "impossible", "give up", "quit", "stop"

To extend, add entries to the `NO_GO_KEYWORDS` list in `utils.py`.
