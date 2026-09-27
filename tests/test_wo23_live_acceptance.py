"""
Project Lucca — WO-23 Phase 2: Live Acceptance
Walton Scheme Completion, Transcript Normalization Parity, and Log Rotation.

Functional Acceptance (Spec 06 §2, Spec 08 §3, Spec 11 §1, WO-23 Phase 2):
1. Walton schemes: present 4 live claims, one per new scheme (SIGN, ANALOGY,
   CONSEQUENCE, PRECEDENT), each with seeded source receipts -> she evaluates
   the correct scheme per premise shape, speaks the critical-question outcome
   with hedge, and a VIOLATED question produces a conditions-carried inference
   (defeasible, not refuted).
2. ITEM-018: an utterance with trailing punctuation + mixed casing routes
   identically through the router and matches the same rule as its normalized form.
3. Rotation: simulate a date boundary -> old file rotated, retention pruned,
   next write lands in the new file; no lost decisions.
4. R.1 includes verbatim spoken output for the scheme scenarios.
5. Traps: fault injection / date mocking / file fixtures must be fixture-scoped
   with zero leakage into other tests.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lucca.core.coherence import ToolReceipt
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import (
    DecisionRecord,
    Done,
    ExecutionTier,
    LLMUsage,
    Provenance,
    RouteAction,
    RouteDecision,
    RouteFeatures,
    TokenDelta,
    UnsignedPayload,
)
from lucca.core.signer_factory import SignerFactory
from lucca.core.text_utils import normalize_transcript
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.store import MemoryStore
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.router.heuristic import HeuristicRouter
from lucca.sandbox.service import SandboxService
from lucca.senses.embed import LocalEmbeddingPort
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS

TEST_MASTER_KEY = b"01234567890123456789012345678901"


@pytest.fixture
def live_db(tmp_path: Path) -> DatabaseManager:
    """Provides a fresh migrated database instance for live acceptance."""
    db_path = tmp_path / "live_acceptance_wo23.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def signer_factory() -> SignerFactory:
    """Provides a SignerFactory using the test master key."""
    return SignerFactory(master_key=TEST_MASTER_KEY)


@pytest.fixture
def live_orch(live_db: DatabaseManager, tmp_path: Path) -> Orchestrator:
    """Provides a hermetic Orchestrator instance configured for live acceptance scenarios."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    store = MemoryStore(
        db=live_db,
        master_key=TEST_MASTER_KEY,
        embedding_port=LocalEmbeddingPort(),
    )
    sandbox = SandboxService(workspace_root=workspace, use_direct_fallback=True)
    router = HeuristicRouter()
    rule_engine = RuleLifecycleManager(db=live_db)

    orch = Orchestrator(
        tts=FakeTTS,
        asr=FakeASR,
        sandbox=sandbox,
        execute_tools=True,
        router=router,
        db=live_db,
        rule_engine=rule_engine,
        memory_store=store,
        master_key=TEST_MASTER_KEY,
    )
    orch.current_turn_receipts = []
    orch.executed_tools = []
    orch.history = []
    orch.state = "idle"
    orch.running = True
    orch.current_turn_tier = ExecutionTier.FULL_LOOP
    return orch


def _make_decision_record(decision_id: str, ts: float, transcript: str) -> DecisionRecord:
    """Helper to synthesize a DecisionRecord for rotation testing."""
    return DecisionRecord(
        decision_id=decision_id,
        trace_id=f"tr-{decision_id}",
        session_id="sess-live-01",
        ts=ts,
        features=RouteFeatures(
            transcript=transcript,
            any_active_rule_fired=False,
            any_quarantine_rule_fired=False,
            vad_speech_ms=1000,
            intent="launch_app",
            intent_conf=0.95,
            hour_local=12,
            weekday=1,
            apps_running=[],
            last_tool=None,
            last_tool_ok=None,
            session_turns=0,
            mode="transcript",
            has_registered_rule=False,
        ),
        decision=RouteDecision(
            action=RouteAction.RULE,
            tier=ExecutionTier.REFLEX,
            probabilities={"RULE": 0.95, "LLM": 0.05, "CLARIFY": 0.0},
            prediction_set=[RouteAction.RULE],
            fallback_applied=False,
            elapsed_us=500,
        ),
        router_version="heuristic-1.0-deterministic",
        executed_path="RULE",
        counterfactual_rule_fired=False,
    )


# ============================================================================
# 1. Walton Schemes Live Acceptance (SIGN, ANALOGY, CONSEQUENCE, PRECEDENT)
# ============================================================================


