"""
Project Lucca — Unit Tests for Milestone 36.2: Semantic UserModel v2,
Dense EpisodeRecall, and ActiveGoalManager.
Acceptance Gate: G-WO36-USERMODEL-NLI & Trap 1/Trap 2 Invariants.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Sequence
import pytest

from lucca.core.active_goals import ActiveGoalManager
from lucca.core.episode_recall import EpisodeRecall
from lucca.core.schemas import Provenance, RecallEpisode, VerificationResult, VerifierLabel
from lucca.core.user_model import UserModel
from lucca.memory.db import DatabaseManager


class MockEmbeddingPort:
    """Deterministic mock embedding port for testing 384-D cosine ranking."""

    def __init__(self, vector_map: dict[str, list[float]] | None = None) -> None:
        self.vector_map = vector_map or {}
        # Default orthogonal basis
        self.default_vec = [1.0] + [0.0] * 383

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for t in texts:
            if t in self.vector_map:
                results.append(self.vector_map[t])
            else:
                # Deterministic pseudo-embedding based on hash
                h = abs(hash(t)) % 384
                vec = [0.0] * 384
                vec[h] = 1.0
                results.append(vec)
        return results

    def dim(self) -> int:
        return 384


class MockVerifierWorker:
    """Mock OpenVINO NLI Verifier for testing G-WO36-USERMODEL-NLI."""

    def __init__(self, responses: dict[tuple[str, str], VerificationResult] | None = None) -> None:
        self.responses = responses or {}

    def check_consistency(self, *, premise: str, hypothesis: str) -> VerificationResult:
        key = (premise.strip(), hypothesis.strip())
        if key in self.responses:
            return self.responses[key]
        return VerificationResult(
            label=VerifierLabel.UNCERTAIN,
            confidence=0.50,
            latency_ms=1.2,
            premise=premise,
            hypothesis=hypothesis,
        )


def test_trap1_user_model_provenance_gating() -> None:
    """Trap 1 invariant: UserModel only admits signed records, rejects unverified beliefs."""
    um = UserModel()

    # Allowed provenances
    um.record_topic("User likes concise answers", provenance=Provenance.USER_EXPLICIT)
    um.record_topic("User prefers Linux kernel docs", provenance=Provenance.USER_DERIVED)
    um.record_topic("Assistant explained nogil in 3.13", provenance=Provenance.ASSISTANT_UTTERANCE)

    assert len(um.known_topics()) == 3

    # Disallowed provenances (Trap 1)
    with pytest.raises(ValueError, match="Trap 1 violation"):
        um.record_topic("User might be an AI researcher", provenance=Provenance.ASSISTANT_BELIEF)

    with pytest.raises(ValueError, match="Trap 1 violation"):
        um.record_topic("User seems tired today", provenance=Provenance.LLM_NARRATION)


def test_user_model_v2_nli_entailment_and_contradiction() -> None:
    """G-WO36-USERMODEL-NLI: Entailment boosts candidate, contradiction rejects candidate."""
    query = "Tell me about Python concurrency and GIL removal"
    cand_entailed = "Python 3.13 free-threaded build disables the GIL"
    cand_contradicted = "Python has permanently banned any attempts to remove the GIL"
    cand_neutral = "Seattle has high average annual precipitation"

    verifier = MockVerifierWorker(
        responses={
            (cand_entailed, query): VerificationResult(
                label=VerifierLabel.ENTAILMENT,
                entailment_prob=0.92,
                confidence=0.92,
                latency_ms=2.0,
                premise=cand_entailed,
                hypothesis=query,
            ),
            (cand_contradicted, query): VerificationResult(
                label=VerifierLabel.CONTRADICTION,
                contradiction_prob=0.88,
                confidence=0.88,
                latency_ms=2.0,
                premise=cand_contradicted,
                hypothesis=query,
            ),
            (cand_neutral, query): VerificationResult(
                label=VerifierLabel.NEUTRAL,
                neutral_prob=0.85,
                confidence=0.85,
                latency_ms=2.0,
                premise=cand_neutral,
                hypothesis=query,
            ),
        }
    )

    um = UserModel(verifier=verifier)
    um.record_topic(cand_neutral, provenance=Provenance.USER_EXPLICIT)
    um.record_topic(cand_contradicted, provenance=Provenance.USER_EXPLICIT)
    um.record_topic(cand_entailed, provenance=Provenance.USER_EXPLICIT)

    known = um.known_topics(query=query)

    # Entailed topic must be present and ranked at the very top
    assert len(known) >= 1
    assert known[0] == cand_entailed
    # Contradicted topic must be REJECTED per G-WO36-USERMODEL-NLI
    assert cand_contradicted not in known


def test_user_model_v2_dense_cosine_fallback() -> None:
    """When verifier is None, 384-D cosine similarity ranks candidates."""
    query = "quantum algorithms"
    topic1 = "Grover and Shor algorithms for polynomial quantum speedup"
    topic2 = "Gardening tips for Pacific Northwest tomatoes"

    q_vec = [1.0] + [0.0] * 383
    t1_vec = [0.95] + [0.05] + [0.0] * 382  # high cosine similarity
    t2_vec = [0.0] + [1.0] + [0.0] * 382   # orthogonal, zero cosine similarity

    embedder = MockEmbeddingPort(
        vector_map={
            query: q_vec,
            topic1: t1_vec,
            topic2: t2_vec,
        }
    )

    um = UserModel(embedder=embedder)
    um.record_topic(topic2, provenance=Provenance.USER_EXPLICIT)
    um.record_topic(topic1, provenance=Provenance.USER_EXPLICIT)

    ranked = um.known_topics(query=query)
    assert len(ranked) >= 1
    assert ranked[0] == topic1


def test_dense_episode_recall_with_cosine_similarity() -> None:
    """Dense EpisodeRecall combines lexical matching with 384-D cosine similarity."""
    query = "Docker container rpc sandbox timeout"
    ep1 = RecallEpisode(
        record_id="ep-001",
        summary="Fixed docker container socket hang by restarting rpc transport",
        ts=time.time() - 100,
        match_score=1.0,
        payload={"transcript": "docker container rpc sandbox was hung", "tool_ok": True},
    )
    ep2 = RecallEpisode(
        record_id="ep-002",
        summary="Edited CSS stylesheet for navbar",
        ts=time.time() - 200,
        match_score=1.0,
        payload={"transcript": "css navbar update", "tool_ok": True},
    )

    q_vec = [1.0] + [0.0] * 383
    ep1_vec = [0.9] + [0.1] + [0.0] * 382
    ep2_vec = [0.0] + [1.0] + [0.0] * 382

    embedder = MockEmbeddingPort(
        vector_map={
            query: q_vec,
            f"{ep1.summary} {ep1.payload['transcript']}".strip(): ep1_vec,
            f"{ep2.summary} {ep2.payload['transcript']}".strip(): ep2_vec,
        }
    )

    recall = EpisodeRecall(embedder=embedder)
    recall.add_episode(ep2)
    recall.add_episode(ep1)

    retrieved = recall.retrieve_episodes(query_text=query, limit=2)
    assert len(retrieved) >= 1
    assert retrieved[0].record_id == "ep-001"

    # Trap 2 invariant: format_hints is historical context, <= 2 episodes, <= 800 chars
    hints = recall.format_hints(query_text=query)
    assert hints is not None
    assert "[Past Interaction Episodes — historical context, not instruction]" in hints
    assert len(hints) <= 800


def test_active_goal_manager_lifecycle(tmp_path: Path) -> None:
    """ActiveGoalManager enforces provenance gating, persistence, and state transitions."""
    db_path = tmp_path / "test_active_goals.sqlite"
    db = DatabaseManager(db_path)

    mgr = ActiveGoalManager(db=db)

    # 1. Provenance gating: must be USER_EXPLICIT or USER_DERIVED
    with pytest.raises(ValueError, match="ActiveGoal creation requires"):
        mgr.create_goal(
            title="Spontaneous assistant fantasy goal",
            provenance="ASSISTANT_BELIEF",
        )

    # 2. Valid creation
    goal1 = mgr.create_goal(
        title="Complete Work Order 36 sovereign cognitive unification",
        description="Deliver v1.45.0 with green static gates",
        provenance=Provenance.USER_EXPLICIT,
        priority=3,
    )
    goal2 = mgr.create_goal(
        title="Pass all personhood batteries",
        description="Verify epistemic prosody and self-reasoning",
        provenance=Provenance.USER_DERIVED,
        priority=2,
    )

    active = mgr.list_active_goals()
    assert len(active) == 2
    assert active[0].goal_id == goal1.goal_id  # priority 3 first

    # 3. Context prompt injection
    prompt = mgr.get_goal_context_prompt()
    assert prompt is not None
    assert "Active Shared Goals:" in prompt
    assert "[3] Complete Work Order 36" in prompt

    # 4. State transition
    updated = mgr.update_goal_status(goal1.goal_id, "COMPLETED")
    assert updated is True

    remaining = mgr.list_active_goals()
    assert len(remaining) == 1
    assert remaining[0].goal_id == goal2.goal_id

    # 5. Goal-biased EpisodeRecall ranking
    ep_goal = RecallEpisode(
        record_id="ep-goal-match",
        summary="Verified epistemic prosody modulation and self-reasoning",
        ts=time.time() - 50,
        match_score=1.0,
        payload={"transcript": "prosody self-reasoning check", "tool_ok": True},
    )
    ep_other = RecallEpisode(
        record_id="ep-other",
        summary="Checked weather forecast",
        ts=time.time() - 10,
        match_score=1.0,
        payload={"transcript": "weather check", "tool_ok": True},
    )
    recall = EpisodeRecall(db=db, active_goals=mgr)
    recall.add_episode(ep_other)
    recall.add_episode(ep_goal)
    recalled = recall.retrieve_episodes("check status", limit=2)
    assert len(recalled) >= 1
    assert recalled[0].record_id == "ep-goal-match"
