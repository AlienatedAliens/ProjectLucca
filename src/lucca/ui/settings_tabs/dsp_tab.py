"""
Project Lucca — Granular DSP Audio Post-Processing Suite Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import kokoro_onnx
import numpy as np
import sounddevice as sd
import structlog
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lucca.senses.dsp_chain import AnimeDSPConfig, AnimeVoiceDSP
from lucca.senses.tts import VOICE_ALIASES, parse_voice_blend
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = structlog.get_logger(__name__)


class DSPTab(QWidget):
    """Tab 6: Granular DSP Audio Post-Processing Suite."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Quick Anime DSP Preset Bar
        grp_anime_dsp = QGroupBox("English Anime Voice DSP Presets", self)
        h_adsp = QHBoxLayout(grp_anime_dsp)
        btn_anime_dsp = QPushButton("✨ Apply English Anime Voice DSP Preset", grp_anime_dsp)
        btn_anime_dsp.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        btn_anime_dsp.clicked.connect(self._apply_anime_dsp_preset)
        h_adsp.addWidget(btn_anime_dsp)

        lbl_adsp_desc = QLabel(
            "Applies +3 semitone pitch shift, 120Hz high-pass, presence (+3dB), air boost, and compressor.",
            grp_anime_dsp,
        )
        lbl_adsp_desc.setStyleSheet("color: #a0aec0; font-size: 11px;")
        h_adsp.addWidget(lbl_adsp_desc)
        h_adsp.addStretch()
        layout.addWidget(grp_anime_dsp)

        grp_dsp = QGroupBox("Master Output Processing Chain", self)
        f_dsp = QFormLayout(grp_dsp)

        # Load saved persona DSP preferences from dialog
        persona_cfg = getattr(self.dialog, "persona_cfg", None)
        saved_pitch = (
            int(round(float(getattr(persona_cfg, "dsp_pitch_semitones", 0.0))))
            if persona_cfg
            else 0
        )
        saved_dsp_enabled = (
            bool(getattr(persona_cfg, "dsp_enabled", True))
            if persona_cfg
            else True
        )

        # 1. Voice Pitch Shifter (-12 to +12 semitones)
        h_pitch = QHBoxLayout()
        self.slider_pitch = QSlider(Qt.Orientation.Horizontal, grp_dsp)
        self.slider_pitch.setRange(-12, 12)
        self.slider_pitch.setValue(saved_pitch)
        pitch_txt = f"{saved_pitch:+d} semitones" if saved_pitch != 0 else "0 semitones (Natural)"
        self.lbl_pitch_val = QLabel(pitch_txt, grp_dsp)
        self.lbl_pitch_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_pitch.valueChanged.connect(
            lambda val: self.lbl_pitch_val.setText(
                f"{val:+d} semitones" if val != 0 else "0 semitones (Natural)"
            )
        )
        h_pitch.addWidget(self.slider_pitch)
        h_pitch.addWidget(self.lbl_pitch_val)
        f_dsp.addRow("Voice Pitch Shifter:", h_pitch)

        # 2. Output Gain Trim (-12dB to +6dB)
        h_gain = QHBoxLayout()
        self.slider_gain = QSlider(Qt.Orientation.Horizontal, grp_dsp)
        self.slider_gain.setRange(-24, 12)
        self.slider_gain.setValue(0)
        self.lbl_gain_val = QLabel("0.0 dB", grp_dsp)
        self.lbl_gain_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_gain.valueChanged.connect(
            lambda val: self.lbl_gain_val.setText(f"{(val * 0.5):+.1f} dB")
        )
        h_gain.addWidget(self.slider_gain)
        h_gain.addWidget(self.lbl_gain_val)
        f_dsp.addRow("Master Output Gain Trim:", h_gain)

        # 3. Low-Mid / Highpass Filter
        h_bass = QHBoxLayout()
        self.slider_bass = QSlider(Qt.Orientation.Horizontal, grp_dsp)
        self.slider_bass.setRange(-12, 18)
        self.slider_bass.setValue(0)
        self.lbl_bass_val = QLabel("0.0 dB", grp_dsp)
        self.lbl_bass_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_bass.valueChanged.connect(
            lambda val: self.lbl_bass_val.setText(f"{(val * 0.5):+.1f} dB")
        )
        h_bass.addWidget(self.slider_bass)
        h_bass.addWidget(self.lbl_bass_val)
        f_dsp.addRow("Low-Mid Warmth (250 Hz):", h_bass)

        # 4. Treble / Air Presence Filter
        h_treble = QHBoxLayout()
        self.slider_treble = QSlider(Qt.Orientation.Horizontal, grp_dsp)
        self.slider_treble.setRange(-12, 18)
        self.slider_treble.setValue(6)
        self.lbl_treble_val = QLabel("+3.0 dB", grp_dsp)
        self.lbl_treble_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_treble.valueChanged.connect(
            lambda val: self.lbl_treble_val.setText(f"{(val * 0.5):+.1f} dB")
        )
        h_treble.addWidget(self.slider_treble)
        h_treble.addWidget(self.lbl_treble_val)
        f_dsp.addRow("High Clarity / Air (4-10 kHz):", h_treble)

        # 5. SNES Reverb / Echo Chamber
        h_reverb = QHBoxLayout()
        self.slider_reverb = QSlider(Qt.Orientation.Horizontal, grp_dsp)
        self.slider_reverb.setRange(0, 50)
        self.slider_reverb.setValue(8)
        self.lbl_reverb_val = QLabel("8% (Subtle Ambience)", grp_dsp)
        self.lbl_reverb_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_reverb.valueChanged.connect(
            lambda val: self.lbl_reverb_val.setText(f"{val}% (Wet/Dry Ambience)")
        )
        h_reverb.addWidget(self.slider_reverb)
        h_reverb.addWidget(self.lbl_reverb_val)
        f_dsp.addRow("SNES Reverb / Ambience:", h_reverb)

        # Checkbox toggles
        self.chk_limiter = QCheckBox("Soft-Knee Dynamic Limiter & Fast Compressor", grp_dsp)
        self.chk_limiter.setChecked(saved_dsp_enabled)
        f_dsp.addRow("Dynamic Protection:", self.chk_limiter)

        self.chk_rumble = QCheckBox(
            "120 Hz High-Pass Filter (Removes muddy chest resonance)", grp_dsp
        )
        self.chk_rumble.setChecked(True)
        f_dsp.addRow("Acoustic Cleanup:", self.chk_rumble)

        layout.addWidget(grp_dsp)

        # Live DSP Test Player
        grp_dsp_test = QGroupBox("Live DSP Post-Processing Test Player", self)
        v_dtest = QVBoxLayout(grp_dsp_test)
        self.line_dsp_test = QLineEdit(
            "Testing audio DSP filters: Warmth, clarity, and spatial resonance!",
            grp_dsp_test,
        )
        v_dtest.addWidget(self.line_dsp_test)

        h_dact = QHBoxLayout()
        self.btn_test_dsp = QPushButton("🔊 Play with DSP Post-Processing", grp_dsp_test)
        self.btn_test_dsp.clicked.connect(self._test_dsp_audio)
        self.lbl_dsp_status = QLabel("Ready.", grp_dsp_test)
        h_dact.addWidget(self.btn_test_dsp)
        h_dact.addWidget(self.lbl_dsp_status)
        h_dact.addStretch()
        v_dtest.addLayout(h_dact)

        layout.addWidget(grp_dsp_test)
        layout.addStretch()

    def _apply_anime_dsp_preset(self) -> None:
        self.slider_pitch.setValue(3)  # +3 semitones
        self.slider_gain.setValue(0)
        self.slider_bass.setValue(0)
        self.slider_treble.setValue(6)  # +3.0 dB
        self.slider_reverb.setValue(8)
        self.chk_limiter.setChecked(True)
        self.chk_rumble.setChecked(True)
        self.lbl_dsp_status.setText(
            "Applied English Anime Voice DSP preset (+3 st, presence, air, 120Hz HPF)."
        )

    def _test_dsp_audio(self) -> None:
        self.lbl_dsp_status.setText("Rendering speech with active DSP chain...")
        self.btn_test_dsp.setEnabled(False)

        pitch = self.slider_pitch.value()
        gain_db = self.slider_gain.value() * 0.5
        reverb_pct = self.slider_reverb.value() / 100.0
        text = self.line_dsp_test.text().strip() or "Testing DSP audio chain!"
        voice = getattr(self.dialog, "get_selected_voice_spec", lambda: "af_bella")()
        slider_speed = getattr(self.dialog, "slider_speed", None)
        speed = (slider_speed.value() / 100.0) if slider_speed is not None else 1.0

        def worker() -> None:
            try:
                model_p = Path("C:/ProjectLucca/models/tts/kokoro-v1.0.onnx")
                voices_p = Path("C:/ProjectLucca/models/tts/voices-v1.0.bin")
                if not model_p.exists() or not voices_p.exists():
                    self.lbl_dsp_status.setText("Kokoro model not found.")
                    return

                engine = kokoro_onnx.Kokoro(str(model_p), str(voices_p))
                clean_voice = VOICE_ALIASES.get(voice, voice)
                resolved = parse_voice_blend(engine, clean_voice)
                samples, sr = engine.create(text, voice=resolved, speed=speed)

                dsp = AnimeVoiceDSP(
                    AnimeDSPConfig(
                        pitch_semitones=float(pitch),
                        highpass_cutoff_hz=120.0 if self.chk_rumble.isChecked() else 20.0,
                        presence_gain_db=self.slider_treble.value() * 0.5,
                        master_gain_db=gain_db,
                    )
                )
                processed, play_sr = dsp.process(samples, sr=sr)

                if reverb_pct > 0.02:
                    delay_samples = int(play_sr * 0.08)
                    padded = np.pad(processed, (0, delay_samples))
                    echo = np.pad(processed, (delay_samples, 0)) * (reverb_pct * 0.5)
                    processed = ((padded + echo)[: len(processed)]).astype(np.float32)

                sd.play(processed, play_sr)
                sd.wait()
                self.lbl_dsp_status.setText("✓ DSP playback complete.")
            except Exception as exc:
                _LOG.debug("dsp_playback_failed: %s", exc)
                self.lbl_dsp_status.setText(f"DSP error: {exc}")
            finally:
                self.btn_test_dsp.setEnabled(True)

        threading.Thread(target=worker, daemon=True).start()
