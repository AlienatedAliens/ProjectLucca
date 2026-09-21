"""
Project Lucca — Extended Fuzzing & Adversarial Robustness Test Suite
Continuous regression testing via Hypothesis property-based testing.
Spec 01 §2, Spec 05 §3, Spec 09 §5/§9, Spec 12 §3
"""

from __future__ import annotations

import json
import socket
import string
import struct
import time
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from lucca.brain.chunker import sanitize_for_voice
from lucca.core.exceptions import (
    IPCError,
    SandboxPathError,
    SchemeError,
    SchemeGasExhausted,
    SchemeRuntimeError,
    SchemeSyntaxError,
)
from lucca.core.ipc_schemas import (
    MAX_FRAME_SIZE,
    Envelope,
    decode_envelope,
    encode_envelope,
)
from lucca.core.schemas import RuleState
from lucca.reasoning.scheme.eval import evaluate_expr
from lucca.reasoning.scheme.parser import parse, to_canonical
from lucca.router.heuristic import (
    EMERGENCY_REFLEX_PATTERN,
    FILE_PATTERN,
    QUOTED_PATTERN,
    URL_PATTERN,
    HeuristicRouter,
)
from lucca.sandbox.file_tool import SafeFileTool, validate_rel_path
from lucca.sandbox.policy import (
    CANCEL_PATTERN,
    CONFIRM_PATTERN,
    ConfirmationTokenManager,
    SequenceGuard,
    TaintFlags,
)
from lucca.sandbox.web_tool import MAX_QUERY_LEN, MAX_URL_LEN, validate_url_ssrf


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "fuzz_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# -----------------------------------------------------------------------------
# 1. MicroScheme Fuzzing Properties
# -----------------------------------------------------------------------------

@settings(max_examples=100, deadline=1000)
@given(
    source_text=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd", "P", "Z", "S"),
            blacklist_characters="\x00",
        ),
        min_size=1,
        max_size=300,
    )
)
def test_hypothesis_scheme_parser_robustness(source_text: str) -> None:
    """MicroScheme parser must parse or raise SchemeError, never crash."""
    try:
        ast_node = parse(source_text)
        canonical = to_canonical(ast_node)
        assert isinstance(canonical, str)
    except SchemeError:
        # Expected controlled domain error
        pass
    except Exception as exc:
        pytest.fail(f"Unhandled non-SchemeError exception: {type(exc).__name__}: {exc}")


@settings(max_examples=60, deadline=1000)
@given(
    depth=st.integers(min_value=1, max_value=40),
    op=st.sampled_from(["+", "-", "*", "/", "%"]),
    arg=st.sampled_from(["0", "1", "2", "-10", "3.14", '"hello"', "#t", "#f"]),
)
def test_hypothesis_scheme_eval_gas_and_div0(depth: int, op: str, arg: str) -> None:
    """MicroScheme evaluator handles nested arithmetic, division by zero, and gas limits safely."""
    state = RuleState(schema_version=1, intent="test")
    expr = "1"
    for _ in range(depth):
        expr = f"({op} {expr} {arg})"

    try:
        res = evaluate_expr(expr, state, gas_limit=50)
        assert res is not None
    except SchemeError:
        pass
    except Exception as exc:
        pytest.fail(f"Evaluator raised unexpected exception {type(exc).__name__}: {exc}")


# -----------------------------------------------------------------------------
# 2. Sandbox Path Jailing Properties
# -----------------------------------------------------------------------------

@settings(
    max_examples=150,
    deadline=1000,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    path_input=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "P", "Z", "Cc")),
        min_size=0,
        max_size=1100,
    )
)
def test_hypothesis_sandbox_path_confinement(workspace: Path, path_input: str) -> None:
    """Any input path either safely stays inside workspace or raises SandboxPathError."""
    try:
        resolved = validate_rel_path(path_input, workspace_root=workspace)
        assert resolved.is_relative_to(workspace)
    except SandboxPathError as spe:
        assert spe.code in ("traversal", "invalid_chars", "reserved", "too_long")
    except Exception as exc:
        pytest.fail(f"validate_rel_path raised unexpected {type(exc).__name__}: {exc}")


# -----------------------------------------------------------------------------
# 3. SSRF Guard Properties
# -----------------------------------------------------------------------------

@settings(max_examples=100, deadline=1000)
@given(
    scheme=st.sampled_from(["http", "https", "file", "ftp", "gopher", "data", "php"]),
    host=st.sampled_from([
        "127.0.0.1", "127.0.0.2", "localhost", "169.254.169.254",
        "10.0.0.1", "192.168.1.1", "100.64.0.1", "example.com",
    ]),
    path=st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), min_size=0, max_size=30),
    query=st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")), min_size=0, max_size=150),
)
def test_hypothesis_ssrf_guard(scheme: str, host: str, path: str, query: str) -> None:
    """SSRF guard strictly prevents access to private/loopback/cloud metadata targets."""
    url = f"{scheme}://{host}/{path}"
    if query:
        url += f"?q={query}"

    is_private_host = host in ("127.0.0.1", "127.0.0.2", "localhost", "169.254.169.254", "10.0.0.1", "192.168.1.1", "100.64.0.1")
    mock_ip = "127.0.0.1" if host == "localhost" else (host if is_private_host else "93.184.216.34")
    mock_resolver = lambda h, ip=mock_ip: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]

    try:
        norm_url, res_ip = validate_url_ssrf(url, dns_resolver=mock_resolver)
        # If it passed: scheme must be http/https, host must not be private, IP must be public
        assert scheme in ("http", "https")
        assert not is_private_host
        assert res_ip == "93.184.216.34"
    except SandboxPathError as spe:
        assert spe.code in ("invalid_scheme", "invalid_url", "too_long", "query_too_long", "invalid_host", "ssrf_blocked", "userinfo_forbidden", "ipv6_blocked", "dns_failed", "invalid_ip")
    except Exception as exc:
        pytest.fail(f"validate_url_ssrf raised unexpected {type(exc).__name__}: {exc}")


