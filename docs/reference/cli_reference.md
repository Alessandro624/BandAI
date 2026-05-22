# CLI Reference

All commands assume you're in the project root with the virtual environment activated.

## Pipeline Commands

### `bandai` (or `crewai run`)

Runs the full procurement pipeline. Equivalent to `bandai --mode full`.

```bash
bandai
```

Prompts for preferences via stdin, then runs Scout → Compliance → Proposal.

### `bandai --mode scout`

Scout-only mode. Discovers tenders, prints results, exits.

```bash
bandai --mode scout
```

### `bandai --mode propose --contract <ID>`

Propose mode for a known contract. Skips scouting, creates a stub contract entry, and runs Compliance → Proposal.

```bash
bandai --mode propose --contract GD-2026-00123
```

`--mode propose` requires `--contract`. Without it, exits with an error.

### `bandai --dry-run`

Validates configuration without making LLM calls. Checks:

- Provider name is recognized
- API key is set (not a placeholder)
- `knowledge/company_profile.json` exists
- `config/portals.yaml` exists

```bash
bandai --dry-run
```

Exits 0 on success, 1 on any validation failure.

## Project Scripts

The following commands are declared in `pyproject.toml` and point to the same runtime entry points used by the CLI:

### `run_crew`

Alias of `bandai`.

### `run_with_trigger`

Calls the same runtime as `bandai`. Use this when the pipeline is launched by an external trigger such as a webhook.

### `pytest_unit`

Runs the project test suite with verbosity enabled.

```bash
pytest_unit
```

## Training and Evaluation

### `crewai test`

Runs CrewAI's built-in evaluation. Default: 2 iterations using gpt-4o-mini.

```bash
crewai test
crewai test -n 5 -m gpt-4o    # 5 iterations with GPT-4o
```

### `crewai train`

Trains the crew and writes results to a JSON file.

```bash
crewai train -n 5 -f training.json
```

### `crewai replay`

Replays a previous task execution by task ID.

```bash
crewai replay -t <task_id>
```

## Memory Management

### `crewai reset-memories`

Clears stored memory data. Supports selective clearing.

```bash
crewai reset-memories -a    # All memory types
crewai reset-memories -s    # Short-term only
crewai reset-memories -l    # Long-term only
crewai reset-memories -e    # Entity memory only
crewai reset-memories -kn   # Knowledge memory only
crewai reset-memories -akn  # Agent knowledge only
```

Useful when switching companies or after significant knowledge profile changes.

## Debugging

### `crewai log-tasks-outputs`

Prints the latest task outputs from the most recent run.

```bash
crewai log-tasks-outputs
```

### Verbose logging

Set `LOG_LEVEL` or edit `main.py`:

```python
logging.basicConfig(level=logging.DEBUG, ...)
```

Agent-level verbose output is controlled per-agent via `verbose=True` (enabled by default in all agents).

## Deployment

### `crewai deploy`

Deploys to CrewAI AMP.

```bash
crewai login              # Authenticate
crewai deploy create      # Create deployment
crewai deploy status      # Check status
crewai deploy logs        # View logs
crewai deploy push        # Push code updates
crewai deploy list        # List deployments
crewai deploy remove <id> # Delete deployment
```

## Flow Visualization

### `crewai flow plot`

Generates an HTML file with the flow state machine diagram.

```bash
crewai flow plot
```

Opens in the default browser if a display is available.

## pytest

```bash
pytest tests/ -v                    # Run all tests
pytest tests/test_config.py -v      # Run specific file
pytest tests/ --tb=short            # Shorter tracebacks
pytest tests/ -k "TestKnowledge"    # Run by class name
```

109 tests across 14 test classes covering config, providers, portals, models, knowledge sources, flow structure, utilities, guardrails, and embedder configuration.
