"""Tidying a transcript segment's text after recognition (pure logic).

A port of Tsuzuri's text shaper (https://github.com/GentaAmeku/Tsuzuri), run in
this order:

1. normalize — full-width letters/digits to half-width, 「，．」 to 「、。」, no
   spaces between Japanese characters
2. fillers — drop the dictionary's filler words (えーと, あのー) where they stand
   alone: at the start of a sentence or after 「、」, followed by 「、」 or a space
3. replace — rewrite misheard spellings from the dictionary to the right one
   (クロードコード -> Claude Code), and fix the letter case of the dictionary's
   own Latin words (PNPM -> pnpm)
4. spacing — one half-width space between Japanese and a word with Latin
   letters (Claude Code で); none around digits-only words (15時)

Where a replacement may apply is decided by the character kind of its ends,
because Japanese has no spaces between words: a katakana spelling only when
no katakana touches it, a Latin spelling only when no letter or digit touches
it. Spellings containing kanji or hiragana are never used (homophones are too
common); such words still help as hints.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .dictionary import Dictionary, DictionaryEntry

_KATAKANA = "ァ-ヺー-ヿㇰ-ㇿｦ-ﾟ"  # includes the long mark ー, not the middle dot ・
_JAPANESE_PUNCTUATION = "、。「」『』（）！？：；〜…【】・"
_SENTENCE_ENDS = "。！？!?\n"


def is_katakana(ch: str) -> bool:
    o = ord(ch)
    return 0x30A1 <= o <= 0x30FA or 0x30FC <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0xFF66 <= o <= 0xFF9F


def is_japanese_letter(ch: str) -> bool:
    o = ord(ch)
    return (
        0x3041 <= o <= 0x309F  # hiragana
        or is_katakana(ch)
        or 0x3400 <= o <= 0x4DBF
        or 0x4E00 <= o <= 0x9FFF
        or 0xF900 <= o <= 0xFAFF
        or ch in "々〆"
    )


def _is_ascii_alnum(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def _is_ascii_letter(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


# --- 1. normalize ---------------------------------------------------------


def normalize(text: str) -> str:
    """Full-width letters/digits to half-width, 「，．」 to 「、。」 (or to , . between
    letters/digits: ０．１２ -> 0.12), and no spaces between Japanese characters.
    Spaces next to Latin words stay (runs collapse to one)."""
    chars = [_half_width(c) for c in text]
    out: list[str] = []
    for i, c in enumerate(chars):
        prev = chars[i - 1] if i > 0 else ""
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if c in "，．":
            between = _is_ascii_alnum(prev) if prev else False
            between = between and (_is_ascii_alnum(nxt) if nxt else False)
            out.append(("," if c == "，" else ".") if between else ("、" if c == "，" else "。"))
        elif c in " 　":
            left = out[-1] if out else ""
            if not left or left == " ":
                continue
            right = next((x for x in chars[i + 1 :] if x not in " 　"), "")
            if _is_japanese(left) and right and _is_japanese(right):
                continue
            out.append(" ")
        else:
            out.append(c)
    return "".join(out).rstrip(" ")


def _half_width(c: str) -> str:
    o = ord(c)
    if 0xFF10 <= o <= 0xFF19 or 0xFF21 <= o <= 0xFF3A or 0xFF41 <= o <= 0xFF5A:
        return chr(o - 0xFEE0)
    return c


def _is_japanese(c: str) -> bool:
    return is_japanese_letter(c) or c in _JAPANESE_PUNCTUATION


# --- 2. fillers -------------------------------------------------------------


def remove_fillers(fillers: Iterable[str], text: str) -> str:
    """Drops a filler word only where it stands on its own: at the start of the
    text or a sentence, or right after 「、」, and followed by 「、」, a space or
    the end. 「あの件」 or 「それはえーと思います」 are left alone. Longer fillers go first
    (えーと before えー)."""
    for filler in sorted({f for f in fillers if f}, key=len, reverse=True):
        pattern = re.compile(
            r"(?:^|(?<=[" + re.escape(_SENTENCE_ENDS) + r"、 ]))" + re.escape(filler) + r"(?:、 *| +|$)"
        )
        text = pattern.sub("", text)
    return text


# --- 3. replace -------------------------------------------------------------


def misheard_kind(spelling: str) -> str:
    """"katakana", "latin", "mixed" (Latin letters and katakana) or "unsupported"."""
    letters = [c for c in spelling if c not in " ・"]
    if not letters:
        return "unsupported"
    if all(is_katakana(c) for c in letters):
        return "katakana"
    if spelling.isascii() and any(_is_ascii_letter(c) for c in letters):
        return "latin"
    if (
        all(is_katakana(c) or _is_ascii_alnum(c) for c in letters)
        and any(is_katakana(c) for c in letters)
        and any(_is_ascii_letter(c) for c in letters)
    ):
        return "mixed"
    return "unsupported"


def _before(first: str) -> str:
    return f"(?<![{_KATAKANA}])" if is_katakana(first) else "(?<![A-Za-z0-9])"


def _after(last: str) -> str:
    return f"(?![{_KATAKANA}])" if is_katakana(last) else "(?![A-Za-z0-9])"


def misheard_pattern(spelling: str) -> re.Pattern[str] | None:
    """The regex that finds `spelling` in text, or None if it can't be used."""
    letters = [c for c in spelling if c not in " ・"]
    kind = misheard_kind(spelling)
    if kind == "katakana":
        # 「クロード・コード」 and 「クロード コード」 also match.
        body = "[・ ]?".join(re.escape(c) for c in letters)
        source = f"(?<![{_KATAKANA}])" + body + f"(?![{_KATAKANA}])"
    elif kind == "latin":
        body = " ?".join(re.escape(part) for part in spelling.split(" ") if part)
        source = "(?<![A-Za-z0-9])" + body + "(?![A-Za-z0-9])"
    elif kind == "mixed":
        body = "[・ ]?".join(re.escape(c) for c in letters)
        source = _before(letters[0]) + body + _after(letters[-1])
    else:
        return None
    return re.compile(source, re.IGNORECASE)


