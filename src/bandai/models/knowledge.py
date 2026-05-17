from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

log = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "knowledge"


# Knowledge Models


class PastContract(BaseModel):
    """A previously completed public contract reference."""

    title: str
    value_eur: float
    cpv_codes: list[str]
    year: int
    authority: str
    topics: list[str]


class DepartmentProfile(BaseModel):
    """Capabilities, evidence, and KPIs for a single company department."""

    capabilities: list[str]
    certifications: list[str]
    case_studies: list[str]
    kpis: dict[str, Any]


class CompanyProfile(BaseModel):
    """Complete company procurement profile, loaded from knowledge/.

    This is the single source of truth for company data used across all crews.
    """

    name: str
    vat_number: str
    ateco_codes: list[str]
    certifications: list[str]
    turnover_last_3y_eur: list[float]
    employees: int
    max_bid_value_eur: float
    past_public_contracts: list[PastContract]
    departments: dict[str, DepartmentProfile]

    @property
    def department_names(self) -> list[str]:
        """Return the list of department names."""
        return list(self.departments.keys())


def load_company_profile(path: Path | None = None) -> CompanyProfile:
    """Load the company profile from the knowledge directory."""
    if path is None:
        path = _KNOWLEDGE_DIR / "company_profile.json"

    if not path.exists():
        raise FileNotFoundError(f"Company profile not found at {path}. " "Create knowledge/company_profile.json based on the provided template.")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        profile = CompanyProfile.model_validate(data)
        log.info(
            "Loaded company profile: %s (%d departments, %d past contracts)",
            profile.name,
            len(profile.departments),
            len(profile.past_public_contracts),
        )
        return profile
    except Exception as e:
        raise ValueError(f"Invalid company profile in {path}: {e}") from e
