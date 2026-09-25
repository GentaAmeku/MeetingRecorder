"""VAD stage: detects speech regions with silero-vad.

mic.wav is mostly silence (the time spent listening to the other side).
Feeding silence to Whisper produces a flood of stock hallucinated phrases, so
only the speech regions are cut out and passed through.
"""

from __future__ import annotations

import numpy as np
import torch

from .audio import TARGET_SR

_model = None


def _get_model():
    global _model
    if _model is None:
        from silero_vad import load_silero_vad

        _model = load_silero_vad()
    return _model


def speech_regions(
    audio: np.ndarray,
    sr: int = TARGET_SR,
    *,
    threshold: float = 0.5,
    min_silence_ms: int = 300,
    speech_pad_ms: int = 200,
) -> list[tuple[float, float]]:
    """Returns speech regions as [(start_s, end_s), ...].

    Raising threshold makes detection stricter (dropping weaker speech). mic
    is expected to be called with a stricter threshold than system.
    """
    from silero_vad import get_speech_timestamps

    model = _get_model()
    tensor = torch.from_numpy(np.ascontiguousarray(audio))
    stamps = get_speech_timestamps(
        tensor,
        model,
        sampling_rate=sr,
        return_seconds=True,
        threshold=threshold,
        min_silence_duration_ms=min_silence_ms,
        speech_pad_ms=speech_pad_ms,
    )
    return [(float(s["start"]), float(s["end"])) for s in stamps]
