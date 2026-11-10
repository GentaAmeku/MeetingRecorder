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
| NVIDIA `Nemotron-3-Diarization` (as `sakasegawa/Nemotron-3-Diarization-GGUF`, `Nemotron-3-Diarization-99M-Q8_0.gguf`) | Speaker diarization | OpenMDW License Agreement 1.1 (NVIDIA's model card: "ready for commercial or non-commercial use"; the GGUF conversion carries the same license and ships its `LICENSE.OpenMDW-1.1`) | <https://huggingface.co/nvidia/Nemotron-3-Diarization> (license reference), <https://huggingface.co/sakasegawa/Nemotron-3-Diarization-GGUF> (actual download source, fetched by `speech pull`) |

Checked 2026-09-25 (Whisper) and 2026-11-10 (Nemotron 3 Diarization) via each
project's Hugging Face model card. Neither download needs a Hugging Face
account: both repositories are ungated.

## External tool (installed separately, not a Python dependency)

| Tool | License (as published) | Notes |
| --- | --- | --- |
| [speech.cpp](https://github.com/nyosegawa/speech.cpp) (`speech` command) | MIT | Runs the diarization model above. You install it yourself (see SETUP); MeetingRecorder only calls it as a separate process. Its README notes that model weights stay under their authors' licenses. Checked 2026-11-10 |

## Key direct dependencies (`postprocess/pyproject.toml`, resolved in `postprocess/uv.lock`)

| Package | License (as published) | Notes |
| --- | --- | --- |
| `mlx-whisper` | MIT | PyPI license field; source at `ml-explore/mlx-examples` |
| `silero-vad` | MIT | PyPI license field |
| `numpy` | BSD-3-Clause (plus a few small vendored bits under 0BSD/MIT/Zlib/CC0-1.0, per PyPI's license expression) | |
| `soundfile` | BSD-3-Clause | PyPI license field |
| `pytest` (dev only, not shipped) | MIT | Not part of the runtime |

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
