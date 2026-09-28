"""
Project Lucca — Streaming Chunker & Tool Demux Mechanical Tests
Spec 08 §6 (T-CHK-01 through T-CHK-10)
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from lucca.brain.chunker import StreamingChunker, normalise_text
from lucca.brain.toolcall_demux import ToolCallDemux
from lucca.core.schemas import TokenDelta, ToolCallEnd


def test_t_chk_01_decimal_protection_char_stream():
    """T-CHK-01: 'Pi is 3.14. Next.' streamed char-by-char never splits inside 3.14."""
    chunker = StreamingChunker()
    text = "Pi is 3.14. Next."
    chunks = []
    for ch in text:
        chunks.extend(chunker.feed(ch))
    chunks.extend(chunker.flush())

    chunk_texts = [c.text for c in chunks]
    assert "Pi is 3." not in chunk_texts
    assert any("3.14" in t for t in chunk_texts)


def test_t_chk_02_filename_dots_preserved():
    """T-CHK-02: 'Open config.yaml and README.md now.' preserves dots without split."""
    chunker = StreamingChunker()
    chunks = chunker.feed("Open config.yaml and README.md now.")
    chunks.extend(chunker.flush())

    assert len(chunks) == 1
    assert "config.yaml" in chunks[0].text
    assert "README.md" in chunks[0].text


def test_t_chk_03_abbreviation_dr_smith():
    """T-CHK-03: 'Dr. Smith arrived. He left.' -> does not split on Dr."""
    chunker = StreamingChunker()
    chunks = chunker.feed("Dr. Smith arrived. He left.")
    chunks.extend(chunker.flush())

    texts = [c.text for c in chunks]
    assert not any(t.strip() == "Dr." for t in texts)
    assert any("Dr. Smith" in t for t in texts)


def test_t_chk_04_eg_ie_abbreviations():
    """T-CHK-04: 'e.g. apples, i.e. fruit. Done.' -> no split on e.g. or i.e."""
    chunker = StreamingChunker()
    chunks = chunker.feed("e.g. apples, i.e. fruit. Done.")
    chunks.extend(chunker.flush())

    texts = [c.text for c in chunks]
    assert not any(t.strip() == "e.g." for t in texts)
    assert not any(t.strip() == "i.e." for t in texts)


def test_t_chk_05_force_split_run_on_text():
    """T-CHK-05: 400-char text with no punctuation -> force-split <= 260; no chunk > 260."""
    chunker = StreamingChunker()
    word = "word "
    long_text = word * 80  # 400 chars
    chunks = chunker.feed(long_text)
    chunks.extend(chunker.flush())

    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.text) <= 260


def test_t_chk_07_markdown_normalisation():
    """T-CHK-07: Markdown bold, code, links stripped from spoken text."""
    input_text = "**Bold** and `code` and [link](http://example.com/test). Next."
    norm = normalise_text(input_text)
    assert "**" not in norm
    assert "`" not in norm
    assert "http://" not in norm
    assert "Bold" in norm
    assert "link" in norm


def test_t_chk_08_emoji_and_smart_quotes():
    """T-CHK-08: Emoji removed, smart quotes normalised."""
    input_text = "“Hello world” 😊 … test — next"
    norm = normalise_text(input_text)
    assert '"Hello world"' in norm
    assert "😊" not in norm
    assert "..." in norm
    assert ", next" in norm


def test_t_chk_09_is_first_and_reset():
    """T-CHK-09: is_first only on chunk 0; reset() restores is_first=True on next turn."""
    chunker = StreamingChunker()
    c1 = chunker.feed("This is the first sentence. ")
    c2 = chunker.feed("This is the second sentence of the reply and it is long enough. ")
    all_chunks = c1 + c2

    assert len(all_chunks) >= 2
    assert all_chunks[0].is_first is True
    assert all_chunks[1].is_first is False

    # Reset (barge-in)
    chunker.reset()
    c_new = chunker.feed("New sentence after barge-in. ")
    assert len(c_new) >= 1
    assert c_new[0].is_first is True


def test_t_chk_10_tool_call_demux_inline_and_structured():
    """T-CHK-10: Tool-call JSON demuxed to ToolCallEnd; never passed as spoken text."""
    demux = ToolCallDemux()

    # 1. Inline tool call
    inline_stream = [
        TokenDelta(delta='{"name": "launch_app", '),
        TokenDelta(delta='"arguments": {"app": "calculator"}}'),
    ]
    events = []
    for delta in inline_stream:
        events.extend(demux.feed(delta))
    events.extend(demux.flush())

    tool_ends = [e for e in events if isinstance(e, ToolCallEnd)]
    text_deltas = [e for e in events if isinstance(e, TokenDelta)]

    assert len(tool_ends) == 1
    assert tool_ends[0].call.tool == "launch_app"
    assert tool_ends[0].call.args == {"app": "calculator"}
    assert len(text_deltas) == 0

    # 2. Plain text (not a tool call)
    demux2 = ToolCallDemux()
    text_stream = [
        TokenDelta(delta="Here is some regular spoken text. "),
        TokenDelta(delta="It is not a tool call."),
    ]
    events2 = []
    for delta in text_stream:
        events2.extend(demux2.feed(delta))
    events2.extend(demux2.flush())

    tool_ends2 = [e for e in events2 if isinstance(e, ToolCallEnd)]
    text_deltas2 = [e for e in events2 if isinstance(e, TokenDelta)]

    assert len(tool_ends2) == 0
    assert len(text_deltas2) >= 2


def test_t_chk_11_tool_call_demux_function_tag_bonsai_style():
    """T-CHK-11: Qwen/Harmony-style <function=...> blocks (Bonsai 2) demuxed to
    ToolCallEnd, including mid-stream after narration text; never spoken."""
    demux = ToolCallDemux()

    # 1. Mid-stream function tag after narration (Bonsai 2 leak pattern)
    stream = [
        TokenDelta(delta="Let me try another approach.\n\n"),
        TokenDelta(delta="<function=run_python>\n<parameter=code>"),
        TokenDelta(delta='print("hello")</parameter>\n</function>'),
    ]
    events = []
    for delta in stream:
        events.extend(demux.feed(delta))
    events.extend(demux.flush())

    tool_ends = [e for e in events if isinstance(e, ToolCallEnd)]
    text_deltas = [e for e in events if isinstance(e, TokenDelta)]

    assert len(tool_ends) == 1
    assert tool_ends[0].call.tool == "run_python"
    assert tool_ends[0].call.args == {"code": 'print("hello")'}
    # Narration before the tag is spoken; the tag itself is never spoken
    joined = "".join(e.delta for e in text_deltas)
    assert "Let me try another approach." in joined
    assert "<function=" not in joined

    # 2. Function tag at stream start
    demux2 = ToolCallDemux()
    stream2 = [
        TokenDelta(delta="<function=launch_app>\n"),
        TokenDelta(delta="<parameter=app>Notepad</parameter>\n"),
        TokenDelta(delta="</function>"),
    ]
    events2 = []
    for delta in stream2:
        events2.extend(demux2.feed(delta))
    events2.extend(demux2.flush())

    tool_ends2 = [e for e in events2 if isinstance(e, ToolCallEnd)]
    assert len(tool_ends2) == 1
    assert tool_ends2[0].call.tool == "launch_app"
    assert tool_ends2[0].call.args == {"app": "Notepad"}


# ============================================================================
# WO-9 A6 (F-WO8-26): Gemma demux hardening — T-CHK-12 / T-CHK-13
# ============================================================================


def test_t_chk_12_mid_stream_gemma_tool_call_never_spoken():
    """A tool call arriving AFTER narration must be demuxed, never spoken."""
    demux = ToolCallDemux()
    events: list = []
    events.extend(demux.feed(TokenDelta(delta="Let me check that. ")))
    events.extend(
        demux.feed(TokenDelta(delta='<|tool_call|>call:memory_search{"query": "Sean"}<tool_call|>'))
    )
    events.extend(demux.flush())

    spoken = "".join(e.delta for e in events if isinstance(e, TokenDelta))
    calls = [e for e in events if isinstance(e, ToolCallEnd)]
    assert "tool_call" not in spoken, "unresolved tool markup leaked as speech"
    assert len(calls) == 1
    assert calls[0].call.tool == "memory_search"
    assert calls[0].call.args == {"query": "Sean"}
    assert "Let me check that." in spoken


def test_t_chk_13_lenient_gemma_sentinel_args():
    """Malformed Gemma args (query:<|"|>...<|"|>) parse via the lenient fallback."""
    demux = ToolCallDemux()
    events: list = demux.feed(
        TokenDelta(
            delta='Let me save that. <|tool_call|>call:memory_commit{query:<|"|>My name is Sean<|"|>}'
        )
    )
    events.extend(demux.flush())

    calls = [e for e in events if isinstance(e, ToolCallEnd)]
    assert len(calls) == 1
    assert calls[0].call.tool == "memory_commit"
    assert calls[0].call.args == {"query": "My name is Sean"}
    spoken = "".join(e.delta for e in events if isinstance(e, TokenDelta))
    assert '<|"' not in spoken and "tool_call" not in spoken


def test_t_chk_13b_unresolved_markup_dropped_on_flush():
    """Unparseable tool markup must never be spoken, even at flush."""
    demux = ToolCallDemux()
    events: list = demux.feed(TokenDelta(delta="<|tool_call|>call:broken{no closing"))
    events.extend(demux.flush())
    spoken = "".join(e.delta for e in events if isinstance(e, TokenDelta))
    assert "tool_call" not in spoken
    assert "<|" not in spoken


@given(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=20))
@settings(max_examples=100, deadline=1000)
def test_p_04_chunker_invariants(deltas: list[str]):
    """P-04: Any list of Unicode deltas -> never raises; no chunk > FORCE_SPLIT_AT."""
    chunker = StreamingChunker()
    chunks = []
    for delta in deltas:
        chunks.extend(chunker.feed(delta))
    chunks.extend(chunker.flush())

    for c in chunks:
        assert len(c.text) <= 260


def test_normalise_text_strips_system_tool_traces_and_directives():
    """Verify leaked system tool trace and directive tokens are stripped from spoken text."""
    leaked = (
        "[System Executed Tool Trace: time-greeting-v1({}) -> Status: ok.]\n"
        "Directive: The action above has completed. Grounding your response strictly in the "
        "tool execution output above without fabricating metrics or unverified facts, speak to "
        "the user in your natural companion voice to summarize what happened and what was found. "
        "Do NOT use markdown formatting, bullet points, asterisks, or backticks; "
        "speak in natural, clean spoken prose.\n\n"
        "Yahoo! It is so awesome to see you again!"
    )
    cleaned = normalise_text(leaked)
    assert "[System Executed" not in cleaned
    assert "Directive:" not in cleaned
    assert "Yahoo! It is so awesome to see you again!" in cleaned

