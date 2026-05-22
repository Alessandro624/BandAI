# Tools

Four custom CrewAI tools, all in `tools/crawler_tools.py`. All extend `BaseTool` and use Pydantic input schemas.

## TenderCrawlerTool

Crawls a procurement portal for matching tenders.

**Input:** `CrawlerInput`

```text
portal_name: str   - Human-readable portal name
base_url: str      - Portal entry URL
keywords: list[str] - Search terms (accepts string or JSON array)
max_results: int   - Limit, default 10
```

**Output:** JSON array of tender notices with keys: `portal`, `url`, `title`, `contract_id`, `contracting_authority`, `deadline`, `value_euros`, `raw_text`.

**Status:** Stub. Returns mock data with randomized values. The real implementation needs `httpx` + `BeautifulSoup` for portal-specific scraping. The mock is sufficient for end-to-end pipeline testing.

**Used by:** Crawler Agent (Scout crew, one instance per portal).

---

## ContractDetailTool

Fetches full metadata for a single tender by Contract ID.

**Input:** `ContractLookupInput`

```text
contract_id: str  - Unique tender identifier
portal_url: str   - Source portal URL
```

**Output:** JSON with `contract_id`, `source_url`, `completeness_score`, and boolean flags for `has_technical_spec`, `has_admin_clauses`, `has_award_criteria`.

**Status:** Stub. The real implementation should hit the ANAC open data API at `https://dati.anticorruzione.it/opendata/`.

**Used by:** Crawler Agent and Resolution Agent (Scout crew).

---

## ComplianceCheckerTool

Cross-references company profile against tender requirements.

**Input:** `ComplianceInput`

```text
tender_raw_text: str       - Full tender text
company_profile_json: str  - Company profile as JSON string
```

**Output:** JSON with three lists: `met`, `missing`, `uncertain`.

**Status:** Stub. Returns hardcoded example analysis. The real implementation needs NLP extraction to map tender requirements to company certifications, turnover thresholds, and past contract history.

**Used by:** Advocate and Auditor agents (Compliance crew).

---

## ProposalWriterTool

Writes a Markdown proposal document to disk.

**Input:** `DocumentGeneratorInput`

```text
title: str              - Document title
sections: dict[str, str] - Section name -> Markdown content
output_path: str        - File path, default "output/proposal_output.md"
```

**Output:** Confirmation string with the file path, or an error message.

**Behavior:** Creates parent directories automatically (`mkdir(parents=True)`). Overwrites existing files. Writes UTF-8 encoded Markdown.

**Status:** Functional. This is the only tool with a real implementation.

**Used by:** Proposal Architect (Proposal crew).

---

## Input Schema Details

All schemas use Pydantic `Field` descriptions for LLM-readable documentation:

- `CrawlerInput` - `keywords` field has a `@field_validator` that accepts either a JSON string or a raw string, converting single values to `["value"]`.
- `ContractLookupInput` - Straightforward key-value lookup.
- `DocumentGeneratorInput` - Default output path is `output/proposal_output.md`.
- `ComplianceInput` - Expects the full company profile as a serialized JSON string, which the agent constructs from knowledge.

## Adding a New Tool

1. Define a Pydantic input schema in `tools/crawler_tools.py`.
2. Create a class extending `BaseTool` with `name`, `description`, `args_schema`, and `_run()`.
3. Import and assign to the relevant agent via the `tools=[]` parameter.
4. Add tests in `tests/test_config.py` or a new `tests/test_tools.py`.
