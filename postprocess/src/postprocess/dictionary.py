"""Reading a Tsuzuri-format word dictionary and choosing the words to hint to Whisper.

Tsuzuri (https://github.com/GentaAmeku/Tsuzuri) is a dictation app by the same
author. Its dictionary.json lists the words you use (product names, tech
terms, people) and the ways they get misheard; its usage.json counts how often
each word came up. Reading the same file here means a word added while
dictating also helps meeting transcripts. Both files are only ever read, never
written.

The file can also be written by hand in the same shape:

    {
      "version": 1,
      "entries": [
        {"surface": "Claude Code", "from": ["クロードコード"], "hint": true, "pinned": false}
      ],
      "fillers": ["えーと", "あのー"]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DICTIONARY_PATH = Path.home() / "Library" / "Application Support" / "Tsuzuri" / "dictionary.json"

# Same ranking as Tsuzuri: pinned words, then words added in the last
# RECENT_DAYS, then words used most in the last COUNT_DAYS.
RECENT_DAYS = 14
COUNT_DAYS = 30


@dataclass(frozen=True)
class DictionaryEntry:
    """One word. `misheard` lists the spellings the recognizer produces instead of `surface`."""

    surface: str
    misheard: tuple[str, ...] = ()
    hint: bool = True
    pinned: bool = False


@dataclass(frozen=True)
class TermUsage:
    added_at: datetime | None = None
    daily: dict[str, int] = field(default_factory=dict)  # "yyyy-MM-dd" -> count
    last_used_at: datetime | None = None

    def count(self, days: int, now: datetime) -> int:
        """How many times the word was used in the `days` days up to `now` (local calendar days)."""
        return sum(self.daily.get((now - timedelta(days=offset)).date().isoformat(), 0) for offset in range(days))


@dataclass(frozen=True)
class Dictionary:
    entries: tuple[DictionaryEntry, ...] = ()
    fillers: tuple[str, ...] = ()
    usage: dict[str, TermUsage] = field(default_factory=dict)


def _text(value: object) -> str | None:
    """A usable single-line string, or None."""
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        return None
    value = value.strip()
    return value or None


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def parse_dictionary(text: str) -> Dictionary:
    """Parses dictionary.json leniently (pure logic). Entries without a usable
    surface are skipped; a malformed file yields an empty dictionary.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return Dictionary()
    if not isinstance(data, dict):
        return Dictionary()
    entries: list[DictionaryEntry] = []
    for raw in data.get("entries", []) if isinstance(data.get("entries"), list) else []:
        if not isinstance(raw, dict) or (surface := _text(raw.get("surface"))) is None:
            continue
        misheard = raw.get("from", [])
        entries.append(
            DictionaryEntry(
                surface=surface,
                misheard=tuple(m for m in (_text(x) for x in misheard if isinstance(misheard, list)) if m and m != surface),
                hint=raw.get("hint", True) is not False,
                pinned=raw.get("pinned") is True,
            )
        )
    fillers = data.get("fillers", [])
    return Dictionary(
        entries=tuple(entries),
        fillers=tuple(f for f in (_text(x) for x in (fillers if isinstance(fillers, list) else [])) if f),
    )


def parse_usage(text: str) -> dict[str, TermUsage]:
    """Parses Tsuzuri's usage.json ({"terms": {surface: {addedAt, daily, lastUsedAt}}}) leniently."""
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(terms, dict):
        return {}
    usage: dict[str, TermUsage] = {}
    for surface, raw in terms.items():
        if not isinstance(raw, dict):
            continue
        daily = raw.get("daily", {})
        usage[surface] = TermUsage(
            added_at=_date(raw.get("addedAt")),
            daily={k: v for k, v in daily.items() if isinstance(k, str) and isinstance(v, int)} if isinstance(daily, dict) else {},
            last_used_at=_date(raw.get("lastUsedAt")),
        )
    return usage


def load_dictionary(path: Path) -> Dictionary | None:
    """Reads the dictionary at `path` and the usage.json next to it.

    Returns None when the dictionary file is missing or unreadable: the
    dictionary is optional and must never stop transcription.
    """
    try:
        dictionary = parse_dictionary(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    try:
        usage = parse_usage((path.parent / "usage.json").read_text(encoding="utf-8"))
    except OSError:
        usage = {}
    return Dictionary(entries=dictionary.entries, fillers=dictionary.fillers, usage=usage)


def select_hints(dictionary: Dictionary, now: datetime) -> list[str]:
    """The hint words in priority order (a port of Tsuzuri's HintSelector):
    pinned words, then words added within RECENT_DAYS (newest first), then the
    rest by how often they were used in the last COUNT_DAYS (ties: most
    recently used, then dictionary order). How many fit is decided later by
    the Whisper prompt's token budget.
    """
    candidates = [e for e in dictionary.entries if e.hint]
    usage = dictionary.usage
    pinned = [e for e in candidates if e.pinned]
    recent_limit = now - timedelta(days=RECENT_DAYS)
    recent = sorted(
        (
            (e, usage[e.surface].added_at)
            for e in candidates
            if not e.pinned and e.surface in usage and usage[e.surface].added_at is not None
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    recent = [e for e, added in recent if added >= recent_limit]
    oldest = datetime.min.replace(tzinfo=now.tzinfo)

    def rank(indexed: tuple[int, DictionaryEntry]) -> tuple[int, float, int]:
        index, entry = indexed
        term = usage.get(entry.surface)
        count = term.count(COUNT_DAYS, now) if term else 0
        last = term.last_used_at if term and term.last_used_at else oldest
        return (-count, _negate(last, oldest), index)

    ranked = [e for _, e in sorted(enumerate(candidates), key=rank)]
    selected: list[str] = []
    for entry in pinned + recent + ranked:
        if entry.surface not in selected:
            selected.append(entry.surface)
    return selected


def _negate(moment: datetime, oldest: datetime) -> float:
    """Sort key that puts later moments first."""
    return -(moment - oldest).total_seconds()
