# Customization

## Adding a Procurement Portal

Add an entry to `config/portals.yaml`:

```yaml
portals:
  - name: "Lombardia Sintel"
    base_url: "https://www.sintel.regione.lombardia.it"
    reliability: 0.70
    country_filter: "IT"
```

The Scout crew automatically creates a Crawler Agent for each portal. No code changes needed.

**Reliability guidelines:**

- 0.90-1.00 - Official national/EU sources (ANAC, TED)
- 0.75-0.89 - Regional procurement platforms (MePA, Sardegna CAT)
- 0.50-0.74 - Municipal or niche portals

The Resolution Agent uses reliability as a weighting factor in consensus polling. A portal with 0.70 contributes less to the canonical record than one with 1.00.

## Adding a Department

Edit `knowledge/company_profile.json` and add a new key under `departments`:

```json
"Data Science": {
  "capabilities": [
    "ML model development and deployment",
    "Statistical analysis and forecasting",
    "Data pipeline engineering (ETL)"
  ],
  "certifications": ["AWS Certified Machine Learning"],
  "case_studies": [
    "Predictive maintenance for utility company (2023) - EUR 120k, 35% downtime reduction"
  ],
  "kpis": {
    "model_accuracy_percent": 92,
    "projects_delivered": 8
  }
}
```

The Proposal crew will automatically create a Department Representative agent for this division. The agent will have access to all capabilities, certifications, case studies, and KPIs when bidding for proposal sections.

## Adding Certifications or Past Contracts

In the same `company_profile.json`:

```json
{
  "certifications": [
    "...existing certs...",
    "ISO 27701:2019"
  ],
  "past_public_contracts": [
    "...existing contracts...",
    {
      "title": "Cloud Migration for Regione Toscana",
      "value_eur": 320000.0,
      "cpv_codes": ["72212517", "48900000"],
      "year": 2024,
      "authority": "Regione Toscana",
      "topics": ["cloud migration", "public sector"]
    }
  ]
}
```

The Compliance crew reads these to match against tender requirements. More certifications and past contracts in relevant CPV categories increase the Advocate's confidence score.

## Adding a Custom LLM Provider

In `config/_constants.py`, extend the `PROVIDERS` dict:

```python
PROVIDERS["groq"] = ProviderProfile(
    name="groq",
    description="Groq - fast inference",
    base_url="https://api.groq.com/openai/v1",
    main=LLMProfile(model="llama-3.3-70b-versatile", temperature=0.3, max_tokens=4096),
    fast=LLMProfile(model="llama-3.1-8b-instant", temperature=0.3, max_tokens=2048),
    env_key="GROQ_API_KEY",
)
```

Set `LLM_PROVIDER=groq` and `GROQ_API_KEY=your-key` in `.env`.

## Adding Knowledge Sources

The knowledge system accepts any file format CrewAI supports: JSON, PDF, CSV, text. To add a new source:

1. Place the file in `knowledge/`.
2. Open `knowledge_sources.py` and extend `get_all_knowledge_sources()`:

```python
from crewai.knowledge.source.pdf_knowledge_source import PDFKnowledgeSource

def get_all_knowledge_sources() -> list:
    sources = []
    try:
        sources.append(get_company_knowledge_source())
    except FileNotFoundError:
        log.warning("...")

    # Add regulatory reference
    try:
        reg_path = "dlgs_36_2023_summary.pdf"
        if reg_path.exists():
            sources.append(PDFKnowledgeSource(file_paths=[str(reg_path)]))
    except Exception:
        log.warning("Failed to load regulatory PDF")

    return sources
```

All agents in all crews gain access to the new source through semantic embedding. No prompt changes needed.

## Adding a New Tool

1. Define the input schema and tool class in `tools/crawler_tools.py`:

```python
class RAGSearchInput(BaseModel):
    query: str = Field(..., description="Search query for the knowledge base")

class RAGSearchTool(BaseTool):
    name: str = "RAGSearchTool"
    description: str = "Searches the company knowledge base for relevant information."
    args_schema: Type[BaseModel] = RAGSearchInput

    def _run(self, query: str) -> str:
        # Implementation
        return json.dumps(results)
```

1. Assign to agents in their respective crew files:

```python
agent = Agent(
    ...,
    tools=[RAGSearchTool()],
)
```

## Adjusting Scoring Weights

The auctioneer's composite formula is fixed in `config/tasks_proposal.yaml`:

```text
composite = (relevance_score × 0.50) + (evidence_quality_score × 0.35) + (section_coverage_bonus × 0.15)
```

To change weights, edit the `auction_task` description in the YAML. The weights are embedded in the task prompt - the auctioneer follows them as instructions.

## Adjusting Review Limits

Set `MAX_REVIEW_ITERATIONS` in `.env`:

```bash
MAX_REVIEW_ITERATIONS=3
```

Default is 5. Lower values force faster decisions but may miss legitimate CONDITIONAL-GO resolutions. The flow forces NO-GO when the limit is reached.
