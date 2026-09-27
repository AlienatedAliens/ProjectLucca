"""
Project Lucca — Means-Ends Planner Unit & Integration Tests (WO-22 Phase 1)
Ratified 2026-09-27 by owner.

Tests:
1. Valid 3-step plan executes in order with per-step receipts recorded.
2. Invalid tool name -> revision requested -> second failure -> honest refusal.
3. Step args failing schema -> revision requested -> fixed on revision -> plan executes.
4. >8 steps -> Pydantic ValidationError.
5. Non-contiguous step orders ([2, 2, 1], [1, 3]) -> Pydantic ValidationError.
6. Plan step requiring confirmation still prompts/checks (confirmation gate honored, Trap 1).
   If declined -> step fails, remaining cancelled.
7. Plan referencing a deduction intermediate in step purpose resolves intermediate via ReasoningContext.
8. ITEM-017 narration for executed 3-step plan cites every executed step (search + fetch + write).
9. ITEM-017 partial failure: narration names the failed step and the cancelled remainder.
10. Deontic violation pre-check: unsafe plan step is caught and revised/refused.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from lucca.brain.prompt_builder import build_plan_narration_messages
from lucca.core.orchestrator import Orchestrator
from lucca.core.reasoning_context import ReasoningContext
from lucca.core.schemas import Done, GoalPlan, LLMUsage, PlanStep, TokenDelta
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import aggregate_plan_narration_summary
from lucca.sandbox.service import SandboxService
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


@pytest.fixture
def orch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Orchestrator:
    """Provides a hermetic test orchestrator with fake ASR/TTS and mocked network tools."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # Hermetic tool mocks for search and fetch
    def mock_search_web(query: str, max_results: int = 5) -> tuple[dict[str, object], str]:
        return {
            "query": query,
            "ok": True,
            "results": [
                {
                    "title": "Metal Gear Solid",
                    "url": "https://example.com/mgs",
                    "snippet": "Released in 1998 by Konami.",
                }
            ],
        }, "1. Metal Gear Solid - 1998 Konami\n"

    def mock_fetch_url(url: str, **kwargs: object) -> tuple[dict[str, object], str]:
        return {
            "url": url,
            "status_code": 200,
            "content_type": "text/html",
        }, "# MGS\nMetal Gear Solid was released in 1998."

    monkeypatch.setattr("lucca.sandbox.service.search_web", mock_search_web)
    monkeypatch.setattr("lucca.sandbox.service.fetch_url", mock_fetch_url)

    sandbox = SandboxService(workspace_root=workspace, use_direct_fallback=True)
    orchestrator = Orchestrator(
        tts=FakeTTS,
        asr=FakeASR,
        execute_tools=True,
        sandbox=sandbox,
    )
    return orchestrator


# ============================================================================
# 1. Valid 3-Step Plan Execution
# ============================================================================


def test_valid_3step_plan_executes_in_order_with_receipts(orch: Orchestrator) -> None:
    """Test 1: Valid 3-step plan executes in order with per-step receipts recorded."""
    plan_data = {
        "plan_id": "plan-mgs-001",
        "goal": "Research Metal Gear Solid and save summary to notes",
        "rationale": "Search web, fetch article, and save verified summary to notes.",
        "steps": [
            {
                "order": 1,
                "tool": "search_web",
                "args": {"query": "Metal Gear Solid release year"},
                "purpose": "Find release year of MGS",
            },
            {
                "order": 2,
                "tool": "fetch_url",
                "args": {"url": "https://example.com/mgs"},
                "purpose": "Read official page details",
            },
            {
                "order": 3,
                "tool": "note_write",
                "args": {"name": "MGS", "content": "Released in 1998"},
                "purpose": "Save confirmed year into notes",
            },
        ],
    }

    llm = FakeLLM(
        script=[
            TokenDelta(delta=json.dumps(plan_data)),
            Done(usage=LLMUsage(prompt_tokens=30, completion_tokens=80)),
        ]
    )

    trace = TurnTrace(trace_id="tr-plan-001", origin="text")
    plan = orch.run_planning_step(
        goal="Research Metal Gear Solid and save summary to notes",
        trace=trace,
        llm=llm,
    )

    assert plan is not None
    assert plan.plan_id == "plan-mgs-001"
    assert len(plan.steps) == 3
    assert len(plan.receipts) == 3

    # Check order and tool execution
    assert plan.receipts[0]["order"] == 1
    assert plan.receipts[0]["tool"] == "search_web"
    assert plan.receipts[0]["ok"] is True

    assert plan.receipts[1]["order"] == 2
    assert plan.receipts[1]["tool"] == "fetch_url"
    assert plan.receipts[1]["ok"] is True

    assert plan.receipts[2]["order"] == 3
    assert plan.receipts[2]["tool"] == "note_write"
    assert plan.receipts[2]["ok"] is True

    assert orch.current_turn_plan is plan
    assert orch.last_spoken_plan_narration is not None


