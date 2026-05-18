from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from bandai.utils import CONFIG_DIR

log = logging.getLogger(__name__)


# Portal Config Model


class PortalConfig(BaseModel):
    """Immutable configuration for a single procurement portal."""

    name: str
    base_url: str
    reliability: float = Field(..., ge=0.0, le=1.0)
    country_filter: str | None = None


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