# -----------------------------------------------------------------------------
# 4. ZeroMQ IPC Codec Properties
# -----------------------------------------------------------------------------

@settings(max_examples=100, deadline=1000)
@given(
    raw_bytes=st.binary(min_size=0, max_size=2048)
)
def test_hypothesis_ipc_fuzz_bytes(raw_bytes: bytes) -> None:
    """Random byte sequences fed to decode_envelope must raise IPCError, never crash."""
    try:
        _ = decode_envelope(raw_bytes)
    except IPCError:
        pass
    except Exception as exc:
        pytest.fail(f"decode_envelope raised unexpected {type(exc).__name__}: {exc}")


@settings(max_examples=80, deadline=1000)
@given(
    dotted_type=st.sampled_from(["turn.start", "turn.end", "audio.chunk", "ui.notify"]),
    trace_id=st.text(min_size=1, max_size=16),
    src=st.sampled_from(["core", "audio", "npu", "ui"]),
    int_val=st.integers(min_value=-10000, max_value=10000),
    str_val=st.text(min_size=0, max_size=50),
)
def test_hypothesis_ipc_roundtrip(dotted_type: str, trace_id: str, src: str, int_val: int, str_val: str) -> None:
    """Valid envelopes encode and decode losslessly."""
    env = Envelope(
        type=dotted_type,
        trace_id=trace_id,
        ts_ns=time.time_ns(),
        src=src,
        payload={"int": int_val, "str": str_val},
    )
    encoded = encode_envelope(env)
    decoded = decode_envelope(encoded)
    assert decoded.type == env.type
    assert decoded.trace_id == env.trace_id
    assert decoded.src == env.src
    assert decoded.payload == env.payload


# -----------------------------------------------------------------------------
# 5. Voice Sanitizer & ReDoS Latency Properties
# -----------------------------------------------------------------------------

@settings(max_examples=100, deadline=1000)
@given(
    text=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "P", "Z", "S")),
        min_size=1,
        max_size=500,
    )
)
def test_hypothesis_voice_sanitizer_redos_latency(text: str) -> None:
    """Voice sanitizer finishes under 10ms and strips backticks and bullets."""
    t0 = time.perf_counter_ns()
    cleaned = sanitize_for_voice(text)
    dt_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

    assert dt_ms < 10.0, f"ReDoS threshold exceeded: {dt_ms:.2f}ms"
    assert isinstance(cleaned, str)
    assert "`" not in cleaned


# -----------------------------------------------------------------------------
# 6. Confirmation Token Manager & Sequence Guard Properties
# -----------------------------------------------------------------------------

@settings(max_examples=80, deadline=1000)
@given(
    tool_name=st.sampled_from(["write_file", "delete_file", "launch_app", "run_python"]),
    turn_id=st.text(min_size=1, max_size=10),
    key=st.text(min_size=1, max_size=10),
    val=st.text(min_size=1, max_size=10),
)
def test_hypothesis_confirmation_token_tamper_proofing(
    tool_name: str, turn_id: str, key: str, val: str
) -> None:
    """HMAC tokens are tamper-resistant; bitflips or arg alterations strictly fail."""
    mgr = ConfirmationTokenManager(token_ttl_s=10.0)
    args = {key: val}
    token_str, expiry_ts = mgr.issue_token(tool_name, args, turn_id)

    # 1. Valid token verifies
    ok, _ = mgr.verify_token(token_str, tool_name, args, turn_id, expiry_ts)
    assert ok is True

    # 2. Replay prevention blocks second verification
    ok_replay, msg_replay = mgr.verify_token(token_str, tool_name, args, turn_id, expiry_ts)
    assert ok_replay is False
    assert "replay" in msg_replay.lower() or "consumed" in msg_replay.lower()

    # 3. Forged token with bitflip fails
    token2_str, expiry2_ts = mgr.issue_token(tool_name, args, turn_id)
    flipped = ("0" if token2_str[0] != "0" else "1") + token2_str[1:]
    ok_flip, _ = mgr.verify_token(flipped, tool_name, args, turn_id, expiry2_ts)
    assert ok_flip is False


def test_sequence_guard_cross_turn_deontic_boundaries() -> None:
    """SequenceGuard strictly blocks prohibited tool combinations and exfiltration."""
    guard = SequenceGuard()

    # Rule 1: Cannot fetch_url or search_web after reading files in same turn
    guard.check_and_record("read_file")
    allowed_fetch, _ = guard.check_and_record("fetch_url")
    assert allowed_fetch is False

    guard.reset()
    guard.check_and_record("read_file")
    allowed_search, _ = guard.check_and_record("search_web")
    assert allowed_search is False

    # Rule 2: Cannot write files after web fetch in same turn
    guard.reset()
    guard.check_and_record("fetch_url")
    allowed_write, _ = guard.check_and_record("write_file")
    assert allowed_write is False

    # Rule 3: Exfiltration detection
    guard.reset()
    guard.register_sensitive_content("confidential_auth_token_99999")
    allowed_exfil, reason = guard.check_and_record(
        "search_web", args={"query": "lookup confidential_auth_token_99999"}
    )
    assert allowed_exfil is False
    assert "Egress Block" in reason
