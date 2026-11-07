"""
Project Lucca — V10 Master Verification Pipeline
Executes the next horizon of Order of Work (v10):
1. Verifies llama-server health with canonical settings
2. Runs the fresh Sealed Parametric Reasoning Benchmark (N=25, 5 per suite)
3. Evaluates Direct, Extended Thinking, and Compound arms on unseen programmatic items
4. Logs exact discordant pairs, McNemar two-sided p-values, and per-suite accuracy
"""

from __future__ import annotations

import os
import runpy
import sys
import time
import traceback
from pathlib import Path

import httpx

ROOT = Path("C:/Projects/ProjectLucca")
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)
os.environ["PYTHONIOENCODING"] = "utf-8"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def wait_for_llm_server(timeout_s: float = 60.0) -> bool:
    print("[HEALTH] Checking llama-server at http://127.0.0.1:8080/health ...", flush=True)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get("http://127.0.0.1:8080/health", timeout=3.0)
            if r.status_code == 200:
                print(f"[HEALTH] llama-server READY: {r.text.strip()}", flush=True)
                return True
        except Exception:
            pass
        time.sleep(1.5)
    print("[HEALTH] ERROR: llama-server did not become healthy within timeout.", flush=True)
    return False


def run_script_inprocess(label: str, script_rel: str, argv_args: list[str]) -> bool:
    print(f"\n{'=' * 78}", flush=True)
    print(f"[START] {label}: {script_rel} {' '.join(argv_args)}", flush=True)
    print(f"{'=' * 78}", flush=True)
    t0 = time.perf_counter()
    old_argv = sys.argv[:]
    script_path = str(ROOT / script_rel) if not Path(script_rel).is_absolute() else script_rel
    sys.argv = [script_path, *argv_args]
    ok = True
    try:
        runpy.run_path(script_path, run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(f"[WARN] {label} exited with code {exc.code}", flush=True)
            ok = False
    except Exception:
        print(f"[ERROR] Exception in {label}:", flush=True)
        traceback.print_exc()
        ok = False
    finally:
        sys.argv = old_argv
    elapsed = time.perf_counter() - t0
    print(f"[DONE]  {label} finished in {elapsed:.1f}s (ok={ok})", flush=True)
    return ok


def main() -> int:
    if not wait_for_llm_server(timeout_s=60.0):
        return 1

    # 1. Run the fresh Sealed Parametric Suite (5 per suite = 25 unseen programmatic tasks)
    ok_sealed = run_script_inprocess(
        "Sealed Parametric Reasoning Benchmark (N=25)",
        "scripts/run_sealed_parametric_suite.py",
        ["--limit-per-suite", "5", "--model-tag", "12B_V138"],
    )

    print("\n" + "=" * 78)
    print("V10 PIPELINE EXECUTION COMPLETE")
    print(f"Sealed Parametric Benchmark: {'PASS' if ok_sealed else 'CHECK LOG'}")
    print("=" * 78)
    return 0 if ok_sealed else 1


if __name__ == "__main__":
    raise SystemExit(main())
