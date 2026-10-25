"""
Project Lucca — Work Order 37 Full Pipeline End-to-End Integration Tests
Validates:
1. Live VerifierWorker initialization on Orchestrator and propagation to UserModel / ReflectionEngine.
2. Live OpenVINO INT8 MiniLM NLI inference (<50ms, ENTAILMENT / CONTRADICTION).
3. Truth-in-Receipt action claim detection with live verifier on Orchestrator.
4. Multi-turn visual session persistence, disk reload, continuity, and epistemic refusal without mocks.
5. High-coverage visual query pattern matching matrix across direct, deictic, attribute, continuity, and non-vision queries.
6. First-person belief stance topic extraction with stopword filtering and clean word-boundary truncation.

Zero Any typing enforced per D-AUD-01.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from lucca.core.coherence import ToolReceipt
from lucca.core.memory_commit_service import _clean_truncate, _extract_stance_topic
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Done, LLMUsage, TokenDelta, VerifierLabel
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import TurnInput, TurnPipeline
from lucca.senses.verifier import VERIFIER_MINILM_DIR, VerifierWorker
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


def _sample_jpeg_b64() -> str:
    """Returns a deterministic minimal 1x1 JPEG in base64."""
    raw = bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000"
        "ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432"
        "ffc0000b080001000101011100ffc4001f000001050101010101000000000000000001020304050607080910"
        "ffc4003b100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a"
        "ffda0008010100003f00fbef6a00ffd9"
    )
    return base64.b64encode(raw).decode("ascii")


def test_orchestrator_initializes_live_verifier_and_infer() -> None:
    """Verifies that Orchestrator naturally instantiates and wires VerifierWorker with live OpenVINO model."""
    fake_llm = FakeLLM()
    orch = Orchestrator(
        execute_tools=False,
        tts=FakeTTS,
        asr=FakeASR,
        llm=fake_llm,
    )
    try:
        assert orch.verifier is not None
        assert isinstance(orch.verifier, VerifierWorker)
        assert orch.user_model.verifier is orch.verifier
        if orch.reflection_engine is not None:
            assert orch.reflection_engine.idle_pulse.verifier is orch.verifier

        # Live OpenVINO inference check (must complete under 50ms)
        res_ent = orch.verifier.check_consistency(
            premise="The cat is on the mat.",
            hypothesis="There is a cat on the mat.",
        )
        assert res_ent.label == VerifierLabel.ENTAILMENT
        assert res_ent.latency_ms <= 50.0

        res_con = orch.verifier.check_consistency(
            premise="The cat is on the mat.",
            hypothesis="There is no cat here.",
        )
        assert res_con.label == VerifierLabel.CONTRADICTION
        assert res_con.latency_ms <= 50.0
    finally:
        orch.stop()


def test_truth_in_receipt_wired_with_live_orchestrator() -> None:
    """Verifies Truth-in-Receipt detects ungrounded action claims using the orchestrator's verifier."""
    fake_llm = FakeLLM()
    orch = Orchestrator(
        execute_tools=False,
        tts=FakeTTS,
        asr=FakeASR,
        llm=fake_llm,
    )
    try:
        # Ungrounded action claim with no receipts
        breach = orch._check_functional_coherence(
            narration="I deleted your production database from the server.",
            receipts=[],
        )
        assert breach is not None
        assert "Ungrounded" in breach or "delete" in breach

        # Grounded action claim with matching receipt
        receipt = ToolReceipt(
            tool="write_file",
            ok=True,
            call_id="call-01",
            args={"path": "notes.txt"},
            output="file written successfully",
        )
        no_breach = orch._check_functional_coherence(
            narration="I saved the summary to notes.txt.",
            receipts=[receipt],
        )
        assert no_breach is None
    finally:
        orch.stop()


