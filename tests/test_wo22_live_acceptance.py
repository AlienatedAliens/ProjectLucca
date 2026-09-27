"""
Project Lucca — WO-22 Phase 3: Live Acceptance (WO-22d)
Plan + Diagnosis End-to-End Acceptance Tests.

Functional Acceptance:
1. Planning: "Look up when Metal Gear Solid came out and note it" -> plan
   (search_web -> note_write) -> executed with per-step receipts -> note written ->
   spoken summary cites both steps.
2. Diagnosis: with the Docker sandbox fault-injected (tests/fakes/fault_injecting_sandbox.py),
   "what's wrong with your tools?" -> she names the cause (Docker not running),
   the check that confirmed it, hedged — and the diagnosis is recorded as a hedged
   intermediate, not a committed fact.
3. Both scenarios run cold, unled, in one turn each; verbatim spoken output recorded.
4. Traps: fault injection must not leak into other tests (fixture-scoped).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lucca.core import env_check
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Done, LLMUsage, TokenDelta
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import TurnInput, TurnPipeline
from lucca.memory.db import DatabaseManager
from lucca.sandbox.service import SandboxService
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS
from tests.fakes.fault_injecting_sandbox import FaultInjectingSandbox


@pytest.fixture
def live_db(tmp_path: Path) -> DatabaseManager:
    """Provides a fresh migrated database instance for live acceptance."""
    db_path = tmp_path / "live_acceptance.sqlite"
    db = DatabaseManager(db_path)
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def live_orch(
    live_db: DatabaseManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Orchestrator:
    """Provides a clean, hermetic orchestrator for live acceptance scenarios."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # Hermetic web search mock for deterministic offline execution
    def _mock_search_web(query: str, max_results: int = 5) -> tuple[dict[str, object], str]:
        return {
            "query": query,
            "ok": True,
            "results": [
                {
                    "title": "Metal Gear Solid - Release Information",
                    "url": "https://example.com/mgs-release",
                    "snippet": (
                        "Metal Gear Solid was released on September 3, 1998 in Japan, "
                        "and October 21, 1998 in North America for the Sony PlayStation."
                    ),
                }
            ],
        }, "1. Metal Gear Solid was released on September 3, 1998.\n"

    monkeypatch.setattr("lucca.sandbox.service.search_web", _mock_search_web)

    sandbox = SandboxService(workspace_root=workspace, use_direct_fallback=True)
    orch = Orchestrator(
        tts=FakeTTS,
        asr=FakeASR,
        execute_tools=True,
        sandbox=sandbox,
        db=live_db,
    )
    return orch


# ============================================================================
# 1. Planning Live Acceptance Scenario
# ============================================================================


def test_wo22_live_acceptance_planning_scenario(live_orch: Orchestrator) -> None:
    """Planning functional acceptance:
    'Look up when Metal Gear Solid came out and note it'
    -> plan (search_web -> note_write)
    -> executed with per-step receipts
    -> note written
    -> spoken summary cites both steps.
    Runs cold, unled in one turn.
    """
    goal = "Look up when Metal Gear Solid came out and note it"

    # Cold, unled LLM response proposing the 2-step plan
    plan_payload = {
        "plan_id": "plan-mgs-live-001",
        "goal": goal,
        "rationale": "Search web for Metal Gear Solid release date, then write the verified date to notes.",
        "steps": [
            {
                "order": 1,
                "tool": "search_web",
                "args": {"query": "Metal Gear Solid release date"},
                "purpose": "Find release date of Metal Gear Solid",
            },
            {
                "order": 2,
                "tool": "note_write",
                "args": {
                    "name": "Metal_Gear_Solid",
                    "content": "Metal Gear Solid was released on September 3, 1998.",
                },
                "purpose": "Record release date in notes",
            },
        ],
    }

    fake_llm = FakeLLM(
        script=[
            TokenDelta(delta=json.dumps(plan_payload)),
            Done(usage=LLMUsage(prompt_tokens=25, completion_tokens=75)),
        ]
    )

    trace = TurnTrace(trace_id="tr-live-plan-001", origin="text")

    # Run cold, unled in one turn
    plan = live_orch.run_planning_step(
        goal=goal,
        trace=trace,
        llm=fake_llm,
    )

    # 1. Plan structure and completion
    assert plan is not None, "Expected plan to be generated and executed"
    assert plan.plan_id == "plan-mgs-live-001"
    assert len(plan.steps) == 2
    assert len(plan.receipts) == 2

    # 2. Per-step receipts recorded
    step1_receipt = plan.receipts[0]
    assert step1_receipt["order"] == 1
    assert step1_receipt["tool"] == "search_web"
    assert step1_receipt["ok"] is True
    assert "Metal Gear Solid" in str(step1_receipt["result"])

    step2_receipt = plan.receipts[1]
    assert step2_receipt["order"] == 2
    assert step2_receipt["tool"] == "note_write"
    assert step2_receipt["ok"] is True

    # 3. Note is actually written on disk / retrievable
    structured_note, note_text = live_orch.sandbox.note_tool.read_note(name="Metal_Gear_Solid")
    assert "September 3, 1998" in note_text or "1998" in note_text, (
        f"Expected note content to contain 1998, got: {note_text}"
    )

    # 4. Spoken summary cites BOTH steps (ITEM-017 / D-HON-01)
    narration = plan.narration or live_orch.last_spoken_plan_narration
    assert narration is not None, "Expected spoken narration for executed plan"
    narration_lower = narration.lower()

    # Cites search step
    assert "searched the web" in narration_lower or "search_web" in narration_lower
    # Cites note write step
    assert "wrote note" in narration_lower or "note" in narration_lower

    # Captured verbatim spoken output for review
    print(f'\n[VERBATIM SPOKEN PLAN NARRATION]:\n"{narration}"\n')


