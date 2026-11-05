"""Decoupage unique d'une replique en blocs de synthese."""

from __future__ import annotations

import re

MIN_SENTENCE = 12
MAX_SENTENCE = 240
FIRST_MIN = 18
FIRST_MAX = 55


def sentences(text: str) -> list[str]:
    text = " ".join(str(text or "").split())
    if not text:
        return []
    raw: list[str] = []
    current = ""
    for index, character in enumerate(text):
        current += character
        if character in ".!?…:;":
            following = text[index + 1] if index + 1 < len(text) else " "
            if following == " " or index + 1 == len(text):
                raw.append(current.strip())
                current = ""
    if current.strip():
        raw.append(current.strip())

    split: list[str] = []
    for sentence in raw:
        while len(sentence) > MAX_SENTENCE:
            window = sentence[:MAX_SENTENCE]
            cut = window.rfind(", ")
            if cut < MIN_SENTENCE:
                cut = window.rfind(" ")
            if cut < MIN_SENTENCE:
                break
            split.append(sentence[: cut + 1].strip())
            sentence = sentence[cut + 1 :].strip()
        if sentence:
            split.append(sentence)

    def can_merge(sentence: str) -> bool:
        return len(sentence) < MIN_SENTENCE and not sentence.endswith(("?", "!"))

    final: list[str] = []
    for sentence in split:
        if final and can_merge(sentence) and not final[-1].endswith(("?", "!")):
            final[-1] = f"{final[-1]} {sentence}"
        else:
            final.append(sentence)
    if len(final) > 1 and can_merge(final[0]):
        final[1] = f"{final[0]} {final[1]}"
        final.pop(0)
    return final


def shorten_first(parts: list[str]) -> list[str]:
    if not parts or len(parts[0]) <= FIRST_MAX:
        return parts
    head = parts[0]
    cut = -1
    for match in re.finditer(r"[,;:—–]\s", head[: FIRST_MAX + 2]):
        if match.start() >= FIRST_MIN:
            cut = match.end()
            break
    if cut < 0:
        space = head.rfind(" ", FIRST_MIN, FIRST_MAX + 1)
        if space < 0:
            return parts
        cut = space + 1
    first = head[:cut].strip()
    rest = head[cut:].strip()
    return [first, rest, *parts[1:]] if rest else parts


def chunks(text: str) -> list[str]:
    return shorten_first(sentences(text))
