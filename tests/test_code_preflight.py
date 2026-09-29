"""
Unit and integration tests for WO-26 Phase 4:
The Autonomous "Run-Before-You-Speak" Code Verification Loop & Batched Prompt Contract.

Tests:
1. Assertion extraction across doctest, inline equality, arrow notations, and explicit asserts.
2. AST syntax gate and Docker preflight execution.
3. 3.0s timeout with fail-open behavior.
4. 1-Shot self-repair loop on assertion discrepancy.
5. Remediated 7 HumanEval tasks (32, 101, 103, 115, 116, 132, 145) + 7 sibling tasks.
6. Preflight On vs. Off ablation.
"""

import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lucca.core.orchestrator import Orchestrator
from lucca.core.schemas import TokenDelta, TurnTrace
from lucca.core.turn_pipeline import is_code_synthesis_request
from lucca.sandbox.preflight import (
    build_preflight_runner_code,
    extract_docstring_assertions,
    extract_python_code,
)
from lucca.sandbox.schemas import PreflightResult
from lucca.sandbox.service import SandboxService


# ===========================================================================
# 1. Assertion Extraction Suite
# ===========================================================================


def test_extract_doctest_assertions() -> None:
    code = """
def separate_paren_groups(paren_string: str) -> list[str]:
    '''
    >>> separate_paren_groups('( ) (( )) (( )( ))')
    ['()', '(())', '(()())']
    >>> 2 + 2 == 4
    True
    '''
    return []
"""
    assertions = extract_docstring_assertions(code)
    assert len(assertions) == 2
    assert "assert (separate_paren_groups('( ) (( )) (( )( ))')) == (['()', '(())', '(()())'])" in assertions
    assert "assert (2 + 2 == 4) is True" in assertions


def test_extract_inline_equalities_and_arrows() -> None:
    code = """
def words_string(s):
    '''
    words_string("Hi, my name is John") == ["Hi", "my", "name", "is", "John"]
    words_string("One, two, three, four, five, six") == ["One", "two", "three", "four", "five", "six"]
    '''
    pass

def rounded_avg(n, m):
    '''
    rounded_avg(1, 5) => "0b11"
    rounded_avg(7, 5) => -1
    '''
    pass

def is_nested(string):
    '''
    is_nested('[[]]') ➞ True
    is_nested('[]]]]]]][[[[[]') ➞ False
    '''
    pass
"""
    assertions = extract_docstring_assertions(code)
    assert 'assert (words_string("Hi, my name is John")) == (["Hi", "my", "name", "is", "John"])' in assertions
    assert 'assert (words_string("One, two, three, four, five, six")) == (["One", "two", "three", "four", "five", "six"])' in assertions
    assert 'assert (rounded_avg(1, 5)) == ("0b11")' in assertions
    assert 'assert (rounded_avg(7, 5)) == (-1)' in assertions
    assert "assert (is_nested('[[]]')) is True" in assertions
    assert "assert (is_nested('[]]]]]]][[[[[]')) is False" in assertions


def test_extract_explicit_assert_and_prompt_examples() -> None:
    code = "def add(a, b): return a + b"
    prompt_examples = [
        "add(1, 2) == 3",
        "assert add(0, 0) == 0",
        ">>> add(-1, 1)\n0",
    ]
    assertions = extract_docstring_assertions(code, docstring_examples=prompt_examples)
    assert len(assertions) == 3
    assert "assert (add(1, 2)) == (3)" in assertions
    assert "assert add(0, 0) == 0" in assertions
    assert "assert (add(-1, 1)) == (0)" in assertions


def test_is_code_synthesis_request_gate() -> None:
    assert is_code_synthesis_request("def words_string(s):") is True
    assert is_code_synthesis_request("import math\ndef find_zero(xs):") is True
    assert is_code_synthesis_request("Write a python function to compute factorial") is True
    assert is_code_synthesis_request("Complete the following Python function:") is True
    assert is_code_synthesis_request("Hello, what is the weather like?") is False
    assert is_code_synthesis_request("Where is Perth located?") is False


