"""Post-processing CLI.

Transcribes the mic/system tracks of a recording session, merges them
chronologically, and writes out the self/other conversation log as
transcript.md / transcript.json.

The target is chosen one of three ways:
- `postprocess <session_dir>`  … a given session (always overwritten)
- `postprocess`               … the latest session (always overwritten)
- `postprocess --all-pending` … batch-processes anything pending (no transcript.md yet)

At the end of processing, recordings/index.json (the catalog of all
sessions) is fully rebuilt. `postprocess --sync` re-runs only that full
index rebuild, without transcribing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .align import LabeledSegment, assign_speakers, group_turns, merge_tracks
from .audio import load_normalized
from .cleanup import (
    delete_source_audio,
    delete_transcribed_audio,
    session_action,
)
from .config import DEFAULT_OTHER_NAME, DEFAULT_SELF_NAME, load_config, normalize_language
from .diarize import DEFAULT_CLUSTER_THRESHOLD, DEFAULT_MODEL_DIR, diarize_system
from .index import write_index
from .metadata import load_session_meta
from .render import render_json, render_markdown
from .segments import Segment
from .sessions import DEFAULT_RECORDINGS_ROOT, latest_session, pending_sessions
from .transcribe import (
    DEFAULT_MODEL,
    TARGET_SR,
    track_vad_threshold,
    transcribe_audio,
    transcribe_track,
)


def process_session(
    session_dir: Path,
    *,
    language: str,
    model: str,
    diarize: bool = True,
    num_speakers: int = -1,
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
    diarization_model_dir: Path = DEFAULT_MODEL_DIR,
    self_name: str = DEFAULT_SELF_NAME,
    other_name: str = DEFAULT_OTHER_NAME,
) -> tuple[Path, Path]:
    """Processes one session and writes out transcript.md / transcript.json."""

    mic_wav = session_dir / "mic.wav"
    mic: list[Segment] = (
        transcribe_track(
            str(mic_wav),
            language=language,
            model=model,
            vad_threshold=track_vad_threshold("mic"),
        )
        if mic_wav.exists()
        else []
    )

    # system reuses the same normalized waveform for both transcription and diarization.
    # A session with a counterpart name declares itself 1-on-1 -> bypass diarization
    # (the single other side = that real name).
    meta = load_session_meta(session_dir)
    effective_diarize = diarize and not meta.counterpart_name

    system_labeled: list[LabeledSegment] = []
    system_wav = session_dir / "system.wav"
    if system_wav.exists():
        system_audio = load_normalized(str(system_wav))
        system_segs = transcribe_audio(
            system_audio,
            language=language,
            model=model,
            vad_threshold=track_vad_threshold("system"),
        )
        speakers = (
            diarize_system(
                system_audio,
                TARGET_SR,
                model_dir=diarization_model_dir,
                num_speakers=num_speakers,
                cluster_threshold=cluster_threshold,
            )
            if effective_diarize
            else None
        )
        # Falls back to a single bucket when speakers is None (not installed/failed/--no-diarize).
        system_labeled = assign_speakers(system_segs, speakers)

    labeled = merge_tracks(mic, system_labeled)
    turns = group_turns(labeled)

    md_path = session_dir / "transcript.md"
    json_path = session_dir / "transcript.json"
    md_path.write_text(
        render_markdown(turns, meta, self_name=self_name, other_name=other_name),
        encoding="utf-8",
    )
    json_path.write_text(render_json(labeled), encoding="utf-8")
    return md_path, json_path


def _resolve_targets(args: argparse.Namespace) -> list[Path]:
    """Determines the list of target sessions from the CLI arguments."""
    if args.all_pending:
        targets = pending_sessions(args.recordings_dir)
        if not targets:
            print("No pending sessions (transcript.md already exists for all of them)")
        return targets
    if args.session_dir is not None:
        return [args.session_dir]
    latest = latest_session(args.recordings_dir)
    if latest is None:
        print(f"No session found: {args.recordings_dir}", file=sys.stderr)
        raise SystemExit(1)
    return [latest]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="postprocess",
        description="Builds a self/other conversation log (Transcript) from a recording session",
    )
    parser.add_argument(
        "session_dir", type=Path, nargs="?", help="Recording session directory (defaults to the latest)"
    )
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Batch-process pending sessions (no transcript.md yet)",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Skip transcription and only re-run the later stage (full index.json rebuild)",
    )
    parser.add_argument(
        "--delete-transcribed-audio",
        action="store_true",
        help="Batch-delete the input audio from existing sessions that already have both Transcripts",
    )
    parser.add_argument(
        "--keep-source-audio",
        action="store_true",
        help="Keep mic.wav / system.wav after generating the Transcript (default: delete)",
    )
    parser.add_argument(
        "--recordings-dir",
        type=Path,
        default=DEFAULT_RECORDINGS_ROOT,
        help="Recordings root (default: ~/Documents/MeetingRecorder/recordings)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help=(
            "ASR language ('auto' or a Whisper language code; default: the "
            "transcript.language value in postprocess-config.json, or 'auto' if unset)"
        ),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="MLX Whisper model")
    parser.add_argument(
        "--no-diarize",
        dest="diarize",
        action="store_false",
        help="Disable speaker diarization for the other side (always output a single \"Other\")",
    )
    parser.add_argument(
        "--speakers",
        type=int,
        default=-1,
        help="Fix the number of people on the other side (default -1 = auto-estimate)",
    )
    parser.add_argument(
        "--cluster-threshold",
        type=float,
        default=DEFAULT_CLUSTER_THRESHOLD,
        help=(
            "Clustering threshold for auto-estimating speakers. Higher merges more into the "
            f"same speaker (default {DEFAULT_CLUSTER_THRESHOLD})"
        ),
    )
    parser.add_argument(
        "--diarization-model-dir",
        type=Path,
        default=DEFAULT_MODEL_DIR,
        help="Where the speaker-diarization model lives (default: ~/Documents/MeetingRecorder/models/diarization)",
    )
    parser.add_argument(
        "--model-status",
        action="store_true",
        help="Print model status (missing/downloading/ready/error) and exit",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print --model-status as JSON"
    )
    parser.add_argument(
        "--download-models",
        action="store_true",
        help="Download models (progress is printed as JSON Lines)",
    )
    parser.add_argument(
        "--delete-models",
        action="store_true",
        help="Delete models (prints the result as JSON)",
    )
    parser.add_argument(
        "--only",
        choices=["whisper", "diarization"],
        help="Limit --download-models / --delete-models to a single model",
    )
    args = parser.parse_args()

    # Model-management mode (independent of the transcription path).
    if args.model_status:
        _run_model_status(json_out=args.json)
        return
    if args.download_models:
        raise SystemExit(_run_download_models(only=args.only))
    if args.delete_models:
        raise SystemExit(_run_delete_models(only=args.only))

    if args.all_pending and args.session_dir is not None:
        parser.error("session_dir and --all-pending cannot be given together")

    if args.delete_transcribed_audio:
        if (
            args.session_dir is not None
            or args.all_pending
            or args.sync
            or args.keep_source_audio
        ):
            parser.error(
                "--delete-transcribed-audio cannot be combined with session_dir / "
                "--all-pending / --sync / --keep-source-audio"
            )
        if not args.recordings_dir.is_dir():
            print(f"Recordings root not found: {args.recordings_dir}", file=sys.stderr)
            raise SystemExit(1)
        try:
            deleted_sessions, deleted_files = delete_transcribed_audio(
                args.recordings_dir
            )
        except OSError as error:
            print(
                f"Failed to delete audio files: {error}", file=sys.stderr
            )
            raise SystemExit(3) from error
        print(
            f"deleted {deleted_files} audio file(s) from "
            f"{deleted_sessions} transcribed session(s)"
        )
        return

    cfg = load_config()
    if args.language is not None:
        language = normalize_language(args.language)
        if language is None:
            parser.error(
                f"unsupported --language {args.language!r}: use 'auto' or a Whisper "
                "language code such as 'en' or 'ja'"
            )
    else:
        language = cfg.language

    # --sync: skip transcription, only rebuild index.json.
    if args.sync:
        if args.session_dir is not None or args.all_pending:
            parser.error("--sync cannot be combined with session_dir / --all-pending")
        if not args.recordings_dir.is_dir():
            print(f"Recordings root not found: {args.recordings_dir}", file=sys.stderr)
            raise SystemExit(1)
        index_path = write_index(args.recordings_dir)
        print(f"rebuilt {index_path}")
        return

    targets = _resolve_targets(args)
    actions = [(session_dir, session_action(session_dir)) for session_dir in targets]

    missing_audio = [
        session_dir for session_dir, action in actions if action == "missing"
    ]
    if missing_audio:
        for session_dir in missing_audio:
            print(
                f"No input audio, and the Transcripts aren't complete either: {session_dir}",
                file=sys.stderr,
            )
    if missing_audio and (not args.all_pending or len(missing_audio) == len(actions)):
        raise SystemExit(1)

    processable_actions = [
        (session_dir, action) for session_dir, action in actions if action != "missing"
    ]
    needs_transcription = any(
        action == "transcribe" for _, action in processable_actions
    )

    if (
        needs_transcription
        and args.diarize
        and not diarize_system_available(args.diarization_model_dir)
    ):
        print(
            "Note: the speaker-diarization model was not found. The other side will be "
            "output as a single \"Other\" bucket. "
            "(Download the model with: scripts/download_diarization_models.sh)",
            file=sys.stderr,
        )

    # Refuse to implicitly download: if Whisper isn't downloaded yet, stop clearly
    # instead of letting mlx download it silently.
    if needs_transcription and not _whisper_ready():
        print(
            "The Whisper model has not been downloaded. Please run "
            "`postprocess --download-models --only whisper` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    for session_dir, action in processable_actions:
        if action == "complete":
            print(
                f"[{session_dir.name}] already transcribed / source audio already deleted"
            )
            continue
        if action == "cleanup":
            _finish_source_audio(
                session_dir,
                keep_source_audio=args.keep_source_audio,
            )
            continue

        md_path, json_path = process_session(
            session_dir,
            language=language,
            model=args.model,
            diarize=args.diarize,
            num_speakers=args.speakers,
            cluster_threshold=args.cluster_threshold,
            diarization_model_dir=args.diarization_model_dir,
            self_name=cfg.self_name,
            other_name=cfg.other_name,
        )
        print(f"[{session_dir.name}] wrote {md_path.name} / {json_path.name}")
        _finish_source_audio(
            session_dir,
            keep_source_audio=args.keep_source_audio,
        )

    # Later stage 4, index: rebuild derived artifacts. A failure here doesn't
    # count as a transcription failure.
    if args.recordings_dir.is_dir():
        try:
            write_index(args.recordings_dir)
        except OSError as e:
            print(f"Warning: failed to update index.json: {e}", file=sys.stderr)

    if missing_audio:
        raise SystemExit(1)


def _finish_source_audio(session_dir: Path, *, keep_source_audio: bool) -> None:
    """Keeps the input audio per the setting, or deletes it once the safety conditions are met."""
    if keep_source_audio:
        print(f"[{session_dir.name}] kept source audio file(s)")
        return

    _delete_audio_or_exit(session_dir)


def _delete_audio_or_exit(session_dir: Path) -> None:
    """Deletes the input audio, exiting in a way that makes clear the Transcript is still complete on failure."""
    try:
        deleted = delete_source_audio(session_dir)
    except (OSError, ValueError) as error:
        print(
            "Failed to delete the audio file(s) "
            f"(the Transcript was already saved): {error}",
            file=sys.stderr,
        )
        raise SystemExit(3) from error
    print(f"[{session_dir.name}] deleted {len(deleted)} source audio file(s)")


def diarize_system_available(model_dir: Path) -> bool:
    """For the CLI startup notice: whether the diarization models are present."""
    from .diarize import models_present

    return models_present(model_dir)


def _whisper_ready() -> bool:
    from .models import whisper_ready

    return whisper_ready()


def _run_model_status(*, json_out: bool) -> None:
    """Prints model status (--model-status)."""
    from .models import model_status, status_json

    if json_out:
        print(status_json())
        return
    for m in model_status():
        print(f"{m.id}: {m.state}  ({m.size_label}) {m.name}")


def _run_download_models(*, only: str | None) -> int:
    """Downloads models (--download-models). Returns the process exit code."""
    from .models import DIARIZATION_ID, WHISPER_ID, download_model

    targets = [only] if only else [WHISPER_ID, DIARIZATION_ID]
    rc = 0
    for model_id in targets:
        rc |= download_model(model_id)
    return rc


def _run_delete_models(*, only: str | None) -> int:
    """Deletes models (--delete-models). Returns the process exit code."""
    from .models import DIARIZATION_ID, WHISPER_ID, delete_model

    targets = [only] if only else [WHISPER_ID, DIARIZATION_ID]
    rc = 0
    for model_id in targets:
        rc |= delete_model(model_id)
    return rc
