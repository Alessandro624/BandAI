# Knowledge System

BandAI uses CrewAI's knowledge system to give agents semantic access to company data, rather than injecting everything into prompts.

## Architecture

```text
knowledge/
└── company_profile.json     <- Single source of truth

knowledge_sources.py         <- Factory: StringKnowledgeSource builder
models/knowledge.py          <- Pydantic models: CompanyProfile, DepartmentProfile, PastContract
```

Two parallel data paths serve different purposes:

1. **Prompt injection** - `load_company_profile()` reads the JSON, validates it through `CompanyProfile` Pydantic model, and injects formatted strings into task descriptions. Used by Compliance and Proposal crews for explicit data like certifications, turnover, and department names.

2. **Semantic embedding** - `get_all_knowledge_sources()` wraps the same JSON in a `StringKnowledgeSource`, which CrewAI chunks and embeds for RAG retrieval. Available to all agents in all crews for implicit, query-driven access.

Both paths read the same file. They're not redundant - prompt injection ensures critical data is always present, while semantic embedding lets agents query for context that isn't explicitly formatted into the prompt.

## Company Profile Structure

```json
{
  "name": "BandAI",
  "vat_number": "IT12345678901",
  "ateco_codes": ["62.01.09", "62.02.00"],
  "certifications": ["ISO 9001:2015", "ISO 27001:2022", "..."],
  "turnover_last_3y_eur": [2100000.0, 2450000.0, 2800000.0],
  "employees": 28,
  "max_bid_value_eur": 1500000.0,
  "past_public_contracts": [
    {
      "title": "...",
      "value_eur": 150000.0,
      "cpv_codes": ["72000000"],
      "year": 2022,
      "authority": "Comune di Milano",
      "topics": ["AI consulting", "public sector"]
    }
  ],
  "departments": {
    "Cloud Infrastructure": {
      "capabilities": ["..."],
      "certifications": ["..."],
      "case_studies": ["..."],
      "kpis": {"uptime_sla": "99.99%", "avg_migration_weeks": 8}
    }
  }
}
```

### Field Reference

| Field                    | Type               | Used By                           |
|--------------------------|--------------------|-----------------------------------|
| `name`                   | str                | All crews (task formatting)       |
| `vat_number`             | str                | Compliance (SOA requirements)     |
| `ateco_codes`            | list[str]          | Scout (CPV matching)              |
| `certifications`         | list[str]          | Compliance (requirement matching) |
| `turnover_last_3y_eur`   | list[float]        | Compliance (financial thresholds) |
| `employees`              | int                | Compliance (SOA size class)       |
| `max_bid_value_eur`      | float              | Compliance (bid ceiling)          |
| `past_public_contracts`  | list[PastContract] | Compliance (track record)         |
| `departments`            | dict[str, Dept]    | Proposal (agent generation)       |

## How Knowledge Sources Work

`StringKnowledgeSource` wraps the company data as formatted JSON text. CrewAI chunks the text by semantic boundaries and embeds each chunk into a vector database. When an agent needs information, CrewAI's RAG pipeline retrieves the most relevant chunks based on the current task context.

The company profile JSON is formatted as human-readable text, making it easier for LLMs to parse and reference specific fields:

```json
{
  "name": "...",
  "vat_number": "...",
  ...
}
```

This approach means:

- No path dependencies - data is loaded once and cached
- Graceful degradation - if RAG fails, agents fall back to prompt-injected data
- Flexible chunking - CrewAI automatically determines optimal chunk boundaries based on semantic similarity

## Knowledge Source Factory

`knowledge_sources.py` exposes three functions:

```python
def get_company_knowledge_data() -> dict[str, Any]:
    # Load and return the company profile JSON as a dict
    # Raises FileNotFoundError if company_profile.json doesn't exist

def get_company_knowledge_source() -> StringKnowledgeSource:
    # Build a StringKnowledgeSource from the company data (formatted as JSON text)
    # Raises FileNotFoundError if data loading fails

def get_all_knowledge_sources() -> list[KnowledgeSource]:
    # Returns list (possibly empty). Never raises.
    # Logs warnings on failure - agents fall back to prompt-only data.
```

All three crews call `get_all_knowledge_sources()` at build time. The sources are passed to the `Crew()` constructor via `knowledge_sources=`.

**Key change from path-based to data-based:**

- No hardcoded file paths in knowledge sources
- Data is loaded once, validated, and converted to knowledge source content
- This enables easy testing and mocking

## Graceful Degradation

If the knowledge system fails (embedding model unavailable, file missing), the pipeline still works. Prompt-injected data covers the critical fields. The knowledge source factory catches all exceptions and returns an empty list, logging a warning:

```text
WARNING | bandai.knowledge_sources | Company profile knowledge source not found -
agents will rely on prompt-injected data only.
```

## Validation

The company profile is validated through `CompanyProfile` Pydantic model at two points:

1. **In `load_company_profile(data: dict | None)`** - when any crew reads the profile:

   ```python
   # Call with no args (uses get_company_knowledge_data internally):
   profile = load_company_profile()
   
   # Or provide a custom dict for testing:
   profile = load_company_profile({"name": "...", ...})
   ```

2. **In `validate_config()` at startup** - before any crew is built, validates that `knowledge/company_profile.json` exists and is parseable.

Missing required fields trigger a `ValidationError` with a clear message:

```python
# This will fail:
load_company_profile({"name": "TestCo"})
# → ValueError: Invalid company profile data: 8 validation errors
```

## Adding More Knowledge

To add additional knowledge sources, extend `get_all_knowledge_sources()`:

```python
from crewai.knowledge.source.pdf_knowledge_source import PDFKnowledgeSource
from crewai.knowledge.source.string_knowledge_source import StringKnowledgeSource

def get_all_knowledge_sources() -> list:
    sources = []
    
    # Company profile (existing)
    try:
        sources.append(get_company_knowledge_source())
    except FileNotFoundError:
        log.warning("Company profile not found...")

    # Example: Add regulatory guidelines as text
    try:
        regulations = (Path(__file__).resolve().parents[2] / "knowledge" / "regulations.txt").read_text()
        sources.append(StringKnowledgeSource(content=regulations))
    except Exception:
        log.warning("Regulations not found...")
    
    return sources
```

**Data-first approach:**

- Load data (JSON, text, PDF, etc.)
- Wrap in appropriate `*KnowledgeSource` (String, PDF, CSV, etc.)
- Return list to crews

This keeps the knowledge system decoupled from file paths and makes it easy to switch sources or add multiple types simultaneously.
