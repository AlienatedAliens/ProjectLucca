"""
Project Lucca — Clipboard Perception Tool
Reads system clipboard text with truncation and safety boundaries.
"""

from __future__ import annotations

import sys
import structlog

logger = structlog.get_logger(__name__)


def read_clipboard_text(max_chars: int = 2000) -> tuple[str, bool]:
    """
    Reads plain text from the system clipboard.
    Returns (text, is_truncated).
    Truncates at max_chars.
    """
    if sys.platform != "win32":
        return "", False

    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    cf_unicodetext = 13
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    kernel32.GlobalLock.restype = wintypes.LPCWSTR
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    if not user32.OpenClipboard(None):
        logger.warning("clipboard_open_failed")
        return "", False

    text = ""
    try:
        handle = user32.GetClipboardData(cf_unicodetext)
        if handle:
            text_ptr = kernel32.GlobalLock(handle)
            text = str(text_ptr) if text_ptr else ""
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()

    truncated = len(text) > max_chars
    final_text = text[:max_chars]
    return final_text, truncated
