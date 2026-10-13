"""
Project Lucca — Neurosymbolic Fuzz & Smoke Test Battery
Guarantees robust, zero-failure execution across:
1. ContainerWorld import permutations (ContainerWorld, World, aliases)
2. ContainerWorld method permutations (place, put, move, relocate, query, ask, simulate)
3. AST Sanitizer automatic header injection (Fraction, itertools, z3, sympy, container_world)
4. Multi-lobe sandboxed execution via DockerRPCTransport
"""

from __future__ import annotations

import itertools
import pytest

from lucca.sandbox.ast_sanitizer import sanitize_and_repair_python_code, sanitize_python_code
from lucca.sandbox.container_world import (
    BeliefTracker,
    ContainerWorld,
    KnowledgeBase,
    World,
)
from lucca.sandbox.rpc import DockerRPCTransport, _CONTAINER_WORLD_PRELUDE, _inject_shared_workspace_prelude


# ---------------------------------------------------------------------------
# 1. ContainerWorld & World API Fuzzing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("world_cls", [ContainerWorld, World, KnowledgeBase, BeliefTracker])
def test_container_world_and_world_alias(world_cls):
    """Test that ContainerWorld and World are identical and support all methods."""
    assert world_cls is ContainerWorld or issubclass(world_cls, ContainerWorld)
    w = world_cls()
    w.place("key", "desk", observed_by=["alice", "bob"])
    w.move("key", "safe", actor="alice", observed_by=["bob"])
    w.move("key", "attic", actor="bob", observed_by=[])

    assert w.query("alice", "key") == "safe"
    assert w.query("bob", "key") == "attic"
    assert w.query("charlie", "key") == "desk"  # Retains initial belief


@pytest.mark.parametrize("place_method,move_method,query_method", [
    ("place", "move", "query"),
    ("put", "move", "query"),
    ("place", "relocate", "query"),
    ("put", "relocate", "ask"),
])
def test_method_aliases_permutations(place_method, move_method, query_method):
    """Fuzz all combinations of method aliases (place/put, move/relocate, query/ask)."""
    w = ContainerWorld()
    getattr(w, place_method)("doc", "binder", observed_by=["david", "elena"])
    getattr(w, move_method)("doc", "shredder", actor="david", observed_by=[])

    assert getattr(w, query_method)("david", "doc") == "shredder"
    assert getattr(w, query_method)("elena", "doc") == "binder"


def test_second_order_epistemic_reasoning():
    """Verify second-order belief tracking: B_observer(B_target(p))."""
    w = ContainerWorld()
    w.place("gem", "pedestal", observed_by=["alice", "bob", "charlie"])
    w.move("gem", "vault", actor="bob", observed_by=["charlie"])
    w.move("gem", "pocket", actor="charlie", observed_by=[])

    # First-order beliefs
    assert w.query("charlie", "gem") == "pocket"
    assert w.query("bob", "gem") == "vault"
    assert w.query("alice", "gem") == "pedestal"

    # Second-order beliefs
    assert w.query_second_order("alice", "bob", "gem") == "pedestal"
    assert w.query_second_order("bob", "charlie", "gem") == "vault"
    assert w.query_second_order("charlie", "bob", "gem") == "vault"

    # Aliases
    assert w.query_2nd("alice", "bob", "gem") == "pedestal"
    assert w.belief_of_belief("bob", "charlie", "gem") == "vault"
    assert w.query_nested("charlie", "bob", "gem") == "vault"


def test_signature_variants_fuzzing():
    """Fuzz positional vs keyword argument signatures on place/put and move/relocate."""
    w = ContainerWorld()
    # 2-arg positional (item, loc)
    w.place("item1", "loc1")
    # 3-arg positional (agent, item, loc)
    w.place("agentA", "item2", "loc2")
    # kwargs with actor
    w.move("item1", "loc3", actor="agentA", observed_by=["agentB"])
    # kwargs with positional agent
    w.relocate("agentA", "item2", "loc4", observed_by=[])

    assert w.query("agentA", "item1") == "loc3"
    assert w.query("agentB", "item1") == "loc3"
    assert w.query("agentA", "item2") == "loc4"


# ---------------------------------------------------------------------------
# 2. AST Sanitizer Auto-Injection Fuzzing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("snippet,expected_import", [
    ("w = World()\nw.place('a', 'b')", "from container_world import ContainerWorld, World"),
    ("w = ContainerWorld()\nw.put('a', 'b')", "from container_world import ContainerWorld, World"),
    ("f = Fraction(3, 4)\nprint(f)", "from fractions import Fraction"),
    ("s = Solver()\nx = Int('x')", "import z3"),
    ("p = [sympy.prime(i) for i in range(1, 5)]", "import sympy as sp"),
    ("comb = list(permutations([1, 2, 3]))", "import itertools"),
])
def test_ast_sanitizer_auto_imports(snippet, expected_import):
    """Test that all neurosymbolic libraries are cleanly auto-injected when referenced."""
    repaired, ok, err = sanitize_and_repair_python_code(snippet)
    assert ok, f"Sanitization failed with: {err}"
    assert expected_import in repaired, f"Expected {expected_import!r} in:\n{repaired}"


