import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_modern_2024_benchmarks import query_llm_with_meta, extract_python_code_with_stage, compare_math_results
from lucca.sandbox.rpc import DockerRPCTransport

transport = DockerRPCTransport(container_name="lucca-file-sandbox")
transport.ensure_container_running()

# 10 items that passed on Turn 1 in the 319 baseline
# Let's pick 10 passing indices from the 319 run:
baseline_file = Path("logs/test_reports/checkpoint_math500_v1.3-empty-feedback-heldout-400.json")
b_data = json.loads(baseline_file.read_text(encoding="utf-8"))

pass_turn1_items = [x for x in b_data if x["passed"] and not x.get("feedback_triggered")][:10]

print(f"Testing 10 Turn-1 passing items under Plan-then-Code (Variant B)...")
flips = []
for item in pass_turn1_items:
    idx = item["idx"]
    problem = item["problem"]
    expected_ans = item["expected_ans"]
    
    prompt = (
        f"You are a competition mathematician and computer algebra expert. Solve the following problem by writing "
        f"a concise Python script (< 30 lines) using SymPy or arithmetic that computes and prints ONLY the final exact answer.\n"
        f"STRICT RULES:\n"
        f"1. You may write a brief plan (at most 3 lines) before the code block. Then output the complete Python script in a ```python ... ``` block (< 30 lines).\n"
        f"2. Simplify all expressions completely before printing. Print only the exact mathematical value, without labels (e.g. print `5`, not `x = 5`).\n"
        f"3. The script MUST compute the final answer into a variable and end with a print(answer) statement that prints ONLY the final answer on stdout. Do not leave the final answer unprinted.\n\n"
        f"Problem: {problem}\n"
    )
    
    resp, finish, tokens = query_llm_with_meta(prompt, max_tokens=768, enable_thinking=False)
    code, stage = extract_python_code_with_stage(resp)
    
    pred_str = ""
    if code:
        res = transport.execute(f"test-b-{idx}", "run_python", {"code": code}, timeout_s=15)
        if res.exit_code == 0 and res.content and res.content.strip():
            lines = [l.strip() for l in res.content.strip().splitlines() if l.strip()]
            if lines:
                pred_str = lines[-1]
    
    is_pass = compare_math_results(pred_str, expected_ans, use_sympy=True)
    status = "PASS" if is_pass else "FAIL"
    print(f"Idx {idx:03d} | {status} | Pred: {pred_str[:20]} | Exp: {expected_ans[:20]} | Tok: {tokens} | Fin: {finish}", flush=True)
    if not is_pass:
        flips.append(idx)

print(f"\nResult on 10 previously passing Turn-1 items: {10 - len(flips)}/10 passed.")
if flips:
    print(f"REGRESSIONS on previously working items: {flips}")
