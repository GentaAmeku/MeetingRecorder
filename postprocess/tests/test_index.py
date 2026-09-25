"""Pure-logic unit tests for index.json generation (tmp_path, no real audio needed)."""

import json
from pathlib import Path

from postprocess.index import (
    SCHEMA_VERSION,
    build_index,
    extract_excerpt,
    session_entry,
    write_index,
)

_TRANSCRIPT = """# Meeting Transcript: 週次定例 — 2026-06-30 15:30 (40m 12s)

- Me: MacBook Pro Microphone
- Other: system audio (meeting participants)

---

[00:12] Me: おはようございます、始めましょうか。
[00:15] Other A: はい、お願いします。
"""


def _make_session(
    root: Path,
    name: str,
    *,
    metadata: str | None = None,
    transcript: str | None = None,
) -> Path:
    d = root / name
    d.mkdir(parents=True)
    if metadata is not None:
        (d / "metadata.json").write_text(metadata, encoding="utf-8")
    if transcript is not None:
        (d / "transcript.md").write_text(transcript, encoding="utf-8")
    return d


# --- extract_excerpt ---


def test_excerpt_skips_header_and_picks_turns():
    got = extract_excerpt(_TRANSCRIPT)
    assert got.startswith("[00:12] Me:")
    assert "[00:15] Other A:" in got
    assert "system audio" not in got  # header meta lines aren't included
    assert "# Meeting Transcript" not in got


def test_excerpt_truncates_long_turn():
    md = "---\n" + "[00:01] Me: " + "あ" * 500 + "\n"
    got = extract_excerpt(md, max_chars=50)
    assert len(got) == 51  # 50 + …
    assert got.endswith("…")


def test_excerpt_empty_and_headerless():
    assert extract_excerpt("") == ""
    # A turn line is picked up even without a `---`
    assert extract_excerpt("[00:01] Me: こんにちは\n") == "[00:01] Me: こんにちは"


# --- session_entry ---


def test_session_entry_full(tmp_path):
    meta = {
        "title": "週次定例",
        "startedAt": "2026-06-30T15:30:00+09:00",
        "endedAt": "2026-06-30T16:10:00+09:00",
        "durationSec": 2400,
        "counterpartName": "田中",
    }
    d = _make_session(
        tmp_path,
        "2026-06-30_1530_週次定例",
        metadata=json.dumps(meta),
        transcript=_TRANSCRIPT,
    )
    e = session_entry(d)
    assert e == {
        "dir": "2026-06-30_1530_週次定例",
        "title": "週次定例",
        "startedAt": "2026-06-30T15:30:00+09:00",
        "endedAt": "2026-06-30T16:10:00+09:00",
        "durationSec": 2400,
        "counterpartName": "田中",
        "hasTranscript": True,
        "excerpt": e["excerpt"],
    }
    assert e["excerpt"].startswith("[00:12]")


def test_session_entry_pending_and_legacy_metadata(tmp_path):
    # Old schema (no title, etc.) + transcript not yet processed
    d = _make_session(tmp_path, "2026-07-01_1130_meeting", metadata="{}")
    e = session_entry(d)
    assert e["hasTranscript"] is False
    assert e["excerpt"] == ""
    assert e["title"] == ""
    assert e["counterpartName"] == ""


def test_session_entry_broken_metadata_is_ignored(tmp_path):
    d = _make_session(tmp_path, "2026-07-01_1200_meeting", metadata="{broken json")
    assert session_entry(d) is None


# --- build_index ---


def test_build_index_sorted_newest_first():
    entries = [
        {"dir": "a", "startedAt": "2026-06-29T10:00:00+09:00"},
        {"dir": "c", "startedAt": "2026-07-01T10:00:00+09:00"},
        {"dir": "b", "startedAt": "2026-06-30T10:00:00+09:00"},
    ]
    idx = build_index(entries, generated_at="2026-07-02T18:00:00+09:00")
    assert idx["schemaVersion"] == SCHEMA_VERSION
    assert idx["generatedAt"] == "2026-07-02T18:00:00+09:00"
    assert [e["dir"] for e in idx["sessions"]] == ["c", "b", "a"]


def test_build_index_missing_started_at_falls_back_to_dir():
    entries = [
        {"dir": "2026-07-01_1000_meeting", "startedAt": ""},
        {"dir": "2026-07-01_1100_meeting", "startedAt": ""},
    ]
    idx = build_index(entries, generated_at="x")
    assert [e["dir"] for e in idx["sessions"]] == [
        "2026-07-01_1100_meeting",
        "2026-07-01_1000_meeting",
    ]


# --- write_index ---


def test_write_index_rebuilds_from_scratch(tmp_path):
    _make_session(
        tmp_path,
        "2026-06-30_1530_週次定例",
        metadata=json.dumps({"startedAt": "2026-06-30T15:30:00+09:00"}),
        transcript=_TRANSCRIPT,
    )
    _make_session(tmp_path, "2026-07-01_1130_meeting", metadata="{}")
    _make_session(tmp_path, "2026-07-01_1200_meeting", metadata="{broken")  # ignored
    (tmp_path / "not_a_session").mkdir()  # no metadata.json -> ignored

    # A stale index left behind is replaced by the full rebuild
    (tmp_path / "index.json").write_text('{"stale": true}', encoding="utf-8")

    path = write_index(tmp_path)
    assert path == tmp_path / "index.json"
    idx = json.loads(path.read_text(encoding="utf-8"))
    assert idx["schemaVersion"] == SCHEMA_VERSION
    assert "stale" not in idx
    dirs = [e["dir"] for e in idx["sessions"]]
    assert dirs == ["2026-07-01_1130_meeting", "2026-06-30_1530_週次定例"]
    assert not list(tmp_path.glob(".index.json.tmp"))  # no temp file left behind
