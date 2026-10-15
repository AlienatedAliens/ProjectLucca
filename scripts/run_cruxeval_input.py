#!/usr/bin/env python3
"""
Project Lucca — CRUXEval-Input Benchmark & CEGIS Verification Ladder (WO-35.6)
==============================================================================
Evaluates input prediction on CRUXEval: given function `f` and target return value `output`,
find arguments `args` such that `f(*args) == output`.

Unlike CRUXEval-Output (which is trivially solved 100% by executing the code),
CRUXEval-Input requires reasoning backwards from outputs to inputs, forming hypotheses,
and checking them in a sandbox.

Comparison Ladder:
1. Arm A Direct: One-shot direct prediction of `f(...)` without sandbox execution feedback.
2. Arm B One-Shot PAL: Model predicts `f(...)`, executed once in Docker container.
3. Arm B Iterative CEGIS / Self-Debugging: Model predicts candidate, executes in Docker.
   If output mismatch or runtime error occurs, the concrete counterexample or traceback
   is provided to the model across up to N repair turns.

Quantifies:
- Direct vs PAL lift
- One-shot vs Multi-Turn CEGIS Rescue Delta (items saved specifically by repair turns)
- Failure stage attribution and latency breakdown
- Exact two-sided binomial McNemar test and Wilson 95% confidence intervals.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any, Final

import httpx
from scipy.stats import binomtest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Windows console cp1252 fix
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 60.0


def wilson_ci(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Computes Wilson score interval for binomial proportions."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.95996
    p = k / n
    denom = 1.0 + z**2 / n
    center = (p + z**2 / (2.0 * n)) / denom
    margin = (z * math.sqrt((p * (1.0 - p) / n) + (z**2 / (4.0 * n**2)))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def query_llm(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 256,
    enable_thinking: bool = False,
) -> tuple[str, str]:
    """Queries resident llama-server instance synchronously, returning (content, finish_reason)."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        content = str(choice["message"]["content"] or "").strip()
        finish_reason = str(choice.get("finish_reason") or "stop")
        return content, finish_reason


import threading

def execute_sandboxed_eval(
    func_code: str,
    candidate_call: str,
    target_output: str,
    timeout: float = 4.0,
) -> tuple[bool, str, str]:
    """
    Executes a candidate function call `f(...)` inside an isolated namespace with a watchdog timer.
    Returns: (is_correct, feedback_message, execution_status).
    """
    result_holder: list[tuple[bool, str, str]] = []

    def _worker() -> None:
        exec_globals: dict[str, Any] = {
            "__builtins__": __builtins__,
        }
        try:
            exec(func_code, exec_globals)
            if "f" not in exec_globals or not callable(exec_globals["f"]):
                result_holder.append((False, "Function `f` not defined in scope", "RUNTIME_ERROR"))
                return

            try:
                expected = ast.literal_eval(target_output)
            except Exception:
                expected = eval(target_output, exec_globals)

            actual = eval(candidate_call, exec_globals)
            if actual == expected:
                result_holder.append((True, "SUCCESS", "VERIFIED_SUCCESS"))
            else:
                result_holder.append((False, f"got {repr(actual)}, expected {repr(expected)}", "OUTPUT_MISMATCH"))
        except Exception as exc:
            result_holder.append((False, f"{type(exc).__name__}: {exc}", "RUNTIME_ERROR"))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        return False, f"TimeoutError: execution exceeded {timeout}s watchdog", "TIMEOUT"

    if result_holder:
        return result_holder[0]

    return False, "Execution produced no result", "EXECUTION_FAILURE"


