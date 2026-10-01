"""
Project Lucca — Standard Academic Benchmark Battery (PAL & Agentic Tool Micro-Suite)
Evaluates:
  1. GSM8K in PAL Mode (Program-Aided Language via Docker Python sandbox)
  2. HumanEval (Python code synthesis pass@1 via Docker execution)
  3. Big-Bench Hard (BBH) Algorithmic Subsets (boolean_expressions, geometric_shapes,
     tracking_shuffled_objects, dyck_languages)

Usage:
  uv run python scripts/run_standard_academic_benchmarks.py --benchmark gsm8k --samples 50
  uv run python scripts/run_standard_academic_benchmarks.py --benchmark humaneval --samples 50
  uv run python scripts/run_standard_academic_benchmarks.py --benchmark bbh --samples 30
  uv run python scripts/run_standard_academic_benchmarks.py --benchmark all --samples 30
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.brain.llm_client import LLMClient
from lucca.core.config import get_config
from lucca.sandbox.rpc import DockerRPCTransport


DATA_DIR = REPO_ROOT / "data" / "benchmarks"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = REPO_ROOT / "logs" / "test_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# Dataset Fetchers
# ===========================================================================

def get_gsm8k_dataset() -> list[dict]:
    """Fetch GSM8K test set."""
    cache_file = DATA_DIR / "gsm8k_test.jsonl"
    if not cache_file.exists():
        print("Downloading GSM8K test set from OpenAI repository...")
        url = "https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            cache_file.write_bytes(resp.read())
        print(f"  [OK] Saved GSM8K dataset to {cache_file}")

    lines = cache_file.read_text(encoding="utf-8").splitlines()
    data = [json.loads(line) for line in lines if line.strip()]
    return data


def get_humaneval_dataset() -> list[dict]:
    """Fetch HumanEval test set."""
    cache_file = DATA_DIR / "humaneval.jsonl"
    if not cache_file.exists():
        print("Downloading HumanEval dataset from OpenAI repository...")
        url = "https://raw.githubusercontent.com/openai/human-eval/master/data/HumanEval.jsonl.gz"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            decompressed = gzip.decompress(resp.read())
            cache_file.write_bytes(decompressed)
        print(f"  [OK] Saved HumanEval dataset to {cache_file}")

    lines = cache_file.read_text(encoding="utf-8").splitlines()
    data = [json.loads(line) for line in lines if line.strip()]
    return data


def get_bbh_subset(subset_name: str) -> list[dict]:
    """Fetch a Big-Bench Hard subset."""
    filename = f"{subset_name}.json"
    cache_file = DATA_DIR / f"bbh_{filename}"
    if not cache_file.exists():
        print(f"Downloading BBH {subset_name} from Google/BBH repository...")
        url = f"https://raw.githubusercontent.com/suzgunmirac/BIG-bench-Hard/main/bbh/{filename}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            cache_file.write_bytes(resp.read())
        print(f"  [OK] Saved BBH {subset_name} to {cache_file}")

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    return data.get("examples", [])


# ===========================================================================
# Extraction & Evaluation Helpers
# ===========================================================================

def extract_python_code(text: str) -> str:
    """Extract code from markdown blocks or bare python."""
    # Look for ```python ... ```
    m = re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # If no backticks, check if it starts with def/import
    lines = text.strip().splitlines()
    code_lines = []
    for l in lines:
        if any(l.startswith(k) for k in ("import ", "from ", "def ", "    ", "\t", "#", "print(", "return ", "if ", "for ", "while ")):
            code_lines.append(l)
    if code_lines:
        return "\n".join(code_lines).strip()
    return text.strip()


def extract_gsm8k_ground_truth(answer_str: str) -> float | None:
    """Extract numeric answer following ####."""
    m = re.search(r"####\s*(-?[0-9,]+(?:\.[0-9]+)?)", answer_str)
    if m:
        clean = m.group(1).replace(",", "")
        try:
            return float(clean)
        except ValueError:
            return None
    return None


def extract_numeric_from_stdout(stdout: str) -> float | None:
    """Extract last printed number from python stdout."""
    lines = stdout.strip().splitlines()
    if not lines:
        return None
    # Check last line first
    last_line = lines[-1].strip()
    # Try finding numbers
    nums = re.findall(r"-?[0-9]+(?:\.[0-9]+)?", last_line)
    if nums:
        try:
            return float(nums[-1])
        except ValueError:
            pass
    # Scan all lines in reverse
    for line in reversed(lines):
        nums = re.findall(r"-?[0-9]+(?:\.[0-9]+)?", line)
        if nums:
            try:
                return float(nums[-1])
            except ValueError:
                pass
    return None


def query_llm(prompt: str, max_tokens: int = 1024, enable_thinking: bool = False, retries: int = 2) -> str:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msg = data["choices"][0]["message"]
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning_content") or ""
                return content if content else reasoning
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"   [WARN] LLM query failed after {retries} attempts: {exc}")
                return ""
    return ""


