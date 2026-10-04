#!/usr/bin/env python3
"""Step 2b: HumanEval Canonical 164 Tasks — Paired Evaluation (Raw vs Assisted).

Evaluates 164 canonical HumanEval tasks using a paired design:
1. Turn 1 generation runs once under cache_prompt=False, temp=0.0, seed=42.
2. Arm A (Raw): Preflight rescue OFF. The generated Turn 1 code is evaluated directly
   against the canonical test suite (check(entry_point)).
3. Arm B (Assisted): Preflight rescue ON. If docstring assertions fail in preflight,
   the model is re-prompted 1-shot with the execution assertion error, and the repaired
   code is evaluated against the canonical test suite.

Outputs:
- logs/test_reports/humaneval_canonical_raw_164.json
- logs/test_reports/humaneval_canonical_assisted_164.json
"""

from __future__ import annotations

import json
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
from lucca.sandbox.service import SandboxService
from scripts.run_modern_2024_benchmarks import (
    extract_python_code,
    get_env_metadata,
    query_llm_with_meta,
)

DATA_FILE = REPO_ROOT / "data" / "benchmarks" / "humaneval.jsonl"
RAW_OUTPUT_FILE = REPO_ROOT / "logs" / "test_reports" / "humaneval_canonical_raw_164.json"
ASSISTED_OUTPUT_FILE = REPO_ROOT / "logs" / "test_reports" / "humaneval_canonical_assisted_164.json"


