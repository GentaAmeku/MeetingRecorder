"""Pure-logic unit tests for the align stage (assign_speakers / merge_tracks / group_turns)."""

from postprocess.align import OTHER, SELF, assign_speakers, group_turns, merge_tracks
from postprocess.align import LabeledSegment as L
from postprocess.segments import Segment, SpeakerSegment as SP


def test_merge_labels_and_sorts_by_start():
    mic = [Segment(2.0, 3.0, "selfA"), Segment(6.0, 7.0, "selfB")]
    # system is passed already processed by assign_speakers (no diarization -> all other)
    system = assign_speakers(
        [Segment(0.0, 1.5, "otherA"), Segment(4.0, 5.0, "otherB")], None
    )
    merged = merge_tracks(mic, system)
    assert [(m.speaker, m.text) for m in merged] == [
        (OTHER, "otherA"),
        (SELF, "selfA"),
        (OTHER, "otherB"),
        (SELF, "selfB"),
    ]


def test_merge_simultaneous_keeps_both_earlier_end_first():
    mic = [Segment(1.0, 2.0, "self")]
    system = assign_speakers([Segment(1.0, 3.0, "other")], None)
    merged = merge_tracks(mic, system)
    # Same start time -> the one that ends earlier (self, end=2.0) comes first
    assert [m.text for m in merged] == ["self", "other"]


def test_assign_speakers_fallback_when_no_diarization():
    system = [Segment(0.0, 1.0, "a"), Segment(2.0, 3.0, "b")]
    for speakers in (None, []):
        labeled = assign_speakers(system, speakers)
        assert [ls.speaker for ls in labeled] == [OTHER, OTHER]
        assert [ls.text for ls in labeled] == ["a", "b"]


def test_assign_speakers_overlap_and_first_appearance_numbering():
    system = [
        Segment(0.0, 2.0, "first person"),
        Segment(5.0, 7.0, "next person"),
        Segment(10.0, 12.0, "first person again"),
    ]
    # The speaker ID's numeric value is unrelated to order of first appearance (7 speaks first).
    # Confirms numbering follows order of first appearance instead.
    speakers = [
        SP(0.0, 3.0, 7),   # first appearance -> other-1
        SP(4.5, 8.0, 2),   # next -> other-2
        SP(9.5, 13.0, 7),  # 7 seen again -> other-1
    ]
    labeled = assign_speakers(system, speakers)
    assert [ls.speaker for ls in labeled] == ["other-1", "other-2", "other-1"]


def test_assign_speakers_picks_max_overlap():
    system = [Segment(0.0, 10.0, "crosstalk")]  # spans 2 speakers, but overlaps speaker 2 more
    speakers = [SP(0.0, 3.0, 1), SP(3.0, 10.0, 2)]
    labeled = assign_speakers(system, speakers)
    # First appearance is 1 (other-1), but the largest overlap is with 2 (other-2)
    assert labeled[0].speaker == "other-2"


def test_assign_speakers_no_overlap_is_generic_other():
    system = [Segment(100.0, 101.0, "isolated")]
    speakers = [SP(0.0, 3.0, 1)]
    labeled = assign_speakers(system, speakers)
    assert labeled[0].speaker == OTHER


def test_group_splits_turns_between_distinct_others():
    # other-1 / other-2 after diarization are treated as distinct speakers, so their turns split
    segs = [
        L("other-1", 0.0, 1.0, "A"),
        L("other-2", 1.2, 2.0, "B"),
    ]
    turns = group_turns(segs)
    assert [t.speaker for t in turns] == ["other-1", "other-2"]


def test_group_merges_consecutive_same_speaker():
    segs = [
        L(SELF, 0.0, 1.0, "Hello"),
        L(SELF, 1.2, 2.0, "let's get started"),
        L(OTHER, 2.5, 3.5, "sure"),
    ]
    turns = group_turns(segs)
    assert len(turns) == 2
    assert turns[0].speaker == SELF
    assert turns[0].text == "Hello let's get started"
    assert turns[0].start == 0.0 and turns[0].end == 2.0
    assert turns[1].text == "sure"


def test_group_splits_same_speaker_on_large_gap():
    segs = [
        L(SELF, 0.0, 1.0, "first half"),
        L(SELF, 100.0, 101.0, "much later"),
    ]
    turns = group_turns(segs, max_gap=30.0)
    assert len(turns) == 2
    assert [t.text for t in turns] == ["first half", "much later"]


def test_group_empty():
    assert group_turns([]) == []
