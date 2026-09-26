"""
Unit tests for lucca.memory.entities
Spec 04 §5 (Entity resolution)
"""

from pathlib import Path

import pytest

from lucca.memory.db import DatabaseManager
from lucca.memory.entities import canonicalise, resolve_entity


@pytest.fixture
def temp_db(tmp_path: Path) -> DatabaseManager:
    db_path = tmp_path / "test_entities.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()
    yield db
    db.close()


def test_canonicalise() -> None:
    """canonicalise normalizes NFC, lowercases, strips disallowed punct, collapses whitespace."""
    assert canonicalise("  Alice   Bob  ") == "alice bob"
    assert canonicalise("Hello, World!") == "hello world"
    assert canonicalise("user@example.com") == "user@example.com"
    assert canonicalise("path/to/file.txt") == "path/to/file.txt"
    assert canonicalise("snake_case-and-kebab") == "snake_case-and-kebab"
    assert canonicalise("Cafe\u0301") == "café"  # NFD to NFC
    assert canonicalise("What??? No way!!!") == "what no way"
    assert canonicalise("") == ""


def test_resolve_entity_first_person(temp_db: DatabaseManager) -> None:
    """First-person pronouns and empty surface resolve to canonical entity 'user'."""
    conn = temp_db.get_connection()
    try:
        with conn:
            for term in ["I", "me", "my", "myself", "  Me  ", ""]:
                eid, canonical = resolve_entity(conn, term, entity_type="thing")
                assert canonical == "user"
                assert isinstance(eid, int)

            # Check in DB that user was inserted as type 'user'
            cur = conn.cursor()
            cur.execute("SELECT entity_id, canonical, type FROM kg_entities WHERE canonical = 'user'")
            row = cur.fetchone()
            assert row is not None
            assert row[1] == "user"
            assert row[2] == "user"
    finally:
        conn.close()


def test_resolve_entity_exact_match(temp_db: DatabaseManager) -> None:
    """Exact match in kg_entities returns the existing entity without duplicates."""
    conn = temp_db.get_connection()
    try:
        with conn:
            eid1, can1 = resolve_entity(conn, "Calculator", entity_type="app")
            assert can1 == "calculator"

            # Subsequent resolution with same canonical name returns same ID
            eid2, can2 = resolve_entity(conn, "calculator", entity_type="app")
            assert eid1 == eid2
            assert can2 == "calculator"

            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM kg_entities WHERE canonical = 'calculator'")
            assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_resolve_entity_exact_alias_match(temp_db: DatabaseManager) -> None:
    """Exact match in kg_aliases returns the canonical entity."""
    conn = temp_db.get_connection()
    try:
        with conn:
            eid, can = resolve_entity(conn, "Google Chrome", entity_type="app")
            assert can == "google chrome"

            # Manually register an alias
            cur = conn.cursor()
            cur.execute("INSERT INTO kg_aliases (alias, entity_id) VALUES ('chrome', ?)", (eid,))

            # Resolving "chrome" should resolve to eid and "google chrome"
            alias_eid, alias_can = resolve_entity(conn, "Chrome", entity_type="app")
            assert alias_eid == eid
            assert alias_can == "google chrome"
    finally:
        conn.close()


def test_resolve_entity_fuzzy_match_alias_creation(temp_db: DatabaseManager) -> None:
    """Fuzzy match (score >= 94.0 and same type) resolves to canonical and records alias + audit."""
    conn = temp_db.get_connection()
    try:
        with conn:
            eid, can = resolve_entity(conn, "playstation portable", entity_type="device", now=1000.0)
            assert can == "playstation portable"

            # "playstation portabl" differs by 1 char out of 20 -> rapidfuzz ratio >= 94.0
            fuzzy_eid, fuzzy_can = resolve_entity(
                conn, "playstation portabl", entity_type="device", now=1005.0
            )
            assert fuzzy_eid == eid
            assert fuzzy_can == "playstation portable"

            # Verify alias was added to kg_aliases
            cur = conn.cursor()
            cur.execute("SELECT alias, entity_id FROM kg_aliases WHERE alias = 'playstation portabl'")
            row = cur.fetchone()
            assert row is not None
            assert row[1] == eid

            # Verify audit record was created in memory_audit
            cur.execute("SELECT kind, reason FROM memory_audit WHERE ts = 1005.0")
            audit_row = cur.fetchone()
            assert audit_row is not None
            assert audit_row[0] == "alias_added"
            assert "playstation portable" in audit_row[1]
    finally:
        conn.close()


def test_resolve_entity_fuzzy_match_different_type_creates_new(
    temp_db: DatabaseManager,
) -> None:
    """Fuzzy match with different entity_type does not merge; creates a new entity."""
    conn = temp_db.get_connection()
    try:
        with conn:
            eid_app, can_app = resolve_entity(conn, "super mario brothers", entity_type="game")
            # Typo with different type "movie"
            eid_movie, can_movie = resolve_entity(
                conn, "super mario brother", entity_type="movie"
            )
            assert eid_movie != eid_app
            assert can_movie == "super mario brother"
    finally:
        conn.close()
