import json
import time
import urllib.request
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.sandbox.rpc import DockerRPCTransport
from scripts.run_modern_2024_benchmarks import (
    get_math500_dataset,
    extract_math500_ground_truth,
    extract_python_code_with_stage,
    query_llm_with_meta,
)

REPORTS_DIR = Path("logs/test_reports")
p_319 = REPORTS_DIR / "checkpoint_math500_v1.3-empty-feedback-heldout-400.json"
data_319 = json.loads(p_319.read_text(encoding="utf-8"))

fb_319_map = {d["idx"]: d for d in data_319 if d.get("feedback_triggered")}
fb_indices = sorted(list(fb_319_map.keys()))
print(f"Loaded {len(fb_indices)} feedback items from 319 run.")

all_data = get_math500_dataset()
dev_dataset = all_data[100:500]

print("Initializing DockerRPCTransport...")
transport = DockerRPCTransport(container_name="lucca-file-sandbox")
transport.ensure_container_running()

turn1_cache_file = REPORTS_DIR / "turn1_cache_108.json"
turn1_cache = {}
if turn1_cache_file.exists():
    try:
        turn1_cache = json.loads(turn1_cache_file.read_text(encoding="utf-8"))
        print(f"Loaded {len(turn1_cache)} existing items from {turn1_cache_file.name}")
    except Exception:
        turn1_cache = {}

matches_63 = 0
diffs_63 = 0
differing_items = []

for pos, curr_idx in enumerate(fb_indices, 1):
    str_idx = str(curr_idx)
    item = dev_dataset[curr_idx - 1]
    problem = item["problem"]
    expected_ans = extract_math500_ground_truth(item["solution"])
    
    # Check if already cached
    if str_idx in turn1_cache:
        t1_rec = turn1_cache[str_idx]
    else:
        prompt = (
            f"You are a competition mathematician and computer algebra expert. Solve the following problem by writing "
            f"a concise Python script (< 30 lines) using SymPy or arithmetic that computes and prints ONLY the final exact answer.\n"
            f"STRICT RULES:\n"
            f"1. Output ONLY a ```python ... ``` block. DO NOT write explanations, prose, or rambling comments.\n"
            f"2. Simplify all expressions completely before printing. Print only the exact mathematical value, without labels (e.g. print `5`, not `x = 5`).\n"
            f"3. The script MUST compute the final answer into a variable and end with a print(answer) statement that prints ONLY the final answer on stdout. Do not leave the final answer unprinted.\n\n"
            f"Problem: {problem}\n"
        )
        t0 = time.perf_counter()
        resp, finish_reason, comp_tokens = query_llm_with_meta(prompt=prompt, max_tokens=768, enable_thinking=False)
        t_llm = time.perf_counter() - t0
        
        code, stage = extract_python_code_with_stage(resp)
        exec_res_exit = 0
        exec_res_stderr = ""
        math_out = ""
        
        if code:
            exec_res = transport.execute(f"turn1-{curr_idx}", "run_python", {"code": code}, timeout_s=20)
            exec_res_exit = exec_res.exit_code
            exec_res_stderr = exec_res.stderr or ""
            math_out = exec_res.content or ""
            UNUSABLE_STDOUT_PATTERNS = ("<built-in", "<function", "<class", "<module", "object at 0x")
            if any(pat in math_out for pat in UNUSABLE_STDOUT_PATTERNS):
                math_out = ""
        
        t1_rec = {
            "idx": curr_idx,
            "item_id": f"dev-{curr_idx}",
            "subject": item.get("subject", "math"),
            "level": item.get("level", 0),
            "problem": problem,
            "expected_ans": expected_ans,
            "turn1_prompt": prompt,
            "turn1_response": resp,
            "turn1_code": code,
            "turn1_stage": stage,
            "turn1_exit_code": exec_res_exit,
            "turn1_stderr": exec_res_stderr,
            "turn1_stdout": math_out,
            "turn1_finish_reason": finish_reason,
            "turn1_completion_tokens": comp_tokens,
            "turn1_latency_s": round(t_llm, 3),
            "turn1_needs_feedback": (exec_res_exit != 0 or not math_out.strip()),
        }
        turn1_cache[str_idx] = t1_rec
        turn1_cache_file.write_text(json.dumps(turn1_cache, indent=2), encoding="utf-8")
    
    # Diff against 319 stored code if this was one of the 63 failed items
    ref_319 = fb_319_map[curr_idx]
    if not ref_319.get("passed"):
        stored_code = ref_319.get("generated_code", "")
        current_code = t1_rec["turn1_code"]
        if current_code.strip() == stored_code.strip():
            matches_63 += 1
        else:
            diffs_63 += 1
            differing_items.append((curr_idx, len(current_code), len(stored_code)))
    
    print(f"[{pos:03d}/108] Idx {curr_idx:03d} | Needs FB: {t1_rec['turn1_needs_feedback']} | Exit: {t1_rec['turn1_exit_code']} | Lat: {t1_rec['turn1_latency_s']:.2f}s", flush=True)

print(f"\n--- Turn 1 Generation & Verification Summary ---")
print(f"Total processed: {len(turn1_cache)}/108")
print(f"Items needing feedback: {sum(1 for r in turn1_cache.values() if r.get('turn1_needs_feedback'))}/108")
print(f"Comparison on the 63 failed items (where Turn 1 code was saved):")
print(f"  Exact matches: {matches_63}")
print(f"  Differences: {diffs_63}")
if differing_items:
    print(f"  Differing items (idx, len_current, len_stored): {differing_items}")