# ===========================================================================
# Benchmark Runners
# ===========================================================================

def run_gsm8k_pal(transport: DockerRPCTransport, samples: int = 50, checkpoint_file: Path | None = None) -> dict:
    """Evaluate GSM8K using PAL mode (Program-Aided Language)."""
    dataset = get_gsm8k_dataset()
    if samples > 0 and samples < len(dataset):
        dataset = dataset[:samples]

    ckpt_path = checkpoint_file or (REPORTS_DIR / "gsm8k_pal_checkpoint.json")

    results = []
    passed_count = 0
    start_idx = 1

    # Load existing checkpoint if available
    if ckpt_path.exists():
        try:
            ckpt_data = json.loads(ckpt_path.read_text(encoding="utf-8"))
            results = ckpt_data.get("results", [])
            passed_count = ckpt_data.get("passed", 0)
            start_idx = len(results) + 1
            print(f"Resuming GSM8K from checkpoint: {len(results)}/{len(dataset)} already evaluated ({passed_count} PASS)")
        except Exception as e:
            print(f"Could not load checkpoint: {e}")

    print(f"\n=======================================================")
    print(f"Running GSM8K in PAL Mode ({len(dataset)} problems, starting at #{start_idx})")
    print(f"Method: Program-Aided Language (Docker Python Execution)")
    print(f"=======================================================")

    t_start = time.perf_counter()

    for idx in range(start_idx, len(dataset) + 1):
        item = dataset[idx - 1]
        q = item["question"]
        gt_raw = item["answer"]
        gt_val = extract_gsm8k_ground_truth(gt_raw)

        prompt = (
            "You are a mathematical code solver. Solve the following math problem by writing clean, executable Python code.\n"
            "Define variables, calculate the solution step by step, and finish with a print() statement showing only the final numerical answer.\n"
            "Put all Python code inside a ```python ... ``` block.\n\n"
            f"Problem: {q}\n"
        )

        t0 = time.perf_counter()
        resp = query_llm(prompt=prompt, max_tokens=1024, enable_thinking=False)
        t_llm = time.perf_counter() - t0

        code = extract_python_code(resp)
        exec_res = transport.execute(f"gsm8k-{idx}", "run_python", {"code": code}, timeout_s=15)
        stdout = exec_res.content or ""
        stderr = exec_res.stderr or ""
        exit_code = exec_res.exit_code

        pred_val = extract_numeric_from_stdout(stdout)
        
        # Grading
        is_pass = False
        if gt_val is not None and pred_val is not None:
            if abs(gt_val - pred_val) < 1e-4:
                is_pass = True

        if is_pass:
            passed_count += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"

        print(f"[{idx:03d}/{len(dataset)}] {status_str} | Pred: {pred_val} | Expected: {gt_val} | Latency: {t_llm:.2f}s")
        if not is_pass:
            print(f"   Code snippet: {code[:120]}...")
            if stderr:
                print(f"   Stderr: {stderr[:120]}...")

        results.append({
            "idx": idx,
            "question": q,
            "ground_truth_raw": gt_raw,
            "ground_truth_numeric": gt_val,
            "predicted_numeric": pred_val,
            "code": code,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "passed": is_pass,
            "llm_latency_s": round(t_llm, 3),
        })

        # Save checkpoint every 10 problems
        if idx % 10 == 0 or idx == len(dataset):
            ckpt_payload = {
                "benchmark": "GSM8K_PAL",
                "total_evaluated": len(results),
                "total_dataset": len(dataset),
                "passed": passed_count,
                "accuracy_pct": round(passed_count / len(results) * 100.0, 2),
                "results": results,
            }
            ckpt_path.write_text(json.dumps(ckpt_payload, indent=2), encoding="utf-8")

    elapsed = time.perf_counter() - t_start
    acc = (passed_count / len(dataset)) * 100.0 if dataset else 0.0

    print(f"\n--- GSM8K PAL Summary ---")
    print(f"Total: {len(dataset)} | Passed: {passed_count} | Accuracy: {acc:.1f}% | Elapsed: {elapsed:.1f}s\n")

    return {
        "benchmark": "GSM8K_PAL",
        "total": len(dataset),
        "passed": passed_count,
        "accuracy_pct": round(acc, 2),
        "elapsed_s": round(elapsed, 2),
        "results": results,
    }


