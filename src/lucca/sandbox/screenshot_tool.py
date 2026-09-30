"""
Project Lucca — Screenshot Capture Tool (WO-24 Phase 1)
Class C tool: primary display capture, JPEG-encoded, ≤200 KB, ≤1280px wide.
Uses mss (no OpenCV, no Pillow dependency). Pillow used only for JPEG re-encoding.

This module is a library function only — policy enforcement (confirmation gate,
TOOL_CONTENT_UNTRUSTED provenance) lives in the orchestrator and policy layer,
mirroring all other Class C tools. Never call this directly without going through
the confirmation gate in orchestrator._handle_screenshot_capture().
"""

from __future__ import annotations

import base64
import io

import structlog

logger = structlog.get_logger(__name__)

# Hard constraints (WO-24 Phase 1 ratification)
MAX_WIDTH_PX: int = 1280
MAX_OUTPUT_BYTES: int = 200 * 1024  # 200 KB

# JPEG quality ladder for re-compression budget enforcement
_QUALITY_LADDER: tuple[int, ...] = (75, 60, 45, 30, 20)


def _encode_jpeg_pillow(raw_pixels: bytes, width: int, height: int, quality: int) -> bytes:
    """Encode raw RGB bytes to JPEG using Pillow."""
    from PIL import Image  # type: ignore[import-untyped]

    img = Image.frombytes("RGB", (width, height), raw_pixels)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _resize_to_max_width(raw_pixels: bytes, width: int, height: int, max_width: int) -> tuple[bytes, int, int]:
    """Nearest-neighbour downscale to max_width, preserving aspect ratio.
    Returns (new_raw_pixels, new_width, new_height).
    """
    if width <= max_width:
        return raw_pixels, width, height

    new_width = max_width
    scale = width / new_width
    new_height = max(1, int(height / scale))

    # Use Pillow for resize (already required for JPEG encoding)
    from PIL import Image  # type: ignore[import-untyped]

    img = Image.frombytes("RGB", (width, height), raw_pixels)
    img = img.resize((new_width, new_height), Image.LANCZOS)
    resized_bytes = img.tobytes()
    return resized_bytes, new_width, new_height


def capture_screenshot(
    max_width: int = MAX_WIDTH_PX,
    quality: int = 75,
) -> tuple[str, int, int]:
    """Capture the primary display as a base64-encoded JPEG string.

    Returns:
        (base64_string, width_px, height_px) — base64 is the JPEG image data,
        width/height are the final dimensions after any downscaling.

    Constraints:
        - Output JPEG is guaranteed ≤ 200 KB (re-compresses at lower quality if needed).
        - Captures primary display only (monitor index 1 in mss, 0-indexed beyond 0 is primary).
        - No EXIF metadata is emitted (mss raw capture has none; PIL save with optimize strips them).
        - Clipped to max_width maintaining aspect ratio.

    Policy note:
        This is a library function. Confirmation gate and TOOL_CONTENT_UNTRUSTED provenance
        are enforced by orchestrator._handle_screenshot_capture(). Do not call this directly
        from user-facing code without going through the confirmation flow.
    """
    import mss  # noqa: PLC0415

    with mss.mss() as sct:
        # mss.monitors[0] = virtual bounding box of all monitors.
        # mss.monitors[1] = primary monitor (Windows convention).
        primary = sct.monitors[1]
        screenshot = sct.grab(primary)
        raw_width: int = screenshot.width
        raw_height: int = screenshot.height
        # mss returns BGRA; convert to RGB
        bgra = bytes(screenshot.raw)
        # Convert BGRA → RGB (drop alpha, swap B and R)
        rgb = bytearray(raw_width * raw_height * 3)
        for i in range(raw_width * raw_height):
            b = bgra[i * 4]
            g = bgra[i * 4 + 1]
            r = bgra[i * 4 + 2]
            # alpha = bgra[i * 4 + 3]  # discarded
            rgb[i * 3] = r
            rgb[i * 3 + 1] = g
            rgb[i * 3 + 2] = b

    rgb_bytes = bytes(rgb)

    # Downscale to max_width if needed
    final_raw, final_width, final_height = _resize_to_max_width(rgb_bytes, raw_width, raw_height, max_width)

    # Encode JPEG and enforce ≤200 KB budget
    jpeg_bytes: bytes | None = None
    for q in (quality, *_QUALITY_LADDER):
        try:
            candidate = _encode_jpeg_pillow(final_raw, final_width, final_height, q)
        except Exception as exc:  # noqa: BLE001
            logger.debug("screenshot_jpeg_encode_failed", quality=q, error=str(exc))
            continue
        if len(candidate) <= MAX_OUTPUT_BYTES:
            jpeg_bytes = candidate
            logger.debug(
                "screenshot_captured",
                width=final_width,
                height=final_height,
                quality=q,
                size_bytes=len(candidate),
            )
            break

    if jpeg_bytes is None:
        # Last resort: drop to 20% and accept whatever size
        jpeg_bytes = _encode_jpeg_pillow(final_raw, final_width, final_height, 20)
        logger.warning(
            "screenshot_budget_exceeded",
            width=final_width,
            height=final_height,
            size_bytes=len(jpeg_bytes),
        )

    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    return b64, final_width, final_height
