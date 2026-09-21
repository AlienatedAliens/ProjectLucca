"""
Brain Bake-Off — battery driver.

Runs the selected tests for one candidate, starting exactly one llama-server at a
time, writing everything under <out_dir>/<label>/ and a battery_summary.json.

Tests:
  persona        run_persona_refusal.py       (own server, 16k)
  context        run_context_sweep.py         (own servers, 16k..128k)
  probe          scripts/probe_brain_candidate.py  tool-routing smoke (server @16k)
  comprehensive  scripts/comprehensive_100_eval.py (server @16k, via LLMClient)
  confab         scripts/bench_confabulation_battery.py (server @16k, via LLMClient)

Usage:
    python scripts/brain_bakeoff/run_battery.py --candidate gemma4
    python scripts/brain_bakeoff/run_battery.py --candidate bonsai2 --tests persona context
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from bakeoff_common import (
    REPO_ROOT,
    Candidate,
    Defaults,
    ServerHandle,
    gpu_temp_c,
    load_registry,
    write_json,
)

HERE = Path(__file__).resolve().parent
PY = sys.executable
ALL_TESTS = ["persona", "context", "probe", "comprehensive", "confab"]
# Child processes may emit emoji/UTF-8 (e.g. model output); cmd.exe consoles are cp1252.
UTF8_ENV = {"PYTHONIOENCODING": "utf-8"}


def _run(cmd: list[str], env: dict[str, str], log_path: Path) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None  # noqa: S101
        for line in proc.stdout:
            safe = line.encode(sys.stdout.encoding or "ascii", errors="replace").decode(
                sys.stdout.encoding or "ascii"
            )
            sys.stdout.write(safe)
            log.write(line)
        rc = proc.wait()
    return rc, time.perf_counter() - t0


def _with_server(cand: Candidate, d: Defaults, out_dir: Path, name: str) -> ServerHandle:
    srv = ServerHandle(
        candidate=cand,
        defaults=d,
        ctx=d.ctx,
        kv_type=d.kv_type,
        log_path=out_dir / f"server_{name}.log",
    )
    if not srv.start_with_kv_fallback():
        raise RuntimeError(f"server failed to load for {name}: {srv.error_tail[-400:]}")
    print(
        f"[server] {cand.label} up in {srv.load_seconds:.1f}s  kv={srv.kv_type}"
        f"{' (fallback)' if srv.kv_fallback_applied else ''}  vram={srv.vram_after_load_mib} MiB"
    )
    return srv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--tests", nargs="+", default=ALL_TESTS, choices=ALL_TESTS)
    ap.add_argument("--ctx", type=int, nargs="+", default=[16384, 32768, 65536, 131072])
    args = ap.parse_args()

    d, cands = load_registry()
    cand = cands[args.candidate]
    out_dir = d.out_dir / cand.label
    out_dir.mkdir(parents=True, exist_ok=True)
    env = cand.runtime_env()
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + ";" + env.get("PYTHONPATH", "")

    summary: dict[str, object] = {
        "candidate": cand.label,
        "thinking": cand.thinking,
        "abliterated": cand.abliterated,
        "server_bin": str(cand.server_bin),
        "gguf": str(cand.gguf),
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gpu_temp_start_c": gpu_temp_c(),
        "tests": {},
    }
    tests: dict[str, object] = {}

    for t in args.tests:
        print("\n" + "=" * 78 + f"\n== {cand.label} :: {t}\n" + "=" * 78)
        try:
            if t == "persona":
                rc, secs = _run(
                    [PY, str(HERE / "run_persona_refusal.py"), "--candidate", cand.key],
                    env,
                    out_dir / "persona.log",
                )
                tests[t] = {
                    "rc": rc,
                    "seconds": round(secs, 1),
                    "artifact": str(out_dir / "persona_refusal.json"),
                }
            elif t == "context":
                rc, secs = _run(
                    [
                        PY,
                        str(HERE / "run_context_sweep.py"),
                        "--candidate",
                        cand.key,
                        "--ctx",
                        *map(str, args.ctx),
                    ],
                    env,
                    out_dir / "context.log",
                )
                tests[t] = {
                    "rc": rc,
                    "seconds": round(secs, 1),
                    "artifact": str(out_dir / "context_sweep" / "context_sweep.json"),
                }
            else:
                srv = _with_server(cand, d, out_dir, t)
                try:
                    if t == "probe":
                        cmd = [
                            PY,
                            str(REPO_ROOT / "scripts" / "probe_brain_candidate.py"),
                            "--name",
                            cand.label,
                            "--max-tokens",
                            "1024",
                            "--repeats",
                            "2",
                            "--out-dir",
                            str(out_dir),
                        ]
                        if cand.thinking == "off":
                            cmd.append("--no-think")
                        artifact = (
                            out_dir
                            / f"{cand.label}{'_nothink' if cand.thinking == 'off' else ''}_probe.json"
                        )
                    elif t == "comprehensive":
                        artifact = out_dir / "comprehensive_100.json"
                        cmd = [
                            PY,
                            str(REPO_ROOT / "scripts" / "comprehensive_100_eval.py"),
                            "--candidate",
                            cand.label,
                            "--out",
                            str(artifact),
                        ]
                    else:  # confab
                        artifact = out_dir / "confabulation_battery.json"
                        cmd = [
                            PY,
                            str(REPO_ROOT / "scripts" / "bench_confabulation_battery.py"),
                            "--candidate",
                            cand.label,
                            "--out",
                            str(artifact),
                        ]
                    rc, secs = _run(cmd, env, out_dir / f"{t}.log")
                    tests[t] = {
                        "rc": rc,
                        "seconds": round(secs, 1),
                        "artifact": str(artifact),
                        "server_vram_mib": srv.vram_after_load_mib,
                        "kv_type": srv.kv_type,
                    }
                finally:
                    srv.stop()
        except (RuntimeError, OSError) as e:
            tests[t] = {"rc": -1, "error": str(e)}
            print(f"[battery] {t} FAILED: {e}")

    summary["tests"] = tests
    summary["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    summary["gpu_temp_end_c"] = gpu_temp_c()
    write_json(out_dir / "battery_summary.json", summary)
    print("\nBATTERY SUMMARY:\n" + json.dumps(summary, indent=2))
    return 0 if all(isinstance(v, dict) and v.get("rc") == 0 for v in tests.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
