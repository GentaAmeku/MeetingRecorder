"""align stage: merges each track's transcript into a single chronological conversation.

Segments from mic are labeled self, and segments from system are labeled
other, then merged by start time. The audio tracks themselves are already
sample-synced at recording time, so this stage only needs to reconcile
timestamps at the transcript level.

For the other side (system), when a speaker-diarization result (diarize.py)
is available, each segment is attributed to whichever speaker overlaps it the
most and assigned `other-1 / other-2 …` in order of first appearance. Without
diarization, everything falls back to a single `other` as before. Overlapping
speech is kept as separate segments, with the earlier start first.
"""

from __future__ import annotations

from dataclasses import dataclass

from .segments import Segment, SpeakerSegment

SELF = "self"
OTHER = "other"

# Split into a new turn once the gap since the same speaker's last segment exceeds this (seconds).
DEFAULT_MAX_GAP = 30.0


@dataclass(frozen=True)
class LabeledSegment:
    """A segment tagged with a speaker label."""

    speaker: str  # SELF | OTHER
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Turn:
    """One speaking turn formed by joining consecutive segments from the same speaker."""

    speaker: str
    start: float
    end: float
    text: str


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Overlap between two intervals, in seconds (0 if they don't overlap)."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speakers(
    system: list[Segment], speakers: list[SpeakerSegment] | None
) -> list[LabeledSegment]:
    """Tags the system track's text segments with speaker labels.

    When `speakers` (the diarization result) is None/empty, everything falls
    back to a single `other`. Otherwise, each text segment is assigned
    whichever speaker **overlaps it the most**, and speaker IDs are numbered
    `other-1 / other-2 …` in **order of first appearance** (by the start time
    of each speaker's first region). A segment that overlaps no speaker region
    gets the generic `other`.
    """
    if not speakers:
        return [LabeledSegment(OTHER, s.start, s.end, s.text) for s in system]

    ordered = sorted(speakers, key=lambda sp: (sp.start, sp.end))
    rank: dict[int, int] = {}
    for sp in ordered:
        if sp.speaker not in rank:
            rank[sp.speaker] = len(rank) + 1

    labeled: list[LabeledSegment] = []
    for seg in system:
        best_id: int | None = None
        best_ov = 0.0
        for sp in ordered:
            ov = _overlap(seg.start, seg.end, sp.start, sp.end)
            if ov > best_ov:
                best_ov = ov
                best_id = sp.speaker
        label = OTHER if best_id is None else f"{OTHER}-{rank[best_id]}"
        labeled.append(LabeledSegment(label, seg.start, seg.end, seg.text))
    return labeled


def merge_tracks(
    mic: list[Segment], system: list[LabeledSegment]
) -> list[LabeledSegment]:
    """Labels mic as self and merges it chronologically with the already-labeled system track.

    `system` has already been labeled by assign_speakers (other or other-N).
    Overlapping speech (same start time) is stable-sorted by start then end, keeping both.
    """
    labeled = [LabeledSegment(SELF, s.start, s.end, s.text) for s in mic]
    labeled += list(system)
    labeled.sort(key=lambda ls: (ls.start, ls.end))
    return labeled


def group_turns(
    segments: list[LabeledSegment], *, max_gap: float = DEFAULT_MAX_GAP
) -> list[Turn]:
    """Joins consecutive segments from the same speaker into a single turn.

    Starts a new turn when the speaker changes, or when the same speaker's gap
    since the previous segment's end reaches max_gap seconds.
    """
    turns: list[Turn] = []
    for seg in segments:
        if (
            turns
            and turns[-1].speaker == seg.speaker
            and seg.start - turns[-1].end <= max_gap
        ):
            prev = turns[-1]
            joined = f"{prev.text} {seg.text}".strip()
            turns[-1] = Turn(prev.speaker, prev.start, seg.end, joined)
        else:
            turns.append(Turn(seg.speaker, seg.start, seg.end, seg.text))
    return turns
