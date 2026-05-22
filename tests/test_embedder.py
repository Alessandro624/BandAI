from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Mock: crewai.rag.embeddings.providers.custom.embedding_callable
_mod_ec = types.ModuleType("crewai.rag.embeddings.providers.custom.embedding_callable")


class _MockEmbeddingFunction:
    pass


_mod_ec.CustomEmbeddingFunction = _MockEmbeddingFunction
sys.modules.setdefault(
    "crewai.rag.embeddings.providers.custom",
    types.ModuleType("crewai.rag.embeddings.providers.custom"),
)
sys.modules["crewai.rag.embeddings.providers.custom.embedding_callable"] = _mod_ec

# Mock: crewai.rag.embeddings.providers.custom.custom_provider
_mod_cp = types.ModuleType("crewai.rag.embeddings.providers.custom.custom_provider")


class _MockCustomProvider:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mod_cp.CustomProvider = _MockCustomProvider
sys.modules["crewai.rag.embeddings.providers.custom.custom_provider"] = _mod_cp

from bandai.config.embedder import OpenRouterEmbeddingFunction  # noqa: E402


class TestVLModelDetection:
    """Verify that model names containing vision-language keywords are flagged."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "nvidia/llama-nemotron-embed-vl-1b-v2:free",
            "some-vl-model",
            "openai/vision-embed",
            "nemo-vl-large",
            "vila-v2",
        ],
    )
    def test_vl_keywords_detected(self, model_name: str) -> None:
        emb = OpenRouterEmbeddingFunction(model_name=model_name)
        assert emb._is_vl is True

    @pytest.mark.parametrize(
        "model_name",
        [
            "text-embedding-3-large",
            "nomic-embed-text:latest",
            "bge-large-en-v1.5",
            "sentence-transformers/all-MiniLM-L6-v2",
        ],
    )
    def test_non_vl_keywords_not_detected(self, model_name: str) -> None:
        emb = OpenRouterEmbeddingFunction(model_name=model_name)
        assert emb._is_vl is False


class TestBuildInputVL:
    """Verify _build_input wraps text in content array format for VL models."""

    def test_wraps_texts(self) -> None:
        emb = OpenRouterEmbeddingFunction(model_name="nvidia/llama-nemotron-embed-vl-1b-v2:free")
        result = emb._build_input(["hello", "world"])
        assert isinstance(result, list)
        assert len(result) == 2
        assert "content" in result[0]
        assert isinstance(result[0]["content"], list)
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][0]["text"] == "hello"


class TestBuildInputNonVL:
    """Verify _build_input returns plain list for non-VL models."""

    def test_plain_list(self) -> None:
        emb = OpenRouterEmbeddingFunction(model_name="text-embedding-3-large")
        texts = ["hello", "world"]
        result = emb._build_input(texts)
        assert result is texts  # Should return the same list object
        assert result == ["hello", "world"]


class TestName:
    """Verify the static name() identifier."""

    def test_returns_openrouter(self) -> None:
        assert OpenRouterEmbeddingFunction.name() == "openrouter"


class TestCallEmptyInput:
    """Verify __call__ returns [] for empty input."""

    def test_empty_list(self) -> None:
        emb = OpenRouterEmbeddingFunction()
        result = emb([])
        assert result == []


class TestCallSuccess:
    """Verify successful embedding call returns list of np.ndarray."""

    @patch("bandai.config.embedder.requests.post")
    def test_returns_ndarray_list(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3]},
                {"embedding": [0.4, 0.5, 0.6]},
            ]
        }
        mock_post.return_value = mock_response

        emb = OpenRouterEmbeddingFunction(model_name="test/model", api_key="sk-test")
        result = emb(["hello", "world"])

        assert len(result) == 2
        assert isinstance(result[0], np.ndarray)
        assert result[0].dtype == np.float32
        np.testing.assert_array_almost_equal(result[0], np.array([0.1, 0.2, 0.3], dtype=np.float32))
        np.testing.assert_array_almost_equal(result[1], np.array([0.4, 0.5, 0.6], dtype=np.float32))

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "/embeddings" in call_kwargs[0][0]


class TestCallNoDataError:
    """Verify ValueError is raised when API returns no embedding data."""

    @patch("bandai.config.embedder.requests.post")
    def test_raises_value_error(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_post.return_value = mock_response

        emb = OpenRouterEmbeddingFunction(model_name="test/model", api_key="sk-test")
        with pytest.raises(ValueError, match="no embedding data"):
            emb(["hello"])


class TestGetEmbedderNoProvider:
    """When EMBEDDER_PROVIDER is not set, returns None."""

    def test_returns_none(self) -> None:
        from bandai.config.embedder import get_embedder

        get_embedder.cache_clear()
        with patch.dict("os.environ", {"EMBEDDER_PROVIDER": ""}, clear=False):
            # Need to remove the env var entirely for the code path
            with patch("bandai.config.embedder.os.getenv", return_value=None):
                result = get_embedder()
        assert result is None
        get_embedder.cache_clear()


class TestGetEmbedderOpenRouter:
    """When EMBEDDER_PROVIDER=openrouter, returns a CustomProvider-like object."""

    def test_returns_custom_provider_object(self) -> None:
        from bandai.config.embedder import get_embedder

        get_embedder.cache_clear()
        env = {
            "EMBEDDER_PROVIDER": "openrouter",
            "EMBEDDER_MODEL": "test/vl-model",
            "EMBEDDER_API_KEY": "sk-test",
            "OPENROUTER_API_KEY": "sk-test",
        }
        with patch.dict("os.environ", env, clear=False):
            result = get_embedder()

        assert result is not None
        assert hasattr(result, "embedding_callable")
        assert result.embedding_callable is OpenRouterEmbeddingFunction
        assert result.model_name == "test/vl-model"
        get_embedder.cache_clear()


class TestGetEmbedderOllama:
    """When EMBEDDER_PROVIDER=ollama, returns a dict with correct structure."""

    def test_returns_dict(self) -> None:
        from bandai.config.embedder import get_embedder

        get_embedder.cache_clear()
        env = {
            "EMBEDDER_PROVIDER": "ollama",
            "EMBEDDER_MODEL": "nomic-embed-text:latest",
            "EMBEDDER_BASE_URL": "http://localhost:11434",
        }
        with patch.dict("os.environ", env, clear=False):
            result = get_embedder()

        assert isinstance(result, dict)
        assert result["provider"] == "ollama"
        assert result["config"]["model_name"] == "nomic-embed-text:latest"
        assert result["config"]["url"] == "http://localhost:11434"
        get_embedder.cache_clear()
