"""
Project Lucca — Clock Interface and Implementations
Spec 02 (ClockPort), F-ARCH-102, F-ARCH-107
"""

import time
from lucca.ports import ClockPort


class SystemClock:
    """Production clock using system time."""

    def now_utc(self) -> float:
        return time.time()

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def now_ns(self) -> int:
        return time.time_ns()


class FixedClock:
    """Deterministic simulated clock for tests and replay."""

    def __init__(self, initial_time: float = 0.0) -> None:
        self._current_time: float = initial_time

    def set_time(self, t: float) -> None:
        self._current_time = t

    def advance(self, seconds: float) -> None:
        self._current_time += seconds

    def now_utc(self) -> float:
        return self._current_time

    def monotonic_ns(self) -> int:
        return int(self._current_time * 1_000_000_000)

    def now_ns(self) -> int:
        return int(self._current_time * 1_000_000_000)
