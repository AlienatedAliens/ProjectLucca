"""Machine-logged Judge 3 runner for NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL (`NVIDIA-Nemotron` family).

Preserves `scripts/wo45/run_wo45_v3_judge.py` 100% byte-for-byte intact (as hashed in
`live_v3_prereg_lock.json`) by importing `evaluate_item`, `extract_rubric_sections`, `query_llama_build`,
`sha256_file`, `stop_servers`, and `wait_for_server` directly from `scripts.wo45.run_wo45_v3_judge`,
and launching `llama-server.exe` (`build 11868`, native `nemotron_h_moe`) with `--n-cpu-moe` so the
17.62 GiB GGUF fits cleanly inside 16 GB RTX 5080 VRAM + DDR5 host RAM at `T=0.0, seed=42`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.wo45.run_wo45_v3_judge import (  # noqa: E402
    DEFAULT_RUBRIC_PATH,
    LLAMA_EXE,
    LUCCA_HOME,
    evaluate_item,
    extract_rubric_sections,
    query_llama_build,
    sha256_file,
    stop_servers,
    wait_for_server,
)

NEMOTRON_PROFILE: dict[str, str] = {
    "backend": "llama_server",
    "judge_model": "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL",
    "judge_family": "NVIDIA-Nemotron",
    "model_path": str(
        LUCCA_HOME / "models" / "llm" / "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-IQ4_NL.gguf"
    ),
}


def start_nemotron_llama_server(
    model_path: Path, port: int, workers: int, n_cpu_moe: int
) -> tuple[subprocess.Popen[bytes], str]:
    stop_servers()
    server_build = query_llama_build()
    cmd = [
        str(LLAMA_EXE),
        "--model",
        str(model_path),
        "--port",
        str(port),
        "--n-gpu-layers",
        "99",
        "--n-cpu-moe",
        str(n_cpu_moe),
        "--ctx-size",
        "8192",
        "--parallel",
        str(max(1, workers)),
        "--no-webui",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, f"{server_build} | n_cpu_moe={n_cpu_moe}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["qualification", "pool", "arm_guess"], default="pool"
    )
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--rubric-path", type=Path, default=DEFAULT_RUBRIC_PATH)
    parser.add_argument("--port", type=int, default=18097)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--shard-size", type=int, default=200)
    parser.add_argument("--n-cpu-moe", type=int, default=12)
    args = parser.parse_args()

    prof = NEMOTRON_PROFILE
    model_path = Path(prof["model_path"])
    if not model_path.exists():
        raise FileNotFoundError(f"Missing Nemotron GGUF model path: {model_path}")

    sections = extract_rubric_sections(args.rubric_path.read_text(encoding="utf-8"))
    all_items = [
        json.loads(ln)
        for ln in args.input_jsonl.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]

    model_sha = sha256_file(model_path)
    print(
        f"[Judge v3 {prof['judge_model']}] mode={args.mode} items={len(all_items)} "
        f"shard_size={args.shard_size} workers={args.workers} n_cpu_moe={args.n_cpu_moe}",
        flush=True,
    )
    proc, server_build = start_nemotron_llama_server(
        model_path, args.port, args.workers, args.n_cpu_moe
    )
    try:
        if not wait_for_server(args.port, timeout_s=240.0):
            raise RuntimeError(f"Nemotron llama-server failed to become ready on port {args.port}")

        results_by_id: dict[str, dict[str, Any]] = {}
        shard_size = max(1, args.shard_size)
        total_shards = (len(all_items) + shard_size - 1) // shard_size

        for s_idx in range(total_shards):
            shard_items = all_items[s_idx * shard_size : (s_idx + 1) * shard_size]
            failed_for_retry: list[tuple[dict[str, Any], str]] = []

            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
                futs = {
                    pool.submit(
                        evaluate_item,
                        args.port,
                        prof["backend"],
                        prof,
                        model_sha,
                        server_build,
                        sections,
                        it,
                        args.mode,
                    ): it
                    for it in shard_items
                }
                for fut in as_completed(futs):
                    it = futs[fut]
                    try:
                        row = fut.result()
                        results_by_id[str(row["blind_id"])] = row
                    except Exception as exc:  # noqa: BLE001
                        failed_for_retry.append((it, str(exc)))

            # Identical RM-5 locked single-worker truncation/parse retry rule with explicit retry_log
            for it, first_err in failed_for_retry:
                retry_events: list[dict[str, Any]] = [
                    {
                        "attempt": 1,
                        "workers": args.workers,
                        "error": first_err,
                        "timestamp_utc": datetime.now(UTC).isoformat(),
                    }
                ]
                recovered: dict[str, Any] | None = None
                for retry_num in (2, 3):
                    time.sleep(1.0)
                    try:
                        row = evaluate_item(
                            args.port,
                            prof["backend"],
                            prof,
                            model_sha,
                            server_build,
                            sections,
                            it,
                            args.mode,
                            max_tokens=640,
                        )
                        retry_events.append(
                            {
                                "attempt": retry_num,
                                "workers": 1,
                                "max_tokens": 640,
                                "status": "ok",
                                "timestamp_utc": datetime.now(UTC).isoformat(),
                            }
                        )
                        row["retried"] = True
                        row["retry_log"] = retry_events
                        recovered = row
                        break
                    except Exception as retry_exc:  # noqa: BLE001
                        retry_events.append(
                            {
                                "attempt": retry_num,
                                "workers": 1,
                                "max_tokens": 640,
                                "error": str(retry_exc),
                                "timestamp_utc": datetime.now(UTC).isoformat(),
                            }
                        )
                if recovered is None:
                    raise RuntimeError(
                        f"Item {it['blind_id']} failed after locked single-worker retries: {retry_events}"
                    )
                results_by_id[str(recovered["blind_id"])] = recovered

            print(
                f"  [{prof['judge_model']}] shard {s_idx + 1}/{total_shards} complete "
                f"({len(results_by_id)}/{len(all_items)} total, retries={len(failed_for_retry)})",
                flush=True,
            )

        ordered_rows = [results_by_id[str(it["blind_id"])] for it in all_items]
        args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        args.output_jsonl.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in ordered_rows) + "\n",
            encoding="utf-8",
        )
        print(
            f"[Judge v3 {prof['judge_model']}] Saved {len(ordered_rows)} rows -> {args.output_jsonl}",
            flush=True,
        )
    finally:
        proc.terminate()
        stop_servers()


if __name__ == "__main__":
    main()
