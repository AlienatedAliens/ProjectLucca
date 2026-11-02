import sys, json, httpx
from pathlib import Path
sys.path.insert(0, str(Path("scripts").resolve()))
from run_concept_arc import ABDUCTION_GBNF_GRAMMAR, SERVER_URL, query_llm

task = json.loads(Path('data/benchmarks/ConceptARC/corpus/AboveBelow/AboveBelow1.json').read_text())
train_pairs = task['train']
test_pair = task['test'][0]

train_desc = ""
for idx, ex in enumerate(train_pairs[:4]):
    train_desc += f"Example {idx+1}:\nInput:\n{ex['input']}\nOutput:\n{ex['output']}\n\n"

abduction_prompt = (
    "You are an expert ARC-AGI reasoning engine. Analyze this spatial grid transformation.\n"
    "Study the training examples and formulate the core operational rule connecting input to output.\n\n"
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

payload = {
    "messages": [{"role": "user", "content": abduction_prompt}],
    "temperature": 0.1,
    "max_tokens": 400,
    "grammar": ABDUCTION_GBNF_GRAMMAR,
}

r = httpx.post(SERVER_URL, json=payload, timeout=30)
print("With 4 examples Status code:", r.status_code)
if r.status_code == 200:
    print("Success content:", r.json()["choices"][0]["message"]["content"][:200])
else:
    print("Error text:", r.text)
