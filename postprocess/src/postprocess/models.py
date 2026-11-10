"""Model management: status detection and downloads.

Status detection and downloading are owned by the CLI (here), so the
recording app can surface whether a model is needed, already downloaded, or
in progress. Status is one of 4 values: missing/downloading/ready/error.
- Whisper: judged by the completeness of the HF cache (tries the same
  snapshot_download as mlx_whisper with local_files_only). This avoids
  mistaking an incomplete download for ready just because the directory exists.
- Speaker diarization (Nemotron 3 via speech.cpp): judged by whether the
  `speech` command is installed and reports the model as fetched
  (diarize.models_present). Fetching and removing go through `speech pull` /
  `speech rm`, so the file lives in speech.cpp's own model folder.

Download progress is streamed to stdout as JSON Lines, which the caller (the
recording app) turns into a % bar.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass

from .diarize import MODEL_NAME as DIARIZATION_MODEL_NAME
from .diarize import find_speech, models_present
from .transcribe import DEFAULT_MODEL as WHISPER_REPO

WHISPER_ID = "whisper"
DIARIZATION_ID = "diarization"

# What `speech pull` prints to stderr while fetching, e.g. "  98 MB of 106 MB, 92%, 23.4 MB/s".
_PULL_PROGRESS = re.compile(r"(\d+(?:\.\d+)?) MB of (\d+(?:\.\d+)?) MB, (\d+)%")

SPEECH_MISSING_MESSAGE = (
    "speech.cpp is not installed (the `speech` command was not found). "
    "Install it as SETUP.md describes, then download again."
)


@dataclass(frozen=True)
class ModelStatus:
    id: str
    name: str
    size_label: str
    state: str  # missing | downloading | ready | error


# ---- Status detection -------------------------------------------------------------

def whisper_ready() -> bool:
    """Whether Whisper is fully downloaded in the HF cache (the same check mlx uses)."""
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(WHISPER_REPO, local_files_only=True)
        return True
    except Exception:
        return False


def model_status() -> list[ModelStatus]:
    """Returns the status of every model (detection only, never downloads)."""
    return [
        ModelStatus(
            WHISPER_ID,
            "Whisper (large-v3-turbo)",
            "~1.5GB",
            "ready" if whisper_ready() else "missing",
        ),
        ModelStatus(
            DIARIZATION_ID,
            "Speaker diarization (Nemotron 3)",
            "~106MB",
            "ready" if models_present() else "missing",
        ),
    ]


def status_json() -> str:
    return json.dumps([asdict(m) for m in model_status()], ensure_ascii=False)


# ---- Progress emitter ---------------------------------------------------------

def _emit(obj: dict) -> None:
    """Prints one line of JSON Lines to stdout (read line-by-line by the recording app)."""
    print(json.dumps(obj, ensure_ascii=False), flush=True)


# ---- Download ---------------------------------------------------------

def download_model(model_id: str) -> int:
    """Downloads one model, streaming progress as JSON Lines. 0 on success, 1 on failure."""
    try:
        if model_id == WHISPER_ID:
            _download_whisper()
        elif model_id == DIARIZATION_ID:
            _download_diarization()
        else:
            _emit({"model": model_id, "state": "error", "message": "unknown model"})
            return 1
    except Exception as exc:  # noqa: BLE001 - funneled into an error line per the progress contract
        _emit({"model": model_id, "state": "error", "message": str(exc)})
        return 1
    _emit({"model": model_id, "state": "ready"})
    return 0


def delete_model(model_id: str) -> int:
    """Deletes one model. 0 on success, 1 on failure. Deleted from the Python side since the CLI knows the exact paths."""
    try:
        if model_id == WHISPER_ID:
            from huggingface_hub import scan_cache_dir

            cache = scan_cache_dir()
            hashes = [
                rev.commit_hash
                for repo in cache.repos
                if repo.repo_id == WHISPER_REPO
                for rev in repo.revisions
            ]
            if hashes:
                cache.delete_revisions(*hashes).execute()
        elif model_id == DIARIZATION_ID:
            speech = find_speech()
            if speech is not None:
                subprocess.run(
                    [str(speech), "rm", DIARIZATION_MODEL_NAME],
                    capture_output=True,
                    check=True,
                )
        else:
            _emit({"model": model_id, "state": "error", "message": "unknown model"})
            return 1
    except Exception as exc:  # noqa: BLE001
        _emit({"model": model_id, "state": "error", "message": str(exc)})
        return 1
    _emit({"model": model_id, "state": "missing"})
    return 0


def _download_whisper() -> None:
    """Fetches huggingface_hub's download progress by hooking it into JSON Lines."""
    from huggingface_hub import snapshot_download

    from tqdm.auto import tqdm as _base_tqdm

    class _JsonTqdm(_base_tqdm):
        _last_pct = -1

        def update(self, n=1):
            result = super().update(n)
            total = self.total or 0
            # Only drive the % bar off the large weight file(s).
            if total > 50_000_000:
                pct = int(self.n * 100 / total)
                if pct != _JsonTqdm._last_pct:
                    _JsonTqdm._last_pct = pct
                    _emit({
                        "model": WHISPER_ID,
                        "state": "downloading",
                        "pct": max(0, min(99, pct)),
                        "downloaded_mb": round(self.n / 1_000_000),
                        "total_mb": round(total / 1_000_000),
                    })
            return result

    _emit({"model": WHISPER_ID, "state": "downloading", "pct": 0})
    try:
        snapshot_download(WHISPER_REPO, tqdm_class=_JsonTqdm)
    except TypeError:
        # Older huggingface_hub versions don't support tqdm_class -> fetch without progress.
        snapshot_download(WHISPER_REPO)


def _download_diarization() -> None:
    """Fetches the model with `speech pull`, turning its stderr progress into JSON Lines."""
    speech = find_speech()
    if speech is None:
        raise RuntimeError(SPEECH_MISSING_MESSAGE)
    _emit({"model": DIARIZATION_ID, "state": "downloading", "pct": 0})
    proc = subprocess.Popen(
        [str(speech), "pull", DIARIZATION_MODEL_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    assert proc.stderr is not None
    tail = ""  # the last progress-free text, for the error message
    buffer = b""
    while True:
        chunk = proc.stderr.read1(4096)
        if not chunk:
            break
        buffer += chunk
        # Progress lines end with \r (redrawn in place) or \n.
        *lines, buffer = re.split(rb"[\r\n]", buffer)
        for raw in lines:
            tail = _take_pull_text(raw, tail)
    tail = _take_pull_text(buffer, tail)
    if proc.wait() != 0:
        raise RuntimeError(tail or f"speech pull {DIARIZATION_MODEL_NAME} failed")


def _take_pull_text(raw: bytes, tail: str) -> str:
    """Emits progress for one piece of `speech pull` stderr; returns the latest non-progress text."""
    text = raw.decode("utf-8", "replace").strip()
    if text and not _emit_pull_progress(text):
        return text
    return tail


def _emit_pull_progress(text: str) -> bool:
    """Emits one progress line for a `speech pull` progress text. False if the text isn't progress."""
    m = _PULL_PROGRESS.search(text)
    if not m:
        return False
    done_mb, total_mb, pct = float(m.group(1)), float(m.group(2)), int(m.group(3))
    _emit({
        "model": DIARIZATION_ID,
        "state": "downloading",
        "pct": max(0, min(99, pct)),
        "downloaded_mb": round(done_mb),
        "total_mb": round(total_mb),
    })
    return True