# ===========================================================================
# 2. Docker Preflight Execution & Fail-Open Behavior
# ===========================================================================


@pytest.fixture
def docker_sandbox(tmp_path: Path) -> SandboxService:
    srv = SandboxService(
        workspace_root=tmp_path / "workspace",
        notes_dir=tmp_path / "notes",
        use_direct_fallback=False,
    )
    yield srv
    srv.close()


def test_preflight_syntax_error_fast_rejection(docker_sandbox: SandboxService) -> None:
    broken_syntax = "def bad_func(:\n    return 42"
    res = docker_sandbox.preflight_verify_code(broken_syntax)
    assert res.success is False
    assert res.fail_open is False
    assert "SyntaxError" in (res.error_msg or "")
    assert res.assertions_run == 0


def test_preflight_passing_code_in_docker(docker_sandbox: SandboxService) -> None:
    code = """
def double_val(x):
    '''>>> double_val(5)\n10'''
    return x * 2
"""
    res = docker_sandbox.preflight_verify_code(code)
    assert res.success is True
    assert res.fail_open is False
    assert res.error_msg is None
    assert res.assertions_run == 1


def test_preflight_failing_code_assertion_reporting(docker_sandbox: SandboxService) -> None:
    flawed_code = r"""
def words_string(s):
    '''
    words_string("One, two, three, four, five, six,") == ["One", "two", "three", "four", "five", "six"]
    '''
    import re
    return re.split(r'[,\s]+', s.strip()) if s.strip() else []
"""
    res = docker_sandbox.preflight_verify_code(flawed_code)
    assert res.success is False
    assert res.fail_open is False
    assert "AssertionError" in (res.error_msg or "")
    assert "Got:" in (res.error_msg or "")
    assert "Expected:" in (res.error_msg or "")


def test_preflight_timeout_fail_open(docker_sandbox: SandboxService) -> None:
    infinite_loop = """
def freeze():
    '''>>> freeze() == 1'''
    import time
    while True:
        time.sleep(0.1)
    return 1
"""
    res = docker_sandbox.preflight_verify_code(infinite_loop, timeout_s=1.0)
    # Fail-open requirement: 3.0s timeout returns success=True with warning rather than hanging
    assert res.success is True
    assert res.fail_open is True
    assert "preflight_timeout" in (res.error_msg or "")


# ===========================================================================
# 3. 1-Shot Self-Repair Loop
# ===========================================================================


def test_one_shot_self_repair_loop(docker_sandbox: SandboxService) -> None:
    # 1. Initial flawed candidate (trailing comma bug from HumanEval/101 audit)
    flawed_candidate = r"""
def words_string(s):
    '''
    words_string("One, two, three, four, five, six,") == ["One", "two", "three", "four", "five", "six"]
    '''
    import re
    return re.split(r'[,\s]+', s.strip()) if s.strip() else []
"""
    initial_check = docker_sandbox.preflight_verify_code(flawed_candidate)
    assert initial_check.success is False

    # 2. Simulated model repair turn receiving preflight error details
    repaired_candidate = r"""
def words_string(s):
    '''
    words_string("One, two, three, four, five, six,") == ["One", "two", "three", "four", "five", "six"]
    '''
    import re
    return [w for w in re.split(r'[,\s]+', s.strip()) if w]
"""
    repaired_check = docker_sandbox.preflight_verify_code(repaired_candidate)
    assert repaired_check.success is True
    assert repaired_check.error_msg is None


# ===========================================================================
# 4. The 7 Remediated HumanEval Tasks & 7 Sibling Tasks in Docker
# ===========================================================================


