"""Unit tests for the diarize stage and the diarization model's download/delete.

speech.cpp itself isn't needed: a small fake `speech` script stands in for it,
answering `models --json`, `diarize`, `pull` and `rm` the way the real command
does, and logging how it was called.
"""

import json
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

import postprocess.diarize as diarize
import postprocess.models as models
from postprocess.diarize import (
    MODEL_NAME,
    diarize_system,
    find_speech,
    models_present,
    parse_catalog_entry,
    parse_segments,
)
from postprocess.segments import SpeakerSegment

_FAKE_SPEECH = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys
    from pathlib import Path

    here = Path(__file__).parent
    args = sys.argv[1:]
    with open(here / "calls.log", "a") as log:
        log.write(json.dumps(args) + "\\n")
    if args[:2] == ["models", "--json"]:
        print((here / "catalog.json").read_text())
    elif args[:1] == ["diarize"]:
        wav = Path(args[-1])
        (here / "wav_seen").write_text(str(wav) + "\\n" + str(wav.exists()))
        code = int((here / "diarize_exit").read_text()) if (here / "diarize_exit").exists() else 0
        if code == 0:
            print((here / "diarize_out.json").read_text())
        sys.exit(code)
    elif args[:1] == ["pull"]:
        sys.stderr.write("Fetching nemotron-3-diarization (106 MB)\\n")
        sys.stderr.write("  53 MB of 106 MB, 50%, 20.0 MB/s\\r  106 MB of 106 MB, 100%, 20.0 MB/s\\n")
        sys.stderr.write("Fetched nemotron-3-diarization in 5 s")
        print(here / "model.gguf")
    elif args[:1] == ["rm"]:
        pass
    """
)


@pytest.fixture
def fake_speech(tmp_path):
    """A fake `speech` command whose model is fetched. Returns its folder (logs and knobs live there)."""
    folder = tmp_path / "speech"
    folder.mkdir()
    script = folder / "speech"
    script.write_text(_FAKE_SPEECH.format(python=sys.executable))
    script.chmod(0o755)
    model = folder / "model.gguf"
    model.write_bytes(b"gguf")
    _write_catalog(folder, fetched=True)
    (folder / "diarize_out.json").write_text(
        json.dumps(
            {
                "file": "x.wav",
                "segments": [
                    {"start": 3.5, "end": 4.0, "speaker": 1},
                    {"start": 0.25, "end": 3.0, "speaker": 0},
                ],
            }
        )
    )
    return folder


def _write_catalog(folder: Path, *, fetched: bool) -> None:
    catalog = {
        "version": "0.10.1",
        "directory": str(folder),
        "models": [
            {"name": "silero-vad", "type": "f32", "files": [{"type": "f32", "path": "/x", "fetched": True}]},
            {
                "name": MODEL_NAME,
                "type": "q8_0",
                "files": [
                    {"type": "f16", "path": str(folder / "other.gguf"), "fetched": True},
                    {"type": "q8_0", "path": str(folder / "model.gguf"), "fetched": fetched},
                ],
            },
        ],
        "old": [],
    }
    (folder / "catalog.json").write_text(json.dumps(catalog))


def _calls(folder: Path) -> list[list[str]]:
    log = folder / "calls.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _audio() -> np.ndarray:
    return np.zeros(16000 * 5, dtype=np.float32)


# ---- parsing -------------------------------------------------------------------


def test_parse_segments_sorts_by_start_and_keeps_speaker_ids():
    out = json.dumps(
        {"file": "a.wav", "segments": [{"start": 2.0, "end": 3.0, "speaker": 1}, {"start": 0.5, "end": 1.5, "speaker": 0}]}
    )
    assert parse_segments(out + "\n") == [
        SpeakerSegment(0.5, 1.5, 0),
        SpeakerSegment(2.0, 3.0, 1),
    ]


def test_parse_segments_of_silence_is_empty():
    assert parse_segments(json.dumps({"file": "a.wav", "segments": []})) == []


def test_parse_catalog_entry_picks_the_default_type():
    catalog = {
        "models": [
            {
                "name": MODEL_NAME,
                "type": "q8_0",
                "files": [{"type": "f16", "path": "/f16"}, {"type": "q8_0", "path": "/q8"}],
            }
        ]
    }
    assert parse_catalog_entry(catalog)["path"] == "/q8"


def test_parse_catalog_entry_without_the_model_is_none():
    assert parse_catalog_entry({"models": [{"name": "silero-vad", "files": []}]}) is None


# ---- locating speech -------------------------------------------------------------


def test_find_speech_uses_an_explicit_executable(fake_speech):
    assert find_speech(fake_speech / "speech") == fake_speech / "speech"


def test_find_speech_rejects_an_explicit_path_that_is_missing(tmp_path):
    assert find_speech(tmp_path / "nope") is None


def test_find_speech_falls_back_to_known_locations(fake_speech, monkeypatch):
    monkeypatch.setattr(diarize.shutil, "which", lambda _: None)
    monkeypatch.setattr(diarize, "KNOWN_SPEECH_LOCATIONS", (Path("/nonexistent/speech"), fake_speech / "speech"))
    assert find_speech() == fake_speech / "speech"


# ---- diarize_system ----------------------------------------------------------------


def test_diarize_system_returns_segments_and_removes_its_temporary_wav(fake_speech):
    segs = diarize_system(_audio(), 16000, speech_bin=fake_speech / "speech")

    assert segs == [SpeakerSegment(0.25, 3.0, 0), SpeakerSegment(3.5, 4.0, 1)]
    wav, existed = (fake_speech / "wav_seen").read_text().splitlines()
    assert existed == "True"  # speech got a real file...
    assert not Path(wav).exists()  # ...which is gone afterwards (it holds voices)
    diarize_call = [c for c in _calls(fake_speech) if c[0] == "diarize"][0]
    # The model is passed as the fetched file, never as a name speech would fetch.
    assert diarize_call[1] == str(fake_speech / "model.gguf")
    assert diarize_call[2:4] == ["--format", "json"]


def test_diarize_system_without_a_fetched_model_never_runs_diarize(fake_speech):
    _write_catalog(fake_speech, fetched=False)

    assert diarize_system(_audio(), 16000, speech_bin=fake_speech / "speech") is None
    assert not [c for c in _calls(fake_speech) if c[0] == "diarize"]


def test_diarize_system_without_speech_is_none(tmp_path):
    assert diarize_system(_audio(), 16000, speech_bin=tmp_path / "nope") is None


def test_diarize_system_is_none_when_speech_fails(fake_speech):
    (fake_speech / "diarize_exit").write_text("1")

    assert diarize_system(_audio(), 16000, speech_bin=fake_speech / "speech") is None
    wav, _ = (fake_speech / "wav_seen").read_text().splitlines()
    assert not Path(wav).exists()


def test_models_present_follows_the_catalog(fake_speech):
    assert models_present(fake_speech / "speech")
    _write_catalog(fake_speech, fetched=False)
    assert not models_present(fake_speech / "speech")


# ---- download / delete (models.py) ------------------------------------------------


def _lines(capsys) -> list[dict]:
    return [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.strip()]


def test_download_diarization_turns_speech_pull_progress_into_lines(fake_speech, monkeypatch, capsys):
    monkeypatch.setattr(models, "find_speech", lambda: fake_speech / "speech")

    assert models.download_model(models.DIARIZATION_ID) == 0

    lines = _lines(capsys)
    pcts = [l["pct"] for l in lines if l["state"] == "downloading"]
    assert pcts == [0, 50, 99]  # 100% is reported as ready, not as 100
    assert lines[-1] == {"model": "diarization", "state": "ready"}
    assert ["pull", MODEL_NAME] in _calls(fake_speech)


def test_download_diarization_without_speech_explains_what_to_install(monkeypatch, capsys):
    monkeypatch.setattr(models, "find_speech", lambda: None)

    assert models.download_model(models.DIARIZATION_ID) == 1

    last = _lines(capsys)[-1]
    assert last["state"] == "error"
    assert "speech.cpp" in last["message"]


def test_delete_diarization_runs_speech_rm(fake_speech, monkeypatch, capsys):
    monkeypatch.setattr(models, "find_speech", lambda: fake_speech / "speech")

    assert models.delete_model(models.DIARIZATION_ID) == 0

    assert ["rm", MODEL_NAME] in _calls(fake_speech)
    assert _lines(capsys)[-1] == {"model": "diarization", "state": "missing"}
