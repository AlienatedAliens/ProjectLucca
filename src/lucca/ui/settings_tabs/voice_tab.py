"""
Project Lucca — Voice Architecture & Synthesis Studio Tab
WO-30, Spec 07 §5, Spec 16 §4

Supported Ratified Voice Engines:
1. Kokoro-82M (Vector Blender & Dual-Vector Tensor Mixer)
2. KittenTTS (KittenML 15M Nano / 80M Mini CPU ONNX with Text Normalization)
3. Pocket TTS (Kyutai Labs Lightweight Edge-Streaming Voice Cloner)
4. Supertonic 3 (Multilingual Code-Switching & Language Detection)
5. KokoClone (Kokoro Audio Clip Zero-Shot Style Adapter)
"""

from __future__ import annotations

import logging
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Final

import kokoro_onnx
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lucca.senses.tts import (
    VOICE_ALIASES,
    VOICE_RECIPES,
    enhance_anime_expressive_punctuation,
    get_available_voices,
    parse_voice_blend,
)
from lucca.speech.engines import (
    ENGINE_CATALOG,
    KITTEN_VOICES,
    KOKOCLONE_PRESETS,
    POCKET_VOICES,
    SUPERTONIC_VOICES,
    get_voice_engine,
    parse_engine_from_spec,
)
from lucca.speech.kokoclone import compute_cloned_style_vector, get_kokoclone_metadata
from lucca.speech.text_normalizer import normalize_text
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = logging.getLogger(__name__)


class VoiceTabSignals(QObject):
    """Thread-safe signal bridge marshaling background synthesis updates to the Qt main thread."""

    status_updated = pyqtSignal(str)
    test_done = pyqtSignal(bool, str)


