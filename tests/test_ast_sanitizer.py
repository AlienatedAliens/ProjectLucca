from lucca.sandbox.ast_sanitizer import sanitize_and_repair_python_code


def test_missing_print_function():
    code = """
def solve():
    return 100
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "print(solve())" in repaired or "print(_res)" in repaired


def test_missing_print_variable():
    code = """
a = 10
b = 20
ans = a + b
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "print(ans)" in repaired


def test_caret_and_implicit_mult():
    code = """
import sympy as sp
x = sp.Symbol('x')
expr = 2x^2 + 5x - 3
ans = expr.subs(x, 1)
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "2 *x" in repaired or "2*x" in repaired
    assert "print(ans)" in repaired


def test_unclosed_parenthesis():
    code = """
import math
ans = math.sqrt(144
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "print(ans)" in repaired


def test_missing_sympy_import():
    code = """
x = symbols('x')
res = solve(x**2 - 16, x)
print(res)
"""
    repaired, ok, err = sanitize_and_repair_python_code(code)
    assert ok, err
    assert "import sympy as sp" in repaired


if __name__ == "__main__":
    test_missing_print_function()
    test_missing_print_variable()
    test_caret_and_implicit_mult()
    test_unclosed_parenthesis()
    test_missing_sympy_import()
    print("All AST Sanitizer Tests PASSED successfully!")
