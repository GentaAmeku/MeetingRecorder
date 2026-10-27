"""Pure-logic unit tests for building Whisper's initial_prompt from hint words."""

from postprocess.transcribe import build_prompt


def by_chars(text: str) -> int:
    """A stand-in tokenizer: one token per character."""
    return len(text)


def test_joins_words_with_japanese_comma():
    assert build_prompt(["Claude Code", "Vitest"], by_chars) == "Claude Code、Vitest"


def test_skips_words_over_budget_but_keeps_trying_shorter_ones():
    # " A、LongWord" would be 11 > 8, so LongWord is skipped and B still fits.
    assert build_prompt(["A", "LongWord", "B"], by_chars, max_tokens=6) == "A、B"


def test_drops_duplicates_blanks_and_newlines():
    assert build_prompt(["A", "", " A ", "x\ny", "B"], by_chars) == "A、B"


def test_nothing_to_hint():
    assert build_prompt([], by_chars) is None
    assert build_prompt(["TooLongForTheBudget"], by_chars, max_tokens=5) is None


def test_real_tokenizer_stays_inside_whisper_limit():
    from postprocess.transcribe import MAX_PROMPT_TOKENS, whisper_prompt
    from mlx_whisper.tokenizer import get_tokenizer

    words = [f"用語{i}" for i in range(300)]
    prompt = whisper_prompt(words)
    tokenizer = get_tokenizer(multilingual=True, num_languages=100, task="transcribe")
    assert prompt is not None
    assert len(tokenizer.encode(" " + prompt)) <= MAX_PROMPT_TOKENS
