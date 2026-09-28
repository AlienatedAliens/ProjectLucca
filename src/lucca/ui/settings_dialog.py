"""
Project Lucca — Chrono Trigger Configuration Suite
WO-18e (F-ARCH-104)

Decomposed settings dialog coordinating per-tab modules in `lucca.ui.settings_tabs`.
Direct domain coupling is eliminated; all domain operations route through `StudioFacade`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import JsonValue
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lucca.brain.prompt_builder import get_persona_config, save_persona_to_config
from lucca.brain.server_ctl import is_healthy
from lucca.core.config import get_config
from lucca.core.studio_facade import StudioFacade
from lucca.ui.settings_tabs import (
    FORBIDDEN_SHELLS,
    AboutTab,
    DSPTab,
    HotkeysTab,
    LispTab,
    LLMTab,
    ManualTab,
    MemoryTab,
    PersonaTab,
    TelemetryTab,
    ToolsTab,
    VoiceTab,
    load_whitelist_apps,
    save_whitelist_apps,
)
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    pass

_LOG = logging.getLogger(__name__)

# Re-exports for test compatibility
__all__ = [
    "FORBIDDEN_SHELLS",
    "SettingsDialog",
    "is_healthy",
    "load_whitelist_apps",
    "save_whitelist_apps",
]


class SettingsDialog(QDialog):
    """
    Project Lucca — Chrono Trigger Configuration Suite (11 Tabs)
    0. 🧠 Persona & Archetypes (Lossless TOML, Prose Compilation, Granular Modulators)
    1. 🎙️ Voice Blender & Mixing (All 54 Kokoro voices, Dual-vector tensor blender, Anime Presets)
    2. ⚡ LLM Tuning & Granular Context Window (Model Registry, GGUF Meta, VRAM Guard, Honest Restart)
    3. 🛠️ Tool Studio & Whitelist
    4. λ MicroScheme LISP Reasoning Studio
    5. ⌨️ Hotkeys & Push-To-Talk
    6. 🎛️ DSP Audio Post-Processing (Formant Pitch Shift, High-Pass, Presence, Compressor, Saturation)
    7. 💾 Memory System (Episodic & Semantic Browser & Editor)
    8. 📊 Telemetry & Live Session Log Viewer
    9. 📖 User Manual (Interactive chapter manual)
    10. ℹ️ About Lucca (Dedicated lore, topology, credits)
    """

    FORBIDDEN_SHELLS = FORBIDDEN_SHELLS

    def __init__(
        self,
        current_voice: str = "genki_heroine",
        current_speed: float = 1.05,
        current_ptt_key: str = "alt_gr",
        current_archetype: str = "inventor",
        current_formality: str = "casual",
        current_custom_prompt: str = "",
        on_save_config: Callable[[dict[str, JsonValue]], None] | None = None,
        parent: QWidget | None = None,
        facade: StudioFacade | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project Lucca — Configuration Suite")
        self.resize(960, 720)
        self.setMinimumSize(760, 520)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)

        self.facade = facade or StudioFacade()

        self.current_voice = current_voice
        self.current_speed = current_speed
        self.current_ptt_key = current_ptt_key
        self.current_archetype = current_archetype
        self.current_formality = current_formality
        self.current_custom_prompt = current_custom_prompt
        self.on_save_config = on_save_config

        # Load global app & LLM configuration
        self.app_config = get_config()
        self.llm_cfg = self.app_config.llm

        # Load persona configuration from persona.toml
        self.persona_cfg = get_persona_config()
        if self.persona_cfg.voice:
            self.current_voice = self.persona_cfg.voice
        if self.persona_cfg.speed is not None:
            self.current_speed = self.persona_cfg.speed
        if self.persona_cfg.ptt_key:
            self.current_ptt_key = self.persona_cfg.ptt_key
        if self.persona_cfg.archetype:
            self.current_archetype = self.persona_cfg.archetype
        if self.persona_cfg.formality:
            self.current_formality = self.persona_cfg.formality
        if self.persona_cfg.custom_prompt is not None:
            self.current_custom_prompt = self.persona_cfg.custom_prompt

        self.current_tech_depth = self.persona_cfg.traits.technical_depth
        self.current_warmth = self.persona_cfg.traits.warmth
        self.current_directness = self.persona_cfg.traits.directness

        self.current_never_pretend = self.persona_cfg.boundaries.never_pretend_to_feel
        self.current_refuse_topics = list(self.persona_cfg.boundaries.refuse_topics)

        self.current_uses_name = self.persona_cfg.uses_your_name
        self.current_admits_uncertainty = self.persona_cfg.admits_uncertainty

        self.current_affect_enabled = self.persona_cfg.affect.enabled
        self.current_decay_tau = self.persona_cfg.affect.decay_tau_seconds
        self.current_max_speed_delta = self.persona_cfg.affect.max_speed_delta

        self.user_archetypes: dict[str, str] = dict(self.persona_cfg.user_archetypes)
        self.whitelisted_apps: list[dict[str, str]] = load_whitelist_apps()

        self._build_ui()

    def center_on_screen(self) -> None:
        """
        Centers the dialog within the visible available work area of the active display,
        guaranteeing the titlebar and entire window are strictly within screen bounds.
        """
        screen = None
        cursor_pos = QCursor.pos()
        for s in QGuiApplication.screens():
            if s.geometry().contains(cursor_pos):
                screen = s
                break

        if screen is None:
            screen = QGuiApplication.primaryScreen()

        if screen is None:
            return

        avail = screen.availableGeometry()

        target_w = min(self.width(), max(760, avail.width() - 40))
        target_h = min(self.height(), max(520, avail.height() - 60))
        if target_w < self.width() or target_h < self.height():
            self.resize(target_w, target_h)

        x = avail.x() + (avail.width() - self.width()) // 2
        y = avail.y() + (avail.height() - self.height()) // 2

        min_x = avail.left() + 20
        max_x = max(min_x, avail.right() - self.width() - 20)
        min_y = avail.top() + 30
        max_y = max(min_y, avail.bottom() - self.height() - 20)

        clamped_x = max(min_x, min(x, max_x))
        clamped_y = max(min_y, min(y, max_y))

        self.move(clamped_x, clamped_y)

    def showEvent(self, event: object) -> None:
        super().showEvent(event)
        if not getattr(self, "_already_centered", False):
            self._already_centered = True
            self.center_on_screen()

    def _create_scrollable_tab(self, tab_instance: QWidget) -> QScrollArea:
        """Wraps a tab content widget inside a responsive, styled QScrollArea."""
        scroll = QScrollArea(self.tabs)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #081036;
                width: 10px;
                margin: 0px;
                border: 1px solid #101c54;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #1c2e88;
                min-height: 24px;
                border-radius: 3px;
                border: 1px solid #3b82f6;
            }
            QScrollBar::handle:vertical:hover {
                background: #2563eb;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: #081036;
                height: 10px;
                margin: 0px;
                border: 1px solid #101c54;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #1c2e88;
                min-width: 24px;
                border-radius: 3px;
                border: 1px solid #3b82f6;
            }
            QScrollBar::handle:horizontal:hover {
                background: #2563eb;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)
        tab_instance.setStyleSheet("background: transparent;")
        scroll.setWidget(tab_instance)
        return scroll

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header Title Banner
        hdr = QHBoxLayout()
        lbl_title = QLabel("⏳ PROJECT LUCCA CONFIGURATION SUITE", self)
        lbl_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: 900; letter-spacing: 1.5px;")
        hdr.addWidget(lbl_title)
        hdr.addStretch()
        main_layout.addLayout(hdr)

        self.tabs = QTabWidget(self)

        # Decomposed Tab Instances
        self.tab_persona = PersonaTab(self, self.facade)
        self.tab_voice = VoiceTab(self, self.facade)
        self.tab_llm = LLMTab(self, self.facade)
        self.tab_tools = ToolsTab(self, self.facade)
        self.tab_lisp = LispTab(self, self.facade)
        self.tab_hotkeys = HotkeysTab(self, self.facade)
        self.tab_dsp = DSPTab(self, self.facade)
        self.tab_memory = MemoryTab(self, self.facade)
        self.tab_telemetry = TelemetryTab(self, self.facade)
        self.tab_manual = ManualTab(self, self.facade)
        self.tab_about = AboutTab(self, self.facade)

        self._all_tabs: list[QWidget] = [
            self.tab_persona,
            self.tab_voice,
            self.tab_llm,
            self.tab_tools,
            self.tab_lisp,
            self.tab_hotkeys,
            self.tab_dsp,
            self.tab_memory,
            self.tab_telemetry,
            self.tab_manual,
            self.tab_about,
        ]

        # Tab 0: 🧠 Persona & Archetypes (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_persona), "🧠 Persona")

        # Tab 1: 🎙️ Voice Blender & Mixing (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_voice), "🎙️ Voice Blender")

        # Tab 2: ⚡ LLM Tuning & Granular Context (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_llm), "⚡ LLM Tuning")

        # Tab 3: 🛠️ Tool Studio & Whitelist (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_tools), "🛠️ Tool Studio")

        # Tab 4: λ MicroScheme LISP Reasoning Studio (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_lisp), "λ LISP Studio")

        # Tab 5: ⌨️ Hotkeys & Push-To-Talk (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_hotkeys), "⌨️ Hotkeys")

        # Tab 6: 🎛️ DSP Audio Post-Processing (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_dsp), "🎛️ DSP Audio")

        # Tab 7: 💾 Episodic & Semantic Memory System (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_memory), "💾 Memory System")

        # Tab 8: 📊 Telemetry & Live Session Logs (Wrapped in QScrollArea)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_telemetry), "📊 Telemetry & Logs")

        # Tab 9: 📖 User Manual (Interactive chapter manual)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_manual), "📖 User Manual")

        # Tab 10: ℹ️ About Lucca (Dedicated lore, topology, credits)
        self.tabs.addTab(self._create_scrollable_tab(self.tab_about), "ℹ️ About Lucca")

        main_layout.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Bottom Action Bar
        btn_box = QHBoxLayout()
        self.lbl_global_status = QLabel("System Engine · Operational", self)
        self.lbl_global_status.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-style: italic;")
        btn_box.addWidget(self.lbl_global_status)
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_apply = QPushButton("Apply", self)
        btn_apply.clicked.connect(lambda: self._handle_save(close_dialog=False))
        btn_box.addWidget(btn_apply)

        btn_save = QPushButton("✓ Save & Close", self)
        btn_save.clicked.connect(lambda: self._handle_save(close_dialog=True))
        btn_box.addWidget(btn_save)

        main_layout.addLayout(btn_box)

    def _on_tab_changed(self, index: int) -> None:
        """Loads telemetry and log files on demand when switching to Tab 8, or refreshes Tab 7."""
        if index == 8:
            self.tab_telemetry._refresh_diag_snapshot()
            self.tab_telemetry._scan_and_reload_logs()
        elif index == 7:
            self.tab_memory._refresh_memories()

    def get_selected_voice_spec(self) -> str:
        return self.tab_voice.get_selected_voice_spec()

    # Pass-through test helpers and delegates
    @property
    def list_manual_chapters(self) -> QListWidget:
        return self.tab_manual.list_manual_chapters

    @property
    def txt_manual_body(self) -> QTextEdit:
        return self.tab_manual.txt_manual_body

    def _on_manual_chapter_selected(self, index: int) -> None:
        self.tab_manual._on_manual_chapter_selected(index)

    @property
    def lisp_rules(self) -> dict[str, dict[str, JsonValue]]:
        return self.tab_lisp.lisp_rules

    def __getattr__(self, name: str) -> object:
        # Transparently delegate attribute lookups to child tabs for backwards compatibility
        for tab in getattr(self, "_all_tabs", []):
            if hasattr(tab, name):
                return getattr(tab, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    # =========================================================================
    # Configuration Apply & Lossless Save
    # =========================================================================
    def _handle_save(self, close_dialog: bool = True) -> None:
        # 1. Save Persona to persona.toml losslessly via prompt_builder
        arch = str(self.tab_persona.combo_archetype.currentData())
        form = str(self.tab_persona.combo_formality.currentData())
        custom = self.tab_persona.txt_custom_prompt.toPlainText().strip()
        td = self.tab_persona.slider_tech.value() / 100.0
        wm = self.tab_persona.slider_warmth.value() / 100.0
        dr = self.tab_persona.slider_directness.value() / 100.0
        uses_name = self.tab_persona.chk_uses_name.isChecked()
        admits_unc = self.tab_persona.chk_admits_uncertainty.isChecked()
        never_pret = self.tab_persona.chk_never_pretend.isChecked()

        raw_refuse = self.tab_persona.line_refuse_topics.text().strip()
        refuse_list = [r.strip() for r in raw_refuse.split(",") if r.strip()]

        affect_en = self.tab_persona.chk_affect_enabled.isChecked()
        decay_tau = float(self.tab_persona.slider_affect_decay.value())
        max_speed = self.tab_persona.slider_affect_delta.value() / 100.0
        selected_voice = self.tab_voice.get_selected_voice_spec()
        selected_speed = self.tab_voice.slider_speed.value() / 100.0
        selected_ptt = str(self.tab_hotkeys.combo_ptt_key.currentData())
        selected_pitch = float(self.tab_dsp.slider_pitch.value())
        dsp_en = self.tab_dsp.chk_limiter.isChecked() or abs(selected_pitch) > 0.1

        save_persona_to_config(
            archetype=arch,
            formality=form,
            custom_prompt=custom,
            voice=selected_voice,
            speed=selected_speed,
            ptt_key=selected_ptt,
            technical_depth=td,
            warmth=wm,
            directness=dr,
            uses_your_name=uses_name,
            admits_uncertainty=admits_unc,
            never_pretend_to_feel=never_pret,
            refuse_topics=refuse_list,
            affect_enabled=affect_en,
            decay_tau_seconds=decay_tau,
            max_speed_delta=max_speed,
            user_archetypes=self.user_archetypes,
            dsp_pitch_semitones=selected_pitch,
            dsp_enabled=dsp_en,
        )

        # 2. Prepare full config payload
        data = self.tab_llm.combo_llm_model.currentData()
        model_name = data["rel_path"] if data else self.llm_cfg.model

        cfg: dict[str, JsonValue] = {
            "voice": selected_voice,
            "speed": selected_speed,
            "ptt_key": selected_ptt,
            "persona_archetype": arch,
            "formality": form,
            "custom_system_prompt": custom,
            "llm_model": model_name,
            "context_length": self.tab_llm.spin_context.value(),
            "pitch_semitones": selected_pitch,
            "dsp_enabled": dsp_en,
            "gain_db": self.tab_dsp.slider_gain.value() * 0.5,
            "bass_db": self.tab_dsp.slider_bass.value() * 0.5,
            "treble_db": self.tab_dsp.slider_treble.value() * 0.5,
            "reverb_pct": self.tab_dsp.slider_reverb.value(),
            "limiter_enabled": self.tab_dsp.chk_limiter.isChecked(),
            "rumble_filter_enabled": self.tab_dsp.chk_rumble.isChecked(),
        }

        if self.on_save_config is not None:
            self.on_save_config(cfg)

        # Reload persona_cfg in dialog
        self.persona_cfg = get_persona_config()
        self.current_voice = selected_voice
        self.current_speed = selected_speed
        self.current_ptt_key = selected_ptt

        if close_dialog:
            self.accept()
        else:
            self.lbl_global_status.setText("✓ Configuration applied and saved successfully!")
            self.lbl_global_status.setStyleSheet("color: #44dd44; font-weight: bold;")
