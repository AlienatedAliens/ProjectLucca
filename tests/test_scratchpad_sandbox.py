"""
Project Lucca — Scratchpad Sandbox Isolation & Stress Suite
Spec 09, Spec 14, D-AUD-13, ADR-013, D-REAS-05
Verifies:
1. Physical sandbox container isolation (--network none, --read-only, unprivileged user).
2. Host isolation (no access to host drive C: or host environment).
3. Timeout enforcement on infinite loops or slow macros (<= 500ms budget).
4. Concrete counterexample discovery across mutated / poisoned macros.
5. Live container execution without host fallback.
"""

import time
import pytest

from lucca.core.scratchpad import MacroTestCase, ScratchpadFalsifier
from lucca.reasoning.scheme.macros import MacroDefinition
from lucca.reasoning.scheme.parser import Symbol, parse_expr
from lucca.sandbox.rpc import DockerRPCTransport


@pytest.fixture(scope="module")
def container_rpc() -> DockerRPCTransport:
    rpc = DockerRPCTransport(container_name="lucca-file-sandbox", use_direct_fallback=False)
    if not rpc.is_docker_available():
        pytest.skip("WSL2 / Docker is not available in this test environment")
    if not rpc.is_container_running():
        assert rpc.ensure_container_running(), "Failed to start lucca-file-sandbox container"
    # Warm up persistent worker
    rpc.execute(call_id="warmup-scratchpad", tool="run_python", args={"code": "1"})
    return rpc


def test_sandbox_network_none_confinement(container_rpc: DockerRPCTransport) -> None:
    """
    D-AUD-13 Invariant: The container sandbox has --network none.
    Socket creation and connect attempts must fail with Errno 101 (Network is unreachable).
    """
    net_probe_code = """
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    s.connect(('1.1.1.1', 80))
    print('CONNECTED')
except Exception as exc:
    print(f'BLOCKED:{type(exc).__name__}:{exc}')
"""
    res = container_rpc.execute(call_id="stress-net-1", tool="run_python", args={"code": net_probe_code})
    assert res.ok is True
    out_str = str(res.content)
    assert "BLOCKED" in out_str
    assert "Network is unreachable" in out_str or "101" in out_str
    assert "CONNECTED" not in out_str


def test_sandbox_read_only_root_confinement(container_rpc: DockerRPCTransport) -> None:
    """
    D-AUD-13 Invariant: Container root filesystem is strictly read-only.
    Attempts to write to system directories (/etc, /usr, /bin) must raise EROFS.
    """
    fs_probe_code = """
import os
try:
    with open('/usr/bin/malicious_binary', 'w') as f:
        f.write('payload')
    print('WROTE_SYSTEM')
except Exception as exc:
    print(f'BLOCKED:{type(exc).__name__}:{exc}')
"""
    res = container_rpc.execute(call_id="stress-ro-1", tool="run_python", args={"code": fs_probe_code})
    assert res.ok is True
    out_str = str(res.content)
    assert "BLOCKED" in out_str
    assert "Read-only file system" in out_str or "30" in out_str
    assert "WROTE_SYSTEM" not in out_str


def test_sandbox_host_isolation_enforced(container_rpc: DockerRPCTransport) -> None:
    """
    D-AUD-13 Invariant: Host Windows filesystem (C:\\, Windows system files)
    is completely inaccessible inside the sandbox container.
    """
    host_probe_code = """
import os
has_c = os.path.exists('C:\\\\Windows')
has_mnt_c = os.path.exists('/mnt/c/Windows')
print(f'HOST_ACCESSIBLE:{has_c or has_mnt_c}')
"""
    res = container_rpc.execute(call_id="stress-host-1", tool="run_python", args={"code": host_probe_code})
    assert res.ok is True
    assert "HOST_ACCESSIBLE:False" in str(res.content)


