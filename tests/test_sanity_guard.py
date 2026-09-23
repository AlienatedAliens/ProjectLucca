"""
Unit tests for Pre-Narration Sanity-Check Guard (WO-13.1 / Fault Mode C).
Spec: docs/DECISIONS.md (D-META-01).
Verifies that corrupted, impossible, or inverted tool output scalars are
flagged before narration while benign outputs pass cleanly in < 200 microseconds.
Zero-Any invariant enforced.
"""

from __future__ import annotations

import time

from lucca.core.sanity_guard import SanityCheckGuard, SanityCheckResult


def test_sanity_guard_sub_200us_budget() -> None:
    """Verifies that the sanity check executes well within its 200 us budget."""
    guard = SanityCheckGuard()
    t0 = time.perf_counter_ns()
    res = guard.validate(
        tool_name="run_python",
        tool_args={"code": "print(348291 * 9281034)"},
        tool_output="3236823534",
        user_query="Compute 348291 times 9281034 using python.",
    )
    t_diff_us = (time.perf_counter_ns() - t0) / 1000.0
    assert t_diff_us < 500.0, f"Execution took {t_diff_us:.1f} us, expected sub-millisecond"
    assert res.elapsed_us < 200.0, f"Internal timer reported {res.elapsed_us:.1f} us >= 200 us"


def test_fault_c01_large_multiplication_under_order() -> None:
    """Probe C01: 348291 * 9281034 -> 3236823534 (3.2 billion vs 3.2 trillion)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="run_python",
        tool_args={"code": "print(348291 * 9281034)"},
        tool_output="3236823534",
        user_query="Compute 348291 times 9281034 using python.",
    )
    assert not res.is_valid
    assert res.violation_type == "ORDER_OF_MAGNITUDE_MISMATCH"
    assert res.directive is not None
    assert "order-of-magnitude" in res.directive.lower()


def test_fault_c02_speed_of_light_missing_orders() -> None:
    """Probe C02: speed of light in vacuum -> 29,979 m/s (missing factor of 10,000)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="search_web",
        tool_args={"query": "speed of light vacuum m/s"},
        tool_output="Speed of light in vacuum is exactly 29,979 meters per second.",
        user_query="Look up the speed of light in vacuum in meters per second.",
    )
    assert not res.is_valid
    assert res.violation_type == "PHYSICAL_CONSTANT_ANOMALY"
    assert res.directive is not None
    assert "speed of light" in res.directive.lower()


def test_fault_c03_negative_physical_distance() -> None:
    """Probe C03: Sydney to Melbourne -> -877.0 km (negative scalar distance)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="run_python",
        tool_args={"code": "calculate_distance('Sydney', 'Melbourne')"},
        tool_output="-877.0 km",
        user_query="Calculate the distance from Sydney to Melbourne in kilometers.",
    )
    assert not res.is_valid
    assert res.violation_type == "NEGATIVE_PHYSICAL_SCALAR"
    assert res.directive is not None
    assert "negative" in res.directive.lower()


def test_fault_c05_multiplication_inversion_division() -> None:
    """Probe C05: 100 / 4 -> 400 (multiplication slip on division)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="run_python",
        tool_args={"code": "print(100 / 4)"},
        tool_output="400",
        user_query="Calculate one fourth of 100.",
    )
    assert not res.is_valid
    assert res.violation_type == "ARITHMETIC_INVERSION_OR_MAGNITUDE"
    assert res.directive is not None
    assert "inversion" in res.directive.lower() or "discrepancy" in res.directive.lower()


def test_fault_c06_absolute_zero_sign_inversion() -> None:
    """Probe C06: 0 Kelvin -> +273.15 C (sign inversion on absolute zero)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="run_python",
        tool_args={"code": "print(0 - 273.15)"},
        tool_output="273.15 C",
        user_query="Convert zero Kelvin to degrees Celsius.",
    )
    assert not res.is_valid
    assert res.violation_type == "THERMODYNAMIC_LIMIT_VIOLATION"
    assert res.directive is not None
    assert "zero kelvin" in res.directive.lower()


def test_fault_c07_circle_area_decimal_slip() -> None:
    """Probe C07: circle radius 10 -> 31.4159 (multiplied by r instead of r^2)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="run_python",
        tool_args={"code": "import math; print(math.pi * 10**2)"},
        tool_output="31.4159",
        user_query="Compute the area of a circle with radius 10 using python.",
    )
    assert not res.is_valid
    assert res.violation_type == "ORDER_OF_MAGNITUDE_MISMATCH"
    assert res.directive is not None
    assert "circle area" in res.directive.lower()


