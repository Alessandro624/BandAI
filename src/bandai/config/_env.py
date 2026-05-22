from __future__ import annotations

import os

from pydantic import BaseModel, Field

from bandai.config._constants import PROVIDERS, ProviderProfile  # noqa: E402

# Environment Override Model


class EnvOverrides(BaseModel):
    """Parsed LLM environment variable overrides."""

    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)

    @classmethod
    def from_env(cls, prefix: str) -> EnvOverrides:
        """Read overrides for prefix (MAIN_ or FAST_)."""

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