def test_humaneval_32_find_zero_and_sibling(docker_sandbox: SandboxService) -> None:
    # Task 32: Polynomial root-finding via robust scipy.optimize.bisect
    code_32 = """
import math
import scipy.optimize

def poly(xs: list, x: float):
    return sum([coeff * math.pow(x, i) for i, coeff in enumerate(xs)])

def find_zero(xs: list):
    '''
    >>> round(find_zero([1, 2]), 2)
    -0.5
    >>> round(find_zero([-6, 11, -6, 1]), 2)
    1.0
    '''
    f = lambda x: poly(xs, x)
    # Search for sign change in expanding brackets
    bracket = 1.0
    while f(-bracket) * f(bracket) > 0 and bracket < 1e5:
        bracket *= 2.0
    if f(-bracket) * f(bracket) <= 0:
        return scipy.optimize.bisect(f, -bracket, bracket)
    return 0.0
"""
    res_32 = docker_sandbox.preflight_verify_code(code_32)
    assert res_32.success is True

    # Sibling 32: Cubic polynomial root-finding
    code_32_sibling = """
import scipy.optimize

def find_zero_cubic(a, b, c, d):
    '''
    >>> round(find_zero_cubic(1, -6, 11, -6), 2)
    1.0
    '''
    f = lambda x: a * (x**3) + b * (x**2) + c * x + d
    return scipy.optimize.bisect(f, 0.0, 1.5)
"""
    res_sibling = docker_sandbox.preflight_verify_code(code_32_sibling)
    assert res_sibling.success is True


def test_humaneval_101_words_string_and_sibling(docker_sandbox: SandboxService) -> None:
    # Task 101: Trailing comma handling
    code_101 = r"""
def words_string(s):
    '''
    words_string("Hi, my name is John") == ["Hi", "my", "name", "is", "John"]
    words_string("One, two, three, four, five, six,") == ["One", "two", "three", "four", "five", "six"]
    '''
    import re
    return [w for w in re.split(r'[,\s]+', s.strip()) if w]
"""
    res_101 = docker_sandbox.preflight_verify_code(code_101)
    assert res_101.success is True

    # Sibling 101: Semicolon and space tag parser with trailing separator
    code_101_sibling = r"""
def split_tags(s):
    '''
    split_tags("python; rust; go;") == ["python", "rust", "go"]
    split_tags(";alpha; beta ;") == ["alpha", "beta"]
    '''
    import re
    return [t for t in re.split(r'[;\s]+', s.strip()) if t]
"""
    res_sibling = docker_sandbox.preflight_verify_code(code_101_sibling)
    assert res_sibling.success is True


def test_humaneval_103_rounded_avg_and_sibling(docker_sandbox: SandboxService) -> None:
    # Task 103: Round-to-nearest and binary formatting
    code_103 = """
def rounded_avg(n, m):
    '''
    rounded_avg(1, 5) => "0b11"
    rounded_avg(7, 5) => -1
    rounded_avg(10, 20) => "0b1111"
    rounded_avg(20, 33) => "0b11010"
    '''
    if n > m:
        return -1
    avg = (n + m) / 2.0
    return bin(round(avg))
"""
    res_103 = docker_sandbox.preflight_verify_code(code_103)
    assert res_103.success is True

    # Sibling 103: Hexadecimal rounded range sum
    code_103_sibling = """
def rounded_avg_hex(n, m):
    '''
    rounded_avg_hex(1, 5) => "0x3"
    rounded_avg_hex(10, 5) => -1
    rounded_avg_hex(15, 16) => "0x10"
    '''
    if n > m:
        return -1
    avg = (n + m) / 2.0
    return hex(round(avg))
"""
    res_sibling = docker_sandbox.preflight_verify_code(code_103_sibling)
    assert res_sibling.success is True


