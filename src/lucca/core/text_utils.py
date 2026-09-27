"""
Project Lucca — Unified Transcript & Text Utilities (ITEM-018 / WO-23 Phase 0).

Provides a single canonical normalizer applied at the ASR boundary so that
HeuristicRouter and MicroScheme rule evaluator consume identical text.
Guarantees parity across punctuation, casing, contractions, and spelled sequences.
"""

from __future__ import annotations

import re


def normalize_spelled_words(transcript: str) -> tuple[str, list[str]]:
    """
    Detects single-letter spelling sequences (hyphenated 'F-A-W-K-N-E-R', period-separated
    'F. A. W. K. N. E. R.', or space-separated single letters 'F A W K N E R') from ASR output,
    assembles them into title-cased words, and returns (normalized_transcript, detected_words).
    """
    detected_words: list[str] = []

    # 1. Period-separated letters (e.g. F. A. W. K. N. E. R. or F.A.W.K.N.E.R.)
    def replace_period(m: re.Match[str]) -> str:
        raw = str(m.group(0))
        letters = re.findall(r"[a-zA-Z]", raw)
        if len(letters) >= 3:
            w = str("".join(letters).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(r"\b[a-zA-Z]\.(?:\s*[a-zA-Z]\.){2,}", replace_period, transcript)

    # 2. Hyphen-separated letters (e.g. F-A-W-K-N-E-R or F - A - W - K - N - E - R)
    def replace_hyphen(m: re.Match[str]) -> str:
        raw = str(m.group(0))
        letters = re.findall(r"[a-zA-Z]", raw)
        if len(letters) >= 3:
            w = str("".join(letters).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(r"\b[a-zA-Z](?:\s*-\s*[a-zA-Z]){2,}\b", replace_hyphen, text)

    # 3. Space-separated single letters (e.g. F A W K N E R or W K N E R)
    def replace_spaces(m: re.Match[str]) -> str:
        raw = str(m.group(1))
        tokens = raw.split()
        if len(tokens) >= 3 and all(len(t) == 1 and t.isalpha() for t in tokens):
            w = str("".join(tokens).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(
        r"(?:^|(?<=\s))([a-zA-Z](?:\s+[a-zA-Z]){2,})(?=\s|[.,!?]|$)",
        replace_spaces,
        text,
    )

    return text, list(dict.fromkeys(detected_words))


def normalize_transcript(text: str) -> str:
    """Canonical ASR transcript normalizer (ITEM-018 / Spec 06 §2 / WO-23).

    Applied ONCE at the ASR boundary so router and rule evaluator consume
    the exact same normalized string.
    - Strips leading and trailing whitespace
    - Normalizes unicode punctuation (curly quotes/apostrophes to straight quotes,
      em/en dashes to hyphens)
    - Assembles spelled-out letter sequences (F-A-W-K-N-E-R / F A W K N E R -> Fawkner)
    - Collapses internal whitespace runs to a single space
    - Strips trailing sentence punctuation (. ? ! , ; :) that varies by ASR model/prompt
    - Preserves internal punctuation (apostrophes in contractions, hyphens in words)
    """
    if not text:
        return ""

    # 1. Unicode quotes, dashes, non-breaking spaces
    s = (
        text.replace("‘", "'")
        .replace("’", "'")
        .replace("‚", "'")
        .replace("‛", "'")
        .replace("′", "'")
        .replace("‵", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("„", '"')
        .replace("‟", '"')
        .replace("″", '"')
        .replace("‶", '"')
        .replace("—", "-")
        .replace("–", "-")
        .replace("−", "-")
        .replace("\u00a0", " ")
    )

    # 2. Spelled-word normalization (e.g., F-A-W-K-N-E-R -> Fawkner)
    s, _ = normalize_spelled_words(s)

    # 3. Collapse multiple whitespace characters and strip ends
    s = re.sub(r"\s+", " ", s).strip()

    # 4. Strip trailing sentence punctuation (. ? ! , ; :)
    s = re.sub(r"[.?!,;:]+$", "", s).strip()

    return s
