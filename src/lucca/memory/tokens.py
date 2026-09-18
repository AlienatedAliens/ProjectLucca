"""
Project Lucca — Memory Token & Query Processing
Spec 04 §2, §6, Property Test P-06
"""

import re
from typing import Final

SPLIT_PATTERN: Final[re.Pattern[str]] = re.compile(r"[_.\-/\\]+")


def subtokens(text: str) -> str:
    """
    Extract auxiliary sub-tokens by splitting tokens on delimiters (_ . - / \\).
    A pure Python function used identically at index time (before INSERT)
    and at query time.
    """
    cleaned = text.replace("\x00", " ")
    parts: list[str] = []
    for word in cleaned.split():
        sub_parts = SPLIT_PATTERN.split(word)
        if len(sub_parts) > 1:
            for p in sub_parts:
                p_clean = p.strip()
                if p_clean:
                    parts.append(p_clean)
    return " ".join(parts)


STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "ought",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    }
)


def clean_term(token: str) -> str:
    """Strip edge punctuation while preserving inner delimiters."""
    return token.strip(" \t\r\n.,!?:;\"'()[]{}<>~`#$*")


def escape_fts_token(token: str) -> str:
    """
    Escape an individual token for safe use in FTS5 MATCH queries.
    Strips internal null bytes, trims, and doubles any double-quotes.
    """
    cleaned = token.replace("\x00", " ").strip()
    if not cleaned:
        return '""'
    escaped = cleaned.replace('"', '""')
    return f'"{escaped}"'


def build_fts_query(text: str) -> str:
    """
    Construct a valid, injection-safe FTS5 MATCH expression from arbitrary text.
    Filters out conversational stop words when informative content tokens exist,
    strips edge punctuation, and wraps each token in double quotes with quote-doubling.
    Guarantees that ANY input string executes without error against FTS5 tables (P-06).
    """
    sanitized = text.replace("\x00", " ")
    raw_tokens = sanitized.split()
    if not raw_tokens:
        return '""'

    cleaned = [clean_term(t) for t in raw_tokens]
    valid_tokens = [t for t in cleaned if t]
    if not valid_tokens:
        return '""'

    content_tokens = [t for t in valid_tokens if t.lower() not in STOP_WORDS]
    tokens_to_use = content_tokens if content_tokens else valid_tokens

    escaped_tokens = [escape_fts_token(t) for t in tokens_to_use if t.strip()]
    return " OR ".join(escaped_tokens) if escaped_tokens else '""'
