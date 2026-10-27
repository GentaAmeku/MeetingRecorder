# postprocess

A post-processing CLI that turns MeetingRecorder's recorded material
(`mic.wav` / `system.wav` / `metadata.json`) into a self/other conversation
log (Transcript).

Independent of the recording app (Swift). The only contact point is the
filesystem contract of the Recording Session directory and `metadata.json`.
ASR runs locally with MLX Whisper (Apple Silicon). It never summarizes (that's a downstream AI's job).

## Stages (normalize -> transcribe -> diarize -> align -> cleanup)

1. **normalize** — Converts each track to 16kHz mono float (system is downmixed) + light peak normalization.
2. **transcribe** — Passes only the speech regions silero-vad finds to MLX Whisper (default `auto` language detection / `large-v3-turbo`), avoiding hallucinations from silence. mic uses a stricter VAD threshold. The counterpart's name, the meeting title and the [word dictionary](#word-dictionary)'s words go to Whisper as a prompt. Stock lines Whisper invents for silence (「ご視聴ありがとうございました」, "Thanks for watching") are dropped. Each segment's text is then tidied: full-width letters and punctuation normalized, standalone fillers removed, misheard spellings from the dictionary corrected, and a space put between Japanese and Latin words.
3. **diarize** (speaker diarization for the other side) — Runs sherpa-onnx on `system.wav` to get speaker regions, attributes each utterance to whichever speaker overlaps it most, and assigns them to `Other A / Other B …` (in order of first appearance). mic is always self, so it's never a target. **Always on; falls back to a single "Other" if the model isn't installed or fails.**
4. **align** — Merges each track's transcript by time and writes out `transcript.md` / `transcript.json` labeled self/other (A/B/…).
5. **cleanup** — Once both `transcript.md` and `transcript.json` are saved, deletes the input `mic.wav` / `system.wav` by default. Kept when `--keep-source-audio` is given. Whether the index succeeded is never a deletion condition.
6. **index** — Fully rebuilds `recordings/index.json` (the catalog of every session) at the end of each run. An agent can search across sessions in two steps: "read the index -> read the transcript of whichever session it needs".

## Development

Run all of the following commands from inside `postprocess/`.

```sh
cd postprocess
uv sync          # install dependencies
uv run pytest    # unit tests
```

### Running it (generating a Transcript)

```sh
uv run postprocess <session_dir>   # process a given session
uv run postprocess                 # process the latest session
uv run postprocess --all-pending   # batch-process anything pending (missing either Transcript)
uv run postprocess <session_dir> --keep-source-audio # keep the original audio after generating the Transcript
uv run postprocess --sync          # skip transcription, only the later stage (full index.json rebuild)
uv run postprocess --delete-transcribed-audio # batch-delete audio from existing, already-transcribed sessions
```

