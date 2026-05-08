#!/usr/bin/env python
import argparse
import json
import logging
import sys
import warnings
import re

from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from bandai.crews.compliance_crew import ComplianceCrew
from bandai.crews.proposal_crew import ProposalCrew
from bandai.crews.scout_crew import ScoutCrew
from bandai.models import ComplianceVerdict, FinalProposal
from bandai.config import IMPLICIT_NO_GO_KEYWORDS, _MAX_REVIEW_ITERATIONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bandai")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


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


def _is_implicit_no_go(text: str) -> bool:
    """
    Fast keyword check for abandonment language.
    Runs before any LLM call - zero cost, zero latency.
    The human_review_task also handles ambiguous cases inside the LLM.
    """
    lower = text.lower()
    return any(kw in lower for kw in IMPLICIT_NO_GO_KEYWORDS)


def _extract_json_array(raw: str) -> list:
    """
    Attempt to extract a JSON array from the raw string.
    Handles cases where the LLM might return a single object or a list of objects.
    """
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in the input.")
    return json.loads(match.group())


def run_scouting() -> list[dict]:
    log.info("=== PHASE 1: SCOUTING ===")
    print("\nDescribe your preferences for this scouting session.")
    print("Examples: sector, region, minimum/maximum amount, keywords...")
    user_preferences = input("Preferences (press Enter to skip): ").strip()
    if not user_preferences:
        user_preferences = "No specific preferences - use standard CPV filters."
    built_crew, resolution_task = ScoutCrew().build(user_preferences=user_preferences)
    built_crew.kickoff()
    raw = resolution_task.output.raw
    try:
        parsed = _extract_json_array(raw)
        contracts: list[dict] = [json.loads(item) if isinstance(item, str) else item for item in parsed]
    except (json.JSONDecodeError, AttributeError, ValueError) as e:
        log.error("Failed to parse Scout output as JSON. Raw output:\n%s", raw)
        contracts = []

    # TODO: hard coded filename - consider dynamic naming with timestamp or user input
    _save_json({"contracts": contracts}, "01_scout_results.json")
    log.info("Scout found %d unique contracts.", len(contracts))
    return contracts


def run_compliance(contracts: list[dict]) -> list[tuple[dict, ComplianceVerdict]]:
    log.info("=== PHASE 2: COMPLIANCE ANALYSIS (%d contracts) ===", len(contracts))
    approved: list[tuple[dict, ComplianceVerdict]] = []
    no_go_log: list[dict] = []

    for i, contract in enumerate(contracts, 1):
        summary = _contract_to_summary(contract)
        log.info("  [%d/%d] %s", i, len(contracts), contract.get("title", "?"))

        built_crew, verdict_task = ComplianceCrew().build(summary)
        built_crew.kickoff()

        verdict: ComplianceVerdict = verdict_task.output.pydantic
        log.info("  -> %s  (score=%.2f)", verdict.bid_decision, verdict.compliance_score)
        if verdict.bid_decision == "CONDITIONAL-GO":
            iteration = 1
            while iteration <= _MAX_REVIEW_ITERATIONS and verdict.bid_decision == "CONDITIONAL-GO":

                human_note = _ask_human_on_conditional_go(contract, verdict, iteration, _MAX_REVIEW_ITERATIONS)

                # Exit 1: user skipped (empty input)
                if not human_note:
                    log.info("  Human skipped - keeping CONDITIONAL-GO as-is.")
                    break

                # Exit 2: fast implicit NO-GO detection (pre-LLM)
                if _is_implicit_no_go(human_note):
                    log.warning("  Implicit NO-GO detected from human input: '%s'", human_note)
                    verdict = ComplianceVerdict(
                        bid_decision="NO-GO",
                        conditions=[],
                        key_risks=verdict.key_risks,
                        key_strengths=verdict.key_strengths,
                        compliance_score=verdict.compliance_score,
                        legal_flags=verdict.legal_flags,
                        verdict_rationale=(f"The user has reported inability to proceed " f'(iter {iteration}): "{human_note}"'),
                    )
                    break

                # Substantive input: run review crew
                review_crew, review_task = ComplianceCrew().build_review(
                    contract_summary=summary,
                    original_verdict=verdict,
                    human_note=human_note,
                    iteration=iteration,
                )
                review_crew.kickoff()
                verdict = review_task.output.pydantic
                log.info(
                    "  Review iter %d : %s (score=%.2f)",
                    iteration,
                    verdict.bid_decision,
                    verdict.compliance_score,
                )
                iteration += 1

            # Exit 3: max iterations reached, still CONDITIONAL-GO : NO-GO
            if verdict.bid_decision == "CONDITIONAL-GO":
                log.warning("  MAX_REVIEW_ITERATIONS (%d) reached - forcing NO-GO.", _MAX_REVIEW_ITERATIONS)
                verdict = ComplianceVerdict(
                    bid_decision="NO-GO",
                    conditions=verdict.conditions,
                    key_risks=verdict.key_risks + [f"{_MAX_REVIEW_ITERATIONS} limit of iterations reached"],
                    key_strengths=verdict.key_strengths,
                    compliance_score=verdict.compliance_score,
                    legal_flags=verdict.legal_flags,
                    verdict_rationale=(
                        f"No resolution reached after {_MAX_REVIEW_ITERATIONS} human review iterations. Bid classified as NO-GO for security reasons. Reopen manually if the situation changes."
                    ),
                )
        log.info("  -> %s  (score=%.2f)", verdict.bid_decision, verdict.compliance_score)

        contract_id = contract.get("canonical_contract_id", f"unknown_{i}")
        _save_json(
            {"contract": contract, "verdict": verdict.model_dump()},
            f"02_compliance_{i:02d}_{contract_id}.json",
        )

        if verdict.bid_decision in ("GO", "CONDITIONAL-GO"):
            approved.append((contract, verdict))
        else:
            no_go_log.append(
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
                    "review_instructions": ("Evaluate whether the blocks in key_risks can be removed before the deadline (e.g., subcontracts, ATI, missing documents)."),
                }
            )
            log.warning("  NO-GO - flagged for human review: %s", contract.get("title", "?"))

    if no_go_log:
        _save_json(
            {"no_go_contracts": no_go_log, "total": len(no_go_log)},
            "02_no_go_review_required.json",
        )
        log.warning("%d contract(s) NO-GO -> output/02_no_go_review_required.json", len(no_go_log))

    log.info("%d / %d contracts approved.", len(approved), len(contracts))
    return approved