def test_wo23_live_acceptance_walton_schemes(
    live_orch: Orchestrator, signer_factory: SignerFactory
) -> None:
    """Walton schemes live functional acceptance:
    Present 4 live claims, one per new scheme, each with seeded source receipts:
    - SIGN: symptom claim with seeded receipt; alternative explanation in store causes CQ failure;
    - ANALOGY: case comparison with seeded receipt; relevant difference in store causes CQ failure;
    - CONSEQUENCE: causal claim with seeded receipt; countervailing side effect causes CQ failure;
    - PRECEDENT: prior case ruling with seeded receipt; superseded/overruled status causes CQ failure.

    For each:
    - Orchestrator evaluates the correct scheme per premise shape;
    - Speaks the critical-question outcome with hedge;
    - A VIOLATED question produces a conditions-carried inference (defeasible, not refuted);
    - Verbatim spoken output recorded for owner review.
    """
    user_signer = signer_factory.user_speech()
    spoken_history: list[str] = []
    live_orch._speak_text = lambda trace, text: spoken_history.append(text)

    # ------------------------------------------------------------------------
    # 1. SIGN Scheme Scenario
    # ------------------------------------------------------------------------
    # Seed store with alternative explanation fact (causes Q_SIGN_DISPUTE violation)
    t_sign_dispute = user_signer.sign(
        UnsignedPayload(
            content="alternative explanation for zero_cpu_load is sensor_offline",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce=os.urandom(16).hex(),
            created_at=time.time() - 100,
            trace_id="tr-live-sign-dispute",
        )
    )
    live_orch.memory_store.commit(t_sign_dispute)

    # Seed tool receipt from system telemetry source
    live_orch.current_turn_receipts = [
        ToolReceipt(
            tool="system_monitor",
            call_id="call-sysmon-01",
            source="sysmon.local",
            output="sysmon.local asserts zero_cpu_load indicates idle_npu",
        )
    ]

    # Propose inference step
    step_sign_json = json.dumps(
        [
            {
                "premises": ["sysmon.local asserts zero_cpu_load indicates idle_npu"],
                "s": "zero_cpu_load",
                "p": "indicates",
                "o": "idle_npu",
                "confidence": 0.85,
            }
        ]
    )
    fake_llm_sign = FakeLLM(
        script=[
            TokenDelta(delta=step_sign_json),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=25)),
        ]
    )
    trace_sign = TurnTrace(trace_id="tr-live-sign", origin="text")

    accepted_sign, spoken_sign = live_orch.run_deduction_step(
        goal="Assess whether zero CPU load indicates idle NPU",
        trace=trace_sign,
        llm=fake_llm_sign,
    )

    # Invariants for SIGN:
    assert len(accepted_sign) == 1, "Expected SIGN inference step to be accepted defeasibly"
    sign_step = accepted_sign[0]
    # Docked from 0.85 by -0.25 (alternative explanation found) -> 0.60
    assert sign_step.confidence == 0.60
    assert any("alternative explanation" in c for c in sign_step.conditions)
    assert spoken_sign is not None
    assert "I think zero_cpu_load indicates idle_npu" in spoken_sign
    assert "not sure enough to keep it" in spoken_sign

    print(f'\n[VERBATIM SPOKEN SIGN NARRATION]:\n"{spoken_sign}"\n')

    # ------------------------------------------------------------------------
    # 2. ANALOGY Scheme Scenario
    # ------------------------------------------------------------------------
    # Seed store with critical difference fact (causes Q_ANALOGY_DIFFERENCES violation)
    t_analogy_diff = user_signer.sign(
        UnsignedPayload(
            content="linux_pipeline differs from bsd_pipeline in threading_model",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce=os.urandom(16).hex(),
            created_at=time.time() - 90,
            trace_id="tr-live-analogy-diff",
        )
    )
    live_orch.memory_store.commit(t_analogy_diff)

    live_orch.current_turn_receipts = [
        ToolReceipt(
            tool="audio_lab",
            call_id="call-audiolab-01",
            source="audio-bench.org",
            output="audio-bench.org asserts linux_pipeline similar_to bsd_pipeline",
        )
    ]

    step_analogy_json = json.dumps(
        [
            {
                "premises": ["audio-bench.org asserts linux_pipeline similar_to bsd_pipeline"],
                "s": "linux_pipeline",
                "p": "analogous_to",
                "o": "bsd_pipeline",
                "confidence": 0.85,
            }
        ]
    )
    fake_llm_analogy = FakeLLM(
        script=[
            TokenDelta(delta=step_analogy_json),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=25)),
        ]
    )
    trace_analogy = TurnTrace(trace_id="tr-live-analogy", origin="text")

    accepted_analogy, spoken_analogy = live_orch.run_deduction_step(
        goal="Determine if Linux audio pipeline is analogous to BSD pipeline",
        trace=trace_analogy,
        llm=fake_llm_analogy,
    )

    # Invariants for ANALOGY:
    assert len(accepted_analogy) == 1, "Expected ANALOGY step to be accepted defeasibly"
    analogy_step = accepted_analogy[0]
    # Docked from 0.85 by -0.30 (defeating difference found) -> 0.55
    assert analogy_step.confidence == 0.55
    assert any("differs" in c or "threading_model" in c for c in analogy_step.conditions)
    assert spoken_analogy is not None
    assert "I think linux_pipeline analogous_to bsd_pipeline" in spoken_analogy
    assert "not sure enough to keep it" in spoken_analogy

    print(f'\n[VERBATIM SPOKEN ANALOGY NARRATION]:\n"{spoken_analogy}"\n')

    # ------------------------------------------------------------------------
    # 3. CONSEQUENCE Scheme Scenario
    # ------------------------------------------------------------------------
    # Seed store with countervailing side effect (causes Q_CONSEQ_COUNTERVAILING violation)
    t_csq_side_effect = user_signer.sign(
        UnsignedPayload(
            content="disabling_wal causes catastrophic_corruption side effect",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce=os.urandom(16).hex(),
            created_at=time.time() - 80,
            trace_id="tr-live-csq-side-effect",
        )
    )
    live_orch.memory_store.commit(t_csq_side_effect)

    live_orch.current_turn_receipts = [
        ToolReceipt(
            tool="tuning_guide",
            call_id="call-sqlite-01",
            source="sqlite-tuning.com",
            output="sqlite-tuning.com asserts disabling_wal causes write_throughput_boost",
        )
    ]

    step_csq_json = json.dumps(
        [
            {
                "premises": [
                    "sqlite-tuning.com asserts disabling_wal causes write_throughput_boost"
                ],
                "s": "disabling_wal",
                "p": "causes",
                "o": "write_throughput_boost",
                "confidence": 0.85,
            }
        ]
    )
    fake_llm_csq = FakeLLM(
        script=[
            TokenDelta(delta=step_csq_json),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=25)),
        ]
    )
    trace_csq = TurnTrace(trace_id="tr-live-csq", origin="text")

    accepted_csq, spoken_csq = live_orch.run_deduction_step(
        goal="Assess whether disabling WAL causes write throughput boost",
        trace=trace_csq,
        llm=fake_llm_csq,
    )

    # Invariants for CONSEQUENCE:
    assert len(accepted_csq) == 1, "Expected CONSEQUENCE step to be accepted defeasibly"
    csq_step = accepted_csq[0]
    # Docked from 0.85 by -0.30 (countervailing side effect) -> 0.55
    assert csq_step.confidence == 0.55
    assert any(
        "catastrophic_corruption" in c or "side effect" in c for c in csq_step.conditions
    )
    assert spoken_csq is not None
    assert "I think disabling_wal causes write_throughput_boost" in spoken_csq
    assert "not sure enough to keep it" in spoken_csq

    print(f'\n[VERBATIM SPOKEN CONSEQUENCE NARRATION]:\n"{spoken_csq}"\n')

    # ------------------------------------------------------------------------
    # 4. PRECEDENT Scheme Scenario
    # ------------------------------------------------------------------------
    # Seed store with overturned/superseded status (causes Q_PREC_RATIFIED violation)
    t_precedent_superseded = user_signer.sign(
        UnsignedPayload(
            content="precedent_case_101 was overruled and superseded by board_ruling_2026",
            provenance=Provenance.USER_EXPLICIT,
            kind="transcript",
            confidence=1.0,
            nonce=os.urandom(16).hex(),
            created_at=time.time() - 70,
            trace_id="tr-live-precedent-superseded",
        )
    )
    live_orch.memory_store.commit(t_precedent_superseded)

    live_orch.current_turn_receipts = [
        ToolReceipt(
            tool="policy_kb",
            call_id="call-policy-01",
            source="compliance.internal",
            output="compliance.internal asserts audit_case_402 governed_by precedent_case_101 with congruent facts",
        )
    ]

    step_prc_json = json.dumps(
        [
            {
                "premises": [
                    "compliance.internal asserts audit_case_402 governed_by precedent_case_101 with congruent facts"
                ],
                "s": "audit_case_402",
                "p": "governed_by",
                "o": "precedent_case_101",
                "confidence": 0.85,
            }
        ]
    )
    fake_llm_prc = FakeLLM(
        script=[
            TokenDelta(delta=step_prc_json),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=25)),
        ]
    )
    trace_prc = TurnTrace(trace_id="tr-live-prc", origin="text")

    accepted_prc, spoken_prc = live_orch.run_deduction_step(
        goal="Determine if audit case 402 is governed by precedent 101",
        trace=trace_prc,
        llm=fake_llm_prc,
    )

    # Invariants for PRECEDENT:
    assert len(accepted_prc) == 1, "Expected PRECEDENT step to be accepted defeasibly"
    prc_step = accepted_prc[0]
    # Docked from 0.85 by -0.25 (precedent overturned or superseded) -> 0.60
    assert prc_step.confidence == 0.60
    assert any("overturned" in c or "superseded" in c for c in prc_step.conditions)
    assert spoken_prc is not None
    assert "I think audit_case_402 governed_by precedent_case_101" in spoken_prc
    assert "not sure enough to keep it" in spoken_prc

    print(f'\n[VERBATIM SPOKEN PRECEDENT NARRATION]:\n"{spoken_prc}"\n')

    # All 4 spoken narrations were routed through _speak_text
    assert len(spoken_history) == 4


