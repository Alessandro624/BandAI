"""Mocked integration tests for the BandAI Scout -> Compliance -> Proposal flow.

These tests validate orchestration behavior without calling real CrewAI crews,
LLM providers, external portals, or writing production output files.
"""

from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest

pytestmark = pytest.mark.mock_llm


def _install_import_stubs_when_crewai_is_unavailable() -> None:
    """Allow this mocked flow test module to run in lightweight environments.

    The real project depends on CrewAI, but these tests monkeypatch every crew
    call.  When CrewAI is not installed locally, minimal stubs are enough to
    import ``bandai.flow`` and exercise its pure orchestration logic.
    """
    try:
        importlib.import_module("crewai.flow.flow")
        return
    except Exception:
        pass

    crewai_module = sys.modules.setdefault("crewai", types.ModuleType("crewai"))
    flow_package = sys.modules.setdefault("crewai.flow", types.ModuleType("crewai.flow"))
    flow_module = types.ModuleType("crewai.flow.flow")

    class Flow:
        @classmethod
        def __class_getitem__(cls, _item: object) -> type["Flow"]:
            return cls

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    def _identity_decorator(*_decorator_args: object, **_decorator_kwargs: object):
        def _decorate(func):
            return func

        return _decorate

    flow_module.Flow = Flow
    flow_module.listen = _identity_decorator
    flow_module.router = _identity_decorator
    flow_module.start = _identity_decorator
    sys.modules["crewai.flow.flow"] = flow_module
    flow_package.flow = flow_module
    crewai_module.flow = flow_package

    knowledge_package = types.ModuleType("crewai.knowledge")
    knowledge_source_package = types.ModuleType("crewai.knowledge.source")
    string_knowledge_module = types.ModuleType("crewai.knowledge.source.string_knowledge_source")

    class StringKnowledgeSource:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    string_knowledge_module.StringKnowledgeSource = StringKnowledgeSource
    sys.modules["crewai.knowledge"] = knowledge_package
    sys.modules["crewai.knowledge.source"] = knowledge_source_package
    sys.modules["crewai.knowledge.source.string_knowledge_source"] = string_knowledge_module
    knowledge_source_package.string_knowledge_source = string_knowledge_module
    knowledge_package.source = knowledge_source_package
    crewai_module.knowledge = knowledge_package

    for module_name, class_name in {
        "bandai.crews.scout_crew": "ScoutCrew",
        "bandai.crews.compliance_crew": "ComplianceCrew",
        "bandai.crews.proposal_crew": "ProposalCrew",
    }.items():
        module = types.ModuleType(module_name)
        setattr(module, class_name, type(class_name, (), {}))
        sys.modules[module_name] = module


_install_import_stubs_when_crewai_is_unavailable()

from bandai import flow as flow_module  # noqa: E402
from bandai.flow import BandAIFlow, BandAIState  # noqa: E402
from tests.fixtures.sample_data import (  # noqa: E402
    conditional_go_verdict,
    go_verdict,
    no_go_verdict,
    sample_contract,
    sample_proposal,
)


@dataclass
class CallLog:
    scout: list[str] = field(default_factory=list)
    compliance: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)
    proposal: list[str] = field(default_factory=list)
    saved_json: list[tuple[str, dict]] = field(default_factory=list)


class FakeCrew:
    def __init__(self, calls: list[str], label: str) -> None:
        self._calls = calls
        self._label = label

    def kickoff(self) -> None:
        self._calls.append(self._label)


class FakeOutput:
    def __init__(self, pydantic: Any, raw: str = "fake raw output") -> None:
        self.pydantic = pydantic
        self.raw = raw


class FakeTask:
    def __init__(self, pydantic: Any) -> None:
        self.output = FakeOutput(pydantic=pydantic)


def make_flow(human_note: str = "") -> BandAIFlow:
    """Create a BandAIFlow instance with CrewAI-managed state initialized."""
    return BandAIFlow(human_input_fn=lambda *_args: human_note)


@pytest.fixture
def call_log(monkeypatch: pytest.MonkeyPatch) -> CallLog:
    calls = CallLog()
    monkeypatch.setattr(
        flow_module,
        "save_json",
        lambda data, filename: calls.saved_json.append((filename, data)),
    )
    monkeypatch.setattr(BandAIFlow, "_print_summary", lambda self: None)
    return calls


def patch_scout(monkeypatch: pytest.MonkeyPatch, calls: CallLog, contracts: list[dict]) -> None:
    class FakeScoutCrew:
        def build(self, user_preferences: str):
            return FakeCrew(calls.scout, user_preferences), FakeTask(contracts)

    monkeypatch.setattr(flow_module, "ScoutCrew", FakeScoutCrew)


def patch_compliance(
    monkeypatch: pytest.MonkeyPatch,
    calls: CallLog,
    verdicts: list[Any],
    review_verdicts: list[Any] | None = None,
) -> None:
    class FakeComplianceCrew:
        def build(self, contract_summary: str):
            return FakeCrew(calls.compliance, contract_summary), FakeTask(verdicts.pop(0))

        def build_review(self, contract_summary: str, original_verdict, human_note: str, iteration: int = 1):
            if review_verdicts is None:
                raise AssertionError("Unexpected review crew call")
            return FakeCrew(calls.review, human_note), FakeTask(review_verdicts.pop(0))

    monkeypatch.setattr(flow_module, "ComplianceCrew", FakeComplianceCrew)


