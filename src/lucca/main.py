"""
Project Lucca — Supervisor & Four-Process Lifecycle Entry Point
Spec 01 §1, §7, ADR-008
"""

import multiprocessing as mp
import subprocess
import sys
import time

import httpx

from lucca.core.config import get_config
from lucca.core.env_check import run_env_check
from lucca.core.orchestrator import Orchestrator
from lucca.senses.audio_proc import AudioProcess
from lucca.senses.npu_proc import NPUProcess
from lucca.ui.app import UIApplication


def run_audio_process() -> None:
    proc = AudioProcess()
    try:
        proc.start()
        while proc.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        proc.stop()


def run_npu_process() -> None:
    proc = NPUProcess()
    try:
        proc.start()
    except KeyboardInterrupt:
        proc.stop()


def run_ui_process() -> None:
    ui = UIApplication()
    try:
        ui.run()
    except KeyboardInterrupt:
        ui.quit()


class Supervisor:
    def __init__(self) -> None:
        self.config = get_config()
        self.llama_proc: subprocess.Popen[bytes] | None = None
        self.children: dict[str, mp.Process] = {}
        self.orchestrator: Orchestrator | None = None
        self.running = False

    def boot(self) -> None:
        print("=" * 65)
        print("  PROJECT LUCCA — SYSTEM BOOT (SUPERVISOR)")
        print("=" * 65)

        # T-BOOT-03: Security check: llama-server must never bind 0.0.0.0
        if self.config.llm.host == "0.0.0.0":  # noqa: S104
            sys.stderr.write(
                "FATAL [T-BOOT-03]: llama-server cannot bind 0.0.0.0. Bound to localhost only.\n"
            )
            sys.exit(3)

        # 1. Environment Verification
        print("[1/5] Verifying environment & hardware...")
        if run_env_check() != 0:
            sys.stderr.write("FATAL [T-BOOT-01]: Environment check failed.\n")
            sys.exit(1)

        # 2. Check / Start llama-server natively on Windows
        print("[2/5] Initializing llama-server on dGPU...")
        self._ensure_llama_server()

        # 3. Spawn NPU & AI Worker Process
        print("[3/5] Spawning lucca-npu...")
        npu_p = mp.Process(target=run_npu_process, name="lucca-npu", daemon=True)
        npu_p.start()
        self.children["npu"] = npu_p

        # 4. Spawn Audio Subsystem (sounddevice + PTT)
        print("[4/5] Spawning lucca-audio...")
        audio_p = mp.Process(target=run_audio_process, name="lucca-audio", daemon=True)
        audio_p.start()
        self.children["audio"] = audio_p

        # 5. Spawn Desktop Avatar UI (PyQt6)
        if self.config.ui.enabled:
            print("[5/5] Spawning lucca-ui...")
            ui_p = mp.Process(target=run_ui_process, name="lucca-ui", daemon=True)
            ui_p.start()
            self.children["ui"] = ui_p

        # Start Core Orchestrator in supervisor process
        print("Starting core orchestrator...")
        self.orchestrator = Orchestrator()
        self.orchestrator.start()
        self.running = True

        print("=" * 65)
        print(f"  LUCCA ONLINE: All 4 processes active. (LLM Mode: {self.config.llm.mode.upper()})")
        print("  Press Right-Ctrl or Alt-Gr to talk to Lucca.")
        print("=" * 65)

    def _ensure_llama_server(self) -> None:
        url = f"http://{self.config.llm.host}:{self.config.llm.port}/health"
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                print("  llama-server is already active and healthy.")
                return
        except (httpx.HTTPError, OSError):
            pass

        # Launch llama-server.exe
        llama_exe = self.config.home_dir / "app" / "llama-server" / "llama-server.exe"
        model_gguf = self.config.home_dir / self.config.llm.model
        mmproj_gguf = self.config.home_dir / self.config.llm.mmproj

        cmd = [
            str(llama_exe),
            "--model", str(model_gguf),
            "--n-gpu-layers", "99",
            "--ctx-size", str(self.config.llm.ctx),
            "--cache-type-k", self.config.llm.kv_type,
            "--cache-type-v", self.config.llm.kv_type,
            "--parallel", "1",
            "--flash-attn", "on",
            "--host", self.config.llm.host,
            "--port", str(self.config.llm.port),
            "--no-webui",
            "--jinja",
            "--log-format", "json",
        ]
        if self.config.llm.mode == "audio" and mmproj_gguf.exists():
            cmd.extend(["--mmproj", str(mmproj_gguf)])

        self.llama_proc = subprocess.Popen(  # noqa: S603
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        # Poll /health up to 60s
        t0 = time.time()
        while time.time() - t0 < 60.0:
            try:
                r = httpx.get(url, timeout=1.0)
                if r.status_code == 200:
                    print(f"  llama-server ready in {time.time()-t0:.1f}s.")
                    return
            except (httpx.HTTPError, OSError):
                pass
            time.sleep(0.5)

        sys.stderr.write("FATAL: llama-server failed to respond on /health within 60s.\n")
        sys.exit(5)

    def run_forever(self) -> None:
        try:
            while self.running:
                # Supervise child processes
                for name, p in list(self.children.items()):
                    if not p.is_alive():
                        sys.stderr.write(
                            f"WARNING: Child process '{name}' exited with code {p.exitcode}.\n"
                        )
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self) -> None:
        print("\nOrdered shutdown initiated...")
        self.running = False
        if self.orchestrator:
            self.orchestrator.stop()

        for _name, p in self.children.items():
            if p.is_alive():
                p.terminate()
                p.join(timeout=2.0)
                if p.is_alive():
                    p.kill()

        if self.llama_proc and self.llama_proc.poll() is None:
            self.llama_proc.terminate()
            try:
                self.llama_proc.wait(timeout=3.0)
            except (subprocess.TimeoutExpired, OSError):
                self.llama_proc.kill()

        print("Shutdown complete.")


def main() -> None:
    # Set multiprocessing start method to spawn for Windows clean subprocesses
    mp.set_start_method("spawn", force=True)
    supervisor = Supervisor()
    supervisor.boot()
    supervisor.run_forever()


if __name__ == "__main__":
    main()
