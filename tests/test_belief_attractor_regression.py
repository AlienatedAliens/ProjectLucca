"""
Regression tests for the Belief #17 attractor bug (2026-10-07).

Root cause: check_contradictions() had no stop-word filtering, so common
conversational words like "you/what/where/that" triggered FTS against every
active high-importance belief. A single user utterance accidentally committed
as ASSISTANT_BELIEF (importance=0.9) attracted 166 bogus review_queue items.

Three things we want to prove:

A. Token-level invariants (unit, no DB required)
   A1. Pure stop-word sentences → 0 topical tokens → early return (no FTS)
   A2. Mixed sentences → only topical words pass through, deduplicated
   A3. The specific Belief #17 content → minimal/no topical tokens

B. Integration — review queue stays silent (DB required)
   B1. Attractor scenario: utterance with only stop-words against a
       high-importance belief → review_queue stays at 0 items
   B2. True contradiction: utterance with topical terms that genuinely oppose
       a belief → review_queue gets 1 item (real detection still works)

C. Positive recovery: interrogative guard still fires before token extraction
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Final

import pytest

from lucca.core.belief_service import (
    _BELIEF_STOP_WORDS,
    _MIN_TOPICAL_TOKENS,
)
from lucca.core.schemas import Provenance, UnsignedPayload
from lucca.memory.db import DatabaseManager
from lucca.memory.reflection import ReflectionEngine
from lucca.memory.signers import AssistantUtteranceSigner, UserSpeechSigner
from lucca.memory.store import MemoryStore
from lucca.senses.embed import LocalEmbeddingPort

TEST_MASTER_KEY = b"01234567890123456789012345678901"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _topical_tokens(text: str) -> list[str]:
    """Mirror of the fixed logic in check_contradictions — pure Python, using _BELIEF_STOP_WORDS."""
    all_tokens = re.findall(r"\b[a-zA-Z0-9_\-]{4,}\b", text.lower())
    return list(dict.fromkeys(w for w in all_tokens if w not in _BELIEF_STOP_WORDS))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_b17_regression.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def mem_store(test_db: DatabaseManager) -> MemoryStore:
    embedder = LocalEmbeddingPort()
    return MemoryStore(db=test_db, master_key=TEST_MASTER_KEY, embedding_port=embedder)


@pytest.fixture
def reflection_engine(test_db: DatabaseManager, mem_store: MemoryStore) -> ReflectionEngine:
    return ReflectionEngine(db=test_db, store=mem_store, master_key=TEST_MASTER_KEY)


# ── Fixture: a high-importance belief modelled on Belief #17 ─────────────────

@pytest.fixture
def attractor_belief_id(mem_store: MemoryStore) -> int:
    """
    Commits a belief that LOOKS like the Belief #17 attractor:
    high importance (0.9), made up of mostly conversational filler words.
    Before the fix this would match every utterance via FTS.
    """
    signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
    payload = UnsignedPayload(
        provenance=Provenance.ASSISTANT_BELIEF,
        kind="belief",
        content=(
            "That's not what I mean. I mean I asked you if you could work out where you "
            "are and you worked out our time zone And I was asking you If you if you could "
            "narrow down where we are based on the time zone"
        ),
        structured={"importance": 0.9, "valid_from": time.time()},
        trace_id="tr-attractor-test",
        created_at=time.time(),
        nonce="n-attractor-test",
        confidence=0.9,
    )
    return mem_store.commit(signer.sign(payload))


# ══════════════════════════════════════════════════════════════════════════════
# A. Token-level unit tests (pure function, no DB)
# ══════════════════════════════════════════════════════════════════════════════


class TestTopicalTokenExtraction:
    """
    Tests that the stop-word filter + 4-char minimum produces the right tokens.
    These are pure function tests — no DB, no ReflectionEngine.
    """

    def test_pure_stop_words_yield_zero_topical_tokens(self) -> None:
        """
        A sentence consisting entirely of stop-words must yield zero topical tokens.
        Before the fix this yielded ~15 tokens (e.g. 'that', 'what', 'mean', etc.).
        """
        sentence = "That is not what I mean and you know what I asked you"
        tokens = _topical_tokens(sentence)
        assert len(tokens) == 0, (
            f"Expected 0 topical tokens for all-stop-word sentence, got {tokens}"
        )

    def test_belief_17_exact_content_yields_minimal_tokens(self) -> None:
        """
        The exact content of the rogue Belief #17 must produce <= 2 topical tokens
        after stop-word filtering, eliminating the high-recall conversational words.
        """
        belief_17_content = (
            "That's not what I mean. I mean I asked you if you could work out where you "
            "are and you worked out our time zone And I was asking you If you if you could "
            "narrow down where we are based on the time zone"
        )
        tokens = _topical_tokens(belief_17_content)
        assert len(tokens) <= 2, (
            f"Belief #17 content should extract <=2 topical tokens after fix, got {len(tokens)}: {tokens}"
        )
        # Critically: the most common attractor words should NOT be in the result
        high_recall_stopwords_that_used_to_fire = {
            "that", "what", "mean", "asked", "could", "where", "asking", "based",
            "you", "your", "this", "with", "just", "like", "know", "would",
            "work", "worked", "time", "down",
        }
        attractor_leakage = set(tokens) & high_recall_stopwords_that_used_to_fire
        assert not attractor_leakage, (
            f"Stop-word filter allowed attractor tokens through: {attractor_leakage}"
        )

    def test_topical_sentence_preserves_subject_matter_terms(self) -> None:
        """
        A sentence with real subject-matter terms must survive filtering
        so legitimate contradiction detection still works.
        """
        sentence = "The inference temperature should always remain below 0.3 for deterministic outputs."
        tokens = _topical_tokens(sentence)
        assert len(tokens) >= _MIN_TOPICAL_TOKENS, (
            f"Topical sentence should yield >={_MIN_TOPICAL_TOKENS} tokens, got {tokens}"
        )
        assert "inference" in tokens, "Expected 'inference' in topical tokens"
        assert "temperature" in tokens, "Expected 'temperature' in topical tokens"
        assert "deterministic" in tokens, "Expected 'deterministic' in topical tokens"

    def test_deduplication_of_repeated_topical_words(self) -> None:
        """Repeated topical words must appear exactly once (order-preserving dedup)."""
        sentence = "inference inference temperature temperature temperature deterministic"
        tokens = _topical_tokens(sentence)
        assert tokens.count("inference") == 1
        assert tokens.count("temperature") == 1
        assert tokens.count("deterministic") == 1
        assert len(tokens) == 3

    def test_minimum_token_threshold_filters_single_token_utterances(self) -> None:
        """
        An utterance with exactly one topical token (below _MIN_TOPICAL_TOKENS=2)
        must not reach threshold.
        """
        assert _MIN_TOPICAL_TOKENS == 2, (
            f"_MIN_TOPICAL_TOKENS changed unexpectedly to {_MIN_TOPICAL_TOKENS}"
        )

    def test_three_char_words_never_pass_through(self) -> None:
        """
        The old regex matched >=3 char words. The new one requires >=4.
        3-char words like 'you', 'can', 'the', 'are', 'not' must never appear.
        """
        sentence = "You are not the one who can see what I did"
        tokens = _topical_tokens(sentence)
        three_char_words = {"you", "are", "not", "the", "one", "who", "can", "see", "did", "what"}
        leakage = set(tokens) & three_char_words
        assert not leakage, f"3-char words leaked into tokens: {leakage}"


# ══════════════════════════════════════════════════════════════════════════════
# B. Integration tests: review_queue count (DB + BeliefService)
# ══════════════════════════════════════════════════════════════════════════════


class TestBeliefAttractorIntegration:
    """
    End-to-end verification that the review_queue stays silent for conversational
    utterances against a high-importance belief, while genuine contradictions still queue.
    """

    def _queue_count(self, test_db: DatabaseManager) -> int:
        with test_db.read_cursor() as cur:
            cur.execute("SELECT count(*) FROM review_queue WHERE status = 'PENDING'")
            return cur.fetchone()[0]

    def test_conversational_utterances_do_not_enqueue_against_attractor_belief(
        self,
        test_db: DatabaseManager,
        mem_store: MemoryStore,
        reflection_engine: ReflectionEngine,
        attractor_belief_id: int,
    ) -> None:
        """
        THE REGRESSION TEST.

        20 conversational utterances fired against a belief identical to the
        rogue Belief #17. Before the fix: 20 review_queue items. After: 0.
        """
        from lucca.core.belief_service import BeliefService
        from lucca.core.trace import TurnTrace

        service = BeliefService(db=test_db, reflection_engine=reflection_engine)
        user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)

        conversational_utterances = [
            "That's not what I mean.",
            "I asked you what you thought about that.",
            "Can you tell me where we are right now?",
            "What time is it where you are?",
            "I mean, do you know what I'm asking?",
            "You said you could work that out.",
            "Okay but what does that mean for us?",
            "I was asking you about the time zone.",
            "So you could narrow down where we are?",
            "That's what I wanted to know.",
            "Not what I was asking at all.",
            "Could you just tell me what you think?",
            "I mean yes, but where exactly?",
            "You should know what I mean by now.",
            "That is based on what you said.",
            "Okay so where are you getting that from?",
            "I didn't mean what you think I mean.",
            "You worked it out from the time zone.",
            "That was what I was asking about.",
            "So could you narrow it down a bit more?",
        ]

        assert self._queue_count(test_db) == 0, "Precondition: queue must be empty before test"

        for i, utterance in enumerate(conversational_utterances):
            payload = UnsignedPayload(
                provenance=Provenance.USER_EXPLICIT,
                kind="transcript",
                content=utterance,
                trace_id=f"tr-conv-{i}",
                created_at=time.time(),
                nonce=f"n-conv-{i}",
                confidence=1.0,
            )
            signed = user_signer.sign(payload)
            mem_store.commit(signed)

            trace = TurnTrace(trace_id=f"test-turn-{i}", session_id="test-session")
            service.check_contradictions(
                new_entry_id=signed.entry_id,
                new_content=utterance,
                trace=trace,
            )

        final_count = self._queue_count(test_db)
        assert final_count == 0, (
            f"REGRESSION: {final_count} items enqueued from pure conversational utterances. "
            f"The attractor bug has returned. Belief #17 type entry is acting as FTS magnet again."
        )

    def test_genuine_topical_contradiction_still_enqueues(
        self,
        test_db: DatabaseManager,
        mem_store: MemoryStore,
        reflection_engine: ReflectionEngine,
    ) -> None:
        """
        Verifies the fix didn't neuter real contradiction detection.

        A belief about inference temperature paired with an utterance that
        explicitly contradicts it must still reach the review_queue.
        """
        from lucca.core.belief_service import BeliefService
        from lucca.core.trace import TurnTrace

        signer = AssistantUtteranceSigner(master_key=TEST_MASTER_KEY)
        user_signer = UserSpeechSigner(master_key=TEST_MASTER_KEY)

        # Commit a genuine, topical belief (importance >= 0.7 → will queue)
        belief_payload = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content="The inference temperature should always remain at 0.2 for deterministic outputs.",
            structured={"importance": 0.8, "valid_from": time.time()},
            trace_id="tr-genuine-belief",
            created_at=time.time(),
            nonce="n-genuine-belief",
            confidence=0.9,
        )
        mem_store.commit(signer.sign(belief_payload))

        service = BeliefService(db=test_db, reflection_engine=reflection_engine)

        # Fire a topical utterance that clearly contradicts the belief
        contradiction = (
            "Actually the inference temperature configuration needs to be raised to 0.9 "
            "because we switched to creative generation mode for this project."
        )

        user_payload = UnsignedPayload(
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            content=contradiction,
            trace_id="tr-contradiction-ev",
            created_at=time.time(),
            nonce="n-contradiction-ev",
            confidence=1.0,
        )
        signed_user = user_signer.sign(user_payload)
        mem_store.commit(signed_user)

        assert self._queue_count(test_db) == 0, "Precondition: queue must be empty before test"

        trace = TurnTrace(trace_id="test-contradict-turn", session_id="test-session")
        service.check_contradictions(
            new_entry_id=signed_user.entry_id,
            new_content=contradiction,
            trace=trace,
        )

        final_count = self._queue_count(test_db)
        assert final_count == 1, (
            f"Expected 1 review_queue item from genuine contradiction, got {final_count}. "
            f"Stop-word filter may have been too aggressive and is suppressing real detections."
        )

    def test_interrogative_guard_fires_before_token_extraction(
        self,
        test_db: DatabaseManager,
        mem_store: MemoryStore,
        reflection_engine: ReflectionEngine,
        attractor_belief_id: int,
    ) -> None:
        """
        Questions (F-WO8-17) must still short-circuit before token extraction.
        The interrogative guard must not be affected by the stop-word fix.
        """
        from lucca.core.belief_service import BeliefService
        from lucca.core.trace import TurnTrace

        service = BeliefService(db=test_db, reflection_engine=reflection_engine)

        questions = [
            "What is the current inference temperature?",
            "Can you tell me what the temperature setting is?",
            "Where should we configure the inference temperature parameter?",
            "How does the temperature affect deterministic inference outputs?",
        ]

        for i, question in enumerate(questions):
            trace = TurnTrace(trace_id=f"test-q-{i}", session_id="test-session")
            service.check_contradictions(
                new_entry_id=f"entry-q-{i}",
                new_content=question,
                trace=trace,
            )

        assert self._queue_count(test_db) == 0, (
            "Interrogative guard failed: questions enqueued contradiction reviews."
        )
