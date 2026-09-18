"""
Property Test P-08 & Wire Framing Tests (Spec 01 §2)
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lucca.core.exceptions import IPCError
from lucca.core.ipc_schemas import (
    MAX_FRAME_SIZE,
    Envelope,
    decode_envelope,
    encode_envelope,
)


def test_basic_codec_round_trip():
    env = Envelope(
        type="turn.start",
        trace_id="01J8ABCDEF1234567890ABCDEF",
        ts_ns=123456789,
        src="core",
        payload={"mode": "audio", "turn": 1},
    )
    wire_bytes = encode_envelope(env)
    assert len(wire_bytes) > 4

    decoded = decode_envelope(wire_bytes)
    assert decoded.v == env.v
    assert decoded.type == env.type
    assert decoded.trace_id == env.trace_id
    assert decoded.ts_ns == env.ts_ns
    assert decoded.src == env.src
    assert decoded.payload == env.payload


def test_oversized_frame_rejected():
    large_payload = "x" * (MAX_FRAME_SIZE + 10)
    env = Envelope(
        type="test.large",
        trace_id="01J8ABCDEF1234567890ABCDEF",
        ts_ns=1000,
        src="core",
        payload={"data": large_payload},
    )
    with pytest.raises(IPCError, match="exceeds 1 MiB limit"):
        encode_envelope(env)


def test_truncated_frame_rejected():
    with pytest.raises(IPCError, match="truncated"):
        decode_envelope(b"12")


def test_corrupt_json_rejected():
    # 4 bytes length prefix = 10, followed by invalid json
    import struct

    bad_frame = struct.pack(">I", 10) + b"{not_json:"
    with pytest.raises(IPCError, match="decoding failed"):
        decode_envelope(bad_frame)


# Hypothesis Property Test P-08: Envelope codec round-trip for arbitrary valid payloads
@settings(max_examples=200, deadline=None)
@given(
    dotted_type=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._-"),
        min_size=1,
        max_size=50,
    ),
    trace_id=st.text(min_size=1, max_size=32),
    ts_ns=st.integers(min_value=0, max_value=2**63 - 1),
    src=st.sampled_from(["core", "audio", "npu", "ui"]),
    payload=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(),
            st.booleans(),
        ),
        max_size=10,
    ),
)
def test_hypothesis_p08_codec_round_trip(dotted_type, trace_id, ts_ns, src, payload):
    env = Envelope(
        type=dotted_type,
        trace_id=trace_id,
        ts_ns=ts_ns,
        src=src,
        payload=payload,
    )
    encoded = encode_envelope(env)
    decoded = decode_envelope(encoded)

    assert decoded.type == env.type
    assert decoded.trace_id == env.trace_id
    assert decoded.ts_ns == env.ts_ns
    assert decoded.src == env.src
    assert decoded.payload == env.payload


def test_ui_schemas_codec_round_trip():
    from lucca.core.ipc_schemas import (
        UICaptionPayload,
        UIConfigUpdatePayload,
        UIUserTextPayload,
    )

    # 1. UICaptionPayload
    cap = UICaptionPayload(text="Hello world!", is_final=True, source="assistant")
    env_cap = Envelope(
        type="ui.caption", trace_id="123", ts_ns=1000, src="core", payload=cap.model_dump()
    )
    dec_cap = decode_envelope(encode_envelope(env_cap))
    assert dec_cap.payload["text"] == "Hello world!"
    assert dec_cap.payload["is_final"] is True
    assert dec_cap.payload["source"] == "assistant"

    # 2. UIUserTextPayload
    user_txt = UIUserTextPayload(text="What is your status?")
    env_txt = Envelope(
        type="ui.user_text", trace_id="", ts_ns=2000, src="ui", payload=user_txt.model_dump()
    )
    dec_txt = decode_envelope(encode_envelope(env_txt))
    assert dec_txt.payload["text"] == "What is your status?"

    # 3. UIConfigUpdatePayload
    cfg = UIConfigUpdatePayload(voice="af_bella", speed=1.05, ptt_key="alt-gr")
    env_cfg = Envelope(
        type="ui.config_update", trace_id="", ts_ns=3000, src="ui", payload=cfg.model_dump()
    )
    dec_cfg = decode_envelope(encode_envelope(env_cfg))
    assert dec_cfg.payload["voice"] == "af_bella"
    assert dec_cfg.payload["speed"] == 1.05
    assert dec_cfg.payload["ptt_key"] == "alt-gr"
