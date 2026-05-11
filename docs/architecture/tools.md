# Tools Architecture

## Overview

BandAI uses CrewAI tools to provide agents with operational capabilities beyond pure reasoning.

The current tool implementations are defined in:

```text
src/bandai/tools/crawler_tools.py
```

Despite the filename, this module currently contains several tool categories:

- tender crawling
- contract detail lookup
- compliance checking
- proposal document generation

Some tools are currently mock implementations and are intended to be replaced with real integrations over time.

## Input Schemas

The tools use Pydantic input schemas to define and validate expected arguments.

| Schema | Used by | Purpose |
|---|---|---|
| `CrawlerInput` | `TenderCrawlerTool` | Defines portal crawling inputs |
| `ContractLookupInput` | `ContractDetailTool` | Defines contract lookup inputs |
| `ComplianceInput` | `ComplianceCheckerTool` | Defines compliance analysis inputs |
| `DocumentGeneratorInput` | `ProposalWriterTool` | Defines proposal document generation inputs |

## `CrawlerInput`

Fields:

- `portal_name`: human-readable name of the procurement portal.
- `base_url`: entry URL of the portal to crawl.
- `keywords`: list of keywords to search for.
- `max_results`: maximum number of contracts to return.

The `keywords` field includes a validator that accepts either a list or a JSON/string input. If a string cannot be parsed as JSON, it is treated as a single keyword.

## `ContractLookupInput`

Fields:

- `contract_id`: unique identifier of the contract.
- `portal_url`: portal URL where the contract was found.

This schema is used when an agent needs to enrich or verify an individual tender notice.

## `ComplianceInput`

Fields:

- `tender_raw_text`: raw tender text to analyze.
- `company_profile_json`: JSON string containing company profile information.

This schema is intended for tools that compare tender requirements against company capabilities.

## `DocumentGeneratorInput`

Fields:

- `title`: title of the generated document.
- `sections`: mapping from section titles to Markdown content.
- `output_path`: output filename for the generated document.

## Tool Summary

| Tool | Current status | Main responsibility |
|---|---|---|
| `TenderCrawlerTool` | Mock | Return matching tender notices as JSON |
| `ContractDetailTool` | Mock | Return detailed metadata for a contract |
| `ComplianceCheckerTool` | Mock | Return structured compliance gap analysis |
| `ProposalWriterTool` | Functional basic implementation | Write a Markdown proposal document to disk |

## `TenderCrawlerTool`

### Purpose

`TenderCrawlerTool` is intended to crawl a procurement portal and return matching tender notices.

### Inputs

- `portal_name`
- `base_url`
- `keywords`
- `max_results`

### Output

A JSON array of tender-like objects.

The current mock output includes fields such as:

- `portal`
- `url`
- `title`
- `contract_id`
- `contracting_authority`
- `deadline`
- `value_euros`
- `raw_text`

### Current limitations

- It does not perform real HTTP crawling.
- It does not parse real procurement pages.
- It returns random mock contract IDs and values.
- It currently uses `value_euros`, while the main contract model uses `value_eur`.
- It does not currently return `cpv_codes`, although downstream tasks may expect them.

### Future improvements

- Implement real crawling with `httpx` and `BeautifulSoup`.
- Add portal-specific adapters.
- Normalize output fields to match `RawContract`.
- Add CPV extraction.
- Add deadline and value parsing.
- Add retry and timeout handling.
- Add tests using static HTML fixtures.

## `ContractDetailTool`

### Purpose

`ContractDetailTool` is intended to fetch full metadata for a single tender notice.

### Inputs

- `contract_id`
- `portal_url`

### Output

A JSON object containing metadata and completeness indicators.

The current mock output includes:

- `contract_id`
- `source_url`
- `completeness_score`
- `has_technical_spec`
- `has_admin_clauses`
- `has_award_criteria`

### Current limitations

- It does not call a real open data API yet.
- Metadata is randomly generated.
- It does not fetch annexes or administrative documents.
- It does not verify whether the contract ID exists.

### Future improvements

- Integrate with public procurement open data APIs.
- Fetch contract documents and annexes.
- Add document availability checks.
- Add source traceability.
- Return typed structured metadata.

## `ComplianceCheckerTool`

### Purpose

`ComplianceCheckerTool` is intended to compare tender requirements against the company profile.

### Inputs

- `tender_raw_text`
- `company_profile_json`

### Output

A JSON object with requirement analysis.

The current mock output includes:

- `met`
- `missing`
- `uncertain`

### Current limitations

- It does not perform real requirement extraction.
- It does not parse the company profile JSON.
- It returns static mock findings.
- It does not distinguish legal, technical, financial, and certification requirements.

### Future improvements

- Add semantic extraction of tender requirements.
- Parse and validate company profile data.
- Classify requirements by category.
- Add confidence scores.
- Return citations to tender text.
- Support structured compliance checklists.

## `ProposalWriterTool`

### Purpose

`ProposalWriterTool` writes a Markdown proposal document from structured proposal sections.

### Inputs

- `title`
- `sections`
- `output_path`

### Output

A confirmation message containing the output path.

### Current behavior

The tool:

1. Creates a Markdown heading from the proposal title.
2. Adds each section as a Markdown `##` heading.
3. Writes the assembled content to the specified output path using UTF-8 encoding.
4. Returns either a success message or an error message.

### Current limitations

- It writes Markdown only.
- It does not create parent directories automatically.
- It does not sanitize output paths.
- It does not support DOCX or PDF export.
- It returns plain text instead of a structured result object.

### Future improvements

- Add output path validation.
- Create parent directories automatically.
- Return structured JSON status.
- Add DOCX/PDF generation.
- Add proposal templates.
- Add tests for generated Markdown content.

## Tool Usage by Crews

| Crew | Tools used |
|---|---|
| `ScoutCrew` | `TenderCrawlerTool`, `ContractDetailTool` |
| `ComplianceCrew` | `ComplianceCheckerTool` |
| `ProposalCrew` | `ProposalWriterTool` |

## Cross-Crew Tool Flow

```text
ScoutCrew
    ↓
TenderCrawlerTool
    ↓
ContractDetailTool
    ↓
Resolved opportunities
    ↓
ComplianceCrew
    ↓
ComplianceCheckerTool
    ↓
ComplianceVerdict
    ↓
ProposalCrew
    ↓
ProposalWriterTool
    ↓
Markdown proposal output
```

## Current Limitations

The tools layer is still early-stage.

Main limitations:

- Most tools are still mock implementations.
- Outputs are not always aligned with Pydantic models.
- Random mock data makes deterministic tests harder.
- Portal-specific behavior is not implemented yet.
- Document parsing, OCR, and PDF support are not implemented yet.

## Future Improvements

Potential improvements include:

- Replace mock crawler behavior with real portal adapters.
- Add PDF parsing.
- Add OCR extraction.
- Add procurement portal adapters.
- Add semantic requirement extraction.
- Add deterministic test fixtures.
- Add typed tool outputs.
- Align tool output keys with `RawContract` and `ResolvedContract`.