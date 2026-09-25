from pathlib import Path

import pytest
import postprocess as cli

from postprocess.cleanup import (
    delete_source_audio,
    delete_transcribed_audio,
    session_action,
)
from postprocess.config import PostprocessConfig


def _make_session(
    root: Path,
    name: str,
    *,
    audio: tuple[str, ...] = (),
    transcripts: tuple[str, ...] = (),
) -> Path:
    session = root / name
    session.mkdir(parents=True)
    (session / "metadata.json").write_text("{}", encoding="utf-8")
    for filename in audio:
        (session / filename).write_bytes(b"audio")
    for filename in transcripts:
        (session / filename).write_text("transcript", encoding="utf-8")
    return session


@pytest.mark.parametrize(
    ("audio", "transcripts", "expected"),
    [
        (("mic.wav", "system.wav"), (), "transcribe"),
        (("mic.wav",), (), "transcribe"),
        (
            ("mic.wav", "system.wav"),
            ("transcript.md", "transcript.json"),
            "transcribe",
        ),
        (("system.wav",), ("transcript.md", "transcript.json"), "cleanup"),
        ((), ("transcript.md", "transcript.json"), "complete"),
        ((), ("transcript.md",), "missing"),
    ],
)
def test_session_action(tmp_path, audio, transcripts, expected):
    session = _make_session(tmp_path, "session", audio=audio, transcripts=transcripts)
    assert session_action(session) == expected


def test_delete_source_audio_requires_both_transcripts(tmp_path):
    session = _make_session(
        tmp_path,
        "session",
        audio=("mic.wav", "system.wav"),
        transcripts=("transcript.md",),
    )

    with pytest.raises(ValueError, match="Both transcript.md and transcript.json"):
        delete_source_audio(session)

    assert (session / "mic.wav").is_file()
    assert (session / "system.wav").is_file()


def test_delete_source_audio_deletes_only_existing_audio(tmp_path):
    session = _make_session(
        tmp_path,
        "session",
        audio=("system.wav",),
        transcripts=("transcript.md", "transcript.json"),
    )

    assert delete_source_audio(session) == (session / "system.wav",)
    assert not (session / "system.wav").exists()
    assert (session / "transcript.md").is_file()
    assert (session / "transcript.json").is_file()


def test_delete_transcribed_audio_skips_incomplete_sessions(tmp_path):
    complete = _make_session(
        tmp_path,
        "2026-08-07_1000_complete",
        audio=("mic.wav", "system.wav"),
        transcripts=("transcript.md", "transcript.json"),
    )
    incomplete = _make_session(
        tmp_path,
        "2026-08-07_1100_incomplete",
        audio=("mic.wav", "system.wav"),
        transcripts=("transcript.md",),
    )

    assert delete_transcribed_audio(tmp_path) == (1, 2)
    assert not (complete / "mic.wav").exists()
    assert not (complete / "system.wav").exists()
    assert (incomplete / "mic.wav").is_file()
    assert (incomplete / "system.wav").is_file()


def _stub_config(monkeypatch):
    """Replaces config loading with the defaults, so tests that run the whole CLI
    never read the real file at ~/Documents/.../postprocess-config.json."""
    monkeypatch.setattr(cli, "load_config", lambda: PostprocessConfig())


def test_main_deletes_audio_after_transcript_outputs_are_written(tmp_path, monkeypatch):
    session = _make_session(
        tmp_path,
        "2026-08-07_1000_session",
        audio=("mic.wav", "system.wav"),
    )

    def write_transcripts(session_dir, **_):
        md_path = session_dir / "transcript.md"
        json_path = session_dir / "transcript.json"
        md_path.write_text("transcript", encoding="utf-8")
        json_path.write_text("[]", encoding="utf-8")
        return md_path, json_path

    monkeypatch.setattr(cli, "process_session", write_transcripts)
    monkeypatch.setattr(cli, "_whisper_ready", lambda: True)
    monkeypatch.setattr(cli, "diarize_system_available", lambda _: True)
    _stub_config(monkeypatch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "postprocess",
            str(session),
            "--recordings-dir",
            str(tmp_path),
        ],
    )

    cli.main()

    assert (session / "transcript.md").is_file()
    assert (session / "transcript.json").is_file()
    assert not (session / "mic.wav").exists()
    assert not (session / "system.wav").exists()


def test_main_keeps_audio_when_requested(tmp_path, monkeypatch):
    session = _make_session(
        tmp_path,
        "2026-08-14_1000_session",
        audio=("mic.wav", "system.wav"),
    )

    def write_transcripts(session_dir, **_):
        md_path = session_dir / "transcript.md"
        json_path = session_dir / "transcript.json"
        md_path.write_text("transcript", encoding="utf-8")
        json_path.write_text("[]", encoding="utf-8")
        return md_path, json_path

    monkeypatch.setattr(cli, "process_session", write_transcripts)
    monkeypatch.setattr(cli, "_whisper_ready", lambda: True)
    monkeypatch.setattr(cli, "diarize_system_available", lambda _: True)
    _stub_config(monkeypatch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "postprocess",
            str(session),
            "--keep-source-audio",
            "--recordings-dir",
            str(tmp_path),
        ],
    )

    cli.main()

    assert (session / "transcript.md").is_file()
    assert (session / "transcript.json").is_file()
    assert (session / "mic.wav").is_file()
    assert (session / "system.wav").is_file()