def test_fault_c08_human_age_lifespan_breach() -> None:
    """Probe C08: Queen Elizabeth II -> 196 years old (exceeds biological limits)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="search_web",
        tool_args={"query": "Queen Elizabeth II age at death"},
        tool_output="Queen Elizabeth II passed away at the verified age of 196 years old.",
        user_query="How old was Queen Elizabeth II when she died?",
    )
    assert not res.is_valid
    assert res.violation_type == "BIOLOGICAL_LIMIT_VIOLATION"
    assert res.directive is not None
    assert "human age" in res.directive.lower()


def test_fault_c09_prime_number_logic_contradiction() -> None:
    """Probe C09: 17 is prime -> False (claims 17 is divisible by 3 and 5)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="run_python",
        tool_args={"code": "is_prime(17)"},
        tool_output="False (17 is divisible by 3)",
        user_query="Is 17 a prime number?",
    )
    assert not res.is_valid
    assert res.violation_type == "ARITHMETIC_LOGIC_CONTRADICTION"
    assert res.directive is not None
    assert "prime" in res.directive.lower()


def test_fault_c10_tokyo_population_scale_understated() -> None:
    """Probe C10: Tokyo population -> 14,000 residents (small town scale)."""
    guard = SanityCheckGuard()
    res = guard.validate(
        tool_name="search_web",
        tool_args={"query": "Tokyo population census"},
        tool_output="Tokyo has a recorded population of 14,000 residents.",
        user_query="What is the current population of Tokyo?",
    )
    assert not res.is_valid
    assert res.violation_type == "DEMOGRAPHIC_SCALE_ANOMALY"
    assert res.directive is not None
    assert "population scale" in res.directive.lower()


def test_benign_outputs_pass_cleanly() -> None:
    """Verifies that legitimate, correct outputs pass validation with is_valid=True."""
    guard = SanityCheckGuard()

    # 1. Correct arithmetic product
    res1: SanityCheckResult = guard.validate(
        tool_name="run_python",
        tool_args={"code": "print(348291 * 9281034)"},
        tool_output="3232500612894",
        user_query="Compute 348291 times 9281034 using python.",
    )
    assert res1.is_valid
    assert res1.directive is None

    # 2. Correct distance
    res2: SanityCheckResult = guard.validate(
        tool_name="run_python",
        tool_args={"code": "calculate_distance('Sydney', 'Melbourne')"},
        tool_output="877.0 km",
        user_query="Calculate the distance from Sydney to Melbourne in kilometers.",
    )
    assert res2.is_valid

    # 3. Correct speed of light
    res3: SanityCheckResult = guard.validate(
        tool_name="search_web",
        tool_args={"query": "speed of light vacuum m/s"},
        tool_output="299,792,458 m/s",
        user_query="Look up the speed of light in vacuum in meters per second.",
    )
    assert res3.is_valid

    # 4. Correct absolute zero
    res4: SanityCheckResult = guard.validate(
        tool_name="run_python",
        tool_args={"code": "print(0 - 273.15)"},
        tool_output="-273.15 C",
        user_query="Convert zero Kelvin to degrees Celsius.",
    )
    assert res4.is_valid

    # 5. Correct division
    res5: SanityCheckResult = guard.validate(
        tool_name="run_python",
        tool_args={"code": "print(100 / 4)"},
        tool_output="25.0",
        user_query="Calculate one fourth of 100.",
    )
    assert res5.is_valid

    # 6. Correct Tokyo population in millions
    res6: SanityCheckResult = guard.validate(
        tool_name="search_web",
        tool_args={"query": "Tokyo population census"},
        tool_output="Tokyo has an estimated population of approximately 14 million residents.",
        user_query="What is the current population of Tokyo?",
    )
    assert res6.is_valid
