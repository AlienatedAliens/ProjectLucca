"""
Project Lucca — Visual Pipeline Debugger & Telemetry HTTP Server
Spec 01 §1, Spec 10 §1-§3, ADR-005

Serves the visual debugger UI and real-time streaming REST API for live pipeline monitoring and trace replay:
- GET /                    -> Visual Pipeline Debugger UI (HTML/JS/CSS)
- GET /api/live            -> Current pipeline state (what is happening RIGHT NOW)
- GET /api/traces          -> Array of trace summaries for filtering and triage
- GET /api/trace/<id>      -> Full forensic trace record for a specific flow
- GET /api/hardware        -> Real-time silicon telemetry (RTX 5080 Laptop GPU, CPU, NPU)
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
TELEMETRY_DIR = REPO_ROOT / "logs" / "telemetry"
UI_DIR = REPO_ROOT / "ui" / "pipeline_debugger"
TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
UI_DIR.mkdir(parents=True, exist_ok=True)

LIVE_STATE_FILE = TELEMETRY_DIR / "live_pipeline_state.json"
FLOW_TRACES_FILE = TELEMETRY_DIR / "flow_traces.jsonl"


def get_hardware_telemetry() -> dict:
    """Sample live hardware telemetry directly from nvidia-smi."""
    telemetry = {
        "timestamp": time.time(),
        "gpu": {
            "name": "NVIDIA GeForce RTX 5080 Laptop GPU",
            "vram_used_mib": 0.0,
            "vram_total_mib": 16303.0,
            "vram_used_gib": 0.0,
            "vram_total_gib": 15.92,
            "power_draw_w": 0.0,
            "power_limit_w": 175.0,
            "temperature_c": 0,
            "util_pct": 0,
        },
        "cpu": {"model": "Intel Core Ultra 9 275HX", "cores": 24},
        "npu": {"model": "Intel AI Boost NPU", "status": "ACTIVE_STANDBY"},
    }
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,power.draw,temperature.gpu,utilization.gpu", "--format=csv,nounits,noheader"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 5:
                used_mib = float(parts[0])
                total_mib = float(parts[1])
                telemetry["gpu"]["vram_used_mib"] = used_mib
                telemetry["gpu"]["vram_total_mib"] = total_mib
                telemetry["gpu"]["vram_used_gib"] = round(used_mib / 1024.0, 2)
                telemetry["gpu"]["vram_total_gib"] = round(total_mib / 1024.0, 2)
                telemetry["gpu"]["power_draw_w"] = float(parts[2])
                telemetry["gpu"]["temperature_c"] = int(float(parts[3]))
                telemetry["gpu"]["util_pct"] = int(float(parts[4]))
    except Exception:
        pass
    return telemetry


class DebuggerHTTPHandler(BaseHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            ui_html_file = UI_DIR / "index.html"
            if not ui_html_file.exists():
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Debugger UI HTML file not found.")
                return
            content = ui_html_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/live":
            state = {}
            if LIVE_STATE_FILE.exists():
                try:
                    state = json.loads(LIVE_STATE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    state = {"active": False, "details": "Parsing state..."}
            else:
                state = {"active": False, "details": "No active flow recorded."}
            body = json.dumps(state).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/hardware":
            hw = get_hardware_telemetry()
            body = json.dumps(hw).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/traces":
            traces = []
            if FLOW_TRACES_FILE.exists():
                try:
                    with open(FLOW_TRACES_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                t = json.loads(line)
                                task = t.get("task_info", {})
                                verdict = t.get("verdict", {})
                                err = ""
                                for tank in t.get("tanks", []):
                                    if tank.get("stderr"):
                                        err = tank.get("stderr")[:120]
                                        break
                                traces.append({
                                    "trace_id": t.get("trace_id"),
                                    "index": task.get("index", 0),
                                    "subject": task.get("subject", ""),
                                    "level": task.get("level", 0),
                                    "passed": t.get("passed", False),
                                    "strict_pass": verdict.get("strict_pass", t.get("passed", False)),
                                    "lenient_pass": verdict.get("lenient_pass", t.get("passed", False)),
                                    "failure_class": verdict.get("failure_class", ""),
                                    "reconstructed": t.get("reconstructed", False),
                                    "tags": t.get("tags", []),
                                    "predicted": str(t.get("predicted_ans", ""))[:40],
                                    "expected": str(t.get("expected_ans", ""))[:40],
                                    "total_latency_s": t.get("total_latency_s", 0.0),
                                    "timestamp": t.get("timestamp", ""),
                                    "error_preview": err,
                                })
                            except Exception:
                                continue
                except Exception as exc:
                    traces = []
            body = json.dumps(traces).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path.startswith("/api/trace/"):
            target_id = path.split("/api/trace/")[-1].strip()
            found_trace = None
            if FLOW_TRACES_FILE.exists():
                try:
                    with open(FLOW_TRACES_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                t = json.loads(line)
                                if t.get("trace_id") == target_id or str(t.get("task_info", {}).get("index")) == target_id:
                                    found_trace = t
                                    break
                            except Exception:
                                continue
                except Exception:
                    pass
            if found_trace:
                body = json.dumps(found_trace).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error": "Trace not found"}')
            return

        # Static assets
        static_file = UI_DIR / path.lstrip("/")
        if static_file.exists() and static_file.is_file():
            mime_type, _ = mimetypes.guess_type(str(static_file))
            content = static_file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def log_message(self, format: str, *args: any) -> None:
        # Suppress noisy HTTP request logging
        pass


def run_server(port: int = 8765) -> None:
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, DebuggerHTTPHandler)
    print(f"\n=======================================================")
    print(f"Project Lucca — Visual Pipeline Debugger Server")
    print(f"UI available at: http://127.0.0.1:{port}")
    print(f"Live telemetry:  http://127.0.0.1:{port}/api/live")
    print(f"Flow traces API: http://127.0.0.1:{port}/api/traces")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping debugger server...")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve Project Lucca Visual Debugger")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve debugger on")
    args = parser.parse_args()
    run_server(port=args.port)
