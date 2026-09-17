"""
Project Lucca — Deterministic Entity Resolution
Spec 04 §5 (Entity resolution)
"""

import re
import sqlite3
import time
import unicodedata
from typing import Final

import rapidfuzz

FIRST_PERSON_TERMS: Final[frozenset[str]] = frozenset({"i", "me", "my", "myself"})
ALLOWED_PUNCT: Final[str] = "._-/@"
STRIP_PUNCT_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^\w\s._\-/@]", flags=re.UNICODE)


def canonicalise(text: str) -> str:
    """
    1. NFC normalization
    2. Lowercase
    3. Strip punctuation except ._-/@
    4. Collapse whitespace
    """
    norm = unicodedata.normalize("NFC", text).lower()
    filtered = STRIP_PUNCT_PATTERN.sub("", norm)
    return " ".join(filtered.split()).strip()


def resolve_entity(
    conn: sqlite3.Connection,
    surface: str,
    entity_type: str = "thing",
    now: float | None = None,
) -> tuple[int, str]:
    """
    Resolve an entity surface form to (entity_id, canonical) per Spec 04 §5:
    1. Canonicalise
    2. First-person (i, me, my, myself) and empty subject -> entity 'user'
    3. Exact canonical match in kg_entities
    4. Exact alias match in kg_aliases
    5. rapidfuzz.fuzz.ratio(canonical, existing.canonical) >= 94 and same type -> alias
    6. Else create new entity in kg_entities
    """
    current_time = now if now is not None else time.time()
    can = canonicalise(surface)

    if can in FIRST_PERSON_TERMS or not can:
        can = "user"
        entity_type = "user"

    # 3. Exact match in kg_entities
    cur = conn.cursor()
    cur.execute("SELECT entity_id, canonical FROM kg_entities WHERE canonical = ?", (can,))
    row = cur.fetchone()
    if row is not None:
        return int(row[0]), str(row[1])

    # 4. Exact alias match in kg_aliases
    cur.execute(
        "SELECT a.entity_id, e.canonical FROM kg_aliases a "
        "JOIN kg_entities e ON a.entity_id = e.entity_id WHERE a.alias = ?",
        (can,),
    )
    row = cur.fetchone()
    if row is not None:
        return int(row[0]), str(row[1])

    # 5. Fuzzy match against existing entities of same type
    cur.execute("SELECT entity_id, canonical FROM kg_entities WHERE type = ?", (entity_type,))
    candidates = cur.fetchall()
    best_id: int | None = None
    best_canonical: str | None = None
    best_score = 0.0

    for cid, cname in candidates:
        score = rapidfuzz.fuzz.ratio(can, cname)
        if score > best_score:
            best_score = score
            best_id = int(cid)
            best_canonical = str(cname)

    if best_id is not None and best_canonical is not None and best_score >= 94.0:
        # Add alias and audit
        cur.execute(
            "INSERT OR IGNORE INTO kg_aliases(alias, entity_id) VALUES (?, ?)",
            (can, best_id),
        )
        cur.execute(
            "INSERT INTO memory_audit(ts, kind, reason) VALUES (?, 'alias_added', ?)",
            (current_time, f"Fuzz score {best_score:.1f}% ({can} -> {best_canonical})"),
        )
        return best_id, best_canonical

    # 6. Create new entity
    cur.execute(
        "INSERT INTO kg_entities(canonical, type, created_at) VALUES (?, ?, ?)",
        (can, entity_type, current_time),
    )
    if cur.lastrowid is None:
        raise RuntimeError("Failed to insert entity: lastrowid is None")
    new_id = int(cur.lastrowid)
    return new_id, can