def _case_pattern(surface: str) -> re.Pattern[str] | None:
    """Finds the dictionary's own Latin word written in another case (PNPM for
    pnpm, storybook for Storybook). Underscores also count as part of a word
    here, so names like node_modules are left alone."""
    if misheard_kind(surface) != "latin":
        return None
    body = " ?".join(re.escape(part) for part in surface.split(" ") if part)
    return re.compile("(?<![A-Za-z0-9_])" + body + "(?![A-Za-z0-9_])", re.IGNORECASE)


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    surface: str


class TermReplacer:
    def __init__(self, entries: Iterable[DictionaryEntry]):
        rules: list[_Rule] = []
        for entry in entries:
            for spelling in entry.misheard:
                if (pattern := misheard_pattern(spelling)) is not None:
                    rules.append(_Rule(pattern, entry.surface))
            if (pattern := _case_pattern(entry.surface)) is not None:
                rules.append(_Rule(pattern, entry.surface))
        self._rules = rules

    def replace(self, text: str) -> str:
        """Overlapping matches: the longest wins (then the earliest), and each
        spot is rewritten once, so a replaced word isn't rewritten again by a
        shorter one (クロードコード -> Claude Code, not Claude + コード)."""
        matches = [
            (m.start(), m.end(), rule.surface)
            for rule in self._rules
            for m in rule.pattern.finditer(text)
        ]
        chosen: list[tuple[int, int, str]] = []
        for start, end, surface in sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0])):
            if all(end <= s or start >= e for s, e, _ in chosen):
                chosen.append((start, end, surface))
        for start, end, surface in sorted(chosen, key=lambda m: m[0], reverse=True):
            text = text[:start] + surface + text[end:]
        return text


# --- 4. spacing -------------------------------------------------------------


def _is_word_char(c: str) -> bool:
    return _is_ascii_alnum(c) or c in "._+#-/"


def _word_has_letter(chars: list[str], index: int, forward: bool) -> bool:
    i = index
    while 0 <= i < len(chars) and _is_word_char(chars[i]):
        if _is_ascii_letter(chars[i]):
            return True
        i += 1 if forward else -1
    return False


def wa_obun_spacing(text: str) -> str:
    """One half-width space between a Japanese letter and a word that has Latin
    letters in it. Digits-only words (15時, 3つ) and punctuation get none."""
    chars = list(text)
    if len(chars) < 2:
        return text
    out = [chars[0]]
    for i in range(1, len(chars)):
        left, right = chars[i - 1], chars[i]
        if is_japanese_letter(left) and _is_word_char(right) and _word_has_letter(chars, i, True):
            out.append(" ")
        elif _is_word_char(left) and is_japanese_letter(right) and _word_has_letter(chars, i - 1, False):
            out.append(" ")
        out.append(right)
    return "".join(out)


# --- all together -----------------------------------------------------------


class Shaper:
    """normalize -> fillers -> replace -> spacing, with the dictionary's words.
    Without a dictionary only normalize and spacing apply."""

    def __init__(self, dictionary: Dictionary | None = None):
        self._fillers = dictionary.fillers if dictionary else ()
        self._replacer = TermReplacer(dictionary.entries if dictionary else ())

    def shape(self, text: str) -> str:
        text = normalize(text)
        text = remove_fillers(self._fillers, text)
        text = self._replacer.replace(text)
        return wa_obun_spacing(text).strip()