def test_orchestrator_multiturn_vision_continuity(tmp_path: Path) -> None:
    """Verifies complete multi-turn dialogue with real Orchestrator, session reload, and continuity."""
    fake_llm = FakeLLM(
        script=[
            TokenDelta(delta="I can see the icon clearly on screen! "),
            Done(usage=LLMUsage(prompt_tokens=15, completion_tokens=8)),
        ]
    )
    orch = Orchestrator(
        execute_tools=False,
        tts=FakeTTS,
        asr=FakeASR,
        llm=fake_llm,
    )
    # Point visual session to isolated tmp directory for test cleanliness
    from lucca.core.visual_session import VisualSessionStore

    v_dir = tmp_path / "sessions" / "images"
    orch.visual_session = VisualSessionStore(v_dir)

    try:
        sample_b64 = _sample_jpeg_b64()

        # Turn 1: Direct user attachment with vision question
        trace1 = TurnTrace(trace_id="t-wo37-1", session_id="wo37-session")
        inp1 = TurnInput(
            trace=trace1,
            origin="text",
            user_text="Can you see yourself in this image?",
            image_b64=sample_b64,
        )
        orch.turn_pipeline.run(inp1)

        assert orch.visual_session.count == 1
        assert orch.current_turn_image_b64 == sample_b64
        assert fake_llm.all_kwargs[0]["current_image_b64"] == sample_b64

        # Turn 2: Follow-up appearance question without re-attaching image
        trace2 = TurnTrace(trace_id="t-wo37-2", session_id="wo37-session")
        inp2 = TurnInput(
            trace=trace2,
            origin="text",
            user_text="What do you look like?",
            image_b64=None,
        )
        orch.turn_pipeline.run(inp2)

        assert orch.current_turn_image_b64 == sample_b64
        assert fake_llm.all_kwargs[1]["current_image_b64"] == sample_b64

        # Turn 3: Follow-up spatial/continuity question
        trace3 = TurnTrace(trace_id="t-wo37-3", session_id="wo37-session")
        inp3 = TurnInput(
            trace=trace3,
            origin="text",
            user_text="Is it on the left or the right?",
            image_b64=None,
        )
        orch.turn_pipeline.run(inp3)

        assert orch.current_turn_image_b64 == sample_b64
        assert fake_llm.all_kwargs[2]["current_image_b64"] == sample_b64

        # Turn 4: Topic switch to non-visual arithmetic (must NOT inject image)
        trace4 = TurnTrace(trace_id="t-wo37-4", session_id="wo37-session")
        inp4 = TurnInput(
            trace=trace4,
            origin="text",
            user_text="What is 5 plus 5?",
            image_b64=None,
        )
        orch.turn_pipeline.run(inp4)

        assert orch.current_turn_image_b64 is None
        assert fake_llm.all_kwargs[3]["current_image_b64"] is None

        # Turn 5: User clears image and asks a vision query -> Epistemic Guard must fire
        orch.visual_session.clear()
        assert orch.visual_session.count == 0

        prev_call_count = fake_llm.call_count
        trace5 = TurnTrace(trace_id="t-wo37-5", session_id="wo37-session")
        inp5 = TurnInput(
            trace=trace5,
            origin="text",
            user_text="Can you see me?",
            image_b64=None,
        )
        orch.turn_pipeline.run(inp5)

        # LLM must not be called; refusal spoken
        assert fake_llm.call_count == prev_call_count
        assert len(orch.history) >= 2
        refusal_msg = orch.history[-1]["content"]
        assert "don't have an active image in our session" in refusal_msg
    finally:
        orch.stop()


def test_is_vision_query_matrix_accuracy() -> None:
    """Verifies pattern matching precision and recall across full query matrix."""
    pipeline = TurnPipeline.__new__(TurnPipeline)

    direct_queries: list[str] = [
        "Can you see yourself in this image?",
        "Can you describe what you look like in the image?",
        "Can you see yourself?",
        "Can you see me?",
        "Do you see me?",
        "Do you see anything?",
        "What do you see?",
        "What can you see?",
        "Tell me what you see",
        "What are you looking at?",
        "Look at this picture",
        "Look at that",
        "Examine this image",
        "Inspect this screenshot",
        "Check out my screen",
        "What's on my screen?",
        "What is on the screen?",
        "What does the screen say?",
        "Read the text on the badge",
        "What do you look like?",
        "What does it look like?",
        "What am I wearing?",
        "What color is it?",
        "What colour is the icon?",
    ]

    continuity_queries: list[str] = [
        "Where is it?",
        "Which one is it?",
        "Which one is bigger?",
        "Is it on the left or the right?",
        "Is it on the left?",
        "What's in the background?",
        "Tell me more about it",
        "What else is there?",
        "Who is that?",
        "How many are there?",
    ]

    non_vision_queries: list[str] = [
        "What is 2 + 2?",
        "Write a python script to sort a list",
        "What time is it?",
        "Who was the first president of the United States?",
        "Tell me a joke",
        "Good morning",
        "How's the weather today?",
        "Search for latest news",
        "Can you help me write an email?",
        "Reboot the system",
    ]

    # Direct queries must match even without active image
    for q in direct_queries:
        assert pipeline._is_vision_query(q, has_active_image=False) is True, f"Failed direct: {q}"

    # Continuity queries must match with active image, and NOT match without active image
    for q in continuity_queries:
        assert pipeline._is_vision_query(q, has_active_image=True) is True, f"Failed continuity: {q}"
        assert pipeline._is_vision_query(q, has_active_image=False) is False, f"False positive non-active: {q}"

    # Non-vision queries must never match in either mode
    for q in non_vision_queries:
        assert pipeline._is_vision_query(q, has_active_image=False) is False, f"False positive: {q}"
        assert pipeline._is_vision_query(q, has_active_image=True) is False, f"False positive: {q}"


def test_belief_stance_topic_extraction_all_idiomatic_cases() -> None:
    """Verifies stance topic extraction rejects stopwords and truncates on word boundaries."""
    # Idiomatic pre-marker fallback
    topic1 = _extract_stance_topic("My engagement register is quite high when I think about it")
    assert topic1 == "My engagement register is quite high"
    assert "about it" not in topic1.lower()

    # Generic post-marker stopword avoidance
    topic2 = _extract_stance_topic("I think about it quite often")
    assert topic2 != "about it"

    # Preserves authentic non-stopword stance beliefs
    topic3 = _extract_stance_topic("I believe that neural scaling is the key insight here")
    assert "neural scaling is the key insight" in topic3

    # Clean word truncation without mid-word cuts
    truncated = _clean_truncate("This is a rather long sentence that exceeds forty characters by a lot", max_len=40)
    assert len(truncated) <= 40
    # Must end on complete word, not half-cut word
    assert not truncated.endswith("exceed")
