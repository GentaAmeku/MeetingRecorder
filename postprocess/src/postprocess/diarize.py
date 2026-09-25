"""diarize stage: runs speaker diarization on system.wav to get speaker regions.

The engine is sherpa-onnx's OfflineSpeakerDiarization (pyannote segmentation +
speaker embedding + clustering, all ONNX). Only the system track is a target
(mic is always self = a single speaker, so it's never diarized).

Designed to always run and never break:
- If the model isn't at the default path / sherpa_onnx isn't installed /
  loading or running fails -> returns None. The caller
  (align.assign_speakers) falls back None to a single "other" bucket.
- For that reason, importing sherpa_onnx is deferred, so the core
  transcription still works in an environment where it isn't installed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .segments import SpeakerSegment

# The model lives under the local personal app's Documents folder.
# Keep this path aligned with the in-app download destination for the next phase (turning this into an app).
DEFAULT_MODEL_DIR = Path.home() / "Documents" / "MeetingRecorder" / "models" / "diarization"

# Filenames the download script places (sherpa-onnx public models).
# segmentation ends up as model.onnx inside a folder after extracting the tar.bz2.
SEGMENTATION_MODEL = Path("sherpa-onnx-pyannote-segmentation-3-0") / "model.onnx"
EMBEDDING_MODEL = Path("3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx")

# Clustering threshold (higher merges more speakers together). Measured
# against real meetings (2 people on the other side, Japanese, meeting-app
# compressed audio): 0.5 over-splits into 10 people, 0.9 converges on the
# real headcount. Raising it to 1.0 over-merges everyone into one, so the
# default is 0.9.
DEFAULT_CLUSTER_THRESHOLD = 0.9


def models_present(model_dir: Path = DEFAULT_MODEL_DIR) -> bool:
    """Whether the full diarization model set is present at the default path."""
    return (model_dir / SEGMENTATION_MODEL).exists() and (
        model_dir / EMBEDDING_MODEL
    ).exists()


def diarize_system(
    audio: np.ndarray,
    sr: int,
    *,
    model_dir: Path = DEFAULT_MODEL_DIR,
    num_speakers: int = -1,
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> list[SpeakerSegment] | None:
    """Diarizes a 16kHz mono float system waveform.

    Returns speaker regions (start/end/speaker ID) ordered by start time.
    Returns None if the model isn't installed, isn't supported, or diarization
    fails, so the caller can fall back to a single bucket.

    num_speakers: number of people on the other side. -1 auto-estimates (via
    the clustering threshold); a positive value fixes it.
    cluster_threshold: clustering threshold used for auto-estimation (higher merges more).
    """
    if not models_present(model_dir):
        return None
    try:
        import sherpa_onnx
    except ImportError:
        return None

    seg_model = str(model_dir / SEGMENTATION_MODEL)
    emb_model = str(model_dir / EMBEDDING_MODEL)
    try:
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=seg_model
                ),
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=emb_model),
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=num_speakers, threshold=cluster_threshold
            ),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )
        sd = sherpa_onnx.OfflineSpeakerDiarization(config)
    except Exception:
        return None

    # The diarizer requires the model's specific sample rate (16k). The
    # caller already normalizes to TARGET_SR, but fall back safely if it
    # ever mismatches.
    if sr != sd.sample_rate:
        return None

    try:
        result = sd.process(audio.astype(np.float32)).sort_by_start_time()
    except Exception:
        return None

    return [SpeakerSegment(r.start, r.end, r.speaker) for r in result]
