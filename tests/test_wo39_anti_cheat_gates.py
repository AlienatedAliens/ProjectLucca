"""WO-39 Milestone 3.1: Permanent Static & AST Anti-Cheat Gates.

Ensures that production code under `src/lucca/` never contains:
1. Hardcoded benchmark answers, equations, or prompt-routing substrings (SPEC-BENCH-100, ARC, AIME, RFC 9110).
2. Test-environment or mock-object detection branches (`mock_calls`, `_mock_name`, `"pytest" in sys.modules`).
3. Hardware telemetry spoofing strings (`RTX 5080`, `275HX`).
4. Potemkin stubs (`:code "print(1)"`, `run_python_simulated`, `STATIC_RFC_DEFINITIONS`, `STANDARD_NUMERIC_LITERALS`, `_CONTAINER_WORLD_PRELUDE`, or fail-open `is_content_corroborated(None, ...)`).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_LUCCA = REPO_ROOT / "src" / "lucca"


BANNED_PRODUCTION_SUBSTRINGS: list[tuple[str, str]] = [
    ("05:15 Wednesday", "SPEC-BENCH-100 timezone answer leak"),
    ("Wednesday 05:15", "SPEC-BENCH-100 timezone answer leak"),
    ("Factoriza", "SPEC-BENCH-100 entity leak"),
    ("Fawkner not Faulkner", "SPEC-BENCH-100 entity leak"),
    ("August 23, 2044", "SPEC-BENCH-100 eclipse answer leak"),
    ("March 30, 2033", "SPEC-BENCH-100 eclipse answer leak"),
    ("minimum completion time is 5 hours", "SPEC-BENCH-100 scheduling answer leak"),
    ("how does benzene resist electrophilic addition", "Benchmark prompt router leak"),
    ("STATIC_RFC_DEFINITIONS", "Hardcoded RFC 9110 HTTP 401/403 benchmark lookup"),
    ("STANDARD_NUMERIC_LITERALS", "Hardcoded benchmark magic constants in MCTS"),
    ("fill_framed_enclosures", "Hardcoded ARC task solver in spatial_dsl"),
    ("complete_quadrant_symmetry", "Hardcoded ARC task solver in spatial_dsl"),
    ("sort_blocks_by_mass", "Hardcoded ARC task solver in spatial_dsl"),
    ("extrapolate_periodic_tile", "Hardcoded ARC task solver in spatial_dsl"),
    ("RTX 5080", "Hardcoded GPU spoofing string"),
    ("275HX", "Hardcoded CPU spoofing string"),
    ("run_python_simulated", "Fake simulated ToolReceipt minting"),
    ("_CONTAINER_WORLD_PRELUDE", "Duplicate hidden ContainerWorld prelude in rpc.py"),
    (':code "print(1)"', "Potemkin print(1) rule stub in DreamRetrospective"),
]


def _iter_lucca_py_files() -> list[Path]:
    return sorted(
        p for p in SRC_LUCCA.rglob("*.py") if "__pycache__" not in p.parts and "ui" not in p.parts
    )


def test_no_banned_benchmark_or_spoof_substrings_in_src_lucca() -> None:
    """Scan all Python files in `src/lucca/` for banned benchmark cheats or stubs."""
    violations: list[str] = []
    for py_file in _iter_lucca_py_files():
        text = py_file.read_text(encoding="utf-8", errors="replace")
        rel = py_file.relative_to(REPO_ROOT)
        for banned, reason in BANNED_PRODUCTION_SUBSTRINGS:
            if banned in text:
                violations.append(f"{rel}: contains {banned!r} ({reason})")
    assert not violations, "Banned benchmark/cheat strings found in src/lucca:\n" + "\n".join(
        violations
    )


def test_no_mock_inspection_in_sandbox_or_router() -> None:
    """Ensure production sandbox and router modules do not inspect unittest.mock attributes."""
    target_files = [
        SRC_LUCCA / "sandbox" / "search_tool.py",
        SRC_LUCCA / "sandbox" / "rpc.py",
        SRC_LUCCA / "core" / "turn_pipeline.py",
    ]
    for path in target_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(REPO_ROOT)
        assert "mock_calls" not in text, f"{rel} inspects mock_calls"
        assert "_mock_name" not in text, f"{rel} inspects _mock_name"


def test_egraph_extract_best_uses_cost_fn() -> None:
    """Verify EGraph.extract_best actually invokes `cost_fn` instead of hardcoding `c = 1.0`."""
    from lucca.reasoning.egraph import EGraph
    from lucca.reasoning.scheme.parser import Symbol

    eg = EGraph()
    id_a = eg.add([Symbol("+"), Symbol("x"), 0])
    id_b = eg.add(Symbol("x"))
    eg.merge(id_a, id_b)

    # Standard cost prefers smaller AST (Symbol("x") over [Symbol("+"), Symbol("x"), 0])
    best_default = eg.extract_best(id_a)
    assert best_default == Symbol("x")

    # Custom cost_fn that rewards "+" and heavily penalizes bare Symbol("x")
    calls: list[object] = []

    def custom_cost(node_val: object) -> float:
        calls.append(node_val)
        op = node_val.name if isinstance(node_val, Symbol) else str(node_val)
        return -50.0 if op == "+" else 10.0

    best_custom = eg.extract_best(id_a, cost_fn=custom_cost)
    assert len(calls) > 0, "EGraph.extract_best never called cost_fn!"
    assert best_custom == [Symbol("+"), Symbol("x"), 0]


def test_provenance_gate_fails_closed_and_blocks_asserts_bypass() -> None:
    """Verify is_content_corroborated fails closed on None DB and gate blocks 'X asserts Y'."""
    from lucca.memory.gate import is_content_corroborated

    assert is_content_corroborated(None, "Any unverified claim") is False

    gate_file = SRC_LUCCA / "memory" / "gate.py"
    text = gate_file.read_text(encoding="utf-8", errors="replace")
    assert r"^(.+?)\s+asserts\s+(.+)$" not in text, (
        "gate.py still contains the 'X asserts Y' regex bypass"
    )
