import argparse
import copy
import json
import re
import sys
import time
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.sandbox.rpc import DockerRPCTransport
from scripts.run_modern_2024_benchmarks import (
    compare_math_results,
    extract_math_answer_from_text,
    extract_python_code_with_stage,
    query_llm_with_meta,
)

REPORTS_DIR = REPO_ROOT / "logs" / "test_reports"
CACHE_FILE = REPORTS_DIR / "turn1_cache_108.json"


def strip_full_line_comments(code: str) -> tuple[str, bool, int]:
    """Remove full-line comments (lstrip starts with '#') and collapse blank lines.
    Do not touch inline comments or string literals.
    Returns (stripped_code, is_stripped_empty, comment_lines_removed).
    """
    clean_lines = []
    lines = code.splitlines()
    removed_count = 0
    for line in lines:
        if line.lstrip().startswith("#"):
            removed_count += 1
            continue
        if not line.strip():
            if clean_lines and clean_lines[-1] != "":
                clean_lines.append("")
            continue
        clean_lines.append(line)

    stripped = "\n".join(clean_lines).strip()
    is_empty = len(stripped) == 0
    return stripped, is_empty, removed_count


def build_feedback_prompt(
    mode: str,
    problem: str,
    code: str,
    exec_res_exit: int,
    exec_res_stderr: str,
    math_out: str,
) -> tuple[str, bool, int]:
    """Build Turn 2 feedback prompt based on reprompt_mode: stub, clean, or stripped.
    Returns (prompt, stripped_empty, comment_lines_removed).
    """
    stripped_empty = False
    comment_lines_removed = 0

    if exec_res_exit != 0:
        err_trace = (exec_res_stderr or math_out).strip()
        # For traceback, both 51cbf4b and 958e1dc include code
        code_to_pass = code
        if mode == "stripped":
            stripped_code, is_empty, removed = strip_full_line_comments(code)
            comment_lines_removed = removed
            if not is_empty:
                code_to_pass = stripped_code
        prompt = (
            f"You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem produced an execution error in the sandbox:\n\n"
            f"Problem: {problem}\n\n"
            f"Your Initial Script:\n```python\n{code_to_pass}\n```\n\n"
            f"Execution Error / Traceback in Docker:\n{err_trace[:600]}\n\n"
            f"Please diagnose the error (e.g. fix syntax/import/attribute mistakes, or if SymPy's analytical solver fails, use numerical iteration or search). "
            f"Output ONLY the corrected complete Python script in a ```python ... ``` block (< 30 lines) that ends with print(...) printing ONLY the final answer."
        )
        return prompt, stripped_empty, comment_lines_removed

    # Empty stdout branch (exit code 0, empty or unprinted stdout)
    if mode == "stub":
        # Verbatim 51cbf4b template
        prompt = (
            f"You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem executed with exit code 0, but produced EMPTY stdout because it forgot to print the final answer:\n\n"
            f"Problem: {problem}\n\n"
            f"Your Initial Script:\n```python\n{code}\n```\n\n"
            f"CRITICAL REQUIREMENT:\n"
            f"The script must compute the final exact answer and explicitly print it on stdout. Do not write rambling comments or derivations.\n"
            f"Output ONLY the corrected complete Python script in a ```python ... ``` block (< 30 lines) that ends with print(answer) printing ONLY the final answer."
        )
    elif mode == "clean":
        # Verbatim 958e1dc template
        prompt = (
            f"You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem executed with exit code 0, but produced EMPTY or unprinted stdout:\n\n"
            f"Problem: {problem}\n\n"
            f"CRITICAL REQUIREMENT:\n"
            f"The script must compute the final exact answer and explicitly print it on stdout using print(answer). Do not write rambling comments or derivations.\n"
            f"Output ONLY the corrected complete Python script in a ```python ... ``` block (< 30 lines) that ends with print(answer) printing ONLY the final answer."
        )
    elif mode == "stripped":
        stripped_code, is_empty, removed = strip_full_line_comments(code)
        stripped_empty = is_empty
        comment_lines_removed = removed
        if stripped_empty:
            prompt = (
                f"You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem executed with exit code 0, but produced EMPTY or unprinted stdout:\n\n"
                f"Problem: {problem}\n\n"
                f"CRITICAL REQUIREMENT:\n"
                f"The script must compute the final exact answer and explicitly print it on stdout using print(answer). Do not write rambling comments or derivations.\n"
                f"Output ONLY the corrected complete Python script in a ```python ... ``` block (< 30 lines) that ends with print(answer) printing ONLY the final answer."
            )
        else:
            prompt = (
                f"You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem executed with exit code 0, but produced EMPTY stdout because it forgot to print the final answer:\n\n"
                f"Problem: {problem}\n\n"
                f"Your Initial Script:\n```python\n{stripped_code}\n```\n\n"
                f"CRITICAL REQUIREMENT:\n"
                f"The script must compute the final exact answer and explicitly print it on stdout. Do not write rambling comments or derivations.\n"
                f"Output ONLY the corrected complete Python script in a ```python ... ``` block (< 30 lines) that ends with print(answer) printing ONLY the final answer."
            )
    else:
        raise ValueError(f"Unknown reprompt mode: {mode}")

    return prompt, stripped_empty, comment_lines_removed