# ============================================================================
# 2. ITEM-018 Live Acceptance: Transcript Normalization & Rule Parity
# ============================================================================


def test_wo23_live_acceptance_item018_transcript_parity_and_rule_match(
    live_orch: Orchestrator,
) -> None:
    """ITEM-018 Live Acceptance:
    An utterance with trailing punctuation + mixed casing routes identically
    through HeuristicRouter and matches the same rule as its normalized form.
    """
    # 1. Register a test rule in rule lifecycle manager
    rule_source = """
    (rule "calc-live-parity-v1"
      :when (intent= "launch_app")
      :plan (list (tool "run_python" :code "2 + 2"))
      :priority 10)
    """
    rule = live_orch.rule_engine.register_rule(rule_source)
    rule.status = "ACTIVE"

    # 2. Raw vs Normalized utterances
    raw_utterance = "  Launch Calculator, Please!?!  "
    norm_utterance = normalize_transcript(raw_utterance)
    assert norm_utterance == "Launch Calculator, Please"

    # 3. Router classification parity
    has_registered = any(r.status == "ACTIVE" for r in live_orch.rule_engine.rules.values())
    decision_raw = live_orch.router.route(raw_utterance, has_registered_rule=has_registered)
    decision_norm = live_orch.router.route(norm_utterance, has_registered_rule=has_registered)

    assert decision_raw.action == decision_norm.action == RouteAction.RULE
    assert decision_raw.tier == decision_norm.tier == ExecutionTier.ACT_THEN_NARRATE
    assert live_orch.router.last_decision_record is not None
    assert live_orch.router.last_decision_record.features.transcript == norm_utterance
    assert live_orch.router.last_decision_record.features.intent == "launch_app"

    # 4. Orchestrator RuleState parity
    state_raw = live_orch._build_rule_state(raw_utterance)
    state_norm = live_orch._build_rule_state(norm_utterance)

    assert state_raw.transcript == state_norm.transcript == norm_utterance
    assert state_raw.intent == state_norm.intent == "launch_app"
    assert state_raw.entities == state_norm.entities

    # 5. Rule execution parity
    outcomes_raw = live_orch.rule_engine.evaluate(state_raw, mode="active")
    outcomes_norm = live_orch.rule_engine.evaluate(state_norm, mode="active")

    assert len(outcomes_raw) == len(outcomes_norm) == 1
    assert outcomes_raw[0].fired is True
    assert outcomes_norm[0].fired is True
    assert outcomes_raw[0].rule_id == outcomes_norm[0].rule_id == "calc-live-parity-v1"


