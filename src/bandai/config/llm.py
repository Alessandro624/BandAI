from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crewai.llms.base_llm import BaseLLM  # type: ignore

from bandai.config._env import EnvOverrides, get_active_provider, get_api_key  # noqa: E402

# LLM Factory


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
    model_id = profile_model if f"{provider.name}/" in profile_model else f"{provider.name}/{profile_model}"

    return LLM(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        temperature=profile_temperature,
        max_tokens=profile_max,
    )