# ============================================================================
# 2. Invalid Tool Name -> Revision -> Honest Refusal
# ============================================================================


def test_invalid_tool_name_triggers_revision_then_refusal(orch: Orchestrator) -> None:
    """Test 2: Invalid tool name -> revision requested -> second failure -> honest refusal."""
    bad_plan_1 = {
        "plan_id": "plan-bad-1",
        "goal": "Exploit system",
        "steps": [
            {
                "order": 1,
                "tool": "unregistered_hack_tool",
                "args": {"target": "kernel"},
                "purpose": "Attempt invalid action",
            }
        ],
    }
    bad_plan_2 = {
        "plan_id": "plan-bad-2",
        "goal": "Exploit system",
        "steps": [
            {
                "order": 1,
                "tool": "another_nonexistent_tool",
                "args": {},
                "purpose": "Still bad",
            }
        ],
    }

    rounds = [
        [
            TokenDelta(delta=json.dumps(bad_plan_1)),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20)),
        ],
        [
            TokenDelta(delta=json.dumps(bad_plan_2)),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=20)),
        ],
    ]
    llm = FakeLLM(rounds=rounds)

    trace = TurnTrace(trace_id="tr-plan-bad-tool", origin="text")
    plan = orch.run_planning_step(goal="Exploit system", trace=trace, llm=llm)

    assert plan is None
    assert llm.call_count == 2
    assert any("I can't plan that safely because" in s for s in orch.current_turn_tool_spoken)


# ============================================================================
# 3. Step Args Failing Schema -> Revision -> Plan Executes
# ============================================================================


def test_step_args_failing_schema_triggers_revision_then_succeeds(
    orch: Orchestrator, tmp_path: Path
) -> None:
    """Test 3: Step args failing schema -> revision requested -> fixed on revision -> plan executes."""
    test_file = tmp_path / "workspace" / "notes.txt"
    test_file.write_text("Secret notes", encoding="utf-8")

    # Round 1: ReadFileArgs requires path min_length=1; empty string fails schema
    bad_args_plan = {
        "plan_id": "plan-fix-1",
        "goal": "Read file",
        "steps": [
            {
                "order": 1,
                "tool": "read_file",
                "args": {"path": ""},
                "purpose": "Read note content",
            }
        ],
    }
    # Round 2: Fixed arguments
    good_args_plan = {
        "plan_id": "plan-fix-2",
        "goal": "Read file",
        "steps": [
            {
                "order": 1,
                "tool": "read_file",
                "args": {"path": "notes.txt"},
                "purpose": "Read note content",
            }
        ],
    }

    rounds = [
        [
            TokenDelta(delta=json.dumps(bad_args_plan)),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=20)),
        ],
        [
            TokenDelta(delta=json.dumps(good_args_plan)),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=20)),
        ],
    ]
    llm = FakeLLM(rounds=rounds)

    trace = TurnTrace(trace_id="tr-plan-arg-fix", origin="text")
    plan = orch.run_planning_step(goal="Read file", trace=trace, llm=llm)

    assert plan is not None
    assert llm.call_count == 2
    assert len(plan.receipts) == 1
    assert plan.receipts[0]["ok"] is True


