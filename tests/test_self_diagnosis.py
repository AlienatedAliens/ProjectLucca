"""
Unit and integration tests for Lucca Self-Diagnosis Engine (WO-22 Phase 2).
Spec 11 §7, Fault Model v1, ITEM-021.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import ulid

from lucca.core import env_check
from lucca.core.orchestrator import Orchestrator
from lucca.core.reasoning_context import ReasoningContext
from lucca.core.schemas import (
    DecisionRecord,
    ExecutionTier,
    RouteAction,
    RouteDecision,
    RouteFeatures,
    ToolCall,
)
from lucca.core.self_diagnosis import (
    DEFAULT_FAULT_MODEL_PATH,
    Diagnosis,
    DiagnosisEngine,
    is_self_diagnosis_query,
)
from lucca.core.trace import TurnTrace
from lucca.memory.db import DatabaseManager
from lucca.memory.retrieval import (
    HybridRetriever,
    index_decision_record,
    search_decision_records,
)


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseManager:
    """Provides an isolated migrated SQLite database for testing."""
    db = DatabaseManager(tmp_path / "test_diagnosis.sqlite")
    db.migrate()
    yield db
    db.close()


def _make_dummy_decision_record(
    transcript: str,
    tool_name: str = "run_python",
    tool_ok: bool = False,
    action: RouteAction = RouteAction.RULE,
) -> DecisionRecord:
    """Helper to create a populated DecisionRecord for testing."""
    features = RouteFeatures(
        transcript=transcript,
        transcript_lower=transcript.lower(),
        intent="compute",
        intent_conf=0.90,
        tier=ExecutionTier.ACT_THEN_NARRATE,
        last_tool=tool_name,
        last_tool_ok=tool_ok,
    )
    decision = RouteDecision(
        action=action,
        tier=ExecutionTier.ACT_THEN_NARRATE,
        prediction_set=[action],
        probabilities={"RULE": 1.0, "LLM": 0.0, "CLARIFY": 0.0},
        fallback_applied=False,
        elapsed_us=1200,
    )
    return DecisionRecord(
        decision_id=f"dec-{ulid.ULID()}",
        trace_id=f"trace-{ulid.ULID()}",
        session_id=f"sess-{ulid.ULID()}",
        ts=1700000000.0,
        features=features,
        decision=decision,
        router_version="heuristic-1.0",
        executed_path=action.value,
        tool_calls=[
            ToolCall(call_id=f"call-{ulid.ULID()}", tool=tool_name, args={"code": "print(1)"})
        ],
        tool_ok=tool_ok,
    )


# ---------------------------------------------------------------------------
# Test 1: Each fault model entry matches its seeded symptoms
# ---------------------------------------------------------------------------


def test_fault_model_entries_match_seeded_symptoms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each of the 5 curated fault patterns matches its distinct seeded symptoms."""
    # Ensure checks don't fail during pure symptom-matching test
    monkeypatch.setattr(env_check, "check_system_ram", lambda: (True, "RAM ok"))
    monkeypatch.setattr(env_check, "check_docker_wsl", lambda: (True, "Docker ok"))
    monkeypatch.setattr(env_check, "check_audio_ring", lambda: (True, "Audio ring ok"))
    monkeypatch.setattr(env_check, "check_mshybrid_vram", lambda: (True, "VRAM ok"))
    monkeypatch.setattr(env_check, "check_models_manifest", lambda: (True, "Manifest ok"))
    monkeypatch.setattr(env_check, "check_wsl_status", lambda: (True, "WSL ok"))

    engine = DiagnosisEngine()
    assert len(engine.fault_model) == 5

    cases = [
        ("boot MemoryError: OpenVINO compile failed", "boot_memory_error"),
        ({"error": "run_python returns policy_violation"}, "docker_wsl_down"),
        ("ASR latency spike with normal NPU load", "audio_ring_contention"),
        ("llama-server unhealthy VRAM over-budget", "llama_server_unhealthy"),
        ("frozen-binary --check timeout wsl unresponsive", "frozen_binary_timeout"),
    ]

    for symptoms, expected_fault_id in cases:
        diagnoses = engine.diagnose(symptoms)
        assert len(diagnoses) > 0, f"Expected diagnosis for symptom '{symptoms}'"
        top = diagnoses[0]
        assert top.fault_id == expected_fault_id, (
            f"Expected fault {expected_fault_id}, got {top.fault_id} for '{symptoms}'"
        )


