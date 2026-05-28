from __future__ import annotations

import logging
import os

from pydantic import BaseModel, Field, HttpUrl
from typing import Literal, Optional

import yaml
from pathlib import Path

from bandai.utils import CONFIG_DIR

log = logging.getLogger(__name__)



### -----------------------------------------------------------------------------------
###
###     Defining Configuration Directives for Extraction Process
###
### -----------------------------------------------------------------------------------

class SelectorIdentifier(BaseModel):
    type: str
    text: str

class ActionDescription(BaseModel):
    selector: SelectorIdentifier
    action_type: Literal['click']
    wait_after_action: Literal['networkidle'] | int


class DiscoveryProcess(BaseModel):
    
    base_search_url: HttpUrl
    elements_per_page: int

    ## Main Selector
    list_wrapper_selector: SelectorIdentifier
    next_page_selector: SelectorIdentifier

    actions_to_perform: list[ActionDescription]


class ExtractionProcess(BaseModel):
    base_resource_url: HttpUrl
    main_content_selector: SelectorIdentifier


# Portal Config Model


class PortalConfig(BaseModel):
    """Immutable configuration for a single procurement portal."""

    name: str
    info: Optional[str] = None
    base_url: Optional[HttpUrl] = None
    reliability: float = Field(..., ge=0.0, le=1.0)
    country_filter: Optional[str] = None

    discovery: Optional[DiscoveryProcess] = None
    extraction: Optional[ExtractionProcess] = None

    def is_ready_for_discovery(self) -> bool:
        return self.discovery is not None

    def is_ready_for_extraction(self) -> bool:
        return self.discovery is not None




# Loading


def _load_portals(path: Path | None = None) -> list[PortalConfig]:
    """Load portal definitions from the YAML config file."""
    if path is None:
        path = CONFIG_DIR / "portals.yaml"

    if not path.exists():
        log.warning("Portal config not found at %s. Using empty portal list.", path)
        return []

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    portals = [PortalConfig.model_validate(p) for p in data.get("portals", [])]
    log.info("Loaded %d portal definitions from %s", len(portals), path)
    return portals


BANDI_PORTALS: list[PortalConfig] = _load_portals()


def validate_portals() -> None:
    """Raise ValueError if no portal is configured."""
    if not BANDI_PORTALS:
        raise ValueError("No procurement portals configured. " f"Ensure {CONFIG_DIR / 'portals.yaml'} contains at least one portal entry.")


def reload_portals() -> list[PortalConfig]:
    """Re-read portals from disk and update the module-level list."""
    global BANDI_PORTALS  # noqa: PLW0603
    BANDI_PORTALS = _load_portals()
    _rebuild_weights()
    return BANDI_PORTALS


# Weight Helpers


def _read_default_portal_weight() -> float:
    w = float(os.getenv("DEFAULT_PORTAL_WEIGHT", "0.5"))
    return max(0.0, min(1.0, w))


def _rebuild_weights() -> None:
    """Rebuild the PORTAL_WEIGHTS dict from the current BANDI_PORTALS."""
    global PORTAL_WEIGHTS  # noqa: PLW0603
    PORTAL_WEIGHTS = {p.name: p.reliability for p in BANDI_PORTALS}


PORTAL_WEIGHTS: dict[str, float] = {p.name: p.reliability for p in BANDI_PORTALS}
_DEFAULT_PORTAL_WEIGHT = _read_default_portal_weight()


def portal_weight(portal_name: str) -> float:
    """Return the reliability weight for a portal, falling back to the default."""
    return PORTAL_WEIGHTS.get(portal_name, _DEFAULT_PORTAL_WEIGHT)
