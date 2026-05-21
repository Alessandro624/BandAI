from __future__ import annotations

import os

from bandai.utils import KNOWLEDGE_DIR  # noqa: E402
from bandai.config._constants import PROVIDERS  # noqa: E402


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
