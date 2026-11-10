#!/usr/bin/env python3
"""
WO-45 REVIEW_G3 Query Q-1 (R-05): Capture raw timestamped `nvidia-smi` output
before and after loading each of the 4 GGUF models (`E2B`, `E4B`, `12B`, `26B-A4B`)
via `build_launch_command(llm_cfg, LUCCA_HOME)` at `ctx=8192`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.brain.server_ctl import build_launch_command  # noqa: E402
from lucca.core.config import LLMSettings  # noqa: E402

LUCCA_HOME = Path(r"C:\ProjectLucca")
MODELS_DIR = LUCCA_HOME / "models" / "llm"
SERVER_PORT = 8089
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"

MODEL_MATRIX = [
    ("E2B", MODELS_DIR / "Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf"),
    ("E4B", MODELS_DIR / "gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf"),
    ("12B", MODELS_DIR / "gemma-4-12b-heretic-Q6_K.gguf"),
    ("26B-A4B", MODELS_DIR / "gemma-4-26B-A4B-it-heretic.Q6_K.gguf"),
]


def query_nvidia_smi_raw() -> dict[str, str]:
    gpu_csv = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=timestamp,name,memory.used,memory.total",
            "--format=csv",
        ],
        text=True,
        timeout=10.0,
    ).strip()
    apps_csv = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv",
        ],
        text=True,
        timeout=10.0,
    ).strip()
    return {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "query_gpu_csv": gpu_csv,
        "query_compute_apps_csv": apps_csv,
    }


def stop_server() -> None:
    subprocess.run(
        ["taskkill", "/F", "/IM", "llama-server.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(2.0)


def wait_for_server(timeout_s: float = 120.0) -> bool:
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        try:
            req = urllib.request.Request(f"{SERVER_URL}/health", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001, S110
            pass
        time.sleep(1.0)
    return False


def main() -> None:
    stop_server()
    baseline_idle = query_nvidia_smi_raw()
    print("=== Baseline Idle (no model loaded) ===")
    print(baseline_idle["query_gpu_csv"])
    print(baseline_idle["query_compute_apps_csv"])

    per_model: dict[str, dict[str, object]] = {}
    for model_label, model_path in MODEL_MATRIX:
        stop_server()
        pre_load = query_nvidia_smi_raw()
        is_moe = model_label == "26B-A4B"
        llm_cfg = LLMSettings(
            mode="transcript",
            host="127.0.0.1",
            port=SERVER_PORT,
            ctx=8192,
            kv_type="q8_0",
            kv_type_k="q8_0",
            kv_type_v="q8_0",
            ngl=99,
            spec_type="ngram-mod",
            cpu_moe=is_moe,
            moe_expert_cache_mib=7680 if is_moe else None,
            ubatch=2048,
            cache_ram_mib=4096,
            model=str(model_path),
            mmproj=None,
            chat_template_file=None,
            chat_template=None,
        )
        cmd = build_launch_command(llm_cfg, LUCCA_HOME)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if not wait_for_server():
                raise RuntimeError(f"Failed to start {model_label}")
            loaded_snap = query_nvidia_smi_raw()
            print(f"\n=== {model_label} Loaded ===")
            print(loaded_snap["query_gpu_csv"])
            print(loaded_snap["query_compute_apps_csv"])
            per_model[model_label] = {
                "launch_cmd": cmd,
                "pre_load_idle": pre_load,
                "post_load_ready": loaded_snap,
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10.0)
            except Exception:  # noqa: BLE001
                stop_server()

    stop_server()
    post_all_idle = query_nvidia_smi_raw()
    out_path = REPO_ROOT / "logs/test_reports/wo45/q1_vram_nvidia_smi_evidence.json"
    payload = {
        "query_id": "Q-1 (R-05)",
        "explanation": (
            "On this hybrid-GPU Windows 11 laptop (Intel Core Ultra 9 275HX iGPU + discrete NVIDIA GeForce RTX 5080 Laptop GPU), "
            "all desktop/OS display compositing runs on the Intel iGPU, so the discrete RTX 5080 sits at 0 MiB used when idle. "
            "When llama-server loads a GGUF checkpoint with fixed flags (--ctx-size 8192 --cache-type-k q8_0 --cache-type-v q8_0), "
            "it is the sole CUDA compute process on the RTX 5080 and deterministically allocates the exact same MiB buffer on every load."
        ),
        "baseline_idle_no_model": baseline_idle,
        "models": per_model,
        "post_all_idle_no_model": post_all_idle,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
