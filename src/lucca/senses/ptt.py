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
VK_RMENU: Final[int] = 0xA5     # Windows virtual-key code for Right Alt / Alt-Gr
VK_LMENU: Final[int] = 0xA4     # Windows virtual-key code for Left Alt
VK_RSHIFT: Final[int] = 0xA1    # Windows virtual-key code for Right Shift
DEFAULT_POLL_INTERVAL_S: Final[float] = 0.005  # 5 ms polling interval
DEBOUNCE_MIN_SECONDS: Final[float] = 0.150  # Discard presses < 150 ms
AUTO_RELEASE_SECONDS: Final[float] = 29.5  # Hard ceiling auto-release

KEY_MAP: Final[dict[str, list[int]]] = {
    "right ctrl": [VK_RCONTROL],
    "right control": [VK_RCONTROL],
    "rctrl": [VK_RCONTROL],
    "alt gr": [VK_RMENU],
    "altgr": [VK_RMENU],
    "alt-gr": [VK_RMENU],
    "right alt": [VK_RMENU],
    "ralt": [VK_RMENU],
    "right shift": [VK_RSHIFT],
    "rshift": [VK_RSHIFT],
}


class PTTListener:
    """
    High-priority Windows PTT listener polling GetAsyncKeyState.
    Avoids low-level keyboard hook unhooks and hangs.
    Accepts Right Control or Alt-Gr (Right Alt) by default.
    """

    def __init__(
        self,
        on_pressed: Callable[[int], None],
        on_released: Callable[[int, float], None],
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        max_duration_s: float = AUTO_RELEASE_SECONDS,
        target_vk: int | None = None,
        key_name: str | None = None,
    ) -> None:
        self.on_pressed = on_pressed
        self.on_released = on_released
        self.poll_interval_s = poll_interval_s
        self.max_duration_s = max_duration_s

        if target_vk is not None:
            self.target_vks: list[int] = [target_vk]
        elif key_name and key_name.lower().strip() in KEY_MAP:
            self.target_vks = KEY_MAP[key_name.lower().strip()]
        else:
            # Default to accepting either Right Control OR Alt-Gr (Right Alt)
            self.target_vks = [VK_RCONTROL, VK_RMENU]

        self._running = False
        self._thread: threading.Thread | None = None
        self._is_down = False
        self._press_time_monotonic = 0.0
        self._press_time_ns = 0

    def set_key(self, key_name: str) -> None:
        """Dynamically rebind PTT target key."""
        k = key_name.lower().strip()
        if k in KEY_MAP:
            self.target_vks = KEY_MAP[k]
        elif k in ("all", "both", "default"):
            self.target_vks = [VK_RCONTROL, VK_RMENU]

    def is_key_down(self) -> bool:
        """Queries whether any of the target keys is physically held down right now."""
        for vk in self.target_vks:
            state = int(ctypes.windll.user32.GetAsyncKeyState(vk))
            if (state & 0x8000) != 0:
                return True
        return False

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
