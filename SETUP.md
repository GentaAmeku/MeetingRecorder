# Setup

There is no signed release build — you build MeetingRecorder from source in
Xcode. This is written as a checklist you can follow yourself, or hand to a
coding agent. [SETUP.ja.md](SETUP.ja.md) has the same steps in Japanese.

## 1. Prerequisites

- macOS 15.6 (Sequoia) or later.
- Xcode 26 or later (App Store, or developer.apple.com), with the macOS SDK. Tested with Xcode 26.4.
- An Apple ID added to Xcode (Xcode → Settings → Accounts) — a free Personal
  Team is enough for local builds and running the app on your own Mac.
- To use transcription: Apple Silicon, plus [uv](https://docs.astral.sh/uv/)
  (`brew install uv` or see uv's own install docs).

## 2. Clone

```sh
git clone https://github.com/GentaAmeku/MeetingRecorder.git
cd MeetingRecorder
```

## 3. Set your own Team ID and bundle identifier

The Xcode project has no Team ID or bundle identifier baked in — they come
from an untracked `Local.xcconfig` file, so your values never end up in git.

```sh
cp MeetingRecorder/Configuration/Local.xcconfig.example MeetingRecorder/Configuration/Local.xcconfig
```

Edit `MeetingRecorder/Configuration/Local.xcconfig`:

```
DEVELOPMENT_TEAM = YOUR_TEAM_ID
MEETING_RECORDER_BUNDLE_ID_PREFIX = com.yourname
```

- `DEVELOPMENT_TEAM`: your Apple Developer Team ID. Find it in Xcode →
  Settings → Accounts → (your Apple ID) → your team → "Team ID", or on
  developer.apple.com's Membership Details page. You can also leave it
  blank and pick a team from Xcode's Signing & Capabilities tab after
  opening the project instead.
- `MEETING_RECORDER_BUNDLE_ID_PREFIX`: any reverse-DNS prefix you control,
  e.g. `com.yourname`. The three targets become `<prefix>.MeetingRecorder`,
  `<prefix>.MeetingRecorderTests` and `<prefix>.MeetingRecorderUITests`.

Without this file, the project still opens and builds — it just uses an
empty team and the placeholder prefix `com.example`, which is enough to
build unsigned or for CI but not to install on your own Mac. macOS ties the
microphone/screen-recording permission grant to the bundle identifier + Team
ID pair (its "designated requirement"), so **keep the same values across
rebuilds** or you'll have to re-grant permissions each time they change.

## 4. Open and build

```sh
open MeetingRecorder/MeetingRecorder.xcodeproj
```

Select the **MeetingRecorder** scheme and press Run (⌘R). The first launch
will ask for microphone and screen-recording permission — see step 6.

From the command line instead (this is what CI runs too):

```sh
xcodebuild build \
  -project MeetingRecorder/MeetingRecorder.xcodeproj \
  -scheme MeetingRecorder \
  -configuration Debug \
  -destination 'platform=macOS'
```

On a machine with 16GB of RAM or less, keep the build's parallelism down
(`-jobs 4` or lower) if you build from the command line, and remove
`DerivedData`/`build/` folders once you're done — Xcode's derived data for
this project can otherwise use a few hundred MB to a few GB.

To reinstall after code changes without going through Xcode's UI each time,
`scripts/install_app.sh` builds a Release build and copies it to
`/Applications` (asks for `sudo` if needed).

## 5. Set up transcription (optional)

Recording works without this section; you'll just get `mic.wav` /
`system.wav` and no transcript.

```sh
cd postprocess
uv sync
```

This creates `postprocess/.venv/bin/postprocess`. The app finds this CLI
automatically — `scripts/install_app.sh` (if you use it instead of step 4)
runs `uv sync --frozen` here and passes this absolute path to the build as
the `POSTPROCESS_CLI_PATH` build setting, which the app reads via
Info.plist. There's no settings screen to pick it by hand.

If you run the app straight from Xcode (⌘R) for development instead of
going through `scripts/install_app.sh`, that build never gets the CLI path
baked in, so transcription will report the tool as missing. As a
developer-only workaround, you can override the CLI path for that one build
(bundle id is the prefix from step 3 + `.MeetingRecorder`) by running this
**from the repository root**. An override that isn't executable is ignored,
and the path baked in at install time is used instead:

```sh
defaults write <prefix>.MeetingRecorder postprocessCLIPathOverride "$(pwd)/postprocess/.venv/bin/postprocess"
```

To remove the override:

```sh
defaults delete <prefix>.MeetingRecorder postprocessCLIPathOverride
```

Whenever it can't run (e.g. a required model isn't downloaded), both the
Settings panel and the model sheet point that out.

Then, from the app: **⚙ (Settings) → "Download Models…"**. This downloads:

- **Whisper** (`mlx-community/whisper-large-v3-turbo`, ~1.5GB) — required
  for any transcription.
- **Speaker separation** (sherpa-onnx's pyannote-segmentation-3.0 +
  3D-Speaker ERes2Net models, ~45MB total) — optional; without it, every
  participant on the other side is rendered as a single "Other" (or your `otherName`).

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for each model's
license. The upstream `pyannote/segmentation-3.0` model on Hugging Face is
gated (login + accepting its terms), but this app never talks to Hugging
Face for it — both the in-app downloader and the script below fetch the
same weights, converted to ONNX, from `sherpa-onnx`'s own GitHub release
assets, so no Hugging Face account is needed for diarization at all.

If you'd rather fetch the speaker-separation models by hand:

```sh
scripts/download_diarization_models.sh
```

## 6. Grant permissions

The first recording and the first transcription each trigger their own
permission prompt:

- **Microphone** — for your own voice.
- **Screen & System Audio Recording** — for the other side's voice (the
  single-stream capture needs this even though no video is kept; without it
  the microphone can't be recorded either). System Settings → Privacy &
  Security → Screen & System Audio Recording.
- **Files and Folders — Documents Folder** — this is the base case, and
  macOS prompts for it automatically the first time the app or the
  transcription subprocess reads/writes under `~/Documents/MeetingRecorder`.
  Nothing to configure ahead of time.
- **Full Disk Access** (last resort — only if transcription still fails with
  a permission error after granting the above). A plain folder outside the
  protected set (Desktop/Documents/Downloads/iCloud Drive, …) needs no
  permission at all, so this is for the opposite case: the `postprocess`
  CLI/venv sitting *inside* one of those other protected/synced locations
  (e.g. iCloud Drive) that the Documents-folder grant doesn't cover —
  System Settings → Privacy & Security → Full Disk Access → add
  MeetingRecorder.

## 7. Build and test without signing (CI-style)

```sh
xcodebuild test \
  -project MeetingRecorder/MeetingRecorder.xcodeproj \
  -scheme MeetingRecorder \
  -configuration Debug \
  -destination 'platform=macOS' \
  -only-testing:MeetingRecorderTests \
  CODE_SIGNING_ALLOWED=NO
```

The unit tests launch the app as a test host. If you created
`Local.xcconfig`, that host runs with your real bundle ID and can touch your
own app's settings, so give the test run a throwaway prefix:

```sh
xcodebuild test … MEETING_RECORDER_BUNDLE_ID_PREFIX=com.example.test
```

`-only-testing:MeetingRecorderTests` runs the unit tests only; the UI test
target (`MeetingRecorderUITests`) needs a real logged-in GUI session and
won't run headlessly (this is also why CI only runs the unit tests — see
`.github/workflows/ci.yml`).

```sh
cd postprocess
uv run pytest
```

Neither test suite records audio, runs the models, or needs network access
beyond `uv sync`/model downloads done ahead of time.

## Optional: launch from OnCue

Nothing to set up — the `meetingrecorder://` URL scheme is registered by the
app itself the first time it's built and run. See the "Optional: launch from
OnCue" section in [README.md](README.md) for what it does and how the query
is validated.

## Optional: hand off to an AI agent after transcription

Off by default (Target = "None"), and entirely optional — see the
"Optional: hand off to an AI agent after transcription" section in
[README.md](README.md) for what it does and its risk, and the ⚙ settings
popover for where to configure it. Opening via Orca requires the working
folder to already be registered with Orca.