def run_humaneval(transport: DockerRPCTransport, samples: int = 50) -> dict:
    """Evaluate HumanEval Python function generation pass@1."""
    dataset = get_humaneval_dataset()
    if samples > 0 and samples < len(dataset):
        dataset = dataset[:samples]

    print(f"\n=======================================================")
    print(f"Running HumanEval ({len(dataset)} coding tasks)")
    print(f"Method: pass@1 via Docker Sandbox Execution")
    print(f"=======================================================")

    results = []
    passed_count = 0
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

        t0 = time.perf_counter()
        resp = query_llm(prompt=instruction, max_tokens=1024, enable_thinking=False)
        t_llm = time.perf_counter() - t0

        completion_code = extract_python_code(resp)
        # If the model repeated the prompt, ensure it doesn't double-define
        if prompt.strip() in completion_code:
            full_code = f"{completion_code}\n\n{test_code}\n\ncheck({entry_point})\n"
        else:
            full_code = f"{prompt}\n{completion_code}\n\n{test_code}\n\ncheck({entry_point})\n"

        exec_res = transport.execute(f"he-{idx}", "run_python", {"code": full_code}, timeout_s=15)
        is_pass = (exec_res.exit_code == 0)

        if is_pass:
            passed_count += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"

        print(f"[{idx:03d}/{len(dataset)}] {status_str} | Task: {task_id} | Entry: {entry_point} | Latency: {t_llm:.2f}s")
        if not is_pass and exec_res.stderr:
            print(f"   Stderr: {exec_res.stderr.strip()[:140]}...")

        results.append({
            "task_id": task_id,
            "entry_point": entry_point,
            "prompt": prompt,
            "completion": completion_code,
            "exit_code": exec_res.exit_code,
            "stderr": exec_res.stderr,
            "passed": is_pass,
            "llm_latency_s": round(t_llm, 3),
        })

    elapsed = time.perf_counter() - t_start
    pass_rate = (passed_count / len(dataset)) * 100.0 if dataset else 0.0

    print(f"\n--- HumanEval Summary ---")
    print(f"Total: {len(dataset)} | Passed: {passed_count} | Pass@1: {pass_rate:.1f}% | Elapsed: {elapsed:.1f}s\n")

    return {
        "benchmark": "HumanEval",
        "total": len(dataset),
        "passed": passed_count,
        "pass_at_1_pct": round(pass_rate, 2),
        "elapsed_s": round(elapsed, 2),
        "results": results,
    }


def extract_bbh_answer(subset_key: str, resp: str, target: str) -> tuple[str, bool]:
    """Extract and grade BBH answer based on subset type."""
    resp_clean = resp.strip()
    target_clean = target.strip()

    if subset_key == "boolean_expressions":
        m = re.findall(r"\b(true|false)\b", resp_clean, re.IGNORECASE)
        pred = m[-1].lower() if m else resp_clean.splitlines()[-1].strip().lower()
        is_pass = (pred == target_clean.lower())
        return pred, is_pass

    elif subset_key in ("geometric_shapes", "tracking_shuffled_objects_three_objects"):
        clean_target = target_clean.strip("() \n\t").lower()
        m = re.findall(r"\(([A-Za-z0-9])\)", resp_clean)
        if m:
            pred_letter = m[-1].lower()
        else:
            m2 = re.findall(r"\b([A-Za-z0-9])\b", resp_clean.splitlines()[-1])
            pred_letter = m2[-1].lower() if m2 else resp_clean.splitlines()[-1].strip("() \n\t").lower()
        is_pass = (pred_letter == clean_target)
        return f"({pred_letter.upper()})", is_pass

    elif subset_key == "dyck_languages":
        lines = [l.strip() for l in resp_clean.splitlines() if l.strip()]
        last_line = lines[-1] if lines else ""
        last_line = re.sub(r"^(?:Answer|Output|Sequence|Result)\s*:\s*", "", last_line, flags=re.IGNORECASE).strip()
        is_pass = (last_line == target_clean) or (target_clean in resp_clean)
        return last_line, is_pass

    return resp_clean, False