def test_humaneval_115_max_fill_and_sibling(docker_sandbox: SandboxService) -> None:
    # Task 115: Per-row bucket capacity ceiling division
    code_115 = """
import math

def max_fill(grid, capacity):
    '''
    max_fill([[0,0,1,0], [0,1,0,0], [1,1,1,1]], 1) == 6
    max_fill([[0,0,1,1], [0,0,0,0], [1,1,1,1], [0,1,1,1]], 2) == 5
    max_fill([[0,0,0], [0,0,0]], 5) == 0
    '''
    return sum(math.ceil(sum(row) / capacity) for row in grid)
"""
    res_115 = docker_sandbox.preflight_verify_code(code_115)
    assert res_115.success is True

    # Sibling 115: Mine cart trips per track
    code_115_sibling = """
import math

def mine_cart_trips(tracks, cart_capacity):
    '''
    mine_cart_trips([[2, 3], [0, 4]], 2) == 5
    mine_cart_trips([[0, 0], [0, 0]], 5) == 0
    '''
    return sum(math.ceil(sum(track) / cart_capacity) for track in tracks)
"""
    res_sibling = docker_sandbox.preflight_verify_code(code_115_sibling)
    assert res_sibling.success is True


def test_humaneval_116_sort_array_and_sibling(docker_sandbox: SandboxService) -> None:
    # Task 116: Sort array by number of 1-bits with decimal tie-breaking
    code_116 = """
def sort_array(arr):
    '''
    sort_array([1, 5, 2, 3, 4]) == [1, 2, 4, 3, 5]
    sort_array([-2, -3, -4, -5, -6]) == [-4, -2, -6, -5, -3]
    sort_array([1, 0, 2, 3, 4]) == [0, 1, 2, 4, 3]
    '''
    return sorted(arr, key=lambda x: (bin(x).count('1'), x))
"""
    res_116 = docker_sandbox.preflight_verify_code(code_116)
    assert res_116.success is True

    # Sibling 116: Sort by set bits in 16-bit word
    code_116_sibling = """
def sort_by_popcount(nums):
    '''
    sort_by_popcount([7, 3, 1, 0]) == [0, 1, 3, 7]
    sort_by_popcount([-1, -2]) == [-2, -1]
    '''
    def bits(x):
        return bin(x & 0xFFFF).count('1') if x < 0 else bin(x).count('1')
    return sorted(nums, key=lambda x: (bits(x), x))
"""
    res_sibling = docker_sandbox.preflight_verify_code(code_116_sibling)
    assert res_sibling.success is True


def test_humaneval_132_is_nested_and_sibling(docker_sandbox: SandboxService) -> None:
    # Task 132: Subsequence bracket nesting detection
    code_132 = """
def is_nested(string):
    '''
    is_nested('[[]]') ➞ True
    is_nested('[]]]]]]][[[[[]') ➞ False
    is_nested('[][]') ➞ False
    is_nested('[]') ➞ False
    is_nested('[[][]]') ➞ True
    is_nested('[[]][[') ➞ True
    '''
    opening_indices = []
    closing_indices = []
    for i, ch in enumerate(string):
        if ch == '[':
            opening_indices.append(i)
        elif ch == ']':
            closing_indices.append(i)
    closing_indices.reverse()
    count = 0
    i = 0
    l_open = len(opening_indices)
    for idx in closing_indices:
        if i < l_open and idx > opening_indices[i]:
            count += 1
            i += 1
    return count >= 2
"""
    res_132 = docker_sandbox.preflight_verify_code(code_132)
    assert res_132.success is True

    # Sibling 132: Parenthesis nested subsequence detection
    code_132_sibling = """
def is_nested_parens(s):
    '''
    is_nested_parens('(())') ➞ True
    is_nested_parens('()()') ➞ False
    is_nested_parens('()') ➞ False
    is_nested_parens('((()))') ➞ True
    '''
    opens = [i for i, c in enumerate(s) if c == '(']
    closes = [i for i, c in enumerate(s) if c == ')'][::-1]
    count = 0
    i = 0
    for idx in closes:
        if i < len(opens) and idx > opens[i]:
            count += 1
            i += 1
    return count >= 2
"""
    res_sibling = docker_sandbox.preflight_verify_code(code_132_sibling)
    assert res_sibling.success is True


