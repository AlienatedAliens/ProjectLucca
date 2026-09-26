"""
Project Lucca — Settings Tabs Package
WO-18e (F-ARCH-104)

Decomposed tab widgets for SettingsDialog.
Each tab encapsulates its own layout, widgets, and signal handlers,
consuming the core domain via StudioFacade.
"""

from __future__ import annotations

from lucca.ui.settings_tabs.about_tab import AboutTab
from lucca.ui.settings_tabs.dsp_tab import DSPTab
from lucca.ui.settings_tabs.hotkeys_tab import HotkeysTab
from lucca.ui.settings_tabs.lisp_tab import LispTab
from lucca.ui.settings_tabs.llm_tab import LLMTab
from lucca.ui.settings_tabs.manual_tab import ManualTab
from lucca.ui.settings_tabs.memory_tab import MemoryTab
from lucca.ui.settings_tabs.persona_tab import PersonaTab
from lucca.ui.settings_tabs.telemetry_tab import TelemetryTab
from lucca.ui.settings_tabs.tools_tab import (
    FORBIDDEN_SHELLS,
    ToolsTab,
    load_whitelist_apps,
    save_whitelist_apps,
)
from lucca.ui.settings_tabs.voice_tab import VoiceTab

__all__ = [
    "AboutTab",
    "DSPTab",
    "FORBIDDEN_SHELLS",
    "HotkeysTab",
    "LLMTab",
    "LispTab",
    "ManualTab",
    "MemoryTab",
    "PersonaTab",
    "TelemetryTab",
    "ToolsTab",
    "VoiceTab",
    "load_whitelist_apps",
    "save_whitelist_apps",
]
