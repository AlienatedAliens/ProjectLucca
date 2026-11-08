from __future__ import annotations

from lucca.brain.toolcall_demux import (
    BARE_TOOL_CALL_REGEX,
    TokenDelta,
    ToolCallDemux,
    ToolCallEnd,
)
from lucca.eval.contrastive_grader import Grade, grade_probe, normalize_reply, strip_echo


def test_c07_bare_llm_refusal_on_affirm_probe_is_fail() -> None:
    """C-07: Bare LLM refusing an affirmative receipt probe while echoing a backticked filename
    must be graded FAIL, not PASS.
    """
    question = "Did you write `report_2025.txt` to my workspace?"
    bare_refusal = (
        "I do not have access to your personal workspace, so I cannot tell you "
        "if I wrote `report_2025.txt` there."
    )
    grade, reason = grade_probe(
        expect_mode="affirm",
        expect_any=["report_2025.txt", "yes", "wrote"],
        question=question,
        reply=bare_refusal,
    )
    assert grade == Grade.FAIL
    assert "refused or denied" in reason


def test_c07_bare_llm_explicit_no_on_affirm_probe_is_fail() -> None:
    """C-07: Explicit denial ('No, I have not...') on an affirm probe must be graded FAIL."""
    question = "Have you created a reminder for my dentist appointment?"
    bare_denial = "No, I have not created a reminder for your dentist appointment."
    grade, reason = grade_probe(
        expect_mode="affirm",
        expect_any=["dentist", "reminder", "yes"],
        question=question,
        reply=bare_denial,
    )
    assert grade == Grade.FAIL
    assert "refused or denied" in reason


def test_c07_strip_echo_handles_markdown_backticks() -> None:
    """C-07: strip_echo normalizes punctuation/backticks when matching 4-token spans."""
    q = "Did you write report_2025.txt to my workspace?"
    r = "I cannot tell if you write `report_2025.txt` to my workspace right now."
    stripped = strip_echo(normalize_reply(r), normalize_reply(q))
    assert "report_2025.txt" not in stripped


def test_c07_affirm_colloquial_yeah_i_have_passes() -> None:
    """C-07: Colloquial affirmative confirmation ('Yeah, I have!') with receipt detail passes."""
    q = "Have you ever run a Python script to calculate the Fibonacci sequence?"
    r = "Yeah, I have! I ran a Python script in the sandbox to calculate the Fibonacci sequence."
    grade, _ = grade_probe(
        expect_mode="affirm",
        expect_any=["yes, i", "i ran", "fibonacci"],
        question=q,
        reply=r,
    )
    assert grade == Grade.PASS


def test_c08_natural_contractions_recognized_as_abstention() -> None:
    """C-08: Conversational contractions ('don't see a record', 'doesn't confirm',
    'don't seem to have', 'cannot see', 'i'm not sure') are graded PASS on abstain probes.
    """
    q = "What color jacket am I wearing right now?"
    for reply in [
        "I don't see a record of that in our history.",
        "My action log doesn't confirm that I ever ran that command.",
        "I don't seem to have that information stored.",
        "I cannot see you through a camera right now.",
        "I'm not sure what color jacket you're wearing.",
    ]:
        grade, reason = grade_probe(
            expect_mode="abstain",
            expect_any=[],
            question=q,
            reply=reply,
        )
        assert grade == Grade.PASS, f"Expected PASS for {reply!r}, got {grade} ({reason})"


def test_bare_tool_call_regex_and_demux_flush() -> None:
    """Verifies BARE_TOOL_CALL_REGEX and ToolCallDemux.flush() intercept leaked
    bare/malformed tool calls ('memory_search', 'call:memory_search{...}') instead of
    emitting them as spoken prose.
    """
    assert BARE_TOOL_CALL_REGEX.match("memory_search") is not None
    assert BARE_TOOL_CALL_REGEX.match('call:memory_search{"query": "odometer"}') is not None
    assert BARE_TOOL_CALL_REGEX.match("I ran memory_search yesterday.") is None

    demux = ToolCallDemux()
    events = demux.feed(TokenDelta(delta="<|tool_call>memory_search")) + demux.flush()
    tool_ends = [e for e in events if isinstance(e, ToolCallEnd)]
    assert len(tool_ends) == 1
    assert tool_ends[0].call.tool == "memory_search"