def test_humaneval_145_order_by_points_and_sibling(docker_sandbox: SandboxService) -> None:
    # Task 145: Signed digit sum with stable tiebreaking
    code_145 = """
def order_by_points(nums):
    '''
    >>> order_by_points([1, 11, -1, -11, -12]) == [-1, -11, 1, -12, 11]
    >>> order_by_points([]) == []
    '''
    def digit_sum(n):
        s = str(n)
        if s.startswith('-'):
            digits = [-int(s[1])] + [int(d) for d in s[2:]]
        else:
            digits = [int(d) for d in s]
        return sum(digits)
    return sorted(nums, key=digit_sum)
"""
    res_145 = docker_sandbox.preflight_verify_code(code_145)
    assert res_145.success is True

    # Sibling 145: Signed digit balance sorting
    code_145_sibling = """
def order_by_digit_balance(nums):
    '''
    >>> order_by_digit_balance([-15, 15, -2, 2]) == [-2, 2, -15, 15]
    '''
    def weight(n):
        s = str(n)
        if s.startswith('-'):
            return -int(s[1]) + sum(int(d) for d in s[2:])
        return sum(int(d) for d in s)
    return sorted(nums, key=weight)
"""
    res_sibling = docker_sandbox.preflight_verify_code(code_145_sibling)
    assert res_sibling.success is True


# ===========================================================================
# 5. Preflight On vs. Off Ablation
# ===========================================================================


def test_preflight_on_off_ablation(docker_sandbox: SandboxService) -> None:
    """Ablation: Evaluates flawed raw implementations with Preflight OFF vs. ON."""
    flawed_tasks = [
        (
            "Task 101 (trailing comma)",
            r"""
def words_string(s):
    '''
    words_string("One, two, three, four, five, six,") == ["One", "two", "three", "four", "five", "six"]
    '''
    import re
    return re.split(r'[,\s]+', s.strip()) if s.strip() else []
""",
        ),
        (
            "Task 103 (floor int)",
            """
def rounded_avg(n, m):
    '''
    rounded_avg(1, 2) => "0b10"
    rounded_avg(7, 12) => "0b1010"
    '''
    return bin(int((n + m) / 2))
""",
        ),
        (
            "Task 116 (inf negative)",
            """
def sort_array(arr):
    '''
    sort_array([-2, -3, -4, -5, -6]) == [-4, -2, -6, -5, -3]
    '''
    return sorted(arr, key=lambda x: (bin(x).count('1') if x >= 0 else float('inf'), x))
""",
        ),
    ]

    # Preflight OFF: Raw implementations fail assertions
    off_failures = 0
    for name, code in flawed_tasks:
        res = docker_sandbox.preflight_verify_code(code)
        if not res.success:
            off_failures += 1
    assert off_failures == len(flawed_tasks), "All flawed implementations must be caught by preflight"

    # Preflight ON with self-repair: All 3 remediated versions pass
    fixed_tasks = [
        r"""
def words_string(s):
    '''
    words_string("One, two, three, four, five, six,") == ["One", "two", "three", "four", "five", "six"]
    '''
    import re
    return [w for w in re.split(r'[,\s]+', s.strip()) if w]
""",
        """
def rounded_avg(n, m):
    '''
    rounded_avg(1, 2) => "0b10"
    rounded_avg(7, 12) => "0b1010"
    '''
    return bin(round((n + m) / 2.0))
""",
        """
def sort_array(arr):
    '''
    sort_array([-2, -3, -4, -5, -6]) == [-4, -2, -6, -5, -3]
    '''
    return sorted(arr, key=lambda x: (bin(x).count('1'), x))
""",
    ]
    on_passes = sum(
        1 for code in fixed_tasks if docker_sandbox.preflight_verify_code(code).success
    )
    assert on_passes == len(fixed_tasks), "All repaired implementations must pass preflight"
