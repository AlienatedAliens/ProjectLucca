import json
import sys
sys.path.append(".")
from scripts.run_concept_arc import query_llm, ABDUCTION_GBNF_GRAMMAR

with open('data/benchmarks/ConceptARC/corpus/CompleteShape/CompleteShape1.json') as f:
    task = json.load(f)

train_desc = ""
for idx, ex in enumerate(task['train']):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

abduction_prompt = (
    "You are an expert ARC-AGI neurosymbolic reasoning engine. Analyze these spatial grid examples.\n"
    f"{train_desc}"
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
print("Abduction response:\n", resp)
