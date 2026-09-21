"""
Project Lucca — Statistical Verification & Telemetry Utilities
Spec 1.1.2 §5 (S1 Contract), §6.2 (Rung L2), §9 (Ladder Acceptance Tests)

Implements:
1. Wilson score confidence interval with continuity correction (Newcombe 1998, Method 4).
2. Paired McNemar contingency test with exact binomial (for b+c < 25) and
   Edwards continuity-corrected chi-square (for b+c >= 25).
"""

from __future__ import annotations

import math
from typing import Final

# Z-score for standard confidence levels (two-tailed)
Z_VALUES: Final[dict[float, float]] = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.98: 2.3263478740408408,
    0.99: 2.5758293035489004,
}


def wilson_score_interval(
    successes: int,
    total: int,
    confidence: float = 0.95,
    continuity_correction: bool = True,
) -> tuple[float, float]:
    """
    Calculates the two-tailed Wilson score confidence interval for a binomial proportion.

    Args:
        successes: Number of observed successes (k >= 0).
        total: Total number of trials (n >= k).
        confidence: Confidence level (e.g. 0.95 for 95% confidence).
        continuity_correction: Whether to apply Newcombe (1998) continuity correction.

    Returns:
        (lower_bound, upper_bound) clamped to [0.0, 1.0].
    """
    if total < 0 or successes < 0 or successes > total:
        msg = f"Invalid binomial counts: successes={successes}, total={total}"
        raise ValueError(msg)

    if total == 0:
        return 0.0, 1.0

    z = Z_VALUES.get(confidence)
    if z is None:
        # Invert the normal CDF by bisection on erfc (stdlib has no erfcinv):
        # Phi(z) = confidence  <=>  erfc(z / sqrt(2)) = 2 * (1 - confidence)
        if not 0.0 < confidence < 1.0:
            msg = f"confidence must be in (0, 1), got {confidence}"
            raise ValueError(msg)
        target = 2.0 * (1.0 - confidence)
        lo, hi = 0.0, 10.0  # erfc(10/sqrt(2)) ~ 0 for all practical purposes
        for _ in range(80):
            mid = (lo + hi) / 2.0
            if math.erfc(mid / math.sqrt(2.0)) > target:
                lo = mid
            else:
                hi = mid
        z = (lo + hi) / 2.0

    n = float(total)
    p = float(successes) / n
    z2 = z * z

    if not continuity_correction:
        # Standard Wilson score interval (Wilson 1927)
        denom = 1.0 + z2 / n
        center = (p + z2 / (2.0 * n)) / denom
        margin = (z / denom) * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))
        lb = max(0.0, center - margin)
        ub = min(1.0, center + margin)
        return lb, ub

    # Wilson score interval with continuity correction (Newcombe 1998, Method 4)
    # Lower bound calculation
    if successes == 0:
        lb = 0.0
    else:
        radicand_lb = z2 - 1.0 / n + 4.0 * n * p * (1.0 - p) + (4.0 * p - 2.0)
        radicand_lb = max(0.0, radicand_lb)
        lb_num = 2.0 * n * p + z2 - 1.0 - z * math.sqrt(radicand_lb)
        lb_denom = 2.0 * (n + z2)
        lb = max(0.0, lb_num / lb_denom)

    # Upper bound calculation
    if successes == total:
        ub = 1.0
    else:
        radicand_ub = z2 - 1.0 / n + 4.0 * n * p * (1.0 - p) - (4.0 * p - 2.0)
        radicand_ub = max(0.0, radicand_ub)
        ub_num = 2.0 * n * p + z2 + 1.0 + z * math.sqrt(radicand_ub)
        ub_denom = 2.0 * (n + z2)
        ub = min(1.0, ub_num / ub_denom)

    return lb, ub


def mcnemar_test(b: int, c: int, exact: bool = True) -> float:
    """
    Computes two-tailed p-value for the paired McNemar test on discordant pairs:
      b = Model 1 success, Model 2 failure (rule-better)
      c = Model 1 failure, Model 2 success (core-better)

    Under H0, p = 0.5 (equal probability of discordance).

    Args:
        b: Discordant count where rule succeeded and core failed.
        c: Discordant count where rule failed and core succeeded.
        exact: Whether to compute exact binomial test for b + c < 25.

    Returns:
        Two-tailed p-value in [0.0, 1.0].
    """
    if b < 0 or c < 0:
        raise ValueError(f"Discordant counts must be non-negative (got b={b}, c={c})")

    n_discordant = b + c
    if n_discordant == 0:
        return 1.0

    # Exact binomial test for small sample sizes (b + c < 25)
    if exact and n_discordant < 25:
        k = min(b, c)
        # Cumulative binomial probability P(X <= k) for X ~ Binomial(n_discordant, 0.5)
        # Multiplied by 2 for two-tailed test
        p_val = 0.0
        for i in range(k + 1):
            p_val += math.comb(n_discordant, i) * (0.5**n_discordant)
        return min(1.0, 2.0 * p_val)

    # Edwards continuity-corrected chi-square test (df = 1) for b + c >= 25
    diff = abs(b - c)
    if diff <= 1:
        return 1.0

    chi2 = ((diff - 1.0) ** 2) / float(n_discordant)
    # Survival function of chi-square with 1 df:
    # 2 * (1 - Phi(sqrt(chi2))) = erfc(sqrt(chi2 / 2))
    p_val = math.erfc(math.sqrt(chi2 / 2.0))
    return max(0.0, min(1.0, p_val))


def rule_of_three_ucl(n: int, confidence: float = 0.95) -> float:
    """
    One-sided upper confidence bound on a failure rate given 0 observed failures
    in n independent trials (the "Rule of Three", Spec 1.1.2 §6.1).

    UCL = 1 - (1 - confidence)^(1/n); for n >= 10 this is approximately 3/n at 95%.

    This is the ONLY honest statistic for shadow-cluster evidence: 5 clusters with
    0 errors bounds a rule's failure rate to <= ~45%, never to "safe". Shadow
    clusters prove intent recurrence, not safety (safety is Z3 + gas + typed
    accessors + macro bounds).
    """
    if n <= 0:
        return 1.0
    if not 0.0 < confidence < 1.0:
        msg = f"confidence must be in (0, 1), got {confidence}"
        raise ValueError(msg)
    return 1.0 - (1.0 - confidence) ** (1.0 / float(n))
