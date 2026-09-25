"""Pure-logic unit tests for the render stage (transcript.md / transcript.json)."""

import json

from postprocess.align import OTHER, SELF
from postprocess.align import LabeledSegment as L
from postprocess.align import Turn
from postprocess.metadata import SessionMeta
from postprocess.render import render_json, render_markdown


def _meta():
    return SessionMeta(
        started_at="2026-06-30T15:30:00+09:00",
        duration_sec=2412,
        mic_device_name="EarPodsのマイク",
    )


def test_markdown_header_and_turns():
    turns = [
        Turn(SELF, 12.0, 18.0, "おはようございます"),
        Turn(OTHER, 75.0, 90.0, "はい、お願いします"),
    ]
    md = render_markdown(turns, _meta())
    assert "# Meeting Transcript — 2026-06-30 15:30 (40m 12s)" in md
    assert "- Me: Me" in md
    assert "- Mic: EarPodsのマイク" in md
    assert "[00:12] Me: おはようございます" in md
    assert "[01:15] Other: はい、お願いします" in md


def test_markdown_uses_configured_self_name_only_for_human_output():
    turns = [Turn(SELF, 12.0, 18.0, "おはようございます")]

    md = render_markdown(turns, _meta(), self_name="山田")

    assert "- Me: 山田" in md
    assert "- Mic: EarPodsのマイク" in md
    assert "[00:12] 山田: おはようございます" in md


def test_markdown_uses_configured_other_name():
    turns = [Turn(OTHER, 1.0, 2.0, "hello")]

    md = render_markdown(turns, _meta(), other_name="Guest")

    assert "- Others: Guest (system audio, meeting participants)" in md
    assert "[00:01] Guest: hello" in md


def test_markdown_shows_title_when_present():
    meta = SessionMeta(
        started_at="2026-06-30T15:30:00+09:00",
        duration_sec=2412,
        mic_device_name="EarPodsのマイク",
        title="週次定例",
    )
    md = render_markdown([Turn(SELF, 1.0, 2.0, "やあ")], meta)
    assert "# Meeting Transcript: 週次定例 — 2026-06-30 15:30 (40m 12s)" in md


def test_markdown_hides_default_meeting_title():
    meta = SessionMeta(
        started_at="2026-06-30T15:30:00+09:00",
        duration_sec=60,
        mic_device_name="mic",
        title="meeting",
    )
    md = render_markdown([Turn(SELF, 1.0, 2.0, "やあ")], meta)
    # The default "meeting" title isn't shown (only the date/time)
    assert "Transcript: meeting" not in md
    assert "# Meeting Transcript — 2026-06-30 15:30 (1m 0s)" in md


def test_markdown_duration_under_a_minute():
    md = render_markdown(
        [Turn(SELF, 0.0, 1.0, "test")],
        SessionMeta(started_at="bad-iso", duration_sec=11, mic_device_name="mic"),
    )
    # Zero minutes shows seconds only; an unparseable ISO string is shown as-is
    assert "(11s)" in md
    assert "bad-iso" in md


def test_markdown_renders_diarized_others_as_letters():
    turns = [
        Turn(SELF, 0.0, 2.0, "始めます"),
        Turn("other-1", 3.0, 5.0, "はい"),
        Turn("other-2", 6.0, 8.0, "補足です"),
    ]
    md = render_markdown(turns, _meta())
    assert "[00:03] Other A: はい" in md
    assert "[00:06] Other B: 補足です" in md
    # Only two others appear, so a third letter must never show up
    assert "Other C" not in md


def test_markdown_single_other_uses_default_name():
    md = render_markdown([Turn(OTHER, 1.0, 2.0, "どうも")], _meta())
    assert "[00:01] Other: どうも" in md


def test_markdown_uses_counterpart_name_for_other():
    meta = SessionMeta(
        started_at="2026-06-30T15:30:00+09:00",
        duration_sec=600,
        mic_device_name="EarPods",
        counterpart_name="田中",
    )
    turns = [Turn(SELF, 0.0, 2.0, "どうも"), Turn(OTHER, 3.0, 5.0, "よろしく")]
    md = render_markdown(turns, meta)
    assert "- Others: 田中 (system audio)" in md
    assert "[00:03] 田中: よろしく" in md
    assert "[00:00] Me: どうも" in md


def test_json_is_labeled_segment_array():
    segs = [
        L(SELF, 0.1, 0.9, "a"),
        L("other-1", 1.0, 2.0, "b"),
        L("other-2", 2.0, 3.0, "c"),
    ]
    payload = json.loads(render_json(segs))
    assert payload == [
        {"start": 0.1, "end": 0.9, "speaker": "self", "text": "a"},
        {"start": 1.0, "end": 2.0, "speaker": "other-1", "text": "b"},
        {"start": 2.0, "end": 3.0, "speaker": "other-2", "text": "c"},
    ]


def test_speaker_label_joins_cjk_names_without_a_space():
    # Japanese labels read naturally as "相手A"; Latin ones keep the space.
    from postprocess.render import _join_label

    assert _join_label("相手", "A") == "相手A"
    assert _join_label("Other", "A") == "Other A"

