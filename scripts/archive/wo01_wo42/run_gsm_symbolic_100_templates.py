#!/usr/bin/env python3
"""Step 2a: Apple GSM-Symbolic 100-Template Stratified Evaluation (PAL in Docker).

Extracts exactly one instance per template (first instance of each distinct original_id)
from data/benchmarks/GSM_symbolic.jsonl.
Asserts 100 distinct templates before running.
Runs PAL mode in Docker via DockerRPCTransport with cache_prompt=False, temp=0.0, seed=42.
Saves report to logs/test_reports/gsm_symbolic_100_templates.json.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from lucca.reasoning.stats import wilson_score_interval
from lucca.sandbox.rpc import DockerRPCTransport
from scripts.run_modern_2024_benchmarks import (
    extract_gsm_ground_truth,
    extract_python_code,
    get_env_metadata,
    query_llm_with_meta,
)

DATA_FILE = REPO_ROOT / "data" / "benchmarks" / "GSM_symbolic.jsonl"
OUTPUT_FILE = REPO_ROOT / "logs" / "test_reports" / "gsm_symbolic_100_templates.json"


def load_stratified_dataset() -> list[dict]:
    """Load GSM_symbolic.jsonl and take first instance of each distinct original_id."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"GSM_symbolic.jsonl not found at {DATA_FILE}")

    seen_templates = set()
    stratified = []
    lines = DATA_FILE.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        item = json.loads(line)
        orig_id = item.get("original_id")
        if orig_id not in seen_templates:
            seen_templates.add(orig_id)
            stratified.append(item)

    # Strict assertion required by spec
    assert len(stratified) == 100, f"Expected exactly 100 templates, got {len(stratified)}"
    assert len(seen_templates) == 100, f"Expected 100 distinct original_ids, got {len(seen_templates)}"
    return stratified


import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="GSM-Symbolic 100-Template Stratified PAL Evaluation")
    parser.add_argument("--output-file", type=str, default=str(OUTPUT_FILE), help="Output JSON path")
    args = parser.parse_args()
    out_path = Path(args.output_file)

    dataset = load_stratified_dataset()
    print(f"Loaded {len(dataset)} stratified templates from {DATA_FILE}")

    prompt_template = (
        "You are a precise mathematical assistant. Solve the following word problem by writing "
        "a clean Python script that computes the answer and prints ONLY the final numeric value.\n"
        "Put all Python code inside a single ```python ... ``` block. Define all necessary variables.\n\n"
        "Problem: {q}\n"
    )

    req_params = {
        "temperature": 0.0,
        "seed": 42,
        "max_tokens": 1024,
        "cache_prompt": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    env_meta = get_env_metadata(prompt_template=prompt_template, request_params=req_params)

    print("Initializing DockerRPCTransport...")
    transport = DockerRPCTransport(container_name="lucca-file-sandbox")
    transport.ensure_container_running()

    print("\n=======================================================")
    print(f"Step 2a: GSM-Symbolic 100-Template Stratified PAL Evaluation")
    print(f"Commit: {env_meta.get('git_commit')} (dirty: {env_meta.get('git_dirty')})")
    print(f"Prompt Cache: DISABLED (cache_prompt=False)")
    print(f"=======================================================")

    results = []
    passed_count = 0
    t_start = time.perf_counter()

    for idx, item in enumerate(dataset, 1):
        q = item["question"]
        gt_raw = item["answer"]
        gt_val = extract_gsm_ground_truth(gt_raw)

        prompt = (
            "You are a precise mathematical assistant. Solve the following word problem by writing "
            "a clean Python script that computes the answer and prints ONLY the final numeric value.\n"
            "Put all Python code inside a single ```python ... ``` block. Define all necessary variables.\n\n"
            f"Problem: {q}\n"
        )

        t0 = time.perf_counter()
        resp, finish_reason, completion_tokens = query_llm_with_meta(
            prompt=prompt,
            max_tokens=1024,
            enable_thinking=False,
            cache_prompt=False,
        )
        t_llm = time.perf_counter() - t0

        code = extract_python_code(resp)
        exec_res = transport.execute(f"gsm-strat-{idx}", "run_python", {"code": code}, timeout_s=15)

        pred_val = None
        output_text = exec_res.content or ""
        if exec_res.exit_code == 0 and output_text:
            stdout_clean = output_text.strip().replace(",", "").replace("$", "")
            tokens = stdout_clean.split()
            if tokens:
                m = re.search(r"[-+]?\d*\.?\d+", tokens[-1])
                if m:
                    try:
                        pred_val = float(m.group(0))
                    except ValueError:
                        pass

        is_pass = False
        if gt_val is not None and pred_val is not None:
            is_pass = abs(gt_val - pred_val) < 1e-4

        if is_pass:
            passed_count += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"

        print(
            f"[{idx:03d}/100] {status_str} | ID: {item.get('id')} | OrigID: {item.get('original_id')} | "
            f"Pred: {pred_val} | Expected: {gt_val} | Latency: {t_llm:.2f}s",
            flush=True,
        )
        if not is_pass and code:
            snippet = code.replace("\n", " ")[:60]
            print(f"   Code snippet: {snippet}...", flush=True)

        results.append({
            "idx": idx,
            "id": item.get("id"),
            "instance": item.get("instance"),
            "original_id": item.get("original_id"),
            "question": q,
            "ground_truth_raw": gt_raw,
            "expected_val": gt_val,
            "pred_val": pred_val,
            "passed": is_pass,
            "generated_code": code,
            "stdout": exec_res.content,
            "stderr": exec_res.stderr,
            "exit_code": exec_res.exit_code,
            "llm_latency_s": round(t_llm, 3),
            "completion_tokens": completion_tokens,
            "finish_reason": finish_reason,
        })

    elapsed = time.perf_counter() - t_start
    total = len(dataset)
    failed_count = total - passed_count
    acc_pct = (passed_count / total) * 100.0 if total else 0.0
    ci_low, ci_high = wilson_score_interval(passed_count, total)

    report_payload = {
        "timestamp": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "benchmark": "GSM_Symbolic_100_Templates_Stratified",
        "method": "PAL (DockerRPCTransport)",
        "dataset_path": str(DATA_FILE),
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "accuracy_pct": round(acc_pct, 2),
        "wilson_95_ci": [round(ci_low * 100, 2), round(ci_high * 100, 2)],
        "elapsed_s": round(elapsed, 2),
        "git_commit": env_meta.get("git_commit"),
        "git_dirty": env_meta.get("git_dirty"),
        "server_command_line": env_meta.get("server_command_line"),
        "llama_server_build": env_meta.get("llama_server_build"),
        "llama_server_props": env_meta.get("llama_server_props"),
        "docker_image_digest": env_meta.get("docker_image_digest"),
        "prompt_template_sha256": env_meta.get("prompt_template_sha256"),
        "request_params": env_meta.get("request_params"),
        "results": results,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    print(f"\n[OK] Step 2a complete. Saved report to: {out_path}")
    print(f"Counts: n={total}, passed={passed_count}, failed={failed_count}, acc={acc_pct:.2f}%, CI=[{ci_low*100:.2f}%, {ci_high*100:.2f}%]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
