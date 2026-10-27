"""
WO-38 Phase 3 — GBNF action-claim channel production wiring verification.

Validates the audit finding and the flag-gated fix:

- Audit finding (v1): ``get_action_claim_grammar()`` loaded the GBNF text and
  passed it down, but the orchestrator drops the grammar on every round where
  tools are active (``grammar if not round_tools else None``). With
  ``execute_tools=True`` and ``tools=None`` the grammar never reaches the
  llama-server payload — the prompt-only path measured as Paper 2 Arm 1.
- Flag ON (``llm.action_claim_grammar_enabled``): the narration call runs with
  an empty tool list so ``action_claim.gbnf`` actually reaches the sampling
  payload (LLMClient sends grammar XOR tools).
- Flag OFF: byte-identical v1 behavior (TRAP 10; Paper 2 Arm 1 reproduction).
- Supervisor: receipt-less structured action claims are rejected (TIER_1_ABORT);
  receipt-matched claims pass.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from lucca.brain.llm_client import LLMClient
from lucca.core.config import get_config
from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import ChatMessage, Done, LLMUsage
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import TurnPipeline, action_claim_grammar_enabled
from lucca.sandbox.output_supervisor import (
    ActionClaimGrammarSupervisor,
    GateResult,
    SeverityTier,
)
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS

GRAMMAR_TEXT = "root ::= prose-text\nprose-text ::= [a-z]+"


@pytest.fixture
def orch(execute_tools: bool = True) -> Orchestrator:
    o = Orchestrator(
        tts=FakeTTS,
        asr=FakeASR,
        llm=FakeLLM(script=[Done(usage=LLMUsage(prompt_tokens=1, completion_tokens=1))]),
        execute_tools=execute_tools,
    )
    yield o
    o.stop()


def _set_flag(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    cfg = get_config()
    monkeypatch.setattr(cfg.llm, "action_claim_grammar_enabled", value)


# ---------------------------------------------------------------------------
# Layer A: pipeline request decision (narration_grammar_request)
# ---------------------------------------------------------------------------


def test_flag_off_returns_none_tools_and_loaded_grammar(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag OFF: tools=None → v1 orchestrator path; byte-identical behavior."""
    _set_flag(monkeypatch, False)
    assert action_claim_grammar_enabled() is False
    pipeline = orch.turn_pipeline
    assert isinstance(pipeline, TurnPipeline)
    tools, grammar = pipeline.narration_grammar_request()
    assert tools is None
    # The grammar text itself still loads (it is simply dropped by the
    # orchestrator whenever tools are active — the Arm 1 prompt-only path).
    assert grammar is not None and "action-claim-block" in grammar


def test_flag_on_returns_empty_tools_and_loaded_grammar(
    orch: Orchestrator, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag ON: empty tool list keeps round_tools falsy so the grammar survives."""
    _set_flag(monkeypatch, True)
    assert action_claim_grammar_enabled() is True
    tools, grammar = orch.turn_pipeline.narration_grammar_request()
    assert tools == []
    assert grammar is not None and "action-claim-block" in grammar


# ---------------------------------------------------------------------------
# Layer B: orchestrator → FakeLLM kwargs (grammar-drop audit semantics)
# ---------------------------------------------------------------------------


def _run_narration(o: Orchestrator, tools: list[object] | None, grammar: str | None) -> dict[str, object]:
    trace = TurnTrace(trace_id=f"wo38-p3-{id(o)}")
    o._stream_llm_speech(
        trace=trace,
        user_msg="narrate the result",
        decision_id=None,
        messages=[ChatMessage(role="user", content="narrate the result")],
        tools=tools,
        grammar=grammar,
    )
    assert isinstance(o.llm, FakeLLM)
    return o.llm.last_kwargs


def test_v1_active_tools_drop_grammar(orch: Orchestrator) -> None:
    """Audit finding reproduced: with tools=None + execute_tools=True, round tools
    are active and the orchestrator drops the grammar (never reaches sampling)."""
    kwargs = _run_narration(orch, None, GRAMMAR_TEXT)
    assert kwargs.get("grammar") is None
    tools_arg = kwargs.get("tools")
    assert isinstance(tools_arg, list) and len(tools_arg) > 0


def test_flag_on_empty_tools_deliver_grammar(orch: Orchestrator) -> None:
    """Fixed path: with tools=[] the grammar is delivered to the stream request."""
    kwargs = _run_narration(orch, [], GRAMMAR_TEXT)
    assert kwargs.get("grammar") == GRAMMAR_TEXT


# ---------------------------------------------------------------------------
# Layer C: llama-server sampling payload (mock httpx)
# ---------------------------------------------------------------------------


def _capture_payload(client_kwargs: dict[str, object]) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_stream(
        self: httpx.Client, method: str, url: str, json: dict[str, object] | None = None, **kw: object
    ) -> object:  # type: ignore[no-untyped-def]
        captured.update(json or {})

        class FakeResponse:
            status_code = 200

            def iter_lines(self):  # type: ignore[no-untyped-def]
                yield 'data: {"choices": [{"delta": {"content": "ok"}}]}'
                yield "data: [DONE]"

            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *args: object):  # type: ignore[no-untyped-def]
                pass

        return FakeResponse()

    with (
        patch("httpx.Client.stream", fake_stream),
        patch("httpx.Client.post", return_value=None),
    ):
        client = LLMClient(base_url="http://fake-llm:8080")
        list(client.stream_turn(**client_kwargs))  # type: ignore[arg-type]
    return captured


def test_payload_contains_grammar_when_grammar_passed() -> None:
    payload = _capture_payload(
        {
            "messages": [ChatMessage(role="user", content="hi")],
            "grammar": GRAMMAR_TEXT,
            "tools": [],
        }
    )
    assert payload.get("grammar") == GRAMMAR_TEXT
    assert "tools" not in payload  # grammar XOR tools


def test_payload_omits_grammar_when_disabled() -> None:
    payload = _capture_payload({"messages": [ChatMessage(role="user", content="hi")]})
    assert "grammar" not in payload
    assert "tools" in payload  # v1: tool schemas present


# ---------------------------------------------------------------------------
# Layer D: supervisor receipt semantics (plan manifest)
# ---------------------------------------------------------------------------


def test_receipt_less_structured_action_rejected() -> None:
    supervisor = ActionClaimGrammarSupervisor()
    res: GateResult = supervisor.evaluate_clause(
        "[ACTION: send weekly-report.pdf to ali]", verified_receipts=[]
    )
    assert res.is_breach is True
    assert res.breach_type == "ungrounded_action"
    assert res.severity == SeverityTier.TIER_1_ABORT


def test_receipt_matched_structured_action_passes() -> None:
    supervisor = ActionClaimGrammarSupervisor()
    res: GateResult = supervisor.evaluate_clause(
        "[ACTION: send weekly-report.pdf to ali]",
        verified_receipts=[{"action": "send", "target": "weekly-report.pdf", "status": "success"}],
    )
    assert res.is_breach is False
