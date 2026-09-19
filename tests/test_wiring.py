"""
Project Lucca — Integration & Wiring Tests for Router and Rules Pipeline
Spec 05 §4, §6, §8, §9, Spec 06 §1, §2, §4 (F-ARCH-001)
"""

import asyncio
import os
import time
from collections.abc import Generator
from pathlib import Path

import pytest

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    Done,
    LLMEvent,
    LLMUsage,
    MemoryHit,
    Provenance,
    Risk,
    TokenDelta,
    ToolParameter,
    ToolSchema,
    UnsignedPayload,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import UserSpeechSigner
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS

SAMPLE_RULE = """
(rule "open-calc-v1"
  :when (and (intent= "launch_app") (entity-has? "app" "calculator"))
  :plan (list (say "Launching calculator") (tool "launch_app" :app "calculator"))
  :priority 5)
"""


class SpyLLM(FakeLLM):
    """Spy FakeLLM tracking whether stream_turn was called."""

    def __init__(self, script: list[LLMEvent] | None = None) -> None:
        super().__init__(script=script)
        self.call_count = 0

    def stream_turn(
        self,
        current_audio_b64: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> Generator[LLMEvent, None, None]:
        self.call_count += 1
        yield from super().stream_turn(
            current_audio_b64=current_audio_b64,
            current_text=current_text,
            memories=memories,
            history=history,
            temperature=temperature,
            max_tokens=max_tokens,
        )


@pytest.mark.tier2
def test_phase4_router_and_rules_wiring(tmp_path: Path) -> None:
    """
    F-ARCH-001 (Phase 4 Wiring Integration Gate):
    1. Quarantine rule evaluates in shadow mode during normal turns without altering active behavior.
    2. Decisions and decision labels are logged to SQLite.
    3. Counterfactual rule firing is tracked.
    4. Upon promotion to ACTIVE, router selects RouteAction.RULE.
    5. Rule plan executes deterministic actions (Say + ToolCall) and LLM is bypassed.
    """
    db_file = tmp_path / "wiring_test.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    tools = {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
        )
    }

    rule_engine = RuleLifecycleManager(registered_tools=tools)
    managed_rule = rule_engine.register_rule(SAMPLE_RULE)
    assert managed_rule.status == "QUARANTINE"

    # Turn 1: Rule is in QUARANTINE.
    # User says "open calculator".
    # LLM should be invoked because rule is not active yet.
    # Shadow evaluation should record success cluster on the quarantined rule.
    fake_script_1 = [
        TokenDelta(delta="Opening calculator for you now."),
        Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=5)),
    ]
    llm1 = SpyLLM(script=fake_script_1)
    orch = Orchestrator(
        tts=FakeTTS,
        llm=llm1,
        db=db,
        rule_engine=rule_engine,
        execute_tools=False,
    )

    try:
        orch._on_user_text(ts_ns=1000, user_text="open calculator")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=5.0)

        # 1. Verify LLM was invoked on Turn 1
        assert llm1.call_count == 1

        # 2. Verify shadow evaluation fired for quarantined rule and recorded 1 cluster
        assert len(managed_rule.success_clusters) == 1

        # 3. Verify router ran: action was LLM because rule is in QUARANTINE
        with db.read_cursor() as cur:
            cur.execute(
                "SELECT decision_id, action, counterfactual_rule_fired FROM decisions ORDER BY ts ASC"
            )
            rows = cur.fetchall()
            assert len(rows) == 1
            dec1_id, dec1_action, dec1_counterfactual = rows[0]
            assert dec1_action == "LLM"
            assert dec1_counterfactual == 1  # quarantine rule fired in shadow

            # 4. Verify decision label was persisted
            cur.execute(
                "SELECT label, reason FROM decision_labels WHERE decision_id = ?",
                (dec1_id,),
            )
            label1 = cur.fetchone()
            assert label1 is not None
            assert label1[0] in ("POS", "NEG", "INDETERMINATE")

        # Turn 2: Promote rule to ACTIVE
        # Record 4 more distinct clusters so it reaches 5 distinct clusters
        base_ts = 2000000.0
        for i in range(1, 5):
            rule_engine.record_shadow(
                "open-calc-v1",
                matched=True,
                cluster_id=f"cluster_turn1_{i}_{base_ts + i * 1200}",
            )

        promo_result = rule_engine.promote_if_eligible("open-calc-v1")
        assert promo_result.promoted is True
        assert managed_rule.status == "ACTIVE"

        # Now configure LLM spy for Turn 2: if LLM is called, call_count will be > 0
        llm2 = SpyLLM(script=[])
        orch.llm = llm2

        orch._on_user_text(ts_ns=2000, user_text="open calculator")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=5.0)

        # 5. Verify RouteAction.RULE was selected and LLM was bypassed (call_count == 0)
        assert llm2.call_count == 0

        # Verify tool was executed in orchestrator
        assert len(orch.executed_tools) >= 1
        last_tool = orch.executed_tools[-1]
        assert last_tool[0] == "launch_app"
        assert last_tool[1] == {"app": "calculator"}

        # 6. Verify decisions and labels in SQLite for Turn 2
        with db.read_cursor() as cur:
            cur.execute(
                "SELECT decision_id, action, counterfactual_rule_fired FROM decisions ORDER BY ts ASC"
            )
            rows = cur.fetchall()
            assert len(rows) == 2
            dec2_id, dec2_action, dec2_counterfactual = rows[1]
            assert dec2_action == "RULE"
            assert dec2_counterfactual == 0

            cur.execute(
                "SELECT label, reason FROM decision_labels WHERE decision_id = ?",
                (dec2_id,),
            )
            label2 = cur.fetchone()
            assert label2 is not None

    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
        db.close()


