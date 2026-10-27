"""Unit tests for the pure "auto" -> None language mapping (no ASR/model needed)."""

from postprocess.transcribe import AUTO_LANGUAGE, _whisper_language


def test_auto_maps_to_none_for_whisper_auto_detection():
    assert _whisper_language(AUTO_LANGUAGE) is None


def test_explicit_language_code_passes_through():
    assert _whisper_language("en") == "en"
    assert _whisper_language("ja") == "ja"


def test_stock_phrases_are_dropped_even_with_good_confidence():
    from postprocess.transcribe import _looks_hallucinated, is_stock_phrase

    confident = {"no_speech_prob": 0.1, "avg_logprob": -0.2, "compression_ratio": 1.0}
    assert _looks_hallucinated({**confident, "text": "ご視聴ありがとうございました"})
    assert _looks_hallucinated({**confident, "text": " Thanks for watching! "})
    assert is_stock_phrase("チャンネル登録よろしくお願いします。")


def test_real_sentences_that_contain_a_stock_phrase_are_kept():
    from postprocess.transcribe import _looks_hallucinated, is_stock_phrase

    confident = {"no_speech_prob": 0.1, "avg_logprob": -0.2, "compression_ratio": 1.0}
    assert not is_stock_phrase("ありがとうございました")
    assert not _looks_hallucinated({**confident, "text": "ご視聴ありがとうございました、では次の議題です"})
