#!/usr/bin/env python

import argparse
import logging
import sys
import warnings
import subprocess

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from bandai.config import validate_config, get_active_provider, validate_portals
from bandai.flow import BandAIFlow, BandAIState
from bandai.io import OUTPUT_DIR, load_contract_from_outputs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bandai")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BandAI - Italian SME Procurement Agent")
    p.add_argument(
        "--mode",
        choices=["full", "scout", "propose"],
        default="full",
        help="Pipeline mode (default: full)",
    )
    p.add_argument(
        "--contract",
        type=str,
        default=None,
        help="Contract ID for --mode propose",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without running LLM calls",
    )
    return p.parse_args()


def _run_command(command: list[str]) -> None:
    """Run a subprocess command and exit with the same return code."""
    log.info("Running command: %s", " ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        log.error("Command failed with exit code %s", result.returncode)
        sys.exit(result.returncode)


def _startup_validation() -> None:
    """Validate configuration at startup. Exits with clear errors on failure."""
    errors = validate_config()
    if errors:
        log.error("Configuration validation failed:")
        for err in errors:
            log.error("  - %s", err)
        sys.exit(1)

    # Validate that at least one portal is configured.
    try:
        validate_portals()
    except ValueError as exc:
        log.error("Portal validation failed: %s", exc)
        sys.exit(1)

    provider = get_active_provider()
    log.info("Provider: %s (%s)", provider.name, provider.description)


def run() -> None:
    """Run the BandAI procurement pipeline via CrewAI Flow."""
    args = _parse_args()

    # Always validate config, even in dry-run
    _startup_validation()

    log.info("Starting BandAI Flow | mode=%s | dry_run=%s", args.mode, args.dry_run)

    if args.dry_run:
        log.info("DRY-RUN - no LLM calls. Configuration and entrypoint are valid.")
        sys.exit(0)

    if args.mode == "propose" and not args.contract:
        log.error("--mode propose requires --contract <CONTRACT_ID>")
        sys.exit(1)

    try:
        # Initialize flow state
        state = BandAIState(mode=args.mode)

        if args.mode == "propose":
            contract = load_contract_from_outputs(args.contract)
            if contract is None:
                log.error(
                    "Contract %s not found in %s. Run `bandai --mode scout` or `bandai --mode full` first.",
                    args.contract,
                    OUTPUT_DIR,
                )
                sys.exit(1)
            state.contracts = [contract]

        flow = BandAIFlow()
        flow.kickoff(inputs=state.model_dump())

        log.info("BandAI pipeline completed successfully")

    except Exception:
        log.exception("BandAI pipeline failed")
        raise


def train() -> None:
    """Run CrewAI training through the CLI."""
    _run_command(["crewai", "train", *sys.argv[1:]])


def replay() -> None:
    """Replay a previous CrewAI task execution through the CLI."""
    _run_command(["crewai", "replay", *sys.argv[1:]])


def test() -> None:
    """Run CrewAI test evaluations through the CLI."""
    _run_command(["crewai", "test", *sys.argv[1:]])


def run_pytest() -> None:
    """Run unit tests (pytest) via the project script uv run pytest_unit."""
    _run_command(["pytest", "tests/", "-v", *sys.argv[1:]])


def install_chromium() -> None:
    """Install the Chromium browser required by Playwright crawler tools."""
    _run_command([sys.executable, "-m", "playwright", "install", "chromium"])


def run_with_trigger() -> None:
    """Run the BandAI pipeline from an external trigger (webhook/API)."""
    run()


if __name__ == "__main__":
    run()