@pytest.mark.tier2
def test_phase6_memory_and_rules_promotion_wiring(tmp_path: Path) -> None:
    """
    F-DRIFT-001 (Phase 6 T2 Integration Gate: Memory Retrieval/Commit & Rule Promotion):
    1. Memory fact committed via cryptographic gate with UserSpeechSigner.
    2. Orchestrator turn queries MemoryStore; prompt builder passes retrieved memories.
    3. User transcript is committed as USER_EXPLICIT fact in POSTTURN state.
    4. Quarantined rule accumulates shadow execution across 5 distinct clusters.
    5. Rule is promoted to ACTIVE and persists to SQLite across engine reload.
    6. Subsequent turn executes promoted rule directly, bypassing LLM inference.
    """
    db_file = tmp_path / "phase6_wiring.sqlite"
    db = DatabaseManager(db_file)
    db.migrate()

    test_key = b"01234567890123456789012345678901"
    store = MemoryStore(db=db, master_key=test_key, embedding_port=LocalEmbeddingPort())

    # 1. Commit initial memory fact via cryptographic gate
    user_signer = UserSpeechSigner(master_key=test_key)
    unsigned_fact = UnsignedPayload(
        content="User favorite programming language is Python",
        provenance=Provenance.USER_EXPLICIT,
        kind="fact",
        nonce=os.urandom(16).hex(),
        created_at=time.time() - 100,
        trace_id="init-fact-turn",
    )
    signed_fact = user_signer.sign(unsigned_fact)
    asyncio.run(store.commit(signed_fact))

    tools = {
        "launch_app": ToolSchema(
            name="launch_app",
            description="Launch application",
            parameters={"app": ToolParameter(type="string", description="App name")},
            risk=Risk.LAUNCH,
        )
    }

    # Register candidate rule in QUARANTINE
    rule_engine = RuleLifecycleManager(registered_tools=tools, db=db)
    managed_rule = rule_engine.register_rule(SAMPLE_RULE)
    assert managed_rule.status == "QUARANTINE"

    # Turn 1: User asks a question that retrieves the stored memory
    fake_script_1 = [
        TokenDelta(delta="Python is your stated preference!"),
        Done(usage=LLMUsage(prompt_tokens=15, completion_tokens=6)),
    ]
    llm1 = SpyLLM(script=fake_script_1)
    orch = Orchestrator(
        tts=FakeTTS,
        llm=llm1,
        db=db,
        rule_engine=rule_engine,
        memory_store=store,
        master_key=test_key,
        execute_tools=False,
    )

    try:
        orch._on_user_text(ts_ns=1000, user_text="What programming language do I prefer?")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=5.0)

        # 2. Verify LLM was invoked and received the retrieved memory hit
        assert llm1.call_count == 1
        assert llm1.last_memories is not None
        assert any("Python" in m.content for m in llm1.last_memories)

        # 3. Verify user transcript was committed to memory in POSTTURN
        with db.read_cursor() as cur:
            cur.execute(
                "SELECT content, kind FROM memories WHERE content = ?",
                ("What programming language do I prefer?",),
            )
            committed_row = cur.fetchone()
            assert committed_row is not None
            assert committed_row[0] == "What programming language do I prefer?"

            cur.execute(
                "SELECT count(*) FROM provenance_envelopes WHERE provenance = 'USER_EXPLICIT'"
            )
            total_explicit = cur.fetchone()
            assert total_explicit is not None and total_explicit[0] >= 2

        # 4. Record 5 distinct clusters for the quarantined rule across distinct intervals
        base_ts = 3000000.0
        for i in range(5):
            rule_engine.record_shadow(
                "open-calc-v1",
                matched=True,
                cluster_id=f"cluster_phase6_{i}_{base_ts + i * 1200}",
            )

        promo = rule_engine.promote_if_eligible("open-calc-v1")
        assert promo.promoted is True
        assert managed_rule.status == "ACTIVE"

        # 5. Verify rule promotion persisted across engine restart
        restarted_engine = RuleLifecycleManager(registered_tools=tools, db=db)
        assert restarted_engine.rules["open-calc-v1"].status == "ACTIVE"
        orch.rule_engine = restarted_engine

        # 6. Turn 2: User says "open calculator" -> matches newly ACTIVE rule
        llm2 = SpyLLM(script=[])
        orch.llm = llm2

        orch._on_user_text(ts_ns=2000, user_text="open calculator")
        if orch.active_turn_thread:
            orch.active_turn_thread.join(timeout=5.0)

        # Verify LLM was bypassed on Turn 2
        assert llm2.call_count == 0
        assert orch.last_decision is not None
        assert orch.last_decision.executed_path == "RULE"
        assert len(orch.executed_tools) >= 1
        assert orch.executed_tools[-1][0] == "launch_app"
        assert orch.executed_tools[-1][1] == {"app": "calculator"}

    finally:
        orch.stop()
        orch.cap_ring.close()
        orch.cap_ring.unlink()
        orch.play_ring.close()
        orch.play_ring.unlink()
        db.close()
