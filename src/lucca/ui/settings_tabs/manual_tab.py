"""
Project Lucca — Interactive User Manual Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QListWidget,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade


class ManualTab(QWidget):
    """Tab 9: Interactive User Manual (Split Chapter Browser)."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

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
