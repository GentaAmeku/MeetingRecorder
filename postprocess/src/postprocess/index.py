"""Full rebuild of recordings/index.json (the catalog of all sessions).

A derived artifact that lets an agent or skill search across sessions in two
steps: "read the index -> read the transcript of whichever session it
needs". The source of truth is each session's metadata.json / transcript.*;
the index is always fully rebuilt from scratch each time (never incrementally updated).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .metadata import load_session_meta
from .sessions import find_sessions

INDEX_NAME = "index.json"
SCHEMA_VERSION = 1
EXCERPT_MAX_CHARS = 200

_TRANSCRIPT_NAME = "transcript.md"


def extract_excerpt(transcript_md: str, max_chars: int = EXCERPT_MAX_CHARS) -> str:
    """Skips the header in transcript.md and picks up roughly max_chars of the opening turns (pure logic).

    The header ends at the first `---` line. The non-empty lines (turns)
    after that are joined turn by turn, and truncated once max_chars is
    exceeded (anything past that is cut off with a trailing …).
    """
    lines = transcript_md.splitlines()
    body = lines[lines.index("---") + 1 :] if "---" in lines else lines
    picked: list[str] = []
    total = 0
    for raw in body:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        picked.append(line)
        total += len(line)
        if total >= max_chars:
            break
    excerpt = "\n".join(picked)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars] + "…"
    return excerpt


def session_entry(session_dir: Path) -> dict | None:
    """Builds the index entry for one session. Returns None (ignored) if its metadata is corrupt."""
    try:
        meta = load_session_meta(session_dir)
    except (OSError, ValueError):
        return None
    transcript = session_dir / _TRANSCRIPT_NAME
    excerpt = ""
    if transcript.is_file():
        try:
            excerpt = extract_excerpt(transcript.read_text(encoding="utf-8"))
        except OSError:
            excerpt = ""
    return {
        "dir": session_dir.name,
        "title": meta.title,
        "startedAt": meta.started_at,
        "endedAt": meta.ended_at,
        "durationSec": meta.duration_sec,
        "counterpartName": meta.counterpart_name,
        "hasTranscript": transcript.is_file(),
        "excerpt": excerpt,
    }


def build_index(entries: list[dict], *, generated_at: str) -> dict:
    """Builds the full index from a list of entries (pure logic). Sessions are sorted by startedAt descending.

    When startedAt is missing (an older recording), the directory name
    (`YYYY-MM-DD_HHmm_…`) is used instead — since it shares the same format
    as the leading date portion of the ISO timestamp, the order still comes
    out roughly chronological.
    """
    sessions = sorted(
        entries,
        key=lambda e: (e.get("startedAt") or e.get("dir", ""), e.get("dir", "")),
        reverse=True,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "sessions": sessions,
    }


def write_index(root: Path) -> Path:
    """Scans the entire recordings root and atomically rewrites index.json."""
    entries = [e for s in find_sessions(root) if (e := session_entry(s)) is not None]
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    payload = build_index(entries, generated_at=generated_at)
    index_path = root / INDEX_NAME
    tmp_path = root / f".{INDEX_NAME}.tmp"
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp_path, index_path)
    return index_path
