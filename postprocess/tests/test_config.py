"""Pure-logic unit tests for reading postprocess-config.json."""

from postprocess.config import (
    DEFAULT_LANGUAGE,
    DEFAULT_OTHER_NAME,
    DEFAULT_SELF_NAME,
    PostprocessConfig,
    load_config,
    parse_config,
)


def test_parse_full_config():
    cfg = parse_config(
        '{"schemaVersion": 1, "transcript": {"selfName": " 山田 "}}'
    )
    assert cfg.self_name == "山田"


def test_parse_missing_keys_uses_defaults():
    cfg = parse_config("{}")
    assert cfg == PostprocessConfig()
    assert cfg.self_name == DEFAULT_SELF_NAME
    assert cfg.other_name == DEFAULT_OTHER_NAME
    assert cfg.language == DEFAULT_LANGUAGE


def test_parse_unknown_keys_ignored():
    cfg = parse_config('{"future": {"enabled": true}, "x": 2}')
    assert cfg == PostprocessConfig()


def test_parse_legacy_section_is_ignored():
    """An unknown section left behind by an older version is ignored, and the defaults still apply."""
    cfg = parse_config(
        '{"legacyExport": {"enabled": true, "path": "/tmp/old"},'
        ' "transcript": {"selfName": "山田"}}'
    )
    assert cfg == PostprocessConfig(self_name="山田")


def test_parse_broken_json_falls_back_to_defaults():
    assert parse_config("{broken") == PostprocessConfig()
    assert parse_config("[1,2]") == PostprocessConfig()
    assert parse_config('{"transcript": "oops"}') == PostprocessConfig()


def test_parse_invalid_self_name_uses_default():
    for value in ('""', '"  "', '"山田\\n別名"', "42", "null", "[]"):
        cfg = parse_config('{"transcript": {"selfName": ' + value + "}}")
        assert cfg.self_name == DEFAULT_SELF_NAME


def test_parse_other_name():
    cfg = parse_config('{"transcript": {"otherName": " Guest "}}')
    assert cfg.other_name == "Guest"


def test_parse_invalid_other_name_uses_default():
    for value in ('""', '"  "', '"line1\\nline2"', "42", "null", "[]"):
        cfg = parse_config('{"transcript": {"otherName": ' + value + "}}")
        assert cfg.other_name == DEFAULT_OTHER_NAME


def test_parse_language():
    cfg = parse_config('{"transcript": {"language": " en "}}')
    assert cfg.language == "en"


def test_parse_invalid_language_uses_default():
    for value in ('""', '"  "', "42", "null", "[]"):
        cfg = parse_config('{"transcript": {"language": ' + value + "}}")
        assert cfg.language == DEFAULT_LANGUAGE


def test_load_config_missing_file_is_default(tmp_path):
    assert load_config(tmp_path / "nope.json") == PostprocessConfig()


def test_load_config_reads_file(tmp_path):
    p = tmp_path / "postprocess-config.json"
    p.write_text(
        '{"transcript": {"selfName": "田中", "otherName": "Guest", "language": "en"}}',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.self_name == "田中"
    assert cfg.other_name == "Guest"
    assert cfg.language == "en"


def test_language_is_normalized_and_validated():
    # Codes and names are accepted in any case; unsupported values fall back to auto.
    from postprocess.config import normalize_language

    assert normalize_language(" JA ") == "ja"
    assert normalize_language("Japanese") == "ja"
    assert normalize_language("Auto") == "auto"
    assert normalize_language("xx") is None
    assert parse_config('{"transcript": {"language": "xx"}}').language == "auto"
    assert parse_config('{"transcript": {"language": "EN"}}').language == "en"

