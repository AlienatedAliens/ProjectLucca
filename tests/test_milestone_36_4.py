"""
Project Lucca — Unit Tests for Milestone 36.4:
Constitutional Kernel Fingerprint, Epistemic Prosody & Sovereign Sight.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from PIL import Image

from lucca.core.constitutional import compute_constitutional_hash
from lucca.core.schemas import DecisionRecord, RouteAction, RouteDecision, RouteFeatures
from lucca.sandbox.screenshot_tool import extract_ocr_from_image
from lucca.speech.tts import modulate_epistemic_prosody
from lucca.ui.states import THEMES, get_epistemic_theme


def test_constitutional_kernel_hash() -> None:
    """Computes deterministic 64-char SHA-256 constitutional hash and binds to DecisionRecord."""
    h1 = compute_constitutional_hash()
    assert isinstance(h1, str)
    assert len(h1) == 64
    # Determinism
    h2 = compute_constitutional_hash()
    assert h1 == h2

    # Verify attachment to DecisionRecord
    record = DecisionRecord(
        decision_id="dec-test-01",
        trace_id="tr-test-01",
        session_id="sess-test-01",
        ts=1234567.89,
        features=RouteFeatures(
            transcript="test query",
            token_count=2,
            has_question_mark=False,
            has_imperative_verb=False,
            leading_intent_keyword="test",
            entity_count=0,
            sentiment_heuristic=0.0,
            is_empty_or_whitespace=False,
        ),
        decision=RouteDecision(action=RouteAction.RULE, confidence=1.0, prediction_set=[RouteAction.RULE], elapsed_us=1200),
        executed_path="RULE",
        constitutional_hash=h1,
    )
    assert record.constitutional_hash == h1
    d_dict = record.model_dump()
    assert d_dict["constitutional_hash"] == h1


def test_epistemic_prosody_modulation() -> None:
    """Modulates Kokoro TTS speed and pitch based on epistemic verification state."""
    base_speed = 1.05
    base_pitch = 0.0

    # 1. CHECKED_FORMALIZATION_AGREED: confident, faster, steady
    s_conf, p_conf = modulate_epistemic_prosody(base_speed, base_pitch, "CHECKED_FORMALIZATION_AGREED")
    assert s_conf > base_speed
    assert p_conf == base_pitch

    # 2. SPECULATION: tentative, slower, inquisitive pitch
    s_spec, p_spec = modulate_epistemic_prosody(base_speed, base_pitch, "SPECULATION")
    assert s_spec < base_speed
    assert p_spec > base_pitch

    # 3. Normal / Neutral: identity
    s_norm, p_norm = modulate_epistemic_prosody(base_speed, base_pitch, "NEUTRAL")
    assert s_norm == base_speed
    assert p_norm == base_pitch


def test_epistemic_ui_sprite_states() -> None:
    """UI sprite themes contain epistemic states with distinct visual palettes."""
    assert "epistemic_verified" in THEMES
    assert "epistemic_speculation" in THEMES

    t_ver = get_epistemic_theme("CHECKED_FORMALIZATION_AGREED")
    assert t_ver.glow_color == "#38BDF8"  # Sapphire glow

    t_spec = get_epistemic_theme("SPECULATION")
    assert t_spec.primary_color == "#7C3AED"  # Violet primary

    t_default = get_epistemic_theme("UNKNOWN")
    assert t_default == THEMES["speaking"]


def test_sovereign_sight_cpu_ocr_fallback() -> None:
    """CPU OCR fallback extracts real text via Windows 11 WinRT OcrEngine without mmproj."""
    from PIL import ImageDraw

    # 1. Blank canvas fallback check
    img_blank = Image.new("RGB", (640, 480), color=(255, 255, 255))
    buf_blank = io.BytesIO()
    img_blank.save(buf_blank, format="JPEG")
    summary_blank = extract_ocr_from_image(buf_blank.getvalue())
    assert isinstance(summary_blank, str)
    assert "OCR CPU Fallback" in summary_blank
    assert "640x480" in summary_blank

    # 2. Canvas with rendered text extracted by WinRT Windows.Media.Ocr.OcrEngine
    img_text = Image.new("RGB", (640, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img_text)
    draw.text((40, 60), "LUCCA SOVEREIGN SIGHT", fill=(0, 0, 0))
    buf_text = io.BytesIO()
    img_text.save(buf_text, format="PNG")
    summary_text = extract_ocr_from_image(buf_text.getvalue())
    assert "OCR CPU Fallback" in summary_text
    assert "640x200" in summary_text
    assert "LUCCA" in summary_text.upper()