# ============================================================================
# 4 & 5. Schema Validation: >8 Steps & Non-Contiguous Order
# ============================================================================


def test_plan_steps_greater_than_8_raises_validation_error() -> None:
    """Test 4: >8 steps -> Pydantic ValidationError."""
    nine_steps = [
        PlanStep(order=i, tool="read_file", args={"path": f"f{i}.txt"}, purpose=f"Step {i}")
        for i in range(1, 10)
    ]
    with pytest.raises(ValidationError) as exc_info:
        GoalPlan(plan_id="p-too-many", goal="Too many steps", steps=nine_steps)

    assert "at most 8 items" in str(exc_info.value)


def test_plan_steps_non_contiguous_order_raises_validation_error() -> None:
    """Test 5: Non-contiguous step orders ([2, 2, 1], [1, 3]) -> Pydantic ValidationError."""
    # Negative control 1: [2, 2, 1]
    steps_duplicate = [
        PlanStep(order=2, tool="read_file", args={"path": "a.txt"}, purpose="First 2"),
        PlanStep(order=2, tool="read_file", args={"path": "b.txt"}, purpose="Second 2"),
        PlanStep(order=1, tool="read_file", args={"path": "c.txt"}, purpose="Third 1"),
    ]
    with pytest.raises(ValidationError) as exc1:
        GoalPlan(plan_id="p-order-dup", goal="Duplicate orders", steps=steps_duplicate)
    assert "contiguous sequence 1..3, got [2, 2, 1]" in str(exc1.value)

    # Negative control 2: [1, 3] (missing 2)
    steps_gap = [
        PlanStep(order=1, tool="read_file", args={"path": "a.txt"}, purpose="Step 1"),
        PlanStep(order=3, tool="read_file", args={"path": "b.txt"}, purpose="Step 3"),
    ]
    with pytest.raises(ValidationError) as exc2:
        GoalPlan(plan_id="p-order-gap", goal="Gap in orders", steps=steps_gap)
    assert "contiguous sequence 1..2, got [1, 3]" in str(exc2.value)


# ============================================================================
# 6. Confirmation Gate & Trap 3 (Partial-Failure Honesty)
# ============================================================================


def test_plan_step_requiring_confirmation_is_gated_and_cancels_on_decline(
    orch: Orchestrator, tmp_path: Path
) -> None:
    """Test 6: Confirmation required tool checks gate. If declined, step fails and remainder is cancelled."""
    target_file = tmp_path / "workspace" / "output.txt"
    plan_data = {
        "plan_id": "plan-confirm-1",
        "goal": "Search then write to file",
        "steps": [
            {
                "order": 1,
                "tool": "search_web",
                "args": {"query": "MGS release date"},
                "purpose": "Search release date",
            },
            {
                "order": 2,
                "tool": "write_file",
                "args": {"path": str(target_file), "content": "1998"},
                "purpose": "Write release date to file",
            },
            {
                "order": 3,
                "tool": "note_write",
                "args": {"name": "MGS", "content": "Saved"},
                "purpose": "Record in note",
            },
        ],
    }

    llm = FakeLLM(
        script=[
            TokenDelta(delta=json.dumps(plan_data)),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=50)),
        ]
    )

    # Mock user declining confirmation for write_file
    orch._request_confirmation = MagicMock(return_value=False)  # type: ignore[assignment]

    trace = TurnTrace(trace_id="tr-plan-confirm-decline", origin="text")
    plan = orch.run_planning_step(goal="Search then write", trace=trace, llm=llm)

    assert plan is not None
    # Step 1 succeeded, Step 2 failed (declined), Step 3 cancelled
    assert len(plan.receipts) == 2
    assert plan.receipts[0]["ok"] is True
    assert plan.receipts[1]["ok"] is False
    assert plan.receipts[1]["tool"] == "write_file"
    assert "cancelled" in str(plan.receipts[1]["result"])

    # Honesty: spoken narration names failed Step 2 (write_file) and cancelled remainder (note_write)
    assert plan.narration is not None
    assert "Step 2 (write_file) failed" in plan.narration
    assert "cancelled the remaining steps (note_write)" in plan.narration
    assert any("cancelled the remaining steps" in s for s in orch.current_turn_tool_spoken)


