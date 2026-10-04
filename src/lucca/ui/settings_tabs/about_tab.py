"""
Project Lucca — Dedicated About Section Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGroupBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade


class AboutTab(QWidget):
    """Tab 10: Dedicated About Section."""

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        about_box = QGroupBox("Project Lucca — System Architecture & Details", self)
        v_about = QVBoxLayout(about_box)

        txt_about = QTextEdit(about_box)
        txt_about.setReadOnly(True)
        txt_about.setHtml("""
            <div style="text-align: center; margin-bottom: 12px;">
                <h2 style="color: #ffd700; font-size: 20px; margin-bottom: 2px;">⏳ PROJECT LUCCA DESKTOP COMPANION</h2>
                <span style="color: #38bdf8; font-family: monospace; font-weight: bold;">Version 1.35.6 Production Release</span>
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

            <h4 style="color: #ffd700; border-bottom: 1px solid #4a62a8; padding-bottom: 4px; margin-top: 14px;">Cognitive Reasoning & Native Capabilities</h4>
            <ul style="color: #ffffff; line-height: 1.5;">
                <li><strong>Concert Layer:</strong> Bidirectional bridge between abductive neural generation and MicroScheme deductive invariant verification.</li>
                <li><strong>Defeasible Reasoning Rung:</strong> 4-tier standards of proof (Spark, Preponderance, Clear & Convincing, Beyond Reasonable Doubt) with Toulmin argumentation and Walton critical question schemes.</li>
                <li><strong>Practical Reasoning & Diagnostics:</strong> 8-step means-ends goal planning and host diagnostic self-reasoning.</li>
                <li><strong>24 Native Tools:</strong> Sandboxed workspace file operations, multimodal vision capture, safe clipboard text inspection, math computation, web research, and bi-temporal memory management.</li>
            </ul>

            <h4 style="color: #ffd700; border-bottom: 1px solid #4a62a8; padding-bottom: 4px; margin-top: 14px;">Physical Hardware Topology Detected on Host</h4>
            <ul style="color: #ffffff; line-height: 1.5;">
                <li><strong>dGPU:</strong> NVIDIA GeForce RTX 5080 Laptop GPU (16.0 GB GDDR7 VRAM, Flash-Attention enabled, dedicated compute Disp.A: Off)</li>
                <li><strong>CPU:</strong> Intel Core Ultra 9 275HX (24 cores, 24 threads, up to 5.4 GHz)</li>
                <li><strong>Host RAM:</strong> 16.0 GB High-Speed System RAM</li>
                <li><strong>NPU:</strong> Intel AI Boost Neural Processing Unit (Low-power 15W dedicated AI engine)</li>
                <li><strong>iGPU:</strong> Intel(R) Graphics iGPU (Windows desktop & DWM compositor offload)</li>
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
