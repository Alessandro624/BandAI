from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from bandai.knowledge_sources import get_company_knowledge_data

log = logging.getLogger(__name__)


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
    """
    Complete company procurement profile, loaded from knowledge/.

    This is the single source of truth for company data used across
    all crews.  Fields are validated by Pydantic on load.
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


# Loaders


def parse_company_profile(data: dict[str, Any]) -> CompanyProfile:
    """Validate raw dict data into a CompanyProfile."""
    try:
        return CompanyProfile.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Invalid company profile data: {exc}") from exc


@lru_cache(maxsize=1)
def load_company_profile() -> CompanyProfile:
    """
    Load, validate, and cache the company profile from disk.

    The result is cached for the lifetime of the process so that
    repeated calls across crew builds do not re-read or re-validate
    the same file.
    """
    data = get_company_knowledge_data()

    try:
        profile = CompanyProfile.model_validate(data)
        log.info(
            "Loaded company profile: %s (%d departments, %d past contracts)",
            profile.name,
            len(profile.departments),
            len(profile.past_public_contracts),
        )
        return profile
    except Exception as exc:
        raise ValueError(f"Invalid company profile data: {exc}") from exc


def clear_profile_cache() -> None:
    """Clear the cached company profile. Useful in tests."""
    load_company_profile.cache_clear()
