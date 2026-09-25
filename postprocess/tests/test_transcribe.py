"""Unit tests for the pure "auto" -> None language mapping (no ASR/model needed)."""

from postprocess.transcribe import AUTO_LANGUAGE, _whisper_language


def test_auto_maps_to_none_for_whisper_auto_detection():
    assert _whisper_language(AUTO_LANGUAGE) is None


def test_explicit_language_code_passes_through():
    assert _whisper_language("en") == "en"
    assert _whisper_language("ja") == "ja"