# ============================================================================
# 3. ITEM-023 Live Acceptance: Decision Log Calendar-Day Rotation & Pruning
# ============================================================================


def test_wo23_live_acceptance_decision_log_rotation_and_retention(tmp_path: Path) -> None:
    """ITEM-023 Live Acceptance:
    Simulates a calendar-day boundary on decision logging:
    - On date rollover, existing decisions.jsonl is rotated to decisions-YYYY-MM-DD.jsonl;
    - Retention pruning retains the N most recent rotated files and deletes older ones;
    - Next write lands cleanly in a fresh decisions.jsonl;
    - Zero decisions lost across rotation boundary.
    """
    log_file = tmp_path / "logs" / "decisions.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Set retention to 3 rotated files for explicit boundary verification
    router = HeuristicRouter(log_path=log_file, retention_files=3)

    # Day 1: 2026-09-24 UTC (2 records)
    day1_dt = datetime(2026, 9, 24, 10, 0, 0, tzinfo=UTC)
    router._log_decision_jsonl(
        _make_decision_record("dec-01", day1_dt.timestamp(), "open calculator")
    )
    router._log_decision_jsonl(
        _make_decision_record("dec-02", (day1_dt + timedelta(minutes=1)).timestamp(), "open terminal")
    )
    os.utime(log_file, (day1_dt.timestamp(), day1_dt.timestamp()))

    # Day 2: 2026-09-25 UTC (1 record) -> rotates Day 1
    day2_dt = datetime(2026, 9, 25, 11, 0, 0, tzinfo=UTC)
    router._log_decision_jsonl(
        _make_decision_record("dec-03", day2_dt.timestamp(), "open editor")
    )
    os.utime(log_file, (day2_dt.timestamp(), day2_dt.timestamp()))

    # Day 3: 2026-09-26 UTC (1 record) -> rotates Day 2
    day3_dt = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    router._log_decision_jsonl(
        _make_decision_record("dec-04", day3_dt.timestamp(), "open browser")
    )
    os.utime(log_file, (day3_dt.timestamp(), day3_dt.timestamp()))

    # Day 4: 2026-09-27 UTC (1 record) -> rotates Day 3 (now 3 rotated files: Day 1, Day 2, Day 3)
    day4_dt = datetime(2026, 9, 27, 13, 0, 0, tzinfo=UTC)
    router._log_decision_jsonl(
        _make_decision_record("dec-05", day4_dt.timestamp(), "check status")
    )
    os.utime(log_file, (day4_dt.timestamp(), day4_dt.timestamp()))

    # Day 5: 2026-09-28 UTC (1 record) -> rotates Day 4; prunes Day 1 (retains Day 4, Day 3, Day 2)
    day5_dt = datetime(2026, 9, 28, 14, 0, 0, tzinfo=UTC)
    router._log_decision_jsonl(
        _make_decision_record("dec-06", day5_dt.timestamp(), "play music")
    )

    # 1. Pruning verification: Day 1 is pruned, Days 2, 3, 4 retained
    rotated_day1 = tmp_path / "logs" / "decisions-2026-09-24.jsonl"
    rotated_day2 = tmp_path / "logs" / "decisions-2026-09-25.jsonl"
    rotated_day3 = tmp_path / "logs" / "decisions-2026-09-26.jsonl"
    rotated_day4 = tmp_path / "logs" / "decisions-2026-09-27.jsonl"

    assert not rotated_day1.exists(), f"Oldest file was not pruned: {rotated_day1}"
    assert rotated_day2.exists(), f"Expected retained file: {rotated_day2}"
    assert rotated_day3.exists(), f"Expected retained file: {rotated_day3}"
    assert rotated_day4.exists(), f"Expected retained file: {rotated_day4}"

    # 2. Active file contains Day 5 record
    active_lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(active_lines) == 1
    assert "dec-06" in active_lines[0]

    # 3. Retained files contain their respective records
    day2_lines = rotated_day2.read_text(encoding="utf-8").strip().splitlines()
    assert len(day2_lines) == 1
    assert "dec-03" in day2_lines[0]

    day3_lines = rotated_day3.read_text(encoding="utf-8").strip().splitlines()
    assert len(day3_lines) == 1
    assert "dec-04" in day3_lines[0]

    day4_lines = rotated_day4.read_text(encoding="utf-8").strip().splitlines()
    assert len(day4_lines) == 1
    assert "dec-05" in day4_lines[0]


# ============================================================================
# 4. Fixture Isolation & Leakage Control
# ============================================================================


def test_wo23_live_acceptance_fixture_isolation(live_orch: Orchestrator) -> None:
    """Verifies that live acceptance fixtures do not leak state across tests:
    - Empty initial memory tables;
    - Clean rule engine state;
    - Hermetic sandbox workspace.
    """
    with live_orch.db.read_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM memories")
        mem_count = cur.fetchone()[0]
        assert mem_count == 0

    assert len(live_orch.rule_engine.rules) == 0
    assert live_orch.current_turn_receipts == []