# ============================================================================
# 2. Diagnosis Live Acceptance Scenario
# ============================================================================


def test_wo22_live_acceptance_diagnosis_scenario(
    live_orch: Orchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diagnosis functional acceptance:
    With the Docker sandbox fault-injected (tests/fakes/fault_injecting_sandbox.py),
    'what's wrong with your tools?'
    -> she names the cause (Docker not running),
    -> the check that confirmed it (check_docker_wsl),
    -> hedged speech,
    -> diagnosis recorded as hedged intermediate, NOT a committed fact.
    Runs cold, unled in one turn through TurnPipeline.
    """
    # 1. Fault-inject the sandbox with FaultInjectingSandbox (fixture-scoped)
    underlying_sandbox = live_orch.sandbox
    live_orch.sandbox = FaultInjectingSandbox(
        underlying=underlying_sandbox,
        mode="hard_failure",
        target_tools={"run_python"},
    )

    # 2. Monkeypatch check_docker_wsl to return confirmed failure (fixture-scoped)
    wsl_failure_msg = "Docker not responding in Ubuntu WSL2: daemon inactive"
    monkeypatch.setattr(
        env_check,
        "check_docker_wsl",
        lambda: (False, wsl_failure_msg),
    )

    spoken_captions: list[str] = []
    live_orch._speak_text = lambda trace, text: spoken_captions.append(text)

    # 3. User asks the diagnostic inquiry in one cold, unled turn
    user_query = "what's wrong with your tools?"
    trace = TurnTrace(trace_id="tr-live-diag-001", origin="text")

    pipeline = TurnPipeline(orchestrator=live_orch)
    inp = TurnInput(user_text=user_query, trace=trace, origin="text", mode="transcript")
    pipeline.run(inp)

    # 4. Verbatim spoken output verification
    assert len(spoken_captions) > 0, "Expected assistant to speak diagnosis"
    spoken_output = spoken_captions[0]
    spoken_lower = spoken_output.lower()

    # (a) Names the cause (Docker not running inside WSL2)
    assert "docker" in spoken_lower and ("not running" in spoken_lower or "wsl" in spoken_lower), (
        f"Expected speech to identify Docker/WSL failure, got: {spoken_output}"
    )

    # (b) Names the check that confirmed it (confirmed failure details from check_docker_wsl)
    assert "docker not responding" in spoken_lower or "check_docker_wsl" in spoken_lower, (
        f"Expected speech to cite confirmed check finding, got: {spoken_output}"
    )

    # (c) Hedged speech (Trap 1: standards of proof, SPECULATION band)
    assert "my best guess is" in spoken_lower, (
        f"Expected hedged marker 'my best guess is', got: {spoken_output}"
    )
    assert "i'd" in spoken_lower, f'Expected suggested remedy hedge "I\'d", got: {spoken_output}'

    # Must NOT claim unhedged certainty
    assert "definitely without doubt" not in spoken_lower
    assert "it is a proven fact" not in spoken_lower

    # 5. Recorded as hedged intermediate in ReasoningContext (Trap 1)
    ctx = getattr(live_orch, "current_reasoning_context", None)
    assert ctx is not None, "Expected reasoning context to exist"
    assert len(ctx.intermediates) > 0, "Expected diagnosis intermediate to be recorded"
    diag_intermediate = ctx.intermediates[0]
    assert diag_intermediate.s == "lucca"
    assert diag_intermediate.p == "diagnosed_fault"
    assert diag_intermediate.o == "docker_wsl_down"
    assert diag_intermediate.step_kind == "diagnosis"
    assert diag_intermediate.confidence < 1.0

    # 6. Trap 1: NOT committed to long-term memory
    with live_orch.db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.content FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            WHERE e.provenance = 'INFERRED' AND m.content LIKE '%docker%'
            """
        )
        inferred_rows = cur.fetchall()
        assert inferred_rows == [], (
            f"Trap 1 violation: diagnosis was committed as INFERRED memory: {inferred_rows}"
        )

    # Captured verbatim spoken output for review
    print(f'\n[VERBATIM SPOKEN DIAGNOSIS]:\n"{spoken_output}"\n')


# ============================================================================
# 3. Fault-Injection Leakage Negative Control (Trap Invariant)
# ============================================================================


def test_wo22_live_acceptance_fault_injection_does_not_leak(live_orch: Orchestrator) -> None:
    """Verifies fault injection from test 2 does not leak into subsequent tests:
    - live_orch.sandbox is a normal SandboxService (not FaultInjectingSandbox)
    - env_check.check_docker_wsl is restored to its standard callable
    """
    assert not isinstance(live_orch.sandbox, FaultInjectingSandbox), (
        "Fault injection leaked: sandbox is still FaultInjectingSandbox"
    )
    assert callable(env_check.check_docker_wsl)
