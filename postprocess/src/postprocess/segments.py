"""Transcript segment representation and pure-logic time-axis operations.

This module has no dependency on audio processing or ASR (kept separate to be easy to unit test).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """One spoken segment. Times are seconds since the recording started."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SpeakerSegment:
    """A "who spoke when" region returned by speaker diarization (carries no text).

    `speaker` is an integer ID assigned by the diarizer (meaningless on its
    own; mapped to Other A/B, etc. in order of first appearance).
    """

    start: float
    end: float
    speaker: int


def shift_segments(segments: list[Segment], offset: float) -> list[Segment]:
    """Shifts each segment's time forward by offset seconds.

    Used to map a relative time within a VAD-cut chunk (chunk start = 0) back
    to the original track's absolute time.
    """
    return [
        Segment(start=round(s.start + offset, 3), end=round(s.end + offset, 3), text=s.text)
        for s in segments
    ]
