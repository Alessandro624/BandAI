from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from bandai.utils import KNOWLEDGE_DIR, NO_GO_KEYWORDS, PROJECT_ROOT

if TYPE_CHECKING:
    from crewai.llms.base_llm import BaseLLM  # type: ignore

log = logging.getLogger(__name__)
logging.getLogger("opentelemetry.attributes").setLevel(logging.ERROR)


# Environment Override Model


class EnvOverrides(BaseModel):
    """Parsed LLM environment variable overrides."""

    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)

    @classmethod
    def from_env(cls, prefix: str) -> EnvOverrides:
        """Read overrides for *prefix* (MAIN_ or FAST_)."""

        def _float(key: str) -> float | None:
            raw = os.getenv(key)
            if raw is None:
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        def _int(key: str) -> int | None:
            raw = os.getenv(key)
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        return cls(
            model=os.getenv(f"{prefix}MODEL") or None,
            temperature=_float(f"{prefix}TEMPERATURE"),
            max_tokens=_int(f"{prefix}MAX_TOKENS"),
        )


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
        if "/" in self.main.model:
            return self.main.model
        return f"{self.name}/{self.main.model}"

    @property
    def fast_model(self) -> str:
        """Full model identifier in provider/model format."""
        if "/" in self.fast.model:
            return self.fast.model
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


@lru_cache(maxsize=4)
def get_llm(fast: bool = False) -> BaseLLM:  # type: ignore[valid-type]
    """Return a cached CrewAI LLM object for the active provider.

    The same (fast, provider, env-state) combination returns the
    identical LLM instance, avoiding redundant object creation
    across multiple crew builds in a single pipeline run.
    """
    from crewai import LLM  # type: ignore

    provider = get_active_provider()

    # Allow overriding base URL via env var (useful for local servers)
    base_url = os.getenv("PROVIDER_BASE_URL", provider.base_url)

    # Start from provider profile, then apply optional env overrides
    profile = provider.fast if fast else provider.main
    overrides = EnvOverrides.from_env("FAST_" if fast else "MAIN_")

    profile_model = overrides.model or profile.model
    profile_temperature = overrides.temperature if overrides.temperature is not None else profile.temperature
    profile_max = overrides.max_tokens if overrides.max_tokens is not None else profile.max_tokens

    api_key = get_api_key() if provider.env_key else None

    # If profile_model already contains provider prefix, use it; otherwise combine with provider.name
    model_id = profile_model if "/" in profile_model else f"{provider.name}/{profile_model}"

    return LLM(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        temperature=profile_temperature,
        max_tokens=profile_max,
    )


@lru_cache(maxsize=1)
def get_embedder() -> dict | None:
    """Return a cached embedder configuration dict for Crew(embedder=...)."""
    provider = os.getenv("EMBEDDER_PROVIDER")
    if not provider:
        return None

    model = os.getenv("EMBEDDER_MODEL", "")
    base_url = os.getenv("EMBEDDER_BASE_URL", "")
    api_key = os.getenv("EMBEDDER_API_KEY", "")

    # If model is empty, fall back to sensible defaults per provider
    if not model:
        if provider == "ollama":
            model = "nomic-embed-text:latest"
        elif provider == "openai":
            model = "text-embedding-3-large"
        else:
            model = "default-embed-model"

    embedder: dict = {"provider": provider, "config": {"model_name": model}}
    if base_url:
        embedder["config"]["url"] = base_url
    if api_key:
        embedder["config"]["api_key"] = api_key

    return embedder


def get_memory() -> "Memory | bool":  # type: ignore[valid-type]:
    """
    Return a CrewAI Memory object wired to the active provider.

    Memory objects are intentionally not cached: each crew should
    receive its own independent Memory instance so that context
    isolation is preserved across pipeline phases.
    """
    if os.getenv("DISABLE_MEMORY", "false").lower() in ("1", "true", "yes"):
        return False  # type: ignore[return-value]

    from crewai.memory.unified_memory import Memory  # type: ignore

    # Memory uses the fast model for its analysis LLM (scope inference,
    # importance scoring, consolidation).  The model ID must match
    # whatever the active provider expects.
    memory_llm = get_llm(fast=True)

    return Memory(
        llm=memory_llm,
        embedder=get_embedder(),
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

    knowledge_path = KNOWLEDGE_DIR / "company_profile.json"
    if not knowledge_path.exists():
        errors.append(f"[knowledge] Company profile not found at {knowledge_path}. " "Create it based on the template.")

    from bandai.utils import CONFIG_DIR

    portals_path = CONFIG_DIR / "portals.yaml"
    if not portals_path.exists():
        errors.append(f"[portals] Portal config not found at {portals_path}. " "The project requires at least one portal definition.")

    return errors


# Review Loop Limits

_MAX_REVIEW_ITERATIONS = int(os.getenv("MAX_REVIEW_ITERATIONS", "5"))

# Cache Management (testing)


def clear_caches() -> None:
    """Clear all LLM/embedder caches. Useful in tests."""
    get_llm.cache_clear()
    get_embedder.cache_clear()
