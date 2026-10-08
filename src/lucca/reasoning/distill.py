"""
Project Lucca — Post-Turn Belief Proposition Distiller
Spec 03, Release v1.35.7 (Phase 4)
Zero-Any Rule Compliant.
"""

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

from lucca.core.schemas import (
    Provenance,
    SignedPayload,
    UnsignedPayload,
)
from lucca.memory.signers import DerivedFactSigner
from lucca.ports import SpeechLLMPort

logger = structlog.get_logger(__name__)

DEFAULT_GRAMMAR_PATH = Path("config/grammars/belief_distill.gbnf")


class DistilledProposition(BaseModel):
    """Structured third-person canonical proposition distilled from conversational speech."""

    topic: str
    canonical_proposition: str
    polarity: str = "TRUE"
    confidence: float = 0.90
    source_turn_ids: list[str] = Field(default_factory=list)


def _clean_conversational_filler(text: str) -> str:
    """Removes first/second-person filler and conversational noise programmatically."""
    clean = text.strip()
    filler_pattern = (
        r"^(?:actually|well|i mean|you know|wait|hey|um|uh|look|so|basically|listen|honestly)[,\s]+"
    )
    while True:
        m = re.match(filler_pattern, clean, re.IGNORECASE)
        if not m:
            break
        clean = clean[m.end():].lstrip()

    # Normalize first-person phrasing to third-person statement
    clean = re.sub(r"^(?:i\s+prefer|i\s+like|i\s+want)\s+", "The user prefers ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^(?:i\s+always\s+use)\s+", "The user always uses ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^(?:i\s+never\s+use)\s+", "The user never uses ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^(?:i\s+don't\s+support|i\s+dont\s+support|we\s+don't\s+support)\s+", "System does not support ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^(?:i\s+am\s+in|i\s+live\s+in)\s+", "The user is located in ", clean, flags=re.IGNORECASE)

    if clean:
        clean = clean[0].upper() + clean[1:]
    if clean and not clean.endswith((".", "!", "?")):
        clean += "."
    return clean


def distill_contradiction_to_proposition(
    old_content: str,
    new_content: str,
    topic: str = "general",
    llm: SpeechLLMPort | None = None,
    grammar_path: Path | None = None,
) -> DistilledProposition:
    """
    Distills a confirmed contradiction into a clean third-person declarative proposition.
    Uses GBNF-constrained JSON generation via SpeechLLMPort if available,
    with a deterministic fallback.
    """
    g_path = grammar_path or DEFAULT_GRAMMAR_PATH
    grammar_text: str | None = None
    if g_path.exists():
        try:
            grammar_text = g_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.debug("gbnf_grammar_read_failed", path=str(g_path), error=str(exc))

    if llm is not None and grammar_text:
        try:
            prompt = (
                f"Distill this revised fact into a third-person canonical proposition.\n"
                f"Prior statement: {old_content}\n"
                f"New utterance: {new_content}\n"
                f"Topic: {topic}\n"
            )
            events = list(
                llm.stream_turn(
                    current_text=prompt,
                    grammar=grammar_text,
                    max_tokens=120,
                    temperature=0.0,
                )
            )
            # Collect full generated text from LLM events
            gen_text = "".join(getattr(ev, "text", "") or "" for ev in events).strip()
            if gen_text:
                parsed = json.loads(gen_text)
                if isinstance(parsed, dict) and "canonical_proposition" in parsed:
                    return DistilledProposition(
                        topic=str(parsed.get("topic", topic)),
                        canonical_proposition=str(parsed["canonical_proposition"]),
                        polarity=str(parsed.get("polarity", "TRUE")),
                        confidence=0.95,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_gbnf_distillation_failed_fallback_to_cleaner", error=str(exc))

    # Deterministic programmatic distillation fallback
    clean_prop = _clean_conversational_filler(new_content)
    return DistilledProposition(
        topic=topic,
        canonical_proposition=clean_prop,
        polarity="TRUE",
        confidence=0.85,
    )


def sign_distilled_proposition(
    distilled: DistilledProposition,
    signer: DerivedFactSigner,
    source_entry_ids: list[str],
    now: float | None = None,
) -> SignedPayload:
    """
    Signs a distilled proposition under Provenance.USER_DERIVED using DerivedFactSigner.
    Adheres strictly to ADR-006 / Spec 03 provenance invariants:
    Raw LLM generations are LLM_NARRATION (forbidden from memory);
    only derived signed envelopes referencing verified source inputs are memory-eligible.
    """
    current_time = now if now is not None else time.time()
    unsigned = UnsignedPayload(
        provenance=Provenance.USER_DERIVED,
        kind="belief",
        content=distilled.canonical_proposition,
        source_entry_ids=source_entry_ids,
        structured={
            "topic": distilled.topic,
            "polarity": distilled.polarity,
            "distillation_stage": "post_turn_consolidated",
        },
        trace_id=f"distill-{uuid.uuid4().hex[:8]}",
        created_at=current_time,
        nonce=uuid.uuid4().hex,
        confidence=distilled.confidence,
    )
    return signer.sign(unsigned)


def quarantine_rejected_distillate(
    db: object,
    entry_id: str,
    reason: str,
    memory_id: int | None = None,
    stage: str = "distillation",
    now: float | None = None,
) -> None:
    """
    Persists rejected distillates to the SQLite memory_quarantine table (D-MEM-05).
    Rejected propositions are never silently discarded and remain auditable by lucca-admin.
    """
    current_time = now if now is not None else time.time()
    conn: sqlite3.Connection | None = None
    if hasattr(db, "get_writer"):
        conn = getattr(db, "get_writer")()
    elif hasattr(db, "conn"):
        conn = getattr(db, "conn")
    elif isinstance(db, sqlite3.Connection):
        conn = db

    if conn is not None:
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_quarantine (
                    memory_id INTEGER,
                    entry_id TEXT,
                    reason TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    quarantined_at REAL NOT NULL,
                    PRIMARY KEY (entry_id, quarantined_at)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO memory_quarantine (memory_id, entry_id, reason, stage, quarantined_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (memory_id, entry_id, reason, stage, current_time),
            )
            logger.info(
                "distillate_quarantined",
                entry_id=entry_id,
                reason=reason,
                stage=stage,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "quarantine_persist_failed",
                entry_id=entry_id,
                error=str(exc),
            )
