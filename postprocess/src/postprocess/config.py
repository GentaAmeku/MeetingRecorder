"""Reading postprocess-config.json (display names, transcription language).

Unknown keys are ignored (neither read nor written). Keys written by an older
version keep working with their defaults if left in place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / "Documents" / "MeetingRecorder" / "postprocess-config.json"
DEFAULT_SELF_NAME = "Me"
DEFAULT_OTHER_NAME = "Other"
DEFAULT_LANGUAGE = "auto"


@dataclass(frozen=True)
class PostprocessConfig:
    self_name: str = DEFAULT_SELF_NAME
    other_name: str = DEFAULT_OTHER_NAME
    language: str = DEFAULT_LANGUAGE


def _parse_name(section: dict, key: str, default: str) -> str:
    raw = section.get(key)
    if not isinstance(raw, str) or "\n" in raw or "\r" in raw:
        return default
    value = raw.strip()
    return value or default


def normalize_language(value: object) -> str | None:
    """Returns "auto" or a Whisper language code for a user-supplied value, or
    None when the value isn't usable. Accepts codes ("ja") and names
    ("japanese") in any case, ignoring surrounding whitespace.
    """
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        return None
    text = value.strip().lower()
    if not text:
        return None
    if text == DEFAULT_LANGUAGE:
        return text
    try:
        from mlx_whisper.tokenizer import LANGUAGES, TO_LANGUAGE_CODE
    except ImportError:  # pragma: no cover - mlx-whisper is a hard dependency
        return text if text.isalpha() and 2 <= len(text) <= 3 else None
    if text in LANGUAGES:
        return text
    return TO_LANGUAGE_CODE.get(text)


def _parse_language(section: dict) -> str:
    # An unsupported value falls back to auto-detection instead of stopping
    # transcription after the model has loaded.
    return normalize_language(section.get("language")) or DEFAULT_LANGUAGE


def parse_config(text: str) -> PostprocessConfig:
    """Parses the config JSON (pure logic). A missing key falls back to its
    default; an unknown key is ignored.

    Malformed JSON also falls back to the defaults (a corrupt config file
    must never stop the pipeline).
    """
    try:
        data = json.loads(text)
    except ValueError:
        return PostprocessConfig()
    if not isinstance(data, dict):
        return PostprocessConfig()
    section = data.get("transcript", {})
    if not isinstance(section, dict):
        return PostprocessConfig()
    return PostprocessConfig(
        self_name=_parse_name(section, "selfName", DEFAULT_SELF_NAME),
        other_name=_parse_name(section, "otherName", DEFAULT_OTHER_NAME),
        language=_parse_language(section),
    )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> PostprocessConfig:
    """Reads the config file. Returns the defaults if it doesn't exist."""
    try:
        return parse_config(path.read_text(encoding="utf-8"))
    except OSError:
        return PostprocessConfig()
