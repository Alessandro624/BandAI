from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

_mod_ec = types.ModuleType("crewai.rag.embeddings.providers.custom.embedding_callable")


class _MockEmbeddingFunction:
    pass


_mod_ec.CustomEmbeddingFunction = _MockEmbeddingFunction
sys.modules.setdefault(
    "crewai.rag.embeddings.providers.custom",
    types.ModuleType("crewai.rag.embeddings.providers.custom"),
)
sys.modules["crewai.rag.embeddings.providers.custom.embedding_callable"] = _mod_ec

_mod_cp = types.ModuleType("crewai.rag.embeddings.providers.custom.custom_provider")


class _MockCustomProvider:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mod_cp.CustomProvider = _MockCustomProvider
sys.modules["crewai.rag.embeddings.providers.custom.custom_provider"] = _mod_cp


_mock_memory_module = types.ModuleType("crewai.memory.unified_memory")


class _FakeMemory:
    def __init__(self, llm=None, embedder=None):
        self.llm = llm
        self.embedder = embedder


_mock_memory_module.Memory = _FakeMemory
sys.modules["crewai.memory"] = types.ModuleType("crewai.memory")
sys.modules["crewai.memory.unified_memory"] = _mock_memory_module


class TestGetMemoryDisabled:
    """When DISABLE_MEMORY is set to a truthy value, returns False."""

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "Yes", "YES"])
    def test_returns_false(self, value: str) -> None:
        from bandai.config.memory import get_memory

        with patch.dict("os.environ", {"DISABLE_MEMORY": value}, clear=False):
            result = get_memory()
        assert result is False


class TestGetMemoryEnabledMockedCrewAI:
    """With DISABLE_MEMORY not set, verify Memory is created with correct args."""

    def test_creates_memory_with_llm_and_embedder(self) -> None:
        from bandai.config.memory import get_memory

        fake_llm = MagicMock(name="fake-llm")
        fake_embedder = MagicMock(name="fake-embedder")

        with patch.dict("os.environ", {"DISABLE_MEMORY": "false"}, clear=False):
            with patch("bandai.config.llm.get_llm", return_value=fake_llm) as mock_get_llm:
                with patch("bandai.config.embedder.get_embedder", return_value=fake_embedder) as mock_get_embedder:
                    result = get_memory()

        assert isinstance(result, _FakeMemory)
        assert result.llm is fake_llm
        assert result.embedder is fake_embedder
        mock_get_llm.assert_called_once_with(fast=True)
        mock_get_embedder.assert_called_once()
