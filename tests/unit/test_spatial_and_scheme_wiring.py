"""
Unit tests for WO-43 Phase 3.5 Behavioral Organ Activation:
1. CEGIS restricted sandbox (`execute_unshackled_python`) exposes `arc_primitives`, `spatial_dsl`, `spatial_scheme`, `mereo`, and `realize_real`.
2. MicroScheme `build_env` / `evaluate_expr` resolves `math_primitives`, `universal_primitives`, `skills`, and `realize_real`.
3. `lucca.admin` exposes the `repl` CLI subcommand (`lucca.reasoning.repl_loop`).
"""

from __future__ import annotations

from lucca.admin import create_parser
from lucca.reasoning.cegis_sandbox import execute_unshackled_python
from lucca.reasoning.scheme.eval import build_env, evaluate_expr
from lucca.reasoning.scheme.parser import parse_expr


def test_cegis_sandbox_exposes_arc_primitives() -> None:
    """Verifies that execute_unshackled_python can call get_objects, rotate_90, and gravity_drop."""
    code = """
def transform(grid):
    objs = get_objects(grid)
    assert len(objs) >= 1
    dropped = gravity_drop(grid, direction="down")
    return rotate_90(dropped, clockwise=True, times=1)
"""
    grid_in = [[1, 0], [0, 0]]
    outcome = execute_unshackled_python(code, grid_in, timeout_s=4.0)
    assert outcome.success is True, f"Expected success, got {outcome.error_type}: {outcome.error_message}"
    # gravity_drop([[1, 0], [0, 0]], "down") -> [[0, 0], [1, 0]]
    # rotate_90([[0, 0], [1, 0]], clockwise=True) -> [[1, 0], [0, 0]]
    assert outcome.output_grid == [[1, 0], [0, 0]]


def test_cegis_sandbox_exposes_spatial_dsl_and_mereo() -> None:
    """Verifies that execute_unshackled_python can call analyze_symbolic_invariants, crop_grid, and mereo."""
    code = """
def transform(grid):
    inv = analyze_symbolic_invariants([{"input": grid, "output": grid}])
    assert inv is not None
    cropped = crop_grid(grid, 0, 0, 1, 1)
    assert not mereo.part_of(frozenset([(0, 0)]), frozenset([(1, 1)]))
    return cropped
"""
    grid_in = [[2, 3, 0], [4, 5, 0], [0, 0, 0]]
    outcome = execute_unshackled_python(code, grid_in, timeout_s=4.0)
    assert outcome.success is True, f"Expected success, got {outcome.error_type}: {outcome.error_message}"
    assert outcome.output_grid == [[2, 3], [4, 5]]



def test_scheme_evaluator_resolves_math_universal_skills_and_realize_real() -> None:
    """Verifies that build_env() and evaluate_expr() resolve math, universal, skills, and realize_real primitives."""
    env = build_env()
    for sym in (
        "simplify",
        "factor",
        "expand",
        "solve",
        "reverse",
        "union",
        "manhattan-dist",
        "point-in-interval?",
        "during-real?",
        "active-skill-limit",
    ):
        assert sym in env, f"Expected '{sym}' in build_env()"

    assert evaluate_expr(parse_expr("(reverse (list 1 2 3))")) == [3, 2, 1]
    assert evaluate_expr(parse_expr("(manhattan-dist (list 0 0) (list 3 4))")) == 7
    assert evaluate_expr(parse_expr("(point-in-interval? 5 (list 1 10))")) is True
    assert evaluate_expr(parse_expr("(during-real? (list 2 4) (list 1 10))")) is True
    assert int(evaluate_expr(parse_expr("(active-skill-limit)"))) > 0  # type: ignore[arg-type]


def test_admin_cli_exposes_repl_subcommand() -> None:
    """Verifies that lucca-admin parser registers the repl subcommand."""
    parser = create_parser()
    args = parser.parse_args(["repl", "--list-tasks", "--task", "CenterMinimal"])
    assert args.cmd == "repl"
    assert args.list_tasks is True
    assert args.task == "CenterMinimal"
