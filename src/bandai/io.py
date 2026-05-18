from __future__ import annotations

import json
import logging
from pathlib import Path

from bandai.utils import PROJECT_ROOT

log = logging.getLogger(__name__)

OUTPUT_DIR: Path = PROJECT_ROOT / "output"

# Ensure the output directory exists at import time.
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_json(data: dict, filename: str) -> Path:
    """Persist data as a pretty-printed JSON file in the output directory."""
    path = OUTPUT_DIR / filename
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved: %s", path)
    return path
