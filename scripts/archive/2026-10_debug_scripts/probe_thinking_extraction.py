#!/usr/bin/env python3
import json
import re
from pathlib import Path
import httpx

SERVER_URL = "http://127.0.0.1:8080/v1/chat/completions"

def query(prompt: str, enable_thinking: bool = True, max_tokens: int = 2048) -> tuple[str, str]:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6 if enable_thinking else 0.1,
        "top_p": 0.95 if enable_thinking else 1.0,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        return str(choice["message"]["content"] or ""), str(choice.get("finish_reason") or "stop")

def probe_nav():
    data = json.loads(Path("data/benchmarks/bbh_navigate.json").read_text(encoding="utf-8"))
    ex = data["examples"][0]
    prompt = (
        "Answer the following spatial navigation question.\n"
        "Output ONLY 'Yes' or 'No' as your final answer.\n\n"
        f"{ex['input']}"
    )
    content, finish = query(prompt, enable_thinking=True, max_tokens=2048)
    matches = list(re.finditer(r"\b(Yes|No)\b", content, re.IGNORECASE))
    pred = matches[-1].group(1).capitalize() if matches else None
    print(f"[Nav Probe] Target: {ex['target']} | Pred: {pred} | Finish: {finish}")
    print(f"Content tail: {content[-200:]!r}\n")

def probe_ded():
    data = json.loads(Path("data/benchmarks/bbh_logical_deduction_three_objects.json").read_text(encoding="utf-8"))
    ex = data["examples"][0]
    prompt = (
        "Solve this logic deduction problem. State your final answer as (A), (B), or (C).\n\n"
        f"{ex['input']}"
    )
    content, finish = query(prompt, enable_thinking=True, max_tokens=2048)
    matches = list(re.finditer(r"\(([A-C])\)", content))
    if not matches:
        matches = list(re.finditer(r"\b([A-C])\b", content))
    pred = f"({matches[-1].group(1).upper()})" if matches else None
    target_clean = str(ex["target"]).strip()
    target_letter = re.sub(r"[^A-Za-z]", "", target_clean).upper()
    print(f"[Ded Probe] Target: ({target_letter}) | Pred: {pred} | Finish: {finish}")
    print(f"Content tail: {content[-200:]!r}\n")

def probe_crux():
    crux_file = Path("data/benchmarks/cruxeval/data/cruxeval.jsonl")
    first_line = crux_file.read_text(encoding="utf-8").strip().split("\n")[0]
    ex = json.loads(first_line)
    code_body = str(ex["code"]).strip()
    input_val = str(ex["input"]).strip()
    target_out = str(ex["output"]).strip()
    prompt = (
        "You are a Python code interpreter. Determine the EXACT return value of `f` for the given input.\n"
        f"Code:\n```python\n{code_body}\n```\n\n"
        f"Input:\n{input_val}\n\n"
        "Output the return value in ```...``` format."
    )
    content, finish = query(prompt, enable_thinking=True, max_tokens=2048)
    match_code = re.findall(r"```(?:python)?\s*(.*?)\s*```", content, re.DOTALL)
    pred = match_code[-1].strip() if match_code else content.strip()
    print(f"[Crux Probe] Target: {target_out!r} | Pred: {pred!r} | Finish: {finish}")
    print(f"Content tail: {content[-200:]!r}\n")

if __name__ == "__main__":
    probe_nav()
    probe_ded()
    probe_crux()