def test_scratchpad_infinite_loop_timeout_protection() -> None:
    """
    Verify that an infinite/cyclic macro or timeout expiration fails fast on the timeout budget (<= 500ms)
    and marks the candidate falsified without deadlocking the host.
    """
    # 1. Cyclic / self-referential macro expansion protection
    falsifier = ScratchpadFalsifier(timeout_ms=150.0, allow_in_process_fallback=True)
    cyclic_macro = MacroDefinition(
        name="cycle",
        params=["x"],
        body=[Symbol("cycle"), Symbol("x")],
    )
    cases = [
        MacroTestCase(inputs={"x": 1}, expected_output=1),
        MacroTestCase(inputs={"x": 2}, expected_output=2),
        MacroTestCase(inputs={"x": 3}, expected_output=3),
    ]

    t0 = time.perf_counter()
    outcome_cyclic = falsifier.falsify(cyclic_macro, cases)
    elapsed = (time.perf_counter() - t0) * 1000.0

    assert outcome_cyclic.passed is False
    assert outcome_cyclic.falsified is True
    assert elapsed < 500.0, f"Execution must fail fast under 500ms, took {elapsed:.2f}ms"
    assert "expansion" in (outcome_cyclic.failure_reason or "").lower()

    # 2. Strict timeout budget exceeded check
    strict_falsifier = ScratchpadFalsifier(timeout_ms=0.0001, allow_in_process_fallback=True)
    valid_macro = MacroDefinition(
        name="id-op",
        params=["x"],
        body=parse_expr("(+ x 0)"),
    )
    time.sleep(0.001)
    outcome_timeout = strict_falsifier.falsify(valid_macro, cases)
    assert outcome_timeout.passed is False
    assert outcome_timeout.falsified is True
    assert "timeout" in (outcome_timeout.failure_reason or "").lower()


def test_scratchpad_counterexample_catching_battery() -> None:
    """
    Tests falsifier precision across a diverse battery of mutated / faulty macros.
    Every faulty candidate must be caught and produce an explicit counterexample.
    """
    falsifier = ScratchpadFalsifier(allow_in_process_fallback=True)

    test_matrix = [
        # 1. Off-by-one arithmetic error
        (
            MacroDefinition(name="bad-inc", params=["x"], body=parse_expr("(+ x 2)")),
            [
                MacroTestCase(inputs={"x": 0}, expected_output=1),
                MacroTestCase(inputs={"x": 1}, expected_output=2),
                MacroTestCase(inputs={"x": 2}, expected_output=3),
            ],
            "Output mismatch",
        ),
        # 2. Inverted comparison
        (
            MacroDefinition(name="bad-gt", params=["x", "y"], body=parse_expr("(< x y)")),
            [
                MacroTestCase(inputs={"x": 10, "y": 5}, expected_output=True),
                MacroTestCase(inputs={"x": 20, "y": 2}, expected_output=True),
                MacroTestCase(inputs={"x": 3, "y": 1}, expected_output=True),
            ],
            "Output mismatch",
        ),
        # 3. Arithmetic division by zero crash
        (
            MacroDefinition(name="div-zero", params=["x"], body=parse_expr("(/ x 0)")),
            [
                MacroTestCase(inputs={"x": 10}, expected_output=1),
                MacroTestCase(inputs={"x": 20}, expected_output=2),
                MacroTestCase(inputs={"x": 30}, expected_output=3),
            ],
            "division by zero",
        ),
    ]

    for macro_def, cases, expected_err_substring in test_matrix:
        outcome = falsifier.falsify(macro_def, cases)
        assert outcome.passed is False, f"Mutant {macro_def.name} should have failed falsification"
        assert outcome.falsified is True
        assert outcome.counterexample is not None
        assert expected_err_substring.lower() in (outcome.failure_reason or "").lower()


def test_scratchpad_container_direct_execution(container_rpc: DockerRPCTransport) -> None:
    """
    Verifies live execution inside the container with allow_in_process_fallback=False.
    """
    falsifier = ScratchpadFalsifier(
        transport=container_rpc,
        timeout_ms=2000.0,
        allow_in_process_fallback=False,
    )

    # 1. Valid macro in container
    valid_macro = MacroDefinition(
        name="double-val",
        params=["n"],
        body=parse_expr("(* n 2)"),
    )
    valid_cases = [
        MacroTestCase(inputs={"n": 3}, expected_output=6),
        MacroTestCase(inputs={"n": 5}, expected_output=10),
        MacroTestCase(inputs={"n": 7}, expected_output=14),
    ]
    res_valid = falsifier.falsify(valid_macro, valid_cases)
    assert res_valid.passed is True
    assert res_valid.falsified is False
    assert res_valid.passed_cases == 3

    # 2. Poisoned macro in container
    bad_macro = MacroDefinition(
        name="poison-double",
        params=["n"],
        body=parse_expr("(* n 3)"),  # Triples instead of doubles
    )
    res_bad = falsifier.falsify(bad_macro, valid_cases)
    assert res_bad.passed is False
    assert res_bad.falsified is True
    assert res_bad.counterexample is not None
    assert "Output mismatch" in (res_bad.failure_reason or "")
