"""Unit tests for model management (building status / JSON / download contract).

Excludes an actual download (bandwidth, time). Status detection depends on
the real environment, so this only verifies it's "one of the 4 states", while
locking down the deterministic parts: id/size/JSON schema.
"""

import json

from postprocess.models import (
    DIARIZATION_ID,
    WHISPER_ID,
    download_model,
    model_status,
    status_json,
)

_VALID_STATES = {"missing", "downloading", "ready", "error"}


def test_model_status_has_two_known_models():
    statuses = model_status()
    ids = [m.id for m in statuses]
    assert ids == [WHISPER_ID, DIARIZATION_ID]


def test_model_status_fields():
    by_id = {m.id: m for m in model_status()}
    assert by_id[WHISPER_ID].size_label == "~1.5GB"
    assert by_id[DIARIZATION_ID].size_label == "~45MB"
    for m in by_id.values():
        assert m.state in _VALID_STATES
        assert m.name  # has a display name


def test_status_json_is_valid_array():
    payload = json.loads(status_json())
    assert isinstance(payload, list) and len(payload) == 2
    for entry in payload:
        assert set(entry.keys()) == {"id", "name", "size_label", "state"}
        assert entry["state"] in _VALID_STATES


def test_download_unknown_model_emits_error_line(capsys):
    rc = download_model("bogus")
    assert rc == 1
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    obj = json.loads(lines[-1])
    assert obj["model"] == "bogus"
    assert obj["state"] == "error"
