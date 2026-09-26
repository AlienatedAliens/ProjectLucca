"""
Project Lucca — LLM Architecture & Engine Tuning Tab
WO-18e (F-ARCH-104)
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lucca.brain.server_ctl import (
    is_healthy,
    scan_model_registry,
    start_server,
    stop_server,
)
from lucca.core.config import LLMSettings, get_config
from lucca.ui.theme import CT_GOLD_TEXT

if TYPE_CHECKING:
    from lucca.core.studio_facade import StudioFacade

_LOG = logging.getLogger(__name__)


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
            _LOG.debug("server_restart_failed: %s", exc)
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
            _LOG.debug("model_download_failed: %s", exc)
            self.finished_signal.emit(False, f"Download failed: {exc}")


class LLMTab(QWidget):
    """Tab 2: LLM Architecture & Engine Tuning (Model Registry & Honest Control)."""

    server_health_checked = pyqtSignal(bool, int)

    def __init__(self, dialog: QWidget, facade: StudioFacade) -> None:
        super().__init__()
        self.dialog = dialog
        self.facade = facade
        self.app_config = get_config()
        self.llm_cfg = self.app_config.llm
        self.download_worker: ModelDownloadWorker | None = None
        self.server_worker: ServerRestartWorker | None = None
        self.server_health_checked.connect(self._on_server_health_checked)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Dynamic Model Registry & GGUF Metadata Card
        grp_reg = QGroupBox(
            "Model Registry (Scanned from models/llm/*.gguf) & GGUF Metadata", self
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
        grp_ctx = QGroupBox("Granular Context Window & 15.0 GB RTX 5080 VRAM Fit Guard", self)
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
        grp_sampling = QGroupBox("Sampling Hyperparameters & Multimodal Mode", self)
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
        grp_srv = QGroupBox("Active LLM Inference Server Process Control", self)
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
        grp_dl = QGroupBox("Curated Model Catalog & Verified GGUF Downloader", self)
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
