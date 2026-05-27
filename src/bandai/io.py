from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
OUTPUT_DIR: Path = PROJECT_ROOT / "output"

# Ensure the output directory exists at import time.
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_json(data: dict, filename: str) -> Path:
    """Persist data as a pretty-printed JSON file in the output directory."""
    path = OUTPUT_DIR / filename
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved: %s", path)
    return path


def load_contract_from_outputs(contract_id: str, output_dir: Path | None = None) -> dict[str, Any] | None:
    """Return a previously discovered contract from output artifacts."""
    search_dir = output_dir or OUTPUT_DIR
    scout_path = search_dir / "01_scout_results.json"

    if not scout_path.exists():
        return None

    try:
        data = json.loads(scout_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("Could not parse scout output file: %s", scout_path)
        return None

    contracts = data.get("contracts", [])
    if not isinstance(contracts, list):
        return None

    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        if contract.get("canonical_contract_id") == contract_id or contract.get("contract_id") == contract_id:
            return contract

    return None
