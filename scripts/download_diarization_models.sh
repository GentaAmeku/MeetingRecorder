#!/usr/bin/env bash
#
# Downloads the speaker-diarization (sherpa-onnx) models to the default path.
#
#   scripts/download_diarization_models.sh [MODEL_DIR]
#
# Default MODEL_DIR: ~/Documents/MeetingRecorder/models/diarization
#   - sherpa-onnx-pyannote-segmentation-3-0/model.onnx  (speaker segmentation)
#   - 3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx (speaker embedding)
#
# Both come from sherpa-onnx's public releases (no HuggingFace login needed).
# Keep this layout aligned with diarize.py's DEFAULT_MODEL_DIR for a future in-app download flow.
set -euo pipefail

MODEL_DIR="${1:-$HOME/Documents/MeetingRecorder/models/diarization}"
SEG_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMB_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

if [ -f "sherpa-onnx-pyannote-segmentation-3-0/model.onnx" ]; then
  echo "segmentation: already present (skip)"
else
  echo "segmentation: downloading…"
  curl -fSL -o seg.tar.bz2 "$SEG_URL"
  tar xjf seg.tar.bz2
  rm -f seg.tar.bz2
fi

if [ -f "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx" ]; then
  echo "embedding: already present (skip)"
else
  echo "embedding: downloading…"
  curl -fSL -O "$EMB_URL"
fi

echo "done: $MODEL_DIR"
