# Tools

Runtime CrewAI tools live in `tools/crawler_tools.py`. All extend `BaseTool` and use Pydantic input schemas.

## TendersOverviewExtractorTool

Navigates a configured tender listing portal with Playwright and returns list-page content as Markdown for the Discovery Agent to parse into `TenderOverview` objects.

**Input:** `TendersOverviewExtractorInput`

```text
portal_name: str
tenders_count: int
```

**Used by:** Discovery Agent in `ScoutCrew`.

---

## SinglePageLoaderTool

Loads a single tender detail page with Playwright and returns cleaned Markdown for the Extraction Agent to parse into `TenderInfo` objects.

**Input:** `SinglePageLoaderInput`

```text
portal_name: str
url: str
```

**Used by:** Extraction Agent in `ScoutCrew`.

---

## ProposalWriterTool

Writes a Markdown proposal document to disk.

**Input:** `DocumentGeneratorInput`

```text
title: str
sections: dict[str, str]
output_path: str
```

**Output:** Confirmation string with the file path, or an error message.

**Behavior:** Creates parent directories automatically and writes UTF-8 Markdown.

**Used by:** Proposal Architect in `ProposalCrew`.

## Adding a New Tool

1. Define a Pydantic input schema in `tools/crawler_tools.py`.
2. Create a class extending `BaseTool` with `name`, `description`, `args_schema`, and `_run()`.
3. Assign it to the relevant agent only when it provides real runtime behavior.
4. Add focused tests for the schema and behavior.