def test_main_completed_session_without_audio_is_idempotent(tmp_path, monkeypatch):
    session = _make_session(
        tmp_path,
        "2026-08-07_1000_session",
        transcripts=("transcript.md", "transcript.json"),
    )
    monkeypatch.setattr(
        cli,
        "_whisper_ready",
        lambda: pytest.fail("must not check Whisper for an already-processed session"),
    )
    _stub_config(monkeypatch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "postprocess",
            str(session),
            "--recordings-dir",
            str(tmp_path),
        ],
    )

    cli.main()

    assert (session / "transcript.md").read_text(encoding="utf-8") == "transcript"
    assert (session / "transcript.json").read_text(encoding="utf-8") == "transcript"


def test_all_pending_processes_valid_sessions_before_reporting_missing_audio(
    tmp_path, monkeypatch
):
    valid = _make_session(
        tmp_path,
        "2026-08-14_1000_valid",
        audio=("mic.wav", "system.wav"),
    )
    missing = _make_session(
        tmp_path,
        "2026-08-14_1100_missing",
        transcripts=("transcript.md",),
    )

    def write_transcripts(session_dir, **_):
        md_path = session_dir / "transcript.md"
        json_path = session_dir / "transcript.json"
        md_path.write_text("transcript", encoding="utf-8")
        json_path.write_text("[]", encoding="utf-8")
        return md_path, json_path

    monkeypatch.setattr(cli, "process_session", write_transcripts)
    monkeypatch.setattr(cli, "_whisper_ready", lambda: True)
    monkeypatch.setattr(cli, "diarize_system_available", lambda _: True)
    _stub_config(monkeypatch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "postprocess",
            "--all-pending",
            "--recordings-dir",
            str(tmp_path),
        ],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 1
    assert (valid / "transcript.md").is_file()
    assert (valid / "transcript.json").is_file()
    assert not (valid / "mic.wav").exists()
    assert not (valid / "system.wav").exists()
    assert (missing / "transcript.md").is_file()
    assert not (missing / "transcript.json").exists()


def test_main_delete_transcribed_audio_cleans_existing_sessions(tmp_path, monkeypatch):
    session = _make_session(
        tmp_path,
        "2026-08-07_1000_session",
        audio=("mic.wav", "system.wav"),
        transcripts=("transcript.md", "transcript.json"),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "postprocess",
            "--delete-transcribed-audio",
            "--recordings-dir",
            str(tmp_path),
        ],
    )

    cli.main()

    assert not (session / "mic.wav").exists()
    assert not (session / "system.wav").exists()


def test_language_defaults_to_config_value_when_not_given_on_cli(tmp_path, monkeypatch):
    session = _make_session(
        tmp_path,
        "2026-08-07_1000_session",
        audio=("mic.wav", "system.wav"),
    )
    captured = {}

    def write_transcripts(session_dir, **kwargs):
        captured["language"] = kwargs["language"]
        md_path = session_dir / "transcript.md"
        json_path = session_dir / "transcript.json"
        md_path.write_text("transcript", encoding="utf-8")
        json_path.write_text("[]", encoding="utf-8")
        return md_path, json_path

    monkeypatch.setattr(cli, "process_session", write_transcripts)
    monkeypatch.setattr(cli, "_whisper_ready", lambda: True)
    monkeypatch.setattr(cli, "diarize_system_available", lambda _: True)
    monkeypatch.setattr(cli, "load_config", lambda: PostprocessConfig(language="en"))
    monkeypatch.setattr(
        "sys.argv",
        ["postprocess", str(session), "--recordings-dir", str(tmp_path)],
    )

    cli.main()

    assert captured["language"] == "en"


def test_explicit_language_flag_overrides_config_value(tmp_path, monkeypatch):
    session = _make_session(
        tmp_path,
        "2026-08-07_1000_session",
        audio=("mic.wav", "system.wav"),
    )
    captured = {}

    def write_transcripts(session_dir, **kwargs):
        captured["language"] = kwargs["language"]
        md_path = session_dir / "transcript.md"
        json_path = session_dir / "transcript.json"
        md_path.write_text("transcript", encoding="utf-8")
        json_path.write_text("[]", encoding="utf-8")
        return md_path, json_path

    monkeypatch.setattr(cli, "process_session", write_transcripts)
    monkeypatch.setattr(cli, "_whisper_ready", lambda: True)
    monkeypatch.setattr(cli, "diarize_system_available", lambda _: True)
    monkeypatch.setattr(cli, "load_config", lambda: PostprocessConfig(language="en"))
    monkeypatch.setattr(
        "sys.argv",
        ["postprocess", str(session), "--language", "ja", "--recordings-dir", str(tmp_path)],
    )

    cli.main()

    assert captured["language"] == "ja"