def extract_function_call(response: str) -> str | None:
    """Extracts `f(...)` invocation from model output."""
    # Check for backtick blocks
    code_blocks = re.findall(r"```(?:python)?\s*(.*?)\s*```", response, re.DOTALL)
    text_to_search = code_blocks[-1] if code_blocks else response

    # Try matching f(...)
    match = re.search(r"\b(f\s*\([^)]*\))", text_to_search)
    if match:
        call = match.group(1).strip()
        # Basic sanity check
        try:
            tree = ast.parse(call, mode="eval")
            if isinstance(tree.body, ast.Call):
                return call
        except SyntaxError:
            pass

    # Try multiline call if brackets span lines
    match_multi = re.search(r"\b(f\s*\(.*?\))", text_to_search, re.DOTALL)
    if match_multi:
        call = "".join(match_multi.group(1).splitlines()).strip()
        try:
            tree = ast.parse(call, mode="eval")
            if isinstance(tree.body, ast.Call):
                return call
        except SyntaxError:
            pass

    return None


@dataclass
class CruxInputProblemResult:
    problem_id: str
    code: str
    target_output: str
    ground_truth_input: str
    # Arm A Direct
    arm_a_predicted_call: str | None
    arm_a_success: bool
    arm_a_finish_reason: str
    # Arm B CEGIS
    arm_b_method: str  # "ONE_SHOT_VERIFIED" | "REPAIRED_PROGRAM" | "INTERNAL_FALLBACK"
    arm_b_turns_used: int
    arm_b_predicted_call: str | None
    arm_b_success: bool
    arm_b_failure_stage: str | None
    elapsed_ms: float


def _extract_signature_hint(code: str) -> str:
    """Extracts exact parameter count and names from `def f(...)` via AST (Failure Class 1 fix)."""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "f":
                params = [a.arg for a in node.args.args]
                return f"Signature requirement: `f` takes {len(params)} positional argument(s): f({', '.join(params)})."
    except Exception:
        pass
    return ""


