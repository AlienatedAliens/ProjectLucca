import json
import sys
sys.path.append(".")
from pathlib import Path
from scripts.run_concept_arc import (
    analyze_symbolic_invariants,
    query_llm,
    ABDUCTION_GBNF_GRAMMAR,
    AbductionPayload,
    PrimitiveDomain,
    resolve_scoped_primitives,
    summarize_grid_objects,
    column_heights,
    compute_grid_diff,
    extract_python_code,
    execute_transform_code,
    generate_visual_diff,
)

with open('data/benchmarks/ConceptARC/corpus/CompleteShape/CompleteShape1.json') as f:
    task = json.load(f)

train_pairs = task['train']
train_desc = ""
for idx, ex in enumerate(train_pairs):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

perceptual_manifest = ""
for idx, ex in enumerate(train_pairs):
    in_h, in_w = len(ex["input"]), len(ex["input"][0]) if ex["input"] else 0
    out_h, out_w = len(ex["output"]), len(ex["output"][0]) if ex["output"] else 0
    in_summary = summarize_grid_objects(ex["input"])
    out_summary = summarize_grid_objects(ex["output"])
    diff_summary = compute_grid_diff(ex["input"], ex["output"])
    in_col_h = column_heights(ex["input"])
    out_col_h = column_heights(ex["output"])
    shape_info = f"Input shape: {in_h}x{in_w} -> Output shape: {out_h}x{out_w}"
    perceptual_manifest += (
        f"Example {idx+1} {shape_info}\n"
        f"Example {idx+1} Input Objects: {in_summary}\n"
        f"Example {idx+1} Output Objects: {out_summary}\n"
        f"Example {idx+1} Column Heights: {in_col_h} -> Output: {out_col_h}\n"
        f"Example {idx+1} Diffs: {diff_summary}\n\n"
    )

invariants = analyze_symbolic_invariants(train_pairs)

abduction_prompt = (
    "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples, object structures, and coordinate diffs.\n"
    "Core Inductive Priors:\n"
    "- Color integers are arbitrary symbolic tokens. Never deduce rules based on color arithmetic.\n"
    "- The rule is governed by abstract spatial relations: relative positioning, motion toward boundary, shape identity/equality, enclosure, symmetry, order, or size.\n\n"
    f"{train_desc}"
    f"Perceptual Object Manifest & Diffs:\n{perceptual_manifest}"
    "Formulate an Operational Hypothesis and output a strict JSON object according to this schema:\n"
    "{\n"
    '  "primary_domain": "ORDERING" | "SYMMETRY" | "TOPOLOGY" | "EXTRACTION" | "MOTION" | "MORPHOLOGY" | "TALLY",\n'
    '  "secondary_domain": <domain_or_null>,\n'
    '  "selection_rule": "<which objects or regions are selected or filtered>",\n'
    '  "transformation_rule": "<what spatial transformation occurs>",\n'
    '  "color_rule": "<what output colors are assigned or preserved>"\n'
    "}\n"
    "Output ONLY valid JSON."
)

abduction_resp = query_llm(
    abduction_prompt,
    temperature=0.1,
    max_tokens=400,
    grammar=ABDUCTION_GBNF_GRAMMAR,
)
print("Abduction response:\n", abduction_resp)
d = json.loads(abduction_resp)
primary = PrimitiveDomain(d["primary_domain"])
sec_raw = d.get("secondary_domain")
secondary = PrimitiveDomain(sec_raw) if sec_raw and sec_raw != "null" else None
payload = AbductionPayload(primary, secondary, d.get("selection_rule", ""), d.get("transformation_rule", ""), d.get("color_rule", ""))

helpers_text, guidance_list = resolve_scoped_primitives(invariants, payload.primary_domain, payload.secondary_domain)
rules = [
    "- Color integers are arbitrary symbolic tokens. Never hardcode numeric color literals from training examples into the output! Always preserve existing cell colors or extract them dynamically.",
]
rules.extend(guidance_list)
rules.append("- CRITICAL: Write clean executable Python code with NO comments whatsoever. Do NOT write '# ...' comments. Start immediately with 'def transform(grid):'.")
rules_text = "\n".join(rules)

synthesis_prompt = (
    "Write a concise Python function `transform(grid: list[list[int]]) -> list[list[int]]` implementing this rule:\n"
    f"{payload.to_readable_hypothesis()}\n\n"
    f"Available helpers:\n{helpers_text}\n\n"
    f"Rules:\n{rules_text}\n\n"
    f"{train_desc}"
)

print("=== Synthesis Prompt Helpers ===\n", helpers_text)
print("=== Rules ===\n", rules_text)

for temp in [0.15, 0.35, 0.55]:
    resp = query_llm(synthesis_prompt, temperature=temp, max_tokens=1024)
    code = extract_python_code(resp)
    print(f"--- Temp {temp} Code ---\n{code}")
    for p_idx, pair in enumerate(train_pairs):
        try:
            pred = execute_transform_code(code, pair["input"])
            if pred == pair["output"]:
                print(f"  Example {p_idx+1}: PASS")
            else:
                print(f"  Example {p_idx+1}: FAIL (diff: {generate_visual_diff(pred, pair['output'])[:100]})")
        except Exception as e:
            print(f"  Example {p_idx+1}: EXCEPTION {e}")
