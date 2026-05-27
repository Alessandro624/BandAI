from __future__ import annotations

import json
import logging
import re

from typing import Any, Literal, Optional

import yaml
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify  # type: ignore

log = logging.getLogger(__name__)

# Project Paths

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

CONFIG_DIR: Path = PROJECT_ROOT / "src" / "bandai" / "config"

KNOWLEDGE_DIR: Path = PROJECT_ROOT / "knowledge"

# YAML Loading

_yaml_cache: dict[str, dict[str, Any]] = {}


def load_yaml_config(filename: str, *, use_cache: bool = True) -> dict[str, Any]:
    """Load a YAML configuration file from the config/ directory."""
    if use_cache and filename in _yaml_cache:
        return _yaml_cache[filename]

    path = CONFIG_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict in {path}, got {type(data).__name__}")

    if use_cache:
        _yaml_cache[filename] = data

    return data


# Contract Formatting


def contract_to_summary(c: dict) -> str:
    """Format a contract dict into a human-readable summary string."""
    value = c.get("value_eur") or 0
    cpv_codes = c.get("cpv_codes") or []
    if isinstance(cpv_codes, str):
        cpv_codes = [cpv_codes]

    return (
        f"Titolo               : {c.get('title', 'N/A')}\n"
        f"Canonical Contract ID: {c.get('canonical_contract_id', 'N/A')}\n"
        f"Stazione appaltante  : {c.get('contracting_authority', 'N/A')}\n"
        f"Importo a base d'asta: EUR {value:,.0f}\n"
        f"Scadenza             : {c.get('deadline', 'N/A')}\n"
        f"CPV                  : {', '.join(str(code) for code in cpv_codes)}\n"
        f"URL                  : {c.get('canonical_url', 'N/A')}"
    )


# JSON Extraction

_JSON_ARRAY_WRAPPER_KEYS = ("tenders", "items", "root", "contracts", "results", "data")


def _extract_array_from_wrapper(value: Any) -> list | None:
    if isinstance(value, list):
        if not value or all(isinstance(item, dict) for item in value):
            return value
        return None

    if isinstance(value, dict):
        for key in _JSON_ARRAY_WRAPPER_KEYS:
            wrapped = value.get(key)
            if isinstance(wrapped, list):
                return wrapped

    return None


def extract_json_array_text(raw: str) -> str:
    """Extract the first complete JSON array text from a raw LLM output."""
    decoder = json.JSONDecoder()

    for start, char in enumerate(raw):
        if char not in "[{":
            continue

        try:
            parsed, end = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue

        array = _extract_array_from_wrapper(parsed)
        if array is not None:
            return json.dumps(array, ensure_ascii=False)

    raise ValueError("No JSON array found in the input.")


def extract_json_array(raw: str) -> list:
    """Extract a JSON array from a raw LLM output string."""
    return json.loads(extract_json_array_text(raw))


# Implicit NO-GO Detection

NO_GO_KEYWORDS: list[str] = [
    # Italian
    "non ho",
    "non abbiamo",
    "non saremo",
    "non possiamo",
    "non siamo",
    "manca",
    "mancano",
    "impossibile",
    "rinunciamo",
    "abbandoniamo",
    "lasciamo perdere",
    "basta",
    "stop",
    "terminiamo",
    "fermiamo",
    "non partecipo",
    "non partecipiamo",
    "ritiro",
    "ritiriamo",
    # English
    "we don't have",
    "we can't",
    "impossible",
    "give up",
    "stop",
    "quit",
]


def is_implicit_no_go(text: str) -> bool:
    """Fast keyword check for abandonment language (pre-LLM, zero cost)."""
    lower = text.lower()
    return any(kw in lower for kw in NO_GO_KEYWORDS)


### -----------------------------------------------------------------------------------
###
###     Defining Parser/Tranformation for HTML to Markdown Format
###
### -----------------------------------------------------------------------------------


## All the Tags/Classes that needs to be removed from the original HTML Content
_TAGS_TO_REMOVE: list[str] = ["nav", "header", "footer", "aside", "script", "style", "noscript", ".side-bar", ".cookie-banner", ".cookie-notice", ".breadcrumb", ".pagination", ".social-share"]

## Main Content Containers
_MAIN_CONTENT_SELECTORS = [
    ## Extraction
    "main",
    "article",
    "[role='main']",
    "#content",
    ".content",
    "#main-content",
    ".main-content",
    ## Discovery
    "table",
]

PADDING_LINES: int = 5


## Conversion Mode:
##  - Discovery     - No Images, no Styling, just raw content with links.
##                    Try to keep all relevant information about terders' urls for reachability.
##  - Extraction    - Focus on the main content and outer links to documents and attachments.
##  - Full          - Keep everything (structure and content), aside from styling
ConversionMode = Literal["discovery", "extraction", "full"]


_MODE_CONFIG = {
    "discovery": {"description": "Clean Text with urls for reaching Single Tenders", "strip": ["img"]},
    "extraction": {"description": "Single-page Tender Extraction of Information", "strip": ["img"]},
    "full": {"description": "Complete Output with no further stripping (debug mode)", "strip": ["a", "img"]},
}


def html_to_markdown(html_content: str, mode: ConversionMode, max_chars: int = 12000, max_lines: Optional[int] = None) -> str:
    """
    Converter from HTML to Markdown content.
    Based on the requested Mode, it tries to strip all non-relevant information.

    :param html_content: Raw HTML Content to strip
    :type html_content: str
    :param mode: * 'discovery' -> Try to keep lists structure with titles and url for reachability,
                 * 'extraction' -> Keep all relevant information and documents linkage,
                 * 'full' -> No further stripping
    :type mode: ConversionMode
    :param max_chars: Maximum length of the Output (for Context Window Reasons, Saturation etc.)
    :type max_chars: int
    :param max_lines: Maximum number of Lines to keep, if provided. Used for counting the Results.
    :type max_lines: Optional[int]
    """

    ## Init
    config = _MODE_CONFIG[mode]
    soup = BeautifulSoup(html_content, "html.parser")

    ## Removing all Basic Tags/Classes
    for selector in _TAGS_TO_REMOVE:
        for tag in soup.select(selector):
            tag.decompose()  ## Destroys Tags content Recoursively

    ## Main Content Identification
    main_content = None
    for selector in _MAIN_CONTENT_SELECTORS:
        main_content = soup.select_one(selector)
        if main_content:
            break

    ## Fallback on the Body tag
    target = main_content if main_content else soup
    if not target:
        return ""

    ## Markdown Conversion
    markdown = markdownify(html=str(target), heading_style="ATX", strip=config["strip"], newline_style="backslash")  ## Titles with '#' symbol

    ## Possible Multiline Spacing
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

    if max_lines:
        lines = markdown.split("\n")
        if len(lines) > max_lines:
            truncated = lines[:max_lines]
            markdown = "\n".join(truncated)

    ## Markdown Content being too long
    if len(markdown) > max_chars:
        markdown = markdown[:max_chars]

    return markdown