# ============================================================================
# 7. ReasoningContext Intermediates Resolution
# ============================================================================


def test_plan_referencing_deduction_intermediate_resolves_via_context(orch: Orchestrator) -> None:
    """Test 7: Plan referencing a deduction intermediate in step purpose resolves intermediate via ReasoningContext."""
    ctx = ReasoningContext()
    ctx.add_intermediate(
        envelope_id="env-mgs-1998",
        s="metal_gear_solid",
        p="released_in",
        o="1998",
        confidence=0.98,
        step_kind="deduction",
        rule_id="r-fact",
    )

    plan_data = {
        "plan_id": "plan-ctx-1",
        "goal": "Record release date",
        "steps": [
            {
                "order": 1,
                "tool": "note_write",
                "args": {"name": "MGS", "content": "1998"},
                "purpose": "Store verified date citing env-mgs-1998",
            }
        ],
    }

    llm = FakeLLM(
        script=[
            TokenDelta(delta=json.dumps(plan_data)),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=30)),
        ]
    )

    trace = TurnTrace(trace_id="tr-plan-ctx", origin="text")
    plan = orch.run_planning_step(
        goal="Record release date",
        trace=trace,
        llm=llm,
        context=ctx,
    )

    assert plan is not None
    assert len(plan.receipts) == 1
    assert "env-mgs-1998" in plan.receipts[0]["resolved_intermediates"]


# ============================================================================
# 8 & 9. ITEM-017 Narration Aggregation & Partial-Failure Speech
# ============================================================================


def test_item017_narration_aggregates_all_executed_steps(orch: Orchestrator) -> None:
    """Test 8: ITEM-017 narration for executed 3-step plan cites every executed step (search + fetch + write)."""
    plan_data = {
        "plan_id": "plan-mgs-all",
        "goal": "Research MGS",
        "steps": [
            {
                "order": 1,
                "tool": "search_web",
                "args": {"query": "Metal Gear Solid 1998"},
                "purpose": "Search online",
            },
            {
                "order": 2,
                "tool": "fetch_url",
                "args": {"url": "https://example.com/mgs"},
                "purpose": "Fetch site",
            },
            {
                "order": 3,
                "tool": "note_write",
                "args": {"name": "MGS", "content": "Release 1998"},
                "purpose": "Write note",
            },
        ],
    }

    llm = FakeLLM(
        script=[
            TokenDelta(delta=json.dumps(plan_data)),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=60)),
        ]
    )

    trace = TurnTrace(trace_id="tr-plan-narration", origin="text")
    plan = orch.run_planning_step(goal="Research MGS", trace=trace, llm=llm)

    assert plan is not None
    assert plan.narration is not None

    # ITEM-017 invariant: all intermediate actions are verbally described
    narration_lower = plan.narration.lower()
    assert "searched the web" in narration_lower
    assert "fetched" in narration_lower
    assert "wrote note" in narration_lower