# ---------------------------------------------------------------------------
# Test 2: STOP Gate Negative Control: Phantom check name fails loudly
# ---------------------------------------------------------------------------


def test_phantom_check_name_fails_loudly(tmp_path: Path) -> None:
    """DiagnosisEngine must raise ValueError if a fault entry names a check
    absent from env_check (STOP Gate Ratification requirement)."""
    bad_toml = tmp_path / "bad_fault_model.toml"
    bad_toml.write_text(
        """
[[fault]]
id = "fake_fault"
name = "Fake Fault"
symptoms = ["fake symptom"]
cause = "fake cause"
checks = ["check_manifest_hashes"]  # Phantom check!
severity = "high"
suggested_remedy = "none"
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="check_manifest_hashes.*does not exist in lucca.core.env_check"
    ):
        DiagnosisEngine(fault_model_path=bad_toml)


def test_production_fault_model_all_checks_resolve() -> None:
    """Asserts every check entry in config/fault_model.toml resolves to a real
    env_check function (ratified STOP gate invariant)."""
    engine = DiagnosisEngine(fault_model_path=DEFAULT_FAULT_MODEL_PATH)
    assert len(engine.fault_model) == 5
    for fault in engine.fault_model:
        assert len(fault.checks) > 0
        for check_name in fault.checks:
            fn = getattr(env_check, check_name, None)
            assert fn is not None, f"Check '{check_name}' in fault '{fault.id}' is missing"
            assert callable(fn), f"Check '{check_name}' is not callable"


# ---------------------------------------------------------------------------
# Test 3: Unknown symptom combination yields honest abstention
# ---------------------------------------------------------------------------


def test_unknown_symptom_combination_yields_honest_abstention() -> None:
    """Unknown symptoms with healthy checks must return empty list (honest abstention)."""
    engine = DiagnosisEngine()
    diagnoses = engine.diagnose(["quantum decoherence in gpu cache", "alien radio interference"])
    assert diagnoses == []

    # Formatted speech must honestly abstain (named gap)
    speech = engine.format_diagnosis_speech(None)
    assert "no known fault pattern matches" in speech.lower()


# ---------------------------------------------------------------------------
# Test 4: Checks actually invoked and results populate evidence
# ---------------------------------------------------------------------------


def test_checks_invoked_and_populate_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """When a symptom matches, listed checks are executed and evidence records the findings."""
    check_invoked = False

    def _mock_docker_check() -> tuple[bool, str]:
        nonlocal check_invoked
        check_invoked = True
        return False, "Docker CE is not running inside Ubuntu WSL2"

    monkeypatch.setattr(env_check, "check_docker_wsl", _mock_docker_check)

    engine = DiagnosisEngine()
    diagnoses = engine.diagnose({"error": "policy_violation"})

    assert check_invoked is True
    assert len(diagnoses) > 0
    top = diagnoses[0]
    assert top.fault_id == "docker_wsl_down"
    assert top.confidence >= 0.85

    # Check evidence contains the check result
    check_evidence = [e for e in top.evidence if "confirmed failure" in e]
    assert len(check_evidence) > 0
    assert "Docker CE is not running" in check_evidence[0]


# ---------------------------------------------------------------------------
# Test 5: Hedged speech assertions (Trap 1 / Standards of Proof)
# ---------------------------------------------------------------------------


def test_hedged_speech_assertions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Diagnoses must be spoken with hedged language ('my best guess is ...', 'I'd check ...'),
    never unhedged absolute assertions (Trap 1: standards of proof)."""
    monkeypatch.setattr(
        env_check,
        "check_audio_ring",
        lambda: (False, "Audio ring buffer contention: 5 underruns"),
    )

    engine = DiagnosisEngine()
    diagnoses = engine.diagnose("ASR latency spike")
    assert len(diagnoses) > 0
    top = diagnoses[0]

    speech = engine.format_diagnosis_speech(top)

    # Hedged markers
    assert "my best guess is" in speech.lower()
    assert "i'd check" in speech.lower() or "i'd" in speech.lower()

    # Must NOT contain unhedged dogmatic declarations
    assert "it is a proven fact" not in speech.lower()
    assert "definitely without doubt" not in speech.lower()


# ---------------------------------------------------------------------------
# Test 6: ITEM-021: Seeded decision record is retrievable & citable in evidence
# ---------------------------------------------------------------------------


def test_item021_seeded_decision_record_retrieved_and_cited(test_db: DatabaseManager) -> None:
    """ITEM-021: A seeded DecisionRecord matching the symptom is retrievable in-session
    and citable as diagnosis evidence; absence of matching records causes diagnosis
    to proceed on checks alone without fabrication."""
    # Seed a decision record into SQLite
    seeded_record = _make_dummy_decision_record(
        transcript="run_python script for data processing failed with policy_violation",
        tool_name="run_python",
        tool_ok=False,
    )
    index_decision_record(test_db, seeded_record)

    # Verify retrieval works directly and via HybridRetriever
    direct_records = search_decision_records(test_db, "policy_violation", limit=5)
    assert len(direct_records) > 0
    assert direct_records[0].decision_id == seeded_record.decision_id

    retriever = HybridRetriever(db=test_db)
    retriever.index_decision(seeded_record)
    retrieved = retriever.search_decisions("policy_violation", limit=5)
    assert len(retrieved) > 0
    assert retrieved[0].decision_id == seeded_record.decision_id

    # Run DiagnosisEngine with DB attached
    engine = DiagnosisEngine(db=test_db)
    diagnoses = engine.diagnose("run_python returns policy_violation")
    assert len(diagnoses) > 0
    top = diagnoses[0]
    assert isinstance(top, Diagnosis)

    # Verify that the past decision is cited in evidence
    history_citations = [e for e in top.evidence if "Past incident" in e]
    assert len(history_citations) > 0
    assert seeded_record.decision_id in history_citations[0]


def test_item021_absence_of_matching_records_proceeds_without_fabrication(
    test_db: DatabaseManager,
) -> None:
    """ITEM-021 Negative Control: In the absence of matching decision records,
    the diagnosis proceeds on env_checks alone without fabricating past incidents."""
    engine = DiagnosisEngine(db=test_db)
    diagnoses = engine.diagnose("boot MemoryError alloc failure")
    assert len(diagnoses) > 0
    top = diagnoses[0]

    # Verify no fabricated past incident in evidence
    history_citations = [e for e in top.evidence if "Past incident" in e]
    assert len(history_citations) == 0


# ---------------------------------------------------------------------------
# Test 7: Orchestrator Integration & Query Detection
# ---------------------------------------------------------------------------


def test_is_self_diagnosis_query_detection() -> None:
    """User queries asking why tools failed or why system is slow are identified
    as diagnostic queries."""
    assert is_self_diagnosis_query("What's wrong with your tools?") is True
    assert is_self_diagnosis_query("why are you slow?") is True
    assert is_self_diagnosis_query("what is wrong with you?") is True
    assert is_self_diagnosis_query("diagnose yourself") is True
    assert is_self_diagnosis_query("why did that fail?") is True
    assert is_self_diagnosis_query("what's wrong?") is True

    # Non-diagnostic inquiries
    assert is_self_diagnosis_query("open calculator") is False
    assert is_self_diagnosis_query("what is the capital of France?") is False
    assert is_self_diagnosis_query("how are you doing today?") is False


def test_orchestrator_run_self_diagnosis_records_hedged_intermediate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestrator.run_self_diagnosis speaks the hedged diagnosis and records
    it as a hedged intermediate in ReasoningContext (not a committed fact)."""
    monkeypatch.setattr(
        env_check, "check_docker_wsl", lambda: (False, "Docker not responding in Ubuntu WSL2")
    )

    orch = Orchestrator.__new__(Orchestrator)
    orch.db = None
    orch.config = MagicMock()
    orch.current_reasoning_context = ReasoningContext()
    spoken_messages: list[str] = []
    orch._speak_text = lambda trace, text: spoken_messages.append(text)
    orch._publish_caption = lambda *a, **kw: None

    trace = TurnTrace(trace_id="test-trace-diag")
    diagnoses = orch.run_self_diagnosis("what's wrong with your tools?", trace)

    assert len(diagnoses) > 0
    assert len(spoken_messages) == 1
    assert "my best guess is" in spoken_messages[0].lower()

    # Assert recorded as hedged intermediate in reasoning context
    intermediates = orch.current_reasoning_context.intermediates
    assert len(intermediates) == 1
    entry = intermediates[0]
    assert entry.s == "lucca"
    assert entry.p == "diagnosed_fault"
    assert entry.o == "docker_wsl_down"
    assert entry.step_kind == "diagnosis"
    assert entry.confidence < 1.0
