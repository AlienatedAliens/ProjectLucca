"""
Project Lucca — Supervisor & Four-Process Lifecycle Entry Point
Spec 01 §1, §7, ADR-008
"""

import ctypes
import multiprocessing as mp
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001, S110
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001, S110
        pass

from lucca.brain.server_ctl import check_server_status, is_healthy, start_server
from lucca.core.config import get_config
from lucca.core.env_check import run_env_check
from lucca.core.orchestrator import Orchestrator
from lucca.senses.audio_proc import AudioProcess
from lucca.senses.npu_proc import NPUProcess
from lucca.ui.app import UIApplication


def _fake_child_proc() -> None:
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass


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
    finally:
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
        self._shutdown_done: bool = False
        self._restart_attempts: dict[str, list[float]] = {}
        self._next_restart: dict[str, float] = {}
        self.backoff_base: float = 1.0
        self.max_restart_backoff: float = 16.0
        self._targets: dict[str, Callable[[], None]] = {
            "npu": run_npu_process,
            "audio": run_audio_process,
            "ui": run_ui_process,
        }
        if os.environ.get("LUCCA_TEST_FAKES") == "1":
            self._targets = {
                "npu": _fake_child_proc,
                "audio": _fake_child_proc,
                "ui": _fake_child_proc,
            }

    def _spawn_child(self, name: str) -> mp.Process:
        target_fn = self._targets.get(name)
        if target_fn is None:
            raise ValueError(f"Unknown child target: {name}")
        p = mp.Process(target=target_fn, name=f"lucca-{name}", daemon=True)
        p.start()
        return p

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
        self.children["npu"] = self._spawn_child("npu")

        # 4. Spawn Audio Subsystem (sounddevice + PTT)
        print("[4/5] Spawning lucca-audio...")
        self.children["audio"] = self._spawn_child("audio")

        # 5. Spawn Desktop Avatar UI (PyQt6)
        if self.config.ui.enabled:
            print("[5/5] Spawning lucca-ui...")
            self.children["ui"] = self._spawn_child("ui")

        # Start Core Orchestrator in supervisor process
        print("Starting core orchestrator...")
        self.orchestrator = Orchestrator()
        self.orchestrator.start()
        self.running = True

        # Register peers for heartbeat monitoring
        for child_name in self.children:
            self.orchestrator.register_peer(child_name)

        print("=" * 65)
        print(f"  LUCCA ONLINE: All 4 processes active. (LLM Mode: {self.config.llm.mode.upper()})")
        print("  Press Right-Ctrl or Alt-Gr to talk to Lucca.")
        print("=" * 65)

    def _ensure_llama_server(self) -> None:
        if os.environ.get("LUCCA_TEST_FAKES") == "1":
            return
        if is_healthy(self.config.llm.host, self.config.llm.port, timeout=1.0):
            print("  ✓ llama-server is already active and healthy.")
            return

        try:
            h, p = self.config.llm.host, self.config.llm.port
            print(f"  Starting llama-server.exe on {h}:{p}...")
            self.llama_proc = start_server(self.config.llm, self.config.home_dir)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"WARNING: Could not launch llama-server: {exc}\n")
            return

        # Poll /health up to 60s with live progress indicator
        t0 = time.time()
        while time.time() - t0 < 60.0:
            if self.llama_proc is not None and self.llama_proc.poll() is not None:
                rc = self.llama_proc.returncode
                log_p = self.config.home_dir / "logs" / "llama-server.log"
                err_tail = ""
                if log_p.exists():
                    err_tail = log_p.read_text(encoding="utf-8", errors="replace")[-800:]
                sys.stderr.write(
                    f"\nFATAL: llama-server exited with code {rc}.\n"
                    f"Recent server log:\n{err_tail}\n"
                )
                sys.exit(5)

            status = check_server_status(self.config.llm.host, self.config.llm.port, timeout=1.0)
            elapsed = time.time() - t0
            if status == "ready":
                print(f"\n  ✓ llama-server ready on dGPU in {elapsed:.1f}s.")
                return
            if status == "loading":
                print(
                    f"\r  Loading 8GB model tensors into RTX 5080 VRAM... ({elapsed:.0f}s)",
                    end="",
                    flush=True,
                )
            else:
                print(
                    f"\r  Initializing CUDA Flash-Attention engine... ({elapsed:.0f}s)",
                    end="",
                    flush=True,
                )

            time.sleep(0.5)

        sys.stderr.write("\nFATAL: llama-server failed to respond on /health within 60s.\n")
        sys.exit(5)

    def run_forever(self) -> None:
        try:
            while self.running:
                if self.orchestrator and self.orchestrator.quit_requested:
                    sys.stderr.write("UI requested quit. Initiating shutdown...\n")
                    self.running = False
                    break

                now = time.monotonic()
                # Supervise child processes
                for name, p in list(self.children.items()):
                    if not p.is_alive():
                        if name == "ui" and p.exitcode == 0:
                            sys.stderr.write("UI closed by user (exit 0). Initiating shutdown...\n")
                            self.running = False
                            break

                        recent = [
                            t for t in self._restart_attempts.get(name, []) if now - t < 600.0
                        ]
                        self._restart_attempts[name] = recent
                        n = len(recent)

                        if n >= 5:
                            sys.stderr.write(f"DEGRADED: {name} failed 5x in 10 min\n")
                            if self.orchestrator:
                                self.orchestrator._set_state(
                                    "degraded", detail=f"{name}_crashed_5x"
                                )
                            self.children.pop(name, None)
                            self._next_restart.pop(name, None)
                        elif name not in self._next_restart:
                            delay = min(self.max_restart_backoff, (2.0**n) * self.backoff_base)
                            sys.stderr.write(
                                f"WARNING: Child process '{name}' exited with code {p.exitcode}. "
                                f"Restarting in {delay:.1f}s (attempt {n + 1}/5)...\n"
                            )
                            self._next_restart[name] = now + delay
                        elif now >= self._next_restart[name]:
                            del self._next_restart[name]
                            self._restart_attempts[name].append(now)
                            if name in self._targets:
                                self.children[name] = self._spawn_child(name)

                # Consult orchestrator dead peers from heartbeat
                if self.orchestrator:
                    for dead in self.orchestrator.dead_peers():
                        if dead in self.children and self.children[dead].is_alive():
                            sys.stderr.write(
                                f"WARNING: Peer '{dead}' missed 3 heartbeats. Terminating...\n"
                            )
                            self.children[dead].terminate()

                time.sleep(0.1)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        print("\nOrdered shutdown initiated...")
        self.running = False

        # (a) Publish ui.state offline, play.abort, and sys.shutdown
        if self.orchestrator:
            self.orchestrator.publish_offline()

        # (b) Allow children time to process shutdown and release audio/NPU resources
        time.sleep(0.5)

        # (c) Gracefully join children, then terminate/kill if stubborn
        for _name, p in self.children.items():
            if p.is_alive():
                p.join(timeout=3.0)
                if p.is_alive():
                    p.terminate()
                    p.join(timeout=1.0)
                    if p.is_alive():
                        p.kill()

        # (d) Stop orchestrator
        if self.orchestrator:
            self.orchestrator.stop()
            # (e) Unlink shared memory rings
            try:
                self.orchestrator.cap_ring.unlink()
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                self.orchestrator.play_ring.unlink()
            except Exception:  # noqa: BLE001, S110
                pass

        # (f) Terminate llama-server
        if self.llama_proc and self.llama_proc.poll() is None:
            self.llama_proc.terminate()
            try:
                self.llama_proc.wait(timeout=3.0)
            except (subprocess.TimeoutExpired, OSError):
                self.llama_proc.kill()

        print("Shutdown complete.")


def main() -> None:
    # Multiprocessing freeze support for PyInstaller Windows packaging
    mp.freeze_support()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ProjectLucca.DesktopCompanion.0.2"
        )
    except Exception:  # noqa: BLE001, S110
        pass

    # Set multiprocessing start method to spawn for Windows clean subprocesses
    mp.set_start_method("spawn", force=True)
    supervisor = Supervisor()

    def _on_signal(signum: int, frame: object) -> None:
        supervisor.running = False

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _on_signal)

    try:
        supervisor.boot()
        supervisor.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.shutdown()


if __name__ == "__main__":
    main()
