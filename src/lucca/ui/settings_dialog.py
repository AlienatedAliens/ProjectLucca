"""
Project Lucca — Chrono Trigger Configuration Suite
Universal 11-Tab Desktop Control Center & Diagnostics
Spec 01 §1, Spec 16 §3, ADR-005
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import tomllib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import kokoro_onnx
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lucca.brain.prompt_builder import (
    ARCHETYPES,
    compile_trait_modulators,
    get_persona_config,
    preview_system_prompt,
    save_persona_to_config,
)
from lucca.brain.server_ctl import (
    is_healthy,
    scan_model_registry,
    start_server,
    stop_server,
)
from lucca.core.config import LLMSettings, get_config
from lucca.core.schemas import RuleState
from lucca.memory.manager import MemoryManager
from lucca.reasoning.scheme.eval import evaluate_rule
from lucca.reasoning.scheme.parser import parse_rule
from lucca.sandbox.system_tools import get_system_metrics
from lucca.senses.dsp_chain import AnimeDSPConfig, AnimeVoiceDSP
from lucca.senses.tts import (
    VOICE_ALIASES,
    VOICE_RECIPES,
    enhance_anime_expressive_punctuation,
    get_available_voices,
    parse_voice_blend,
)
from lucca.ui.theme import CT_GOLD_TEXT


class ServerRestartWorker(QThread):
    """
    Background worker for restarting llama-server.exe honestly without
    blocking the PyQt GUI thread. Reports real transitions and health checks.
    """

    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, cfg: LLMSettings, home_dir: Path, timeout_s: float = 25.0) -> None:
        super().__init__()
        self.cfg = cfg
        self.home_dir = home_dir
        self.timeout_s = timeout_s

    def run(self) -> None:
        try:
            self.status_signal.emit("Stopping active llama-server process...")
            stop_server(self.cfg.host, self.cfg.port)

            self.status_signal.emit(f"Launching llama-server ({Path(self.cfg.model).name})...")
            start_server(self.cfg, self.home_dir)

            t0 = time.time()
            attempt = 0
            while time.time() - t0 < self.timeout_s:
                attempt += 1
                self.status_signal.emit(
                    f"Waiting for health check (attempt {attempt}, {time.time() - t0:.1f}s elapsed)..."
                )
                if is_healthy(self.cfg.host, self.cfg.port, timeout=1.0):
                    elapsed = time.time() - t0
                    self.finished_signal.emit(
                        True, f"✓ Healthy (Port {self.cfg.port}, {elapsed:.1f}s)"
                    )
                    return
                time.sleep(0.8)

            self.finished_signal.emit(
                False,
                f"Server failed to report healthy within {self.timeout_s:.0f}s. Check model path and logs.",
            )
        except Exception as exc:
            self.finished_signal.emit(False, f"Server restart failed: {exc}")


class ModelDownloadWorker(QThread):
    progress_signal = pyqtSignal(int, float, float, float)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url: str, dest_path: Path) -> None:
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        try:
            temp_dest = self.dest_path.with_suffix(".tmp")
            headers = {"User-Agent": "ProjectLucca-Downloader/1.0"}
            t0 = time.time()
            downloaded = 0

            with httpx.stream(
                "GET", self.url, headers=headers, follow_redirects=True, timeout=60.0
            ) as resp:
                if resp.status_code not in (200, 206):
                    self.finished_signal.emit(False, f"HTTP Error {resp.status_code}")
                    return

                total = int(resp.headers.get("content-length", 0))
                with open(temp_dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                        if self._is_cancelled:
                            temp_dest.unlink(missing_ok=True)
                            self.finished_signal.emit(False, "Download cancelled by user.")
                            return
                        f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = max(0.1, time.time() - t0)
                        speed = (downloaded / (1024 * 1024)) / elapsed
                        pct = int((downloaded / total) * 100) if total > 0 else 0
                        self.progress_signal.emit(
                            pct,
                            round(downloaded / (1024 * 1024), 1),
                            round(total / (1024 * 1024), 1),
                            round(speed, 2),
                        )

            # Validate GGUF header magic bytes
            with open(temp_dest, "rb") as f:
                magic = f.read(4)
                if magic != b"GGUF":
                    temp_dest.unlink(missing_ok=True)
                    self.finished_signal.emit(
                        False,
                        "Validation Error: File is not a valid GGUF binary. Download rejected.",
                    )
                    return

            if temp_dest.exists():
                temp_dest.replace(self.dest_path)
            self.finished_signal.emit(
                True, f"Model successfully downloaded and verified: {self.dest_path.name}"
            )
        except Exception as exc:
            self.finished_signal.emit(False, f"Download failed: {exc}")


def load_whitelist_apps(config_path: Path | None = None) -> list[dict[str, str]]:
    """Loads approved application whitelist dynamically from tool_whitelist.toml (Spec 09 §6)."""
    cfg = get_config()
    cfg_file = config_path or cfg.resolve_path("config") / "tool_whitelist.toml"
    if not cfg_file.exists() and Path("config/tool_whitelist.toml").exists():
        cfg_file = Path("config/tool_whitelist.toml")

    apps: list[dict[str, str]] = []
    if cfg_file.exists():
        try:
            with open(cfg_file, "rb") as f:
                data = tomllib.load(f)
            apps_table = data.get("apps", {})
            for key, entry in apps_table.items():
                if isinstance(entry, dict):
                    name = str(
                        entry.get("aliases", [key])[0] if entry.get("aliases") else key
                    ).title()
                    path_str = str(entry.get("exe", ""))
                    tier = (
                        "Read-Only"
                        if "task" in key
                        else ("Network" if "browser" in key else "Trusted")
                    )
                    status = "Disabled" if entry.get("disabled", False) else "Active"
                    apps.append(
                        {
                            "key": key,
                            "name": name,
                            "path": path_str,
                            "tier": tier,
                            "status": status,
                        }
                    )
        except Exception:  # noqa: BLE001
            pass

    if not apps:
        apps = [
            {
                "key": "calculator",
                "name": "Calculator",
                "path": "calc.exe",
                "tier": "Trusted",
                "status": "Active",
            },
            {
                "key": "notepad",
                "name": "Notepad",
                "path": "notepad.exe",
                "tier": "Trusted",
                "status": "Active",
            },
            {
                "key": "browser",
                "name": "Browser",
                "path": "msedge.exe",
                "tier": "Network",
                "status": "Active",
            },
            {
                "key": "terminal",
                "name": "Terminal",
                "path": "wt.exe",
                "tier": "Trusted",
                "status": "Active",
            },
            {
                "key": "task_manager",
                "name": "Task Manager",
                "path": "taskmgr.exe",
                "tier": "Read-Only",
                "status": "Active",
            },
        ]
    return apps


def save_whitelist_apps(apps: list[dict[str, str]], config_path: Path | None = None) -> None:
    """Saves approved application whitelist to tool_whitelist.toml, enforcing D-AUD-10."""
    cfg = get_config()
    cfg_file = config_path or cfg.resolve_path("config") / "tool_whitelist.toml"
    if not cfg_file.exists() and Path("config/tool_whitelist.toml").exists():
        cfg_file = Path("config/tool_whitelist.toml")

    lines = [
        "# Project Lucca — Approved Desktop Applications Whitelist",
        "# Spec 09 §6, D-AUD-10",
        "",
    ]
    for app in apps:
        key = app.get("key") or Path(app["path"]).stem.lower().replace(" ", "_")
        lines.append(f"[apps.{key}]")
        lines.append(f'exe = "{app["path"]}"')
        aliases = [app["name"].lower(), key]
        lines.append(f"aliases = {json.dumps(aliases)}")
        args = ["{file?}"] if "notepad" in key else (["{url?}"] if "browser" in key else [])
        lines.append(f"args = {json.dumps(args)}")
        single = "true" if ("calc" in key or "task" in key) else "false"
        lines.append(f"single_instance = {single}")
        if app.get("status") == "Disabled":
            lines.append("disabled = true")
        lines.append("")

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text("\n".join(lines), encoding="utf-8")


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
    10. ℹ️ About Lucca (Character lore, 4-process topology, machine specs)
    """

    server_health_checked = pyqtSignal(bool, int)

    def __init__(
        self,
        current_voice: str = "genki_heroine",
        current_speed: float = 1.05,
        current_ptt_key: str = "alt_gr",
        current_archetype: str = "inventor",
        current_formality: str = "casual",
        current_custom_prompt: str = "",
        on_save_config: Callable[[dict[str, Any]], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project Lucca — Configuration Suite")
        self.resize(960, 720)
        self.setMinimumSize(880, 640)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)

        self.current_voice = current_voice
        self.current_speed = current_speed
        self.current_ptt_key = current_ptt_key
        self.current_archetype = current_archetype
        self.current_formality = current_formality
        self.current_custom_prompt = current_custom_prompt
        self.on_save_config = on_save_config

        self.download_worker: ModelDownloadWorker | None = None
        self.server_worker: ServerRestartWorker | None = None
        self.server_health_checked.connect(self._on_server_health_checked)

        # Load global app & LLM configuration
        self.app_config = get_config()
        self.llm_cfg = self.app_config.llm

        # Load persona configuration from persona.toml
        self.persona_cfg = get_persona_config()
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

        try:
            cfg = get_config()
            mk: bytes | None = None
            if cfg.master_key:
                mk = cfg.master_key.encode("utf-8")
            elif cfg.env.mode == "dev":
                mk = b"01234567890123456789012345678901"
            self.memory_manager: MemoryManager | None = MemoryManager(master_key=mk)
        except Exception:
            self.memory_manager = None

        # Canonical MicroScheme rules
        self.lisp_rules: dict[str, dict[str, Any]] = {
            "open-calculator-v1": {
                "category": "Tools & Execution",
                "purpose": "Deterministic rule to launch calculator when requested and not already running.",
                "priority": 10,
                "state": "ACTIVE",
                "code": (
                    '(rule "open-calculator-v1"\n'
                    '  :when (and (intent= "launch_app")\n'
                    '             (entity-has? "app" "calculator")\n'
                    '             (not (app-running? "calculator")))\n'
                    '  :plan (list (tool "launch_app" :app "calculator")\n'
                    '              (say "Opening the calculator."))\n'
                    "  :priority 10)"
                ),
            },
        }

        # Whitelisted Applications loaded dynamically from tool_whitelist.toml (Spec 09 §6)
        self.whitelisted_apps: list[dict[str, str]] = load_whitelist_apps()

        self._build_ui()

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

        # Tab 0: 🧠 Persona & Archetypes
        tab_persona = QWidget()
        self._build_persona_tab(tab_persona)
        self.tabs.addTab(tab_persona, "🧠 Persona")

        # Tab 1: 🎙️ Voice Blender & Mixing
        tab_voice = QWidget()
        self._build_voice_tab(tab_voice)
        self.tabs.addTab(tab_voice, "🎙️ Voice Blender")

        # Tab 2: ⚡ LLM Tuning & Granular Context
        tab_llm = QWidget()
        self._build_llm_tab(tab_llm)
        self.tabs.addTab(tab_llm, "⚡ LLM Tuning")

        # Tab 3: 🛠️ Tool Studio & Whitelist
        tab_tools = QWidget()
        self._build_tools_tab(tab_tools)
        self.tabs.addTab(tab_tools, "🛠️ Tool Studio")

        # Tab 4: λ MicroScheme LISP Reasoning Studio
        tab_lisp = QWidget()
        self._build_lisp_tab(tab_lisp)
        self.tabs.addTab(tab_lisp, "λ LISP Studio")

        # Tab 5: ⌨️ Hotkeys & Push-To-Talk
        tab_ptt = QWidget()
        self._build_ptt_tab(tab_ptt)
        self.tabs.addTab(tab_ptt, "⌨️ Hotkeys")

        # Tab 6: 🎛️ DSP Audio Post-Processing
        tab_dsp = QWidget()
        self._build_dsp_tab(tab_dsp)
        self.tabs.addTab(tab_dsp, "🎛️ DSP Audio")

        # Tab 7: 💾 Episodic & Semantic Memory System
        tab_memory = QWidget()
        self._build_memory_tab(tab_memory)
        self.tabs.addTab(tab_memory, "💾 Memory System")

        # Tab 8: 📊 Telemetry & Live Session Logs
        tab_diag = QWidget()
        self._build_diag_tab(tab_diag)
        self.tabs.addTab(tab_diag, "📊 Telemetry & Logs")

        # Tab 9: 📖 User Manual (Interactive chapter manual)
        tab_manual = QWidget()
        self._build_manual_tab(tab_manual)
        self.tabs.addTab(tab_manual, "📖 User Manual")

        # Tab 10: ℹ️ About Lucca (Dedicated lore, topology, credits)
        tab_about = QWidget()
        self._build_about_tab(tab_about)
        self.tabs.addTab(tab_about, "ℹ️ About Lucca")

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

        btn_save = QPushButton("✓ Apply & Save All Changes", self)
        btn_save.clicked.connect(self._handle_save)
        btn_box.addWidget(btn_save)

        main_layout.addLayout(btn_box)

    # =========================================================================
    # TAB 0: Persona & Archetypes (Lossless TOML, Prose Compilation)
    # =========================================================================
    def _build_persona_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(10)

        # Archetype & Formality Selection
        grp_arch = QGroupBox("Persona Archetype & Inflection Mode", parent)
        f_arch = QFormLayout(grp_arch)

        h_arch_sel = QHBoxLayout()
        self.combo_archetype = QComboBox(grp_arch)
        self._repopulate_archetypes_combo()
        h_arch_sel.addWidget(self.combo_archetype, stretch=3)

        self.btn_add_arch = QPushButton("➕ New Archetype", grp_arch)
        self.btn_add_arch.clicked.connect(self._add_custom_archetype)
        h_arch_sel.addWidget(self.btn_add_arch)

        self.btn_del_arch = QPushButton("🗑️ Delete", grp_arch)
        self.btn_del_arch.clicked.connect(self._delete_custom_archetype)
        h_arch_sel.addWidget(self.btn_del_arch)

        self.combo_archetype.currentIndexChanged.connect(self._on_archetype_changed)
        f_arch.addRow("Active Archetype:", h_arch_sel)

        self.combo_formality = QComboBox(grp_arch)
        self.combo_formality.addItem("Casual (Friendly, colloquial partner dialogue)", "casual")
        self.combo_formality.addItem("Neutral (Balanced, direct assistant phrasing)", "neutral")
        self.combo_formality.addItem("Precise (High technical rigor, concise)", "precise")
        idx_f = self.combo_formality.findData(self.current_formality)
        if idx_f >= 0:
            self.combo_formality.setCurrentIndex(idx_f)
        self.combo_formality.currentIndexChanged.connect(self._update_prompt_preview)
        f_arch.addRow("Conversational Formality:", self.combo_formality)

        layout.addWidget(grp_arch)

        # Behavior & Boundaries
        grp_bound = QGroupBox("Behavior & Boundaries", parent)
        f_bound = QFormLayout(grp_bound)

        self.chk_uses_name = QCheckBox("Address creator by name ('Lucca')", grp_bound)
        self.chk_uses_name.setChecked(self.current_uses_name)
        self.chk_uses_name.toggled.connect(self._update_prompt_preview)
        f_bound.addRow("Identity & Name:", self.chk_uses_name)

        self.chk_admits_uncertainty = QCheckBox(
            "Admit uncertainty aloud ('I\\'m not sure' vs hallucinating)", grp_bound
        )
        self.chk_admits_uncertainty.setChecked(self.current_admits_uncertainty)
        self.chk_admits_uncertainty.toggled.connect(self._update_prompt_preview)
        f_bound.addRow("Truthfulness:", self.chk_admits_uncertainty)

        self.chk_never_pretend = QCheckBox(
            "Never simulate biological emotion (describe affect as system state)", grp_bound
        )
        self.chk_never_pretend.setChecked(self.current_never_pretend)
        self.chk_never_pretend.toggled.connect(self._update_prompt_preview)
        f_bound.addRow("Affect Substrate:", self.chk_never_pretend)

        self.line_refuse_topics = QLineEdit(grp_bound)
        self.line_refuse_topics.setPlaceholderText(
            "e.g. medical diagnosis, financial advice, unauthorized execution (comma-separated)"
        )
        self.line_refuse_topics.setText(", ".join(self.current_refuse_topics))
        self.line_refuse_topics.textChanged.connect(self._update_prompt_preview)
        f_bound.addRow("Declined Topics:", self.line_refuse_topics)

        layout.addWidget(grp_bound)

        # Affect Engine (Read/Write [affect] in persona.toml)
        grp_affect = QGroupBox("Affect Engine (Dynamic Emotional State Decay)", parent)
        f_affect = QFormLayout(grp_affect)

        self.chk_affect_enabled = QCheckBox("Enable dynamic affect state tracking", grp_affect)
        self.chk_affect_enabled.setChecked(self.current_affect_enabled)
        f_affect.addRow("Affect Tracking:", self.chk_affect_enabled)

        h_decay = QHBoxLayout()
        self.slider_affect_decay = QSlider(Qt.Orientation.Horizontal, grp_affect)
        self.slider_affect_decay.setRange(60, 1800)
        self.slider_affect_decay.setSingleStep(30)
        self.slider_affect_decay.setValue(int(self.current_decay_tau))
        decay_init_s = int(self.current_decay_tau)
        decay_init_m = self.current_decay_tau / 60.0
        self.lbl_affect_decay = QLabel(f"{decay_init_s}s ({decay_init_m:.1f}m)", grp_affect)
        self.lbl_affect_decay.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_affect_decay.valueChanged.connect(
            lambda v: self.lbl_affect_decay.setText(f"{v}s ({v / 60.0:.1f}m)")
        )
        h_decay.addWidget(self.slider_affect_decay)
        h_decay.addWidget(self.lbl_affect_decay)
        f_affect.addRow("Half-Life (tau):", h_decay)

        h_delta = QHBoxLayout()
        self.slider_affect_delta = QSlider(Qt.Orientation.Horizontal, grp_affect)
        self.slider_affect_delta.setRange(0, 25)
        self.slider_affect_delta.setValue(int(self.current_max_speed_delta * 100))
        delta_init = int(self.current_max_speed_delta * 100)
        self.lbl_affect_delta = QLabel(f"±{delta_init}%", grp_affect)
        self.lbl_affect_delta.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_affect_delta.valueChanged.connect(
            lambda v: self.lbl_affect_delta.setText(f"±{v}%")
        )
        h_delta.addWidget(self.slider_affect_delta)
        h_delta.addWidget(self.lbl_affect_delta)
        f_affect.addRow("Max Speed Delta:", h_delta)

        layout.addWidget(grp_affect)

        # Granular Trait Modulators (Prose Compilation)
        grp_traits = QGroupBox("Granular Trait Modulators (Compiled to Natural Prose)", parent)
        f_traits = QFormLayout(grp_traits)

        # Tech Depth
        h_td = QHBoxLayout()
        self.slider_tech = QSlider(Qt.Orientation.Horizontal, grp_traits)
        self.slider_tech.setRange(0, 100)
        self.slider_tech.setValue(int(self.current_tech_depth * 100))
        self.lbl_tech_val = QLabel(f"{self.current_tech_depth:.2f}", grp_traits)
        self.lbl_tech_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_tech.valueChanged.connect(self._on_traits_changed)
        h_td.addWidget(self.slider_tech)
        h_td.addWidget(self.lbl_tech_val)
        f_traits.addRow("Technical Depth:", h_td)

        # Warmth
        h_wm = QHBoxLayout()
        self.slider_warmth = QSlider(Qt.Orientation.Horizontal, grp_traits)
        self.slider_warmth.setRange(0, 100)
        self.slider_warmth.setValue(int(self.current_warmth * 100))
        self.lbl_warmth_val = QLabel(f"{self.current_warmth:.2f}", grp_traits)
        self.lbl_warmth_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_warmth.valueChanged.connect(self._on_traits_changed)
        h_wm.addWidget(self.slider_warmth)
        h_wm.addWidget(self.lbl_warmth_val)
        f_traits.addRow("Warmth / Playfulness:", h_wm)

        # Directness
        h_dr = QHBoxLayout()
        self.slider_directness = QSlider(Qt.Orientation.Horizontal, grp_traits)
        self.slider_directness.setRange(0, 100)
        self.slider_directness.setValue(int(self.current_directness * 100))
        self.lbl_directness_val = QLabel(f"{self.current_directness:.2f}", grp_traits)
        self.lbl_directness_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_directness.valueChanged.connect(self._on_traits_changed)
        h_dr.addWidget(self.slider_directness)
        h_dr.addWidget(self.lbl_directness_val)
        f_traits.addRow("Directness:", h_dr)

        self.lbl_compiled_traits = QLabel(grp_traits)
        self.lbl_compiled_traits.setFont(QFont("Consolas", 8))
        self.lbl_compiled_traits.setStyleSheet("color: #a0aec0; font-style: italic;")
        self.lbl_compiled_traits.setWordWrap(True)
        f_traits.addRow("Compiled Prose:", self.lbl_compiled_traits)

        layout.addWidget(grp_traits)

        # Custom Prompt Directives & Live Preview
        grp_prompt = QGroupBox(
            "Custom Persona Directives (Additive) & Live System Prompt Preview", parent
        )
        v_prompt = QVBoxLayout(grp_prompt)

        self.txt_custom_prompt = QPlainTextEdit(grp_prompt)
        self.txt_custom_prompt.setPlaceholderText(
            "Enter optional custom persona directives here (compiled additively)..."
        )
        self.txt_custom_prompt.setPlainText(self.current_custom_prompt)
        self.txt_custom_prompt.setMaximumHeight(80)
        self.txt_custom_prompt.textChanged.connect(self._update_prompt_preview)
        v_prompt.addWidget(self.txt_custom_prompt)

        h_pv_hdr = QHBoxLayout()
        h_pv_hdr.addWidget(
            QLabel("Full Compiled System Prompt (with Architecture & Tools):", grp_prompt)
        )
        h_pv_hdr.addStretch()
        self.lbl_token_count = QLabel("Approx: -- tokens", grp_prompt)
        self.lbl_token_count.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        h_pv_hdr.addWidget(self.lbl_token_count)
        v_prompt.addLayout(h_pv_hdr)

        self.txt_preview = QPlainTextEdit(grp_prompt)
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setMaximumHeight(140)
        self.txt_preview.setFont(QFont("Consolas", 8))
        v_prompt.addWidget(self.txt_preview)

        layout.addWidget(grp_prompt)
        self._on_traits_changed()

    def _repopulate_archetypes_combo(self) -> None:
        self.combo_archetype.blockSignals(True)
        self.combo_archetype.clear()
        self.combo_archetype.addItem("Inventor (Technical, Enthusiastic Companion)", "inventor")
        self.combo_archetype.addItem("Genki (Energetic, Cheerful Partner)", "genki")
        self.combo_archetype.addItem("Kuudere (Quiet, Hyper-Competent Analytical)", "kuudere")

        for name in sorted(self.user_archetypes.keys()):
            self.combo_archetype.addItem(f"Custom: {name}", name)

        idx = self.combo_archetype.findData(self.current_archetype)
        if idx >= 0:
            self.combo_archetype.setCurrentIndex(idx)
        else:
            self.combo_archetype.setCurrentIndex(0)
        self.combo_archetype.blockSignals(False)

    def _on_archetype_changed(self) -> None:
        arch = str(self.combo_archetype.currentData())
        is_custom = arch in self.user_archetypes
        self.btn_del_arch.setEnabled(is_custom)
        self._update_prompt_preview()

    def _add_custom_archetype(self) -> None:
        name, ok = QInputDialog.getText(self, "New Custom Archetype", "Enter archetype identifier:")
        if not ok or not name.strip():
            return
        clean_name = name.strip().lower().replace(" ", "_")
        if clean_name in ARCHETYPES or clean_name in self.user_archetypes:
            QMessageBox.warning(
                self, "Archetype Exists", f"Archetype '{clean_name}' already exists."
            )
            return

        desc, ok_desc = QInputDialog.getMultiLineText(
            self,
            "Archetype Voice & Prose",
            "Enter hybrid prose (3-4 bulleted facts + voice paragraph, <= 120 tokens):",
            "• Specialized technical or conversational focus\n• Direct, expressive delivery\n\nReady to proceed!",
        )
        if not ok_desc or not desc.strip():
            return

        self.user_archetypes[clean_name] = desc.strip()
        self.current_archetype = clean_name
        self._repopulate_archetypes_combo()
        self._update_prompt_preview()

    def _delete_custom_archetype(self) -> None:
        arch = str(self.combo_archetype.currentData())
        if arch not in self.user_archetypes:
            QMessageBox.information(
                self, "Built-in Archetype", "Built-in archetypes cannot be deleted."
            )
            return
        del self.user_archetypes[arch]
        self.current_archetype = "inventor"
        self._repopulate_archetypes_combo()
        self._update_prompt_preview()

    def _on_traits_changed(self) -> None:
        td = self.slider_tech.value() / 100.0
        wm = self.slider_warmth.value() / 100.0
        dr = self.slider_directness.value() / 100.0

        self.lbl_tech_val.setText(f"{td:.2f}")
        self.lbl_warmth_val.setText(f"{wm:.2f}")
        self.lbl_directness_val.setText(f"{dr:.2f}")

        compiled = compile_trait_modulators(td, wm, dr)
        if compiled:
            self.lbl_compiled_traits.setText(f'"{compiled}"')
        else:
            self.lbl_compiled_traits.setText(
                "(Neutral default 0.5 — no additional prompt directives emitted)"
            )

        self._update_prompt_preview()

    def _update_prompt_preview(self) -> None:
        arch = str(self.combo_archetype.currentData())
        form = str(self.combo_formality.currentData())
        custom = self.txt_custom_prompt.toPlainText().strip()
        td = self.slider_tech.value() / 100.0
        wm = self.slider_warmth.value() / 100.0
        dr = self.slider_directness.value() / 100.0
        uses_name = self.chk_uses_name.isChecked()
        admits_unc = self.chk_admits_uncertainty.isChecked()
        never_pret = self.chk_never_pretend.isChecked()

        raw_refuse = self.line_refuse_topics.text().strip()
        refuse_list = [r.strip() for r in raw_refuse.split(",") if r.strip()]

        full_prompt = preview_system_prompt(
            archetype=arch,
            formality=form,
            custom_prompt=custom,
            technical_depth=td,
            warmth=wm,
            directness=dr,
            uses_your_name=uses_name,
            admits_uncertainty=admits_unc,
            never_pretend_to_feel=never_pret,
            refuse_topics=refuse_list,
            user_archetypes=self.user_archetypes,
        )
        self.txt_preview.setPlainText(full_prompt)

        # Estimate tokens truthfully (approx chars / 4)
        n_chars = len(full_prompt)
        n_tokens = max(1, int(n_chars / 4))
        self.lbl_token_count.setText(f"Approx: ~{n_tokens} tokens ({n_chars} chars)")

    # =========================================================================
    # TAB 1: Voice Blender & Mixing (All 54 Kokoro Voices & Anime Presets)
    # =========================================================================
    def _build_voice_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)

        # Anime Preset Quick Bar
        grp_preset = QGroupBox("Quick-Switch Canonical Presets", parent)
        h_pres = QHBoxLayout(grp_preset)
        btn_anime_heroine = QPushButton("✨ Apply English Anime Heroine Preset", grp_preset)
        btn_anime_heroine.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        btn_anime_heroine.clicked.connect(self._apply_anime_heroine_preset)
        h_pres.addWidget(btn_anime_heroine)

        lbl_pres_note = QLabel(
            "Blends 70% af_bella + 30% af_sarah @ 1.20x speed with expressive punctuation.",
            grp_preset,
        )
        lbl_pres_note.setStyleSheet("color: #a0aec0; font-size: 11px;")
        h_pres.addWidget(lbl_pres_note)
        h_pres.addStretch()
        layout.addWidget(grp_preset)

        # Mode Selection
        grp_mode = QGroupBox("Voice Architecture & Vector Generation Mode", parent)
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
            "Single Voice Selector (All Installed Kokoro Vectors)", parent
        )
        f_single = QFormLayout(self.panel_single)
        self.combo_single_voice = QComboBox(self.panel_single)
        for v in pure_voices:
            self.combo_single_voice.addItem(f"{v} (Kokoro 512-dim)", v)
        f_single.addRow("Installed Voice:", self.combo_single_voice)
        layout.addWidget(self.panel_single)

        # Container 2: Canonical Anime Recipe
        self.panel_recipe = QGroupBox("Canonical Anime Voice Blends", parent)
        f_recipe = QFormLayout(self.panel_recipe)
        self.combo_recipe = QComboBox(self.panel_recipe)
        for r_name, r_formula in VOICE_RECIPES.items():
            self.combo_recipe.addItem(f"{r_name.replace('_', ' ').title()} ({r_formula})", r_name)
        f_recipe.addRow("Recipe Preset:", self.combo_recipe)
        layout.addWidget(self.panel_recipe)

        # Container 3: Dual-Vector Tensor Voice Mixer
        self.panel_mixer = QGroupBox("Dual-Vector Linear Tensor Combination Studio", parent)
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

        # Determine initial mode from self.current_voice
        if self.current_voice.startswith("blend:") or "+" in self.current_voice:
            self.rb_mode_mixer.setChecked(True)
            self.line_blend_formula.setText(self.current_voice)
        elif self.current_voice in VOICE_RECIPES:
            self.rb_mode_recipe.setChecked(True)
            idx_r = self.combo_recipe.findData(self.current_voice)
            if idx_r >= 0:
                self.combo_recipe.setCurrentIndex(idx_r)
        else:
            self.rb_mode_single.setChecked(True)
            idx_s = self.combo_single_voice.findData(self.current_voice)
            if idx_s >= 0:
                self.combo_single_voice.setCurrentIndex(idx_s)
        self._sync_voice_mode_ui()

        # Pacing & Speed Multiplier
        grp_speed = QGroupBox("Speaking Pace & Audio Pacing", parent)
        f_speed = QFormLayout(grp_speed)
        h_speed = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Orientation.Horizontal, grp_speed)
        self.slider_speed.setRange(60, 180)
        self.slider_speed.setValue(int(self.current_speed * 100))
        self.lbl_speed_val = QLabel(f"{self.current_speed:.2f}x", grp_speed)
        self.lbl_speed_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_speed.valueChanged.connect(
            lambda val: self.lbl_speed_val.setText(f"{(val / 100.0):.2f}x")
        )
        h_speed.addWidget(self.slider_speed)
        h_speed.addWidget(self.lbl_speed_val)
        f_speed.addRow("Pace Multiplier:", h_speed)
        layout.addWidget(grp_speed)

        # Test Synthesis Box
        grp_test = QGroupBox("Test Voice Playback & Audio Synthesis", parent)
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
                sd.play(samples, sr)
                sd.wait()
                self.lbl_voice_status.setText("✓ Audio playback successful.")
            except Exception as exc:
                self.lbl_voice_status.setText(f"Error: {exc}")
            finally:
                self.btn_test_speech.setEnabled(True)

        threading.Thread(target=worker, daemon=True).start()

    # =========================================================================
    # TAB 2: LLM Architecture & Engine Tuning (Model Registry & Honest Control)
    # =========================================================================
    def _build_llm_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)

        # 1. Dynamic Model Registry & GGUF Metadata Card
        grp_reg = QGroupBox(
            "Model Registry (Scanned from models/llm/*.gguf) & GGUF Metadata", parent
        )
        f_reg = QFormLayout(grp_reg)

        self.combo_llm_model = QComboBox(grp_reg)
        self.combo_llm_model.currentIndexChanged.connect(self._on_model_selection_changed)
        f_reg.addRow("Active GGUF Model:", self.combo_llm_model)

        self.lbl_model_badge = QLabel("Architecture: --", grp_reg)
        self.lbl_model_badge.setStyleSheet("font-weight: bold; font-size: 11px;")
        f_reg.addRow("Compatibility Badge:", self.lbl_model_badge)

        self.lbl_model_meta = QLabel("Header Metadata: --", grp_reg)
        self.lbl_model_meta.setFont(QFont("Consolas", 9))
        self.lbl_model_meta.setStyleSheet(f"color: {CT_GOLD_TEXT};")
        f_reg.addRow("GGUF Metadata:", self.lbl_model_meta)

        layout.addWidget(grp_reg)

        # 2. Context Window & KV-Cache Footprint
        grp_ctx = QGroupBox("Granular Context Window & 15.0 GB RTX 5080 VRAM Fit Guard", parent)
        f_ctx = QFormLayout(grp_ctx)

        h_ctx_ctrl = QHBoxLayout()
        self.slider_context = QSlider(Qt.Orientation.Horizontal, grp_ctx)
        self.slider_context.setRange(512, 32768)
        self.slider_context.setSingleStep(256)
        self.slider_context.setPageStep(1024)
        self.slider_context.setValue(self.llm_cfg.ctx)

        self.spin_context = QSpinBox(grp_ctx)
        self.spin_context.setRange(512, 32768)
        self.spin_context.setSingleStep(256)
        self.spin_context.setValue(self.llm_cfg.ctx)
        self.spin_context.setSuffix(" tokens")

        self.slider_context.valueChanged.connect(self.spin_context.setValue)
        self.spin_context.valueChanged.connect(self.slider_context.setValue)
        self.spin_context.valueChanged.connect(lambda _: self._update_vram_estimation())

        h_ctx_ctrl.addWidget(self.slider_context, stretch=3)
        h_ctx_ctrl.addWidget(self.spin_context, stretch=1)
        f_ctx.addRow("Context Length (n_ctx):", h_ctx_ctrl)

        # KV-cache quantization
        self.combo_kv_type = QComboBox(grp_ctx)
        self.combo_kv_type.addItem("q8_0 (8-bit Quantized KV - Recommended)", "q8_0")
        self.combo_kv_type.addItem("f16 (Full Precision 16-bit KV)", "f16")
        self.combo_kv_type.addItem("q4_0 (4-bit Highly Compressed KV)", "q4_0")
        idx_kv = self.combo_kv_type.findData(self.llm_cfg.kv_type)
        if idx_kv >= 0:
            self.combo_kv_type.setCurrentIndex(idx_kv)
        self.combo_kv_type.currentIndexChanged.connect(lambda _: self._update_vram_estimation())
        f_ctx.addRow("KV-Cache Quantization:", self.combo_kv_type)

        self.lbl_vram_est = QLabel(grp_ctx)
        self.lbl_vram_est.setFont(QFont("Consolas", 9))
        self.lbl_vram_est.setStyleSheet(f"color: {CT_GOLD_TEXT};")
        f_ctx.addRow("VRAM Footprint:", self.lbl_vram_est)

        self.lbl_vram_guard = QLabel(grp_ctx)
        self.lbl_vram_guard.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        f_ctx.addRow("VRAM Fit Status:", self.lbl_vram_guard)

        layout.addWidget(grp_ctx)

        # 3. Advanced Sampling & Generation Parameters
        grp_sampling = QGroupBox("Sampling Hyperparameters & Multimodal Mode", parent)
        f_sampling = QFormLayout(grp_sampling)

        # Temperature
        h_temp = QHBoxLayout()
        self.slider_temp = QSlider(Qt.Orientation.Horizontal, grp_sampling)
        self.slider_temp.setRange(0, 150)
        self.slider_temp.setValue(int(self.llm_cfg.temperature * 100))
        self.lbl_temp_val = QLabel(f"{self.llm_cfg.temperature:.2f}", grp_sampling)
        self.lbl_temp_val.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.slider_temp.valueChanged.connect(
            lambda val: self.lbl_temp_val.setText(f"{val / 100.0:.2f}")
        )
        h_temp.addWidget(self.slider_temp)
        h_temp.addWidget(self.lbl_temp_val)
        f_sampling.addRow("Temperature:", h_temp)

        # Max Tokens
        self.spin_max_tokens = QSpinBox(grp_sampling)
        self.spin_max_tokens.setRange(64, 4096)
        self.spin_max_tokens.setSingleStep(64)
        self.spin_max_tokens.setValue(self.llm_cfg.max_tokens)
        self.spin_max_tokens.setSuffix(" tokens")
        f_sampling.addRow("Max Tokens / Turn:", self.spin_max_tokens)

        # Audio/Transcript Mode
        self.combo_mode = QComboBox(grp_sampling)
        self.combo_mode.addItem("Audio-Native (Raw input_audio via mmproj)", "audio")
        self.combo_mode.addItem("Transcript (Text via Faster-Whisper ASR)", "transcript")
        idx_m = self.combo_mode.findData(self.llm_cfg.mode)
        if idx_m >= 0:
            self.combo_mode.setCurrentIndex(idx_m)
        f_sampling.addRow("Inference Input Mode:", self.combo_mode)

        # GPU Offload Layers
        self.spin_gpu_layers = QSpinBox(grp_sampling)
        self.spin_gpu_layers.setRange(0, 99)
        self.spin_gpu_layers.setValue(99)
        self.spin_gpu_layers.setSuffix(" layers (99 = full dGPU offload)")
        f_sampling.addRow("GPU Offload Layers:", self.spin_gpu_layers)

        layout.addWidget(grp_sampling)

        # 4. Honest Server Control Panel
        grp_srv = QGroupBox("Active LLM Inference Server Process Control", parent)
        f_srv = QFormLayout(grp_srv)

        h_srv_act = QHBoxLayout()
        self.btn_restart_llm = QPushButton("🔄 Restart Llama Server", grp_srv)
        self.btn_restart_llm.clicked.connect(self._restart_llm_server)
        self.lbl_srv_status = QLabel("Checking server health...", grp_srv)
        self.lbl_srv_status.setStyleSheet("color: #a0aec0; font-weight: bold;")
        h_srv_act.addWidget(self.btn_restart_llm)
        h_srv_act.addWidget(self.lbl_srv_status)
        h_srv_act.addStretch()
        f_srv.addRow("Server Lifecycle:", h_srv_act)

        layout.addWidget(grp_srv)

        # 5. Curated Catalog & Verified Downloader
        grp_dl = QGroupBox("Curated Model Catalog & Verified GGUF Downloader", parent)
        v_dl = QVBoxLayout(grp_dl)

        self.table_curated = QTableWidget(3, 4, grp_dl)
        self.table_curated.setHorizontalHeaderLabels(
            ["Model Name", "Architecture", "Size", "Action"]
        )
        hdr_curated = self.table_curated.horizontalHeader()
        if hdr_curated is not None:
            hdr_curated.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_curated.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_curated.setMaximumHeight(110)

        curated_models = [
            (
                "Ultravox v0.5 Llama-3.1-8B Q6_K",
                "Audio-Native (Paired mmproj)",
                "~6.5 GB",
                "https://huggingface.co/fixie-ai/ultravox-v0_5-llama-3_1-8b-gguf/resolve/main/ultravox-v0_5-llama-3_1-8b-Q6_K.gguf",
            ),
            (
                "Qwen2.5-7B-Instruct Q4_K_M",
                "Text / Whisper Transcript",
                "~4.7 GB",
                "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
            ),
            (
                "Llama-3.1-8B-Instruct Q4_K_M",
                "Text / Whisper Transcript",
                "~4.9 GB",
                "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
            ),
        ]

        for row, (name, arch, sz, url) in enumerate(curated_models):
            self.table_curated.setItem(row, 0, QTableWidgetItem(name))
            self.table_curated.setItem(row, 1, QTableWidgetItem(arch))
            self.table_curated.setItem(row, 2, QTableWidgetItem(sz))
            btn_pick = QPushButton("Select URL", grp_dl)
            btn_pick.clicked.connect(lambda _, u=url: self.line_model_url.setText(u))
            self.table_curated.setCellWidget(row, 3, btn_pick)

        v_dl.addWidget(self.table_curated)

        h_url = QHBoxLayout()
        self.line_model_url = QLineEdit(grp_dl)
        self.line_model_url.setPlaceholderText("https://huggingface.co/.../resolve/main/model.gguf")
        self.btn_download_model = QPushButton("⬇ Download Model", grp_dl)
        self.btn_download_model.clicked.connect(self._start_model_download)
        h_url.addWidget(self.line_model_url, stretch=3)
        h_url.addWidget(self.btn_download_model, stretch=1)
        v_dl.addLayout(h_url)

        self.progress_download = QProgressBar(grp_dl)
        self.progress_download.setValue(0)
        self.progress_download.setTextVisible(True)
        v_dl.addWidget(self.progress_download)

        self.lbl_download_status = QLabel("Ready.", grp_dl)
        v_dl.addWidget(self.lbl_download_status)
        layout.addWidget(grp_dl)

        # Initial scans and status
        self._refresh_model_registry()
        self._check_initial_server_health()
        layout.addStretch()

    def _on_server_health_checked(self, ok: bool, port: int) -> None:
        try:
            if ok:
                self.lbl_srv_status.setText(f"✓ Healthy (Port {port})")
                self.lbl_srv_status.setStyleSheet("color: #58d68d; font-weight: bold;")
            else:
                self.lbl_srv_status.setText(f"Offline (Port {port})")
                self.lbl_srv_status.setStyleSheet("color: #f87171; font-weight: bold;")
        except (RuntimeError, AttributeError):
            pass

    def _check_initial_server_health(self) -> None:
        port = self.llm_cfg.port
        host = self.llm_cfg.host

        def check() -> None:
            ok = is_healthy(host, port, timeout=1.0)
            try:
                self.server_health_checked.emit(ok, port)
            except (RuntimeError, AttributeError):
                pass

        threading.Thread(target=check, daemon=True).start()

    def _refresh_model_registry(self) -> None:
        models_dir = self.app_config.home_dir / "models" / "llm"
        registry = scan_model_registry(models_dir, active_model_rel=self.llm_cfg.model)

        self.combo_llm_model.blockSignals(True)
        self.combo_llm_model.clear()

        if not registry:
            self.combo_llm_model.addItem("No GGUF models found in models/llm/", None)
            self.lbl_model_badge.setText("N/A")
            self.lbl_model_meta.setText("Directory empty or missing.")
        else:
            for entry in registry:
                active_str = " (Active Default)" if entry["is_active"] else ""
                label = f"{entry['filename']} ({entry['size_gb']:.1f} GB){active_str}"
                self.combo_llm_model.addItem(label, entry)

            # Pick active entry
            active_idx = 0
            for idx in range(self.combo_llm_model.count()):
                data = self.combo_llm_model.itemData(idx)
                if data and data.get("is_active"):
                    active_idx = idx
                    break
            self.combo_llm_model.setCurrentIndex(active_idx)

        self.combo_llm_model.blockSignals(False)
        self._on_model_selection_changed()

    def _on_model_selection_changed(self) -> None:
        data = self.combo_llm_model.currentData()
        if not data:
            return

        badge_type = data.get("badge_type", "transcript")
        badge_text = data.get("badge", "")

        if badge_type == "audio":
            self.lbl_model_badge.setText(f"{badge_text} (Direct Audio Multimodal Inference)")
            self.lbl_model_badge.setStyleSheet("color: #38bdf8; font-weight: bold;")
            idx = self.combo_mode.findData("audio")
            if idx >= 0:
                self.combo_mode.setCurrentIndex(idx)
        elif badge_type == "missing_mmproj":
            self.lbl_model_badge.setText(
                f"{badge_text} (Download companion mmproj to enable direct audio)"
            )
            self.lbl_model_badge.setStyleSheet("color: #fbbf24; font-weight: bold;")
        else:
            self.lbl_model_badge.setText(f"{badge_text} (Text Model via Whisper ASR)")
            self.lbl_model_badge.setStyleSheet("color: #a78bfa; font-weight: bold;")
            idx = self.combo_mode.findData("transcript")
            if idx >= 0:
                self.combo_mode.setCurrentIndex(idx)

        arch = data.get("architecture", "llama")
        quant = data.get("quantization", "Q4_K_M")
        size_gb = data.get("size_gb", 0.0)
        t_count = data.get("tensor_count", 0)
        self.lbl_model_meta.setText(
            f"Arch: {arch} · Quant: {quant} · Size: {size_gb:.2f} GB · Tensors: {t_count}"
        )

        self._update_vram_estimation()

    def _update_vram_estimation(self) -> None:
        tokens = self.spin_context.value()
        kv_type = str(self.combo_kv_type.currentData())

        # KV-cache footprint (Llama-3-8B class approximation: 32 layers, 8 KV heads, 128 head-dim)
        mb_fp16 = tokens * 0.262144
        gb_fp16 = mb_fp16 / 1024.0

        if kv_type == "q8_0":
            kv_gb = gb_fp16 * 0.5
        elif kv_type == "q4_0":
            kv_gb = gb_fp16 * 0.28
        else:
            kv_gb = gb_fp16

        data = self.combo_llm_model.currentData()
        model_size_gb = data.get("size_gb", 6.0) if data else 6.0
        runtime_overhead_gb = 1.0

        total_vram_gb = model_size_gb + kv_gb + runtime_overhead_gb

        self.lbl_vram_est.setText(
            f"Weights: {model_size_gb:.1f} GB + KV-Cache ({kv_type}): {kv_gb:.2f} GB + Overhead: {runtime_overhead_gb:.1f} GB "
            f"= Total Projected VRAM: {total_vram_gb:.2f} GB (Llama-8B class)"
        )

        # 15.0 GB VRAM Fit Guard
        if total_vram_gb > 15.0:
            self.lbl_vram_guard.setText(
                f"⚠️ EXCEEDS 15.0 GB BUDGET ({total_vram_gb:.1f} GB / 16.0 GB Total) — Reduce context or choose Q8_0/Q4_0 KV!"
            )
            self.lbl_vram_guard.setStyleSheet("color: #f87171; font-weight: bold;")
            self.btn_restart_llm.setEnabled(False)
            self.btn_restart_llm.setToolTip("Projected VRAM exceeds the 15.0 GB budget limit.")
        else:
            self.lbl_vram_guard.setText(
                f"✓ FIT CONFIRMED: {total_vram_gb:.1f} GB / 15.0 GB limit (Fits comfortably on RTX 5080 16GB)"
            )
            self.lbl_vram_guard.setStyleSheet("color: #58d68d; font-weight: bold;")
            self.btn_restart_llm.setEnabled(True)
            self.btn_restart_llm.setToolTip("Ready to launch llama-server.")

    def _restart_llm_server(self) -> None:
        data = self.combo_llm_model.currentData()
        model_rel = data["rel_path"] if data else self.llm_cfg.model
        mmproj_rel = self.llm_cfg.mmproj
        if data and data.get("paired_mmproj"):
            mmproj_rel = f"llm/{data['paired_mmproj'].name}"

        mode = str(self.combo_mode.currentData())
        mode_val: Literal["audio", "transcript"] = "audio" if mode == "audio" else "transcript"
        kv_type = str(self.combo_kv_type.currentData())
        ctx = self.spin_context.value()
        temp = self.slider_temp.value() / 100.0
        max_tok = self.spin_max_tokens.value()

        restart_cfg = LLMSettings(
            mode=mode_val,
            host=self.llm_cfg.host,
            port=self.llm_cfg.port,
            ctx=ctx,
            kv_type=kv_type,
            max_tokens=max_tok,
            temperature=temp,
            model=model_rel,
            mmproj=mmproj_rel,
        )

        self.lbl_srv_status.setText("Stopping active llama-server...")
        self.lbl_srv_status.setStyleSheet("color: #fbbf24; font-weight: bold;")
        self.btn_restart_llm.setEnabled(False)

        self.server_worker = ServerRestartWorker(restart_cfg, self.app_config.home_dir)
        self.server_worker.status_signal.connect(self.lbl_srv_status.setText)
        self.server_worker.finished_signal.connect(self._on_server_restart_finished)
        self.server_worker.start()

    def _on_server_restart_finished(self, success: bool, msg: str) -> None:
        self.btn_restart_llm.setEnabled(True)
        if success:
            self.lbl_srv_status.setText(msg)
            self.lbl_srv_status.setStyleSheet("color: #58d68d; font-weight: bold;")
        else:
            self.lbl_srv_status.setText(f"Error: {msg}")
            self.lbl_srv_status.setStyleSheet("color: #f87171; font-weight: bold;")

    def _start_model_download(self) -> None:
        url = self.line_model_url.text().strip()
        if not url:
            self.lbl_download_status.setText("Please enter a valid model download URL.")
            return

        if not url.startswith("https://"):
            self.lbl_download_status.setText(
                "Error: Only secure HTTPS download URLs are permitted."
            )
            return

        filename = url.split("/")[-1].split("?")[0] or "custom_model.gguf"
        if not filename.endswith(".gguf"):
            self.lbl_download_status.setText("Error: File must have a .gguf extension.")
            return

        dest = self.app_config.home_dir / "models" / "llm" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        self.lbl_download_status.setText(f"Starting download of {filename}...")
        self.btn_download_model.setEnabled(False)

        self.download_worker = ModelDownloadWorker(url, dest)
        self.download_worker.progress_signal.connect(self._on_download_progress)
        self.download_worker.finished_signal.connect(self._on_download_finished)
        self.download_worker.start()

    def _on_download_progress(
        self, pct: int, dl_mb: float, tot_mb: float, speed_mbs: float
    ) -> None:
        self.progress_download.setValue(pct)
        self.lbl_download_status.setText(
            f"Downloading: {dl_mb:.1f} MB / {tot_mb:.1f} MB ({pct}%) at {speed_mbs:.2f} MB/s"
        )

    def _on_download_finished(self, success: bool, msg: str) -> None:
        self.btn_download_model.setEnabled(True)
        self.lbl_download_status.setText(msg)
        if success:
            self._refresh_model_registry()

    # TAB 3: Tool Studio & Whitelist
    # =========================================================================
    def _build_tools_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)

        grp_tools = QGroupBox("Approved Application Whitelist & Permissions", parent)
        v_tools = QVBoxLayout(grp_tools)

        self.table_apps = QTableWidget(len(self.whitelisted_apps), 4, grp_tools)
        self.table_apps.setHorizontalHeaderLabels(
            ["App Name", "Executable Path", "Risk Tier", "Status"]
        )
        hdr_apps = self.table_apps.horizontalHeader()
        if hdr_apps is not None:
            hdr_apps.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for row, app in enumerate(self.whitelisted_apps):
            self.table_apps.setItem(row, 0, QTableWidgetItem(app["name"]))
            self.table_apps.setItem(row, 1, QTableWidgetItem(app["path"]))
            self.table_apps.setItem(row, 2, QTableWidgetItem(app["tier"]))
            self.table_apps.setItem(row, 3, QTableWidgetItem(app["status"]))

        v_tools.addWidget(self.table_apps)

        h_tools_act = QHBoxLayout()
        btn_add_app = QPushButton("➕ Add Application (.exe)", grp_tools)
        btn_add_app.clicked.connect(self._add_app_dialog)
        h_tools_act.addWidget(btn_add_app)

        btn_remove_app = QPushButton("🗑️ Remove Selected", grp_tools)
        btn_remove_app.clicked.connect(self._remove_app)
        h_tools_act.addWidget(btn_remove_app)

        btn_toggle_app = QPushButton("⚡ Toggle Active / Disabled", grp_tools)
        btn_toggle_app.clicked.connect(self._toggle_app_status)
        h_tools_act.addWidget(btn_toggle_app)

        h_tools_act.addStretch()
        v_tools.addLayout(h_tools_act)
        layout.addWidget(grp_tools)
        layout.addStretch()

    FORBIDDEN_SHELLS = {"cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "wsl.exe"}

    def _add_app_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Approved Executable", "C:\\\\", "Executables (*.exe);;All Files (*.*)"
        )
        if path:
            exe_name = Path(path).name.lower()
            if exe_name in self.FORBIDDEN_SHELLS:
                QMessageBox.warning(
                    self,
                    "Security Restriction (D-AUD-10)",
                    f"Shell execution via '{exe_name}' is strictly forbidden by Project Lucca security policy D-AUD-10.",
                )
                return

            name = Path(path).stem.replace("_", " ").title()
            key = Path(path).stem.lower().replace(" ", "_")
            new_entry = {
                "key": key,
                "name": name,
                "path": path,
                "tier": "User-Added",
                "status": "Active",
            }
            self.whitelisted_apps.append(new_entry)
            save_whitelist_apps(self.whitelisted_apps)

            row = self.table_apps.rowCount()
            self.table_apps.insertRow(row)
            self.table_apps.setItem(row, 0, QTableWidgetItem(name))
            self.table_apps.setItem(row, 1, QTableWidgetItem(path))
            self.table_apps.setItem(row, 2, QTableWidgetItem("User-Added"))
            self.table_apps.setItem(row, 3, QTableWidgetItem("Active"))

    def _remove_app(self) -> None:
        row = self.table_apps.currentRow()
        if row >= 0:
            if row < len(self.whitelisted_apps):
                self.whitelisted_apps.pop(row)
                save_whitelist_apps(self.whitelisted_apps)
            self.table_apps.removeRow(row)

    def _toggle_app_status(self) -> None:
        row = self.table_apps.currentRow()
        if row >= 0:
            item = self.table_apps.item(row, 3)
            if item:
                new_status = "Disabled" if item.text() == "Active" else "Active"
                item.setText(new_status)
                if row < len(self.whitelisted_apps):
                    self.whitelisted_apps[row]["status"] = new_status
                    save_whitelist_apps(self.whitelisted_apps)

    # =========================================================================
    # TAB 4: MicroScheme LISP Reasoning Studio
    # =========================================================================
    def _build_lisp_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(10)

        grp_lisp = QGroupBox("MicroScheme Domain-Specific Reasoning Pathways", parent)
        v_lisp = QVBoxLayout(grp_lisp)

        # Category Filter
        h_filter = QHBoxLayout()
        h_filter.addWidget(QLabel("Category Filter:", grp_lisp))
        self.combo_lisp_cat = QComboBox(grp_lisp)
        self.combo_lisp_cat.addItem("All Categories")
        self.combo_lisp_cat.addItem("Hardware & Safety")
        self.combo_lisp_cat.addItem("Cognitive & Temporal")
        self.combo_lisp_cat.addItem("Tools & Execution")
        self.combo_lisp_cat.addItem("Persona & Inflection")
        self.combo_lisp_cat.addItem("Memory & Recall")
        self.combo_lisp_cat.currentTextChanged.connect(self._populate_lisp_table)
        h_filter.addWidget(self.combo_lisp_cat)
        h_filter.addStretch()

        btn_add_rule = QPushButton("➕ Add Reasoning Pathway", grp_lisp)
        btn_add_rule.clicked.connect(self._add_new_rule_dialog)
        h_filter.addWidget(btn_add_rule)
        v_lisp.addLayout(h_filter)

        # Rules Table
        self.table_lisp = QTableWidget(len(self.lisp_rules), 5, grp_lisp)
        self.table_lisp.setHorizontalHeaderLabels(
            ["Category", "Pathway ID", "Purpose", "Priority", "Status"]
        )
        hdr_lisp = self.table_lisp.horizontalHeader()
        if hdr_lisp is not None:
            hdr_lisp.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_lisp.cellClicked.connect(self._on_rule_selected)
        v_lisp.addWidget(self.table_lisp)

        self._populate_lisp_table()

        # In-Place S-Expression Code Editor
        v_lisp.addWidget(QLabel("Canonical MicroScheme S-Expression Definition:", grp_lisp))
        self.txt_rule_code = QPlainTextEdit(grp_lisp)
        self.txt_rule_code.setFont(QFont("Consolas", 10))
        self.txt_rule_code.setMaximumHeight(130)
        v_lisp.addWidget(self.txt_rule_code)

        # Validation and Action Controls
        h_lisp_acts = QHBoxLayout()
        btn_validate_rule = QPushButton("✓ Validate AST Syntax", grp_lisp)
        btn_validate_rule.clicked.connect(self._validate_current_rule)
        h_lisp_acts.addWidget(btn_validate_rule)

        btn_test_eval = QPushButton("▶ Test Evaluation", grp_lisp)
        btn_test_eval.clicked.connect(self._test_eval_rule)
        h_lisp_acts.addWidget(btn_test_eval)

        btn_save_rule = QPushButton("💾 Save Pathway Definition", grp_lisp)
        btn_save_rule.clicked.connect(self._save_selected_rule)
        h_lisp_acts.addWidget(btn_save_rule)

        btn_retire_rule = QPushButton("🗑️ Retire / Remove", grp_lisp)
        btn_retire_rule.clicked.connect(self._retire_selected_rule)
        h_lisp_acts.addWidget(btn_retire_rule)

        h_lisp_acts.addStretch()
        v_lisp.addLayout(h_lisp_acts)

        self.lbl_rule_status = QLabel("Select a pathway to inspect or edit definition.", grp_lisp)
        self.lbl_rule_status.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-style: italic;")
        v_lisp.addWidget(self.lbl_rule_status)

        layout.addWidget(grp_lisp)

    def _populate_lisp_table(self, filter_cat: str = "All Categories") -> None:
        self.table_lisp.setRowCount(0)
        for rule_id, data in self.lisp_rules.items():
            cat = data["category"]
            if filter_cat not in ("All Categories", cat):
                continue

            row = self.table_lisp.rowCount()
            self.table_lisp.insertRow(row)
            self.table_lisp.setItem(row, 0, QTableWidgetItem(cat))
            self.table_lisp.setItem(row, 1, QTableWidgetItem(rule_id))
            self.table_lisp.setItem(row, 2, QTableWidgetItem(data["purpose"]))
            self.table_lisp.setItem(row, 3, QTableWidgetItem(str(data["priority"])))
            self.table_lisp.setItem(row, 4, QTableWidgetItem(data["state"]))

    def _on_rule_selected(self, row: int, col: int) -> None:
        item = self.table_lisp.item(row, 1)
        if not item:
            return
        rule_id = item.text()
        if rule_id in self.lisp_rules:
            data = self.lisp_rules[rule_id]
            self.txt_rule_code.setPlainText(data["code"])
            self.lbl_rule_status.setText(f"Loaded definition for [{rule_id}] ({data['category']}).")

    def _validate_current_rule(self) -> None:
        code = self.txt_rule_code.toPlainText().strip()
        if not code:
            self.lbl_rule_status.setText("No code to validate.")
            return

        try:
            rule_obj = parse_rule(code)
            self.lbl_rule_status.setText(
                f"✓ Syntax valid! Parsed rule '{rule_obj.rule_id}' (Priority: {rule_obj.priority})."
            )
        except Exception as exc:
            self.lbl_rule_status.setText(f"Syntax error: {exc}")

    def _test_eval_rule(self) -> None:
        code = self.txt_rule_code.toPlainText().strip()
        try:
            rule_obj = parse_rule(code)
            sample_state = RuleState(
                intent="launch_app",
                entities={"app": ["calculator"]},
                apps_running=frozenset(),
                hour_local=14,
                weekday=1,
                session_turns=1,
                mode="transcript",
            )
            outcome = evaluate_rule(rule_obj, sample_state)
            if outcome.fired and outcome.plan:
                actions_summary = ", ".join(type(a).__name__ for a in outcome.plan.actions)
                self.lbl_rule_status.setText(
                    f"✓ Evaluated rule '{rule_obj.rule_id}': Conditions matched sample state. Actions: [{actions_summary}]."
                )
            else:
                self.lbl_rule_status.setText(
                    f"✓ Evaluated rule '{rule_obj.rule_id}': Evaluation executed cleanly (preconditions did not match sample state)."
                )
        except Exception as exc:
            self.lbl_rule_status.setText(f"Evaluation error: {exc}")

    def _save_selected_rule(self) -> None:
        row = self.table_lisp.currentRow()
        if row >= 0:
            item = self.table_lisp.item(row, 1)
            if item is not None:
                rule_id = item.text()
                code = self.txt_rule_code.toPlainText()
                if rule_id in self.lisp_rules:
                    self.lisp_rules[rule_id]["code"] = code
                    self.lbl_rule_status.setText(f"✓ Saved definition for [{rule_id}].")

    def _add_new_rule_dialog(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Add LISP Reasoning Pathway", "Enter Pathway Rule ID (e.g. custom-guard-v1):"
        )
        if ok and name:
            clean_name = name.strip()
            self.lisp_rules[clean_name] = {
                "category": "Cognitive & Temporal",
                "purpose": "Custom user-defined reasoning pathway.",
                "priority": 70,
                "state": "ACTIVE",
                "code": f'(rule "{clean_name}"\\n  :when (intent= "custom_action")\\n  :plan (say "Executing custom pathway!")\\n  :priority 70)',
            }
            self._populate_lisp_table(self.combo_lisp_cat.currentText())
            self.lbl_rule_status.setText(f"Added reasoning pathway [{clean_name}].")

    def _retire_selected_rule(self) -> None:
        row = self.table_lisp.currentRow()
        if row >= 0:
            item = self.table_lisp.item(row, 1)
            if item:
                rule_id = item.text()
                if rule_id in self.lisp_rules:
                    del self.lisp_rules[rule_id]
                    self._populate_lisp_table(self.combo_lisp_cat.currentText())
                    self.txt_rule_code.clear()
                    self.lbl_rule_status.setText(f"Retired and removed pathway [{rule_id}].")

    # =========================================================================
    # TAB 5: Hotkeys & Push-To-Talk
    # =========================================================================
    def _build_ptt_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)

        grp_ptt = QGroupBox("Universal Push-to-Talk & Hotkey Listeners", parent)
        f_ptt = QFormLayout(grp_ptt)

        self.combo_ptt_key = QComboBox(grp_ptt)
        self.combo_ptt_key.addItem("Alt-Gr / Right-Ctrl / Right-Shift (Universal Any)", "any")
        self.combo_ptt_key.addItem("Alt-Gr (Right Alt)", "alt_gr")
        self.combo_ptt_key.addItem("Right Control", "right_ctrl")
        self.combo_ptt_key.addItem("Right Shift", "right_shift")
        self.combo_ptt_key.addItem("Left Control", "left_ctrl")
        self.combo_ptt_key.addItem("Spacebar", "space")

        idx = self.combo_ptt_key.findData(self.current_ptt_key)
        if idx >= 0:
            self.combo_ptt_key.setCurrentIndex(idx)
        f_ptt.addRow("Primary Push-to-Talk Key:", self.combo_ptt_key)

        self.combo_ptt_mode = QComboBox(grp_ptt)
        self.combo_ptt_mode.addItem("Hold-to-Talk (Records while key held down)", "hold")
        self.combo_ptt_mode.addItem("Toggle Mode (Press to start, press to stop)", "toggle")
        f_ptt.addRow("Hotkey Operation Mode:", self.combo_ptt_mode)

        self.spin_max_rec = QSpinBox(grp_ptt)
        self.spin_max_rec.setRange(5, 60)
        self.spin_max_rec.setValue(30)
        self.spin_max_rec.setSuffix(" seconds")
        f_ptt.addRow("Max Utterance Ceiling:", self.spin_max_rec)

        self.chk_wake_word = QCheckBox("Enable Hands-Free Local Wake Word ('Lucca')", grp_ptt)
        self.chk_wake_word.setChecked(True)
        f_ptt.addRow("Hands-Free Trigger:", self.chk_wake_word)

        layout.addWidget(grp_ptt)
        layout.addStretch()

    # =========================================================================
    # =========================================================================
    # TAB 6: Granular DSP Audio Post-Processing Suite
    # =========================================================================
    def _build_dsp_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)

        # Quick Anime DSP Preset Bar
        grp_anime_dsp = QGroupBox("English Anime Voice DSP Presets", parent)
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

        grp_dsp = QGroupBox("Master Output Processing Chain", parent)
        f_dsp = QFormLayout(grp_dsp)

        # 1. Voice Pitch Shifter (-12 to +12 semitones)
        h_pitch = QHBoxLayout()
        self.slider_pitch = QSlider(Qt.Orientation.Horizontal, grp_dsp)
        self.slider_pitch.setRange(-12, 12)
        self.slider_pitch.setValue(0)
        self.lbl_pitch_val = QLabel("0 semitones (Natural)", grp_dsp)
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
        self.chk_limiter.setChecked(True)
        f_dsp.addRow("Dynamic Protection:", self.chk_limiter)

        self.chk_rumble = QCheckBox(
            "120 Hz High-Pass Filter (Removes muddy chest resonance)", grp_dsp
        )
        self.chk_rumble.setChecked(True)
        f_dsp.addRow("Acoustic Cleanup:", self.chk_rumble)

        layout.addWidget(grp_dsp)

        # Live DSP Test Player
        grp_dsp_test = QGroupBox("Live DSP Post-Processing Test Player", parent)
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
        voice = self.get_selected_voice_spec()
        speed = self.slider_speed.value() / 100.0

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

                # Use AnimeVoiceDSP processor if pitch is shifted or filters are active
                dsp = AnimeVoiceDSP(
                    AnimeDSPConfig(
                        pitch_semitones=float(pitch),
                        highpass_cutoff_hz=120.0 if self.chk_rumble.isChecked() else 20.0,
                        presence_gain_db=self.slider_treble.value() * 0.5,
                        master_gain_db=gain_db,
                    )
                )
                processed, play_sr = dsp.process(samples, sr=sr)

                # Reverb / echo if selected
                if reverb_pct > 0.02:
                    delay_samples = int(play_sr * 0.08)
                    padded = np.pad(processed, (0, delay_samples))
                    echo = np.pad(processed, (delay_samples, 0)) * (reverb_pct * 0.5)
                    processed = ((padded + echo)[: len(processed)]).astype(np.float32)

                sd.play(processed, play_sr)
                sd.wait()
                self.lbl_dsp_status.setText("✓ DSP playback complete.")
            except Exception as exc:
                self.lbl_dsp_status.setText(f"DSP error: {exc}")
            finally:
                self.btn_test_dsp.setEnabled(True)

        threading.Thread(target=worker, daemon=True).start()

    # TAB 7: Episodic & Semantic Memory System
    # =========================================================================
    def _build_memory_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(10)

        # Database Stats Header Banner
        grp_stats = QGroupBox("Memory Store Statistics & Database Topology", parent)
        h_stats = QHBoxLayout(grp_stats)
        self.lbl_mem_stat_active = QLabel("Active: --", grp_stats)
        self.lbl_mem_stat_total = QLabel("Total Records: --", grp_stats)
        self.lbl_mem_stat_size = QLabel("Disk Size: --", grp_stats)
        self.lbl_mem_stat_active.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.lbl_mem_stat_total.setStyleSheet("color: #ffffff; font-weight: bold;")
        self.lbl_mem_stat_size.setStyleSheet("color: #38bdf8; font-weight: bold;")
        h_stats.addWidget(self.lbl_mem_stat_active)
        h_stats.addWidget(self.lbl_mem_stat_total)
        h_stats.addWidget(self.lbl_mem_stat_size)
        h_stats.addStretch()

        btn_vacuum = QPushButton("🧹 Vacuum & Optimize DB", grp_stats)
        btn_vacuum.clicked.connect(self._vacuum_memory_db)
        h_stats.addWidget(btn_vacuum)
        layout.addWidget(grp_stats)

        # Filter & Search Toolbar
        grp_filter = QGroupBox("Memory Explorer, Semantic Filters & Knowledge Inspector", parent)
        v_filter = QVBoxLayout(grp_filter)

        h_toolbar = QHBoxLayout()
        h_toolbar.addWidget(QLabel("Category Filter:", grp_filter))
        self.combo_mem_kind = QComboBox(grp_filter)
        self.combo_mem_kind.addItem("All Categories", "")
        self.combo_mem_kind.addItem("Episodic Conversation Turns", "episodic")
        self.combo_mem_kind.addItem("Semantic Facts & Knowledge", "fact")
        self.combo_mem_kind.addItem("User Preferences", "preference")
        self.combo_mem_kind.currentIndexChanged.connect(self._refresh_memories)
        h_toolbar.addWidget(self.combo_mem_kind)

        self.line_mem_search = QLineEdit(grp_filter)
        self.line_mem_search.setPlaceholderText("Search content, intent keywords, or provenance...")
        self.line_mem_search.returnPressed.connect(self._refresh_memories)
        h_toolbar.addWidget(self.line_mem_search, stretch=2)

        btn_search = QPushButton("🔍 Search", grp_filter)
        btn_search.clicked.connect(self._refresh_memories)
        h_toolbar.addWidget(btn_search)

        btn_add_fact = QPushButton("➕ Teach New Fact", grp_filter)
        btn_add_fact.clicked.connect(self._add_new_fact_dialog)
        h_toolbar.addWidget(btn_add_fact)

        v_filter.addLayout(h_toolbar)

        # Memory Table
        self.table_mem = QTableWidget(0, 6, grp_filter)
        self.table_mem.setHorizontalHeaderLabels(
            ["ID", "Kind", "Content / Fact Statement", "Importance", "Provenance", "Created At"]
        )
        hdr_mem = self.table_mem.horizontalHeader()
        if hdr_mem is not None:
            hdr_mem.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_mem.cellClicked.connect(self._on_memory_selected)
        v_filter.addWidget(self.table_mem)

        # Selected Memory Inspector & Editor
        grp_inspect = QGroupBox("Selected Memory Inspector & Human-in-the-Loop Editor", grp_filter)
        v_inspect = QVBoxLayout(grp_inspect)

        h_meta = QHBoxLayout()
        self.lbl_inspect_id = QLabel("Memory ID: None", grp_inspect)
        self.lbl_inspect_prov = QLabel("Provenance: None", grp_inspect)
        self.lbl_inspect_conf = QLabel("Confidence: 1.0", grp_inspect)
        self.lbl_inspect_id.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        h_meta.addWidget(self.lbl_inspect_id)
        h_meta.addWidget(self.lbl_inspect_prov)
        h_meta.addWidget(self.lbl_inspect_conf)
        h_meta.addStretch()
        v_inspect.addLayout(h_meta)

        self.txt_inspect_content = QPlainTextEdit(grp_inspect)
        self.txt_inspect_content.setFont(QFont("Consolas", 10))
        self.txt_inspect_content.setMaximumHeight(70)
        v_inspect.addWidget(self.txt_inspect_content)

        h_edit_act = QHBoxLayout()
        h_edit_act.addWidget(QLabel("Importance:", grp_inspect))
        self.slider_inspect_imp = QSlider(Qt.Orientation.Horizontal, grp_inspect)
        self.slider_inspect_imp.setRange(0, 100)
        self.slider_inspect_imp.setValue(80)
        self.lbl_inspect_imp_val = QLabel("0.80", grp_inspect)
        self.slider_inspect_imp.valueChanged.connect(
            lambda val: self.lbl_inspect_imp_val.setText(f"{(val / 100.0):.2f}")
        )
        h_edit_act.addWidget(self.slider_inspect_imp)
        h_edit_act.addWidget(self.lbl_inspect_imp_val)

        btn_save_mem = QPushButton("💾 Save Changes", grp_inspect)
        btn_save_mem.clicked.connect(self._save_memory_changes)
        h_edit_act.addWidget(btn_save_mem)

        btn_del_mem = QPushButton("🗑️ Prune Memory", grp_inspect)
        btn_del_mem.clicked.connect(self._delete_selected_memory)
        h_edit_act.addWidget(btn_del_mem)

        h_edit_act.addStretch()
        v_inspect.addLayout(h_edit_act)

        v_filter.addWidget(grp_inspect)
        layout.addWidget(grp_filter)

        self._current_selected_mid: int | None = None
        self._refresh_memories()

    def _refresh_memories(self) -> None:
        if self.memory_manager is None:
            return

        # Update stats
        try:
            st = self.memory_manager.get_stats()
            self.lbl_mem_stat_active.setText(f"Active Memories: {st.get('active_memories', 0)}")
            self.lbl_mem_stat_total.setText(f"Total Records: {st.get('total_memories', 0)}")
            self.lbl_mem_stat_size.setText(f"DB Size: {st.get('db_size_kb', 0)} KB")
        except Exception:
            pass

        # Populate table
        search = self.line_mem_search.text().strip()
        kind_filter = str(self.combo_mem_kind.currentData())

        try:
            mems = self.memory_manager.list_memories(search=search)
            if kind_filter:
                mems = [m for m in mems if m.get("kind") == kind_filter]

            self.table_mem.setRowCount(0)
            for m in mems:
                row = self.table_mem.rowCount()
                self.table_mem.insertRow(row)

                mid = str(m.get("memory_id", ""))
                kind = str(m.get("kind", ""))
                content = str(m.get("content", ""))
                imp = f"{float(m.get('importance', 0.8)):.2f}"
                prov = str(m.get("provenance", "USER_EXPLICIT"))
                ts = datetime.fromtimestamp(float(m.get("created_at", time.time()))).strftime(
                    "%Y-%m-%d %H:%M"
                )

                self.table_mem.setItem(row, 0, QTableWidgetItem(mid))
                self.table_mem.setItem(row, 1, QTableWidgetItem(kind))
                self.table_mem.setItem(row, 2, QTableWidgetItem(content))
                self.table_mem.setItem(row, 3, QTableWidgetItem(imp))
                self.table_mem.setItem(row, 4, QTableWidgetItem(prov))
                self.table_mem.setItem(row, 5, QTableWidgetItem(ts))
        except Exception as exc:
            print(f"[UI] Memory refresh error: {exc}")

    def _on_memory_selected(self, row: int, col: int) -> None:
        item = self.table_mem.item(row, 0)
        if not item:
            return
        try:
            mid = int(item.text())
            self._current_selected_mid = mid
            content_item = self.table_mem.item(row, 2)
            imp_item = self.table_mem.item(row, 3)
            prov_item = self.table_mem.item(row, 4)

            self.lbl_inspect_id.setText(f"Memory ID: #{mid}")
            self.lbl_inspect_prov.setText(
                f"Provenance: {prov_item.text() if prov_item else 'Unknown'}"
            )
            if content_item:
                self.txt_inspect_content.setPlainText(content_item.text())
            if imp_item:
                val = int(float(imp_item.text()) * 100)
                self.slider_inspect_imp.setValue(val)
        except Exception:
            pass

    def _save_memory_changes(self) -> None:
        if self._current_selected_mid is None or self.memory_manager is None:
            return
        new_txt = self.txt_inspect_content.toPlainText().strip()
        imp = self.slider_inspect_imp.value() / 100.0
        try:
            self.memory_manager.update_memory(self._current_selected_mid, new_txt, imp)
            self._refresh_memories()
            QMessageBox.information(
                self, "Memory Updated", f"Memory #{self._current_selected_mid} saved successfully."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save memory: {exc}")

    def _delete_selected_memory(self) -> None:
        if self._current_selected_mid is None or self.memory_manager is None:
            return
        res = QMessageBox.question(
            self, "Confirm Deletion", f"Permanently prune memory #{self._current_selected_mid}?"
        )
        if res == QMessageBox.StandardButton.Yes:
            try:
                self.memory_manager.delete_memory(self._current_selected_mid, hard=True)
                self._current_selected_mid = None
                self.txt_inspect_content.clear()
                self._refresh_memories()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed to delete memory: {exc}")

    def _add_new_fact_dialog(self) -> None:
        if self.memory_manager is None:
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Teach Lucca a Fact", "Enter knowledge statement or preference:"
        )
        if ok and text.strip():
            try:
                mid = self.memory_manager.add_memory(
                    content=text.strip(),
                    kind="fact",
                    importance=0.85,
                    provenance="USER_EXPLICIT",
                )
                self._refresh_memories()
                QMessageBox.information(
                    self, "Knowledge Stored", f"Stored fact as memory #{mid} with vector embedding."
                )
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed to add fact: {exc}")

    def _vacuum_memory_db(self) -> None:
        if self.memory_manager is None:
            return
        try:
            conn = self.memory_manager.get_connection()
            conn.execute("VACUUM")
            conn.close()
            self._refresh_memories()
            QMessageBox.information(
                self, "Vacuum Complete", "SQLite database and vector indices optimized."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Vacuum failed: {exc}")

    # =========================================================================
    # TAB 8: Telemetry & Live Session Logs
    # =========================================================================
    def _build_diag_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setSpacing(10)

        # Live Substrate Snapshot
        grp_snap = QGroupBox("Live Host Computing Substrates (1000ms Polling)", parent)
        h_snap = QHBoxLayout(grp_snap)
        self.lbl_snap_dgpu = QLabel("dGPU: RTX 5080 (16 GB)", grp_snap)
        self.lbl_snap_npu = QLabel("NPU: AI Boost", grp_snap)
        self.lbl_snap_cpu = QLabel("CPU: Ultra 9 275HX", grp_snap)
        self.lbl_snap_ram = QLabel("RAM: 16 GB Total", grp_snap)
        self.lbl_snap_dgpu.setStyleSheet(f"color: {CT_GOLD_TEXT}; font-weight: bold;")
        self.lbl_snap_npu.setStyleSheet("color: #58d68d; font-weight: bold;")
        self.lbl_snap_cpu.setStyleSheet("color: #f39c12; font-weight: bold;")
        self.lbl_snap_ram.setStyleSheet("color: #38bdf8; font-weight: bold;")
        h_snap.addWidget(self.lbl_snap_dgpu)
        h_snap.addWidget(self.lbl_snap_npu)
        h_snap.addWidget(self.lbl_snap_cpu)
        h_snap.addWidget(self.lbl_snap_ram)
        h_snap.addStretch()

        btn_refresh_snap = QPushButton("🔄 Refresh Snapshot", grp_snap)
        btn_refresh_snap.clicked.connect(self._refresh_diag_snapshot)
        h_snap.addWidget(btn_refresh_snap)
        layout.addWidget(grp_snap)

        # Embedded Session Telemetry Log Viewer
        grp_logs = QGroupBox("Session Telemetry Log Viewer & Progression History", parent)
        v_logs = QVBoxLayout(grp_logs)

        h_log_ctrl = QHBoxLayout()
        h_log_ctrl.addWidget(QLabel("Session Log File:", grp_logs))
        self.combo_log_files = QComboBox(grp_logs)
        self.combo_log_files.currentIndexChanged.connect(self._load_selected_log_file)
        h_log_ctrl.addWidget(self.combo_log_files, stretch=2)

        self.btn_refresh_logs = QPushButton("🔄 Reload File", grp_logs)
        self.btn_refresh_logs.clicked.connect(self._scan_and_reload_logs)
        h_log_ctrl.addWidget(self.btn_refresh_logs)

        self.chk_auto_tail = QCheckBox("▶ Auto-Tail Live (1s)", grp_logs)
        self.chk_auto_tail.setChecked(True)
        h_log_ctrl.addWidget(self.chk_auto_tail)

        btn_open_folder = QPushButton("📁 Open Logs Directory", grp_logs)
        btn_open_folder.clicked.connect(self._open_logs_dir)
        h_log_ctrl.addWidget(btn_open_folder)

        v_logs.addLayout(h_log_ctrl)

        # Dual View Tabs: Parsed Table vs Raw JSONL
        self.tabs_log_view = QTabWidget(grp_logs)

        # Tab A: Parsed Metrics Table
        self.table_logs = QTableWidget(0, 6, grp_logs)
        self.table_logs.setHorizontalHeaderLabels(
            [
                "Timestamp",
                "Host RAM %",
                "Lucca RSS (MB)",
                "dGPU VRAM (Used / Total)",
                "CPU % (Host / Lucca)",
                "NPU Status",
            ]
        )
        hdr_logs = self.table_logs.horizontalHeader()
        if hdr_logs is not None:
            hdr_logs.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr_logs.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabs_log_view.addTab(self.table_logs, "📊 Parsed Telemetry Table")

        # Tab B: Raw JSONL Log Viewer
        self.txt_raw_log = QPlainTextEdit(grp_logs)
        self.txt_raw_log.setReadOnly(True)
        self.txt_raw_log.setFont(QFont("Consolas", 9))
        self.tabs_log_view.addTab(self.txt_raw_log, "📄 Raw JSONL Text")

        v_logs.addWidget(self.tabs_log_view)
        layout.addWidget(grp_logs)

        # Auto-tail timer (only active when Tab 8 is visible)
        self.log_tail_timer = QTimer(self)
        self.log_tail_timer.setInterval(1000)
        self.log_tail_timer.timeout.connect(self._on_log_tail_tick)
        self.log_tail_timer.start()

    def _on_tab_changed(self, index: int) -> None:
        """Loads telemetry and log files on demand when switching to Tab 8."""
        if index == 8:
            self._refresh_diag_snapshot()
            self._scan_and_reload_logs()

    def _refresh_diag_snapshot(self) -> None:
        try:
            m = get_system_metrics()
            ram = m["ram"]
            dgpu = m["dgpu"]
            cpu = m["cpu"]
            npu = m["npu"]

            self.lbl_snap_ram.setText(
                f"RAM: {ram['percent']}% (Lucca {ram.get('lucca_used_mb', 0):.0f} MB)"
            )
            self.lbl_snap_dgpu.setText(
                f"dGPU: {dgpu.get('used_gb', 0):.1f} / {dgpu.get('total_gb', 16.0):.1f} GB"
            )
            self.lbl_snap_cpu.setText(
                f"CPU: {cpu['system_percent']:.1f}% (Lucca {cpu['lucca_percent']:.1f}%)"
            )
            self.lbl_snap_npu.setText(f"NPU: {npu['status'].split(' ')[0]}")
        except Exception:
            pass

    def _scan_and_reload_logs(self) -> None:
        log_dir = Path("C:/ProjectLucca/logs/resource_sessions")
        log_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(list(log_dir.glob("*.jsonl")), reverse=True)

        current = self.combo_log_files.currentData()
        self.combo_log_files.blockSignals(True)
        self.combo_log_files.clear()
        for f in files:
            size_kb = round(f.stat().st_size / 1024, 1)
            self.combo_log_files.addItem(f"{f.name} ({size_kb} KB)", str(f))

        # Check general traces as fallback
        traces_file = Path("C:/ProjectLucca/logs/traces.jsonl")
        if traces_file.exists():
            self.combo_log_files.addItem(
                f"traces.jsonl ({round(traces_file.stat().st_size / 1024, 1)} KB)", str(traces_file)
            )

        if current:
            idx = self.combo_log_files.findData(current)
            if idx >= 0:
                self.combo_log_files.setCurrentIndex(idx)
        self.combo_log_files.blockSignals(False)

        self._load_selected_log_file()

    def _load_selected_log_file(self) -> None:
        path_str = self.combo_log_files.currentData()
        if not path_str or not Path(path_str).exists():
            return

        try:
            text = Path(path_str).read_text(encoding="utf-8")
            self.txt_raw_log.setPlainText(text)

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            self.table_logs.setRowCount(0)

            # Show last 50 entries
            for line in lines[-50:]:
                try:
                    data = json.loads(line)
                    ts = data.get("timestamp", "")
                    if "T" in ts:
                        ts = ts.split("T")[1].split(".")[0]

                    ram = data.get("ram", {})
                    dgpu = data.get("dgpu", {})
                    cpu = data.get("cpu", {})
                    npu = data.get("npu", {})

                    row = self.table_logs.rowCount()
                    self.table_logs.insertRow(row)
                    self.table_logs.setItem(row, 0, QTableWidgetItem(ts))
                    self.table_logs.setItem(
                        row, 1, QTableWidgetItem(f"{ram.get('percent', 0):.1f}%")
                    )
                    self.table_logs.setItem(
                        row,
                        2,
                        QTableWidgetItem(
                            f"{ram.get('lucca_rss_mb', ram.get('lucca_used_mb', 0)):.0f} MB"
                        ),
                    )
                    self.table_logs.setItem(
                        row,
                        3,
                        QTableWidgetItem(
                            f"{dgpu.get('used_vram_gb', dgpu.get('used_gb', 0)):.1f} / {dgpu.get('total_vram_gb', dgpu.get('total_gb', 16.0)):.1f} GB"
                        ),
                    )
                    self.table_logs.setItem(
                        row,
                        4,
                        QTableWidgetItem(
                            f"{cpu.get('system_percent', 0):.1f}% / {cpu.get('lucca_percent', 0):.1f}%"
                        ),
                    )
                    self.table_logs.setItem(
                        row, 5, QTableWidgetItem(str(npu.get("status", "Active")))
                    )
                except Exception:
                    pass

            self.table_logs.scrollToBottom()
        except Exception as exc:
            self.txt_raw_log.setPlainText(f"Error loading log file: {exc}")

    def _on_log_tail_tick(self) -> None:
        if self.chk_auto_tail.isChecked() and self.isVisible() and self.tabs.currentIndex() == 8:
            self._refresh_diag_snapshot()
            self._load_selected_log_file()

    def _open_logs_dir(self) -> None:
        path = self.app_config.home_dir / "logs" / "resource_sessions"
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", str(path)])  # noqa: S603, S607

    # =========================================================================
    # TAB 9: Interactive User Manual (Split Chapter Browser)
    # =========================================================================
    def _build_manual_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal, parent)

        # Left Chapter Picker
        self.list_manual_chapters = QListWidget(splitter)
        self.list_manual_chapters.setMaximumWidth(230)
        self.list_manual_chapters.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

        chapters = [
            "1. Getting Started & Controls",
            "2. Avatar & Commorose Menu",
            "3. Voice Synthesis & Dual-Vector Mixing",
            "4. DSP Audio Post-Processing",
            "5. LLM Tuning & VRAM Sizing",
            "6. MicroScheme LISP Studio",
            "7. Episodic & Semantic Memory",
            "8. Hardware Telemetry & Matrix",
            "9. Application Whitelist & Workspace Security",
            "10. Troubleshooting & FAQ",
        ]
        for ch in chapters:
            self.list_manual_chapters.addItem(ch)
        splitter.addWidget(self.list_manual_chapters)

        # Right Formatted Content View
        self.txt_manual_body = QTextEdit(splitter)
        self.txt_manual_body.setReadOnly(True)
        splitter.addWidget(self.txt_manual_body)

        layout.addWidget(splitter)

        self.list_manual_chapters.currentRowChanged.connect(self._on_manual_chapter_selected)
        self.list_manual_chapters.setCurrentRow(0)

    def _on_manual_chapter_selected(self, index: int) -> None:
        docs = [
            # 0. Getting Started
            """<h2 style='color:#ffd700;'>1. Getting Started & Core Controls</h2>
            <p>Welcome to <strong>Project Lucca</strong>, a local-first autonomous desktop companion powered by high-performance neural computing and retro companion aesthetics.</p>
            <h3 style='color:#38bdf8;'>Core Interaction Rules:</h3>
            <ul>
                <li><strong>Single-Click Lucca:</strong> Toggles the subtitle dialogue bubble and quick chat input bar with click-to-talk button (<code>🎙️</code>).</li>
                <li><strong>Double-Click Lucca:</strong> Opens the Battlefield-style concentric Commorose radial menu. Double-clicking her again closes it.</li>
                <li><strong>Drag to Reposition:</strong> Click and drag Lucca anywhere across your screens. Dialogue bubbles and chat bars stay anchored to her.</li>
                <li><strong>Right-Click Lucca:</strong> Brings up the desktop context menu (Always-on-top toggle, Reset position, Settings, Quit).</li>
            </ul>""",
            # 1. Avatar & Commorose
            """<h2 style='color:#ffd700;'>2. Companion Avatar & Commorose Radial Menu</h2>
            <p>The Commorose is an 8-sector concentric radial menu with an open center hole leaving Lucca 100% visible at all times.</p>
            <h3 style='color:#38bdf8;'>Commorose Polar Sectors:</h3>
            <ul>
                <li><strong>📊 TELEMETRY (North):</strong> Floating Hardware Telemetry HUD with live 5-substrate meters.</li>
                <li><strong>⚙️ SETTINGS (North-East):</strong> Comprehensive 11-tab configuration suite.</li>
                <li><strong>💬 CHAT BAR (East):</strong> Toggles quick text input bar and subtitle speech bubble.</li>
                <li><strong>📁 FOLDERS (South-East):</strong> Opens Windows Explorer to Project Lucca home directory.</li>
                <li><strong>🧠 PERSONA (South):</strong> Switches persona archetype and inflection.</li>
                <li><strong>🎙️ VOICE (South-West):</strong> Kokoro-82M Voice Blender & Dual-vector tensor mixer.</li>
                <li><strong>🛠️ TOOLS (West):</strong> Application whitelist and execution security permissions.</li>
                <li><strong>💻 PROJECT (North-West):</strong> Opens the project directory in Explorer.</li>
            </ul>""",
            # 2. Voice Blender & Mixing
            """<h2 style='color:#ffd700;'>3. Voice Synthesis & Dual-Vector Mixing</h2>
            <p>Kokoro-82M uses 512-dimensional style embedding vectors. You can select from all <strong>54 installed voices</strong> or mix them in arbitrary ratios.</p>
            <h3 style='color:#38bdf8;'>Dual-Vector Tensor Blender:</h3>
            <ul>
                <li>Select <strong>Voice A</strong> and <strong>Voice B</strong> from the dropdowns.</li>
                <li>Move the blend slider to adjust the linear combination ratio (e.g. 70% A / 30% B).</li>
                <li>The engine calculates the weighted vector sum <code>wA * StyleA + wB * StyleB</code> in real time.</li>
                <li>Pacing slider allows fine-tuning speech tempo from 0.60x to 1.80x without pitch distortion.</li>
            </ul>""",
            # 3. DSP Audio Post-Processing
            """<h2 style='color:#ffd700;'>4. DSP Audio Post-Processing Chain</h2>
            <p>Lucca features a modular audio post-processing chain for pristine studio sound:</p>
            <ul>
                <li><strong>Pitch Shifter:</strong> Transpose vocal key by -6 to +6 semitones.</li>
                <li><strong>Master Gain Trim:</strong> Adjust overall output level from -12.0 dB to +6.0 dB.</li>
                <li><strong>Low-Mid Warmth (250 Hz):</strong> Boosts vocal body and warmth.</li>
                <li><strong>High Clarity / Air (6 kHz):</strong> Enhances presence and vocal intimacy.</li>
                <li><strong>SNES Reverb Emulation:</strong> Spatial ambient reflections reminiscent of classic Super Nintendo RPG sound chips.</li>
                <li><strong>Dynamic Soft-Knee Limiter:</strong> Prevents digital distortion and clipping during sudden loud exclamations.</li>
                <li><strong>80 Hz High-Pass Filter:</strong> Cleans up microphone rumble and AC hum.</li>
            </ul>""",
            # 4. LLM Server Tuning
            """<h2 style='color:#ffd700;'>5. LLM Tuning & Granular Context Window</h2>
            <p>Control the active local GGUF model served on your dGPU via <code>llama-server.exe</code>:</p>
            <ul>
                <li><strong>Context Window Slider:</strong> Adjust context length from 512 to 32,768 tokens in 256-token increments.</li>
                <li><strong>KV-Cache VRAM Calculator:</strong> Compares memory consumption across FP16, Q8_0, and Q4_0 quantizations against your 16.0 GB RTX 5080 VRAM ceiling.</li>
                <li><strong>Hot-Reload Server Restart:</strong> Re-launches the server with new arguments in under 2 seconds.</li>
                <li><strong>Integrated Model Downloader:</strong> Directly download GGUF weights from HuggingFace with live progress.</li>
            </ul>""",
            # 5. MicroScheme LISP Studio
            """<h2 style='color:#ffd700;'>6. MicroScheme LISP Reasoning Studio</h2>
            <p>Combines probabilistic LLM generation with deterministic, compiled S-expression reasoning pathways.</p>
            <ul>
                <li>Deterministic State -> Plan symbolic pathways that execute before neural inference.</li>
                <li>In-place Scheme code editor provides syntax validation via the MicroScheme parser.</li>
                <li>Custom rules can be authored, validated, and tested with isolated gas budgets.</li>
            </ul>""",
            # 6. Episodic & Semantic Memory
            """<h2 style='color:#ffd700;'>7. Episodic & Semantic Memory Architecture</h2>
            <p>Lucca stores memories in an auditable, human-readable SQLite database with <code>sqlite-vec</code> vector embeddings:</p>
            <ul>
                <li><strong>Episodic Memories:</strong> Conversation turns and user interactions recorded in real time.</li>
                <li><strong>Semantic Facts:</strong> Learned truths, project details, and technical preferences.</li>
                <li><strong>Human-in-the-Loop Editor:</strong> Search, edit, or prune any memory record directly from the UI.</li>
                <li><strong>Provenance Envelopes:</strong> Cryptographic SHA256 hashes and signer IDs guarantee memory integrity.</li>
            </ul>""",
            # 7. Hardware Substrates & Telemetry
            """<h2 style='color:#ffd700;'>8. Hardware Telemetry & Multi-Substrate Topology</h2>
            <p>Every resource meter in Project Lucca reflects actual physical host hardware:</p>
            <ul>
                <li><strong>dGPU (RTX 5080 Laptop GPU - 16.0 GB VRAM):</strong> llama-server.exe with Flash-Attention.</li>
                <li><strong>NPU (Intel AI Boost):</strong> Whisper speech recognition and vector embeddings via OpenVINO.</li>
                <li><strong>CPU (Intel Core Ultra 9 275HX - 24 Cores):</strong> Orchestrator, ZeroMQ IPC bus, and Kokoro TTS.</li>
                <li><strong>RAM (16.0 GB Host Physical):</strong> Tracks Lucca 4-process RSS footprint vs total host utilization.</li>
                <li><strong>Telemetry Logs:</strong> Rolling JSONL logs stored in <code>logs/resource_sessions/</code>.</li>
            </ul>""",
            # 8. Whitelist & Workspace Security
            """<h2 style='color:#ffd700;'>9. Application Whitelist & Workspace Security</h2>
            <p>Strict security controls govern all companion desktop tools:</p>
            <ul>
                <li><strong>Approved Application Whitelist:</strong> Only applications explicitly authorized in Tab 4 can be launched.</li>
                <li><strong>Workspace Isolation:</strong> File tools operate strictly within the sandboxed workspace directory.</li>
                <li><strong>Sandbox Constraints:</strong> Prohibits unauthorized file access, egress, or system modifications.</li>
            </ul>""",
            # 9. Troubleshooting & FAQ
            """<h2 style='color:#ffd700;'>10. Troubleshooting, Logs & Diagnostic FAQ</h2>
            <ul>
                <li><strong>Audio device not capturing?</strong> Open Tab 6 (Hotkeys) and verify your microphone is selected. Check that Kaspersky or Windows Privacy permits audio device access.</li>
                <li><strong>LLM server connection error?</strong> Go to Tab 3 and click <code>Restart LLM Server</code>. Check that port 8080 is not blocked.</li>
                <li><strong>Inspect live logs:</strong> Go to Tab 9 (Telemetry & Logs) to inspect parsed session metrics or view raw JSONL entries.</li>
            </ul>""",
        ]

        if 0 <= index < len(docs):
            self.txt_manual_body.setHtml(docs[index])

    # =========================================================================
    # TAB 10: Dedicated About Section
    # =========================================================================
    def _build_about_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        about_box = QGroupBox("Project Lucca — System Architecture & Details", parent)
        v_about = QVBoxLayout(about_box)

        txt_about = QTextEdit(about_box)
        txt_about.setReadOnly(True)
        txt_about.setHtml("""
            <div style="text-align: center; margin-bottom: 12px;">
                <h2 style="color: #ffd700; font-size: 20px; margin-bottom: 2px;">⏳ PROJECT LUCCA DESKTOP COMPANION</h2>
                <span style="color: #38bdf8; font-family: monospace; font-weight: bold;">Version 0.2.6</span>
            </div>

            <h4 style="color: #ffd700; border-bottom: 1px solid #4a62a8; padding-bottom: 4px;">Companion Origin & Purpose</h4>
            <p style="color: #ffffff; line-height: 1.5;">
                <strong>Lucca</strong> is an original, brilliant systems and hardware engineer companion.
                Armed with relentless scientific curiosity, deep expertise in systems architecture, and custom-built inventions, Lucca represents low-level software craftsmanship and retro-futuristic companion engineering.
            </p>

            <h4 style="color: #ffd700; border-bottom: 1px solid #4a62a8; padding-bottom: 4px; margin-top: 14px;">4-Process Decoupled Architecture</h4>
            <ul style="color: #ffffff; line-height: 1.5;">
                <li><strong>lucca-supervisor:</strong> Process lifecycle monitor, hardware watchdog, and configuration synchronizer.</li>
                <li><strong>lucca-audio:</strong> Sub-50ms real-time PortAudio ring buffers, Kokoro-82M TTS, and Faster-Whisper ASR.</li>
                <li><strong>lucca-npu:</strong> OpenVINO GenAI neural execution pipeline pinned to the Intel AI Boost NPU.</li>
                <li><strong>lucca-ui:</strong> Transparent, non-blocking PyQt6 desktop overlay, concentric Commorose, and SNES control suite.</li>
            </ul>

            <h4 style="color: #ffd700; border-bottom: 1px solid #4a62a8; padding-bottom: 4px; margin-top: 14px;">Physical Hardware Topology Detected on Host</h4>
            <ul style="color: #ffffff; line-height: 1.5;">
                <li><strong>dGPU:</strong> NVIDIA GeForce RTX 5080 Laptop GPU (16.0 GB GDDR7 VRAM, Flash-Attention enabled)</li>
                <li><strong>CPU:</strong> Intel Core Ultra 9 275HX (24 cores, 24 threads, up to 5.4 GHz)</li>
                <li><strong>Host RAM:</strong> 16.0 GB High-Speed System RAM</li>
                <li><strong>NPU:</strong> Intel AI Boost Neural Processing Unit (Low-power 15W dedicated AI engine)</li>
                <li><strong>iGPU:</strong> Intel Arc Graphics (Standby accelerator)</li>
            </ul>

            <h4 style="color: #ffd700; border-bottom: 1px solid #4a62a8; padding-bottom: 4px; margin-top: 14px;">Technology Stack & Acknowledgments</h4>
            <p style="color: #ffffff; line-height: 1.5;">
                Engineered with Python 3.12, PyQt6, PyZMQ, Kokoro-ONNX, Faster-Whisper, SQLite-vec, RapidFuzz, and MicroScheme.
                Developed in pair programming with Google DeepMind Advanced Agentic Coding.
            </p>

            <p style="color: #889ec8; font-size: 11px; margin-top: 12px; text-align: center;">
                Licensed under the MIT License.
            </p>
        """)
        v_about.addWidget(txt_about)
        layout.addWidget(about_box)

    # =========================================================================
    # =========================================================================
    # Configuration Apply & Lossless Save
    # =========================================================================
    def _handle_save(self) -> None:
        # 1. Save Persona to persona.toml losslessly via prompt_builder
        arch = str(self.combo_archetype.currentData())
        form = str(self.combo_formality.currentData())
        custom = self.txt_custom_prompt.toPlainText().strip()
        td = self.slider_tech.value() / 100.0
        wm = self.slider_warmth.value() / 100.0
        dr = self.slider_directness.value() / 100.0
        uses_name = self.chk_uses_name.isChecked()
        admits_unc = self.chk_admits_uncertainty.isChecked()
        never_pret = self.chk_never_pretend.isChecked()

        raw_refuse = self.line_refuse_topics.text().strip()
        refuse_list = [r.strip() for r in raw_refuse.split(",") if r.strip()]

        affect_en = self.chk_affect_enabled.isChecked()
        decay_tau = float(self.slider_affect_decay.value())
        max_speed = self.slider_affect_delta.value() / 100.0
        selected_voice = self.get_selected_voice_spec()
        selected_speed = self.slider_speed.value() / 100.0
        selected_ptt = str(self.combo_ptt_key.currentData())
        selected_pitch = float(self.slider_pitch.value())
        dsp_en = self.chk_limiter.isChecked() or abs(selected_pitch) > 0.1

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
        data = self.combo_llm_model.currentData()
        model_name = data["rel_path"] if data else self.llm_cfg.model

        cfg: dict[str, Any] = {
            "voice": selected_voice,
            "speed": selected_speed,
            "ptt_key": selected_ptt,
            "persona_archetype": arch,
            "formality": form,
            "custom_system_prompt": custom,
            "llm_model": model_name,
            "context_length": self.spin_context.value(),
            "pitch_semitones": selected_pitch,
            "dsp_enabled": dsp_en,
            "gain_db": self.slider_gain.value() * 0.5,
            "reverb_pct": self.slider_reverb.value(),
            "limiter_enabled": self.chk_limiter.isChecked(),
            "rumble_filter_enabled": self.chk_rumble.isChecked(),
        }

        if self.on_save_config is not None:
            self.on_save_config(cfg)

        self.accept()
