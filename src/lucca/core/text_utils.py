"""
Project Lucca — Unified Transcript & Text Utilities (ITEM-018 / WO-23 Phase 0 / WO-26 Phase 2).

Provides a single canonical normalizer applied at the ASR boundary so that
HeuristicRouter and MicroScheme rule evaluator consume identical text.
Guarantees parity across punctuation, casing, contractions, spelled sequences,
and acoustic corrections.
"""

from __future__ import annotations

import re

FOOD_CONTEXT_KEYWORDS = {
    "food",
    "eat",
    "eating",
    "ate",
    "dinner",
    "lunch",
    "breakfast",
    "meal",
    "restaurant",
    "takeaway",
    "takeout",
    "order",
    "ordered",
    "ordering",
    "menu",
    "seafood",
    "fried",
    "fry",
    "tartar",
    "sauce",
    "pub",
    "hungry",
    "delicious",
    "tasty",
    "snack",
    "portion",
    "serve",
    "serving",
    "vinegar",
    "lemon",
    "battered",
    "chips",
    "dish",
    "cook",
    "cooked",
    "cooking",
    "plate",
}


def collapse_stutter_loops(text: str) -> str:
    """Collapses repetitive syllabic and single-letter ASR stutter loops (>3 identical cycles).

    Prevents runaway microphone feedback loops (e.g. 'C-L-C-L-C-L-L-L...' or 'T-T-T-T-T...')
    from assembling into 100+ character garbage tokens in conversation history.
    """
    if not text:
        return ""
    for _ in range(5):
        prev = text
        # 1. Hyphenated 2-letter syllable loops
        # Trailing attached: e.g. S-I-L-O-G-C-L-C-L-C-L
        text = re.sub(
            r"-\s*(([a-zA-Z]\s*-\s*[a-zA-Z])(?:\s*-\s*\2){2,}(?:\s*-\s*[a-zA-Z])*)(?:\.{2,}|…)?",
            "",
            text,
            flags=re.IGNORECASE,
        )
        # Standalone hyphenated 2-letter cycle: e.g. C-L-C-L-C-L...
        text = re.sub(
            r"(?:^|\s+)(([a-zA-Z]\s*-\s*[a-zA-Z])(?:\s*-\s*\2){2,}(?:\s*-\s*[a-zA-Z])*)(?:\.{2,}|…)?(?=\s|$|[.,?!])",
            "",
            text,
            flags=re.IGNORECASE,
        )
        # Standalone space-separated 2-letter syllable: e.g. C L C L C L
        text = re.sub(
            r"(?:^|\s+)(([a-zA-Z]\s+[a-zA-Z])(?:\s+\2){2,})(?:\.{2,}|…)?(?=\s|$|[.,?!])",
            "",
            text,
            flags=re.IGNORECASE,
        )
        # Standalone period-separated 2-letter syllable: e.g. C. L. C. L. C. L.
        text = re.sub(
            r"(?:^|\s+)(([a-zA-Z]\.\s*[a-zA-Z]\.)(?:\s*\2){2,})(?:\.{2,}|…)?(?=\s|$|[.,?!])",
            "",
            text,
            flags=re.IGNORECASE,
        )

        # 2. Collapse internal runs of >=3 identical consecutive letters down to 1
        text = re.sub(r"([a-zA-Z])(?:\s*-\s*\1){2,}", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"([a-zA-Z]\.)(?:\s*\1){2,}", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\b([a-zA-Z])(?:\s+\1){2,}\b", r"\1", text, flags=re.IGNORECASE)

        # 3. Trailing repeated single letter after a word ending in that letter
        # e.g. 'A-U-D-I-T T' or 'P-Y-T-H-O-N N' (from trailing ASR microphone stutter)
        text = re.sub(
            r"([a-zA-Z])(?:\s*[-.]\s*([a-zA-Z]))*?\s+([a-zA-Z])(?:\.{2,}|…)?(?=\s|$|[.,?!])",
            lambda m: (
                m.group(0).split()[0]
                if m.group(0).split()[-1].replace("-", "").replace(".", "").lower()
                == m.group(0).split()[0].split("-")[-1].replace(".", "").lower()
                else m.group(0)
            ),
            text,
            flags=re.IGNORECASE,
        )

        # 4. Pure standalone single-letter repeat (>=3 identical letters, e.g. T-T-T-T-T...)
        text = re.sub(
            r"(?:^|\s+)([a-zA-Z])(?:\s*-\s*\1){2,}(?:\.{2,}|…)?(?=\s|$|[.,?!])",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"(?:^|\s+)([a-zA-Z])(?:\s+\1){2,}(?:\.{2,}|…)?(?=\s|$|[.,?!])",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(r"\s+", " ", text).strip()
        if text == prev:
            break
    return text


def apply_acoustic_normalizations(text: str) -> str:
    """Context-bounded acoustic substitution heuristics (WO-26 Phase 2).

    Corrects phonetically adjacent speech misrecognitions (e.g. 'fish and ship' -> 'fish and chips')
    only when bounded by relevant topical context (food/dining keywords).
    Guarantees non-food usage (e.g. cargo ship parts) is never falsely rewritten.
    """
    if not text:
        return ""
    tokens = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    has_food_context = bool(tokens & FOOD_CONTEXT_KEYWORDS)
    if has_food_context:

        def repl_fish_ship(m: re.Match[str]) -> str:
            raw = m.group(0)
            if raw.isupper():
                return "FISH AND CHIPS"
            if raw[0].isupper():
                return "Fish and chips" if raw.split()[-1].islower() else "Fish and Chips"
            return "fish and chips"

        text = re.sub(r"\bfish\s+and\s+ship\b", repl_fish_ship, text, flags=re.IGNORECASE)

        def repl_salt_paper(m: re.Match[str]) -> str:
            raw = m.group(0)
            if raw.isupper():
                return "SALT AND PEPPER"
            if raw[0].isupper():
                return "Salt and pepper" if raw.split()[-1].islower() else "Salt and Pepper"
            return "salt and pepper"

        text = re.sub(r"\bsalt\s+and\s+paper\b", repl_salt_paper, text, flags=re.IGNORECASE)

    return text


def normalize_spelled_words(transcript: str) -> tuple[str, list[str]]:
    """Detects single-letter spelling sequences (hyphenated 'F-A-W-K-N-E-R', period-separated

    'F. A. W. K. N. E. R.', or space-separated single letters 'F A W K N E R') from ASR output,
    assembles them into title-cased words (capped at 25 chars), and returns (normalized_transcript, detected_words).
    Collapses repetitive syllabic stutter loops (>3 cycles) before assembly.
    """
    detected_words: list[str] = []

    # 0. Collapse runaway stutter loops before assembly (WO-26 Phase 2)
    text = collapse_stutter_loops(transcript)

    # 1. Period-separated letters (e.g. F. A. W. K. N. E. R. or F.A.W.K.N.E.R.)
    def replace_period(m: re.Match[str]) -> str:
        raw = str(m.group(0))
        letters = re.findall(r"[a-zA-Z]", raw)
        if len(letters) >= 3:
            letters = letters[:25]
            w = str("".join(letters).capitalize())
            detected_words.append(w)
            return w
        return raw

    text = re.sub(r"\b[a-zA-Z]\.(?:\s*[a-zA-Z]\.){2,}", replace_period, text)

    # 2. Hyphen-separated letters (e.g. F-A-W-K-N-E-R or F - A - W - K - N - E - R)
    def replace_hyphen(m: re.Match[str]) -> str:
        raw = str(m.group(0))
        letters = re.findall(r"[a-zA-Z]", raw)
        if len(letters) >= 3:
            letters = letters[:25]
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
            tokens = tokens[:25]
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
    """Canonical ASR transcript normalizer (ITEM-018 / Spec 06 §2 / WO-23 / WO-26 Phase 2).

    Applied ONCE at the ASR boundary so router and rule evaluator consume
    the exact same normalized string.
    - Strips leading and trailing whitespace
    - Normalizes unicode punctuation (curly quotes/apostrophes to straight quotes,
      em/en dashes to hyphens)
    - Collapses runaway repetitive syllabic stutter loops
    - Assembles spelled-out letter sequences (F-A-W-K-N-E-R / F A W K N E R -> Fawkner) <= 25 chars
    - Applies context-bounded acoustic corrections (e.g. fish and ship -> fish and chips in food context)
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

    # 2. Spelled-word normalization (e.g., F-A-W-K-N-E-R -> Fawkner, collapses stutter loops)
    s, _ = normalize_spelled_words(s)

    # 3. Context-bounded acoustic normalization (e.g., fish and ship -> fish and chips)
    s = apply_acoustic_normalizations(s)

    # 4. Collapse multiple whitespace characters and strip ends
    s = re.sub(r"\s+", " ", s).strip()

    # 5. Strip trailing sentence punctuation (. ? ! , ; :)
    s = re.sub(r"[.?!,;:]+$", "", s).strip()

    return s

