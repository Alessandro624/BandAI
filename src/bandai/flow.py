from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from crewai.flow.flow import Flow, listen, router, start  # type: ignore
from crewai.flow.persistence import persist  # type: ignore

from bandai.crews.compliance_crew import ComplianceCrew
from bandai.crews.proposal_crew import ProposalCrew
from bandai.crews.scout_crew import ScoutCrew
from bandai.models import ComplianceVerdict, FinalProposal
from bandai.config import IMPLICIT_NO_GO_KEYWORDS, _MAX_REVIEW_ITERATIONS

from typing import Tuple

log = logging.getLogger("bandai.flow")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


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
    approved_contracts: list[Tuple[dict, dict]] = Field(default_factory=list)
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


# Helper functions


def _save_json(data: dict, filename: str) -> Path:
    path = OUTPUT_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved: %s", path)
    return path


def _contract_to_summary(c: dict) -> str:
    return (
        f"Titolo               : {c.get('title', 'N/A')}\n"
        f"Canonical Contract ID: {c.get('canonical_contract_id', 'N/A')}\n"
        f"Stazione appaltante  : {c.get('contracting_authority', 'N/A')}\n"
        f"Importo a base d'asta: EUR {c.get('value_eur', 0):,.0f}\n"
        f"Scadenza             : {c.get('deadline', 'N/A')}\n"
        f"CPV                  : {', '.join(c.get('cpv_codes', []))}\n"
        f"URL                  : {c.get('canonical_url', 'N/A')}"
    )


def _extract_json_array(raw: str) -> list:
    """Extract a JSON array from the raw LLM output string."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in the input.")
    return json.loads(match.group())


def _is_implicit_no_go(text: str) -> bool:
    """Fast keyword check for abandonment language (pre-LLM, zero cost)."""
    lower = text.lower()
    return any(kw in lower for kw in IMPLICIT_NO_GO_KEYWORDS)


def _ask_human_on_conditional_go(
    contract: dict,
    verdict: ComplianceVerdict,
    iteration: int,
    max_iter: int,
) -> str:
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
    print(f"\nProvide additional information to unlock this opportunity")
    print(f"(e.g., ongoing certifications, partners, already acquired documents).")
    print(f"Press Enter to leave unchanged.")
    print(f"To decline, write: 'enough', 'we don't have X', etc.")
    return input(f"[{iteration}/{max_iter}] Input: ").strip()


# BandAI Flow


@persist()
class BandAIFlow(Flow[BandAIState]):
    """
    CrewAI Flow that orchestrates the full BandAI procurement pipeline.
    """

    @start()
    def begin(self) -> None:
        """Entry point: gather user preferences."""
        if self.state.mode == "full":
            log.info("=== PHASE 1: SCOUTING ===")
            print("\nDescribe your preferences for this scouting session.")
            print("Examples: sector, region, minimum/maximum amount, keywords...")
            prefs = input("Preferences (press Enter to skip): ").strip()
            self.state.user_preferences = prefs or "No specific preferences - use standard CPV filters."
        elif self.state.mode == "scout":
            self.state.user_preferences = "No specific preferences - use standard CPV filters."

    @router(begin)
    def route_from_begin(self) -> str:
        """Decide: scout, or skip straight to compliance?"""
        if self.state.mode in ("full", "scout"):
            return "scout"
        return "skip_scout"

    # Phase 1: Scouting

    @listen("scout")
    def run_scouting(self) -> None:
        """Run the Scout crew to discover tenders."""
        try:
            built_crew, final_task = ScoutCrew().build(user_preferences=self.state.user_preferences)
            built_crew.kickoff()
            raw = final_task.output.raw

            try:
                parsed = _extract_json_array(raw)
                contracts = [json.loads(item) if isinstance(item, str) else item for item in parsed]
            except (json.JSONDecodeError, AttributeError, ValueError):
                log.error("Failed to parse Scout output as JSON. Raw output:\n%s", raw)
                contracts = []

            self.state.contracts = contracts
            self.state.total_contracts = len(contracts)
            _save_json({"contracts": contracts}, "01_scout_results.json")
            log.info("Scout found %d unique contracts.", len(contracts))
        except Exception:
            log.exception("Scouting failed")
            self.state.contracts = []

    @router(run_scouting)
    def route_after_scout(self) -> str:
        """Decide next step after scouting."""
        if self.state.mode == "scout":
            return "end_scout"
        return "start_compliance"

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

    @router(skip_to_compliance)
    def route_skip(self) -> str:
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
    def route_after_init(self) -> str:
        return "process_next_contract"

    @listen("process_next_contract")
    def process_next_contract_func(self) -> None:
        """Process the next contract in the compliance queue."""
        contracts = self.state.contracts
        idx = self.state.current_contract_index

        if idx >= len(contracts):
            # All contracts processed - save NO-GO log
            if self.state.no_go_log:
                _save_json(
                    {"no_go_contracts": self.state.no_go_log, "total": len(self.state.no_go_log)},
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
        self.state.current_summary = _contract_to_summary(contract)

        log.info(
            "  [%d/%d] %s",
            idx + 1,
            len(contracts),
            contract.get("title", "?"),
        )

    @router(process_next_contract_func)
    def route_process_contract(self) -> str:
        """All done, or run compliance on the next contract?"""
        if self.state.current_contract_index >= len(self.state.contracts):
            return "compliance_done"
        return "run_compliance_crew"

    @listen("run_compliance_crew")
    def run_compliance_crew_func(self) -> None:
        """Run the Compliance crew for the current contract."""
        try:
            built_crew, verdict_task = ComplianceCrew().build(self.state.current_summary)
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
    def route_verdict(self) -> str:
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

    # Conditional-GO human review loop

    @listen("handle_conditional_go")
    def handle_conditional_go_func(self) -> None:
        """Handle CONDITIONAL-GO with human review loop.

        All logic lives here - the router just checks the verdict state
        to decide whether to loop or continue.
        """
        verdict = ComplianceVerdict(**self.state.current_verdict)
        contract = self.state.current_contract
        iteration = self.state.review_iteration

        human_note = _ask_human_on_conditional_go(contract, verdict, iteration, _MAX_REVIEW_ITERATIONS)

        # Exit 1: user skipped
        if not human_note:
            log.info("  Human skipped - keeping CONDITIONAL-GO as-is.")
            self._save_compliance_result()
            self.state.current_contract_index += 1
            return

        # Exit 2: fast implicit NO-GO detection (pre-LLM)
        if _is_implicit_no_go(human_note):
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
    def route_after_conditional(self) -> str:
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
    def route_after_compliance(self) -> str:
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

            summary = _contract_to_summary(contract)
            verdict = ComplianceVerdict(**verdict_dict)
            if verdict.bid_decision == "CONDITIONAL-GO" and verdict.conditions:
                summary += "\n\nCONDIZIONI DA SODDISFARE (CONDITIONAL-GO):\n" + "\n".join(f"  - {c}" for c in verdict.conditions)

            try:
                built_crew, proposal_task = ProposalCrew().build(summary)
                built_crew.kickoff()
                proposal: FinalProposal = proposal_task.output.pydantic
                self.state.proposals.append(proposal.model_dump())
                _save_json(
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

    # Internal helpers

    def _save_compliance_result(self) -> None:
        idx = self.state.current_contract_index + 1
        contract = self.state.current_contract
        contract_id = contract.get("canonical_contract_id", f"unknown_{idx}")
        _save_json(
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
