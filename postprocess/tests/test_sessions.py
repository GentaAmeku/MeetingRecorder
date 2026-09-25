"""Pure-logic unit tests for session discovery (tmp_path, no real audio needed)."""

from pathlib import Path

from postprocess.sessions import (
    find_sessions,
    is_session_dir,
    latest_session,
    pending_sessions,
)


def _make_session(root: Path, name: str, *, with_transcript: bool = False) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "metadata.json").write_text("{}", encoding="utf-8")
    if with_transcript:
        (d / "transcript.md").write_text("# t", encoding="utf-8")
        (d / "transcript.json").write_text("[]", encoding="utf-8")
    return d


def test_is_session_dir_requires_metadata(tmp_path):
    d = tmp_path / "2026-07-01_1130_meeting"
    d.mkdir()
    assert not is_session_dir(d)
    (d / "metadata.json").write_text("{}", encoding="utf-8")
    assert is_session_dir(d)


def test_find_sessions_sorted_chronologically(tmp_path):
    _make_session(tmp_path, "2026-07-01_1524_meeting")
    _make_session(tmp_path, "2026-07-01_1059_meeting")
    _make_session(tmp_path, "2026-07-01_1130_meeting")
    (tmp_path / "not_a_session").mkdir()  # no metadata.json -> ignored
    names = [p.name for p in find_sessions(tmp_path)]
    assert names == [
        "2026-07-01_1059_meeting",
        "2026-07-01_1130_meeting",
        "2026-07-01_1524_meeting",
    ]


def test_latest_session_returns_newest(tmp_path):
    _make_session(tmp_path, "2026-07-01_1059_meeting")
    _make_session(tmp_path, "2026-07-01_1524_meeting")
    assert latest_session(tmp_path).name == "2026-07-01_1524_meeting"


def test_latest_session_none_when_empty(tmp_path):
    assert latest_session(tmp_path) is None


def test_pending_excludes_sessions_with_transcript(tmp_path):
    _make_session(tmp_path, "2026-07-01_1059_meeting", with_transcript=True)
    _make_session(tmp_path, "2026-07-01_1130_meeting")  # not yet processed
    _make_session(tmp_path, "2026-07-01_1524_meeting", with_transcript=True)
    names = [p.name for p in pending_sessions(tmp_path)]
    assert names == ["2026-07-01_1130_meeting"]


def test_pending_includes_session_when_json_is_missing(tmp_path):
    d = _make_session(tmp_path, "2026-07-01_1059_meeting")
    (d / "transcript.md").write_text("# t", encoding="utf-8")

    assert pending_sessions(tmp_path) == [d]


def test_find_sessions_missing_root(tmp_path):
    assert find_sessions(tmp_path / "nope") == []
