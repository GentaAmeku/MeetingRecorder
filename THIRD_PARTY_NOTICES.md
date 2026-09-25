# Third-Party Notices

MeetingRecorder does not bundle any of the models or libraries below; the
setup steps in [README.md](README.md) download them, and `postprocess/uv.lock`
pins the exact versions. This file records what each one's own license page
said when checked (dates below), so you can confirm your use is covered
before you rely on it. It is not legal advice — read the linked license
yourself, especially before any commercial or redistribution use.

## Models

| Model | Used for | License (as published) | Source |
| --- | --- | --- | --- |
| `mlx-community/whisper-large-v3-turbo` | Speech-to-text (transcription) | MIT (the upstream `openai/whisper-large-v3-turbo` model card states "License: mit"; the MLX conversion carries the same weights) | <https://huggingface.co/openai/whisper-large-v3-turbo>, <https://huggingface.co/mlx-community/whisper-large-v3-turbo> |
| `pyannote/segmentation-3.0` | Speaker segmentation (diarization) | MIT (per the model card). The **original** upload on Hugging Face is **gated** (login + accepting its terms), but this app never fetches it from there — it downloads the same weights, converted to ONNX, from `sherpa-onnx`'s own GitHub release assets, which carries no such gate | <https://huggingface.co/pyannote/segmentation-3.0> (license reference only — not where this app downloads it from), <https://github.com/k2-fsa/sherpa-onnx/releases> (actual download source) |
| 3D-Speaker `ERes2Net` (`3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx`) | Speaker embedding (diarization) | Apache License 2.0 (the `modelscope/3D-Speaker` repository that publishes this model is Apache-2.0 licensed) | <https://github.com/modelscope/3D-Speaker>, distributed as an ONNX export via sherpa-onnx's release assets: <https://github.com/k2-fsa/sherpa-onnx/releases> |

Checked 2026-09-25 via each project's Hugging Face model card / GitHub
`LICENSE` file. `pyannote/segmentation-3.0`'s Hugging Face gating (a free
account + accepting its terms) applies only if you go fetch the original
upload yourself; this app's downloader and `scripts/download_diarization_models.sh`
both use `sherpa-onnx`'s ungated GitHub release redistribution instead, so
using this app for diarization needs no Hugging Face account.

## Key direct dependencies (`postprocess/pyproject.toml`, resolved in `postprocess/uv.lock`)

| Package | License (as published) | Notes |
| --- | --- | --- |
| `mlx-whisper` | MIT | PyPI license field; source at `ml-explore/mlx-examples` |
| `sherpa-onnx` / `sherpa-onnx-core` | Apache License 2.0 | PyPI page states "Apache licensed, as found in the LICENSE file"; the wheel bundles a compiled `onnxruntime` — its own license is Apache-2.0/MIT depending on backend, see the `sherpa-onnx` repository's `LICENSE` and any bundled `NOTICE` for the full list of statically-linked components |
| `silero-vad` | MIT | PyPI license field |
| `numpy` | BSD-3-Clause (plus a few small vendored bits under 0BSD/MIT/Zlib/CC0-1.0, per PyPI's license expression) | |
| `soundfile` | BSD-3-Clause | PyPI license field |
| `pytest` (dev only, not shipped) | MIT | Not part of the runtime |

`pyannote.audio` is **not** a direct dependency of `postprocess` (diarization
runs through `sherpa-onnx`'s ONNX models, not the `pyannote.audio` Python
package) — it is listed here only because the segmentation model above is
published under the `pyannote` organization. If you swap in the
`pyannote.audio` Python package yourself, its repository
(`pyannote/pyannote-audio`) is MIT-licensed as shown on its GitHub sidebar,
but check the specific version you use.

`mlx-whisper`'s own dependency tree (`mlx`, `numba`, `tiktoken`, `torch`,
`torchaudio`, and the CUDA/NVIDIA packages that `uv.lock` resolves for
non-Apple platforms) is not re-checked here one by one — run
`uv run --with pip-licenses pip-licenses` (after `uv sync` in `postprocess/`)
if you need the full transitive list for your own compliance review.

## Not checked

- Every transitive dependency in `postprocess/uv.lock` beyond the direct
  ones listed above (the CUDA/NVIDIA packages are unused on macOS and exist
  only because `uv.lock` resolves a cross-platform dependency graph).
- Whether your specific use (personal, internal, commercial, redistributed)
  satisfies each license. Read the license pages linked above yourself.
