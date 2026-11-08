import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_modern_2024_benchmarks import (
    query_llm_with_meta,
    extract_python_code_with_stage,
    extract_math_answer_from_text,
    compare_math_results,
)
from lucca.sandbox.rpc import DockerRPCTransport

transport = DockerRPCTransport(container_name="lucca-file-sandbox")
transport.ensure_container_running()

# Load 319 baseline for comparison
baseline_file = Path("logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json")
b_data = {x["idx"]: x for x in json.loads(baseline_file.read_text(encoding="utf-8"))}

cache_file = Path("logs/test_reports/turn1_cache_108.json")
c = json.loads(cache_file.read_text(encoding="utf-8"))

sample_indices = [1, 2, 4, 7, 9, 10, 11, 15, 20, 21, 55, 78, 85, 90, 105, 129, 140, 168, 180, 248]

print(f"=======================================================")
print(f"Testing Variant B (Plan-then-Code) on {len(sample_indices)} Feedback Items")
print(f"Turn 1: Plan-then-Code Prompt (< 3 lines plan, < 30 lines code)")
print(f"Turn 2: Committed Stub Re-prompt (v1.3 Locked)")
print(f"=======================================================\n")

results = []
gained = []
lost = []

for idx in sample_indices:
    rec = c[str(idx)]
    problem = rec["problem"]
    expected_ans = rec["expected_ans"]
    baseline_passed = b_data[idx]["passed"]
    
    # 1. Turn 1 Prompt: Variant B Plan-then-Code
    prompt1 = (
        f"You are a competition mathematician and computer algebra expert. Solve the following problem by writing "
        f"a concise Python script (< 30 lines) using SymPy or arithmetic that computes and prints ONLY the final exact answer.\n"
        f"STRICT RULES:\n"
        f"1. You may write a brief plan (at most 3 lines) before the code block. Then output the complete Python script in a ```python ... ``` block (< 30 lines).\n"
        f"2. Simplify all expressions completely before printing. Print only the exact mathematical value, without labels (e.g. print `5`, not `x = 5`).\n"
        f"3. The script MUST compute the final answer into a variable and end with a print(answer) statement that prints ONLY the final answer on stdout. Do not leave the final answer unprinted.\n\n"
        f"Problem: {problem}\n"
    )
    
    t0 = time.perf_counter()
    resp1, fin1, tok1 = query_llm_with_meta(prompt1, max_tokens=768, enable_thinking=False)
    t1_lat = time.perf_counter() - t0
    code1, stage1 = extract_python_code_with_stage(resp1)
    
    exec1_exit = 0
    exec1_err = ""
    out1 = ""
    pred1 = ""
    t1_pass = False
    
    if code1:
        res1 = transport.execute(f"varb-t1-{idx}", "run_python", {"code": code1}, timeout_s=15)
        exec1_exit = res1.exit_code
        exec1_err = res1.stderr or ""
        out1 = res1.content or ""
        if exec1_exit == 0 and out1.strip():
            lines1 = [l.strip() for l in out1.strip().splitlines() if l.strip()]
            if lines1:
                pred1 = lines1[-1]
                t1_pass = compare_math_results(pred1, expected_ans, use_sympy=True)
    
    final_pass = t1_pass
    final_pred = pred1
    t2_triggered = False
    tok2 = 0
    
    # 2. Turn 2 Feedback if Turn 1 failed
    if not t1_pass:
        t2_triggered = True
        if exec1_exit != 0:
            err_trace = (exec1_err or out1).strip()
            prompt2 = (
                f"You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem produced an execution error in the sandbox:\n\n"
                f"Problem: {problem}\n\n"
                f"Your Initial Script:\n```python\n{code1}\n```\n\n"
                f"Execution Error / Traceback in Docker:\n{err_trace[:600]}\n\n"
                f"Please diagnose the error (e.g. fix syntax/import/attribute mistakes, or if SymPy's analytical solver fails, use numerical iteration or search). "
                f"Output ONLY the corrected complete Python script in a ```python ... ``` block (< 30 lines) that ends with print(...) printing ONLY the final answer."
            )
        else:
            prompt2 = (
                f"You are a competition mathematician and computer algebra expert. The Python script you wrote to solve the problem executed with exit code 0, but produced EMPTY stdout because it forgot to print the final answer:\n\n"
                f"Problem: {problem}\n\n"
                f"Your Initial Script:\n```python\n{code1}\n```\n\n"
                f"CRITICAL REQUIREMENT:\n"
                f"The script must compute the final exact answer and explicitly print it on stdout. Do not write rambling comments or derivations.\n"
                f"Output ONLY the corrected complete Python script in a ```python ... ``` block (< 30 lines) that ends with print(answer) printing ONLY the final answer."
            )
        
        t0_2 = time.perf_counter()
        resp2, fin2, tok2 = query_llm_with_meta(prompt2, max_tokens=768, enable_thinking=False)
        t2_lat = time.perf_counter() - t0_2
        code2, stage2 = extract_python_code_with_stage(resp2)
        
        if code2:
            res2 = transport.execute(f"varb-t2-{idx}", "run_python", {"code": code2}, timeout_s=15)
            if res2.exit_code == 0 and res2.content and res2.content.strip():
                lines2 = [l.strip() for l in res2.content.strip().splitlines() if l.strip()]
                if lines2:
                    final_pred = lines2[-1]
                    if final_pred.lower() in ("none", "null") and len(lines2) >= 2:
                        final_pred = lines2[-2]
                    final_pass = compare_math_results(final_pred, expected_ans, use_sympy=True)
        
        if not final_pred:
            final_pred = extract_math_answer_from_text(resp2)
            final_pass = compare_math_results(final_pred, expected_ans, use_sympy=True)
            
    status = "PASS" if final_pass else "FAIL"
    diff_str = ""
    if not baseline_passed and final_pass:
        gained.append(idx)
        diff_str = " [GAINED vs 319]"
    elif baseline_passed and not final_pass:
        lost.append(idx)
        diff_str = " [LOST vs 319]"
        
    t1_status = "T1_PASS" if t1_pass else ("T1_CRASH" if exec1_exit != 0 else ("T1_LEN" if fin1 == "length" else "T1_EMPTY"))
    print(f"Idx {idx:03d} | {status} ({t1_status}) | Pred: {final_pred[:20]} | Exp: {expected_ans[:20]} | T1_Tok: {tok1} | T2_Tok: {tok2}{diff_str}", flush=True)

print(f"\n--- Summary on {len(sample_indices)} Feedback Items ---")
print(f"Baseline passed: {sum(1 for i in sample_indices if b_data[i]['passed'])}/{len(sample_indices)}")
print(f"Variant B passed: {sum(1 for i in sample_indices if i not in lost and (b_data[i]['passed'] or i in gained))}/{len(sample_indices)}")
print(f"Gained: {len(gained)} {gained}")
print(f"Lost:   {len(lost)} {lost}")
print(f"Net:    {len(gained) - len(lost):+d}")
