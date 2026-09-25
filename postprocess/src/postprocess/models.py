"""Model management: status detection and downloads.

Status detection and downloading are owned by the CLI (here), so the
recording app can surface whether a model is needed, already downloaded, or
in progress. Status is one of 4 values: missing/downloading/ready/error.
- Whisper: judged by the completeness of the HF cache (tries the same
  snapshot_download as mlx_whisper with local_files_only). This avoids
  mistaking an incomplete download for ready just because the directory exists.
- Speaker diarization (sherpa-onnx): judged by the presence of its 2 files
  (diarize.models_present).

Download progress is streamed to stdout as JSON Lines, which the caller (the
recording app) turns into a % bar.
"""

from __future__ import annotations

import json
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from .diarize import (
    DEFAULT_MODEL_DIR as DIARIZATION_MODEL_DIR,
    EMBEDDING_MODEL,
    SEGMENTATION_MODEL,
    models_present,
)
from .transcribe import DEFAULT_MODEL as WHISPER_REPO

WHISPER_ID = "whisper"
DIARIZATION_ID = "diarization"

# Speaker-diarization models (sherpa-onnx public release, no HF login needed).
_SEG_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
_EMB_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
# Progress denominator (seg tar ~6.8MB + emb ~39.6MB).
_DIA_TOTAL_BYTES = 46_500_000


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
            "Speaker diarization (sherpa-onnx)",
            "~45MB",
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
            import shutil

            shutil.rmtree(
                DIARIZATION_MODEL_DIR / SEGMENTATION_MODEL.parent, ignore_errors=True
            )
            (DIARIZATION_MODEL_DIR / EMBEDDING_MODEL).unlink(missing_ok=True)
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
    """Downloads the sherpa-onnx models to the default path (streamed via urllib, with progress)."""
    DIARIZATION_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    _emit({"model": DIARIZATION_ID, "state": "downloading", "pct": 0})
    done = [0]  # cumulative bytes (shared via closure)

    def _progress(chunk: int) -> None:
        done[0] += chunk
        pct = int(done[0] * 100 / _DIA_TOTAL_BYTES)
        _emit({
            "model": DIARIZATION_ID,
            "state": "downloading",
            "pct": max(0, min(99, pct)),
            "downloaded_mb": round(done[0] / 1_000_000),
            "total_mb": round(_DIA_TOTAL_BYTES / 1_000_000),
        })

    # segmentation (tar.bz2 -> extracted)
    seg_dir = DIARIZATION_MODEL_DIR / SEGMENTATION_MODEL.parent
    if not (DIARIZATION_MODEL_DIR / SEGMENTATION_MODEL).exists():
        with tempfile.NamedTemporaryFile(suffix=".tar.bz2", delete=True) as tmp:
            _stream_to_file(_SEG_URL, Path(tmp.name), _progress)
            with tarfile.open(tmp.name, "r:bz2") as tar:
                tar.extractall(DIARIZATION_MODEL_DIR)
        if not (DIARIZATION_MODEL_DIR / SEGMENTATION_MODEL).exists():
            raise RuntimeError(f"Failed to extract segmentation: {seg_dir}")

    # embedding (a single .onnx)
    emb_path = DIARIZATION_MODEL_DIR / EMBEDDING_MODEL
    if not emb_path.exists():
        _stream_to_file(_EMB_URL, emb_path, _progress)


def _stream_to_file(url: str, dest: Path, progress) -> None:
    """Streams a URL to dest, calling progress(bytes) for each chunk."""
    req = urllib.request.Request(url, headers={"User-Agent": "MeetingRecorder"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            progress(len(chunk))
