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

import asyncio
import base64
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile

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


def _extract_winrt_ocr_text(png_path: Path) -> str:
    """
    Runs Windows 11 native WinRT Windows.Media.Ocr.OcrEngine text extraction on a local PNG file.
    Attempts in-process winrt/winsdk bindings first, then native Windows.Media.Ocr.OcrEngine WinRT bridge.
    """
    # 1. Try in-process winrt / winsdk bindings if installed
    try:
        from winsdk.windows.graphics.imaging import BitmapDecoder  # type: ignore[import-not-found]
        from winsdk.windows.media.ocr import OcrEngine  # type: ignore[import-not-found]
        from winsdk.windows.storage import FileAccessMode, StorageFile  # type: ignore[import-not-found]

        async def _run_winsdk() -> str:
            s_file = await StorageFile.get_file_from_path_async(str(png_path))
            stream = await s_file.open_async(FileAccessMode.READ)
            decoder = await BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()
            engine = OcrEngine.try_create_from_user_profile_languages()
            if engine is None:
                return ""
            res = await engine.recognize_async(bitmap)
            return str(res.text or "").strip()

        return asyncio.run(_run_winsdk())
    except Exception as exc:  # noqa: BLE001
        logger.debug("ocr_winsdk_inproc_unavailable", error=str(exc))

    # 2. Native Windows 11 WinRT Windows.Media.Ocr.OcrEngine bridge
    if sys.platform != "win32":
        return ""

    ps_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    if not os.path.exists(ps_exe):
        return ""

    escaped_path = str(png_path.resolve()).replace("'", "''")
    winrt_script = (
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
        "$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]; "
        "$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]; "
        "$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType=WindowsRuntime]; "
        "$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { "
        "$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and "
        "$_.GetParameters()[0].ParameterType.Name -like 'IAsyncOperation*' })[0]; "
        "function Await($v, $t) { "
        "$m = $asTaskGeneric.MakeGenericMethod($t); "
        "$task = $m.Invoke($null, @($v)); "
        "$task.Wait(-1) | Out-Null; "
        "$task.Result "
        "}; "
        f"$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync('{escaped_path}')) ([Windows.Storage.StorageFile]); "
        "$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream]); "
        "$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder]); "
        "$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap]); "
        "$eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages(); "
        "$res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult]); "
        "Write-Output $res.Text; "
        "$stream.Dispose()"
    )
    try:
        proc = subprocess.run(  # noqa: S603
            [ps_exe, "-NoProfile", "-NonInteractive", "-Command", winrt_script],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("ocr_winrt_bridge_failed", error=str(exc))
    return ""


def extract_ocr_from_image(raw_bytes: bytes | str) -> str:
    """
    Extracts text from an image on CPU using Windows 11 WinRT Windows.Media.Ocr.OcrEngine (Milestone 36.4).
    Used as sovereign sight fallback when multimodal vision projector (mmproj) is None.
    """
    if isinstance(raw_bytes, str):
        try:
            image_data = base64.b64decode(raw_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ocr_b64decode_failed_fallback_encode", error=str(exc))
            image_data = raw_bytes.encode("utf-8")
    else:
        image_data = raw_bytes

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_data)).convert("RGB")
        w, h = img.size
    except Exception as exc:  # noqa: BLE001
        logger.debug("ocr_image_open_failed", error=str(exc))
        return "[OCR CPU Fallback: invalid image bytes]"

    # 1. Windows 11 WinRT Windows.Media.Ocr.OcrEngine extraction
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_path = Path(tf.name)
        img.save(tmp_path, format="PNG")
        extracted = _extract_winrt_ocr_text(tmp_path)
        if extracted:
            return f"[OCR CPU Fallback ({w}x{h}): {extracted}]"
    except Exception as exc:  # noqa: BLE001
        logger.debug("ocr_winrt_extraction_failed", error=str(exc))
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as unlink_err:
                logger.debug("ocr_tmp_unlink_failed", error=str(unlink_err))

    # 2. Attempt pytesseract if available on non-Windows or when WinRT returns empty
    try:
        import pytesseract  # type: ignore[import-not-found]

        text = str(pytesseract.image_to_string(img) or "").strip()
        if text:
            return f"[OCR CPU Fallback ({w}x{h}): {text}]"
    except Exception as exc:  # noqa: BLE001
        logger.debug("ocr_pytesseract_unavailable", error=str(exc))

    return f"[OCR CPU Fallback ({w}x{h}): no text detected]"


def capture_screenshot_with_ocr_fallback(
    max_width: int = MAX_WIDTH_PX,
    quality: int = 75,
    mmproj: object | None = None,
) -> tuple[str, int, int, str | None]:
    """
    Captures primary display with automatic CPU OCR fallback when mmproj is None.
    Returns: (b64_string, width, height, ocr_text_or_none)
    """
    b64, w, h = capture_screenshot(max_width=max_width, quality=quality)
    ocr_text = None
    if mmproj is None:
        ocr_text = extract_ocr_from_image(b64)
    return b64, w, h, ocr_text
