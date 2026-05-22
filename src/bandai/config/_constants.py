from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)
logging.getLogger("opentelemetry.attributes").setLevel(logging.ERROR)


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
        if f"{self.name}/" in self.main.model:
            return self.main.model
        return f"{self.name}/{self.main.model}"

    @property
    def fast_model(self) -> str:
        """Full model identifier in provider/model format."""
        if f"{self.name}/" in self.fast.model:
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


# Review Loop Limits

_MAX_REVIEW_ITERATIONS = int(os.getenv("MAX_REVIEW_ITERATIONS", "5"))


# Cache Management (testing)


def clear_caches() -> None:
    """Clear all LLM/embedder caches.  Useful in tests."""
    from bandai.config.llm import get_llm  # noqa: E402
    from bandai.config.embedder import get_embedder  # noqa: E402

    get_llm.cache_clear()
    get_embedder.cache_clear()
