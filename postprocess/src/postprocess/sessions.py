"""Recording session discovery (pure logic).

Finds session directories under the fixed root
`~/Documents/MeetingRecorder/recordings/`. The root is accepted as an
argument so it can be swapped out for tests and automation.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_RECORDINGS_ROOT = Path.home() / "Documents" / "MeetingRecorder" / "recordings"

_TRANSCRIPT_NAMES = ("transcript.md", "transcript.json")


def is_session_dir(path: Path) -> bool:
    """Treats a directory that has a metadata.json as a recording session."""
    return path.is_dir() and (path / "metadata.json").is_file()


def find_sessions(root: Path) -> list[Path]:
    """Returns the sessions directly under root, ascending by directory name (= chronological).

    Session names are `YYYY-MM-DD_HHmm_meeting` (seconds appended on
    collision), so lexicographic order matches chronological order.
    """
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if is_session_dir(p)), key=lambda p: p.name)


def latest_session(root: Path) -> Path | None:
    """The most recent session (largest name = newest). None if there are none."""
    sessions = find_sessions(root)
    return sessions[-1] if sessions else None


def pending_sessions(root: Path) -> list[Path]:
    """Returns, in chronological order, sessions missing either primary artifact."""
    return [
        session
        for session in find_sessions(root)
        if not all((session / name).is_file() for name in _TRANSCRIPT_NAMES)
    ]