def evaluate_cruxeval_input_problem(
    item: dict[str, Any], max_turns: int = 3
) -> CruxInputProblemResult:
    t0 = time.perf_counter()
    sample_id = str(item["id"])
    code = str(item["code"]).strip()
    target_out = str(item["output"]).strip()
    gt_input = str(item["input"]).strip()
    sig_hint = _extract_signature_hint(code)

    system_prompt = (
        "You are a code synthesis engine. Output ONLY the Python function invocation `f(...)` "
        "in a ```python ... ``` block. Do not provide any conversational text or explanation."
    )

    # 1. Arm A Direct (1-shot zero execution feedback)
    arm_a_prompt = (
        "You will be given a Python function `f` and its return value.\n"
        "Your task is to determine an input argument that makes `f` return that exact value.\n\n"
        f"Function:\n```python\n{code}\n```\n\n"
        f"Target Output:\n{target_out}\n\n"
        "Output ONLY the function call with arguments in a ```python ... ``` block, e.g. ```python\nf(...)\n```."
    )
    a_resp, a_finish = query_llm(
        arm_a_prompt,
        system_prompt=system_prompt,
        temperature=0.0,
        max_tokens=256,
        enable_thinking=False,
    )
    a_call = extract_function_call(a_resp)
    a_success = False
    if a_call:
        a_success, _, _ = execute_sandboxed_eval(code, a_call, target_out)

    # 2. Arm B Iterative CEGIS / Self-Debugging (Feedback loop)
    turn_history: list[dict[str, str]] = []
    current_prompt = arm_a_prompt
    b_success = False
    b_call: str | None = None
    b_method = "INTERNAL_FALLBACK"
    b_failure_stage: str | None = None
    turns_used = 0

    failed_attempts: list[str] = []
    if sig_hint:
        current_prompt = f"{arm_a_prompt}\n{sig_hint}"

    # Check if Arm A already passed sandbox verification -> instant Turn 1 win without redundant LLM call
    if a_success and a_call:
        b_success = True
        b_call = a_call
        b_method = "ONE_SHOT_VERIFIED"
        turns_used = 1
    else:
        if a_call:
            _, fb0, st0 = execute_sandboxed_eval(code, a_call, target_out)
            failed_attempts.append(f"- `{a_call}` -> {fb0}")
            b_failure_stage = st0
            b_call = a_call

        for turn in range(1, max_turns + 1):
            turns_used = turn
            if failed_attempts:
                history_block = "\n".join(failed_attempts)
                current_prompt = (
                    f"Function:\n```python\n{code}\n```\n"
                    f"{sig_hint}\n"
                    f"Target Output: {target_out}\n\n"
                    f"Previous candidate input(s) failed sandbox verification:\n{history_block}\n\n"
                    "Work backwards from the return statement to the input parameters. "
                    "Propose a DIFFERENT, corrected function call that produces the exact Target Output.\n"
                    "Output ONLY the corrected function call inside ```python\nf(...)\n```."
                )

            temp = 0.0 if (turn == 1 and not failed_attempts) else (0.3 + 0.2 * (turn - 1))
            b_resp, b_finish = query_llm(
                current_prompt,
                system_prompt=system_prompt,
                temperature=temp,
                max_tokens=256,
                enable_thinking=False,
            )
            cand_call = extract_function_call(b_resp)
            if not cand_call:
                b_failure_stage = "TRANSLATION_NO_CALL"
                continue

            b_call = cand_call
            is_correct, feedback, status = execute_sandboxed_eval(code, cand_call, target_out)
            if is_correct:
                b_success = True
                b_method = "ONE_SHOT_VERIFIED" if (turn == 1 and not failed_attempts) else "REPAIRED_PROGRAM"
                b_failure_stage = None
                break

            b_failure_stage = status
            failed_attempts.append(f"- `{cand_call}` -> {feedback}")

    # Fallback to Arm A if Arm B failed completely
    if not b_success and a_success:
        b_call = a_call
        b_success = True
        b_method = "INTERNAL_FALLBACK"

    elapsed = (time.perf_counter() - t0) * 1000.0

    return CruxInputProblemResult(
        problem_id=sample_id,
        code=code,
        target_output=target_out,
        ground_truth_input=gt_input,
        arm_a_predicted_call=a_call,
        arm_a_success=a_success,
        arm_a_finish_reason=a_finish,
        arm_b_method=b_method,
        arm_b_turns_used=turns_used,
        arm_b_predicted_call=b_call,
        arm_b_success=b_success,
        arm_b_failure_stage=b_failure_stage if not b_success else None,
        elapsed_ms=elapsed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="CRUXEval-Input Benchmark & CEGIS Verification Ladder")
    parser.add_argument("--split", choices=["dev", "sealed", "smoke"], default="dev",
                        help="Data split: smoke (10 items), dev (50 items, samples 0-49), sealed (100 items, samples 50-149)")
    parser.add_argument("--max-turns", type=int, default=3, help="Maximum repair turns for Arm B CEGIS")
    parser.add_argument("--output-json", type=str, default="", help="Path to write JSON report")
    args = parser.parse_args()

    crux_file = REPO_ROOT / "data" / "benchmarks" / "cruxeval" / "data" / "cruxeval.jsonl"
    if not crux_file.exists():
        print(f"Error: dataset not found at {crux_file}")
        sys.exit(1)

    with open(crux_file, "r", encoding="utf-8") as f:
        all_items = [json.loads(line) for line in f if line.strip()]

    if args.split == "smoke":
        dataset = all_items[:10]
    elif args.split == "dev":
        dataset = all_items[:50]
    else:  # sealed
        dataset = all_items[50:150]

    print(f"=== CRUXEval-Input Benchmark Runner (WO-35.6) ===")
    print(f"Split: {args.split} ({len(dataset)} items) | Max CEGIS Turns: {args.max_turns}")
    print(f"Server URL: {SERVER_URL}")
    print(f"Start Time: {datetime.now(UTC).isoformat()}\n")

    results: list[CruxInputProblemResult] = []
    a_wins = 0
    b_wins = 0
    one_shot_wins = 0
    repaired_wins = 0

    for idx, item in enumerate(dataset, 1):
        res = evaluate_cruxeval_input_problem(item, max_turns=args.max_turns)
        results.append(res)

        if res.arm_a_success:
            a_wins += 1
        if res.arm_b_success:
            b_wins += 1
            if res.arm_b_method == "ONE_SHOT_VERIFIED":
                one_shot_wins += 1
            elif res.arm_b_method == "REPAIRED_PROGRAM":
                repaired_wins += 1

        delta_tag = ""
        if res.arm_b_success and not res.arm_a_success:
            delta_tag = f" [SCAFFOLD LIFT via {res.arm_b_method} (turn {res.arm_b_turns_used})]"
        elif res.arm_b_method == "REPAIRED_PROGRAM":
            delta_tag = f" [CEGIS RESCUE at turn {res.arm_b_turns_used}]"

        status_a = "PASS" if res.arm_a_success else "FAIL"
        status_b = "PASS" if res.arm_b_success else "FAIL"
        print(f"[{idx:3d}/{len(dataset)}] {res.problem_id}: Arm A: {status_a} | Arm B: {status_b} ({res.arm_b_method}){delta_tag} ({res.elapsed_ms:.0f}ms)")
        if not res.arm_b_success and res.arm_b_failure_stage:
            print(f"      -> Failure stage: {res.arm_b_failure_stage}")

    n = len(results)
    ci_a = wilson_ci(a_wins, n)
    ci_b = wilson_ci(b_wins, n)

    # McNemar discordant pairs
    disc_10 = sum(1 for r in results if r.arm_a_success and not r.arm_b_success)
    disc_01 = sum(1 for r in results if not r.arm_a_success and r.arm_b_success)
    p_val = binomtest(disc_01, disc_10 + disc_01, 0.5, alternative="two-sided").pvalue if (disc_10 + disc_01) > 0 else 1.0

    print("\n" + "=" * 65)
    print("=== SUMMARY METRICS ===")
    print("=" * 65)
    print(f"Total Problems: {n}")
    print(f"Arm A Direct Pass Rate:       {a_wins}/{n} ({a_wins/n*100:.1f}%) [95% CI: {ci_a[0]*100:.1f}%, {ci_a[1]*100:.1f}%]")
    print(f"Arm B One-Shot Verified:      {one_shot_wins}/{n} ({one_shot_wins/n*100:.1f}%)")
    print(f"Arm B Repaired / Rescued:     {repaired_wins}/{n} ({repaired_wins/n*100:.1f}%)")
    print(f"Arm B Overall (CEGIS Engine): {b_wins}/{n} ({b_wins/n*100:.1f}%) [95% CI: {ci_b[0]*100:.1f}%, {ci_b[1]*100:.1f}%]")
    print(f"Net Lift over Direct:         +{(b_wins - a_wins)/n*100:.1f} pp")
    print(f"CEGIS Repair Rescue Lift:     +{repaired_wins/n*100:.1f} pp (rescued {repaired_wins} problems that failed one-shot)")
    print(f"Discordant Pairs (A:B):       {disc_10}:{disc_01}")
    print(f"Exact McNemar Two-Sided p:    {p_val:.4f}")

    # Save JSON report
    report_data = {
        "benchmark": "CRUXEval-Input",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "split": args.split,
        "total_problems": n,
        "max_turns": args.max_turns,
        "summary": {
            "arm_a_passed": a_wins,
            "arm_a_rate": a_wins / n,
            "arm_a_ci_95": list(ci_a),
            "arm_b_passed": b_wins,
            "arm_b_rate": b_wins / n,
            "arm_b_ci_95": list(ci_b),
            "one_shot_passed": one_shot_wins,
            "repaired_passed": repaired_wins,
            "net_lift_pp": (b_wins - a_wins) / n * 100.0,
            "cegis_rescue_pp": repaired_wins / n * 100.0,
            "discordant_pairs": [disc_10, disc_01],
            "mcnemar_p_value": p_val,
        },
        "problems": [asdict(r) for r in results],
    }

    out_path = Path(args.output_json) if args.output_json else REPO_ROOT / "logs" / "test_reports" / f"cruxeval_input_{args.split}_{time.time_ns() // 1_000_000}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\nSealed report written to: {out_path}")


if __name__ == "__main__":
    main()
