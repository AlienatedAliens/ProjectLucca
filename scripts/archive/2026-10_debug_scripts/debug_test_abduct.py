import json
import sys
sys.path.append('.')
from scripts.run_concept_arc import (
    query_llm,
    ABDUCTION_GBNF_GRAMMAR,
    analyze_symbolic_invariants,
    summarize_grid_objects,
    column_heights,
    compute_grid_diff,
)

with open('data/benchmarks/ConceptARC/corpus/CompleteShape/CompleteShape1.json') as f:
    task = json.load(f)

train_pairs = task['train']
invariants = analyze_symbolic_invariants(train_pairs)

priors = []
if invariants.is_shape_preserving:
    priors.append("- Grid Dimensions: Preserved across all examples (H_in == H_out, W_in == W_out).")
if invariants.has_high_symmetry:
    priors.append("- Discrete Symmetry: High bilateral reflection symmetry detected across axes (strong candidate for shape completion / reflection).")
priors_text = "\n".join(priors)

train_desc = ""
for idx, ex in enumerate(train_pairs):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

perceptual_manifest = ""
for idx, ex in enumerate(train_pairs):
    in_summary = summarize_grid_objects(ex["input"])
    out_summary = summarize_grid_objects(ex["output"])
    diff_summary = compute_grid_diff(ex["input"], ex["output"])
    perceptual_manifest += (
        f"Example {idx+1} Input Objects: {in_summary}\n"
        f"Example {idx+1} Output Objects: {out_summary}\n"
        f"Example {idx+1} Diffs: {diff_summary}\n\n"
    )

abduction_prompt = (
    "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples, object structures, and coordinate diffs.\n"
    "Core Inductive Priors:\n"
    "- Color integers are arbitrary symbolic tokens. Never deduce rules based on color arithmetic.\n"
    "- The rule is governed by abstract spatial relations: relative positioning, motion toward boundary, shape identity/equality, enclosure, symmetry, order, or size.\n\n"
    f"Symbolic Invariants (Computed from Training Pairs):\n{priors_text}\n\n"
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

resp = query_llm(abduction_prompt, temperature=0.1, max_tokens=400, grammar=ABDUCTION_GBNF_GRAMMAR)
print("ABDUCTION:\n", resp)

from scripts.run_concept_arc import (
    AbductionPayload,
    PrimitiveDomain,
    resolve_scoped_primitives,
    extract_python_code,
    execute_transform_code,
)

d = json.loads(resp)
payload = AbductionPayload(PrimitiveDomain(d["primary_domain"]), PrimitiveDomain(d["secondary_domain"]) if d.get("secondary_domain") else None, d["selection_rule"], d["transformation_rule"], d["color_rule"])
helpers_text, guidance = resolve_scoped_primitives(invariants, payload.primary_domain, payload.secondary_domain)
rules = [
    "- Color integers are arbitrary symbolic tokens. Never hardcode numeric color literals from training examples into the output! Always preserve existing cell colors or extract them dynamically.",
]
rules.extend(guidance)
rules.append("- CRITICAL: Write clean executable Python code with NO comments whatsoever. Do NOT write '# ...' comments. Start immediately with 'def transform(grid):'.")
rules_text = "\n".join(rules)

synthesis_prompt = (
    "Write a concise Python function `transform(grid: list[list[int]]) -> list[list[int]]` implementing this rule:\n"
    f"{payload.to_readable_hypothesis()}\n\n"
    f"Available helpers:\n{helpers_text}\n\n"
    f"Rules:\n{rules_text}\n\n"
    f"{train_desc}"
)

print("=== PROMPT RULES ===\n", rules_text)

for temp in [0.15, 0.35, 0.55]:
    c_resp = query_llm(synthesis_prompt, temperature=temp, max_tokens=1024)
    code = extract_python_code(c_resp)
    print(f"=== Temp {temp} Code ===\n", code)
    for p_idx, pair in enumerate(train_pairs):
        try:
            pred = execute_transform_code(code, pair["input"])
            print(f"Ex {p_idx+1}:", "PASS" if pred == pair["output"] else "FAIL")
        except Exception as e:
            print(f"Ex {p_idx+1}: ERROR", e)