def run_bbh_subsets(samples_per_subset: int = 25) -> dict:
    """Evaluate Big-Bench Hard algorithmic subsets."""
    subsets = [
        ("boolean_expressions", "Boolean Logic Evaluation"),
        ("geometric_shapes", "Geometric Shape Classification"),
        ("tracking_shuffled_objects_three_objects", "Object Position Permutation Tracking"),
        ("dyck_languages", "Bracket Nesting & Closure"),
    ]

    all_subset_reports = {}
    total_all = 0
    passed_all = 0
    t_start = time.perf_counter()

    for subset_key, title in subsets:
        examples = get_bbh_subset(subset_key)
        if samples_per_subset > 0 and samples_per_subset < len(examples):
            examples = examples[:samples_per_subset]

        print(f"\n=======================================================", flush=True)
        print(f"Running BBH: {title} ({len(examples)} examples)", flush=True)
        print(f"=======================================================", flush=True)

        sub_passed = 0
        sub_results = []

        for idx, ex in enumerate(examples, 1):
            inp = ex["input"]
            target = ex["target"].strip()

            if subset_key == "boolean_expressions":
                prompt = (
                    "You are a precise algorithmic logic assistant. Evaluate the following boolean expression.\n"
                    "Conclude with your final answer on a new line: either True or False.\n\n"
                    f"Input: {inp}\n"
                )
            elif subset_key in ("geometric_shapes", "tracking_shuffled_objects_three_objects"):
                prompt = (
                    "You are a precise algorithmic logic assistant. Solve the following multiple-choice task.\n"
                    "State your final chosen option letter in parentheses (e.g. (A), (B), (C)) on the final line.\n\n"
                    f"Input: {inp}\n"
                )
            elif subset_key == "dyck_languages":
                prompt = (
                    "You are a precise algorithmic logic assistant. Complete the sequence of closing brackets and symbols.\n"
                    "Provide only the sequence of closing symbols separated by spaces on the final line.\n\n"
                    f"Input: {inp}\n"
                )
            else:
                prompt = f"Solve the following task. Input: {inp}\n"

            t0 = time.perf_counter()
            resp = query_llm(prompt=prompt, max_tokens=1024, enable_thinking=False)
            t_llm = time.perf_counter() - t0

            pred, is_pass = extract_bbh_answer(subset_key, resp, target)

            if is_pass:
                sub_passed += 1
                status_str = "PASS"
            else:
                status_str = "FAIL"

            print(f"[{idx:02d}/{len(examples)}] {status_str} | Pred: '{pred[:30]}' | Target: '{target}' | {t_llm:.2f}s", flush=True)

            sub_results.append({
                "idx": idx,
                "input": inp,
                "target": target,
                "predicted": pred,
                "passed": is_pass,
                "latency_s": round(t_llm, 3),
            })

        sub_acc = (sub_passed / len(examples)) * 100.0 if examples else 0.0
        print(f"--- {title}: {sub_passed}/{len(examples)} ({sub_acc:.1f}%) ---", flush=True)

        all_subset_reports[subset_key] = {
            "title": title,
            "total": len(examples),
            "passed": sub_passed,
            "accuracy_pct": round(sub_acc, 2),
            "results": sub_results,
        }
        total_all += len(examples)
        passed_all += sub_passed

    elapsed = time.perf_counter() - t_start
    overall_acc = (passed_all / total_all) * 100.0 if total_all else 0.0

    print(f"\n--- BBH Overall Summary ---", flush=True)
    print(f"Total: {total_all} | Passed: {passed_all} | Accuracy: {overall_acc:.1f}% | Elapsed: {elapsed:.1f}s\n", flush=True)

    return {
        "benchmark": "BigBench_Hard_Subsets",
        "total": total_all,
        "passed": passed_all,
        "accuracy_pct": round(overall_acc, 2),
        "elapsed_s": round(elapsed, 2),
        "subsets": all_subset_reports,
    }


# ===========================================================================
# Main CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Standard Academic Benchmark Runner for Project Lucca")
    parser.add_argument("--benchmark", choices=["gsm8k", "humaneval", "bbh", "all"], default="all",
                        help="Benchmark to execute (default: all)")
    parser.add_argument("--samples", type=int, default=30,
                        help="Number of samples to run per benchmark (default: 30 for fast academic validation)")
    args = parser.parse_args()

    cfg = get_config()
    cfg.llm.temperature = 0.0

    print("Initializing DockerRPCTransport...")
    transport = DockerRPCTransport()
    if not transport.is_docker_available():
        print("ERROR: Docker daemon is not available in WSL2. Please ensure Docker is running.")
        sys.exit(1)

    final_report = {
        "timestamp": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "model": cfg.llm.model,
        "samples_configured": args.samples,
        "benchmarks": {},
    }

    report_path = REPORTS_DIR / f"academic_benchmarks_{final_report['timestamp']}.json"

    def save_report():
        report_path.write_text(json.dumps(final_report, indent=2), encoding="utf-8")
        (REPORTS_DIR / "academic_benchmarks_latest.json").write_text(json.dumps(final_report, indent=2), encoding="utf-8")

    if args.benchmark in ("gsm8k", "all"):
        final_report["benchmarks"]["gsm8k"] = run_gsm8k_pal(transport, samples=args.samples)
        save_report()

    if args.benchmark in ("humaneval", "all"):
        final_report["benchmarks"]["humaneval"] = run_humaneval(transport, samples=args.samples)
        save_report()

    if args.benchmark in ("bbh", "all"):
        final_report["benchmarks"]["bbh"] = run_bbh_subsets(samples_per_subset=args.samples)
        save_report()

    print(f"\n=======================================================", flush=True)
    print(f"All requested benchmarks completed successfully!", flush=True)
    print(f"Official Academic Report written to: {report_path}", flush=True)
    print(f"=======================================================\n", flush=True)


if __name__ == "__main__":
    main()
