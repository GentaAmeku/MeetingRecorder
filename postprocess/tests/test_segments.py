"""Unit tests for restoring the time axis (a VAD chunk's relative time -> the original track's absolute time)."""

from postprocess.segments import Segment, shift_segments


def test_shift_maps_chunk_relative_to_absolute_time():
    # If VAD cut out [10.0s, 13.0s] as a speech region, a segment at 0.5s
    # within that chunk becomes absolute 10.5s.
    chunk = [Segment(start=0.5, end=1.2, text="こんにちは")]
    shifted = shift_segments(chunk, offset=10.0)
    assert shifted[0].start == 10.5
    assert shifted[0].end == 11.2
    assert shifted[0].text == "こんにちは"


def test_shift_rounds_float_error_to_3_decimals():
    # Rounds 0.1 + 0.2 = 0.30000000000000004 down to 0.3.
    segs = [Segment(start=0.1, end=0.5, text="a")]
    shifted = shift_segments(segs, offset=0.2)
    assert shifted[0].start == 0.3
    assert shifted[0].end == 0.7


def test_shift_empty_list():
    assert shift_segments([], offset=5.0) == []
