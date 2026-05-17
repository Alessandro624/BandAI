from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from crewai.knowledge.source.string_knowledge_source import StringKnowledgeSource  # type: ignore

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_COMPANY_PROFILE_PATH = _PROJECT_ROOT / "knowledge" / "company_profile.json"


# Public helpers


def get_company_knowledge_data() -> dict[str, Any]:
    """Return the company knowledge as validated JSON-compatible data."""
    if not _COMPANY_PROFILE_PATH.exists():
        raise FileNotFoundError(f"Knowledge source not found: {_COMPANY_PROFILE_PATH}. " "Create knowledge/company_profile.json based on the template.")

    return json.loads(_COMPANY_PROFILE_PATH.read_text(encoding="utf-8"))


def get_company_knowledge_source() -> StringKnowledgeSource:
    """Build a CrewAI knowledge source from the company profile data."""
    data = get_company_knowledge_data()
    log.info("Registering company knowledge source from validated data")
    return StringKnowledgeSource(
        content=json.dumps(data, ensure_ascii=False, indent=2),
    )


def get_all_knowledge_sources() -> list:
    """Return every knowledge source available to BandAI agents.

    Currently this is just the company profile, but the list grows
    automatically when new sources are added to knowledge/.
    """
    sources: list = []
    try:
        sources.append(get_company_knowledge_source())
    except FileNotFoundError:
        log.warning("Company profile knowledge source not found - " "agents will rely on prompt-injected data only.")
    except Exception:
        log.warning("Failed to create knowledge source ...")
    return sources