def load_humaneval_dataset() -> list[dict]:
    """Load canonical HumanEval dataset."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"humaneval.jsonl not found at {DATA_FILE}")

    lines = DATA_FILE.read_text(encoding="utf-8").splitlines()
    data = [json.loads(line) for line in lines if line.strip()]
    assert len(data) == 164, f"Expected 164 tasks, got {len(data)}"
    return data


import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="HumanEval Canonical 164 Paired Evaluation")
    parser.add_argument("--label", type=str, default="", help="Optional label suffix for output files")
    args = parser.parse_args()

    raw_out = (
        REPO_ROOT / "logs" / "test_reports" / f"humaneval_canonical_raw_164_{args.label}.json"
        if args.label
        else RAW_OUTPUT_FILE
    )
    asst_out = (
        REPO_ROOT / "logs" / "test_reports" / f"humaneval_canonical_assisted_164_{args.label}.json"
        if args.label
        else ASSISTED_OUTPUT_FILE
    )

    dataset = load_humaneval_dataset()
    print(f"Loaded {len(dataset)} canonical HumanEval tasks from {DATA_FILE}")

    prompt_template = (
        "Complete the following Python function. Provide only the valid Python implementation.\n"
        "Do not include explanation text; put the completed code inside a ```python ... ``` block.\n\n"
        "{prompt}"
    )

    req_params = {
        "temperature": 0.0,
        "seed": 42,
        "max_tokens": 1024,
        "cache_prompt": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    env_meta = get_env_metadata(prompt_template=prompt_template, request_params=req_params)

    print("Initializing DockerRPCTransport and SandboxService...")
    transport = DockerRPCTransport(container_name="lucca-file-sandbox")
    transport.ensure_container_running()
    sandbox_service = SandboxService(use_direct_fallback=False)

    print("\n=======================================================")
    print("Step 2b: HumanEval Canonical 164 Tasks (Paired Design)")
    print(f"Commit: {env_meta.get('git_commit')} (dirty: {env_meta.get('git_dirty')})")
    print(f"Prompt Cache: DISABLED (cache_prompt=False)")
    print("Arm A: Preflight Rescue OFF (Raw)")
    print("Arm B: Preflight Rescue ON (1-Shot Docstring Correction)")
    print("=======================================================\n")

    raw_results = []
    assisted_results = []
    task_comparisons = []

    raw_passed_count = 0
    assisted_passed_count = 0
    preflight_triggered_count = 0
    preflight_rescued_count = 0

    t_start = time.perf_counter()

    for idx, item in enumerate(dataset, 1):
        task_id = item["task_id"]
        prompt = item["prompt"]
        entry_point = item["entry_point"]
        test_code = item["test"]

        instruction = (
            "Complete the following Python function. Provide only the valid Python implementation.\n"
            "Do not include explanation text; put the completed code inside a ```python ... ``` block.\n\n"
            f"{prompt}"
        )

        # 1. Turn 1 Generation (generated once for both arms)
        t0 = time.perf_counter()
        resp, finish_reason, completion_tokens = query_llm_with_meta(
            prompt=instruction,
            max_tokens=1024,
            enable_thinking=False,
            cache_prompt=False,
        )
        t_t1 = time.perf_counter() - t0

        code_t1 = extract_python_code(resp)
        if prompt.strip() in code_t1:
            candidate_raw = code_t1
        else:
            candidate_raw = f"{prompt}\n{code_t1}"

        # 2. Arm A: Evaluate Raw against canonical test suite
        full_code_raw = f"{candidate_raw}\n\n{test_code}\n\ncheck({entry_point})\n"
        exec_raw = transport.execute(f"he-raw-{idx}", "run_python", {"code": full_code_raw}, timeout_s=15)
        raw_pass = (exec_raw.exit_code == 0)
        if raw_pass:
            raw_passed_count += 1

        # 3. Arm B: Preflight verification & optional 1-shot repair
        candidate_assisted = candidate_raw
        preflight_triggered = False
        t_repair = 0.0
        repair_resp = ""
        repair_tokens = 0
        preflight_err = None

        try:
            preflight_res = sandbox_service.preflight_verify_code(candidate_raw)
            if not preflight_res.success and preflight_res.error_msg and preflight_res.assertions_run > 0:
                preflight_triggered = True
                preflight_triggered_count += 1
                preflight_err = preflight_res.error_msg
                corr_prompt = (
                    f"The following implementation for `{entry_point}` was tested in the execution sandbox "
                    f"and failed specification docstring assertions:\n\n"
                    f"```python\n{candidate_raw}\n```\n\n"
                    f"Execution Error / Assertion Failure:\n{preflight_res.error_msg}\n\n"
                    f"Please fix the implementation so that it passes all specification assertions. "
                    f"Provide ONLY the completed code in a ```python ... ``` block."
                )
                t_r0 = time.perf_counter()
                repair_resp, _, repair_tokens = query_llm_with_meta(
                    prompt=corr_prompt,
                    max_tokens=1024,
                    enable_thinking=False,
                    cache_prompt=False,
                )
                t_repair = time.perf_counter() - t_r0
                corr_code = extract_python_code(repair_resp)
                if corr_code:
                    if prompt.strip() in corr_code:
                        candidate_assisted = corr_code
                    else:
                        candidate_assisted = f"{prompt}\n{corr_code}"
        except Exception as pf_exc:
            print(f"   [Preflight Warn] Task {task_id}: {pf_exc}")

        # 4. Arm B: Evaluate Assisted against canonical test suite
        full_code_assisted = f"{candidate_assisted}\n\n{test_code}\n\ncheck({entry_point})\n"
        exec_assisted = transport.execute(f"he-asst-{idx}", "run_python", {"code": full_code_assisted}, timeout_s=15)
        assisted_pass = (exec_assisted.exit_code == 0)
        if assisted_pass:
            assisted_passed_count += 1

        if not raw_pass and assisted_pass:
            preflight_rescued_count += 1

        # Determine task category
        if raw_pass and assisted_pass:
            status_tag = "BOTH_PASS"
        elif not raw_pass and assisted_pass:
            status_tag = "RESCUED (Raw FAIL -> Asst PASS)"
        elif raw_pass and not assisted_pass:
            status_tag = "REGRESSED (Raw PASS -> Asst FAIL)"
        else:
            status_tag = "BOTH_FAIL"

        pf_tag = f" [Preflight Triggered]" if preflight_triggered else ""
        print(
            f"[{idx:03d}/164] {task_id:15s} | Raw: {'PASS' if raw_pass else 'FAIL'} | "
            f"Asst: {'PASS' if assisted_pass else 'FAIL'} | Status: {status_tag}{pf_tag}",
            flush=True,
        )

        raw_results.append({
            "idx": idx,
            "task_id": task_id,
            "entry_point": entry_point,
            "passed": raw_pass,
            "candidate_code": candidate_raw,
            "exit_code": exec_raw.exit_code,
            "stdout": exec_raw.content,
            "stderr": exec_raw.stderr,
            "llm_latency_s": round(t_t1, 3),
            "completion_tokens": completion_tokens,
            "finish_reason": finish_reason,
        })

        assisted_results.append({
            "idx": idx,
            "task_id": task_id,
            "entry_point": entry_point,
            "passed": assisted_pass,
            "candidate_code": candidate_assisted,
            "exit_code": exec_assisted.exit_code,
            "stdout": exec_assisted.content,
            "stderr": exec_assisted.stderr,
            "llm_latency_s": round(t_t1 + t_repair, 3),
            "t1_latency_s": round(t_t1, 3),
            "repair_latency_s": round(t_repair, 3),
            "preflight_triggered": preflight_triggered,
            "preflight_error": preflight_err,
            "t1_tokens": completion_tokens,
            "repair_tokens": repair_tokens,
        })

        task_comparisons.append({
            "idx": idx,
            "task_id": task_id,
            "entry_point": entry_point,
            "raw_passed": raw_pass,
            "assisted_passed": assisted_pass,
            "status": status_tag,
            "preflight_triggered": preflight_triggered,
        })

    elapsed = time.perf_counter() - t_start
    total = len(dataset)

    # Wilson CIs
    raw_ci_low, raw_ci_high = wilson_score_interval(raw_passed_count, total)
    asst_ci_low, asst_ci_high = wilson_score_interval(assisted_passed_count, total)

    raw_report = {
        "timestamp": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "benchmark": "HumanEval_Canonical_Raw_164",
        "arm": "raw (preflight rescue OFF)",
        "dataset_path": str(DATA_FILE),
        "total": total,
        "passed": raw_passed_count,
        "failed": total - raw_passed_count,
        "pass_at_1_pct": round((raw_passed_count / total) * 100.0, 2),
        "wilson_95_ci": [round(raw_ci_low * 100, 2), round(raw_ci_high * 100, 2)],
        "elapsed_s": round(elapsed, 2),
        "git_commit": env_meta.get("git_commit"),
        "git_dirty": env_meta.get("git_dirty"),
        "server_command_line": env_meta.get("server_command_line"),
        "llama_server_build": env_meta.get("llama_server_build"),
        "llama_server_props": env_meta.get("llama_server_props"),
        "docker_image_digest": env_meta.get("docker_image_digest"),
        "prompt_template_sha256": env_meta.get("prompt_template_sha256"),
        "request_params": env_meta.get("request_params"),
        "paired_comparison": {
            "both_pass": sum(1 for c in task_comparisons if c["raw_passed"] and c["assisted_passed"]),
            "both_fail": sum(1 for c in task_comparisons if not c["raw_passed"] and not c["assisted_passed"]),
            "raw_only_pass": sum(1 for c in task_comparisons if c["raw_passed"] and not c["assisted_passed"]),
            "assisted_only_pass": sum(1 for c in task_comparisons if not c["raw_passed"] and c["assisted_passed"]),
            "preflight_triggered": preflight_triggered_count,
            "preflight_rescued": preflight_rescued_count,
        },
        "results": raw_results,
    }

    assisted_report = {
        "timestamp": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "benchmark": "HumanEval_Canonical_Assisted_164",
        "arm": "assisted (preflight rescue ON)",
        "dataset_path": str(DATA_FILE),
        "total": total,
        "passed": assisted_passed_count,
        "failed": total - assisted_passed_count,
        "pass_at_1_pct": round((assisted_passed_count / total) * 100.0, 2),
        "wilson_95_ci": [round(asst_ci_low * 100, 2), round(asst_ci_high * 100, 2)],
        "elapsed_s": round(elapsed, 2),
        "git_commit": env_meta.get("git_commit"),
        "git_dirty": env_meta.get("git_dirty"),
        "server_command_line": env_meta.get("server_command_line"),
        "llama_server_build": env_meta.get("llama_server_build"),
        "llama_server_props": env_meta.get("llama_server_props"),
        "docker_image_digest": env_meta.get("docker_image_digest"),
        "prompt_template_sha256": env_meta.get("prompt_template_sha256"),
        "request_params": env_meta.get("request_params"),
        "paired_comparison": raw_report["paired_comparison"],
        "results": assisted_results,
    }

    raw_out.parent.mkdir(parents=True, exist_ok=True)
    raw_out.write_text(json.dumps(raw_report, indent=2), encoding="utf-8")
    asst_out.write_text(json.dumps(assisted_report, indent=2), encoding="utf-8")

    print("\n=======================================================")
    print("Step 2b Paired Evaluation Summary")
    print(f"Total Tasks: {total}")
    print(f"Raw Pass@1:      {raw_passed_count}/{total} ({raw_passed_count/total*100:.2f}%) | CI: [{raw_ci_low*100:.2f}%, {raw_ci_high*100:.2f}%]")
    print(f"Assisted Pass@1: {assisted_passed_count}/{total} ({assisted_passed_count/total*100:.2f}%) | CI: [{asst_ci_low*100:.2f}%, {asst_ci_high*100:.2f}%]")
    print(f"Both Pass:       {raw_report['paired_comparison']['both_pass']}")
    print(f"Both Fail:       {raw_report['paired_comparison']['both_fail']}")
    print(f"Raw Only Pass:   {raw_report['paired_comparison']['raw_only_pass']}")
    print(f"Rescued (Asst):  {raw_report['paired_comparison']['assisted_only_pass']}")
    print(f"Preflight Fired: {preflight_triggered_count}")
    print(f"Artifact Raw:      {raw_out}")
    print(f"Artifact Assisted: {asst_out}")
    print("=======================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