def run_proposals(approved: list[tuple[dict, ComplianceVerdict]]) -> list[FinalProposal]:
    log.info("=== PHASE 3: PROPOSAL GENERATION (%d contracts) ===", len(approved))
    proposals: list[FinalProposal] = []

    for i, (contract, verdict) in enumerate(approved, 1):
        contract_id = contract.get("canonical_contract_id", f"unknown_{i}")
        log.info("  [%d/%d] Writing proposal for Contract ID %s", i, len(approved), contract_id)

        summary = _contract_to_summary(contract)
        if verdict.bid_decision == "CONDITIONAL-GO" and verdict.conditions:
            summary += "\n\nCONDIZIONI DA SODDISFARE (CONDITIONAL-GO):\n" + "\n".join(f"  - {c}" for c in verdict.conditions)

        built_crew, proposal_task = ProposalCrew().build(summary)
        built_crew.kickoff()

        proposal: FinalProposal = proposal_task.output.pydantic
        proposals.append(proposal)
        _save_json(proposal.model_dump(), f"03_proposal_{i:02d}_{contract_id}.json")
        log.info("  OK %d words, quality=%.2f", proposal.word_count, proposal.quality_score)

    return proposals


def _print_summary(contracts, approved, proposals):
    w = 72
    print("\n" + "=" * w)
    print("  BANDAI - PIPELINE SUMMARY  |  " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * w)
    print(f"  Contracts discovered  : {len(contracts)}")
    print(f"  GO / CONDITIONAL-GO   : {len(approved)}")
    print(f"  Proposals generated   : {len(proposals)}")
    print("-" * w)
    for i, (contract, verdict) in enumerate(approved, 1):
        title = contract.get("title", "N/A")[:48]
        value = contract.get("value_eur", 0)
        print(f"  [{i}] {verdict.bid_decision:<16} | EUR {value:>10,.0f} | {title}...")
    print("=" * w + "\n")


def run() -> None:
    args = _parse_args()

    if args.dry_run:
        log.info("DRY-RUN - no LLM calls. Config OK.")
        sys.exit(0)

    if args.mode == "full":
        contracts = run_scouting()
        approved = run_compliance(contracts)
        proposals = run_proposals(approved)
        _print_summary(contracts, approved, proposals)

    elif args.mode == "scout":
        contracts = run_scouting()
        log.info("Scout-only complete. %d contracts.", len(contracts))

    elif args.mode == "propose":
        if not args.contract:
            log.error("--mode propose requires --contract <CONTRACT_ID>")
            sys.exit(1)
        stub = {
            "canonical_contract_id": args.contract,
            "title": f"Contratto {args.contract} (manuale)",
            "contracting_authority": "Da capitolato",
            "deadline": "Da capitolato",
            "value_eur": 0,
            "cpv_codes": [],
            "canonical_url": f"https://www.anticorruzione.it/contract/{args.contract}",
        }
        approved = run_compliance([stub])
        proposals = run_proposals(approved)
        _print_summary([stub], approved, proposals)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BandAI - Italian SME Procurement Agent")
    p.add_argument("--mode", choices=["full", "scout", "propose"], default="full")
    p.add_argument("--contract", type=str, default=None, help="Contract ID for --mode propose")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def train() -> None:
    log.info("Training not applicable. Use 'bandai' to run.")


def replay() -> None:
    log.info("Use 'crewai replay -t <task_id>' for task replay.")


def test() -> None:
    log.info("Use 'crewai test' for crew testing.")


if __name__ == "__main__":
    run()
