from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Literal

from pydantic import BaseModel, Field, TypeAdapter
from crewai.flow.flow import Flow, listen, router, start  # type: ignore

from bandai.crews.compliance_crew import ComplianceCrew
from bandai.crews.proposal_crew import ProposalCrew
from bandai.crews.scout_crew import ScoutCrew
from bandai.models import ComplianceVerdict, FinalProposal, ResolvedContract
from bandai.config import _MAX_REVIEW_ITERATIONS
from bandai.utils import contract_to_summary, extract_json_array, is_implicit_no_go
from bandai.io import save_json

log = logging.getLogger("bandai.flow")


def _normalize_resolved_contract_dict(contract: dict) -> dict:
    normalized = dict(contract)
    authority = normalized.get("contracting_authority")
    if isinstance(authority, dict):
        normalized["contracting_authority"] = authority.get("name") or "Unknown authority"
    return normalized


# Human Input Callback

HumanInputFn = Callable[
    [dict, ComplianceVerdict, int, int],
    str,
]


def _default_human_input(
    contract: dict,
    verdict: ComplianceVerdict,
    iteration: int,
    max_iter: int,
) -> str:
    """CLI-based human input (blocking)."""
    print(f"\n{'=' * 60}")
    print(f"  CONDITIONAL-GO  [{iteration}/{max_iter}]")
    print(f"  {contract.get('title', '')[:50]}")
    print(f"  Compliance score: {verdict.compliance_score:.2f}")
    print(f"\n  Conditions still open:")
    for c in verdict.conditions:
        print(f"    - {c}")
    print(f"\n  Key risks:")
    for r in verdict.key_risks:
        print(f"    - {r}")
    print(f"{'=' * 60}")
    print(
        f"\nProvide additional information to unlock this opportunity\n"
        f"(e.g., ongoing certifications, partners, already acquired documents).\n"
        f"Press Enter to leave unchanged.\n"
        f"To decline, write: 'enough', 'we don't have X', etc."
    )
    return input(f"[{iteration}/{max_iter}] Input: ").strip()


# Flow State


class BandAIState(BaseModel):
    """Typed state for the BandAI procurement flow."""

    # Inputs
    user_preferences: str = ""
    mode: str = "full"

    # Phase 1: Scouting
    contracts: list[dict] = Field(default_factory=list)

    # Phase 2: Compliance
    current_contract_index: int = 0
    approved_contracts: list[tuple[dict, dict]] = Field(default_factory=list)
    no_go_log: list[dict] = Field(default_factory=list)
    current_verdict: dict | None = None
    current_contract: dict | None = None
    current_summary: str = ""
    review_iteration: int = 0

    # Phase 3: Proposals
    proposals: list[dict] = Field(default_factory=list)

    # Summary
    total_contracts: int = 0
    total_approved: int = 0
    total_proposals: int = 0


# BandAI Flow


