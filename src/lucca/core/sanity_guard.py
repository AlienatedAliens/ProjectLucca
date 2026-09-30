"""
Pre-Narration Sanity-Check Guard (Fault Mode C Remediation).
Spec: docs/DECISIONS.md (D-META-01).
Evaluates tool outputs against physical, arithmetic, and order-of-magnitude boundaries
prior to LLM narration dispatch.
Zero-Any invariant enforced.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from typing import Final

# Known small primes for arithmetic contradiction checks
_SMALL_PRIMES: Final[set[int]] = {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47}

# Major megacities whose population must not be reported as a small town (< 500,000)
_MEGACITIES: Final[set[str]] = {
    "tokyo",
    "shanghai",
    "delhi",
    "beijing",
    "mumbai",
    "sao paulo",
    "mexico city",
    "cairo",
    "dhaka",
    "new york",
    "london",
    "paris",
    "los angeles",
    "seoul",
}


@dataclass(frozen=True)
class SanityCheckResult:
    """Outcome of pre-narration sanity validation."""

    is_valid: bool
    violation_type: str | None = None
    reason: str | None = None
    directive: str | None = None
    elapsed_us: float = 0.0


class SanityCheckGuard:
    """
    Sub-millisecond deterministic boundary validator.
    Inspects tool execution outputs before LLM narration to detect
    physical impossibilities, Fermi magnitude violations, and mathematical contradictions.
    """

    def validate(
        self,
        tool_name: str,
        tool_args: dict[str, object],
        tool_output: str,
        user_query: str = "",
    ) -> SanityCheckResult:
        """
        Validate tool output against physical, mathematical, and order-of-magnitude bounds.
        Executes strictly in < 200 microseconds.
        """
        t0 = time.perf_counter_ns()

        combined_context = f"{user_query} {tool_name} {tool_args}".lower()
        output_lower = tool_output.lower()

        # ---------------------------------------------------------------------
        # Check 1: Physical Positivity (Distance, Duration, Population, Count, Age)
        # ---------------------------------------------------------------------
        positivity_keywords = (
            "distance",
            "km",
            "kilometer",
            "mile",
            "duration",
            "elapsed",
            "seconds",
            "minutes",
            "hours",
            "population",
            "residents",
            "count",
            "headcount",
            "age",
            "years old",
            "radius",
            "area",
        )
        is_financial = any(w in combined_context for w in ("payoff", "profit", "loss", "return", "pnl", "balance", "net", "margin", "auction"))
        has_positivity_kw = not is_financial and any(
            re.search(r"\b" + re.escape(kw) + r"\b", combined_context) for kw in positivity_keywords
        )
        if has_positivity_kw:
            cleaned_output = re.sub(r"(?m)^\s*-\s+", "  ", tool_output)
            pattern = (
                r"(?<![a-zA-Z0-9_\-/:])-\s*(\d+(?:\.\d+)?)"
                r"(?:\s*(?:km|miles?|meters?|seconds?|mins?|hours?|residents?|people|years)\b|\b(?![a-zA-Z]))"
            )
            neg_match = re.search(pattern, cleaned_output)
            if neg_match:
                val = float(neg_match.group(1))
                if val > 0.0:
                    elapsed = (time.perf_counter_ns() - t0) / 1000.0
                    reason = f"Physical quantity must be non-negative, but got -{val}"
                    return SanityCheckResult(
                        is_valid=False,
                        violation_type="NEGATIVE_PHYSICAL_SCALAR",
                        reason=reason,
                        directive=(
                            f"[Sanity Warning: Tool output indicates an anomalous negative "
                            f"physical scalar ({reason}). Acknowledge the execution but state "
                            "transparently that a negative value is physically impossible and "
                            "appears anomalous or unverified.]"
                        ),
                        elapsed_us=elapsed,
                    )

        # ---------------------------------------------------------------------
        # Check 2: Absolute Zero & Thermodynamic Temperature Bounds
        # ---------------------------------------------------------------------
        is_temp_query = (
            "kelvin" in combined_context
            or "celsius" in combined_context
            or "temperature" in combined_context
        )
        if is_temp_query:
            is_abs_zero = (
                "0 kelvin" in combined_context
                or "zero kelvin" in combined_context
                or "absolute zero" in combined_context
            )
            if is_abs_zero:
                # 0 Kelvin is -273.15 C. If output gives positive 273.15 or temperature > 0 C:
                pos_c_match = re.search(
                    r"(?:^|[^\-])(273(?:\.15)?)\s*(?:c|degrees? c)?", output_lower
                )
                if pos_c_match and "-" not in tool_output:
                    elapsed = (time.perf_counter_ns() - t0) / 1000.0
                    reason = (
                        "Zero Kelvin corresponds to -273.15 C, but output gave positive +273.15 C"
                    )
                    return SanityCheckResult(
                        is_valid=False,
                        violation_type="THERMODYNAMIC_LIMIT_VIOLATION",
                        reason=reason,
                        directive=(
                            f"[Sanity Warning: Tool output exhibits a thermodynamic sign "
                            f"contradiction ({reason}). State transparently that zero Kelvin is "
                            "-273.15 C and the tool's positive sign is an anomaly.]"
                        ),
                        elapsed_us=elapsed,
                    )
            # General temperature cannot be below -273.15 C
            sub_abs_zero = re.search(r"-\s*(\d+(?:\.\d+)?)\s*(?:c|celsius)", output_lower)
            if sub_abs_zero:
                c_val = float(sub_abs_zero.group(1))
                if c_val > 273.15:
                    elapsed = (time.perf_counter_ns() - t0) / 1000.0
                    reason = f"Temperature -{c_val} C is below absolute zero (-273.15 C)"
                    return SanityCheckResult(
                        is_valid=False,
                        violation_type="PHYSICAL_LIMIT_VIOLATION",
                        reason=reason,
                        directive=(
                            "[Sanity Warning: Tool output violates the laws of physics "
                            f"({reason}). Acknowledge the execution but explicitly note that "
                            "temperature cannot fall below absolute zero.]"
                        ),
                        elapsed_us=elapsed,
                    )

        # ---------------------------------------------------------------------
        # Check 3: Speed of Light Relativistic Bound
        # ---------------------------------------------------------------------
        if "speed of light" in combined_context or "light in vacuum" in combined_context:
            sol_m_match = re.search(r"(\d[\d,]*)\s*(?:m/s|meters?\s*per\s*second)", output_lower)
            if sol_m_match:
                raw_digits = sol_m_match.group(1).replace(",", "")
                if raw_digits.isdigit():
                    num = float(raw_digits)
                    # Off by more than 1 order of magnitude (e.g. 29,979 m/s instead of ~3e8 m/s)
                    if num < 1.0e7 or num > 4.0e8:
                        elapsed = (time.perf_counter_ns() - t0) / 1000.0
                        reason = (
                            f"Speed of light in vacuum is ~3e8 m/s (~299,792,458 m/s), "
                            f"got {num:,.0f} m/s"
                        )
                        return SanityCheckResult(
                            is_valid=False,
                            violation_type="PHYSICAL_CONSTANT_ANOMALY",
                            reason=reason,
                            directive=(
                                "[Sanity Warning: Tool output for a physical constant is "
                                f"anomalous ({reason}). Acknowledge the tool output but note the "
                                "known canonical value and discrepancy.]"
                            ),
                            elapsed_us=elapsed,
                        )

        # ---------------------------------------------------------------------
        # Check 4: Biological Human Lifespan Bound
        # ---------------------------------------------------------------------
        if any(w in combined_context for w in ("age at death", "died at", "how old was", "age of")):
            age_match = re.search(r"(\d{2,3})\s*(?:years?\s*old|years?\s*of\s*age)", output_lower)
            if age_match:
                age_val = int(age_match.group(1))
                if age_val > 130:
                    elapsed = (time.perf_counter_ns() - t0) / 1000.0
                    reason = (
                        f"Reported age of {age_val} exceeds maximum verified human lifespan "
                        "(~122 years)"
                    )
                    return SanityCheckResult(
                        is_valid=False,
                        violation_type="BIOLOGICAL_LIMIT_VIOLATION",
                        reason=reason,
                        directive=(
                            f"[Sanity Warning: Tool output reports a human age ({age_val} years) "
                            "exceeding verified biological limits. Transparently highlight this "
                            "anomaly rather than asserting it.]"
                        ),
                        elapsed_us=elapsed,
                    )

        # ---------------------------------------------------------------------
        # Check 5: Megacity Population Scale Bound
        # ---------------------------------------------------------------------
        for city in _MEGACITIES:
            has_city = city in combined_context
            has_pop = "population" in combined_context or "residents" in combined_context
            if has_city and has_pop:
                pop_match = re.search(
                    r"(\d[\d,]*)\s*(?:residents|people|inhabitants|citizens)", output_lower
                )
                if pop_match:
                    pop_digits = pop_match.group(1).replace(",", "")
                    if pop_digits.isdigit():
                        pop_num = int(pop_digits)
                        if pop_num < 500_000 and "million" not in output_lower:
                            elapsed = (time.perf_counter_ns() - t0) / 1000.0
                            reason = (
                                f"Megacity {city.title()} population reported as {pop_num:,}, "
                                "orders of magnitude smaller than metropolitan scale"
                            )
                            return SanityCheckResult(
                                is_valid=False,
                                violation_type="DEMOGRAPHIC_SCALE_ANOMALY",
                                reason=reason,
                                directive=(
                                    f"[Sanity Warning: Tool output reports an anomalous population "
                                    f"scale ({reason}). Acknowledge the returned output but state "
                                    "transparently that this appears severely understated.]"
                                ),
                                elapsed_us=elapsed,
                            )

        # ---------------------------------------------------------------------
        # Check 6: Mathematical Modulo / Prime Logic Contradiction
        # ---------------------------------------------------------------------
        if "prime" in combined_context:
            for p in _SMALL_PRIMES:
                if str(p) in combined_context:
                    div_match = re.search(rf"{p}\s+is\s+divisible\s+by\s+(\d+)", output_lower)
                    if div_match:
                        divisor = int(div_match.group(1))
                        if divisor not in (1, p) and (p % divisor) != 0:
                            elapsed = (time.perf_counter_ns() - t0) / 1000.0
                            rem = p % divisor
                            reason = (
                                f"{p} is a prime number and not divisible by {divisor} "
                                f"({p} % {divisor} = {rem})"
                            )
                            return SanityCheckResult(
                                is_valid=False,
                                violation_type="ARITHMETIC_LOGIC_CONTRADICTION",
                                reason=reason,
                                directive=(
                                    f"[Sanity Warning: Tool output asserts a mathematical "
                                    f"contradiction ({reason}). State clearly that the "
                                    "mathematical claim in the tool result is incorrect.]"
                                ),
                                elapsed_us=elapsed,
                            )

        # ---------------------------------------------------------------------
        # Check 7: Fermi Order-of-Magnitude Bounds on Arithmetic
        # ---------------------------------------------------------------------
        code_str = str(tool_args.get("code") or tool_args.get("expr") or "")
        out_nums = re.findall(r"\b\d+(?:\.\d+)?\b", tool_output)

        # Check 7 applies strictly to single-scalar arithmetic evaluations (e.g. calc_math
        # or simple 1-2 line scripts). Multi-number outputs (coordinates, vectors, timestamps)
        # and multi-line scripts are exempted to prevent false-positive inversion warnings.
        # Furthermore, compound expressions containing exponents (^, **) or multiple arithmetic
        # operators are exempted because out_nums[0] does not reflect a simple A * B or A / B.
        num_code_lines = len([line for line in code_str.strip().splitlines() if line.strip()])
        is_scalar_calc = len(out_nums) == 1 and num_code_lines <= 2

        if is_scalar_calc:
            calc_target = f"{user_query} {code_str}"

            # 7a. Multiplication A * B:
            mult_match = re.search(r"(\d+(?:\.\d+)?)\s*[\*x×]\s*(\d+(?:\.\d+)?)", calc_target)
            if mult_match:
                # Do not Fermi-check multiplication if division or exponentiation dominates the expression
                if not (any(op in code_str for op in ("^", "**", "/"))):
                    a_val = float(mult_match.group(1))
                    b_val = float(mult_match.group(2))
                    if a_val > 10.0 and b_val > 10.0:
                        expected_log = math.log10(a_val) + math.log10(b_val)
                        try:
                            res_val = float(out_nums[0])
                            if res_val > 0.0:
                                res_log = math.log10(res_val)
                                # Discrepancy >= 1.5 orders of magnitude (e.g. >= ~30x off)
                                if abs(res_log - expected_log) >= 1.5:
                                    elapsed = (time.perf_counter_ns() - t0) / 1000.0
                                    reason = (
                                        f"Multiplication {a_val:,.0f} * {b_val:,.0f} has Fermi "
                                        f"magnitude ~10^{expected_log:.1f}, but tool returned "
                                        f"{res_val:,.0f} (~10^{res_log:.1f})"
                                    )
                                    return SanityCheckResult(
                                        is_valid=False,
                                        violation_type="ORDER_OF_MAGNITUDE_MISMATCH",
                                        reason=reason,
                                        directive=(
                                            f"[Sanity Warning: Tool output exhibits an "
                                            f"order-of-magnitude discrepancy ({reason}). Acknowledge "
                                            "the execution but state transparently that the result "
                                            "appears inconsistent with mathematical boundary checks.]"
                                        ),
                                        elapsed_us=elapsed,
                                    )
                        except (ValueError, OverflowError):
                            pass

            # 7b. Division A / B (e.g. 100 / 4 or one fourth of 100):
            div_match = re.search(r"(\d+(?:\.\d+)?)\s*[\/÷]\s*(\d+(?:\.\d+)?)", calc_target)
            if not div_match:
                frac_pattern = r"(?:one\s+fourth|1/4|quarter)\s+of\s+(\d+(?:\.\d+)?)"
                frac_match = re.search(frac_pattern, calc_target.lower())
                if frac_match:
                    div_match = re.search(
                        r"(\d+(?:\.\d+)?)\s*[\/÷]\s*(\d+(?:\.\d+)?)",
                        f"{frac_match.group(1)} / 4",
                    )

            if div_match:
                # Only check division inversion if the expression is primarily a division
                # (i.e. not nested inside exponential or compound formulas like A * B^(C/D))
                is_nested_div = any(op in code_str for op in ("^", "**")) or code_str.count("*") > 0
                if not is_nested_div:
                    a_val = float(div_match.group(1))
                    b_val = float(div_match.group(2))
                    if a_val > b_val > 1.0:
                        expected_div = a_val / b_val
                        try:
                            res_val = float(out_nums[0])
                            # Multiplied instead (res_val >= a_val) or inverted (res_val < 1.0)
                            if res_val >= a_val or (res_val < 1.0 and expected_div >= 1.0):
                                elapsed = (time.perf_counter_ns() - t0) / 1000.0
                                reason = (
                                    f"Division of {a_val:,.0f} by {b_val:,.0f} expected "
                                    f"~{expected_div:,.2f}, but tool returned {res_val:,.2f} "
                                    "(multiplication or inversion slip)"
                                )
                                return SanityCheckResult(
                                    is_valid=False,
                                    violation_type="ARITHMETIC_INVERSION_OR_MAGNITUDE",
                                    reason=reason,
                                    directive=(
                                        f"[Sanity Warning: Tool output exhibits an arithmetic "
                                        f"division/inversion discrepancy ({reason}). Acknowledge "
                                        "the execution but state transparently that the output "
                                        "appears inverted or mathematically anomalous.]"
                                    ),
                                    elapsed_us=elapsed,
                                )
                        except (ValueError, OverflowError):
                            pass

            # 7c. Circle area: pi * r^2
            is_circle = "circle" in combined_context
            has_r_or_area = "radius" in combined_context or "area" in combined_context
            if is_circle and has_r_or_area:
                r_match = re.search(r"radius\s*(?:of|=|is)?\s*(\d+(?:\.\d+)?)", combined_context)
                if r_match:
                    r_val = float(r_match.group(1))
                    if r_val > 0.0:
                        expected_area = math.pi * (r_val**2)
                        try:
                            res_val = float(out_nums[0])
                            # Off by >= factor of 3 (e.g. 31.4 vs 314)
                            if abs(math.log10(res_val) - math.log10(expected_area)) >= 0.8:
                                elapsed = (time.perf_counter_ns() - t0) / 1000.0
                                reason = (
                                    f"Area of circle with radius {r_val} is ~{expected_area:,.2f} "
                                    f"(pi * r^2), but tool returned {res_val:,.2f}"
                                )
                                return SanityCheckResult(
                                    is_valid=False,
                                    violation_type="ORDER_OF_MAGNITUDE_MISMATCH",
                                    reason=reason,
                                    directive=(
                                        f"[Sanity Warning: Tool output for circle area exhibits "
                                        f"a formula/order-of-magnitude discrepancy ({reason}). "
                                        "State transparently that the output appears anomalous.]"
                                    ),
                                    elapsed_us=elapsed,
                                )
                        except (ValueError, OverflowError):
                            pass

        elapsed = (time.perf_counter_ns() - t0) / 1000.0
        return SanityCheckResult(is_valid=True, elapsed_us=elapsed)
