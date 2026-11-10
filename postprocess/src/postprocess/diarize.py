"""diarize stage: runs speaker diarization on system.wav to get speaker regions.

The engine is NVIDIA's Nemotron 3 Diarization (an end-to-end Sortformer model,
up to 8 speakers), run through speech.cpp's `speech diarize` command on the
Mac's GPU (Metal). speech.cpp is a separately installed command-line tool, and
the model file lives in speech.cpp's own model folder. Only the system track is
a target (mic is always self = a single speaker, so it's never diarized).

Designed to always run and never break:
- If `speech` isn't found / the model isn't fetched yet / the run fails ->
  returns None. The caller (align.assign_speakers) falls back None to a single
  "other" bucket.
- It never fetches the model by itself: the model is passed to `speech` as a
  file path that is already on disk, so a missing model can't turn a
  transcription into a silent 100MB download. Fetching is models.py's job
  (`postprocess --download-models --only diarization`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .segments import SpeakerSegment

# The model's name in speech.cpp's catalog (`speech models`).
MODEL_NAME = "nemotron-3-diarization"

# An app launched from Finder has a minimal PATH, so after PATH check where
# speech.cpp's installer and Homebrew put the command.
KNOWN_SPEECH_LOCATIONS = (
    Path.home() / ".local" / "bin" / "speech",
    Path("/opt/homebrew/bin/speech"),
    Path("/usr/local/bin/speech"),
)

# Generous: an hour of audio takes well under a minute on Apple silicon's GPU.
_DIARIZE_TIMEOUT_SEC = 1800
_CATALOG_TIMEOUT_SEC = 30


def find_speech(explicit: str | Path | None = None) -> Path | None:
    """Locates speech.cpp's `speech` command. An explicit path wins; None if not found."""
    if explicit is not None:
        path = Path(explicit).expanduser()
        return path if _is_executable(path) else None
    on_path = shutil.which("speech")
    if on_path:
        return Path(on_path)
    for path in KNOWN_SPEECH_LOCATIONS:
        if _is_executable(path):
            return path
    return None


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def catalog_entry(speech: Path) -> dict | None:
    """The diarization model's file entry in `speech models --json` (path, fetched, size), or None."""
    try:
        out = subprocess.run(
            [str(speech), "models", "--json"],
            capture_output=True,
            text=True,
            timeout=_CATALOG_TIMEOUT_SEC,
            check=True,
        ).stdout
        catalog = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return parse_catalog_entry(catalog) if isinstance(catalog, dict) else None


def parse_catalog_entry(catalog: dict) -> dict | None:
    """Picks the default file of MODEL_NAME out of the catalog `speech models --json` prints."""
    for model in catalog.get("models", []):
        if model.get("name") != MODEL_NAME:
            continue
        files = model.get("files") or []
        default_type = model.get("type")
        for entry in files:
            if entry.get("type") == default_type:
                return entry
        return files[0] if files else None
    return None


def model_path(speech: Path) -> Path | None:
    """The fetched model file, or None if `speech` doesn't know the model or hasn't fetched it."""
    entry = catalog_entry(speech)
    if not entry or not entry.get("fetched") or not entry.get("path"):
        return None
    path = Path(entry["path"])
    return path if path.is_file() else None


def models_present(speech_bin: str | Path | None = None) -> bool:
    """Whether diarization can run: `speech` is installed and the model is fetched."""
    speech = find_speech(speech_bin)
    return speech is not None and model_path(speech) is not None


def parse_segments(stdout: str) -> list[SpeakerSegment]:
    """Turns `speech diarize --format json` output (one object per file and line) into speaker regions."""
    segments: list[SpeakerSegment] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        for s in json.loads(line).get("segments", []):
            segments.append(
                SpeakerSegment(float(s["start"]), float(s["end"]), int(s["speaker"]))
            )
    return sorted(segments, key=lambda s: (s.start, s.end))


def diarize_system(
    audio: np.ndarray,
    sr: int,
    *,
    speech_bin: str | Path | None = None,
) -> list[SpeakerSegment] | None:
    """Diarizes a mono float system waveform.

    Returns speaker regions (start/end/speaker ID) ordered by start time.
    Speaker IDs count from 0 in the order the voices first speak. Returns None
    if speech.cpp or the model isn't installed, or diarization fails, so the
    caller can fall back to a single bucket.
    """
    speech = find_speech(speech_bin)
    if speech is None:
        return None
    model = model_path(speech)
    if model is None:
        return None

    # `speech` reads a WAVE file. Write the same normalized waveform the
    # transcription used to a private temporary file, and always remove it
    # (it holds the other side's voices).
    fd, tmp_name = tempfile.mkstemp(prefix="meetingrecorder-diarize-", suffix=".wav")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        sf.write(tmp, audio.astype(np.float32), sr, subtype="PCM_16")
        result = subprocess.run(
            [str(speech), "diarize", str(model), "--format", "json", str(tmp)],
            capture_output=True,
            text=True,
            timeout=_DIARIZE_TIMEOUT_SEC,
        )
        if result.returncode != 0:
            return None
        return parse_segments(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
    finally:
        tmp.unlink(missing_ok=True)