class BandAIFlow(Flow[BandAIState]):
    """
    CrewAI Flow that orchestrates the full BandAI procurement pipeline.
    """

    def __init__(self, human_input_fn: HumanInputFn | None = None) -> None:
        super().__init__()
        self._human_input_fn = human_input_fn or _default_human_input

    @start()
    def begin(self) -> None:
        """Entry point: gather user preferences."""
        if self.state.mode == "full":
            log.info("=== PHASE 1: SCOUTING ===")
            print("\nDescribe your preferences for this scouting session.\n" "Examples: sector, region, minimum/maximum amount, keywords...")
            prefs = input("Preferences (press Enter to skip): ").strip()
            self.state.user_preferences = prefs or "No specific preferences - use standard CPV filters."
        elif self.state.mode == "scout":
            self.state.user_preferences = "No specific preferences - use standard CPV filters."

    @router(begin)
    def route_from_begin(self) -> Literal["scout", "skip_scout"]:
        """Decide next step after scouting."""
        return "scout" if self.state.mode in ("full", "scout") else "skip_scout"

    # Phase 1: Scouting

    @listen("scout")
    def run_scouting(self) -> None:
        """Run the Scout crew to discover tenders."""
        try:
            built_crew, final_task = ScoutCrew().build(
                user_preferences=self.state.user_preferences,
            )
            built_crew.kickoff()

            raw = final_task.output.raw
            log.debug("Raw scout output:\n%s", raw)
            try:
                parsed = [_normalize_resolved_contract_dict(contract) for contract in extract_json_array(raw)]
                resolved = TypeAdapter(list[ResolvedContract]).validate_python(parsed)
                contracts = [contract.model_dump() for contract in resolved]
            except Exception:
                pydantic_output = getattr(final_task.output, "pydantic", None)
                try:
                    parsed = [_normalize_resolved_contract_dict(contract if isinstance(contract, dict) else contract.model_dump()) for contract in (pydantic_output or [])]
                    resolved = TypeAdapter(list[ResolvedContract]).validate_python(parsed)
                    contracts = [contract.model_dump() for contract in resolved]
                except Exception:
                    log.error("Scout output was not parseable. Raw:\n%s", raw)
                    contracts = []

            self.state.contracts = contracts
            self.state.total_contracts = len(contracts)
            save_json({"contracts": contracts}, "01_scout_results.json")
            log.info("Scout found %d unique contracts.", len(contracts))
        except Exception:
            log.exception("Scouting failed")
            self.state.contracts = []

    @router(run_scouting)
    def route_after_scout(self) -> Literal["end_scout", "start_compliance"]:
        """Decide next step after scouting."""
        return "end_scout" if self.state.mode == "scout" else "start_compliance"

    @listen("end_scout")
    def end_scout_only(self) -> None:
        """Scout-only mode: print summary and stop."""
        log.info(
            "Scout-only mode completed | contracts_discovered=%d",
            len(self.state.contracts),
        )

    @listen("skip_scout")
    def skip_to_compliance(self) -> None:
        """Skip scouting when mode != full/scout."""
        log.info("Skipping scouting phase.")
        pass

    @router(skip_to_compliance)
    def route_skip(self) -> Literal["start_compliance"]:
        return "start_compliance"

    # Phase 2: Compliance

    @listen("start_compliance")
    def init_compliance(self) -> None:
        """Initialize compliance analysis for all discovered contracts."""
        log.info(
            "=== PHASE 2: COMPLIANCE ANALYSIS (%d contracts) ===",
            len(self.state.contracts),
        )
        self.state.current_contract_index = 0

    @router(init_compliance)
    def route_after_init(self) -> Literal["process_next_contract"]:
        return "process_next_contract"

    @listen("process_next_contract")
    def process_next_contract_func(self) -> None:
        """Process the next contract in the compliance queue."""
        contracts = self.state.contracts
        idx = self.state.current_contract_index

        if idx >= len(contracts):
            # All contracts processed - save NO-GO log
            if self.state.no_go_log:
                save_json(
                    {
                        "no_go_contracts": self.state.no_go_log,
                        "total": len(self.state.no_go_log),
                    },
                    "02_no_go_review_required.json",
                )
                log.warning(
                    "%d contract(s) NO-GO -> output/02_no_go_review_required.json",
                    len(self.state.no_go_log),
                )
            log.info(
                "%d / %d contracts approved.",
                len(self.state.approved_contracts),
                len(contracts),
            )
            return

        contract = contracts[idx]
        self.state.current_contract = contract
        self.state.current_summary = contract_to_summary(contract)

        log.info("  [%d/%d] %s", idx + 1, len(contracts), contract.get("title", "?"))

    @router(process_next_contract_func)
    def route_process_contract(self) -> Literal["compliance_done", "run_compliance_crew"]:
        """All done, or run compliance on the next contract?"""
        if self.state.current_contract_index >= len(self.state.contracts):
            return "compliance_done"
        return "run_compliance_crew"

    @listen("run_compliance_crew")
    def run_compliance_crew_func(self) -> None:
        """Run the Compliance crew for the current contract."""
        try:
            built_crew, verdict_task = ComplianceCrew().build(
                self.state.current_summary,
            )
            built_crew.kickoff()

            verdict: ComplianceVerdict = verdict_task.output.pydantic
            self.state.current_verdict = verdict.model_dump()
            log.info(
                "  -> %s  (score=%.2f)",
                verdict.bid_decision,
                verdict.compliance_score,
            )
        except Exception:
            log.exception(
                "Compliance crew failed for contract %s",
                self.state.current_contract_index,
            )
            self.state.current_verdict = None

    @router(run_compliance_crew_func)
    def route_verdict(self) -> Literal["handle_conditional_go", "process_next_contract"]:
        """Route based on the compliance verdict."""
        if self.state.current_verdict is None:
            self.state.current_contract_index += 1
            return "process_next_contract"

        verdict = ComplianceVerdict(**self.state.current_verdict)

        if verdict.bid_decision == "CONDITIONAL-GO":
            self.state.review_iteration = 1
            return "handle_conditional_go"
        elif verdict.bid_decision == "GO":
            self.state.approved_contracts.append((self.state.current_contract, self.state.current_verdict))
            self._save_compliance_result()
            self.state.current_contract_index += 1
            return "process_next_contract"
        else:  # NO-GO
            self._save_no_go(verdict)
            self.state.current_contract_index += 1
            return "process_next_contract"

    # Conditional-GO review loop

    @listen("handle_conditional_go")
    def handle_conditional_go_func(self) -> None:
        """Handle CONDITIONAL-GO with human review loop."""
        verdict = ComplianceVerdict(**self.state.current_verdict)
        contract = self.state.current_contract
        iteration = self.state.review_iteration

        human_note = self._human_input_fn(contract, verdict, iteration, _MAX_REVIEW_ITERATIONS)

        # Exit 1: user skipped
        if not human_note:
            log.info("  Human skipped - keeping CONDITIONAL-GO as-is.")
            self.state.approved_contracts.append((contract, self.state.current_verdict))
            self._save_compliance_result()
            self.state.current_contract_index += 1
            return

        # Exit 2: fast implicit NO-GO detection (pre-LLM)
        if is_implicit_no_go(human_note):
            log.warning("  Implicit NO-GO detected: '%s'", human_note)
            self.state.current_verdict = ComplianceVerdict(
                bid_decision="NO-GO",
                conditions=[],
                key_risks=verdict.key_risks,
                key_strengths=verdict.key_strengths,
                compliance_score=verdict.compliance_score,
                legal_flags=verdict.legal_flags,
                verdict_rationale=(f"The user has reported inability to proceed " f'(iter {iteration}): "{human_note}"'),
            ).model_dump()
            self._save_no_go(ComplianceVerdict(**self.state.current_verdict))
            self.state.current_contract_index += 1
            return

        # Substantive input: run review crew
        try:
            review_crew, review_task = ComplianceCrew().build_review(
                contract_summary=self.state.current_summary,
                original_verdict=verdict,
                human_note=human_note,
                iteration=iteration,
            )
            review_crew.kickoff()
            self.state.current_verdict = review_task.output.pydantic.model_dump()
            log.info(
                "  Review iter %d : %s (score=%.2f)",
                iteration,
                self.state.current_verdict["bid_decision"],
                self.state.current_verdict["compliance_score"],
            )
        except Exception:
            log.exception("Review crew failed")
            # Keep original verdict on error

        updated_verdict = ComplianceVerdict(**self.state.current_verdict)

        if updated_verdict.bid_decision == "CONDITIONAL-GO":
            self.state.review_iteration += 1
            if self.state.review_iteration > _MAX_REVIEW_ITERATIONS:
                log.warning(
                    "  MAX_REVIEW_ITERATIONS (%d) reached - forcing NO-GO.",
                    _MAX_REVIEW_ITERATIONS,
                )
                self.state.current_verdict = ComplianceVerdict(
                    bid_decision="NO-GO",
                    conditions=updated_verdict.conditions,
                    key_risks=updated_verdict.key_risks + [f"{_MAX_REVIEW_ITERATIONS} limit of iterations reached"],
                    key_strengths=updated_verdict.key_strengths,
                    compliance_score=updated_verdict.compliance_score,
                    legal_flags=updated_verdict.legal_flags,
                    verdict_rationale=(f"No resolution reached after {_MAX_REVIEW_ITERATIONS} " f"human review iterations. " f"Bid classified as NO-GO for security reasons."),
                ).model_dump()
                self._save_no_go(ComplianceVerdict(**self.state.current_verdict))
                self.state.current_contract_index += 1
                return
            # Still CONDITIONAL-GO under the limit - router will loop back
            return

        # GO or NO-GO from review
        if updated_verdict.bid_decision == "GO":
            self.state.approved_contracts.append((self.state.current_contract, self.state.current_verdict))
            self._save_compliance_result()
        else:
            self._save_no_go(updated_verdict)

        self.state.current_contract_index += 1

    @router(handle_conditional_go_func)
    def route_after_conditional(self) -> Literal["handle_conditional_go", "process_next_contract"]:
        """Loop back for another review iteration, or move on."""
        if self.state.current_verdict is not None:
            verdict = ComplianceVerdict(**self.state.current_verdict)
            if verdict.bid_decision == "CONDITIONAL-GO":
                return "handle_conditional_go"
        return "process_next_contract"

    # Phase 2 done -> Phase 3

    @listen("compliance_done")
    def after_compliance(self) -> None:
        """Compliance phase complete - move to proposals."""
        self.state.total_approved = len(self.state.approved_contracts)
        log.info(
            "Compliance phase completed | approved_contracts=%d",
            self.state.total_approved,
        )

    @router(after_compliance)
    def route_after_compliance(self) -> Literal["start_proposals"]:
        return "start_proposals"

    # Phase 3: Proposals

    @listen("start_proposals")
    def run_proposals(self) -> None:
        """Run the Proposal crew for all approved contracts."""
        log.info(
            "=== PHASE 3: PROPOSAL GENERATION (%d contracts) ===",
            self.state.total_approved,
        )

        for i, (contract, verdict_dict) in enumerate(self.state.approved_contracts, 1):
            contract_id = contract.get("canonical_contract_id", f"unknown_{i}")
            log.info(
                "  [%d/%d] Writing proposal for Contract ID %s",
                i,
                self.state.total_approved,
                contract_id,
            )

            summary = contract_to_summary(contract)
            verdict = ComplianceVerdict(**verdict_dict)
            if verdict.bid_decision == "CONDITIONAL-GO" and verdict.conditions:
                summary += "\n\nCONDIZIONI DA SODDISFARE (CONDITIONAL-GO):\n" + "\n".join(f"  - {c}" for c in verdict.conditions)

            try:
                built_crew, proposal_task = ProposalCrew().build(summary)
                built_crew.kickoff()
                proposal: FinalProposal = proposal_task.output.pydantic
                self.state.proposals.append(proposal.model_dump())
                save_json(
                    proposal.model_dump(),
                    f"03_proposal_{i:02d}_{contract_id}.json",
                )
                log.info(
                    "  OK %d words, quality=%.2f",
                    proposal.word_count,
                    proposal.quality_score,
                )
            except Exception:
                log.exception("Proposal generation failed for contract %s", contract_id)

        self.state.total_proposals = len(self.state.proposals)
        self._print_summary()

    # Internal Helpers

    def _save_compliance_result(self) -> None:
        idx = self.state.current_contract_index + 1
        contract = self.state.current_contract
        contract_id = contract.get("canonical_contract_id", f"unknown_{idx}")
        save_json(
            {"contract": contract, "verdict": self.state.current_verdict},
            f"02_compliance_{idx:02d}_{contract_id}.json",
        )

    def _save_no_go(self, verdict: ComplianceVerdict) -> None:
        contract = self.state.current_contract
        idx = self.state.current_contract_index + 1
        contract_id = contract.get("canonical_contract_id", f"unknown_{idx}")
        self.state.no_go_log.append(
            {
                "requires_human_review": True,
                "contract": {
                    "contract_id": contract_id,
                    "title": contract.get("title", "N/A"),
                    "value_eur": contract.get("value_eur"),
                    "deadline": contract.get("deadline"),
                    "url": contract.get("canonical_url"),
                },
                "verdict": {
                    "bid_decision": verdict.bid_decision,
                    "compliance_score": verdict.compliance_score,
                    "key_risks": verdict.key_risks,
                    "legal_flags": verdict.legal_flags,
                    "verdict_rationale": verdict.verdict_rationale,
                },
                "review_instructions": ("Evaluate whether the blocks in key_risks can be removed " "before the deadline."),
            }
        )
        self._save_compliance_result()
        log.warning(
            "  NO-GO - flagged for human review: %s",
            contract.get("title", "?"),
        )

    def _print_summary(self) -> None:
        w = 72
        print("\n" + "=" * w)
        print("  BANDAI - PIPELINE SUMMARY  |  " + datetime.now().strftime("%Y-%m-%d %H:%M"))
        print("=" * w)
        print(f"  Contracts discovered  : {self.state.total_contracts}")
        print(f"  GO / CONDITIONAL-GO   : {self.state.total_approved}")
        print(f"  Proposals generated   : {self.state.total_proposals}")
        print("-" * w)
        for i, (contract, verdict_dict) in enumerate(self.state.approved_contracts, 1):
            title = contract.get("title", "N/A")[:48]
            value = contract.get("value_eur", 0)
            bid_decision = verdict_dict.get("bid_decision", "N/A")
            print(f"  [{i}] {bid_decision:<16} | EUR {value:>10,.0f} | {title}...")
        print("=" * w + "\n")
