"""normalize stage: normalizes a WAV to Whisper's input format (16kHz mono float32).

- Downmixes system.wav (stereo) to mono (fine, since "the other side" is a single bucket)
- Resamples 48kHz -> 16kHz
- Light peak normalization to stabilize the VAD threshold

The normalized result is never written to disk; it's returned as an
intermediate value passed to transcribe.
"""

from __future__ import annotations

from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

TARGET_SR = 16000


def downmix_mono(audio: np.ndarray) -> np.ndarray:
    """Averages (frames, channels) down to mono (frames,)."""
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1)


def resample(x: np.ndarray, src_sr: int, target_sr: int = TARGET_SR) -> np.ndarray:
    """Resamples src_sr -> target_sr with a polyphase filter."""
    if src_sr == target_sr:
        return x.astype(np.float32, copy=False)
    g = gcd(src_sr, target_sr)
    up = target_sr // g
    down = src_sr // g
    return resample_poly(x, up, down).astype(np.float32)


def peak_normalize(x: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    """Scales the peak to target_peak (returns unchanged if effectively silent)."""
    if x.size == 0:
        return x
    peak = float(np.max(np.abs(x)))
    if peak < 1e-6:
        return x
    return (x * (target_peak / peak)).astype(np.float32)


def load_normalized(path: str, target_sr: int = TARGET_SR) -> np.ndarray:
    """Reads a WAV and returns a float32 array after mono-mixing, resampling, and peak normalization."""
    audio, src_sr = sf.read(path, dtype="float32", always_2d=True)
    mono = downmix_mono(audio)
    mono = resample(mono, src_sr, target_sr)
    return peak_normalize(mono)
