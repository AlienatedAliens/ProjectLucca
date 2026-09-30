from __future__ import annotations

import pytest

from lucca.sandbox.ast_sanitizer import (
    extract_python_code_tolerant,
    sanitize_and_repair_python_code,
)


def test_fenced_code_extraction() -> None:
    text = """Here is the solution:
```python
import math
ans = math.factorial(5)
print(ans)
```
Hope that helps!"""
    code, stage = extract_python_code_tolerant(text)
    assert stage == "fenced"
    assert "ans = math.factorial(5)" in code
    assert "print(ans)" in code


def test_unfenced_code_extraction() -> None:
    text = """
import sympy as sp
x = sp.Symbol('x')
eq = sp.Eq(x**2, 25)
sol = sp.solve(eq, x)
print(sol)
"""
    code, stage = extract_python_code_tolerant(text)
    assert stage in ("unfenced", "longest_ast_slice")
    assert "import sympy as sp" in code
    assert "print(sol)" in code


def test_longest_ast_slice_extraction() -> None:
    text = """
To find the area of the right-angled triangle with base 4 and height 3:
We can write a simple Python calculation:

base = 4
height = 3
area = 0.5 * base * height
print(int(area))

Therefore, the calculated area is 6 square units.
"""
    code, stage = extract_python_code_tolerant(text)
    assert stage in ("longest_ast_slice", "unfenced")
    assert "base = 4" in code
    assert "area = 0.5 * base * height" in code
    assert "print(int(area))" in code
    assert "Therefore, the calculated area" not in code
    assert "To find the area" not in code


def test_preserve_string_literals_and_comments() -> None:
    """Critical Phase 1 Gate: Strings and comments must NEVER be corrupted by operator repair."""
    code = """
s1 = "^"
s2 = "2x^2 + 5x"
s3 = "x*y should stay x*y"
# Comment with caret: x^2 and implicit: 2x
print(s1, s2, s3)
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert '"^"' in repaired
    assert '"2x^2 + 5x"' in repaired
    assert '"x*y should stay x*y"' in repaired
    assert "# Comment with caret: x^2 and implicit: 2x" in repaired


def test_caret_and_implicit_mult_in_code() -> None:
    code = """
import sympy as sp
x = sp.Symbol('x')
expr = 2x^2 + 5x - 3
prod = 3(x + 1)
ans = expr.subs(x, 1) + prod.subs(x, 1)
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    # Caret must become **
    assert "**" in repaired
    # Implicit multiplication must have * inserted
    assert "2 *x" in repaired or "2*x" in repaired or "2 * x" in repaired
    assert "3 *(" in repaired or "3*(" in repaired or "3 * (" in repaired
    assert "print(ans)" in repaired


def test_unclosed_parenthesis_and_brackets() -> None:
    code = """
import math
ans = math.sqrt(144
arr = [1, 2, 3
d = {"a": 1
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "print(ans)" in repaired


def test_missing_sympy_and_math_import() -> None:
    code = """
x = symbols('x')
res = solve(x**2 - 16, x)
root = sqrt(25)
print(res, root)
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "import sympy as sp" in repaired
    assert "import math" in repaired


def test_missing_print_injection() -> None:
    code = """
def solve():
    return 42 * 2
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "print(_res)" in repaired or "print(solve())" in repaired


def test_empty_extraction_returns_empty_stage() -> None:
    prose = "I do not have enough information to solve this problem mathematically."
    code, stage = extract_python_code_tolerant(prose)
    assert stage == "empty"
    assert code == ""
