from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import numpy as np
import requests

log = logging.getLogger(__name__)


# OpenRouter Embedding Function

from crewai.rag.embeddings.providers.custom.embedding_callable import CustomEmbeddingFunction  # type: ignore

# Model name fragments that indicate a multimodal (vision-language)
# embedding model. These models expect the content array input
# format instead of plain text strings.
_VL_MODEL_KEYWORDS = ("vl", "vision", "vila", "nemo-vl")


class OpenRouterEmbeddingFunction(CustomEmbeddingFunction):
    """
    Custom embedding callable for OpenRouter API.

    Uses requests directly instead of the openai SDK so we
    have full control over the request format.  This matters for
    multimodal embedding models (e.g. nvidia/llama-nemotron-embed-vl)
    that expect a content array structure rather than plain text
    strings.

    The __call__ signature matches the protocol expected by both
    ChromaDB (EmbeddingFunction) and CrewAI (CustomProvider
    via build_embedder_from_provider).

    Instantiation kwargs come from provider.model_dump(exclude={
    "embedding_callable"}), so every field on the provider (except
    embedding_callable) must be accepted by __init__.
    """

    def __init__(
        self,
        model_name: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free",
        api_key: str | None = None,
        api_base: str = "https://openrouter.ai/api/v1",
        **_kwargs: Any,
    ) -> None:
        self._model = model_name
        self._api_base = api_base.rstrip("/")
        self._headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }
        self._is_vl = any(kw in model_name.lower() for kw in _VL_MODEL_KEYWORDS)
        log.info(
            "OpenRouter embedder: model=%s, vl=%s, endpoint=%s/embeddings",
            model_name,
            self._is_vl,
            self._api_base,
        )

    @staticmethod
    def name() -> str:
        """ChromaDB calls this to identify the embedding function."""
        return "openrouter"

    def _build_input(self, texts: list[str]) -> Any:
        """
        Wrap plain text into the format expected by the model.

        Vision-language models need a content array with typed
        entries.  Standard text models accept a plain list of strings.
        """
        if not self._is_vl:
            return texts

        # Multimodal format: each document is a dict with a content array.
        return [{"content": [{"type": "text", "text": t}]} for t in texts]

    def __call__(self, input: list[str]) -> list[np.ndarray]:
        """
        Generate embeddings for a list of text documents.

        Args:
            input: List of text strings to embed.

        Returns:
            List of float32 numpy arrays, one per input document.
        """
        if not input:
            return []

        payload: dict[str, Any] = {
            "model": self._model,
            "input": self._build_input(input),
            "encoding_format": "float",
        }

        resp = requests.post(
            f"{self._api_base}/embeddings",
            headers=self._headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()

        data = body.get("data")
        if not data:
            raise ValueError(f"OpenRouter returned no embedding data for model " f"{self._model}. Response: {body}")

        embeddings = [np.array(item["embedding"], dtype=np.float32) for item in data]
        log.info(
            "OpenRouter embeddings: %d docs, dim=%d, model=%s",
            len(embeddings),
            len(embeddings[0]) if embeddings else 0,
            self._model,
        )
        return embeddings


# Embedder Factory


@lru_cache(maxsize=1)
def get_embedder():
    """
    Return a cached embedder for Crew(embedder=...) and Memory().

    OpenRouter: returns a CustomProvider wired to
    OpenRouterEmbeddingFunction.  This callable uses requests
    directly (no openai SDK) and auto-detects vision-language models
    to wrap input in the content array format they require.

    Other providers (ollama, openai native, etc.): returns a dict
    following the {"provider": ..., "config": ...} spec.

    Important: if you switch from one embedder to another (e.g.
    ollama to openrouter), you must reset the persisted ChromaDB
    collections before running.  Run crewai reset-memories -a or
    delete the storage directory returned by
    crewai_core.paths.db_storage_path().
    """
    from crewai.rag.embeddings.providers.custom.custom_provider import CustomProvider  # type: ignore

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
        elif provider == "openrouter":
            model = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
        else:
            model = "default-embed-model"

    if provider == "openrouter":
        base_url = base_url or "https://openrouter.ai/api/v1"
        api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")

        return CustomProvider(
            embedding_callable=OpenRouterEmbeddingFunction,
            model_name=model,
            api_key=api_key or None,
            api_base=base_url or None,
        )

    # OpenAI native and other providers use the standard dict path.
    embedder: dict = {"provider": provider, "config": {"model_name": model}}
    if base_url:
        embedder["config"]["url"] = base_url
    if api_key:
        embedder["config"]["api_key"] = api_key

    return embedder
