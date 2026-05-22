# Testing BandAI

BandAI uses a layered testing strategy so the team can validate the procurement pipeline without making every test depend on live LLM calls. All tests are designed to run in a lightweight environment where CrewAI is not installed: heavy dependencies are stubbed via `sys.modules` at the top of each test file (or in `conftest.py`).

## Test layers

| Layer | Marker | Purpose | Calls real LLMs? |
| --- | --- | --- | --- |
| Unit tests | `unit` | Fast deterministic tests for config, models, parsers, guardrails, embedder, memory, utilities. | No |
| Mocked flow/integration tests | `mock_llm` | Validate Scout -> Compliance -> Proposal orchestration with fake crew outputs. | No |
| LLM smoke tests | `llm` | Small end-to-end checks against real model providers before demos/releases. | Yes |

## Setup

Install development dependencies from the repository root:

```bash
uv sync --extra dev
```

## Commands

Run the full non-LLM test suite. This is the recommended pre-demo/pre-PR command because it does not call real model providers:

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

Run with verbose output and per-test timing:

```bash
uv run pytest -v -m "not llm" --durations=10
```

## Test files

| File | Classes | Tests | What it covers |
| --- | --- | --- | --- |
| `test_config.py` | 12 | 48 | Knowledge models, provider config, env overrides, config validation, portal loading/weights, pipeline models (ComplianceVerdict, RawContract), knowledge sources, flow state persistence, IO utilities, portal reload, LLM factory (lru_cache, env override) |
| `test_embedder.py` | 10 | 19 | VL model keyword detection, `_build_input` for VL/non-VL, static `name()`, empty input, successful embedding call, no-data error, `get_embedder` factory (none/openrouter/ollama) |
| `test_flow_mocked.py` | - | 5 | Scout-only mode, GO -> compliance -> proposal, NO-GO logging, CONDITIONAL-GO kept for proposal, CONDITIONAL-GO with implicit NO-GO |
| `test_guardrails.py` | 2 | 17 | `validate_json_array` (valid, fences, plain text, embedded, invalid), `validate_compliance_verdict` (GO, NO-GO, CONDITIONAL, invalid decision, score bounds, unparseable output) |
| `test_memory.py` | 2 | 8 | `DISABLE_MEMORY` truthy values, memory creation with LLM + embedder args |
| `test_utils.py` | 4 | 12 | `extract_json_array`, `is_implicit_no_go` (Italian/English/empty), `contract_to_summary`, `load_yaml_config` (load/missing/cache/bypass) |
| `fixtures/sample_data.py` | - | - | Shared factories: `sample_contract`, `go_verdict`, `no_go_verdict`, `conditional_go_verdict`, `sample_proposal` |

Total: **109 tests** across 6 test modules and 30 test classes.

## Mocked flow tests

The mocked flow tests live in `tests/test_flow_mocked.py`. They monkeypatch the Scout, Compliance, and Proposal crews with deterministic fake outputs via a `FakeCrew` / `FakeOutput` / `FakeTask` harness. This lets us verify the orchestration rules without crawling real portals, calling LLM providers, or consuming API credits.

The tests install minimal CrewAI stubs at module level (`Flow` with `__class_getitem__` that initializes `self.state`, plus `listen`, `router`, `start` identity decorators). The `Flow.__class_getitem__` mock creates a subclass whose `__init__` instantiates the state model, so `flow.state` is available without the real CrewAI runtime.

Current scenarios covered:

- Scout-only mode stores discovered contracts and stops before compliance.
- `GO` verdicts are approved and passed to proposal generation.
- `NO-GO` verdicts are logged and do not trigger proposal generation.
- `CONDITIONAL-GO` with no extra human note is kept for proposal generation.
- `CONDITIONAL-GO` with an implicit negative human note is converted to `NO-GO` and skips proposal generation.

## CrewAI mocking strategy

CrewAI is **not** installed in the test environment. Each test file that needs crewai symbols installs minimal stubs via `sys.modules` before importing bandai modules. The mocking hierarchy is:

1. `conftest.py` - sets `sys.path` to include `src/`
2. `test_config.py` - stubs `crewai.rag.embeddings.providers.custom.*` and `crewai.knowledge.source.string_knowledge_source`
3. `test_embedder.py` - stubs `crewai.rag.embeddings.providers.custom.*`
4. `test_memory.py` - stubs `crewai.rag.embeddings.providers.custom.*` and `crewai.memory.unified_memory`
5. `test_guardrails.py` - stubs `crewai.TaskOutput`
6. `test_flow_mocked.py` - stubs `crewai.flow.flow`, `crewai.knowledge.source.*`, and the three crew modules

Stubs use `sys.modules.setdefault()` where possible so they do not clobber richer mocks installed by other test modules in the same session.

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
109 passed
```

If these tests pass, the deterministic testing layer is healthy. This does not prove real LLM output quality; it proves the flow routing and orchestration logic behave correctly for the covered scenarios.
