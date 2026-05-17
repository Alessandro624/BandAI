from __future__ import annotations

import logging
from pathlib import Path

from crewai.knowledge.source.json_knowledge_source import JSONKnowledgeSource  # type: ignore

log = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "knowledge"


# Public helpers


def get_company_knowledge_source() -> JSONKnowledgeSource:
    """Build a CrewAI KnowledgeSource from the company profile JSON."""
    path = _KNOWLEDGE_DIR / "company_profile.json"
    if not path.exists():
        raise FileNotFoundError(f"Knowledge source not found: {path}. " "Create knowledge/company_profile.json based on the template.")
    log.info("Registering knowledge source: %s", path)
    return JSONKnowledgeSource(file_path=str(path))


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
