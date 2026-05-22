from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

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

# Mock: crewai.knowledge.source.string_knowledge_source.StringKnowledgeSource
# knowledge_sources.py imports this at module level.
_mod_sks = types.ModuleType("crewai.knowledge.source.string_knowledge_source")


class _MockStringKnowledgeSource:
    def __init__(self, *args, **kwargs):
        self.content = kwargs.get("content", "")

    # Allow in checks on the content string
    def __contains__(self, item):
        return item in self.content if isinstance(self.content, str) else False


_mod_sks.StringKnowledgeSource = _MockStringKnowledgeSource
sys.modules.setdefault("crewai.knowledge.source", types.ModuleType("crewai.knowledge.source"))
sys.modules["crewai.knowledge.source.string_knowledge_source"] = _mod_sks
sys.modules.setdefault("crewai.knowledge", types.ModuleType("crewai.knowledge"))
sys.modules["crewai.knowledge"].source = sys.modules["crewai.knowledge.source"]
if "crewai" in sys.modules:
    sys.modules["crewai"].knowledge = sys.modules["crewai.knowledge"]

# Knowledge model tests


class TestKnowledgeModels:
    """Tests for CompanyProfile, DepartmentProfile, and PastContract models."""

    def test_valid_company_profile(self) -> None:
        from bandai.models.knowledge import CompanyProfile

        data = {
            "name": "TestCo",
            "vat_number": "IT00000000000",
            "ateco_codes": ["62.01.09"],
            "certifications": ["ISO 9001:2015"],
            "turnover_last_3y_eur": [1000000.0, 1200000.0],
            "employees": 10,
            "max_bid_value_eur": 500000.0,
            "past_public_contracts": [
                {
                    "title": "Test Contract",
                    "value_eur": 50000.0,
                    "cpv_codes": ["72000000"],
                    "year": 2023,
                    "authority": "Comune di Test",
                    "topics": ["test"],
                }
            ],
            "departments": {
                "Engineering": {
                    "capabilities": ["Software dev"],
                    "certifications": ["ISO 9001"],
                    "case_studies": [],
                    "kpis": {"on_time": 95},
                }
            },
        }
        profile = CompanyProfile.model_validate(data)
        assert profile.name == "TestCo"
        assert len(profile.departments) == 1
        assert len(profile.past_public_contracts) == 1
        assert profile.department_names == ["Engineering"]

    def test_company_profile_missing_required_field(self) -> None:
        from pydantic import ValidationError
        from bandai.models.knowledge import CompanyProfile

        with pytest.raises(ValidationError):
            CompanyProfile.model_validate({"name": "TestCo"})

    def test_parse_company_profile_from_dict(self) -> None:
        """parse_company_profile accepts a dict of company data."""
        from bandai.models.knowledge import parse_company_profile

        data = {
            "name": "FileCo",
            "vat_number": "IT11111111111",
            "ateco_codes": ["62.01.09"],
            "certifications": [],
            "turnover_last_3y_eur": [500000.0],
            "employees": 5,
            "max_bid_value_eur": 200000.0,
            "past_public_contracts": [],
            "departments": {},
        }
        profile = parse_company_profile(data)
        assert profile.name == "FileCo"
        assert profile.employees == 5

    def test_load_company_profile_default_uses_file(self) -> None:
        """load_company_profile() loads from the knowledge JSON file."""
        from bandai.models.knowledge import load_company_profile

        profile = load_company_profile()
        assert profile.name
        assert isinstance(profile.ateco_codes, list)

    def test_parse_company_profile_invalid_data(self) -> None:
        """parse_company_profile raises ValueError on invalid data."""
        from bandai.models.knowledge import parse_company_profile

        with pytest.raises(ValueError, match="Invalid company profile data"):
            parse_company_profile({"name": "TestCo"})

    def test_load_company_profile_missing_file(self) -> None:
        """load_company_profile() raises FileNotFoundError if JSON missing."""
        from bandai.models.knowledge import load_company_profile, clear_profile_cache
        from unittest.mock import patch as mock_patch

        clear_profile_cache()
        with mock_patch(
            "bandai.knowledge_sources._COMPANY_PROFILE_PATH",
            Path("/nonexistent/knowledge/company_profile.json"),
        ):
            with pytest.raises(FileNotFoundError, match="Knowledge source not found"):
                load_company_profile()
        clear_profile_cache()


