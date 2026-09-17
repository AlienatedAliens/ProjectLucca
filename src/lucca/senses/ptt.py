"""
Project Lucca — Push-to-Talk (PTT) Subsystem
Spec 07 §1, Spec 01 §4
"""

import ctypes
import threading
import time
from collections.abc import Callable
from typing import Final

VK_RCONTROL: Final[int] = 0xA3  # Windows virtual-key code for Right Control
VK_LCONTROL: Final[int] = 0xA2
DEFAULT_POLL_INTERVAL_S: Final[float] = 0.005  # 5 ms polling interval
DEBOUNCE_MIN_SECONDS: Final[float] = 0.150  # Discard presses < 150 ms
AUTO_RELEASE_SECONDS: Final[float] = 29.5  # Hard ceiling auto-release


class PTTListener:
    """
    High-priority Windows PTT listener polling GetAsyncKeyState.
    Avoids low-level keyboard hook unhooks and hangs.
    """

    def __init__(
        self,
        on_pressed: Callable[[int], None],
        on_released: Callable[[int, float], None],
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        max_duration_s: float = AUTO_RELEASE_SECONDS,
        target_vk: int = VK_RCONTROL,
    ) -> None:
        self.on_pressed = on_pressed
        self.on_released = on_released
        self.poll_interval_s = poll_interval_s
        self.max_duration_s = max_duration_s
        self.target_vk = target_vk

        self._running = False
        self._thread: threading.Thread | None = None
        self._is_down = False
        self._press_time_monotonic = 0.0
        self._press_time_ns = 0

    def is_key_down(self) -> bool:
        """Queries whether the target key is physically held down right now."""
        # Most significant bit is set if the key is down
        state = int(ctypes.windll.user32.GetAsyncKeyState(self.target_vk))
        return bool((state & 0x8000) != 0)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="lucca-ptt-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

    def _loop(self) -> None:
        while self._running:
            down = self.is_key_down()
            now_mono = time.monotonic()
            now_ns = time.monotonic_ns()

            if down and not self._is_down:
                # Key transition: UP -> DOWN
                self._is_down = True
                self._press_time_monotonic = now_mono
                self._press_time_ns = now_ns
                self.on_pressed(now_ns)

            elif down and self._is_down:
                # Key held down: check auto-release cap
                duration = now_mono - self._press_time_monotonic
                if duration >= self.max_duration_s:
                    # Trigger auto-release
                    self._is_down = False
                    self.on_released(now_ns, duration * 1000.0)

            elif not down and self._is_down:
                # Key transition: DOWN -> UP
                self._is_down = False
                duration = now_mono - self._press_time_monotonic
                if duration >= DEBOUNCE_MIN_SECONDS:
                    self.on_released(now_ns, duration * 1000.0)
                # Discard presses below debounce threshold without firing release

            time.sleep(self.poll_interval_s)
