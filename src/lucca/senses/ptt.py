"""
Project Lucca — Push-to-Talk (PTT) Subsystem
Spec 07 §1, Spec 01 §4
"""

import ctypes
import threading
import time
from collections.abc import Callable
from typing import Final

import structlog

from lucca.core.trace import now_ns

logger = structlog.get_logger(__name__)

# Windows Virtual-Key Codes (User32)
VK_RCONTROL: Final[int] = 0xA3  # Right Control
VK_LCONTROL: Final[int] = 0xA2  # Left Control
VK_CONTROL: Final[int] = 0x11   # Generic Control (matches either Left or Right)
VK_RMENU: Final[int] = 0xA5     # Right Alt / Alt-Gr
VK_LMENU: Final[int] = 0xA4     # Left Alt
VK_MENU: Final[int] = 0x12      # Generic Alt (matches either Left or Right)
VK_RSHIFT: Final[int] = 0xA1    # Right Shift
VK_LSHIFT: Final[int] = 0xA0    # Left Shift
VK_SHIFT: Final[int] = 0x10     # Generic Shift (matches either Left or Right)
VK_SPACE: Final[int] = 0x20     # Spacebar

DEFAULT_POLL_INTERVAL_S: Final[float] = 0.005  # 5 ms polling interval
DEBOUNCE_MIN_SECONDS: Final[float] = 0.150     # Discard presses < 150 ms
AUTO_RELEASE_SECONDS: Final[float] = 29.5      # Hard ceiling auto-release

KEY_MAP: Final[dict[str, list[int]]] = {
    # Alt-Gr / Right Alt (VK_RMENU only — never generic VK_MENU which catches Left Alt)
    "alt_gr": [VK_RMENU],
    "alt-gr": [VK_RMENU],
    "alt gr": [VK_RMENU],
    "altgr": [VK_RMENU],
    "right_alt": [VK_RMENU],
    "right-alt": [VK_RMENU],
    "right alt": [VK_RMENU],
    "ralt": [VK_RMENU],
    "alt_r": [VK_RMENU],
    # Left Alt
    "left_alt": [VK_LMENU],
    "left-alt": [VK_LMENU],
    "left alt": [VK_LMENU],
    "lalt": [VK_LMENU],
    "alt_l": [VK_LMENU],
    # Right Control (VK_RCONTROL only — never generic VK_CONTROL which catches Left Ctrl)
    "right_ctrl": [VK_RCONTROL],
    "right-ctrl": [VK_RCONTROL],
    "right ctrl": [VK_RCONTROL],
    "right_control": [VK_RCONTROL],
    "right control": [VK_RCONTROL],
    "rctrl": [VK_RCONTROL],
    "ctrl_r": [VK_RCONTROL],
    # Left Control
    "left_ctrl": [VK_LCONTROL],
    "left-ctrl": [VK_LCONTROL],
    "left ctrl": [VK_LCONTROL],
    "left_control": [VK_LCONTROL],
    "left control": [VK_LCONTROL],
    "lctrl": [VK_LCONTROL],
    "ctrl_l": [VK_LCONTROL],
    # Right Shift (VK_RSHIFT only — never generic VK_SHIFT which catches Left Shift)
    "right_shift": [VK_RSHIFT],
    "right-shift": [VK_RSHIFT],
    "right shift": [VK_RSHIFT],
    "rshift": [VK_RSHIFT],
    "shift_r": [VK_RSHIFT],
    # Left Shift
    "left_shift": [VK_LSHIFT],
    "left-shift": [VK_LSHIFT],
    "left shift": [VK_LSHIFT],
    "lshift": [VK_LSHIFT],
    "shift_l": [VK_LSHIFT],
    # Spacebar
    "space": [VK_SPACE],
    "spacebar": [VK_SPACE],
    # Universal Any: specifically Right Alt, Right Ctrl, and Right Shift (excluding Left Alt / Left Shift)
    "any": [VK_RMENU, VK_RCONTROL, VK_RSHIFT],
    "all": [VK_RMENU, VK_RCONTROL, VK_RSHIFT],
    "both": [VK_RMENU, VK_RCONTROL, VK_RSHIFT],
    "default": [VK_RMENU, VK_RCONTROL, VK_RSHIFT],
}


def resolve_key_codes(key_name: str | None) -> list[int]:
    """Resolves a key name or alias into a list of Windows virtual-key codes."""
    if not key_name:
        return [VK_RMENU, VK_RCONTROL, VK_RSHIFT]
    k = key_name.lower().strip()
    k_norm = k.replace("-", "_").replace(" ", "_")
    if k in KEY_MAP:
        return list(KEY_MAP[k])
    if k_norm in KEY_MAP:
        return list(KEY_MAP[k_norm])
    logger.warning("unrecognized_ptt_key_name", key_name=key_name)
    return [VK_RMENU, VK_RCONTROL, VK_RSHIFT]


class PTTListener:
    """
    High-priority Windows PTT listener polling GetAsyncKeyState.
    Avoids low-level keyboard hook unhooks and hangs.
    Accepts Right Alt/Alt-Gr, Right Control, or Right Shift by default.
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
        else:
            self.target_vks = resolve_key_codes(key_name)

        self._running = False
        self._thread: threading.Thread | None = None
        self._is_down = False
        self._press_time_monotonic = 0.0
        self._press_time_ns = 0

    def set_key(self, key_name: str) -> None:
        """Dynamically rebind PTT target key."""
        self.target_vks = resolve_key_codes(key_name)
        logger.info(
            "ptt_target_key_rebound",
            key_name=key_name,
            target_vks=[hex(v) for v in self.target_vks],
        )

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
            current_ns = now_ns()

            if down and not self._is_down:
                # Key transition: UP -> DOWN
                self._is_down = True
                self._press_time_monotonic = now_mono
                self._press_time_ns = current_ns
                self.on_pressed(current_ns)

            elif down and self._is_down:
                # Key held down: check auto-release cap
                duration = now_mono - self._press_time_monotonic
                if duration >= self.max_duration_s:
                    # Trigger auto-release
                    self._is_down = False
                    self.on_released(current_ns, duration * 1000.0)

            elif not down and self._is_down:
                # Key transition: DOWN -> UP
                self._is_down = False
                duration = now_mono - self._press_time_monotonic
                if duration >= DEBOUNCE_MIN_SECONDS:
                    self.on_released(current_ns, duration * 1000.0)
                # Discard presses below debounce threshold without firing release

            time.sleep(self.poll_interval_s)
