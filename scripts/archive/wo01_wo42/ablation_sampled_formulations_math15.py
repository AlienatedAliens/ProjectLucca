#!/usr/bin/env python3
"""Ablation Experiment: Test-Time Compute (Sampled Formulations) on E4B's 15 MATH-500 Derivation Misses.

Tests whether test-time compute (k=5 samples at T=0.7) + consensus / execution voting
can recover the 15 genuine derivation misses identified during E4B vs 12B MATH-500 evaluation.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from collections import Counter
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

from lucca.sandbox.rpc import DockerRPCTransport
from scripts.run_modern_2024_benchmarks import (
    compare_math_lenient,
    compare_math_strict,
    extract_math_answer_from_text,
    extract_python_code_with_stage,
)

E4B_CHECKPOINT = REPO_ROOT / "logs" / "test_reports" / "checkpoint_math500_e4b-test-100.json"
OUT_REPORT = REPO_ROOT / "logs" / "test_reports" / "e4b_sampled_formulations_15_derivation.json"

DERIVATION_INDICES = [10, 19, 23, 28, 31, 33, 35, 37, 52, 61, 71, 73, 79, 81, 95]


def query_llm_sample(prompt: str, temperature: float = 0.7, seed: int = 42, max_tokens: int = 1536) -> str:
    """Query llama-server with temperature sampling."""
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "seed": seed,
        "chat_template_kwargs": {"enable_thinking": False},
        "cache_prompt": False,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        return msg.get("content") or msg.get("reasoning_content") or ""


def build_math_prompt(problem: str) -> str:
    rule_3 = (
        "3. The script MUST compute the final answer into a variable and end with a "
        "print(answer) statement that prints ONLY the final answer on stdout. Do not leave the final answer unprinted.\n\n"
    )
    return (
        f"You are a competition mathematician and computer algebra expert. Solve the following problem by writing "
        f"a concise Python script (< 30 lines) using SymPy or arithmetic that computes and prints ONLY the final exact answer.\n"
        f"STRICT RULES:\n"
        f"1. Output ONLY a ```python ... ``` block. DO NOT write scratchwork in comments (#), explanations, or derivations. Write only executable Python code so that print(answer) is always reached without token exhaustion.\n"
        f"2. Use exact symbolic arithmetic (SymPy Rational, Integer, radicals) instead of float division (/). Never output decimal approximations for fractions or irrationals. For linear systems, prefer direct arithmetic or substitution; if using SymPy solve(), pass `dict=True` (e.g. `sol = solve([eq1, eq2], [x, y], dict=True)`) to reliably obtain a list of dicts and access variables with `sol[0][x]`. Never index plain solve() as `sol[0]`. Simplify all expressions completely before printing. Print only the exact mathematical value, without labels (e.g. print `5`, not `x = 5`).\n"
        f"{rule_3}"
        f"Problem: {problem}\n"
    )


def main() -> int:
    data = json.loads(E4B_CHECKPOINT.read_text(encoding="utf-8"))
    items_to_test = [r for r in data if r["idx"] in DERIVATION_INDICES]

    print("=" * 75)
    print("Project Lucca — Test-Time Compute Ablation on E4B's 15 Derivation Misses")
    print(f"Targeting {len(items_to_test)} items | k=5 samples per item | T=0.7")
    print("=" * 75)

    transport = DockerRPCTransport(container_name="lucca-file-sandbox")
    transport.ensure_container_running()

    k_samples = 5
    results = []
    pass_at_k_strict = 0
    pass_at_k_lenient = 0
    majority_vote_strict = 0
    majority_vote_lenient = 0

    t_start = time.perf_counter()

    for item_num, item in enumerate(items_to_test, 1):
        idx = item["idx"]
        prob = item["problem"]
        expected = item["expected_ans"]
        greedy_pred = item.get("predicted_ans", "")

        prompt = build_math_prompt(prob)
        print(f"\n[{item_num:02d}/15] Item {idx:02d} | Subj: {item.get('subject')} (L{item.get('level')}) | Exp: {expected} | Greedy: {greedy_pred}")

        sample_records = []
        answers_strict_pass = []
        answers_lenient_pass = []
        extracted_preds = []

        for sample_i in range(k_samples):
            seed = 1000 + idx * 10 + sample_i
            t0 = time.perf_counter()
            resp = query_llm_sample(prompt, temperature=0.7, seed=seed)
            t_llm = time.perf_counter() - t0

            raw_code, stage = extract_python_code_with_stage(resp)
            if not raw_code:
                raw_code = resp

            exec_res = transport.execute(f"sample-{idx}-{sample_i}", "run_python", {"code": raw_code}, timeout_s=15)
            output = exec_res.content or ""
            lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
            pred = lines[-1] if lines else ""
            if pred.lower() in ("none", "null") and len(lines) >= 2:
                pred = lines[-2]
            if not pred:
                pred = extract_math_answer_from_text(resp)

            s_pass = compare_math_strict(pred, expected) if pred else False
            l_pass = compare_math_lenient(pred, expected) if pred else False

            sample_records.append({
                "sample_idx": sample_i,
                "seed": seed,
                "latency_s": round(t_llm, 2),
                "exit_code": exec_res.exit_code,
                "pred": pred,
                "strict_pass": s_pass,
                "lenient_pass": l_pass,
            })

            if pred:
                extracted_preds.append(pred)
            if s_pass:
                answers_strict_pass.append(pred)
            if l_pass:
                answers_lenient_pass.append(pred)

            status = "S:Y" if s_pass else ("L:Y" if l_pass else "FAIL")
            print(f"   Sample {sample_i + 1}: [{status}] Pred: '{pred}' (exit {exec_res.exit_code}, {t_llm:.1f}s)")

        # Any sample passed?
        has_strict_pass = len(answers_strict_pass) > 0
        has_lenient_pass = len(answers_lenient_pass) > 0
        if has_strict_pass:
            pass_at_k_strict += 1
        if has_lenient_pass:
            pass_at_k_lenient += 1

        # Majority vote on non-empty preds
        mv_pred = None
        mv_s_pass = False
        mv_l_pass = False
        if extracted_preds:
            counts = Counter(extracted_preds)
            mv_pred, top_count = counts.most_common(1)[0]
            mv_s_pass = compare_math_strict(mv_pred, expected)
            mv_l_pass = compare_math_lenient(mv_pred, expected)
            if mv_s_pass:
                majority_vote_strict += 1
            if mv_l_pass:
                majority_vote_lenient += 1

        print(f"   => Result: Pass@5(Strict)={'YES' if has_strict_pass else 'NO'} | MajorityVote='{mv_pred}' (Strict={'YES' if mv_s_pass else 'NO'})")

        results.append({
            "idx": idx,
            "subject": item.get("subject"),
            "level": item.get("level"),
            "expected_ans": expected,
            "greedy_pred": greedy_pred,
            "samples": sample_records,
            "pass_at_5_strict": has_strict_pass,
            "pass_at_5_lenient": has_lenient_pass,
            "majority_vote_pred": mv_pred,
            "majority_vote_strict": mv_s_pass,
            "majority_vote_lenient": mv_l_pass,
            "distinct_preds_count": len(set(extracted_preds)),
        })

    total_elapsed = time.perf_counter() - t_start

    print("\n" + "=" * 75)
    print("TEST-TIME COMPUTE ABLATION SUMMARY (E4B on 15 Derivation Misses)")
    print("=" * 75)
    print(f"Total Items Tested:           {len(items_to_test)}")
    print(f"Greedy Strict Pass:           0 / 15 (0.0%) [by definition]")
    print(f"Pass@5 Strict (Oracle):       {pass_at_k_strict} / 15 ({pass_at_k_strict / len(items_to_test) * 100:.1f}%)")
    print(f"Pass@5 Lenient (Oracle):      {pass_at_k_lenient} / 15 ({pass_at_k_lenient / len(items_to_test) * 100:.1f}%)")
    print(f"Majority Vote Strict:         {majority_vote_strict} / 15 ({majority_vote_strict / len(items_to_test) * 100:.1f}%)")
    print(f"Majority Vote Lenient:        {majority_vote_lenient} / 15 ({majority_vote_lenient / len(items_to_test) * 100:.1f}%)")
    print(f"Total Elapsed Time:           {total_elapsed:.1f}s ({total_elapsed / len(items_to_test):.1f}s per item)")
    print("=" * 75)

    summary_payload = {
        "timestamp": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "model": "gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf",
        "temperature": 0.7,
        "k_samples": k_samples,
        "total_items": len(items_to_test),
        "pass_at_5_strict_count": pass_at_k_strict,
        "pass_at_5_lenient_count": pass_at_k_lenient,
        "majority_vote_strict_count": majority_vote_strict,
        "majority_vote_lenient_count": majority_vote_lenient,
        "elapsed_s": round(total_elapsed, 2),
        "items": results,
    }

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(f"Saved full report to: {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
