# Flow State Machine

A detailed reference for every state transition in `BandAIFlow`. The flow is defined in `flow.py` using CrewAI's `@start`, `@listen`, and `@router` decorators.

## Wiring Convention

Every method in the flow follows this rule:

- **`@start` / `@listen`** - do work, mutate `self.state`, return **nothing**.
- **`@router(method_ref)`** - read state, return a **string label** that triggers a `@listen("label")`.
- **`@listen("label")`** - triggered exclusively by a `@router` returning that label.

Every non-terminal `@listen` is followed by a `@router` so the flow knows the next step.

## State Model

`BandAIState` is a Pydantic `BaseModel` with fields grouped by pipeline phase:

```python
class BandAIState(BaseModel):
    # Inputs
    user_preferences: str = ""
    mode: str = "full"

    # Phase 1: Scouting
    contracts: list[dict]
    total_contracts: int

    # Phase 2: Compliance (per-contract tracking)
    current_contract_index: int
    current_contract: dict | None
    current_summary: str
    current_verdict: dict | None
    review_iteration: int
    approved_contracts: list[tuple[dict, dict]]
    no_go_log: list[dict]

    # Phase 3: Proposals
    proposals: list[dict]
    total_approved: int
    total_proposals: int
```

State is passed to `kickoff(inputs=state.model_dump())` and mutated internally by flow methods. `@persist` decorator saves state to SQLite for crash recovery.

## Complete Transition Map

### Entry

| Method               | Decorator            | Returns  | Triggers                     |
|----------------------|----------------------|----------|------------------------------|
| `begin()`            | `@start`             | -        | `route_from_begin()`         |
| `route_from_begin()` | `@router(begin)`     | `"scout"` / `"skip_scout"` | `run_scouting()` or `skip_to_compliance()` |

Routing logic:

- `mode in ("full", "scout")` → `"scout"`
- everything else → `"skip_scout"`

### Phase 1: Scouting

| Method                  | Decorator               | Returns | Triggers                       |
|-------------------------|-------------------------|---------|--------------------------------|
| `run_scouting()`        | `@listen("scout")`      | -       | `route_after_scout()`          |
| `route_after_scout()`   | `@router(run_scouting)` | `"end_scout"` / `"start_compliance"` | next phase |
| `end_scout_only()`      | `@listen("end_scout")`  | -       | *(terminal)*                    |
| `skip_to_compliance()`  | `@listen("skip_scout")` | -       | `route_skip()`                  |
| `route_skip()`          | `@router(skip_to_compliance)` | `"start_compliance"` | `init_compliance()` |

### Phase 2: Compliance - Init

| Method                  | Decorator                    | Returns | Triggers                   |
|-------------------------|------------------------------|---------|----------------------------|
| `init_compliance()`     | `@listen("start_compliance")`| -       | `route_after_init()`       |
| `route_after_init()`    | `@router(init_compliance)`   | `"process_next_contract"` | `process_next_contract()` |

### Phase 2: Compliance - Contract Loop

| Method                      | Decorator                          | Returns | Triggers               |
|-----------------------------|-----------------------------------|---------|------------------------|
| `process_next_contract()`   | `@listen("process_next_contract")`| -       | `route_process_contract()` |
| `route_process_contract()`  | `@router(process_next_contract)`  | `"compliance_done"` / `"run_compliance_crew"` | next |
| `run_compliance_crew()`     | `@listen("run_compliance_crew")`  | -       | `route_verdict()`      |
| `route_verdict()`           | `@router(run_compliance_crew)`    | `"process_next_contract"` / `"handle_conditional_go"` | next |

### Phase 2: Compliance - Conditional-GO Review

| Method                      | Decorator                            | Returns | Triggers                    |
|-----------------------------|--------------------------------------|---------|-----------------------------|
| `handle_conditional_go()`   | `@listen("handle_conditional_go")`   | -       | `route_after_conditional()` |
| `route_after_conditional()` | `@router(handle_conditional_go)`     | `"handle_conditional_go"` / `"process_next_contract"` | loop or continue |

`route_after_conditional()` reads `self.state.current_verdict`:

- If `bid_decision == "CONDITIONAL-GO"` → loop back to `handle_conditional_go`
- Anything else (GO, NO-GO, None) → continue to `process_next_contract`

### Phase 2 → Phase 3

| Method                    | Decorator                     | Returns | Triggers                |
|---------------------------|-------------------------------|---------|-------------------------|
| `after_compliance()`      | `@listen("compliance_done")`  | -       | `route_after_compliance()` |
| `route_after_compliance()`| `@router(after_compliance)`   | `"start_proposals"` | `run_proposals()` |

### Phase 3: Proposals

| Method            | Decorator                     | Returns | Triggers     |
|-------------------|-------------------------------|---------|--------------|
| `run_proposals()` | `@listen("start_proposals")`  | -       | *(terminal)* |

## Dead End States

The flow has two terminal states:

1. `end_scout_only()` - Scout mode complete. No further processing.
2. `run_proposals()` - Full pipeline complete. Prints summary.

There is no explicit "error" terminal. All exceptions are caught within methods, logged, and the flow continues with empty/zeroed state.

## Persistence

`@persist` decorator saves flow state to SQLite. On crash and restart, the flow resumes from the last completed step. Useful for long-running compliance phases where individual crew calls can take minutes.

## Visualization

```bash
crewai flow plot
```

Generates an HTML diagram of the decorated methods and their transitions.