def patch_proposal(monkeypatch: pytest.MonkeyPatch, calls: CallLog) -> None:
    class FakeProposalCrew:
        def build(self, contract_summary: str):
            proposal = sample_proposal()
            return FakeCrew(calls.proposal, contract_summary), FakeTask(proposal)

    monkeypatch.setattr(flow_module, "ProposalCrew", FakeProposalCrew)


def run_compliance_for_current_contract(flow: BandAIFlow) -> str:
    flow.init_compliance()
    assert flow.route_after_init() == "process_next_contract"
    flow.process_next_contract_func()
    assert flow.route_process_contract() == "run_compliance_crew"
    flow.run_compliance_crew_func()
    return flow.route_verdict()


def finish_compliance_and_run_proposals(flow: BandAIFlow) -> None:
    flow.process_next_contract_func()
    assert flow.route_process_contract() == "compliance_done"
    flow.after_compliance()
    assert flow.route_after_compliance() == "start_proposals"
    flow.run_proposals()


def test_scout_only_mode_stores_contracts_without_starting_compliance(
    monkeypatch: pytest.MonkeyPatch,
    call_log: CallLog,
) -> None:
    contracts = [sample_contract(), sample_contract(canonical_contract_id="BANDI-2026-002")]
    patch_scout(monkeypatch, call_log, contracts)

    flow = make_flow()
    flow.state.mode = "scout"
    flow.state.user_preferences = "ICT tenders in Calabria"

    flow.run_scouting()

    assert flow.state.contracts == contracts
    assert flow.state.total_contracts == 2
    assert flow.route_after_scout() == "end_scout"
    assert call_log.scout == ["ICT tenders in Calabria"]
    assert call_log.saved_json[0][0] == "01_scout_results.json"


def test_go_contract_runs_compliance_then_generates_proposal(
    monkeypatch: pytest.MonkeyPatch,
    call_log: CallLog,
) -> None:
    patch_compliance(monkeypatch, call_log, [go_verdict()])
    patch_proposal(monkeypatch, call_log)

    flow = make_flow()
    flow.state.contracts = [sample_contract()]
    flow.state.total_contracts = 1

    assert run_compliance_for_current_contract(flow) == "process_next_contract"
    assert len(flow.state.approved_contracts) == 1
    assert flow.state.no_go_log == []

    finish_compliance_and_run_proposals(flow)

    assert call_log.compliance
    assert len(call_log.proposal) == 1
    assert flow.state.total_approved == 1
    assert flow.state.total_proposals == 1
    assert flow.state.proposals[0]["tender_ref"] == "BANDI-2026-001"


def test_no_go_contract_is_logged_and_does_not_generate_proposal(
    monkeypatch: pytest.MonkeyPatch,
    call_log: CallLog,
) -> None:
    patch_compliance(monkeypatch, call_log, [no_go_verdict()])
    patch_proposal(monkeypatch, call_log)

    flow = make_flow()
    flow.state.contracts = [sample_contract()]
    flow.state.total_contracts = 1

    assert run_compliance_for_current_contract(flow) == "process_next_contract"
    assert flow.state.approved_contracts == []
    assert len(flow.state.no_go_log) == 1
    assert flow.state.no_go_log[0]["verdict"]["bid_decision"] == "NO-GO"

    finish_compliance_and_run_proposals(flow)

    assert call_log.proposal == []
    assert flow.state.total_approved == 0
    assert flow.state.total_proposals == 0


def test_conditional_go_without_extra_human_note_is_kept_for_proposal_generation(
    monkeypatch: pytest.MonkeyPatch,
    call_log: CallLog,
) -> None:
    patch_proposal(monkeypatch, call_log)

    flow = make_flow(human_note="")
    flow.state.contracts = [sample_contract()]
    flow.state.total_contracts = 1
    flow.state.current_contract = flow.state.contracts[0]
    flow.state.current_summary = flow_module.contract_to_summary(flow.state.current_contract)
    flow.state.current_verdict = conditional_go_verdict().model_dump()
    flow.state.review_iteration = 1

    flow.handle_conditional_go_func()

    assert flow.state.current_contract_index == 1
    assert len(flow.state.approved_contracts) == 1
    assert flow.state.approved_contracts[0][1]["bid_decision"] == "CONDITIONAL-GO"

    finish_compliance_and_run_proposals(flow)

    assert len(call_log.proposal) == 1
    assert "CONDIZIONI DA SODDISFARE" in call_log.proposal[0]
    assert flow.state.total_approved == 1
    assert flow.state.total_proposals == 1


def test_conditional_go_with_implicit_no_go_note_is_logged_and_skips_proposal(
    monkeypatch: pytest.MonkeyPatch,
    call_log: CallLog,
) -> None:
    patch_proposal(monkeypatch, call_log)

    flow = make_flow(human_note="we don't have this certification")
    flow.state.contracts = [sample_contract()]
    flow.state.total_contracts = 1
    flow.state.current_contract = flow.state.contracts[0]
    flow.state.current_summary = flow_module.contract_to_summary(flow.state.current_contract)
    flow.state.current_verdict = conditional_go_verdict().model_dump()
    flow.state.review_iteration = 1

    flow.handle_conditional_go_func()

    assert flow.state.current_contract_index == 1
    assert flow.state.approved_contracts == []
    assert flow.state.current_verdict["bid_decision"] == "NO-GO"
    assert len(flow.state.no_go_log) == 1

    finish_compliance_and_run_proposals(flow)

    assert call_log.proposal == []
    assert flow.state.total_approved == 0
    assert flow.state.total_proposals == 0
