from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv
from crewai import LLM  # type: ignore

load_dotenv()

_PROVIDER_BASE_URL = os.getenv("PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
_API_KEY = os.getenv("API_KEY", "your_api_key_here")

# TODO: Choose a reasoing-heavy model
_MAIN_MODEL = os.getenv("MAIN_MODEL", "openrouter/free")
_MAIN_TEMPERATURE = float(os.getenv("MAIN_TEMPERATURE", "0.3"))
_MAIN_MAX_TOKENS = int(os.getenv("MAIN_MAX_TOKENS", "4096"))

# TODO: Choose a lightweight model for the parallel agents
_FAST_MODEL = os.getenv("FAST_MODEL", "openrouter/free")
_FAST_TEMPERATURE = float(os.getenv("FAST_TEMPERATURE", "0.3"))
_FAST_MAX_TOKENS = int(os.getenv("FAST_MAX_TOKENS", "4096"))


def get_llm(fast: bool = False) -> LLM:
    """
    Returns a CrewAI LLm object pointing at Provider.

    Args:
        fast (bool): If True, returns a lightweight model for parallel agents.
                     If False, returns a reasoning-heavy model for the main agent.
    """
    return LLM(
        model=_FAST_MODEL if fast else _MAIN_MODEL,
        api_key=_API_KEY,
        base_url=_PROVIDER_BASE_URL,
        temperature=_FAST_TEMPERATURE if fast else _MAIN_TEMPERATURE,
        max_tokens=_FAST_MAX_TOKENS if fast else _MAIN_MAX_TOKENS,
    )


# TODO: move this to a separate file so its easier to modify without affecting the main agent code
BANDI_PORTALS: list[dict] = [
    {
        "name": "ANAC / Simog",
        "base_url": "https://www.anticorruzione.it/-/bandi-di-gara",
        "reliability": 1.00,
        "country_filter": None,
    },
    {
        "name": "TED (EU)",
        "base_url": "https://www.ted.europa.eu/en/search/result",
        "reliability": 0.90,
        "country_filter": "IT",
    },
    {
        "name": "MePA",
        "base_url": "https://www.acquistinretepa.it/opencms/opencms/main/pa/",
        "reliability": 0.85,
        "country_filter": None,
    },
    {
        "name": "Sardegna CAT",
        "base_url": "https://www.sardegacat.it/eprocurement/createWorkspace.do",
        "reliability": 0.75,
        "country_filter": None,
    },
]

PORTAL_WEIGHTS: dict[str, float] = {p["name"]: p["reliability"] for p in BANDI_PORTALS}
_DEFAULT_PORTAL_WEIGHT = float(os.getenv("DEFAULT_PORTAL_WEIGHT", "0.5"))

if _DEFAULT_PORTAL_WEIGHT < 0.0 or _DEFAULT_PORTAL_WEIGHT > 1.0:
    _DEFAULT_PORTAL_WEIGHT = 0.5


def portal_weight(portal_name: str) -> float:
    return PORTAL_WEIGHTS.get(portal_name, _DEFAULT_PORTAL_WEIGHT)


_MAX_REVIEW_ITERATIONS = int(os.getenv("MAX_REVIEW_ITERATIONS", "5"))  # to prevent infinite loops in the review process
IMPLICIT_NO_GO_KEYWORDS = [
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
    # English (in case)
    "we don't have",
    "we can't",
    "impossible",
    "give up",
    "stop",
    "quit",
]


@dataclass
class CompanyProfile:
    name: str = "BandAI"
    vat_number: str = "IT12345678901"
    ateco_codes: list[str] = field(default_factory=lambda: ["62.01.09", "62.02.00"])
    certifications: list[str] = field(default_factory=lambda: ["ISO 9001:2015", "ISO 27001:2022", "ISO 20000-1:2018", "AgID Qualification Cloud (IaaS/PaaS)"])
    turnover_last_3y_eur: list[float] = field(default_factory=lambda: [2_100_000.0, 2_450_000.0, 2_800_000.0])
    employees: int = 28
    departments: list[str] = field(default_factory=lambda: ["Cloud Infrastructure", "Cybersecurity", "Software Development", "Customer Support & SLA Management", "Project Management Office"])
    past_public_contracts: list[dict] = field(
        default_factory=lambda: [
            {
                "title": "AI Consulting for Public Sector",
                "value_eur": 150_000.0,
                "cpv_codes": ["72000000"],
                "year": 2022,
                "authority": "Comune di Milano",
                "topics": ["AI consulting", "public sector"],
            },
            {
                "title": "Data Analysis for Municipal Services",
                "value_eur": 80_000.0,
                "cpv_codes": ["72200000"],
                "year": 2021,
                "authority": "Comune di Milano",
                "topics": ["data analysis", "public services"],
            },
        ]
    )
    max_bid_value_eur: float = 1_500_000.0

    @property
    def knowledge_file(self) -> str:
        """Path to the knowledge base file (relative to the project root)"""
        return f"knowledge/{self.name.replace(' ', '_').lower()}_profile.json"


COMPANY = CompanyProfile()
