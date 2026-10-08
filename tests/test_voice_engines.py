"""
Project Lucca — Unit & Integration Tests for Voice Synthesis Engines Architecture
WO-30, Spec 07 §5, Spec 16 §4

Tests the 5 ratified engines:
1. Kokoro-82M (Vector Blender & Dual-Vector Mixer)
2. KittenTTS (KittenML 15M/80M CPU ONNX with Text Normalization)
3. Pocket TTS (Kyutai Labs Lightweight Edge-Streaming Voice Cloner)
4. Supertonic 3 (Multilingual Code-Switching & Language Detection)
5. KokoClone (Kokoro Audio Clip Zero-Shot Style Adapter)
"""

from __future__ import annotations

import os
from pathlib import Path
import wave

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from lucca.senses.ring_buffer import get_playback_ring
from lucca.senses.tts import TTSWorker
from lucca.speech.engines import (
    ENGINE_CATALOG,
    KittenTTSEngine,
    KokoCloneEngine,
    KokoroEngine,
    PocketTTSEngine,
    Supertonic3Engine,
    get_voice_engine,
    parse_engine_from_spec,
)
from lucca.speech.kokoclone import compute_cloned_style_vector, get_kokoclone_metadata
from lucca.speech.text_normalizer import KittenTextNormalizer, normalize_text
from lucca.ui.settings_dialog import SettingsDialog
from lucca.ui.settings_tabs.voice_tab import VoiceTab


def test_text_normalizer_currency() -> None:
    norm = KittenTextNormalizer()
    s_usd = chr(36) + "1,250.50"
    out_usd = norm.normalize(f"Cost is {s_usd}")
    assert "one thousand two hundred fifty dollars and fifty cents" in out_usd

    s_eur = chr(8364) + "42.15"
    out_eur = norm.normalize(f"Price is {s_eur}")
    assert "forty-two euros and fifteen cents" in out_eur

    s_gbp = chr(163) + "99"
    out_gbp = norm.normalize(f"Total is {s_gbp}")
    assert "ninety-nine pounds" in out_gbp


def test_text_normalizer_dates_times_and_ordinals() -> None:
    text = "On 2026-10-03 at 10:30 PM, player arrived 1st and finished 42nd with 99.5%."
    res = normalize_text(text)
    assert "October third, twenty twenty-six" in res
    assert "ten thirty PM" in res
    assert "first" in res
    assert "forty-second" in res
    assert "ninety-nine point five percent" in res


def test_text_normalizer_abbreviations_and_tech_units() -> None:
    text = "Dr. Lucca measured 16 GB VRAM and 60 ms latency approx."
    res = normalize_text(text)
    assert "Doctor Lucca" in res
    assert "sixteen gigabytes" in res
    assert "V-ram" in res or "V-RAM" in res or "ram" in res.lower()
    assert "sixty milliseconds" in res
    assert "approximately" in res


def test_engine_spec_parsing() -> None:
    eng, sub = parse_engine_from_spec("kittentts:mini:int8")
    assert eng == "kittentts"
    assert sub == "mini:int8"

    eng, sub = parse_engine_from_spec("pocket_tts:clone:C:/sample.wav")
    assert eng == "pocket_tts"
    assert sub == "clone:C:/sample.wav"

    eng, sub = parse_engine_from_spec("supertonic3:ja")
    assert eng == "supertonic3"
    assert sub == "ja"

    eng, sub = parse_engine_from_spec("kokoclone:C:/voice.wav")
    assert eng == "kokoclone"
    assert sub == "C:/voice.wav"

    eng, sub = parse_engine_from_spec("blend:0.70*af_bella+0.30*af_sarah")
    assert eng == "kokoro"
    assert "af_bella" in sub

    # General voice spec maps to Kokoro
    eng, sub = parse_engine_from_spec("genki_heroine")
    assert eng == "kokoro"
    assert sub == "genki_heroine"


def test_engine_catalog_descriptors() -> None:
    assert len(ENGINE_CATALOG) == 5
    for key in ("kokoro", "kittentts", "pocket_tts", "supertonic3", "kokoclone"):
        assert key in ENGINE_CATALOG
        desc = ENGINE_CATALOG[key]  # type: ignore[index]
        assert desc.name
        assert desc.architecture
        assert desc.footprint
        assert desc.strengths
        assert desc.best_for


def test_kittentts_engine_synthesis() -> None:
    engine = get_voice_engine("kittentts")
    assert isinstance(engine, KittenTTSEngine)
    raw = f"Total: {chr(36)}45.00 on 2026-10-03."
    norm = engine.normalize_input(raw)
    assert "forty-five dollars" in norm
    assert "October third, twenty twenty-six" in norm

    samples, sr = engine.synthesize(raw, speed=1.1)
    assert sr == 24000
    assert len(samples) > 0


