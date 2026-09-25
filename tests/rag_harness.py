"""
Project Lucca — Seeded RAG Harness shared helpers (WP-4)
Work Order #8, §6 (F-TS-06)

Shared between the T2 harness (tests/test_rag_seeded_tier2.py) and the T3
live battery (tests/test_rag_live_hw.py):
  - loads the seeded corpus (40 USER_EXPLICIT facts, 20 near-miss distractors,
    10 contradicting ASSISTANT_UTTERANCE recollections) and the 60-probe battery
  - seeds a real MemoryStore via authentic signers (no FakeLLM, no mocks)
  - judging helpers (abstention phrases, marker matching) and report writer
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Coroutine
from pathlib import Path
from typing import Final

from lucca.core.schemas import Provenance, UnsignedPayload
from lucca.memory.signers import AssistantUtteranceSigner, UserSpeechSigner
from lucca.memory.store import MemoryStore

MASTER_KEY: Final[bytes] = b"test_wp4_rag_harness_master_key_32b"
FIXTURES_DIR: Final[Path] = Path(__file__).parent / "fixtures" / "rag"
REPORTS_DIR: Final[Path] = Path(__file__).parent.parent / "logs" / "test_reports"

# Canonical abstention phrases (mirrors the WP-3 A1 live pack contract).
ABSTENTION_PHRASES: Final[frozenset[str]] = frozenset(
    {
        "no record",
        "don't recall",
        "don't have a record",
        "haven't",
        "not aware",
        "i can't find",
        "cannot find",
        "no evidence",
        "no indication",
        "i have no",
        "i'm not aware",
        "i don't recall",
        "i don't have",
        "not find",
        "no recollection",
        "not in my records",
        "no history of",
        "didn't do that",
        "did not do that",
    }
)





def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            rows.append({str(k): v for k, v in obj.items()})
    return rows


def load_corpus() -> list[dict[str, object]]:
    """Load the seeded RAG corpus (facts + distractors + recollections)."""
    return _load_jsonl(FIXTURES_DIR / "seeded_corpus.jsonl")


def load_probes() -> list[dict[str, object]]:
    """Load the 60-probe battery (40 recall / 10 abstention / 10 conflict)."""
    return _load_jsonl(FIXTURES_DIR / "probes.jsonl")


def str_field(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    return str(value) if value is not None else ""


def str_list_field(row: dict[str, object], key: str) -> list[str]:
    value = row.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def seed_rag_corpus(store: MemoryStore, now: float) -> dict[str, int]:
    """
    Seed the corpus rows into a real MemoryStore using authentic signers:
      - facts + distractors  -> USER_EXPLICIT (UserSpeechSigner), kind="fact"
      - recollections        -> ASSISTANT_UTTERANCE (AssistantUtteranceSigner),
                                kind="assistant_utterance" (grounding_eligible=0 by gate)
    Timestamps are spread deterministically across the past 1-10 days.
    Returns {corpus_id: memory_id}.
    """
    user_signer = UserSpeechSigner(master_key=MASTER_KEY)
    utt_signer = AssistantUtteranceSigner(master_key=MASTER_KEY)

    memory_ids: dict[str, int] = {}
    for i, row in enumerate(load_corpus()):
        row_id = str_field(row, "id")
        role = str_field(row, "role")
        is_recollection = role == "recollection"
        provenance = Provenance.ASSISTANT_UTTERANCE if is_recollection else Provenance.USER_EXPLICIT
        # kind must be a valid UnsignedPayload Literal: "assistant_utterance"
        # for recollections, "fact" for USER_EXPLICIT facts and distractors.
        kind = "assistant_utterance" if is_recollection else "fact"
        ts = now - (1 + (i % 10)) * 86400.0 + i * 13.0

        payload = UnsignedPayload(
            provenance=provenance,
            kind=kind,
            content=str_field(row, "content"),
            trace_id=f"tr-rag-seed-{row_id}",
            created_at=ts,
            nonce=uuid.uuid4().hex,
            confidence=0.95 if is_recollection else 1.0,
        )
        signed = utt_signer.sign(payload) if is_recollection else user_signer.sign(payload)
        memory_id = store.commit(signed, now=ts)
        memory_ids[row_id] = int(memory_id)

    return memory_ids


def has_abstention(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in ABSTENTION_PHRASES)


def has_marker(text: str, markers: list[str]) -> bool:
    lower = text.lower()
    return any(marker.lower() in lower for marker in markers)


def write_report(name: str, data: dict[str, object]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = REPORTS_DIR / f"{name}_{ts}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
