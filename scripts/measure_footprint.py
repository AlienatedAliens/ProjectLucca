#!/usr/bin/env python3
"""
Project Lucca — Whole-System Hardware Footprint Monitor
======================================================
Monitors and records live physical resource consumption across consumer hardware:
1. GPU VRAM & Power via nvidia-smi (NVIDIA GeForce RTX 5080 Laptop GPU)
2. Host System RAM via psutil
3. Process-level breakdown: llama-server, Python, WSL2 (vmmem)
4. Container memory limits and cgroup footprint

Can be used as:
- Standalone CLI: `python scripts/measure_footprint.py --duration 10`
- Python context manager / background monitor for benchmark runs:
    with FootprintMonitor(interval_s=1.0) as mon:
        run_benchmark()
    stats = mon.get_summary()
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

import psutil

# Windows UTF-8 stdout
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@dataclass
class GpuSnapshot:
    name: str
    total_mib: float
    used_mib: float
    free_mib: float
    temperature_c: float | None = None
    power_draw_w: float | None = None
    processes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RamSnapshot:
    total_mb: float
    used_mb: float
    available_mb: float
    percent: float
    vmmem_mb: float | None = None
    llama_server_mb: float | None = None
    python_mb: float | None = None


@dataclass
class SystemSnapshot:
    timestamp_utc: str
    gpu: GpuSnapshot | None
    ram: RamSnapshot


def sample_gpu() -> GpuSnapshot | None:
    """Samples NVIDIA GPU telemetry via nvidia-smi CLI."""
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)
        line = res.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        gpu_name = parts[0]
        tot_mib = float(parts[1])
        used_mib = float(parts[2])
        free_mib = float(parts[3])
        temp_c = float(parts[4]) if len(parts) > 4 and parts[4] != "[N/A]" else None
        pwr_w = float(parts[5]) if len(parts) > 5 and parts[5] != "[N/A]" else None

        # Sample compute processes
        cmd_p = [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
        res_p = subprocess.run(cmd_p, capture_output=True, text=True, timeout=5)
        procs: list[dict[str, Any]] = []
        if res_p.returncode == 0 and res_p.stdout.strip():
            for pline in res_p.stdout.strip().split("\n"):
                pparts = [p.strip() for p in pline.split(",")]
                if len(pparts) >= 3:
                    procs.append({
                        "pid": pparts[0],
                        "process_name": pparts[1],
                        "used_gpu_memory_mib": pparts[2],
                    })

        return GpuSnapshot(
            name=gpu_name,
            total_mib=tot_mib,
            used_mib=used_mib,
            free_mib=free_mib,
            temperature_c=temp_c,
            power_draw_w=pwr_w,
            processes=procs,
        )
    except Exception:
        return None


def sample_ram() -> RamSnapshot:
    """Samples host RAM and key processes via psutil."""
    vm = psutil.virtual_memory()
    total_mb = vm.total / (1024 * 1024)
    used_mb = vm.used / (1024 * 1024)
    avail_mb = vm.available / (1024 * 1024)
    pct = vm.percent

    vmmem_mb: float | None = None
    llama_mb: float | None = None
    python_mb: float = 0.0

    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            pname = (proc.info["name"] or "").lower()
            rss_mb = proc.info["memory_info"].rss / (1024 * 1024)
            if "vmmem" in pname:
                vmmem_mb = (vmmem_mb or 0.0) + rss_mb
            elif "llama-server" in pname:
                llama_mb = (llama_mb or 0.0) + rss_mb
            elif "python" in pname:
                python_mb += rss_mb
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return RamSnapshot(
        total_mb=round(total_mb, 1),
        used_mb=round(used_mb, 1),
        available_mb=round(avail_mb, 1),
        percent=pct,
        vmmem_mb=round(vmmem_mb, 1) if vmmem_mb is not None else None,
        llama_server_mb=round(llama_mb, 1) if llama_mb is not None else None,
        python_mb=round(python_mb, 1) if python_mb > 0 else None,
    )


def sample_system() -> SystemSnapshot:
    """Takes a full system snapshot (GPU + RAM)."""
    return SystemSnapshot(
        timestamp_utc=datetime.now(UTC).isoformat(),
        gpu=sample_gpu(),
        ram=sample_ram(),
    )


class FootprintMonitor:
    """
    Background thread that samples system footprint at fixed intervals.
    Provides summary statistics: peak VRAM, peak RAM, temperature delta.
    """

    def __init__(self, interval_s: float = 1.0) -> None:
        self.interval_s = interval_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.snapshots: list[SystemSnapshot] = []

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                snap = sample_system()
                self.snapshots.append(snap)
            except Exception:
                pass
            time.sleep(self.interval_s)

    def start(self) -> None:
        self.snapshots.clear()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def __enter__(self) -> FootprintMonitor:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

    def get_summary(self) -> dict[str, Any]:
        """Calculates min, max, peak VRAM/RAM metrics across all recorded snapshots."""
        if not self.snapshots:
            snap = sample_system()
            self.snapshots.append(snap)

        gpu_used = [s.gpu.used_mib for s in self.snapshots if s.gpu is not None]
        gpu_temps = [s.gpu.temperature_c for s in self.snapshots if s.gpu and s.gpu.temperature_c is not None]
        ram_used = [s.ram.used_mb for s in self.snapshots]
        vmmem = [s.ram.vmmem_mb for s in self.snapshots if s.ram.vmmem_mb is not None]
        llama_ram = [s.ram.llama_server_mb for s in self.snapshots if s.ram.llama_server_mb is not None]

        gpu_name = self.snapshots[0].gpu.name if self.snapshots[0].gpu else "Unknown GPU"
        gpu_total = self.snapshots[0].gpu.total_mib if self.snapshots[0].gpu else 0.0

        return {
            "gpu": {
                "name": gpu_name,
                "total_vram_mib": gpu_total,
                "peak_vram_used_mib": max(gpu_used) if gpu_used else 0.0,
                "min_vram_used_mib": min(gpu_used) if gpu_used else 0.0,
                "mean_vram_used_mib": round(sum(gpu_used) / len(gpu_used), 1) if gpu_used else 0.0,
                "peak_temperature_c": max(gpu_temps) if gpu_temps else None,
            },
            "ram": {
                "total_ram_mb": self.snapshots[0].ram.total_mb,
                "peak_ram_used_mb": max(ram_used) if ram_used else 0.0,
                "min_ram_used_mb": min(ram_used) if ram_used else 0.0,
                "peak_vmmem_wsl2_mb": max(vmmem) if vmmem else None,
                "peak_llama_server_ram_mb": max(llama_ram) if llama_ram else None,
            },
            "samples_count": len(self.snapshots),
            "duration_s": round(len(self.snapshots) * self.interval_s, 1),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lucca Hardware Footprint Monitor")
    parser.add_argument("--duration", type=int, default=0, help="Duration in seconds (0 = single snapshot)")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds")
    parser.add_argument("--output", type=str, default="", help="Optional JSON output path")
    args = parser.parse_args()

    if args.duration <= 0:
        snap = sample_system()
        print("=====================================================")
        print("=== PROJECT LUCCA: HARDWARE FOOTPRINT SNAPSHOT ===")
        print("=====================================================")
        print(f"Timestamp: {snap.timestamp_utc}")
        if snap.gpu:
            print(f"GPU Name:        {snap.gpu.name}")
            print(f"VRAM Used:       {snap.gpu.used_mib:.1f} MiB / {snap.gpu.total_mib:.1f} MiB ({snap.gpu.used_mib/snap.gpu.total_mib*100:.1f}%)")
            print(f"VRAM Free:       {snap.gpu.free_mib:.1f} MiB")
            if snap.gpu.temperature_c is not None:
                print(f"GPU Temp:        {snap.gpu.temperature_c:.0f} °C")
            if snap.gpu.power_draw_w is not None:
                print(f"Power Draw:      {snap.gpu.power_draw_w:.1f} W")
            if snap.gpu.processes:
                print("GPU Compute Processes:")
                for p in snap.gpu.processes:
                    print(f"  - PID {p['pid']}: {p['process_name']} ({p['used_gpu_memory_mib']} MiB)")
        print(f"\nHost RAM Used:   {snap.ram.used_mb:.1f} MB / {snap.ram.total_mb:.1f} MB ({snap.ram.percent:.1f}%)")
        if snap.ram.llama_server_mb is not None:
            print(f"llama-server:    {snap.ram.llama_server_mb:.1f} MB")
        if snap.ram.vmmem_mb is not None:
            print(f"WSL2 (vmmem):    {snap.ram.vmmem_mb:.1f} MB")
        if snap.ram.python_mb is not None:
            print(f"Python:          {snap.ram.python_mb:.1f} MB")

        if args.output:
            Path(args.output).write_text(json.dumps(asdict(snap), indent=2), encoding="utf-8")
            print(f"\n[Snapshot Saved] -> {args.output}")
    else:
        print(f"Monitoring system footprint for {args.duration}s (interval: {args.interval}s)...")
        with FootprintMonitor(interval_s=args.interval) as mon:
            time.sleep(args.duration)
        summary = mon.get_summary()
        print(json.dumps(summary, indent=2))
        if args.output:
            Path(args.output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(f"[Summary Saved] -> {args.output}")


if __name__ == "__main__":
    main()
