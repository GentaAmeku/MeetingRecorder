"""Deleting input audio once the Transcript is complete.

Centralizes the deletion conditions and re-run logic in this module so
auto-transcription, the manual CLI, and batch cleanup of existing sessions
all follow the same rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .sessions import find_sessions

SOURCE_AUDIO_NAMES = ("mic.wav", "system.wav")
TRANSCRIPT_NAMES = ("transcript.md", "transcript.json")

SessionAction = Literal["transcribe", "cleanup", "complete", "missing"]


def transcript_complete(session_dir: Path) -> bool:
    """Whether both primary artifacts, the Markdown and the structured JSON, exist."""
    return all((session_dir / name).is_file() for name in TRANSCRIPT_NAMES)


def existing_source_audio(session_dir: Path) -> tuple[Path, ...]:
    """Returns, in a fixed order, only the input audio that's still present in the session."""
    return tuple(
        path
        for name in SOURCE_AUDIO_NAMES
        if (path := session_dir / name).is_file()
    )


def session_action(session_dir: Path) -> SessionAction:
    """Decides the safe next action from the session's actual state."""
    audio_count = len(existing_source_audio(session_dir))
    complete = transcript_complete(session_dir)

    if audio_count == 0:
        return "complete" if complete else "missing"
    if complete and audio_count < len(SOURCE_AUDIO_NAMES):
        return "cleanup"
    return "transcribe"


def delete_source_audio(session_dir: Path) -> tuple[Path, ...]:
    """Deletes the remaining input audio from a session whose both Transcripts are complete."""
    if not transcript_complete(session_dir):
        raise ValueError("Both transcript.md and transcript.json must be present")

    audio_paths = existing_source_audio(session_dir)
    for path in audio_paths:
        path.unlink()
    return audio_paths


def delete_transcribed_audio(recordings_dir: Path) -> tuple[int, int]:
    """Deletes input audio from every already-transcribed session.

    Returns `(number of sessions whose audio was deleted, number of files deleted)`.
    """
    deleted_sessions = 0
    deleted_files = 0
    for session_dir in find_sessions(recordings_dir):
        if not transcript_complete(session_dir):
            continue
        deleted = delete_source_audio(session_dir)
        if not deleted:
            continue
        deleted_sessions += 1
        deleted_files += len(deleted)
    return deleted_sessions, deleted_files
