"""Pure-logic unit tests for tidying segment text (ported from Tsuzuri's TextShaper tests)."""

from postprocess.dictionary import Dictionary, DictionaryEntry
from postprocess.shaping import (
    Shaper,
    TermReplacer,
    misheard_kind,
    normalize,
    remove_fillers,
    wa_obun_spacing,
)


def entry(surface: str, *misheard: str) -> DictionaryEntry:
    return DictionaryEntry(surface, tuple(misheard))


# --- normalize


def test_normalize_full_width_letters_and_digits():
    assert normalize("ＰＲを３つ") == "PRを3つ"


def test_normalize_full_width_comma_and_period():
    assert normalize("確認しました，あとで直します．") == "確認しました、あとで直します。"
    assert normalize("約０．１２ドル") == "約0.12ドル"


def test_normalize_keeps_half_width_dot():
    assert normalize("Next.js の App Router") == "Next.js の App Router"


def test_normalize_removes_spaces_between_japanese():
    assert normalize("今日は 早めに 上がります。 残りは Jira に") == "今日は早めに上がります。残りは Jira に"
    assert normalize("  Claude   Code で ") == "Claude Code で"


# --- fillers

FILLERS = ["えー", "えーと", "えっと", "あのー"]


def test_removes_fillers_at_sentence_start_and_before_comma():
    assert remove_fillers(FILLERS, "えーと、PR を見てください。") == "PR を見てください。"
    assert remove_fillers(FILLERS, "明日は、あのー、10時からです。") == "明日は、10時からです。"
    assert remove_fillers(FILLERS, "了解です。えっと 次の件です") == "了解です。次の件です"


def test_keeps_words_that_are_not_standalone_fillers():
    assert remove_fillers(FILLERS, "あの件は明日です。") == "あの件は明日です。"
    assert remove_fillers(FILLERS, "ええ、そうです。") == "ええ、そうです。"
    assert remove_fillers(FILLERS, "それはえーと思います") == "それはえーと思います"


# --- replace

REPLACER = TermReplacer(
    [
        entry("Claude Code", "クロードコード", "クラウドコード", "cloud code"),
        entry("Claude", "クロード"),
        entry("GitHub", "github"),
        entry("静的", "性的"),
    ]
)


def test_replaces_katakana():
    assert REPLACER.replace("クロードコードで直して") == "Claude Codeで直して"
    assert REPLACER.replace("クロード・コードで直して") == "Claude Codeで直して"


def test_katakana_needs_non_katakana_neighbors():
    assert REPLACER.replace("スーパークロードコード") == "スーパークロードコード"
    assert REPLACER.replace("クロードー") == "クロードー"


def test_latin_ignores_case_but_needs_word_boundaries():
    assert REPLACER.replace("Cloud Code を開く") == "Claude Code を開く"
    assert REPLACER.replace("Github と githubx") == "GitHub と githubx"


def test_longest_match_wins_and_is_rewritten_once():
    assert REPLACER.replace("クロードとクロードコード") == "ClaudeとClaude Code"


def test_mixed_latin_and_katakana():
    replacer = TermReplacer([entry("Vitest", "Bテスト"), entry("GraphQL", "グラフQL")])
    assert replacer.replace("いま B テストの設定を見直す") == "いま Vitestの設定を見直す"
    assert replacer.replace("グラフ QL のスキーマ") == "GraphQL のスキーマ"
    assert replacer.replace("ABテストを回す") == "ABテストを回す"
    assert replacer.replace("Bテストケース") == "Bテストケース"
    assert misheard_kind("Bテスト") == "mixed"


def test_kanji_spellings_are_never_used():
    assert REPLACER.replace("性的解析") == "性的解析"
    assert misheard_kind("性的") == "unsupported"


def test_fixes_the_case_of_dictionary_words():
    replacer = TermReplacer([entry("pnpm"), entry("mise"), entry("Storybook"), entry("Node")])
    assert replacer.replace("PNPMで入れて、Miseでそろえる") == "pnpmで入れて、miseでそろえる"
    assert replacer.replace("storybook を開く") == "Storybook を開く"
    # Part of a longer name stays as it is.
    assert replacer.replace("node_modules と pnpmx") == "node_modules と pnpmx"


# --- spacing


def test_spacing_between_japanese_and_latin_words():
    assert wa_obun_spacing("Claude Codeで、Next.jsのPRを見る") == "Claude Code で、Next.js の PR を見る"


def test_no_spacing_for_digits_or_punctuation():
    assert wa_obun_spacing("15時に3つ、約0.12ドル。") == "15時に3つ、約0.12ドル。"
    assert wa_obun_spacing("「PR」を") == "「PR」を"
    assert wa_obun_spacing("Slack で声をかける") == "Slack で声をかける"


# --- all together


def test_shaper_runs_every_step_in_order():
    dictionary = Dictionary(entries=(entry("Claude Code", "クロードコード"),), fillers=("えーと",))
    assert Shaper(dictionary).shape("えーと、クロード・コードで ＰＲ を 見て") == "Claude Code で PR を見て"


def test_shaper_without_dictionary_only_normalizes_and_spaces():
    assert Shaper().shape("クロードコードでＰＲを見て") == "クロードコードで PR を見て"
