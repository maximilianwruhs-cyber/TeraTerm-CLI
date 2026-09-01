"""Deterministic serial RX response scoring."""

from __future__ import annotations

import math

SILENCE_FLOOR = 0.05
STRONG_SCORE = 0.55

_PRINTABLE = frozenset({0x09, 0x0A, 0x0D, *range(0x20, 0x7F)})
_KEYWORDS = (
    "help",
    "command",
    "commands",
    "usage",
    "ok",
    "error",
    "menu",
    "available",
)
_PROMPT_ENDS = (">", "#", "$", ":")


def score_rx(data: bytes) -> float:
    if not data:
        return 0.0

    printable = sum(1 for b in data if b in _PRINTABLE)
    ratio = printable / len(data)
    byte_score = min(1.0, math.log2(1 + len(data)) / 10)

    text = data.decode("latin-1", errors="replace").lower()
    keyword_bonus = 0.0
    for kw in _KEYWORDS:
        if kw in text:
            keyword_bonus += 0.08
    keyword_bonus = min(keyword_bonus, 0.32)

    prompt_bonus = 0.0
    for line in text.splitlines():
        if line.rstrip().endswith(_PROMPT_ENDS):
            prompt_bonus = 0.05
            break

    total = byte_score + keyword_bonus + prompt_bonus
    if ratio < 0.5:
        total *= 0.3
    return max(0.0, min(1.0, total))
