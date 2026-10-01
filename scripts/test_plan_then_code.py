import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_modern_2024_benchmarks import query_llm_with_meta, extract_python_code_with_stage
from lucca.sandbox.rpc import DockerRPCTransport

cache_file = Path("logs/test_reports/turn1_cache_108.json")
c = json.loads(cache_file.read_text(encoding="utf-8"))

test_indices = [55, 78, 140, 168]

# Variant B Prompt Formulation:
# "Change the prompt to allow at most a 3-line plan before the code block, then the script. Remove the 'no comments' wording."
for idx in test_indices:
    item = c[str(idx)]
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

    t0 = time.perf_counter()
    resp, finish, tokens = query_llm_with_meta(prompt, max_tokens=768, enable_thinking=False)
    lat = time.perf_counter() - t0
    code, stage = extract_python_code_with_stage(resp)
    
    print(f"\n================ Idx {idx} ================")
    print(f"Finish: {finish} | Tokens: {tokens} | Latency: {lat:.2f}s | Stage: {stage}")
    print("--- Full Raw Response ---")
    print(resp[:400])
    if len(resp) > 400:
        print("...\n" + resp[-150:])
    print("--- Extracted Code Snippet ---")
    print("\n".join(code.splitlines()[:10]))
    print(f"Code line count: {len(code.splitlines())}")