def run_variant(mode: str, sample_indices: list[int] | None = None) -> list[dict]:
    if not CACHE_FILE.exists():
        raise FileNotFoundError(f"Turn 1 cache not found at {CACHE_FILE}. Run reproduce_turn1_108.py first.")

    turn1_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    indices = sorted([int(k) for k in turn1_cache.keys()])
    if sample_indices:
        indices = [i for i in indices if i in sample_indices]

    print(f"\n=======================================================")
    print(f"Running Reprompt Variant [{mode.upper()}] on {len(indices)} Feedback Items")
    print(f"Turn 1: FROZEN from turn1_cache_108.json (Zero Turn-1 Variance)")
    print(f"Turn 2 Max Tokens: 768 | Temp: 0.0 | Seed: 42")
    print(f"=======================================================\n")

    transport = DockerRPCTransport(container_name="lucca-file-sandbox")
    transport.ensure_container_running()

    results = []
    passed_count = 0
    t_start = time.perf_counter()

    for pos, idx in enumerate(indices, 1):
        rec = turn1_cache[str(idx)]
        problem = rec["problem"]
        expected_ans = rec["expected_ans"]
        code = rec["turn1_code"]
        exec_res_exit = rec["turn1_exit_code"]
        exec_res_stderr = rec["turn1_stderr"]
        math_out = rec["turn1_stdout"]
        t1_lat = rec["turn1_latency_s"]
        t1_tok = rec["turn1_completion_tokens"]
        t1_fin = rec["turn1_finish_reason"]

        prompt2, stripped_empty, removed_comments = build_feedback_prompt(
            mode=mode,
            problem=problem,
            code=code,
            exec_res_exit=exec_res_exit,
            exec_res_stderr=exec_res_stderr,
            math_out=math_out,
        )

        t0 = time.perf_counter()
        resp2, finish2, tokens2 = query_llm_with_meta(prompt=prompt2, max_tokens=768, enable_thinking=False)
        t_corr = time.perf_counter() - t0

        code2, stage2 = extract_python_code_with_stage(resp2)
        exec2_exit = 0
        exec2_stderr = ""
        math_out2 = ""
        feedback_succeeded = False
        pred_str = ""

        if code2:
            exec_res2 = transport.execute(f"reprompt-{mode}-{idx}", "run_python", {"code": code2}, timeout_s=20)
            exec2_exit = exec_res2.exit_code
            exec2_stderr = exec_res2.stderr or ""
            math_out2 = exec_res2.content or ""
            if exec2_exit == 0 and math_out2 and any(l.strip() for l in math_out2.strip().splitlines()):
                lines2 = [l.strip() for l in math_out2.strip().splitlines() if l.strip()]
                if lines2:
                    pred_str = lines2[-1]
                    if pred_str.lower() in ("none", "null") and len(lines2) >= 2:
                        pred_str = lines2[-2]
                    feedback_succeeded = True

        if not pred_str:
            pred_str = extract_math_answer_from_text(resp2)

        is_pass = compare_math_results(pred_str, expected_ans, use_sympy=True)
        if is_pass:
            passed_count += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"

        total_lat = round(t1_lat + t_corr, 3)
        total_tokens = t1_tok + tokens2
        is_empty_or_no_code = (not code2) or (exec2_exit == 0 and not math_out2.strip())

        safe_pred = pred_str[:30].encode("ascii", "replace").decode("ascii")
        safe_expected = expected_ans[:30].encode("ascii", "replace").decode("ascii")
        print(f"[{pos:03d}/{len(indices)}] {status_str} | Idx {idx:03d} | Pred: {safe_pred} | Exp: {safe_expected} | T2 Lat: {t_corr:.2f}s | T2 Tok: {tokens2}", flush=True)

        results.append({
            "idx": idx,
            "item_id": f"dev-{idx}",
            "reprompt_mode": mode,
            "stripped_empty": stripped_empty if mode == "stripped" else False,
            "comment_lines_removed": removed_comments if mode == "stripped" else 0,
            "passed": is_pass,
            "feedback_succeeded": feedback_succeeded,
            "predicted_ans": pred_str,
            "expected_ans": expected_ans,
            "turn1_code": code,
            "turn2_code": code2,
            "turn2_empty_or_no_code": is_empty_or_no_code,
            "turn2_latency_s": round(t_corr, 3),
            "turn2_tokens": tokens2,
            "turn2_finish_reason": finish2,
            "llm_latency_s": total_lat,
            "completion_tokens": total_tokens,
        })

    elapsed = time.perf_counter() - t_start
    print(f"\n--- Variant [{mode.upper()}] Summary ---")
    print(f"Items: {len(indices)} | Passed: {passed_count} ({passed_count/len(indices)*100:.1f}%) | Elapsed: {elapsed:.1f}s\n")
    return results


def main():
    parser = argparse.ArgumentParser(description="Three-way Turn 2 re-prompt comparison on feedback items")
    parser.add_argument("--mode", type=str, choices=["stub", "clean", "stripped", "all"], required=True)
    parser.add_argument("--sample", type=str, default="", help="Comma-separated subset of indices for testing (e.g. '1,2,4,7,9')")
    args = parser.parse_args()

    sample_indices = [int(x.strip()) for x in args.sample.split(",") if x.strip().isdigit()] if args.sample else None

    modes_to_run = ["stub", "clean", "stripped"] if args.mode == "all" else [args.mode]
    for mode in modes_to_run:
        results = run_variant(mode, sample_indices=sample_indices)
        suffix = f"_sample" if sample_indices else ""
        out_file = REPORTS_DIR / f"reprompt_variant_{mode}_108{suffix}.json"
        out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"[OK] Saved results to: {out_file}")


if __name__ == "__main__":
    main()