def test_item017_partial_failure_names_failed_step_and_cancelled_remainder(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 9: ITEM-017 partial failure: narration names the failed step and the cancelled remainder."""

    # Mock fetch_url to return a failure
    def mock_failing_fetch_url(url: str, **kwargs: object) -> tuple[dict[str, object], str]:
        raise RuntimeError("HTTP 404 Not Found")

    monkeypatch.setattr("lucca.sandbox.service.fetch_url", mock_failing_fetch_url)

    plan_data = {
        "plan_id": "plan-fail-middle",
        "goal": "Fetch and note",
        "steps": [
            {
                "order": 1,
                "tool": "search_web",
                "args": {"query": "MGS"},
                "purpose": "Search query",
            },
            {
                "order": 2,
                "tool": "fetch_url",
                "args": {"url": "https://example.com/mgs-404"},
                "purpose": "Fetch page",
            },
            {
                "order": 3,
                "tool": "note_write",
                "args": {"name": "MGS", "content": "data"},
                "purpose": "Save to note",
            },
        ],
    }

    llm = FakeLLM(
        script=[
            TokenDelta(delta=json.dumps(plan_data)),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=60)),
        ]
    )

    trace = TurnTrace(trace_id="tr-plan-partial-fail", origin="text")
    plan = orch.run_planning_step(goal="Fetch and note", trace=trace, llm=llm)

    assert plan is not None
    assert len(plan.receipts) == 2
    assert plan.receipts[0]["ok"] is True
    assert plan.receipts[1]["ok"] is False

    # Narration must cite failed step and cancelled remainder
    assert "Step 2 (fetch_url) failed" in plan.narration
    assert "cancelled the remaining steps (note_write)" in plan.narration


# ============================================================================
# 10. Deontic Pre-Check Invariant
# ============================================================================


def test_plan_with_deontic_violation_triggers_revision_or_refusal(orch: Orchestrator) -> None:
    """Test 10: SpeculativeBDIValidator intercepts unsafe steps during plan validation."""
    # Attempting to read Windows System32 is prohibited by SpeculativeBDIValidator
    forbidden_plan = {
        "plan_id": "plan-bdi-viol",
        "goal": "Read system file",
        "steps": [
            {
                "order": 1,
                "tool": "read_file",
                "args": {"path": "C:\\Windows\\System32\\cmd.exe"},
                "purpose": "Read system binary",
            }
        ],
    }

    rounds = [
        [
            TokenDelta(delta=json.dumps(forbidden_plan)),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=30)),
        ],
        [
            TokenDelta(delta=json.dumps(forbidden_plan)),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=30)),
        ],
    ]
    llm = FakeLLM(rounds=rounds)

    trace = TurnTrace(trace_id="tr-plan-bdi", origin="text")
    plan = orch.run_planning_step(goal="Read system file", trace=trace, llm=llm)

    assert plan is None
    assert any("deontic violation" in s.lower() for s in orch.current_turn_tool_spoken)


def test_aggregate_plan_narration_summary() -> None:
    """Tests deterministic aggregate_plan_narration_summary formatting."""
    executed = [
        ("search_web", {"query": "MGS"}, True, "found"),
        ("fetch_url", {"url": "https://example.com"}, False, "timeout"),
    ]
    cancelled = [("note_write", {"name": "MGS"})]
    summary = aggregate_plan_narration_summary(
        executed_steps=executed,
        cancelled_steps=cancelled,
        failed_step_order=2,
    )
    assert "Step 1: search_web" in summary
    assert "Step 2: fetch_url" in summary
    assert "Remaining steps cancelled due to Step 2 failure: note_write" in summary


def test_build_plan_narration_messages() -> None:
    """Tests LLM message construction for multi-step plan narration."""
    messages = build_plan_narration_messages(
        goal="Research MGS",
        plan_id="plan-mgs-test",
        step_summaries=[
            ("search_web", {"query": "MGS"}, True, "found"),
            ("fetch_url", {"url": "https://example.com"}, True, "article text"),
        ],
    )
    assert len(messages) == 3
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert messages[2].role == "assistant"
    content = str(messages[2].content)
    assert "plan-mgs-test" in content
    assert "Step 1: search_web" in content
    assert "Step 2: fetch_url" in content
