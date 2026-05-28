# Main Pipeline

BandAI runs a three-phase procurement pipeline orchestrated by a CrewAI Flow. The flow is a deterministic state machine - every transition is explicit, every branch has a fallback.

## Execution Modes

| Mode | Phases Run | Human Input | Use Case |
| ----------- | ------------------- | ------------- | --------------------------------------- |
| `full` | Scout -> Compliance -> Proposal | Preferences + conditional review | Complete end-to-end run |
| `scout` | Scout only | Preferences | Quick opportunity discovery |
| `propose` | Compliance -> Proposal | Conditional review | Single known contract, skip scouting |
| `report` | Report generation only | None | Stakeholder review of existing outputs |

Mode is set via `--mode` flag or by calling `BandAIState(mode=...)`.

## Entry Point

`main.py` is a thin wrapper. It validates configuration (provider, API key, knowledge file, portals), parses CLI args, prepares the initial `BandAIState`, then delegates to `BandAIFlow.kickoff(inputs=state.model_dump())`.

For `--mode propose`, the wrapper loads the selected contract from `output/01_scout_results.json` before kickoff so the flow can start directly from compliance without running scouting.

For `--mode report`, the wrapper skips CrewAI entirely and generates `output/report.html` from the JSON artifacts already present in `output/`.

```text
main.py  ->  _startup_validation()  ->  BandAIState(...)  ->  BandAIFlow().kickoff(inputs=state.model_dump())
```

No business logic lives in main. All orchestration is in `flow.py`.

## Flow State Machine

The flow uses a Pydantic state model (`BandAIState`) with CrewAI decorators. State is managed in-memory by CrewAI Flow:

- `@start` - entry point, returns nothing
- `@listen("label")` - reacts to a named event emitted by a `@router`, returns nothing
- `@router(method_ref)` - reads state, returns a string label that triggers a `@listen`

Every non-terminal `@listen` is followed by a `@router` so the flow always knows the next step.

### Phase 1: Scouting

```text
begin() ---> route_from_begin() ---> "scout"     /    "skip_scout"
                                        │                  │
                                 @listen("scout")  @listen("skip_scout")
                                  run_scouting()    skip_to_compliance()
                                        │                  │
                                route_after_scout()   route_skip()
                                        ├─ scout -> "end_scout" -> "start_compliance"
                                        └─ full  -> "start_compliance"
```

`begin()` collects user preferences via stdin in `full` mode. In `scout` mode it skips the prompt. The `run_scouting()` method builds and kicks off `ScoutCrew`, parses the JSON output, and stores contracts in state.

### Phase 2: Compliance

```text
@listen("start_compliance")
init_compliance() ---> route_after_init() ---> "process_next_contract"

@listen("process_next_contract")
process_next_contract() --> route_process_contract()
  ├─ all done           --> "compliance_done"
  └─ more contracts     --> "run_compliance_crew"

@listen("run_compliance_crew")
run_compliance_crew()   --> route_verdict()
  ├─ None / GO / NO-GO  --> "process_next_contract" (loop)
  └─ CONDITIONAL-GO     --> "handle_conditional_go"

@listen("handle_conditional_go")
handle_conditional_go() --> route_after_conditional()
  ├─ still CONDITIONAL  --> "handle_conditional_go" (loop)
  └─ GO / NO-GO / None  --> "process_next_contract"
```

The compliance loop processes one contract at a time. The CONDITIONAL-GO path triggers a human review cycle with a configurable maximum iteration count (`MAX_REVIEW_ITERATIONS`, default 5). An implicit NO-GO keyword detector catches abandonment language ("we don't have", "impossible", "rinunciamo") without burning an LLM call.

### Phase 3: Proposals

```text
@listen("compliance_done")
after_compliance() --> route_after_compliance() --> "start_proposals"

@listen("start_proposals")
run_proposals()    --> STOP
```

`run_proposals()` iterates over all approved contracts, builds and kicks off `ProposalCrew` for each, and writes the final proposal JSON to `output/`.

## Human Interaction Points

1. **Preference input** - `begin()` in `full` mode. Free text describing sector, region, budget, keywords.
2. **Conditional-GO review** - `handle_conditional_go()`. Displays the verdict, open conditions, and key risks. User provides additional context or signals abandonment.
3. **Preference filter review** - `preference_filter_task` has `human_input=True`, which pauses crew execution for review.

## Outputs

All artifacts land in `output/`:

| File Pattern                    | Content                              |
|---------------------------------|--------------------------------------|
| `01_scout_results.json`         | All discovered contracts             |
| `02_compliance_{nn}_{id}.json`  | Individual compliance verdicts       |
| `02_no_go_review_required.json` | Consolidated NO-GO contracts         |
| `03_proposal_{nn}_{id}.json`    | Final proposal per contract          |
| `report.html`                   | Stakeholder-ready HTML summary       |

## Logging

All logging uses Python's `logging` module with the `bandai` namespace. Format:

```text
2026-01-15 10:30:00 | INFO     | bandai.flow | Scout found 12 unique contracts.
```

Set `LOG_LEVEL` env var or adjust `logging.basicConfig()` in `main.py` for verbosity control.
