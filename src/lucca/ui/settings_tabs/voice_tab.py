"""
Project Lucca — Voice Blender Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import kokoro_onnx
import sounddevice as sd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
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
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = logging.getLogger(__name__)


class VoiceTab(QWidget):
    """Tab 1: Voice Blender & Mixing (All 54 Kokoro Voices & Anime Presets)."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Anime Preset Quick Bar
        grp_preset = QGroupBox("Quick-Switch Canonical Presets", self)
        h_pres = QHBoxLayout(grp_preset)
        btn_anime_heroine = QPushButton("✨ English Anime Heroine", grp_preset)
        btn_anime_heroine.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        btn_anime_heroine.clicked.connect(self._apply_anime_heroine_preset)
        h_pres.addWidget(btn_anime_heroine)

        btn_asuka = QPushButton("🔴 Asuka Langley Soryu (RVC v2)", grp_preset)
        btn_asuka.setStyleSheet("color: #ff4d4f; font-weight: bold;")
        btn_asuka.clicked.connect(self._apply_asuka_preset)
        h_pres.addWidget(btn_asuka)

        lbl_pres_note = QLabel(
            "Quick-switch between standard anime blend and Asuka RVC neural voice.",
            grp_preset,
        )
        lbl_pres_note.setStyleSheet("color: #a0aec0; font-size: 11px;")
        h_pres.addWidget(lbl_pres_note)
        h_pres.addStretch()
        layout.addWidget(grp_preset)

        # Mode Selection
        grp_mode = QGroupBox("Voice Architecture & Vector Generation Mode", self)
        h_mode = QHBoxLayout(grp_mode)
        self.rb_mode_single = QRadioButton("Single Native Voice", grp_mode)
        self.rb_mode_recipe = QRadioButton("Anime Recipe Preset", grp_mode)
        self.rb_mode_mixer = QRadioButton("Dual-Vector Tensor Mixer", grp_mode)
        h_mode.addWidget(self.rb_mode_single)
        h_mode.addWidget(self.rb_mode_recipe)
        h_mode.addWidget(self.rb_mode_mixer)
        layout.addWidget(grp_mode)

        all_installed = get_available_voices()
        pure_voices = [v for v in all_installed if v not in VOICE_RECIPES]

        # Container 1: Single Native Voice
        self.panel_single = QGroupBox(
            "Single Voice Selector (All Installed Kokoro Vectors)", self
        )
        f_single = QFormLayout(self.panel_single)
        self.combo_single_voice = QComboBox(self.panel_single)
        for v in pure_voices:
            self.combo_single_voice.addItem(f"{v} (Kokoro 512-dim)", v)
        f_single.addRow("Installed Voice:", self.combo_single_voice)
        layout.addWidget(self.panel_single)

        # Container 2: Canonical Anime Recipe
        self.panel_recipe = QGroupBox("Canonical Anime Voice Blends", self)
        f_recipe = QFormLayout(self.panel_recipe)
        self.combo_recipe = QComboBox(self.panel_recipe)
        for r_name, r_formula in VOICE_RECIPES.items():
            if r_name == "asuka":
                label = "🔴 Asuka Langley Soryu (RVC v2 Neural Voice @ +6st)"
            else:
                label = f"{r_name.replace('_', ' ').title()} ({r_formula})"
            self.combo_recipe.addItem(label, r_name)
        f_recipe.addRow("Recipe Preset:", self.combo_recipe)
        layout.addWidget(self.panel_recipe)

        # Container 3: Dual-Vector Tensor Voice Mixer
        self.panel_mixer = QGroupBox("Dual-Vector Linear Tensor Combination Studio", self)
        f_mixer = QFormLayout(self.panel_mixer)

        self.combo_voice_a = QComboBox(self.panel_mixer)
        self.combo_voice_b = QComboBox(self.panel_mixer)
        for v in pure_voices:
            self.combo_voice_a.addItem(v, v)
            self.combo_voice_b.addItem(v, v)

        idx_a = self.combo_voice_a.findData("af_bella")
        if idx_a < 0:
            idx_a = self.combo_voice_a.findData("af_sky")
        if idx_a >= 0:
            self.combo_voice_a.setCurrentIndex(idx_a)

        idx_b = self.combo_voice_b.findData("af_sarah")
        if idx_b < 0:
            idx_b = self.combo_voice_b.findData("jf_alpha")
        if idx_b >= 0:
            self.combo_voice_b.setCurrentIndex(idx_b)

        f_mixer.addRow("Primary Vector (Voice A):", self.combo_voice_a)
        f_mixer.addRow("Secondary Vector (Voice B):", self.combo_voice_b)

        h_blend = QHBoxLayout()
        self.slider_blend = QSlider(Qt.Orientation.Horizontal, self.panel_mixer)
        self.slider_blend.setRange(0, 100)
        self.slider_blend.setValue(70)
        self.lbl_blend_ratio = QLabel("70% A / 30% B", self.panel_mixer)
        self.lbl_blend_ratio.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        h_blend.addWidget(self.slider_blend)
        h_blend.addWidget(self.lbl_blend_ratio)
        f_mixer.addRow("Tensor Blend Ratio:", h_blend)

        self.line_blend_formula = QLineEdit("blend:0.70*af_bella+0.30*af_sarah", self.panel_mixer)
        self.line_blend_formula.setFont(QFont("Consolas", 10))
        f_mixer.addRow("Computed Synthesis Formula:", self.line_blend_formula)

        self.combo_voice_a.currentIndexChanged.connect(self._update_blend_formula)
        self.combo_voice_b.currentIndexChanged.connect(self._update_blend_formula)
        self.slider_blend.valueChanged.connect(self._update_blend_formula)

        layout.addWidget(self.panel_mixer)

        # Wire Mode Switches
        self.rb_mode_single.toggled.connect(self._sync_voice_mode_ui)
        self.rb_mode_recipe.toggled.connect(self._sync_voice_mode_ui)
        self.rb_mode_mixer.toggled.connect(self._sync_voice_mode_ui)

        # Determine initial mode from current_voice
        cur_voice = getattr(self.dialog, "current_voice", "genki_heroine")
        if cur_voice.startswith("blend:") or "+" in cur_voice:
            self.rb_mode_mixer.setChecked(True)
            self.line_blend_formula.setText(cur_voice)
        elif cur_voice in VOICE_RECIPES:
            self.rb_mode_recipe.setChecked(True)
            idx_r = self.combo_recipe.findData(cur_voice)
            if idx_r >= 0:
                self.combo_recipe.setCurrentIndex(idx_r)
        else:
            self.rb_mode_single.setChecked(True)
            idx_s = self.combo_single_voice.findData(cur_voice)
            if idx_s >= 0:
                self.combo_single_voice.setCurrentIndex(idx_s)
        self._sync_voice_mode_ui()

        # Pacing & Speed Multiplier
        grp_speed = QGroupBox("Speaking Pace & Audio Pacing", self)
        f_speed = QFormLayout(grp_speed)
        h_speed = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Orientation.Horizontal, grp_speed)
        self.slider_speed.setRange(60, 180)
        cur_speed = getattr(self.dialog, "current_speed", 1.05)
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

        # Test Synthesis Box
        grp_test = QGroupBox("Test Voice Playback & Audio Synthesis", self)
        v_test = QVBoxLayout(grp_test)
        self.line_test_text = QLineEdit(
            "Ah, Lucca here! Audio systems and voice blending are fully operational!",
            grp_test,
        )
        v_test.addWidget(self.line_test_text)

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

    def _apply_anime_heroine_preset(self) -> None:
        self.rb_mode_mixer.setChecked(True)
        idx_a = self.combo_voice_a.findData("af_bella")
        if idx_a >= 0:
            self.combo_voice_a.setCurrentIndex(idx_a)
        idx_b = self.combo_voice_b.findData("af_sarah")
        if idx_b >= 0:
            self.combo_voice_b.setCurrentIndex(idx_b)
        self.slider_blend.setValue(70)
        self.slider_speed.setValue(120)  # 1.20x speed
        self._update_blend_formula()
        self.lbl_voice_status.setText(
            "Applied English Anime Heroine Preset (70% af_bella + 30% af_sarah @ 1.20x)."
        )

    def _apply_asuka_preset(self) -> None:
        self.rb_mode_recipe.setChecked(True)
        idx_r = self.combo_recipe.findData("asuka")
        if idx_r >= 0:
            self.combo_recipe.setCurrentIndex(idx_r)
        self.slider_speed.setValue(105)  # 1.05x speed
        self.line_test_text.setText("Anta baka?! What took you so long to figure this out?")
        self.lbl_voice_status.setText(
            "Applied Asuka Langley Soryu Preset (RVC v2 + Kokoro 70% af_sky + 30% jf_alpha @ +6st)."
        )

    def _sync_voice_mode_ui(self) -> None:
        self.panel_single.setVisible(self.rb_mode_single.isChecked())
        self.panel_recipe.setVisible(self.rb_mode_recipe.isChecked())
        self.panel_mixer.setVisible(self.rb_mode_mixer.isChecked())

    def _update_blend_formula(self) -> None:
        v_a = str(self.combo_voice_a.currentData())
        v_b = str(self.combo_voice_b.currentData())
        val = self.slider_blend.value()
        w_a = val / 100.0
        w_b = (100 - val) / 100.0
        self.lbl_blend_ratio.setText(f"{val}% A / {100 - val}% B")
        self.line_blend_formula.setText(f"blend:{w_a:.2f}*{v_a}+{w_b:.2f}*{v_b}")

    def get_selected_voice_spec(self) -> str:
        if self.rb_mode_mixer.isChecked():
            return self.line_blend_formula.text().strip()
        elif self.rb_mode_recipe.isChecked():
            return str(self.combo_recipe.currentData())
        else:
            return str(self.combo_single_voice.currentData())

    def _test_voice_sample(self) -> None:
        voice = self.get_selected_voice_spec()
        speed = self.slider_speed.value() / 100.0
        raw_text = self.line_test_text.text().strip() or "Testing Kokoro synthesis!"
        text = enhance_anime_expressive_punctuation(raw_text)

        self.lbl_voice_status.setText("Synthesizing voice sample...")
        self.btn_test_speech.setEnabled(False)

        def worker() -> None:
            try:
                model_p = Path("C:/ProjectLucca/models/tts/kokoro-v1.0.onnx")
                voices_p = Path("C:/ProjectLucca/models/tts/voices-v1.0.bin")
                if not model_p.exists() or not voices_p.exists():
                    self.lbl_voice_status.setText("Models not found on disk.")
                    return

                engine = kokoro_onnx.Kokoro(str(model_p), str(voices_p))
                clean_voice = VOICE_ALIASES.get(voice, voice)
                resolved = parse_voice_blend(engine, clean_voice)
                samples, sr = engine.create(text, voice=resolved, speed=speed)

                # If Asuka voice selected, run through Asuka RVC converter
                if voice in ("asuka", "asuka_langley") or "asuka" in str(voice).lower():
                    try:
                        from lucca.speech.rvc.converter import get_asuka_converter

                        conv = get_asuka_converter()
                        samples = conv.convert(samples, orig_sr=sr, out_sr=sr)
                    except Exception as rvc_exc:
                        _LOG.debug("asuka_test_convert_failed: %s", rvc_exc)

                sd.play(samples, sr)
                sd.wait()
                self.lbl_voice_status.setText("✓ Audio playback successful.")
            except Exception as exc:
                _LOG.debug("speech_test_failed: %s", exc)
                self.lbl_voice_status.setText(f"Error: {exc}")
            finally:
                self.btn_test_speech.setEnabled(True)

        threading.Thread(target=worker, daemon=True).start()
