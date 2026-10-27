"""transcribe stage: transcribes one track with VAD + MLX Whisper.

Only the speech regions VAD identifies are passed to Whisper (to avoid
hallucinations from silence), and each region's relative time is mapped back
to the original track's absolute time to produce the segment list.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

import mlx_whisper
import numpy as np

from .audio import TARGET_SR, load_normalized
from .segments import Segment, shift_segments
from .vad import speech_regions

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"
AUTO_LANGUAGE = "auto"

# Per-track VAD threshold. mic is mostly silence so it's stricter; system has
# continuous audio so it's more lenient.
VAD_THRESHOLD = {"mic": 0.6, "system": 0.4}

# A segment whose compression ratio exceeds this is treated as a repetitive hallucination and dropped.
_MAX_COMPRESSION_RATIO = 2.4

# Whisper keeps at most 223 tokens of prompt text. Stay inside it with room to spare.
MAX_PROMPT_TOKENS = 200


def _whisper_language(language: str) -> str | None:
    """Maps our "auto" sentinel to None, which tells mlx_whisper to auto-detect
    the spoken language; any other value is passed through as a Whisper language code.
    """
    return None if language == AUTO_LANGUAGE else language


def build_prompt(
    terms: Iterable[str],
    count_tokens: Callable[[str], int],
    max_tokens: int = MAX_PROMPT_TOKENS,
) -> str | None:
    """Joins hint words into one line for Whisper's initial_prompt (pure logic).

    Words are taken in order and joined with 「、」; a word that would push the
    line past `max_tokens` is skipped and later (shorter) words are still
    tried, the same way Tsuzuri builds its WhisperKit prompt. Returns None when
    there is nothing to hint.
    """
    prompt = ""
    seen: set[str] = set()
    for term in terms:
        term = term.strip()
        if not term or "\n" in term or term in seen:
            continue
        seen.add(term)
        candidate = term if not prompt else f"{prompt}、{term}"
        if count_tokens(" " + candidate) <= max_tokens:
            prompt = candidate
    return prompt or None


def whisper_prompt(terms: Iterable[str]) -> str | None:
    """build_prompt with Whisper's own multilingual tokenizer counting the tokens."""
    from mlx_whisper.tokenizer import get_tokenizer

    tokenizer = get_tokenizer(multilingual=True, num_languages=100, task="transcribe")
    return build_prompt(terms, lambda text: len(tokenizer.encode(text)))


def transcribe_track(
    path: str,
    *,
    language: str = AUTO_LANGUAGE,
    model: str = DEFAULT_MODEL,
    vad_threshold: float = 0.5,
    initial_prompt: str | None = None,
) -> list[Segment]:
    """Transcribes one track's WAV and returns a chronological segment list."""
    return transcribe_audio(
        load_normalized(path),
        language=language,
        model=model,
        vad_threshold=vad_threshold,
        initial_prompt=initial_prompt,
    )


def transcribe_audio(
    audio: np.ndarray,
    *,
    language: str = AUTO_LANGUAGE,
    model: str = DEFAULT_MODEL,
    vad_threshold: float = 0.5,
    initial_prompt: str | None = None,
) -> list[Segment]:
    """Transcribes an already-normalized (16kHz mono float) waveform.

    Kept separate from loading so the same system waveform can be reused for diarization.
    `initial_prompt` (the dictionary's hint words) is given to every speech
    region, so each one knows how the meeting's words are spelled.
    """
    regions = speech_regions(audio, sr=TARGET_SR, threshold=vad_threshold)

    segments: list[Segment] = []
    for start_s, end_s in regions:
        chunk = audio[int(start_s * TARGET_SR) : int(end_s * TARGET_SR)]
        if chunk.size == 0:
            continue
        result = mlx_whisper.transcribe(
            chunk.astype(np.float32),
            path_or_hf_repo=model,
            language=_whisper_language(language),
            # --- Anti-hallucination settings ---
            condition_on_previous_text=False,  # break the chain of repeated hallucinations
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=_MAX_COMPRESSION_RATIO,
            temperature=0.0,
            initial_prompt=initial_prompt,
        )
        chunk_segments = [
            Segment(start=s["start"], end=s["end"], text=s["text"].strip())
            for s in result.get("segments", [])
            if s["text"].strip() and not _looks_hallucinated(s)
        ]
        segments.extend(shift_segments(chunk_segments, offset=start_s))

    segments.sort(key=lambda s: s.start)
    return segments


def _looks_hallucinated(seg: dict) -> bool:
    """A light guard that rejects low-confidence/repetitive segments as hallucinations."""
    if seg.get("no_speech_prob", 0.0) > 0.6 and seg.get("avg_logprob", 0.0) < -1.0:
        return True
    if seg.get("compression_ratio", 0.0) > _MAX_COMPRESSION_RATIO:
        return True
    return False


def track_vad_threshold(track: str) -> float:
    """Default VAD threshold for a given track name (mic/system)."""
    return VAD_THRESHOLD.get(track, 0.5)
