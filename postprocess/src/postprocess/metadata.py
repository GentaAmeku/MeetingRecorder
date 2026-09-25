"""Reads Transcript-header information from metadata.json (the contract with the recording app)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionMeta:
    started_at: str  # ISO 8601 (kept as-is)
    duration_sec: int
    mic_device_name: str
    title: str = ""  # Meeting title (schemaVersion 2+; absent in older recordings, so default "")
    counterpart_name: str = ""  # Counterpart's real name (schemaVersion 3+; empty = no name)
    ended_at: str = ""  # ISO 8601 (for index.json; "" when missing)


def load_session_meta(session_dir: Path) -> SessionMeta:
    """Reads a session directory's metadata.json. Fills in missing/absent fields leniently."""
    data = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    devices = data.get("devices", {})
    return SessionMeta(
        started_at=data.get("startedAt", ""),
        duration_sec=int(data.get("durationSec", 0)),
        mic_device_name=devices.get("micDeviceName", "Unknown microphone"),
        title=data.get("title", ""),  # absent in schemaVersion 1 recordings -> ""
        counterpart_name=data.get("counterpartName", ""),  # schemaVersion 3+ / "" in older recordings
        ended_at=data.get("endedAt", ""),
    )