# Provider config tests


class TestProviderConfig:
    """Tests for multi-provider LLM configuration."""

    def setup_method(self) -> None:
        """Clear LLM caches before each test."""
        from bandai.config import clear_caches

        clear_caches()

    def test_builtin_providers_exist(self) -> None:
        from bandai.config import PROVIDERS

        assert "openrouter" in PROVIDERS
        assert "anthropic" in PROVIDERS
        assert "openai" in PROVIDERS
        assert "ollama" in PROVIDERS
        assert len(PROVIDERS) >= 4

    def test_provider_profile_structure(self) -> None:
        from bandai.config import ProviderProfile, LLMProfile

        provider = ProviderProfile(
            name="test",
            base_url="https://test.example.com/v1",
            main=LLMProfile(model="large", temperature=0.5, max_tokens=2048),
            fast=LLMProfile(model="small", temperature=0.3, max_tokens=1024),
        )
        assert provider.main_model == "test/large"
        assert provider.fast_model == "test/small"
        assert provider.env_key == "API_KEY"

    def test_llm_profile_temperature_bounds(self) -> None:
        from pydantic import ValidationError
        from bandai.config import LLMProfile

        with pytest.raises(ValidationError):
            LLMProfile(model="test", temperature=5.0)

        with pytest.raises(ValidationError):
            LLMProfile(model="test", temperature=-1.0)

    def test_get_active_provider_default(self) -> None:
        from bandai.config import get_active_provider, clear_caches

        clear_caches()
        with patch.dict(os.environ, {"LLM_PROVIDER": ""}, clear=False):
            with patch.dict(os.environ, {"LLM_PROVIDER": "openrouter"}):
                provider = get_active_provider()
                assert provider.name == "openrouter"

    def test_get_active_provider_custom(self) -> None:
        from bandai.config import get_active_provider, clear_caches

        clear_caches()
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
            provider = get_active_provider()
            assert provider.name == "ollama"

    def test_get_active_provider_unknown(self) -> None:
        from bandai.config import get_active_provider, clear_caches

        clear_caches()
        with patch.dict(os.environ, {"LLM_PROVIDER": "nonexistent_provider"}):
            with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
                get_active_provider()

    def test_env_overrides_model(self) -> None:
        from bandai.config import EnvOverrides, clear_caches

        clear_caches()
        with patch.dict(os.environ, {"MAIN_MODEL": "anthropic/claude-3"}):
            overrides = EnvOverrides.from_env("MAIN_")
            assert overrides.model == "anthropic/claude-3"

    def test_env_overrides_none(self) -> None:
        from bandai.config import EnvOverrides, clear_caches

        clear_caches()
        with patch.dict(os.environ, {}, clear=True):
            overrides = EnvOverrides.from_env("FAST_")
            assert overrides.model is None
            assert overrides.temperature is None


# Config validation tests


