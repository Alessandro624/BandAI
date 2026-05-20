# Testing BandAI

BandAI uses a layered testing strategy so the team can validate the procurement pipeline without making every test depend on live LLM calls.

## Test layers

| Layer | Marker | Purpose | Calls real LLMs? |
| --- | --- | --- | --- |
| Unit tests | `unit` | Fast deterministic tests for config, models, parsers, guardrails, and utility functions. | No |
| Mocked flow/integration tests | `mock_llm` | Validate Scout → Compliance → Proposal orchestration with fake crew outputs. | No |
| LLM smoke tests | `llm` | Small end-to-end checks against real model providers before demos/releases. | Yes |

## Setup

Install development dependencies from the repository root:

```bash
uv sync --extra dev
```

## Commands

Run the non-LLM test suite. This is the recommended pre-demo/pre-PR command because it does not call real model providers:

```bash
uv run pytest -q -m "not llm"
```

Run only the mocked flow tests:

```bash
uv run pytest -q -m mock_llm
```

Run real LLM smoke tests only when API keys are configured and the extra cost/time is acceptable:

```bash
uv run pytest -q -m llm
```

## Mocked flow tests

The mocked flow tests live in `tests/test_flow_mocked.py`. They monkeypatch the Scout, Compliance, and Proposal crews with deterministic fake outputs. This lets us verify the orchestration rules without crawling real portals, calling LLM providers, or consuming API credits.

Current scenarios covered:

- Scout-only mode stores discovered contracts and stops before compliance.
- `GO` verdicts are approved and passed to proposal generation.
- `NO-GO` verdicts are logged and do not trigger proposal generation.
- `CONDITIONAL-GO` with no extra human note is kept for proposal generation.
- `CONDITIONAL-GO` with an implicit negative human note is converted to `NO-GO` and skips proposal generation.

## Fixtures

Shared deterministic fixtures live in `tests/fixtures/sample_data.py`. Prefer adding reusable contract, verdict, and proposal factories there instead of duplicating dictionaries inside individual tests.


## Demo checklist

Before a project demo or handoff, run:

```bash
uv sync --extra dev
uv run pytest -q -m "not llm"
```

Expected result for the current mocked testing layer:

```text
5 passed
```

If these tests pass, the deterministic testing layer is healthy. This does not prove real LLM output quality; it proves the flow routing and orchestration logic behave correctly for the covered scenarios.