def test_supertonic3_code_switching() -> None:
    engine = get_voice_engine("supertonic3")
    assert isinstance(engine, Supertonic3Engine)

    langs = engine.detect_languages("Sugoi! The code compiled cleanly.")
    assert "en" in langs

    smoothed = engine.smooth_code_switching("Sugoi! Arigatou gozaimasu!")
    assert "soo-goy" in smoothed
    assert "ah-ree-gah-toh" in smoothed

    samples, sr = engine.synthesize("Sugoi! Compilation complete.", speed=1.0)
    assert sr == 24000
    assert len(samples) > 0


def test_kokoclone_vector_generation(tmp_path: Path) -> None:
    # Synthesize clean 0.5s reference wav
    wav_path = tmp_path / "ref_speech.wav"
    sr = 24000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    sine = (0.4 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(sine.tobytes())

    meta = get_kokoclone_metadata(wav_path)
    assert meta["duration_s"] == 0.5
    assert meta["sample_rate"] == 24000
    assert 200.0 <= meta["f0"] <= 240.0

    kokoro_eng = KokoroEngine().raw_engine
    if kokoro_eng is not None:
        cloned_vec, v_meta = compute_cloned_style_vector(wav_path, kokoro_eng)
        assert cloned_vec.shape == (510, 1, 256)
        assert cloned_vec.dtype == np.float32
        assert "blend_projection" in v_meta

    engine = get_voice_engine("kokoclone")
    assert isinstance(engine, KokoCloneEngine)
    samples, out_sr = engine.synthesize("Testing zero shot clone.", voice_spec=str(wav_path))
    assert out_sr == 24000
    assert len(samples) > 0


def test_pocket_tts_engine() -> None:
    engine = get_voice_engine("pocket_tts")
    assert isinstance(engine, PocketTTSEngine)
    samples, sr = engine.synthesize("Edge stream ready.", speed=1.0)
    assert sr == 24000
    assert len(samples) > 0


def test_voice_tab_ui_modes_and_presets(qapp: QApplication) -> None:
    dlg = SettingsDialog()
    tab = dlg.tab_voice
    assert isinstance(tab, VoiceTab)

    # 1. Test KittenTTS Preset
    tab._apply_kittentts_preset()
    assert tab.rb_engine_kitten.isChecked()
    spec = tab.get_selected_voice_spec()
    assert "kittentts:mini" in spec and "sarah" in spec and "int8" in spec

    # 2. Test Pocket TTS Preset
    tab._apply_pocket_tts_preset()
    assert tab.rb_engine_pocket.isChecked()
    spec = tab.get_selected_voice_spec()
    assert "pocket_tts" in spec

    # 3. Test Supertonic 3 Preset
    tab._apply_supertonic3_preset()
    assert tab.rb_engine_supertonic.isChecked()
    spec = tab.get_selected_voice_spec()
    assert "supertonic3" in spec and "asuka_tsundere" in spec and "auto" in spec

    # 4. Test KokoClone Preset
    tab._apply_kokoclone_preset()
    assert tab.rb_engine_kokoclone.isChecked()
    spec = tab.get_selected_voice_spec()
    assert "kokoclone" in spec

    # 5. Test Kokoro Heroine Preset
    tab._apply_anime_heroine_preset()
    assert tab.rb_engine_kokoro.isChecked()
    spec = tab.get_selected_voice_spec()
    assert spec.startswith("blend:")


def test_tts_worker_dispatches_all_engines() -> None:
    ring = get_playback_ring(create=True)
    worker = TTSWorker(play_ring=ring)

    # Test synthesis for each engine through TTSWorker
    res_kokoro = worker.synthesize(1, "Kokoro active.", voice="blend:0.70*af_bella+0.30*af_sarah")
    assert res_kokoro.samples > 0

    res_kitten = worker.synthesize(2, f"Total: {chr(36)}99.00", voice="kittentts:mini")
    assert res_kitten.samples > 0

    res_pocket = worker.synthesize(3, "Pocket edge streaming.", voice="pocket_tts:stream:warm")
    assert res_pocket.samples > 0

    res_supertonic = worker.synthesize(4, "Sugoi! Code ready.", voice="supertonic3:auto")
    assert res_supertonic.samples > 0

    res_kokoclone = worker.synthesize(5, "Cloned voice active.", voice="kokoclone")
    assert res_kokoclone.samples > 0