class TestConfigValidation:
    """Tests for the validate_config() startup check."""

    def test_validate_config_all_good(self) -> None:
        from bandai.config import validate_config, clear_caches

        clear_caches()
        project_root = Path(__file__).parent.parent
        knowledge_p = project_root / "knowledge" / "company_profile.json"
        portal_p = project_root / "src" / "bandai" / "config" / "portals.yaml"

        assert knowledge_p.exists(), f"Test prerequisite: {knowledge_p} must exist"
        assert portal_p.exists(), f"Test prerequisite: {portal_p} must exist"

        env = {"LLM_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "sk-test-key"}

        with patch.dict(os.environ, env, clear=False):
            errors = validate_config()
            if errors:
                for e in errors:
                    print(f"  UNEXPECTED ERROR: {e}")
            assert errors == []

    def test_validate_config_missing_api_key(self) -> None:
        from bandai.config import validate_config, clear_caches

        clear_caches()
        env = {
            "LLM_PROVIDER": "openrouter",
            "API_KEY": "your_api_key_here",
            "OPENROUTER_API_KEY": "",
        }

        with patch.dict(os.environ, env, clear=True):
            errors = validate_config()
            assert len(errors) >= 1
            assert any("API key" in e for e in errors)

    def test_validate_config_unknown_provider(self) -> None:
        from bandai.config import validate_config, clear_caches

        clear_caches()
        with patch.dict(os.environ, {"LLM_PROVIDER": "nonexistent"}):
            errors = validate_config()
            assert any("Unknown provider" in e for e in errors)


# Portal config tests


class TestPortalConfig:
    """Tests for portal YAML loading."""

    def test_portal_config_valid(self) -> None:
        from bandai.config.portals import PortalConfig

        data = {
            "name": "Test Portal",
            "base_url": "https://test.example.com",
            "reliability": 0.85,
            "country_filter": "IT",
        }
        portal = PortalConfig.model_validate(data)
        assert portal.name == "Test Portal"
        assert portal.reliability == 0.85

    def test_portal_config_reliability_bounds(self) -> None:
        from pydantic import ValidationError
        from bandai.config.portals import PortalConfig

        with pytest.raises(ValidationError):
            PortalConfig.model_validate(
                {
                    "name": "Bad",
                    "base_url": "https://x.com",
                    "reliability": 1.5,
                }
            )

    def test_portal_config_load_from_yaml(self) -> None:
        from bandai.config.portals import _load_portals

        yaml_content = {
            "portals": [
                {"name": "Portal A", "base_url": "https://a.com", "reliability": 0.9},
                {
                    "name": "Portal B",
                    "base_url": "https://b.com",
                    "reliability": 0.7,
                    "country_filter": "DE",
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(yaml_content, f)
            tmp_path = Path(f.name)

        try:
            portals = _load_portals(tmp_path)
            assert len(portals) == 2
            assert portals[0].name == "Portal A"
            assert portals[1].country_filter == "DE"
        finally:
            tmp_path.unlink()

    def test_portal_config_missing_file(self) -> None:
        from bandai.config.portals import _load_portals

        portals = _load_portals(Path("/nonexistent/portals.yaml"))
        assert portals == []

    def test_portal_weights_computed(self) -> None:
        from bandai.config.portals import portal_weight

        w = portal_weight("Nonexistent Portal")
        assert 0.0 <= w <= 1.0

    def test_validate_portals_with_data(self) -> None:
        """validate_portals() should not raise when portals are configured."""
        from bandai.config.portals import validate_portals

        # In the test environment, portals.yaml exists, so this should pass.
        validate_portals()  # Should not raise


# Pipeline model tests


class TestPipelineModels:
    """Tests for Pydantic models used in the pipeline."""

    def test_compliance_verdict_valid(self) -> None:
        from bandai.models.models import ComplianceVerdict

        v = ComplianceVerdict(
            bid_decision="GO",
            key_risks=["minor risk"],
            key_strengths=["strong team"],
            compliance_score=0.85,
            verdict_rationale="Solid match.",
        )
        assert v.bid_decision == "GO"
        assert v.conditions == []
        assert v.legal_flags == []

    def test_compliance_verdict_invalid_decision(self) -> None:
        from pydantic import ValidationError
        from bandai.models.models import ComplianceVerdict

        with pytest.raises(ValidationError):
            ComplianceVerdict(
                bid_decision="MAYBE",
                key_risks=[],
                key_strengths=[],
                compliance_score=0.5,
                verdict_rationale="test",
            )

    def test_compliance_verdict_score_bounds(self) -> None:
        from pydantic import ValidationError
        from bandai.models.models import ComplianceVerdict

        with pytest.raises(ValidationError):
            ComplianceVerdict(
                bid_decision="GO",
                key_risks=[],
                key_strengths=[],
                compliance_score=1.5,
                verdict_rationale="test",
            )

    def test_raw_contract_cpv_alias(self) -> None:
        from bandai.models.models import RawContract

        c = RawContract(
            portal="test",
            url="https://test.com",
            title="Test",
            contracting_authority="Auth",
            deadline="2024-12-31",
            raw_text="text",
            cpvCodes=["72000000"],
        )
        assert c.cpv_codes == ["72000000"]


# Knowledge sources tests


class TestKnowledgeSources:
    """Tests for the CrewAI Knowledge source factory."""

    def test_get_company_knowledge_data_valid(self) -> None:
        from bandai.knowledge_sources import get_company_knowledge_data

        data = get_company_knowledge_data()
        assert isinstance(data, dict)
        assert "name" in data
        assert "ateco_codes" in data

    def test_get_company_knowledge_data_missing(self) -> None:
        from bandai.knowledge_sources import get_company_knowledge_data
        from unittest.mock import patch as mock_patch

        with mock_patch(
            "bandai.knowledge_sources._COMPANY_PROFILE_PATH",
            Path("/nonexistent/knowledge/company_profile.json"),
        ):
            with pytest.raises(FileNotFoundError, match="Knowledge source not found"):
                get_company_knowledge_data()

    def test_get_company_knowledge_source_valid(self) -> None:
        from bandai.knowledge_sources import get_company_knowledge_source

        source = get_company_knowledge_source()
        assert source is not None
        assert hasattr(source, "content")
        assert "name" in source.content  # type: ignore[attr-defined]

    def test_get_company_knowledge_source_missing(self) -> None:
        from bandai.knowledge_sources import get_company_knowledge_source
        from unittest.mock import patch as mock_patch

        with mock_patch(
            "bandai.knowledge_sources._COMPANY_PROFILE_PATH",
            Path("/nonexistent/knowledge/company_profile.json"),
        ):
            with pytest.raises(FileNotFoundError, match="Knowledge source not found"):
                get_company_knowledge_source()

    def test_get_all_knowledge_sources_returns_list(self) -> None:
        from bandai.knowledge_sources import get_all_knowledge_sources

        sources = get_all_knowledge_sources()
        assert isinstance(sources, list)

    def test_get_all_knowledge_sources_graceful_missing(self) -> None:
        from bandai.knowledge_sources import get_all_knowledge_sources
        from unittest.mock import patch as mock_patch

        with mock_patch(
            "bandai.knowledge_sources._COMPANY_PROFILE_PATH",
            Path("/nonexistent/knowledge/company_profile.json"),
        ):
            sources = get_all_knowledge_sources()
            assert sources == []


# Flow persistence test


class TestFlowPersistence:
    """Tests for @persist decorator and BandAIFlow state model."""

    def test_bandai_state_default(self) -> None:
        from bandai.flow import BandAIState

        state = BandAIState()
        assert state.user_preferences == ""
        assert state.mode == "full"
        assert state.contracts == []
        assert state.approved_contracts == []
        assert state.proposals == []
        assert state.total_contracts == 0

    def test_bandai_state_custom_mode(self) -> None:
        from bandai.flow import BandAIState

        state = BandAIState(mode="scout")
        assert state.mode == "scout"

    def test_bandai_state_serializable(self) -> None:
        import json as _json
        from bandai.flow import BandAIState

        state = BandAIState(
            mode="full",
            contracts=[{"title": "Test", "value_eur": 1000}],
            approved_contracts=[
                (
                    {"title": "T"},
                    {
                        "bid_decision": "GO",
                        "key_risks": [],
                        "key_strengths": [],
                        "compliance_score": 0.9,
                        "verdict_rationale": "ok",
                    },
                )
            ],
        )
        dumped = state.model_dump_json()
        parsed = _json.loads(dumped)
        assert parsed["mode"] == "full"
        assert len(parsed["contracts"]) == 1

    def test_bandai_flow_structure(self) -> None:
        from bandai.flow import BandAIFlow
        from crewai.flow.flow import Flow  # type: ignore[import]

        assert issubclass(BandAIFlow, Flow)
        for method_name in [
            "begin",
            "route_from_begin",
            "run_scouting",
            "route_after_scout",
            "end_scout_only",
            "skip_to_compliance",
            "route_skip",
            "init_compliance",
            "route_after_init",
            "process_next_contract_func",
            "route_process_contract",
            "run_compliance_crew_func",
            "route_verdict",
            "handle_conditional_go_func",
            "route_after_conditional",
            "after_compliance",
            "route_after_compliance",
            "run_proposals",
        ]:
            assert hasattr(BandAIFlow, method_name), f"BandAIFlow missing method: {method_name}"


# IO tests


class TestIO:
    """Tests for bandai.io output utilities."""

    def test_output_dir_exists(self) -> None:
        from bandai.io import OUTPUT_DIR

        assert OUTPUT_DIR.exists()
        assert OUTPUT_DIR.is_dir()

    def test_save_json(self) -> None:
        from bandai.io import save_json

        path = save_json({"test": True}, "_test_output.json")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "test" in content
        path.unlink()

    def test_save_json_nested(self) -> None:
        from bandai.io import save_json

        path = save_json(
            {"contracts": [{"id": 1}]},
            "_test_nested.json",
        )
        assert path.exists()
        path.unlink()


# Reload portals tests


class TestReloadPortals:
    """Tests for reload_portals() reloading from a new YAML file."""

    def test_reload_updates_portal_weights(self) -> None:
        import bandai.config.portals as portals_mod

        yaml_content = {
            "portals": [
                {"name": "Reload Portal A", "base_url": "https://reload-a.com", "reliability": 0.99},
                {"name": "Reload Portal B", "base_url": "https://reload-b.com", "reliability": 0.88},
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(yaml_content, f)
            tmp_path = Path(f.name)

        # Save original module-level state so we can restore it after the test
        original_bandi_portals = portals_mod.BANDI_PORTALS
        original_portal_weights = portals_mod.PORTAL_WEIGHTS

        try:
            # Patch _load_portals to read from our temp file
            with patch.object(
                portals_mod,
                "_load_portals",
                return_value=portals_mod._load_portals(tmp_path),
            ):
                result = portals_mod.reload_portals()

            assert len(result) == 2
            assert result[0].name == "Reload Portal A"
            # Access PORTAL_WEIGHTS through the module reference (not a local
            # binding) because reload_portals() replaces the global dict.
            assert portals_mod.PORTAL_WEIGHTS.get("Reload Portal A") == 0.99
            assert portals_mod.PORTAL_WEIGHTS.get("Reload Portal B") == 0.88
        finally:
            tmp_path.unlink()
            portals_mod.BANDI_PORTALS = original_bandi_portals
            portals_mod.PORTAL_WEIGHTS = original_portal_weights


# Validate portals - no portals configured


class TestValidatePortalsNoPortals:
    """When BANDI_PORTALS is empty, validate_portals raises ValueError."""

    def test_raises_when_no_portals(self) -> None:
        import bandai.config.portals as portals_mod
        from bandai.config.portals import validate_portals

        original_portals = portals_mod.BANDI_PORTALS

        try:
            portals_mod.BANDI_PORTALS = []
            with pytest.raises(ValueError, match="No procurement portals configured"):
                validate_portals()
        finally:
            portals_mod.BANDI_PORTALS = original_portals


# LLM factory tests


class TestLLMFactory:
    """Tests for get_llm factory with mocked CrewAI LLM."""

    def setup_method(self) -> None:
        """Clear LLM caches before each test."""
        from bandai.config import clear_caches

        clear_caches()

    def teardown_method(self) -> None:
        """Clear caches after each test."""
        from bandai.config import clear_caches

        clear_caches()

    def _install_mock_crewai(self) -> MagicMock:
        """Install a mock crewai package in sys.modules with an LLM class.

        get_llm() does a lazy from crewai import LLM inside the
        function body, so we need the mock at the sys.modules level.
        Returns the mock LLM class for further assertions.
        """
        mock_crewai = types.ModuleType("crewai")
        mock_llm_class = MagicMock(return_value=MagicMock())
        mock_crewai.LLM = mock_llm_class
        sys.modules["crewai"] = mock_crewai
        return mock_llm_class

    def _remove_mock_crewai(self) -> None:
        """Remove the mock crewai package from sys.modules."""
        sys.modules.pop("crewai", None)

    def test_get_llm_caches_results(self) -> None:
        """Verify that get_llm returns the same instance for the same args (lru_cache)."""
        from bandai.config.llm import get_llm

        get_llm.cache_clear()
        mock_llm_class = self._install_mock_crewai()

        try:
            with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=False):
                llm1 = get_llm(fast=False)
                llm2 = get_llm(fast=False)

            # lru_cache should return the same object
            assert llm1 is llm2
            mock_llm_class.assert_called_once()
        finally:
            get_llm.cache_clear()
            self._remove_mock_crewai()

    def test_get_llm_env_override_main_model(self) -> None:
        """Verify that MAIN_MODEL env var overrides the provider default."""
        from bandai.config.llm import get_llm

        get_llm.cache_clear()
        mock_llm_class = self._install_mock_crewai()

        try:
            env = {
                "LLM_PROVIDER": "ollama",
                "MAIN_MODEL": "ollama/custom-model",
            }
            with patch.dict(os.environ, env, clear=False):
                llm = get_llm(fast=False)

            mock_llm_class.assert_called_once()
            call_kwargs = mock_llm_class.call_args[1]
            # The model should contain our override
            assert "custom-model" in call_kwargs["model"]
        finally:
            get_llm.cache_clear()
            self._remove_mock_crewai()
