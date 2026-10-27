"""Pure-logic unit tests for the word dictionary (Tsuzuri's format) and hint selection."""

import json
from datetime import datetime, timedelta, timezone

from postprocess.dictionary import (
    Dictionary,
    DictionaryEntry,
    TermUsage,
    load_dictionary,
    parse_dictionary,
    parse_usage,
    select_hints,
)

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def test_parse_tsuzuri_dictionary():
    d = parse_dictionary(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {"surface": "Claude Code", "from": ["クロードコード"], "hint": True, "pinned": False, "source": "manual"},
                    {"surface": "Vitest", "from": ["Bテスト", "Vitest"], "hint": True, "pinned": True},
                    {"surface": "静的", "from": [], "hint": False},
                ],
                "fillers": ["えーと", "あのー"],
            },
            ensure_ascii=False,
        )
    )
    assert d.entries == (
        DictionaryEntry("Claude Code", ("クロードコード",)),
        DictionaryEntry("Vitest", ("Bテスト",), pinned=True),  # the surface itself is not a misheard form
        DictionaryEntry("静的", (), hint=False),
    )
    assert d.fillers == ("えーと", "あのー")


def test_parse_dictionary_is_lenient():
    assert parse_dictionary("not json") == Dictionary()
    assert parse_dictionary("[]") == Dictionary()
    d = parse_dictionary('{"entries": [{"surface": ""}, {"from": ["x"]}, "x", {"surface": "PR"}]}')
    assert d.entries == (DictionaryEntry("PR"),)


def test_parse_usage():
    usage = parse_usage(
        '{"terms": {"PR": {"addedAt": "2026-10-20T00:00:00Z", "daily": {"2026-10-26": 3},'
        ' "lastUsedAt": "2026-10-26T09:00:00Z"}, "bad": 1}}'
    )
    assert set(usage) == {"PR"}
    assert usage["PR"].added_at == datetime(2026, 10, 20, tzinfo=timezone.utc)
    assert usage["PR"].daily == {"2026-10-26": 3}
    assert parse_usage("{}") == {}


def test_load_dictionary_reads_usage_next_to_it(tmp_path):
    (tmp_path / "dictionary.json").write_text('{"entries": [{"surface": "PR"}]}', encoding="utf-8")
    (tmp_path / "usage.json").write_text('{"terms": {"PR": {"daily": {"2026-10-26": 2}}}}', encoding="utf-8")
    d = load_dictionary(tmp_path / "dictionary.json")
    assert d is not None
    assert d.entries == (DictionaryEntry("PR"),)
    assert d.usage["PR"].daily == {"2026-10-26": 2}


def test_load_missing_dictionary_returns_none(tmp_path):
    assert load_dictionary(tmp_path / "nope.json") is None


def _day(offset: int) -> str:
    return (NOW - timedelta(days=offset)).astimezone().date().isoformat()


def test_select_hints_pinned_then_recent_then_most_used():
    d = Dictionary(
        entries=(
            DictionaryEntry("A"),
            DictionaryEntry("B"),
            DictionaryEntry("Pinned", pinned=True),
            DictionaryEntry("New"),
            DictionaryEntry("Often"),
            DictionaryEntry("Hidden", hint=False),
        ),
        usage={
            "New": TermUsage(added_at=NOW - timedelta(days=2)),
            "Often": TermUsage(daily={_day(1): 5}),
            "B": TermUsage(daily={_day(3): 1}),
        },
    )
    assert select_hints(d, NOW) == ["Pinned", "New", "Often", "B", "A"]


def test_select_hints_ignores_old_additions_and_old_counts():
    d = Dictionary(
        entries=(DictionaryEntry("A"), DictionaryEntry("Old")),
        usage={"Old": TermUsage(added_at=NOW - timedelta(days=40), daily={_day(31): 9})},
    )
    # Neither the 40-day-old addition nor the 31-day-old count lifts "Old".
    assert select_hints(d, NOW) == ["A", "Old"]


def test_select_hints_breaks_ties_by_last_use():
    d = Dictionary(
        entries=(DictionaryEntry("A"), DictionaryEntry("B")),
        usage={"B": TermUsage(last_used_at=NOW - timedelta(hours=1))},
    )
    assert select_hints(d, NOW) == ["B", "A"]
