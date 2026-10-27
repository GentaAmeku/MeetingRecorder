"""Unit tests for reading metadata.json (including counterpartName backward compatibility)."""

import json
from pathlib import Path

from postprocess.metadata import load_session_meta


def _write(tmp_path: Path, data: dict) -> Path:
    (tmp_path / "metadata.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_reads_counterpart_name(tmp_path):
    d = _write(tmp_path, {
        "schemaVersion": 3,
        "title": "定例",
        "counterpartName": "田中",
        "startedAt": "2026-06-30T15:30:00+09:00",
        "durationSec": 60,
        "devices": {"micDeviceName": "EarPods"},
    })
    meta = load_session_meta(d)
    assert meta.counterpart_name == "田中"
    assert meta.title == "定例"


def test_old_schema_without_counterpart_defaults_empty(tmp_path):
    # Recordings from schemaVersion 2 or earlier have no counterpartName -> "" for backward compatibility.
    d = _write(tmp_path, {
        "schemaVersion": 2,
        "title": "meeting",
        "startedAt": "2026-06-30T15:30:00+09:00",
        "durationSec": 60,
        "devices": {"micDeviceName": "EarPods"},
    })
    meta = load_session_meta(d)
    assert meta.counterpart_name == ""


def test_meeting_hint_terms_are_the_name_then_the_title():
    from postprocess.metadata import SessionMeta, meeting_hint_terms

    meta = SessionMeta(started_at="", duration_sec=0, mic_device_name="", title=" 週次定例 ", counterpart_name="田中")
    assert meeting_hint_terms(meta) == ["田中", "週次定例"]
    assert meeting_hint_terms(SessionMeta(started_at="", duration_sec=0, mic_device_name="")) == []
