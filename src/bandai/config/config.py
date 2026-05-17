from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_CFG = Path(__file__).parent


# Provider Profile Models


class LLMProfile(BaseModel):
    """Configuration for a single LLM model slot (main or fast)."""

    model: str
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=131072)


class ProviderProfile(BaseModel):
    """Configuration for a complete LLM provider."""

    name: str
    description: str = ""
    base_url: str
    main: LLMProfile
    fast: LLMProfile
    env_key: str = "API_KEY"

    @property
    def main_model(self) -> str:
        """Full model identifier in provider/model format."""
        return f"{self.name}/{self.main.model}"

    @property
    def fast_model(self) -> str:
        """Full model identifier in provider/model format."""
        return f"{self.name}/{self.fast.model}"


# Built-in Provider Profiles

PROVIDERS: dict[str, ProviderProfile] = {
    "openrouter": ProviderProfile(
        name="openrouter",
        description="OpenRouter - multi-provider routing (supports OpenAI, Anthropic, Google, etc.)",
        base_url="https://openrouter.ai/api/v1",
        main=LLMProfile(model="anthropic/claude-sonnet-4-20250514", temperature=0.3, max_tokens=4096),
        fast=LLMProfile(model="openai/gpt-4o-mini", temperature=0.3, max_tokens=4096),
        env_key="OPENROUTER_API_KEY",
    ),
    "anthropic": ProviderProfile(
        name="anthropic",
        description="Anthropic - direct API access",
        base_url="https://api.anthropic.com/v1",
        main=LLMProfile(model="claude-sonnet-4-20250514", temperature=0.3, max_tokens=4096),
        fast=LLMProfile(model="claude-haiku-3-5-20241022", temperature=0.3, max_tokens=4096),
        env_key="ANTHROPIC_API_KEY",
    ),
    "openai": ProviderProfile(
        name="openai",
        description="OpenAI - direct API access",
        base_url="https://api.openai.com/v1",
        main=LLMProfile(model="gpt-4o", temperature=0.3, max_tokens=4096),
        fast=LLMProfile(model="gpt-4o-mini", temperature=0.3, max_tokens=4096),
        env_key="OPENAI_API_KEY",
    ),
    "ollama": ProviderProfile(
        name="ollama",
        description="Ollama - local LLM server",
        base_url="http://localhost:11434/v1",
        main=LLMProfile(model="llama3", temperature=0.3, max_tokens=4096),
        fast=LLMProfile(model="llama3", temperature=0.3, max_tokens=4096),
        env_key="",
    ),
}


# Active Configuration


def get_active_provider() -> ProviderProfile:
    """Return the active provider profile based on LLM_PROVIDER env var."""
    provider_name = os.getenv("LLM_PROVIDER", "openrouter")
    if provider_name not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        raise ValueError(f"Unknown LLM_PROVIDER '{provider_name}'. " f"Available providers: {available}")
    return PROVIDERS[provider_name]


def get_api_key() -> str:
    """Return the API key for the active provider."""
    provider = get_active_provider()

    # Provider-specific key takes priority
    if provider.env_key:
        key = os.getenv(provider.env_key, "")
        if key and key != f"your_{provider.env_key.lower()}_here":
            return key

    # Generic fallback
    key = os.getenv("API_KEY", "")
    if key and key != "your_api_key_here":
        return key

    available_msg = ""
    if provider.env_key:
        available_msg = f" Set {provider.env_key} or API_KEY in your .env file."
    else:
        available_msg = " No API key required for this provider."

    raise ValueError(f"No API key configured for provider '{provider.name}'.{available_msg}")


def get_llm(fast: bool = False) -> "LLM":  # type: ignore[valid-type]
    """Return a CrewAI LLM object for the active provider."""
    from crewai import LLM  # type: ignore[import]

    provider = get_active_provider()
    profile = provider.fast if fast else provider.main
    api_key = get_api_key() if provider.env_key else None

    return LLM(
        model=f"{provider.name}/{profile.model}",
        api_key=api_key,
        base_url=provider.base_url,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
    )


def validate_config() -> list[str]:
    """Validate the runtime configuration and return a list of errors."""
    errors: list[str] = []

    # Check provider
    provider_name = os.getenv("LLM_PROVIDER", "openrouter")
    if provider_name not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        errors.append(f"[LLM_PROVIDER] Unknown provider '{provider_name}'. " f"Available: {available}")
        return errors  # can't continue without a valid provider

    # Check API key
    provider = PROVIDERS[provider_name]
    if provider.env_key:
        key = os.getenv(provider.env_key, "")
        generic_key = os.getenv("API_KEY", "")
        if (not key or key == f"your_{provider.env_key.lower()}_here") and (not generic_key or generic_key == "your_api_key_here"):
            errors.append(f"[{provider.env_key}] No API key set. " f"Set {provider.env_key} or API_KEY in your .env file.")

    # Check knowledge file (project_root/knowledge/company_profile.json)
    knowledge_path = Path(__file__).parent.parent.parent.parent / "knowledge" / "company_profile.json"
    if not knowledge_path.exists():
        errors.append(f"[knowledge] Company profile not found at {knowledge_path}. " "Create it based on the template.")

    # Check portals config
    portals_path = Path(__file__).parent / "portals.yaml"
    if not portals_path.exists():
        errors.append(f"[portals] Portal config not found at {portals_path}. " "The project requires at least one portal definition.")

    return errors


# Review Loop Limits
_MAX_REVIEW_ITERATIONS = int(os.getenv("MAX_REVIEW_ITERATIONS", "5"))

# Implicit NO-GO Keywords
IMPLICIT_NO_GO_KEYWORDS: list[str] = [
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