- The default recordings root is `~/Documents/MeetingRecorder/recordings/` (override with `--recordings-dir`).
- Tune ASR with `--language` (default: `auto`, or the `transcript.language` value from `postprocess-config.json`) and `--model` (default `large-v3-turbo`).
- `--all-pending` is an idempotent entry point that only processes sessions missing `transcript.md` or `transcript.json`. It can be triggered later by a local `launchd` job for automation (a cloud schedule can't reach the local GPU/files).
- `--keep-source-audio` explicitly keeps the input audio for the sessions processed in that run. Without it, both Transcripts are saved and then the audio is deleted as before.
- Re-running on a session that already has both Transcripts but no audio succeeds as already-processed. If audio deletion stopped partway and only one file remains, that one is deleted without overwriting the Transcript.
- Speaker diarization: on by default. `--speakers N` fixes the number of people on the other side (default -1 = auto-estimate), `--no-diarize` disables it, `--diarization-model-dir` overrides where the model lives.
- `--sync` is the recovery entry point for when index.json is missing or stale (idempotent: full scan -> full rewrite). The index is a derived artifact; the source of truth is each session's `metadata.json` / `transcript.*`.

### Configuration: postprocess-config.json

`~/Documents/MeetingRecorder/postprocess-config.json` holds the display names
used in the human-readable Transcript, and the transcription language. If the
file doesn't exist, your name defaults to `Me` and the other side to `Other`.

```json
{
  "schemaVersion": 1,
  "transcript": {
    "selfName": "Yamada",
    "otherName": "Guest",
    "language": "auto"
  }
}
```

- `selfName` is used only in `transcript.md`. Your ID in `transcript.json` stays `self` and never changes. An empty string, a value containing a newline, or a non-string value falls back to `Me`.
- `otherName` is the base name for the other side, used the same way. With a single other speaker it's shown as-is (e.g. `Other`); with multiple, a letter is appended per speaker (e.g. `Other A`, `Other B`). It's ignored for a 1-on-1 session where a counterpart name was set when recording (that real name is used instead). Falls back to `Other` under the same invalid-value rules as `selfName`.
- `language` is the ASR language: `auto` (auto-detect) or a Whisper language code (e.g. `en`, `ja`). Falls back to `auto` when invalid. An explicit `--language` on the command line always overrides this.
- Unknown keys are skipped when reading.
- `dictionary` (a separate section) chooses the [word dictionary](#word-dictionary): `{"path": "~/words.json"}` reads another file, `{"enabled": false}` turns it off. Without the section, Tsuzuri's dictionary is used if it exists.

### Word dictionary

A word dictionary lists the words your meetings use and how they get misheard, so the transcript spells them your way. It uses the format of [Tsuzuri](https://github.com/GentaAmeku/Tsuzuri) (the same author's dictation app), and by default `~/Library/Application Support/Tsuzuri/dictionary.json` is read, so words added while dictating help meetings too. The file is only read, never written. Without it, transcription runs as before.

```json
{
  "version": 1,
  "entries": [
    {"surface": "Claude Code", "from": ["クロードコード"], "hint": true, "pinned": false},
    {"surface": "Vitest", "from": ["Bテスト"], "hint": true, "pinned": true}
  ],
  "fillers": ["えーと", "あのー"]
}
```

- `surface` is how the word should be written; `from` lists the spellings Whisper produces instead.
- **Hints**: words with `hint: true` go to Whisper's `initial_prompt` before transcription — the counterpart's name and the meeting title first, then pinned words, words added in the last 14 days and the most used in the last 30 days (from Tsuzuri's `usage.json` next to the dictionary), as many as fit in 200 tokens.
- **Corrections**: after transcription, `from` spellings are replaced with `surface`. Where a replacement may apply is decided by the kind of characters at its ends, because Japanese has no spaces between words: a katakana spelling only when no katakana touches it, a Latin spelling only when no letter or digit touches it. Spellings with kanji or hiragana are never used (homophones are too common). A Latin `surface` written in another case is also corrected (PNPM → pnpm).
- **Fillers**: `fillers` are removed only where they stand alone — at the start of a sentence or after 「、」, followed by 「、」 or a space.
- `--dictionary <path>` reads another file for one run; `--no-dictionary` transcribes without it.
- On the 40 test sentences from Tsuzuri's evaluation (one speaker, read into a MacBook microphone), the character error rate went from 13.5% to 4.6% and tech terms spelled correctly from 52% to 84%. Meeting audio — other people's voices, overlap, long conversations — may gain less.

### Model management (status check / download)

The CLI owns model status checks and downloads; the recording app calls it to show the status.

```sh
uv run postprocess --model-status                     # show status (missing/ready, etc.)
uv run postprocess --model-status --json              # as JSON (for the recording app)
uv run postprocess --download-models --only whisper     # download only Whisper (progress as JSON Lines)
uv run postprocess --download-models --only diarization # download only speaker diarization
```

- Status is one of `missing / downloading / ready / error`. Whisper is judged by the completeness of the HF cache; speaker diarization by whether its 2 files are present.
- **Prevents implicit downloads**: running transcription while Whisper isn't downloaded stops with "run `--download-models --only whisper` first" (exit 2), instead of silently pulling down 1.5GB.

### Getting the speaker-diarization model (manual fallback)

Splitting the other side into `Other A / Other B …` needs the sherpa-onnx models (~45MB total, no HuggingFace login required). **It still works without them** (falling back to a single "Other"). `--download-models --only diarization` above is the primary path, but you can also fetch it with bash:

```sh
scripts/download_diarization_models.sh    # default: ~/Documents/MeetingRecorder/models/diarization
```

Prerequisite: **use earphones** (to keep the other side's voice from leaking into the mic).

### Automation

- **Manual batch**: `uv run --project . postprocess --all-pending`. You can also delegate running the CLI -> reading `transcript.md` -> summarizing the meeting notes to an AI agent (the specific skill/agent setup is up to your own environment).
- **Background automation via launchd, etc. can be blocked by TCC**, since the recordings/repo/venv live under `~/Documents`, each binary may need its own Full Disk Access grant. Running via a terminal or an interactive agent (i.e. as a child of an already-authorized process) isn't restricted this way.
