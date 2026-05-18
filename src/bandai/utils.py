from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# Project Paths

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

CONFIG_DIR: Path = PROJECT_ROOT / "src" / "bandai" / "config"

KNOWLEDGE_DIR: Path = PROJECT_ROOT / "knowledge"

# YAML Loading

_yaml_cache: dict[str, dict[str, Any]] = {}


def load_yaml_config(filename: str, *, use_cache: bool = True) -> dict[str, Any]:
    """Load a YAML configuration file from the config/ directory."""
    if use_cache and filename in _yaml_cache:
        return _yaml_cache[filename]

    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict in {path}, got {type(data).__name__}")

    if use_cache:
        _yaml_cache[filename] = data

    return data


# Contract Formatting


def contract_to_summary(c: dict) -> str:
    """Format a contract dict into a human-readable summary string."""
    return (
        f"Titolo               : {c.get('title', 'N/A')}\n"
        f"Canonical Contract ID: {c.get('canonical_contract_id', 'N/A')}\n"
        f"Stazione appaltante  : {c.get('contracting_authority', 'N/A')}\n"
        f"Importo a base d'asta: EUR {c.get('value_eur', 0):,.0f}\n"
        f"Scadenza             : {c.get('deadline', 'N/A')}\n"
        f"CPV                  : {', '.join(c.get('cpv_codes', []))}\n"
        f"URL                  : {c.get('canonical_url', 'N/A')}"
    )


# JSON Extraction


def extract_json_array(raw: str) -> list:
    """Extract a JSON array from a raw LLM output string."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in the input.")
    return json.loads(match.group())


# Implicit NO-GO Detection

NO_GO_KEYWORDS: list[str] = [
    # Italian
    "non ho",
    "non abbiamo",
    "non saremo",
    "non possiamo",
    "non siamo",
    "manca",
    "mancano",
    "impossibile",
    "rinunciamo",
    "abbandoniamo",
    "lasciamo perdere",
    "basta",
    "stop",
    "terminiamo",
    "fermiamo",
    "non partecipo",
    "non partecipiamo",
    "ritiro",
    "ritiriamo",
    # English
    "we don't have",
    "we can't",
    "impossible",
    "give up",
    "stop",
    "quit",
]


def is_implicit_no_go(text: str) -> bool:
    """Fast keyword check for abandonment language (pre-LLM, zero cost)."""
    lower = text.lower()
    return any(kw in lower for kw in NO_GO_KEYWORDS)