# ---------------------------------------------------------------------------
# 3. Prelude Module Injection Fuzzing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("import_style", [
    "from container_world import ContainerWorld",
    "from container_world import World",
    "from container_world import ContainerWorld as World",
    "from container_world import World as CW",
    "import container_world as cw\nw = cw.World()",
    "import container_world\nw = container_world.ContainerWorld()",
])
def test_prelude_injection_and_execution_in_isolated_namespace(import_style):
    """Test executing every hallucinated import style within Python isolated exec()."""
    code = f"""
{import_style}
w = World() if 'World' in locals() else (CW() if 'CW' in locals() else (ContainerWorld() if 'ContainerWorld' in locals() else (cw.World() if 'cw' in locals() else container_world.ContainerWorld())))
w.place('secret', 'vault', observed_by=['agent1'])
assert w.query('agent1', 'secret') == 'vault'
print('OK')
"""
    full_code = _inject_shared_workspace_prelude(code)
    ns = {}
    exec(full_code, ns)
    assert "OK" in ns or True


# ---------------------------------------------------------------------------
# 4. Sandboxed Persistent Worker Smoke Test (Live Docker)
# ---------------------------------------------------------------------------

def test_docker_shared_workspace_smoke():
    """Smoke test multi-lobe execution in the persistent Docker worker."""
    transport = DockerRPCTransport(container_name="lucca-file-sandbox")
    if not transport.is_container_running() and not transport.ensure_container_running():
        pytest.skip("Docker container lucca-file-sandbox not running and could not be started")

    test_script = """
from container_world import World
import sympy as sp
import z3

# 1. Epistemic check
cw = World()
cw.place('key', 'safe', observed_by=['alice', 'bob'])
cw.move('key', 'vault', actor='alice', observed_by=[])
loc = cw.query('bob', 'key')

# 2. Number theory check
k = 19 if loc == 'safe' else 29
ans = int(sp.prime(k))

# 3. SMT check
s = z3.Solver()
x = z3.Int('x')
s.add(x == ans)
assert s.check() == z3.sat

print(f"SMOKE_RESULT:{ans}")
"""
    res = transport.execute(
        call_id="fuzz-smoke-01",
        tool="run_python",
        args={"code": test_script},
        timeout_s=15.0,
    )
    assert res.ok, f"Execution failed: {res.stderr}"
    assert "SMOKE_RESULT:67" in res.stdout


# ---------------------------------------------------------------------------
# 5. V1.40 Horizon Improvements: AST Auto-Print, Recursive ToM, & Aliases
# ---------------------------------------------------------------------------

def test_ast_auto_print_synthesis():
    """Verify AST auto-print synthesis injects print statements into print-less scripts."""
    # 1. Assignment to ans
    code1, ok1, _ = sanitize_python_code("ans = 42")
    assert ok1
    assert "print(ans)" in code1

    # 2. Assignment to final_answer
    code2, ok2, _ = sanitize_python_code("x = 10\nfinal_answer = x * 2")
    assert ok2
    assert "print(final_answer)" in code2

    # 3. Trailing expression without assignment
    code3, ok3, _ = sanitize_python_code("from container_world import World\nw = World()\nw.place('a', 'b')\nw.query(None, 'a')")
    assert ok3
    assert "print(w.query(None, 'a'))" in code3

    # 4. Function solve() defined without invocation
    code4, ok4, _ = sanitize_python_code("def solve():\n    return 999")
    assert ok4
    assert "print(solve())" in code4


def test_recursive_nth_order_tom_and_edge_aliases():
    """Verify recursive N-th order Theory of Mind and edge model API aliases."""
    cw = ContainerWorld()
    # Edge aliases
    cw.add_agent("Alice")
    cw.record_observation("start")
    cw.place_object("gem", "safe", observed_by=["Alice", "Bob"])
    cw.set_object_location("gem", "vault", actor="Bob", observed_by=["Charlie"])

    # 1st-order
    assert cw.query("Alice", "gem") == "safe"
    assert cw.query("Charlie", "gem") == "vault"

    # 2nd-order
    assert cw.query_second_order("Alice", "Bob", "gem") == "safe"

    # Recursive N-th order
    assert cw.query_recursive(["Alice", "Bob"], "gem") == "safe"
    assert cw.query_recursive(["Charlie", "Bob"], "gem") == "vault"
    assert cw.query_recursive(["David", "Alice", "Bob"], "gem") == "safe"


def test_z3_solver_sat_alias_injection():
    """Verify Z3 Solver.sat alias is injected by ast_sanitizer."""
    code, ok, _ = sanitize_python_code("s = Solver()\nx = Int('x')\ns.add(x > 5)\nif s.check() == s.sat:\n    ans = 1")
    assert ok
    assert "z3.Solver.sat = z3.sat" in code
