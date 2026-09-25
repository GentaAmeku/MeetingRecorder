"""Rendering transcript.md / transcript.json (pure logic)."""

from __future__ import annotations

import json
from datetime import datetime

from .align import OTHER, SELF, LabeledSegment, Turn
from .config import DEFAULT_OTHER_NAME, DEFAULT_SELF_NAME
from .metadata import SessionMeta


def _join_label(base: str, suffix: str) -> str:
    """Joins a speaker label and its A/B/... suffix. Labels ending in CJK script
    are joined without a space ("相手A"), others with one ("Other A").
    """
    last = base[-1:] if base else ""
    if last and ("\u3040" <= last <= "\u30ff" or "\u3400" <= last <= "\u9fff" or "\uac00" <= last <= "\ud7af"):
        return f"{base}{suffix}"
    return f"{base} {suffix}"


def _speaker_label(
    speaker: str,
    counterpart: str = "",
    self_name: str = DEFAULT_SELF_NAME,
    other_name: str = DEFAULT_OTHER_NAME,
) -> str:
    """Internal speaker label -> display name. self -> self_name / other ->
    the counterpart's name if set, else other_name / other-N -> "other_name A",
    "other_name B", …
    """
    if speaker == SELF:
        return self_name
    if speaker == OTHER:
        return counterpart or other_name
    prefix = f"{OTHER}-"
    if speaker.startswith(prefix):
        try:
            n = int(speaker[len(prefix):])
        except ValueError:
            return other_name
        if 1 <= n <= 26:
            return _join_label(other_name, chr(ord("A") + n - 1))
        return _join_label(other_name, str(n))
    return speaker


def _format_clock(seconds: float) -> str:
    """Seconds -> [MM:SS] (MM grows past 2 digits once the hour mark is passed)."""
    total = int(seconds)
    return f"[{total // 60:02d}:{total % 60:02d}]"


def _format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _format_started_at(iso: str) -> str:
    """ISO 8601 -> 'YYYY-MM-DD HH:MM'. Returns the original text if it can't be parsed."""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return dt.strftime("%Y-%m-%d %H:%M")


def render_markdown(
    turns: list[Turn],
    meta: SessionMeta,
    *,
    self_name: str = DEFAULT_SELF_NAME,
    other_name: str = DEFAULT_OTHER_NAME,
) -> str:
    """Builds the conversation log from a header plus [MM:SS] Name: turns."""
    when = f"{_format_started_at(meta.started_at)} ({_format_duration(meta.duration_sec)})"
    # Show the meeting title in the H1 when set (the default "meeting" carries no
    # information, so just show the date/time then).
    if meta.title and meta.title != "meeting":
        h1 = f"# Meeting Transcript: {meta.title} — {when}"
    else:
        h1 = f"# Meeting Transcript — {when}"
    # Show the counterpart's real name on the Other line when set (1-on-1 meetings).
    others_line = (
        f"- Others: {meta.counterpart_name} (system audio)"
        if meta.counterpart_name
        else f"- Others: {other_name} (system audio, meeting participants)"
    )
    header = [
        h1,
        "",
        f"- Me: {self_name}",
        f"- Mic: {meta.mic_device_name}",
        others_line,
        "",
        "---",
        "",
    ]
    body = [
        f"{_format_clock(t.start)} "
        f"{_speaker_label(t.speaker, meta.counterpart_name, self_name, other_name)}: {t.text}"
        for t in turns
    ]
    return "\n".join(header + body) + "\n"


def render_json(segments: list[LabeledSegment]) -> str:
    """Turns an array of labeled segments into a JSON string."""
    payload = [
        {"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text}
        for s in segments
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
