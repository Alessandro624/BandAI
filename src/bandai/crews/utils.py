from pathlib import Path

import yaml

# Config path: all crews load YAML from src/bandai/config/
_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def load_yaml_config(filename: str) -> dict:
    """Load a YAML configuration file from src/bandai/config/."""
    config_path = _CONFIG_DIR / filename
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))
