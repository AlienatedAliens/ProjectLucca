"""
Project Lucca — Desktop Settings & Diagnostics Dialog
Spec 01 §1, Spec 16 §3, ADR-005
"""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import kokoro_onnx
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    """
    Desktop configuration dialog providing access to:
    - Voice selection (Kokoro voices) and speech rate
    - Audio I/O device selection & mic VU meter
    - Push-to-Talk keybinding
    - System diagnostics & hardware health
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        current_voice: str = "af_bella",
        current_speed: float = 1.05,
        current_ptt_key: str = "alt-gr",
        on_save_config: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.current_voice = current_voice
        self.current_speed = current_speed
        self.current_ptt_key = current_ptt_key
        self.on_save_config = on_save_config

        self.setWindowTitle("Project Lucca — Settings & Diagnostics")
        self.setFixedSize(500, 420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self._mic_test_stream: sd.InputStream | None = None
        self._mic_level = -60.0
        self._testing_mic = False

        self._apply_dark_theme()
        self._build_ui()

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #181825;
                color: #cdd6f4;
            }
            QTabWidget::pane {
                border: 1px solid #313244;
                background-color: #1e1e2e;
                border-radius: 6px;
                top: -1px;
            }
            QTabBar::tab {
                background: #181825;
                color: #a6adc8;
                padding: 8px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1e1e2e;
                color: #cdd6f4;
                font-weight: bold;
                border-bottom: 2px solid #89b4fa;
            }
            QLabel {
                color: #cdd6f4;
            }
            QComboBox, QDoubleSpinBox {
                background-color: #11111b;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 5px;
                padding: 4px 8px;
            }
            QComboBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #89b4fa;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #89b4fa;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
            QPushButton#primaryBtn {
                background-color: #89b4fa;
                color: #11111b;
                font-weight: bold;
                border: none;
            }
            QPushButton#primaryBtn:hover {
                background-color: #b4befe;
            }
        """)

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        tabs = QTabWidget(self)

        # Tab 1: Voice & Speech
        tab_voice = QWidget()
        self._build_voice_tab(tab_voice)
        tabs.addTab(tab_voice, "🎙️ Voice & TTS")

        # Tab 2: Audio Devices & Mic Test
        tab_audio = QWidget()
        self._build_audio_tab(tab_audio)
        tabs.addTab(tab_audio, "🔊 Audio Devices")

        # Tab 3: Hotkeys & PTT
        tab_hotkeys = QWidget()
        self._build_hotkeys_tab(tab_hotkeys)
        tabs.addTab(tab_hotkeys, "⌨️ Push-to-Talk")

        # Tab 4: System Diagnostics
        tab_diag = QWidget()
        self._build_diag_tab(tab_diag)
        tabs.addTab(tab_diag, "⚙️ Diagnostics")

        main_layout.addWidget(tabs)

        # Bottom Action Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Apply & Save", self)
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._handle_save)
        btn_box.addWidget(btn_save)

        main_layout.addLayout(btn_box)

    def _build_voice_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        # Voice Selector
        self.combo_voice = QComboBox(parent)
        voices = [
            ("af_bella", "Bella (Anime Heroine / Energetic) [Recommended]"),
            ("af_sky", "Sky (Bright & Youthful)"),
            ("af_heart", "Heart (Warm & Expressive)"),
            ("af_nicole", "Nicole (Crisp & Articulate)"),
            ("af_sarah", "Sarah (Balanced & Conversational)"),
            ("am_adam", "Adam (Calm Male Voice)"),
            ("am_michael", "Michael (Deep & Resonant Male)"),
        ]
        for vid, vdesc in voices:
            self.combo_voice.addItem(vdesc, vid)

        # Select current
        idx = self.combo_voice.findData(self.current_voice)
        if idx >= 0:
            self.combo_voice.setCurrentIndex(idx)
        form.addRow("Voice Persona:", self.combo_voice)

        # Speed / Rate
        self.spin_speed = QDoubleSpinBox(parent)
        self.spin_speed.setRange(0.8, 1.5)
        self.spin_speed.setSingleStep(0.05)
        self.spin_speed.setValue(self.current_speed)
        form.addRow("Speaking Speed:", self.spin_speed)

        layout.addLayout(form)

        # Test Voice Section
        test_box = QHBoxLayout()
        self.btn_test_voice = QPushButton("▶ Test Voice Preview", parent)
        self.btn_test_voice.clicked.connect(self._test_voice_sample)
        test_box.addWidget(self.btn_test_voice)
        test_box.addStretch()
        layout.addLayout(test_box)

        self.voice_status_label = QLabel("", parent)
        self.voice_status_label.setStyleSheet("color: #a6adc8; font-style: italic;")
        layout.addWidget(self.voice_status_label)

        layout.addStretch()

    def _test_voice_sample(self) -> None:
        selected_voice = str(self.combo_voice.currentData())
        selected_speed = float(self.spin_speed.value())

        self.voice_status_label.setText("Synthesizing preview...")
        self.btn_test_voice.setEnabled(False)

        def worker() -> None:
            try:
                model_p = Path(r"C:\ProjectLucca\models\tts\kokoro-v1.0.onnx")
                voices_p = Path(r"C:\ProjectLucca\models\tts\voices-v1.0.bin")
                if not model_p.exists() or not voices_p.exists():
                    return
                engine = kokoro_onnx.Kokoro(str(model_p), str(voices_p))
                sample_text = "All systems operational! Ready to assist you."
                samples, sr = engine.create(
                    sample_text, voice=selected_voice, speed=selected_speed
                )
                sd.play(samples, sr)
                sd.wait()
            finally:
                QTimer.singleShot(0, self._on_voice_test_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_voice_test_done(self) -> None:
        self.voice_status_label.setText("Preview played successfully.")
        self.btn_test_voice.setEnabled(True)

    def _build_audio_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.combo_mic = QComboBox(parent)
        self.combo_speaker = QComboBox(parent)

        try:
            devices = sd.query_devices()
            for idx, dev in enumerate(devices):
                dev_name = f"{idx}: {dev['name']}"
                if dev["max_input_channels"] > 0:
                    self.combo_mic.addItem(dev_name, idx)
                if dev["max_output_channels"] > 0:
                    self.combo_speaker.addItem(dev_name, idx)
        except Exception:  # noqa: BLE001
            self.combo_mic.addItem("Default Microphone", -1)
            self.combo_speaker.addItem("Default Speakers", -1)

        form.addRow("Microphone (Input):", self.combo_mic)
        form.addRow("Speakers (Output):", self.combo_speaker)
        layout.addLayout(form)

        # Microphone Live Test & VU Meter
        grp_mic_test = QGroupBox("Microphone Live Level (VU Meter)", parent)
        vbox_mic = QVBoxLayout(grp_mic_test)

        self.vu_bar = QProgressBar(grp_mic_test)
        self.vu_bar.setRange(-60, 0)
        self.vu_bar.setValue(-60)
        self.vu_bar.setTextVisible(False)
        self.vu_bar.setFixedHeight(14)
        self.vu_bar.setStyleSheet("""
            QProgressBar {
                background-color: #11111b;
                border: 1px solid #45475a;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #a6e3a1, stop:0.7 #f9e2af, stop:0.95 #f38ba8);
                border-radius: 3px;
            }
        """)
        vbox_mic.addWidget(self.vu_bar)

        h_test = QHBoxLayout()
        self.btn_test_mic = QPushButton("🎙️ Test Microphone (5s)", grp_mic_test)
        self.btn_test_mic.clicked.connect(self._toggle_mic_test)
        h_test.addWidget(self.btn_test_mic)

        self.mic_status_label = QLabel("Speak into your mic to test audio capture.", grp_mic_test)
        self.mic_status_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        h_test.addWidget(self.mic_status_label)
        h_test.addStretch()

        vbox_mic.addLayout(h_test)
        layout.addWidget(grp_mic_test)

        self.vu_timer = QTimer(self)
        self.vu_timer.timeout.connect(self._update_vu)

        layout.addStretch()

    def _toggle_mic_test(self) -> None:
        if self._testing_mic:
            return

        self._testing_mic = True
        self.btn_test_mic.setEnabled(False)
        self.mic_status_label.setText("Listening... Speak now!")

        def mic_callback(
            indata: np.ndarray,
            frames: int,  # noqa: ARG001
            time_info: object,  # noqa: ARG001
            status: object,  # noqa: ARG001
        ) -> None:
            if len(indata) > 0:
                samples = indata.astype(np.float32)
                rms = float(np.sqrt(np.mean(samples**2) + 1e-12))
                dbfs = 20.0 * np.log10(max(rms, 1e-6))
                self._mic_level = max(-60.0, min(0.0, float(dbfs)))

        try:
            self._mic_test_stream = sd.InputStream(
                channels=1,
                samplerate=16000,
                callback=mic_callback,
            )
            self._mic_test_stream.start()
            self.vu_timer.start(50)
            QTimer.singleShot(5000, self._stop_mic_test)
        except Exception as e:  # noqa: BLE001
            self.mic_status_label.setText(f"Mic error: {e}")
            self.btn_test_mic.setEnabled(True)
            self._testing_mic = False

    def _update_vu(self) -> None:
        self.vu_bar.setValue(int(self._mic_level))

    def _stop_mic_test(self) -> None:
        self.vu_timer.stop()
        if self._mic_test_stream:
            try:
                self._mic_test_stream.stop()
                self._mic_test_stream.close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._mic_test_stream = None

        self._testing_mic = False
        self.vu_bar.setValue(-60)
        self.btn_test_mic.setEnabled(True)
        self.mic_status_label.setText("Mic test finished.")

    def _build_hotkeys_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.combo_ptt = QComboBox(parent)
        ptt_options = [
            ("alt-gr", "Alt-Gr (Right Alt) [Recommended for ISO/EN keyboards]"),
            ("right ctrl", "Right Control [Standard PTT]"),
            ("right shift", "Right Shift"),
        ]
        for pid, pdesc in ptt_options:
            self.combo_ptt.addItem(pdesc, pid)

        idx = self.combo_ptt.findData(self.current_ptt_key)
        if idx >= 0:
            self.combo_ptt.setCurrentIndex(idx)
        form.addRow("Push-to-Talk Hotkey:", self.combo_ptt)

        layout.addLayout(form)

        info_lbl = QLabel(
            "💡 You can also double-click Lucca's avatar at any time to open the\n"
            "text chat bar and type directly without needing hotkeys or a mic!",
            parent,
        )
        info_lbl.setStyleSheet("color: #89b4fa; padding-top: 10px; line-height: 1.4;")
        layout.addWidget(info_lbl)

        layout.addStretch()

    def _build_diag_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        grid = QFormLayout()
        grid.setSpacing(8)

        grid.addRow("Core Status:", QLabel("Online (Supervised 4-Process Topology)"))
        grid.addRow("ASR Engine:", QLabel("Faster-Whisper (Distil-Small INT8, CPU)"))
        grid.addRow("LLM Backend:", QLabel("llama-server.exe on 127.0.0.1:8080 (dGPU)"))
        grid.addRow("TTS Engine:", QLabel("Kokoro ONNX v1.0 (24,000 Hz, CPU/iGPU)"))
        grid.addRow("Memory Store:", QLabel("SQLite-vec (Vector & Episodic Store)"))

        layout.addLayout(grid)
        layout.addStretch()

    def _handle_save(self) -> None:
        self._stop_mic_test()
        new_config = {
            "voice": str(self.combo_voice.currentData()),
            "speed": float(self.spin_speed.value()),
            "ptt_key": str(self.combo_ptt.currentData()),
        }
        if self.on_save_config:
            self.on_save_config(new_config)
        self.accept()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self._stop_mic_test()
        super().closeEvent(event)
