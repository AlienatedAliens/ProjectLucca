"""
Project Lucca  Unit Tests for Domain-Agnostic CEGIS AST Mutators
Verifies AST polarity inversion, mask inversion, and binary argument order mutations.
Strict Zero-Any typing enforced per D-AUD-01.
"""

from __future__ import annotations

import ast

from lucca.reasoning.cegis_unshackled import (
    UnshackledCEGISEngine,
    generate_ast_mutants,
)


def test_conditional_polarity_mutation() -> None:
    code = (
        "def transform(grid):\n"
        "    if is_inside:\n"
        "        return 1\n"
        "    return 0\n"
    )
    mutants = generate_ast_mutants(code)
    assert any("if not is_inside:" in m for m in mutants), "Expected negated conditional mutant"

    code_neg = (
        "def transform(grid):\n"
        "    if not is_inside:\n"
        "        return 1\n"
        "    return 0\n"
    )
    mutants_neg = generate_ast_mutants(code_neg)
    assert any("if is_inside:" in m for m in mutants_neg), "Expected un-negated conditional mutant"


def test_mask_inversion_mutation() -> None:
    code = (
        "def transform(grid):\n"
        "    out = np.copy(grid)\n"
        "    out[cavity_mask] = 0\n"
        "    return out\n"
    )
    mutants = generate_ast_mutants(code)
    assert any("out[~cavity_mask]" in m for m in mutants), "Expected inverted mask mutant"

    code_inv = (
        "def transform(grid):\n"
        "    out = np.copy(grid)\n"
        "    out[~cavity_mask] = 0\n"
        "    return out\n"
    )
    mutants_inv = generate_ast_mutants(code_inv)
    assert any("out[cavity_mask]" in m for m in mutants_inv), "Expected un-inverted mask mutant"


def test_binary_argument_swap() -> None:
    code = (
        "def transform(grid):\n"
        "    return in_cavity(a, b)\n"
    )
    mutants = generate_ast_mutants(code)
    assert any("in_cavity(b, a)" in m for m in mutants), "Expected swapped binary argument mutant"


def test_verify_or_mutate_repairs_polarity() -> None:
    """Tests that verify_or_mutate_candidate automatically repairs a polarity slip against train I/O."""
    train_pairs: list[dict[str, list[list[int]]]] = [
        {"input": [[1, 2], [3, 4]], "output": [[0, 2], [3, 4]]},
        {"input": [[1, 5], [6, 7]], "output": [[0, 5], [6, 7]]},
    ]

    # Candidate has an inverted condition: zeroes out when grid[0][0] != 1 (which fails)
    faulty_code = (
        "def transform(grid):\n"
        "    import numpy as np\n"
        "    out = np.array(grid)\n"
        "    if out[0, 0] != 1:\n"
        "        out[0, 0] = 0\n"
        "    return out.tolist()\n"
    )

    engine = UnshackledCEGISEngine()
    # verify_candidate directly should fail
    passed, count, _, _, _ = engine.verify_candidate(faulty_code, train_pairs)
    assert not passed
    assert count == 0

    # verify_or_mutate_candidate should auto-repair via AST polarity mutation
    repaired_code, all_passed, passed_count, _, _, _ = engine.verify_or_mutate_candidate(
        faulty_code, train_pairs
    )
    assert all_passed is True
    assert passed_count == 2
    assert "not" in repaired_code or "==" in repaired_code
