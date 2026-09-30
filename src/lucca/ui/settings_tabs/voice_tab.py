"""
Project Lucca — Voice Blender & CosyVoice 3 Studio Tab
WO-18e (F-ARCH-104), WO-27, Spec 07 §5, Spec 16 §4
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Final

import kokoro_onnx
import sounddevice as sd
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
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

from lucca.core.affective_ode import DiscreteStance
from lucca.senses.tts import (
    VOICE_ALIASES,
    VOICE_RECIPES,
    enhance_anime_expressive_punctuation,
    get_available_voices,
    parse_voice_blend,
)
from lucca.speech.cosyvoice_client import CosyVoice3Client, format_cosyvoice_instruct
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = logging.getLogger(__name__)


class VoiceTabSignals(QObject):
    """Thread-safe signal bridge marshaling background synthesis updates to the Qt main thread."""

    status_updated = pyqtSignal(str)
    audition_done = pyqtSignal(bool, str)
    test_done = pyqtSignal(bool, str)


# 15 Canonical PAD Stances mapped to descriptive UI labels and emotion tags
STANCE_SPECS: Final[list[tuple[str, str, str]]] = [
    ("neutral_steady", "Steady & Balanced (Resting / Baseline)", "steady, balanced, neutral"),
    ("focused_analytical", "Focused & Analytical (Calculations / Systems)", "focused, precise, intellectual"),
    ("calm_relaxed", "Calm & Relaxed (Smooth / Reflective)", "calm, relaxed, smooth"),
    ("energetic_supportive", "Energetic & Supportive (Encouraging / Warm)", "warm, energetic, encouraging"),
    ("guarded_cautious", "Guarded & Cautious (Security / Vigilant)", "cautious, guarded, vigilant"),
    ("subdued_reflective", "Subdued & Reflective (Pensive / Thoughtful)", "subdued, reflective, quiet"),
    ("commanding_protective", "Commanding & Protective (Firm / Safety Override)", "commanding, protective, firm"),
    ("playful_teasing", "Playful & Teasing (Spirited / Witty)", "playful, witty, tsundere teasing"),
    ("eureka_wonder", "Eureka & Wonder (Epiphany / Discovery)", "wonder, awe, eureka epiphany"),
    ("intimate_whisper", "Intimate Whisper (Soft / Gentle Companion)", "intimate, gentle, soft whisper"),
    ("righteous_anger", "Righteous Anger (Indignant / Fierce Reprimand)", "indignant, sharp, fierce reprimand"),
    ("defiant_stubborn", "Defiant & Stubborn (Resolute / Unyielding)", "defiant, stubborn, resolute"),
    ("system_alarm", "System Alarm (Urgent / High-Stress)", "alarmed, urgent, stressed"),
    ("visceral_disgust", "Visceral Disgust (Disdainful / Contemptuous)", "disdainful, contemptuous, cold"),
    ("grief_dejection", "Grief & Dejection (Helpless / Sorrowful)", "dejected, sorrowful, helpless"),
]


class VoiceTab(QWidget):
    """Tab 1: Voice Blender & CosyVoice 3 Frontier Studio."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade

        self.signals = VoiceTabSignals()
        self.signals.status_updated.connect(self._on_status_updated)
        self.signals.audition_done.connect(self._on_audition_done)
        self.signals.test_done.connect(self._on_test_done)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Quick Bar
        grp_preset = QGroupBox("Quick-Switch Canonical Voice Presets", self)
        h_pres = QHBoxLayout(grp_preset)

        btn_cosy_inventor = QPushButton("⚡ Lucca: Tech Inventor (CosyVoice 3)", grp_preset)
        btn_cosy_inventor.setStyleSheet("color: #00e5ff; font-weight: bold;")
        btn_cosy_inventor.clicked.connect(self._apply_cosyvoice_inventor_preset)
        h_pres.addWidget(btn_cosy_inventor)

        btn_cosy_companion = QPushButton("🌸 Lucca: Warm Companion (CosyVoice 3)", grp_preset)
        btn_cosy_companion.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        btn_cosy_companion.clicked.connect(self._apply_cosyvoice_companion_preset)
        h_pres.addWidget(btn_cosy_companion)

        btn_anime_heroine = QPushButton("✨ English Anime Heroine (Kokoro)", grp_preset)
        btn_anime_heroine.setStyleSheet("color: #a0aec0; font-weight: bold;")
        btn_anime_heroine.clicked.connect(self._apply_anime_heroine_preset)
        h_pres.addWidget(btn_anime_heroine)

        h_pres.addStretch()
        layout.addWidget(grp_preset)

        # Mode Selection
        grp_mode = QGroupBox("Voice Architecture & Synthesis Engine", self)
        h_mode = QHBoxLayout(grp_mode)
        self.rb_mode_cosyvoice = QRadioButton("CosyVoice 3 Frontier Neural Engine", grp_mode)
        self.rb_mode_recipe = QRadioButton("Kokoro Recipe Preset", grp_mode)
        self.rb_mode_single = QRadioButton("Single Kokoro Vector", grp_mode)
        self.rb_mode_mixer = QRadioButton("Dual-Vector Tensor Mixer", grp_mode)

        h_mode.addWidget(self.rb_mode_cosyvoice)
        h_mode.addWidget(self.rb_mode_recipe)
        h_mode.addWidget(self.rb_mode_single)
        h_mode.addWidget(self.rb_mode_mixer)
        layout.addWidget(grp_mode)

        # -------------------------------------------------------------
        # Container 0: CosyVoice 3 Frontier Panel
        # -------------------------------------------------------------
        self.panel_cosyvoice = QGroupBox("CosyVoice 3 Frontier Neural Diffusion Studio", self)
        f_cosy = QFormLayout(self.panel_cosyvoice)

        self.combo_cosyvoice_preset = QComboBox(self.panel_cosyvoice)
        self.combo_cosyvoice_preset.addItem("⚡ Lucca: Tech Inventor (Expressive, Inquisitive)", "cosyvoice3:inventor")
        self.combo_cosyvoice_preset.addItem("🌸 Lucca: Warm Companion (Gentle, Natural)", "cosyvoice3:companion")
        self.combo_cosyvoice_preset.addItem("🔥 Lucca: Energetic Heroine (High Dynamic Range)", "cosyvoice3:heroine")
        self.combo_cosyvoice_preset.addItem("🎙️ Custom Reference Audio (.wav Voice Clone)", "cosyvoice3:custom")
        self.combo_cosyvoice_preset.currentIndexChanged.connect(self._on_cosyvoice_preset_changed)
        f_cosy.addRow("Voice Profile:", self.combo_cosyvoice_preset)

        # Custom Audio Sample File Picker Row
        h_custom_wav = QHBoxLayout()
        self.line_custom_wav = QLineEdit(self.panel_cosyvoice)
        self.line_custom_wav.setPlaceholderText("Path to 3-10s clean reference .wav file...")
        self.btn_browse_wav = QPushButton("Browse .wav", self.panel_cosyvoice)
        self.btn_browse_wav.clicked.connect(self._browse_custom_wav)
        h_custom_wav.addWidget(self.line_custom_wav)
        h_custom_wav.addWidget(self.btn_browse_wav)
        f_cosy.addRow("Custom Voice Sample:", h_custom_wav)

        # 3D PAD Affective Stance Audition Section
        self.cb_affect_enabled = QCheckBox("Enable Continuous 3D PAD Emotional Dynamics", self.panel_cosyvoice)
        self.cb_affect_enabled.setChecked(True)
        f_cosy.addRow("Affective ODE:", self.cb_affect_enabled)

        h_stance = QHBoxLayout()
        self.combo_stance = QComboBox(self.panel_cosyvoice)
        for s_id, s_desc, s_tag in STANCE_SPECS:
            self.combo_stance.addItem(f"{s_id.replace('_', ' ').title()}: {s_desc}", (s_id, s_tag))
        self.btn_audition_stance = QPushButton("▶️ Audition Stance", self.panel_cosyvoice)
        self.btn_audition_stance.clicked.connect(self._audition_active_stance)
        h_stance.addWidget(self.combo_stance)
        h_stance.addWidget(self.btn_audition_stance)
        f_cosy.addRow("15-Stance Emotional Audition:", h_stance)

        layout.addWidget(self.panel_cosyvoice)

        # -------------------------------------------------------------
        # Kokoro Legacy Panels
        # -------------------------------------------------------------
        all_installed = get_available_voices()
        pure_voices = [v for v in all_installed if v not in VOICE_RECIPES]

        # Container 1: Single Native Voice
        self.panel_single = QGroupBox("Single Voice Selector (Kokoro 512-dim)", self)
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

        f_mixer.addRow("Primary Voice (A):", self.combo_voice_a)
        f_mixer.addRow("Secondary Voice (B):", self.combo_voice_b)

        h_slider = QHBoxLayout()
        self.slider_blend = QSlider(Qt.Orientation.Horizontal, self.panel_mixer)
        self.slider_blend.setRange(0, 100)
        self.slider_blend.setValue(70)
        self.lbl_blend_ratio = QLabel("70% A / 30% B", self.panel_mixer)
        self.lbl_blend_ratio.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        h_slider.addWidget(self.slider_blend)
        h_slider.addWidget(self.lbl_blend_ratio)
        f_mixer.addRow("Linear Weighting:", h_slider)

        self.line_blend_formula = QLineEdit(self.panel_mixer)
        self.line_blend_formula.setReadOnly(True)
        f_mixer.addRow("Computed Vector Spec:", self.line_blend_formula)

        self.combo_voice_a.currentIndexChanged.connect(self._update_blend_formula)
        self.combo_voice_b.currentIndexChanged.connect(self._update_blend_formula)
        self.slider_blend.valueChanged.connect(self._update_blend_formula)
        self._update_blend_formula()
        layout.addWidget(self.panel_mixer)

        # Mode Radio Button sync
        self.rb_mode_cosyvoice.toggled.connect(self._sync_voice_mode_ui)
        self.rb_mode_single.toggled.connect(self._sync_voice_mode_ui)
        self.rb_mode_recipe.toggled.connect(self._sync_voice_mode_ui)
        self.rb_mode_mixer.toggled.connect(self._sync_voice_mode_ui)

        # Initial selection based on active config
        cur_voice = getattr(self.dialog, "current_voice", "cosyvoice3:inventor")
        if "cosyvoice" in str(cur_voice).lower() or cur_voice in ("inventor", "lucca"):
            self.rb_mode_cosyvoice.setChecked(True)
            if "custom" in cur_voice:
                self.combo_cosyvoice_preset.setCurrentIndex(3)
                parts = cur_voice.split("custom:", 1)
                if len(parts) > 1:
                    self.line_custom_wav.setText(parts[1])
            elif "companion" in cur_voice:
                self.combo_cosyvoice_preset.setCurrentIndex(1)
            elif "heroine" in cur_voice:
                self.combo_cosyvoice_preset.setCurrentIndex(2)
            else:
                self.combo_cosyvoice_preset.setCurrentIndex(0)
        elif cur_voice.startswith("blend:") or "+" in cur_voice:
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
            "All systems operational! The upgraded pipeline is online and ready for our next experiment.",
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

    def _on_cosyvoice_preset_changed(self) -> None:
        is_custom = self.combo_cosyvoice_preset.currentIndex() == 3
        self.line_custom_wav.setEnabled(is_custom)
        self.btn_browse_wav.setEnabled(is_custom)

    def _browse_custom_wav(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Voice Sample (.wav)",
            "",
            "Audio Files (*.wav);;All Files (*)",
        )
        if file_path:
            self.line_custom_wav.setText(file_path)

    def _apply_cosyvoice_inventor_preset(self) -> None:
        self.rb_mode_cosyvoice.setChecked(True)
        self.combo_cosyvoice_preset.setCurrentIndex(0)
        self.slider_speed.setValue(105)
        self.line_test_text.setText("All systems operational! The upgraded pipeline is online and ready for our next experiment.")
        self._sync_voice_mode_ui()
        self.lbl_voice_status.setText("Applied Lucca: Tech Inventor (CosyVoice 3 Frontier Engine).")

    def _apply_cosyvoice_companion_preset(self) -> None:
        self.rb_mode_cosyvoice.setChecked(True)
        self.combo_cosyvoice_preset.setCurrentIndex(1)
        self.slider_speed.setValue(100)
        self.line_test_text.setText("I'm right here with you. Take all the time you need, we'll figure it out together.")
        self._sync_voice_mode_ui()
        self.lbl_voice_status.setText("Applied Lucca: Warm Companion (CosyVoice 3 Frontier Engine).")

    def _apply_anime_heroine_preset(self) -> None:
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
        self.lbl_voice_status.setText(
            "Applied English Anime Heroine Preset (70% af_bella + 30% af_sarah @ 1.20x)."
        )

    def _sync_voice_mode_ui(self) -> None:
        self.panel_cosyvoice.setVisible(self.rb_mode_cosyvoice.isChecked())
        self.panel_single.setVisible(self.rb_mode_single.isChecked())
        self.panel_recipe.setVisible(self.rb_mode_recipe.isChecked())
        self.panel_mixer.setVisible(self.rb_mode_mixer.isChecked())
        self._on_cosyvoice_preset_changed()

    def _update_blend_formula(self) -> None:
        v_a = str(self.combo_voice_a.currentData())
        v_b = str(self.combo_voice_b.currentData())
        val = self.slider_blend.value()
        w_a = val / 100.0
        w_b = (100 - val) / 100.0
        self.lbl_blend_ratio.setText(f"{val}% A / {100 - val}% B")
        self.line_blend_formula.setText(f"blend:{w_a:.2f}*{v_a}+{w_b:.2f}*{v_b}")

    def get_selected_voice_spec(self) -> str:
        if self.rb_mode_cosyvoice.isChecked():
            preset_idx = self.combo_cosyvoice_preset.currentIndex()
            if preset_idx == 3:
                custom_p = self.line_custom_wav.text().strip()
                return f"cosyvoice3:custom:{custom_p}" if custom_p else "cosyvoice3:inventor"
            return str(self.combo_cosyvoice_preset.currentData())
        elif self.rb_mode_mixer.isChecked():
            return self.line_blend_formula.text().strip()
        elif self.rb_mode_recipe.isChecked():
            return str(self.combo_recipe.currentData())
        else:
            return str(self.combo_single_voice.currentData())

    def _on_status_updated(self, msg: str) -> None:
        self.lbl_voice_status.setText(msg)

    def _on_audition_done(self, success: bool, msg: str) -> None:
        self.lbl_voice_status.setText(msg)
        self.btn_audition_stance.setEnabled(True)

    def _on_test_done(self, success: bool, msg: str) -> None:
        self.lbl_voice_status.setText(msg)
        self.btn_test_speech.setEnabled(True)

    def _audition_active_stance(self) -> None:
        """Auditions the selected 3D PAD emotional stance."""
        stance_data = self.combo_stance.currentData()
        if not stance_data:
            return
        stance_id, stance_tag = stance_data
        speed = self.slider_speed.value() / 100.0
        raw_text = self.line_test_text.text().strip() or "All systems operational!"
        preset_idx = self.combo_cosyvoice_preset.currentIndex()
        profile_key = "inventor"
        if preset_idx == 1:
            profile_key = "companion"
        elif preset_idx == 2:
            profile_key = "heroine"

        custom_wav = self.line_custom_wav.text().strip() if preset_idx == 3 else None
        instruct = format_cosyvoice_instruct("Lucca", stance_tag, profile=profile_key)

        self.lbl_voice_status.setText(f"Auditioning stance '{stance_id}' ({stance_tag})...")
        self.btn_audition_stance.setEnabled(False)

        def worker() -> None:
            try:
                cv_client = CosyVoice3Client.get_instance()
                samples, sr = cv_client.test_audio(
                    text=raw_text,
                    instruct=instruct,
                    prompt_wav=custom_wav,
                    speed=speed,
                )
                if samples is not None and len(samples) > 0:
                    self._play_samples(samples, sr)
                    self.signals.audition_done.emit(True, f"✓ Audition '{stance_id}' successful.")
                else:
                    self.signals.audition_done.emit(False, "CosyVoice 3 returned empty audio.")
            except Exception as exc:
                _LOG.debug("stance_audition_failed: %s", exc)
                self.signals.audition_done.emit(False, f"Error: {exc}")

        threading.Thread(target=worker, daemon=True).start()

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
        text = enhance_anime_expressive_punctuation(raw_text)
        preset_idx = self.combo_cosyvoice_preset.currentIndex()
        custom_wav = self.line_custom_wav.text().strip() if (preset_idx == 3 or "custom:" in voice) else None

        self.lbl_voice_status.setText("Synthesizing voice sample...")
        self.btn_test_speech.setEnabled(False)

        def worker() -> None:
            try:
                if "cosyvoice" in voice.lower():
                    # CosyVoice 3 Frontier Synthesis
                    cv_client = CosyVoice3Client.get_instance()
                    profile_key = "inventor"
                    if "companion" in voice:
                        profile_key = "companion"
                    elif "heroine" in voice:
                        profile_key = "heroine"

                    instruct = format_cosyvoice_instruct("Lucca", "warm, energetic, encouraging", profile=profile_key)
                    samples, sr = cv_client.test_audio(
                        text=text,
                        instruct=instruct,
                        prompt_wav=custom_wav,
                        speed=speed,
                    )
                    if samples is not None and len(samples) > 0:
                        self._play_samples(samples, sr)
                        self.signals.test_done.emit(True, "✓ CosyVoice 3 playback successful.")
                    else:
                        self.signals.test_done.emit(False, "CosyVoice 3 returned empty audio.")
                    return

                # Kokoro ONNX Synthesis
                model_p = Path("C:/ProjectLucca/models/tts/kokoro-v1.0.onnx")
                voices_p = Path("C:/ProjectLucca/models/tts/voices-v1.0.bin")
                if not model_p.exists() or not voices_p.exists():
                    self.signals.test_done.emit(False, "Models not found on disk.")
                    return

                engine = kokoro_onnx.Kokoro(str(model_p), str(voices_p))
                clean_voice = VOICE_ALIASES.get(voice, voice)
                resolved = parse_voice_blend(engine, clean_voice)
                samples, sr = engine.create(text, voice=resolved, speed=speed)

                self._play_samples(samples, sr)
                self.signals.test_done.emit(True, "✓ Kokoro playback successful.")
            except Exception as exc:
                _LOG.debug("speech_test_failed: %s", exc)
                self.signals.test_done.emit(False, f"Error: {exc}")

        threading.Thread(target=worker, daemon=True).start()