class VoiceTab(QWidget):
    """Tab 1: Voice Architecture & Synthesis Studio."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade

        self.signals = VoiceTabSignals()
        self.signals.status_updated.connect(self._on_status_updated)
        self.signals.test_done.connect(self._on_test_done)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.cb_affect_enabled = QCheckBox("Enable Continuous 3D PAD Emotional Dynamics", self)
        self.cb_affect_enabled.setChecked(True)

        # -------------------------------------------------------------
        # Quick Bar: Ratified Voice Presets
        # -------------------------------------------------------------
        grp_preset = QGroupBox("Quick-Switch Canonical Voice Presets", self)
        h_pres = QHBoxLayout(grp_preset)

        btn_kokoro = QPushButton("✨ Kokoro Anime Heroine", grp_preset)
        btn_kokoro.setStyleSheet("color: #00e5ff; font-weight: bold;")
        btn_kokoro.clicked.connect(self._apply_anime_heroine_preset)
        h_pres.addWidget(btn_kokoro)

        btn_kitten = QPushButton("🐱 KittenTTS Mini (80M CPU)", grp_preset)
        btn_kitten.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        btn_kitten.clicked.connect(self._apply_kittentts_preset)
        h_pres.addWidget(btn_kitten)

        btn_pocket = QPushButton("⚡ Pocket TTS (Kyutai Edge)", grp_preset)
        btn_pocket.setStyleSheet("color: #a0aec0; font-weight: bold;")
        btn_pocket.clicked.connect(self._apply_pocket_tts_preset)
        h_pres.addWidget(btn_pocket)

        btn_supertonic = QPushButton("🌐 Supertonic 3 (Bilingual)", grp_preset)
        btn_supertonic.setStyleSheet("color: #38bdf8; font-weight: bold;")
        btn_supertonic.clicked.connect(self._apply_supertonic3_preset)
        h_pres.addWidget(btn_supertonic)

        btn_clone = QPushButton("🧬 KokoClone (Voice Cloner)", grp_preset)
        btn_clone.setStyleSheet("color: #ec4899; font-weight: bold;")
        btn_clone.clicked.connect(self._apply_kokoclone_preset)
        h_pres.addWidget(btn_clone)

        h_pres.addStretch()
        layout.addWidget(grp_preset)

        # -------------------------------------------------------------
        # Master Engine Selection Radio Buttons
        # -------------------------------------------------------------
        grp_engine = QGroupBox("Voice Synthesis Engine Architecture", self)
        h_engine = QHBoxLayout(grp_engine)
        self.rb_engine_kokoro = QRadioButton("Kokoro-82M (Vector Blender)", grp_engine)
        self.rb_engine_kitten = QRadioButton("KittenTTS (KittenML CPU ONNX)", grp_engine)
        self.rb_engine_pocket = QRadioButton("Pocket TTS (Kyutai Edge)", grp_engine)
        self.rb_engine_supertonic = QRadioButton("Supertonic 3 (Multilingual)", grp_engine)
        self.rb_engine_kokoclone = QRadioButton("KokoClone (Audio Adapter)", grp_engine)

        h_engine.addWidget(self.rb_engine_kokoro)
        h_engine.addWidget(self.rb_engine_kitten)
        h_engine.addWidget(self.rb_engine_pocket)
        h_engine.addWidget(self.rb_engine_supertonic)
        h_engine.addWidget(self.rb_engine_kokoclone)
        layout.addWidget(grp_engine)

        # -------------------------------------------------------------
        # Panel 1: Kokoro-82M Studio
        # -------------------------------------------------------------
        self.panel_kokoro = QGroupBox("Kokoro-82M Dual-Vector Tensor Blender & Recipes", self)
        v_kokoro = QVBoxLayout(self.panel_kokoro)

        h_kmode = QHBoxLayout()
        self.rb_mode_mixer = QRadioButton("Dual-Vector Tensor Mixer", self.panel_kokoro)
        self.rb_mode_recipe = QRadioButton("Canonical Recipe Preset", self.panel_kokoro)
        self.rb_mode_single = QRadioButton("Single Installed Vector (54 Voices)", self.panel_kokoro)
        self.rb_mode_mixer.setChecked(True)
        h_kmode.addWidget(self.rb_mode_mixer)
        h_kmode.addWidget(self.rb_mode_recipe)
        h_kmode.addWidget(self.rb_mode_single)
        h_kmode.addStretch()
        v_kokoro.addLayout(h_kmode)

        all_installed = get_available_voices()
        pure_voices = [v for v in all_installed if v not in VOICE_RECIPES]

        # Sub-container 1a: Mixer
        self.box_mixer = QWidget(self.panel_kokoro)
        f_mix = QFormLayout(self.box_mixer)
        self.combo_voice_a = QComboBox(self.box_mixer)
        self.combo_voice_b = QComboBox(self.box_mixer)
        for v in pure_voices:
            self.combo_voice_a.addItem(v, v)
            self.combo_voice_b.addItem(v, v)
        f_mix.addRow("Primary Voice (A):", self.combo_voice_a)
        f_mix.addRow("Secondary Voice (B):", self.combo_voice_b)

        h_slider = QHBoxLayout()
        self.slider_blend = QSlider(Qt.Orientation.Horizontal, self.box_mixer)
        self.slider_blend.setRange(0, 100)
        self.slider_blend.setValue(70)
        self.lbl_blend_ratio = QLabel("70% A / 30% B", self.box_mixer)
        self.lbl_blend_ratio.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        h_slider.addWidget(self.slider_blend)
        h_slider.addWidget(self.lbl_blend_ratio)
        f_mix.addRow("Linear Weighting:", h_slider)

        self.line_blend_formula = QLineEdit(self.box_mixer)
        self.line_blend_formula.setReadOnly(True)
        f_mix.addRow("Computed Vector Spec:", self.line_blend_formula)
        v_kokoro.addWidget(self.box_mixer)

        # Sub-container 1b: Recipe
        self.box_recipe = QWidget(self.panel_kokoro)
        f_rec = QFormLayout(self.box_recipe)
        self.combo_recipe = QComboBox(self.box_recipe)
        for r_name, r_formula in VOICE_RECIPES.items():
            self.combo_recipe.addItem(f"{r_name.replace('_', ' ').title()} ({r_formula})", r_name)
        f_rec.addRow("Recipe Preset:", self.combo_recipe)
        v_kokoro.addWidget(self.box_recipe)

        # Sub-container 1c: Single
        self.box_single = QWidget(self.panel_kokoro)
        f_sng = QFormLayout(self.box_single)
        self.combo_single_voice = QComboBox(self.box_single)
        for v in pure_voices:
            self.combo_single_voice.addItem(f"{v} (Kokoro 512-dim)", v)
        f_sng.addRow("Installed Voice:", self.combo_single_voice)
        v_kokoro.addWidget(self.box_single)

        self.combo_voice_a.currentIndexChanged.connect(self._update_blend_formula)
        self.combo_voice_b.currentIndexChanged.connect(self._update_blend_formula)
        self.slider_blend.valueChanged.connect(self._update_blend_formula)
        self.rb_mode_mixer.toggled.connect(self._sync_kokoro_submodes)
        self.rb_mode_recipe.toggled.connect(self._sync_kokoro_submodes)
        self.rb_mode_single.toggled.connect(self._sync_kokoro_submodes)
        self._update_blend_formula()
        self._sync_kokoro_submodes()
        layout.addWidget(self.panel_kokoro)

        # -------------------------------------------------------------
        # Panel 2: KittenTTS (KittenML) Studio
        # -------------------------------------------------------------
        self.panel_kitten = QGroupBox("KittenTTS (KittenML) — High-Efficiency CPU ONNX Studio", self)
        f_kit = QFormLayout(self.panel_kitten)

        self.combo_kitten_variant = QComboBox(self.panel_kitten)
        self.combo_kitten_variant.addItem("KittenTTS Mini (80M parameters — 80 MB on disk)", "mini")
        self.combo_kitten_variant.addItem("KittenTTS Nano (15M parameters — 25 MB on disk)", "nano")
        f_kit.addRow("Model Architecture:", self.combo_kitten_variant)

        self.combo_kitten_voice = QComboBox(self.panel_kitten)
        for v_k, (v_label, _) in KITTEN_VOICES.items():
            self.combo_kitten_voice.addItem(v_label, v_k)
        f_kit.addRow("Voice Persona / Speaker:", self.combo_kitten_voice)

        self.combo_kitten_quant = QComboBox(self.panel_kitten)
        self.combo_kitten_quant.addItem("INT8 Quantized (Optimized for CPU Inference)", "int8")
        self.combo_kitten_quant.addItem("FP32 Full Precision", "fp32")
        f_kit.addRow("Quantization Mode:", self.combo_kitten_quant)

        lbl_kit_desc = QLabel(
            "Designed from scratch for ONNX CPU runtime. Includes an advanced built-in "
            "text-normalization pipeline (currency, dates, numbers, abbreviations) without glitches.",
            self.panel_kitten,
        )
        lbl_kit_desc.setStyleSheet("color: #a0aec0; font-size: 11px;")
        lbl_kit_desc.setWordWrap(True)
        f_kit.addRow("Engine Profile:", lbl_kit_desc)

        h_kit_prev = QHBoxLayout()
        self.btn_preview_norm = QPushButton("🔍 Preview Text Normalization", self.panel_kitten)
        self.btn_preview_norm.clicked.connect(self._preview_text_normalization)
        self.lbl_norm_preview = QLabel("Normalizer ready.", self.panel_kitten)
        self.lbl_norm_preview.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-style: italic;")
        h_kit_prev.addWidget(self.btn_preview_norm)
        h_kit_prev.addWidget(self.lbl_norm_preview)
        h_kit_prev.addStretch()
        f_kit.addRow("Text Normalizer:", h_kit_prev)
        layout.addWidget(self.panel_kitten)

        # -------------------------------------------------------------
        # Panel 3: Pocket TTS (Kyutai Labs) Edge Studio
        # -------------------------------------------------------------
        self.panel_pocket = QGroupBox("Pocket TTS (Kyutai Labs) — Lightweight Edge-Streaming Studio", self)
        f_pkt = QFormLayout(self.panel_pocket)

        self.combo_pocket_voice = QComboBox(self.panel_pocket)
        for v_k, (v_label, _) in POCKET_VOICES.items():
            self.combo_pocket_voice.addItem(v_label, v_k)
        self.combo_pocket_voice.addItem("🎙️ Custom Reference Audio (.wav Voice Clone)", "clone")
        self.combo_pocket_voice.currentIndexChanged.connect(self._on_pocket_voice_changed)
        f_pkt.addRow("Speaker Voice / Persona:", self.combo_pocket_voice)

        self.combo_pocket_profile = QComboBox(self.panel_pocket)
        self.combo_pocket_profile.addItem("Edge Swift (Ultra-Low Latency, High Responsiveness)", "stream:swift")
        self.combo_pocket_profile.addItem("Edge Warm (Balanced Conversational Flow)", "stream:warm")
        f_pkt.addRow("Streaming Profile:", self.combo_pocket_profile)

        h_pkt_wav = QHBoxLayout()
        self.line_pocket_wav = QLineEdit(self.panel_pocket)
        self.line_pocket_wav.setPlaceholderText("Path to clean 3-10s reference .wav file...")
        self.line_pocket_wav.setEnabled(False)
        self.btn_browse_pocket_wav = QPushButton("Browse .wav", self.panel_pocket)
        self.btn_browse_pocket_wav.setEnabled(False)
        self.btn_browse_pocket_wav.clicked.connect(self._browse_pocket_wav)
        h_pkt_wav.addWidget(self.line_pocket_wav)
        h_pkt_wav.addWidget(self.btn_browse_pocket_wav)
        f_pkt.addRow("Reference Voice:", h_pkt_wav)

        h_lat = QHBoxLayout()
        self.slider_pocket_latency = QSlider(Qt.Orientation.Horizontal, self.panel_pocket)
        self.slider_pocket_latency.setRange(20, 120)
        self.slider_pocket_latency.setValue(60)
        self.lbl_pocket_latency = QLabel("60 ms", self.panel_pocket)
        self.lbl_pocket_latency.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_pocket_latency.valueChanged.connect(
            lambda v: self.lbl_pocket_latency.setText(f"{v} ms")
        )
        h_lat.addWidget(self.slider_pocket_latency)
        h_lat.addWidget(self.lbl_pocket_latency)
        f_pkt.addRow("Edge Buffer Latency:", h_lat)
        layout.addWidget(self.panel_pocket)

        # -------------------------------------------------------------
        # Panel 4: Supertonic 3 Multilingual Studio
        # -------------------------------------------------------------
        self.panel_supertonic = QGroupBox("Supertonic 3 — Multilingual Code-Switching Studio", self)
        f_sup = QFormLayout(self.panel_supertonic)

        self.combo_supertonic_voice = QComboBox(self.panel_supertonic)
        for v_k, (v_label, _) in SUPERTONIC_VOICES.items():
            self.combo_supertonic_voice.addItem(v_label, v_k)
        f_sup.addRow("Multilingual Character:", self.combo_supertonic_voice)

        self.combo_supertonic_mode = QComboBox(self.panel_supertonic)
        self.combo_supertonic_mode.addItem("Auto-Detect Language (Real-Time Dynamic Code-Switching)", "auto")
        self.combo_supertonic_mode.addItem("English + Japanese (Bilingual Tech & Anime Terms)", "ja")
        self.combo_supertonic_mode.addItem("English + Chinese (Multilingual Polyglot)", "zh")
        self.combo_supertonic_mode.addItem("English + European (Spanish / French / German)", "eu")
        f_sup.addRow("Language Engine:", self.combo_supertonic_mode)

        self.chk_supertonic_smooth = QCheckBox("Smooth Phonetic Boundaries (Eliminate Phoneme Stumble)", self.panel_supertonic)
        self.chk_supertonic_smooth.setChecked(True)
        f_sup.addRow("Phoneme Filter:", self.chk_supertonic_smooth)

        lbl_sup_desc = QLabel(
            "Avoids the harsh phoneme-stumble that happens when Kokoro encounters mixed-language "
            "sentences. Seamlessly handles foreign phrases, loanwords, and inline code-switching.",
            self.panel_supertonic,
        )
        lbl_sup_desc.setStyleSheet("color: #a0aec0; font-size: 11px;")
        lbl_sup_desc.setWordWrap(True)
        f_sup.addRow("Description:", lbl_sup_desc)
        layout.addWidget(self.panel_supertonic)

        # -------------------------------------------------------------
        # Panel 5: KokoClone Audio Clip Cloner Studio
        # -------------------------------------------------------------
        self.panel_kokoclone = QGroupBox("KokoClone — Kokoro Zero-Shot Audio Clip Cloner", self)
        f_kc = QFormLayout(self.panel_kokoclone)

        self.combo_kokoclone_preset = QComboBox(self.panel_kokoclone)
        for p_k, (p_label, p_path) in KOKOCLONE_PRESETS.items():
            self.combo_kokoclone_preset.addItem(p_label, p_path)
        self.combo_kokoclone_preset.addItem("📁 Custom Reference .wav File (Browse...)", "custom")
        self.combo_kokoclone_preset.currentIndexChanged.connect(self._on_kokoclone_preset_changed)
        f_kc.addRow("Reference Preset:", self.combo_kokoclone_preset)

        h_kc_wav = QHBoxLayout()
        self.line_kokoclone_wav = QLineEdit(self.panel_kokoclone)
        self.line_kokoclone_wav.setText(KOKOCLONE_PRESETS["asuka_studio"][1])
        self.line_kokoclone_wav.setPlaceholderText("Select a 3-10s clean .wav speech clip to clone...")
        self.btn_browse_kokoclone = QPushButton("Browse .wav", self.panel_kokoclone)
        self.btn_browse_kokoclone.clicked.connect(self._browse_kokoclone_wav)
        h_kc_wav.addWidget(self.line_kokoclone_wav)
        h_kc_wav.addWidget(self.btn_browse_kokoclone)
        f_kc.addRow("Reference Clip (.wav):", h_kc_wav)

        h_kc_extract = QHBoxLayout()
        self.btn_extract_kokoclone = QPushButton("🧬 Extract 512-dim Voice Vector", self.panel_kokoclone)
        self.btn_extract_kokoclone.clicked.connect(self._extract_kokoclone_metrics)
        self.lbl_kokoclone_metrics = QLabel("No clip analyzed yet.", self.panel_kokoclone)
        self.lbl_kokoclone_metrics.setStyleSheet(f"color: {CT_GOLD_TEXT};")
        h_kc_extract.addWidget(self.btn_extract_kokoclone)
        h_kc_extract.addWidget(self.lbl_kokoclone_metrics)
        h_kc_extract.addStretch()
        f_kc.addRow("Vector Extraction:", h_kc_extract)

        lbl_kc_desc = QLabel(
            "Adapts the kokoro-onnx pipeline to enable zero-shot voice cloning from short "
            "reference audio clips. Projects pitch, brightness, and energy into Kokoro's style latent space.",
            self.panel_kokoclone,
        )
        lbl_kc_desc.setStyleSheet("color: #a0aec0; font-size: 11px;")
        lbl_kc_desc.setWordWrap(True)
        f_kc.addRow("Architecture:", lbl_kc_desc)
        layout.addWidget(self.panel_kokoclone)

        # Sync Engine Selection Radio Buttons
        self.rb_engine_kokoro.toggled.connect(self._sync_engine_panels)
        self.rb_engine_kitten.toggled.connect(self._sync_engine_panels)
        self.rb_engine_pocket.toggled.connect(self._sync_engine_panels)
        self.rb_engine_supertonic.toggled.connect(self._sync_engine_panels)
        self.rb_engine_kokoclone.toggled.connect(self._sync_engine_panels)

        # -------------------------------------------------------------
        # Pacing & Speed Multiplier
        # -------------------------------------------------------------
        grp_speed = QGroupBox("Speaking Pace & Audio Pacing", self)
        f_speed = QFormLayout(grp_speed)
        h_speed = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Orientation.Horizontal, grp_speed)
        self.slider_speed.setRange(60, 180)
        cur_speed = getattr(self.dialog, "current_speed", 1.10)
        self.slider_speed.setValue(int(cur_speed * 100))
        self.lbl_speed_val = QLabel(f"{cur_speed:.2f}x", grp_speed)
        self.lbl_speed_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_speed.valueChanged.connect(
            lambda val: self.lbl_speed_val.setText(f"{(val / 100.0):.2f}x")
        )
        h_speed.addWidget(self.slider_speed)
        h_speed.addWidget(self.lbl_speed_val)
        f_speed.addRow("Pace Multiplier:", h_speed)
        layout.addWidget(grp_speed)

        # -------------------------------------------------------------
        # Test Synthesis Box
        # -------------------------------------------------------------
        grp_test = QGroupBox("Test Voice Playback & Audio Synthesis", self)
        v_test = QVBoxLayout(grp_test)

        self.line_test_text = QLineEdit(
            "All systems operational! The upgraded pipeline is online and ready for our next experiment.",
            grp_test,
        )
        v_test.addWidget(self.line_test_text)

        # Quick test phrase buttons
        h_sample_btns = QHBoxLayout()
        btn_sample_norm = QPushButton("Sample: Normalizer Test ($120.50 on 2026-10-03)", grp_test)
        btn_sample_norm.setStyleSheet("font-size: 11px;")
        btn_sample_norm.clicked.connect(self._load_sample_norm)

        btn_sample_ja = QPushButton("Sample: Sugoi! Code compilation succeeded!", grp_test)
        btn_sample_ja.setStyleSheet("font-size: 11px;")
        btn_sample_ja.clicked.connect(self._load_sample_ja)

        btn_sample_eng = QPushButton("Sample: Anime Heroine Line", grp_test)
        btn_sample_eng.setStyleSheet("font-size: 11px;")
        btn_sample_eng.clicked.connect(self._load_sample_eng)

        h_sample_btns.addWidget(btn_sample_norm)
        h_sample_btns.addWidget(btn_sample_ja)
        h_sample_btns.addWidget(btn_sample_eng)
        h_sample_btns.addStretch()
        v_test.addLayout(h_sample_btns)

        h_test_act = QHBoxLayout()
        self.btn_test_speech = QPushButton("🔊 Test Voice Synthesis", grp_test)
        self.btn_test_speech.clicked.connect(self._test_voice_sample)
        h_test_act.addWidget(self.btn_test_speech)

        self.lbl_voice_status = QLabel("Ready.", grp_test)
        h_test_act.addWidget(self.lbl_voice_status)
        h_test_act.addStretch()
        v_test.addLayout(h_test_act)

        layout.addWidget(grp_test)
        layout.addStretch()

        # Initial selection based on active config
        cur_voice = getattr(self.dialog, "current_voice", "blend:0.70*af_bella+0.30*af_sarah")
        self._load_initial_voice(cur_voice)

    def _sync_engine_panels(self) -> None:
        self.panel_kokoro.setVisible(self.rb_engine_kokoro.isChecked())
        self.panel_kitten.setVisible(self.rb_engine_kitten.isChecked())
        self.panel_pocket.setVisible(self.rb_engine_pocket.isChecked())
        self.panel_supertonic.setVisible(self.rb_engine_supertonic.isChecked())
        self.panel_kokoclone.setVisible(self.rb_engine_kokoclone.isChecked())

    def _sync_kokoro_submodes(self) -> None:
        self.box_mixer.setVisible(self.rb_mode_mixer.isChecked())
        self.box_recipe.setVisible(self.rb_mode_recipe.isChecked())
        self.box_single.setVisible(self.rb_mode_single.isChecked())

    def _on_pocket_voice_changed(self) -> None:
        is_clone = str(self.combo_pocket_voice.currentData()) == "clone"
        self.line_pocket_wav.setEnabled(is_clone)
        self.btn_browse_pocket_wav.setEnabled(is_clone)

    def _on_kokoclone_preset_changed(self) -> None:
        val = str(self.combo_kokoclone_preset.currentData())
        if val != "custom" and val:
            self.line_kokoclone_wav.setText(val)
            self._extract_kokoclone_metrics()

    def _browse_pocket_wav(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Voice Sample (.wav)", "", "Audio Files (*.wav);;All Files (*)"
        )
        if p:
            self.line_pocket_wav.setText(p)

    def _browse_kokoclone_wav(self) -> None:
        p, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Audio Clip (.wav)", "", "Audio Files (*.wav);;All Files (*)"
        )
        if p:
            self.line_kokoclone_wav.setText(p)
            self._extract_kokoclone_metrics()

    def _extract_kokoclone_metrics(self) -> None:
        wav_path = self.line_kokoclone_wav.text().strip()
        if not wav_path or not Path(wav_path).exists():
            self.lbl_kokoclone_metrics.setText("⚠️ Please select a valid .wav file first.")
            return

        meta = get_kokoclone_metadata(wav_path)
        if "error" in meta:
            self.lbl_kokoclone_metrics.setText(f"❌ Error: {meta['error']}")
            return

        dur = meta.get("duration_s", 0.0)
        f0 = meta.get("f0", 0.0)
        cent = meta.get("centroid", 0.0)
        self.lbl_kokoclone_metrics.setText(
            f"✓ Analyzed {dur}s: Pitch F0={f0}Hz, Centroid={cent}Hz -> 512-dim style vector ready."
        )

    def _preview_text_normalization(self) -> None:
        raw = self.line_test_text.text().strip()
        normalized = normalize_text(raw)
        self.lbl_norm_preview.setText(f"Preview: \"{normalized[:80]}...\"" if len(normalized) > 80 else f"Preview: \"{normalized}\"")

    def _load_sample_norm(self) -> None:
        self.line_test_text.setText(
            "The RTX 5080 GPU cost $1,250.50 on 2026-10-03 with 99.5% accuracy and 16 GB VRAM. Dr. Lucca finished 1st!"
        )
        self._preview_text_normalization()

    def _load_sample_ja(self) -> None:
        self.line_test_text.setText(
            "Sugoi! The compilation succeeded in 12 ms! Arigatou gozaimasu, partner!"
        )

    def _load_sample_eng(self) -> None:
        self.line_test_text.setText(
            "All systems operational! The upgraded pipeline is online and ready for our next experiment."
        )

    def _apply_anime_heroine_preset(self) -> None:
        self.rb_engine_kokoro.setChecked(True)
        self.rb_mode_mixer.setChecked(True)
        idx_a = self.combo_voice_a.findData("af_bella")
        if idx_a >= 0:
            self.combo_voice_a.setCurrentIndex(idx_a)
        idx_b = self.combo_voice_b.findData("af_sarah")
        if idx_b >= 0:
            self.combo_voice_b.setCurrentIndex(idx_b)
        self.slider_blend.setValue(70)
        self.slider_speed.setValue(120)
        self._update_blend_formula()
        self._load_sample_eng()
        self.lbl_voice_status.setText("Applied Kokoro: Anime Heroine (70% af_bella + 30% af_sarah @ 1.20x).")

    def _apply_kittentts_preset(self) -> None:
        self.rb_engine_kitten.setChecked(True)
        self.combo_kitten_variant.setCurrentIndex(0)  # Mini 80M
        idx = self.combo_kitten_voice.findData("sarah")
        if idx >= 0:
            self.combo_kitten_voice.setCurrentIndex(idx)
        self.combo_kitten_quant.setCurrentIndex(0)    # INT8
        self.slider_speed.setValue(110)
        self._load_sample_norm()
        self.lbl_voice_status.setText("Applied KittenTTS Mini: Sarah (80M INT8 CPU ONNX with Text Normalizer).")

    def _apply_pocket_tts_preset(self) -> None:
        self.rb_engine_pocket.setChecked(True)
        idx = self.combo_pocket_voice.findData("alba")
        if idx >= 0:
            self.combo_pocket_voice.setCurrentIndex(idx)
        self.combo_pocket_profile.setCurrentIndex(0)
        self.slider_pocket_latency.setValue(40)
        self.slider_speed.setValue(115)
        self._load_sample_eng()
        self.lbl_voice_status.setText("Applied Pocket TTS: Kyutai Alba (Edge-Streaming Voice, 40ms buffer).")

    def _apply_supertonic3_preset(self) -> None:
        self.rb_engine_supertonic.setChecked(True)
        idx_v = self.combo_supertonic_voice.findData("asuka_tsundere")
        if idx_v >= 0:
            self.combo_supertonic_voice.setCurrentIndex(idx_v)
        self.combo_supertonic_mode.setCurrentIndex(0)  # Auto
        self.chk_supertonic_smooth.setChecked(True)
        self.slider_speed.setValue(115)
        self._load_sample_ja()
        self.lbl_voice_status.setText("Applied Supertonic 3: Asuka Soryu (Trilingual Tsundere with Phoneme Smoothing).")

    def _apply_kokoclone_preset(self) -> None:
        self.rb_engine_kokoclone.setChecked(True)
        self.combo_kokoclone_preset.setCurrentIndex(0)  # Asuka studio clean
        self.slider_speed.setValue(110)
        self._load_sample_eng()
        self._on_kokoclone_preset_changed()
        self.lbl_voice_status.setText(
            "Applied KokoClone: Asuka Langley Soryu (Full Uncut Studio Master — 45s)."
        )

    def _update_blend_formula(self) -> None:
        v_a = str(self.combo_voice_a.currentData())
        v_b = str(self.combo_voice_b.currentData())
        val = self.slider_blend.value()
        w_a = val / 100.0
        w_b = (100 - val) / 100.0
        self.lbl_blend_ratio.setText(f"{val}% A / {100 - val}% B")
        self.line_blend_formula.setText(f"blend:{w_a:.2f}*{v_a}+{w_b:.2f}*{v_b}")

    def _load_initial_voice(self, cur_voice: str) -> None:
        raw = str(cur_voice or "").strip()
        eng_id, sub = parse_engine_from_spec(raw)

        if eng_id == "kittentts":
            self.rb_engine_kitten.setChecked(True)
            if "nano" in sub:
                self.combo_kitten_variant.setCurrentIndex(1)
            else:
                self.combo_kitten_variant.setCurrentIndex(0)
            for v_key in KITTEN_VOICES:
                if v_key in sub:
                    idx = self.combo_kitten_voice.findData(v_key)
                    if idx >= 0:
                        self.combo_kitten_voice.setCurrentIndex(idx)
                    break
        elif eng_id == "pocket_tts":
            self.rb_engine_pocket.setChecked(True)
            if "clone:" in sub:
                idx = self.combo_pocket_voice.findData("clone")
                if idx >= 0:
                    self.combo_pocket_voice.setCurrentIndex(idx)
                self.line_pocket_wav.setText(sub.split("clone:", 1)[1])
            else:
                for v_key in POCKET_VOICES:
                    if v_key in sub:
                        idx = self.combo_pocket_voice.findData(v_key)
                        if idx >= 0:
                            self.combo_pocket_voice.setCurrentIndex(idx)
                        break
        elif eng_id == "supertonic3":
            self.rb_engine_supertonic.setChecked(True)
            for v_key in SUPERTONIC_VOICES:
                if v_key in sub:
                    idx_v = self.combo_supertonic_voice.findData(v_key)
                    if idx_v >= 0:
                        self.combo_supertonic_voice.setCurrentIndex(idx_v)
                    break
            for m in ("ja", "zh", "eu"):
                if f":{m}" in sub or sub.endswith(m):
                    idx_m = self.combo_supertonic_mode.findData(m)
                    if idx_m >= 0:
                        self.combo_supertonic_mode.setCurrentIndex(idx_m)
                    break
        elif eng_id == "kokoclone":
            self.rb_engine_kokoclone.setChecked(True)
            self.line_kokoclone_wav.setText(sub)
            for i in range(self.combo_kokoclone_preset.count()):
                if self.combo_kokoclone_preset.itemData(i) == sub:
                    self.combo_kokoclone_preset.setCurrentIndex(i)
                    break
            if sub and Path(sub).exists():
                self._extract_kokoclone_metrics()
        else:
            # Kokoro
            self.rb_engine_kokoro.setChecked(True)
            if raw.startswith("blend:") or "+" in raw:
                self.rb_mode_mixer.setChecked(True)
                self.line_blend_formula.setText(raw)
            elif raw in VOICE_RECIPES:
                self.rb_mode_recipe.setChecked(True)
                idx_r = self.combo_recipe.findData(raw)
                if idx_r >= 0:
                    self.combo_recipe.setCurrentIndex(idx_r)
            else:
                self.rb_mode_single.setChecked(True)
                clean_single = VOICE_ALIASES.get(raw, raw)
                idx_s = self.combo_single_voice.findData(clean_single)
                if idx_s >= 0:
                    self.combo_single_voice.setCurrentIndex(idx_s)

        self._sync_engine_panels()

    def get_selected_voice_spec(self) -> str:
        """Returns the canonical serialized voice specification string."""
        if self.rb_engine_kitten.isChecked():
            var = str(self.combo_kitten_variant.currentData())
            v_key = str(self.combo_kitten_voice.currentData())
            quant = str(self.combo_kitten_quant.currentData())
            return f"kittentts:{var}:{v_key}:{quant}"
        elif self.rb_engine_pocket.isChecked():
            v_key = str(self.combo_pocket_voice.currentData())
            if v_key == "clone":
                wav_p = self.line_pocket_wav.text().strip()
                return f"pocket_tts:clone:{wav_p}" if wav_p else "pocket_tts:stream:warm"
            return f"pocket_tts:{v_key}"
        elif self.rb_engine_supertonic.isChecked():
            v_key = str(self.combo_supertonic_voice.currentData())
            mode = str(self.combo_supertonic_mode.currentData())
            return f"supertonic3:{v_key}:{mode}"
        elif self.rb_engine_kokoclone.isChecked():
            wav_p = self.line_kokoclone_wav.text().strip()
            return f"kokoclone:{wav_p}" if wav_p else "kokoclone"
        else:
            # Kokoro-82M
            if self.rb_mode_mixer.isChecked():
                return self.line_blend_formula.text().strip()
            elif self.rb_mode_recipe.isChecked():
                return str(self.combo_recipe.currentData())
            else:
                return str(self.combo_single_voice.currentData())

    def _on_status_updated(self, msg: str) -> None:
        self.lbl_voice_status.setText(msg)

    def _on_test_done(self, success: bool, msg: str) -> None:
        self.lbl_voice_status.setText(msg)
        self.btn_test_speech.setEnabled(True)

    def _play_samples(self, samples: np.ndarray, sr: int = 24000) -> None:
        try:
            from lucca.senses.ring_buffer import PLAY_RING_NAME, SharedAudioRing

            ring = SharedAudioRing(PLAY_RING_NAME)
            samples_i16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
            ring.write(samples_i16)
            return
        except Exception as ring_exc:
            _LOG.debug("ring_write_failed_fallback_sd: %s", ring_exc)

        try:
            sd.play(samples, sr)
            sd.wait()
        except Exception as exc:
            _LOG.debug("sounddevice_play_failed: %s", exc)

    def _test_voice_sample(self) -> None:
        voice = self.get_selected_voice_spec()
        speed = self.slider_speed.value() / 100.0
        raw_text = self.line_test_text.text().strip() or "Testing voice synthesis!"
        eng_id, subspec = parse_engine_from_spec(voice)

        self.lbl_voice_status.setText(f"Synthesizing with {ENGINE_CATALOG[eng_id].name}...")
        self.btn_test_speech.setEnabled(False)

        def worker() -> None:
            try:
                engine = get_voice_engine(eng_id)
                ref_wav = ""
                if eng_id == "kokoclone":
                    ref_wav = self.line_kokoclone_wav.text().strip()
                elif eng_id == "pocket_tts" and "clone:" in subspec:
                    ref_wav = self.line_pocket_wav.text().strip()

                samples, sr = engine.synthesize(
                    raw_text,
                    voice_spec=subspec,
                    speed=speed,
                    ref_audio_path=ref_wav,
                )

                if samples is not None and len(samples) > 0:
                    self._play_samples(samples, sr)
                    desc = ENGINE_CATALOG[eng_id].name
                    self.signals.test_done.emit(True, f"✓ {desc} playback successful ({sr} Hz).")
                else:
                    self.signals.test_done.emit(False, "Engine produced empty audio.")
            except Exception as exc:
                _LOG.debug("speech_test_failed: %s", exc)
                self.signals.test_done.emit(False, f"Error: {exc}")

        threading.Thread(target=worker, daemon=True).start()
