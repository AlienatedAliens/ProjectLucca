#!/usr/bin/env python3
"""
Project Lucca — MuSR Object Placements: ContainerWorld Diagnostic & Entity Extraction
Evaluates Theory-of-Mind / Spatial State Tracking across:
- Arm A: Direct Zero-Shot (T=0.0)
- Arm B: Extended Thinking (T=0.6)
- Arm C: Neurosymbolic ContainerWorld (LLM Event Extraction -> Deterministic State Tracker)

Tests whether decomposing narrative spatial reasoning into:
1. LLM structured event extraction (agent, action, item, location, observer)
2. Deterministic belief/world state machine in Python sandbox
rescues the 20-40% failure mode of bare autoregressive attention.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "musr_object_placements.json"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0


@dataclass
class OPDiagnosticResult:
    problem_id: str
    target_letter: str
    target_choice: str
    direct_prediction: str | None
    direct_correct: bool
    thinking_prediction: str | None
    thinking_correct: bool
    extracted_events_count: int
    extraction_syntax_ok: bool
    container_world_location: str | None
    container_world_prediction: str | None
    container_world_correct: bool
    container_world_ms: float


def query_llm(
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.0,
    enable_thinking: bool = False,
    response_format: dict[str, Any] | None = None,
) -> tuple[str, str, int]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert analytical logician. "
                "Analyze stories carefully, track physical object movements, and output your answer as instructed."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    payload: dict[str, Any] = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    if not enable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        res = client.post(SERVER_URL, json=payload)
        res.raise_for_status()
        data = res.json()
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason") or "unknown"
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        msg = choice["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        text = f"{content}\n[REASONING]\n{reasoning}" if (content.strip() and reasoning.strip()) else (content if content.strip() else reasoning)
        return text, finish_reason, completion_tokens


def extract_answer(text: str) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    m = re.findall(r"\b([A-E])\b|\(([A-E])\)", cleaned)
    if m:
        for tup in reversed(m):
            letter = tup[0] or tup[1]
            if letter:
                return f"({letter.upper()})"
    return None


class ContainerWorld:
    """
    Deterministic Theory-of-Mind & Spatial State Tracker.
    Tracks both physical ground-truth locations and per-agent belief states.
    """

    def __init__(self) -> None:
        self.world: dict[str, str] = {}  # item -> current location
        self.beliefs: dict[str, dict[str, str]] = {}  # agent -> item -> believed location

    def process_event(self, ev: dict[str, Any]) -> None:
        agent = str(ev.get("agent", "")).strip().lower()
        action = str(ev.get("action", "")).strip().lower()
        item = str(ev.get("item", "")).strip().lower()
        loc = str(ev.get("location") or ev.get("dst") or "").strip().lower()
        observers = [str(o).strip().lower() for o in ev.get("observed_by", [])]

        if not item or not loc:
            return

        # Physical world update
        if action in ("move", "place", "put", "relocate", "transfer"):
            self.world[item] = loc

        # Belief update: the acting agent always knows where they put it
        if agent:
            if agent not in self.beliefs:
                self.beliefs[agent] = {}
            self.beliefs[agent][item] = loc

        # Any explicit observers also update their belief
        for obs in observers:
            if obs not in self.beliefs:
                self.beliefs[obs] = {}
            self.beliefs[obs][item] = loc

    def query(self, target_agent: str | None, item: str) -> str | None:
        target_item = item.strip().lower()
        if target_agent:
            agent = target_agent.strip().lower()
            if agent in self.beliefs and target_item in self.beliefs[agent]:
                return self.beliefs[agent][target_item]
            # Match partial item name
            for k, v in self.beliefs.get(agent, {}).items():
                if target_item in k or k in target_item:
                    return v

        # Fall back to physical world state
        if target_item in self.world:
            return self.world[target_item]
        for k, v in self.world.items():
            if target_item in k or k in target_item:
                return v
        return None


def run_container_world_solver(
    story: str,
    question: str,
    choices: list[str],
) -> tuple[str | None, str | None, int, bool, float]:
    """
    Extracts events from narrative into JSON, runs ContainerWorld, and selects choice.
    Returns: (predicted_choice_letter, deduced_location, events_count, syntax_ok, elapsed_ms)
    """
    t0 = time.perf_counter()
    prompt = (
        "Extract the sequence of physical object placement and movement events from this story.\n"
        "Return ONLY a JSON object with key \"events\", containing a list of dictionaries with:\n"
        "- \"agent\": name of person moving or observing the object\n"
        "- \"action\": \"put\", \"move\", or \"observe\"\n"
        "- \"item\": item being moved\n"
        "- \"location\": destination location\n"
        "- \"observed_by\": list of other agents present who saw this\n\n"
        f"Story:\n{story}\n\n"
        "Format: {\"events\": [...]}"
    )

    raw, fin, tok = query_llm(
        prompt,
        max_tokens=2048,
        temperature=0.0,
        enable_thinking=False,
        response_format={"type": "json_object"},
    )
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    json_str = m.group(1) if m else raw.strip()

    events = []
    syntax_ok = False
    try:
        data = json.loads(json_str)
        syntax_ok = True
        if isinstance(data, dict):
            if "events" in data and isinstance(data["events"], list):
                events = data["events"]
            else:
                for v in data.values():
                    if isinstance(v, list):
                        events = v
                        break
        elif isinstance(data, list):
            events = data
    except Exception:
        # Fallback: attempt to salvage truncated JSON or extract valid object array
        try:
            m_arr = re.search(r"\[\s*\{.*?\}\s*\]", raw, re.DOTALL)
            if m_arr:
                events = json.loads(m_arr.group(0))
                syntax_ok = True
            else:
                # If cut off at end, close brackets
                last_brace = json_str.rfind("}")
                if last_brace != -1:
                    repaired = json_str[:last_brace+1] + "\n]}"
                    data = json.loads(repaired)
                    events = data.get("events", [])
                    syntax_ok = True
        except Exception:
            pass

    tracker = ContainerWorld()
    for ev in events:
        tracker.process_event(ev)

    # Determine target agent and item from question
    # e.g. "Which location is the most likely place Danny would look to find the earphones given the story?"
    m_agent = re.search(r"place\s+([A-Z][a-z]+)\s+would\s+look", question)
    target_agent = m_agent.group(1) if m_agent else None

    # Identify item
    target_item = "item"
    m_item = re.search(r"find\s+the\s+([a-zA-Z\s]+?)\s+given", question)
    if m_item:
        target_item = m_item.group(1).strip()
    else:
        for c in choices:
            for w in ("notebook", "earphones", "guitar", "keys", "phone", "book", "bag"):
                if w in story.lower():
                    target_item = w
                    break

    deduced_loc = tracker.query(target_agent, target_item)

    # Match deduced_loc against choices
    best_choice_letter = None
    letters = ["(A)", "(B)", "(C)", "(D)", "(E)"][:len(choices)]

    if deduced_loc:
        ded_lower = deduced_loc.lower()
        for idx, ch in enumerate(choices):
            ch_lower = ch.lower()
            if ch_lower in ded_lower or ded_lower in ch_lower:
                best_choice_letter = letters[idx]
                break

    # If no exact match, fallback to keyword overlap with choices
    if not best_choice_letter and deduced_loc:
        scores = [len(set(ch.lower().split()) & set(deduced_loc.lower().split())) for ch in choices]
        if max(scores) > 0:
            best_choice_letter = letters[scores.index(max(scores))]

    elapsed = (time.perf_counter() - t0) * 1000.0
    return best_choice_letter, deduced_loc, len(events), syntax_ok, elapsed


def run_diagnostic(limit: int = 10, seed: int = 42, model_tag: str = "12B") -> None:
    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: MuSR OBJECT PLACEMENTS (ContainerWorld Diagnostic) ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Model: {model_tag} | Limit: {limit} | Seed: {seed}\n", flush=True)

    raw_items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    rng = random.Random(seed)
    rng.shuffle(raw_items)
    items = raw_items[:limit]

    results: list[OPDiagnosticResult] = []

    for idx, it in enumerate(items, start=1):
        pid = f"OP_{idx:02d}"
        context = it["context"].strip()
        q_obj = it["questions"][0]
        question = q_obj["question"].strip()
        choices = q_obj["choices"]
        ans_idx = q_obj["answer"]

        letters = ["(A)", "(B)", "(C)", "(D)", "(E)"][:len(choices)]
        target_letter = letters[ans_idx]
        target_choice = choices[ans_idx]

        choices_str = "\n".join(f"{letters[i]} {choices[i]}" for i in range(len(choices)))
        bare_prompt = (
            f"Story:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Choices:\n{choices_str}\n\n"
            f"Conclude with your final answer as {', '.join(letters)}."
        )

        print(f"[{idx:02d}/{len(items):02d}] {pid}... ", end="", flush=True)

        # 1. Direct Zero-Shot
        t0 = time.perf_counter()
        try:
            d_out, _, _ = query_llm(bare_prompt, max_tokens=512, temperature=0.0, enable_thinking=False)
            d_pred = extract_answer(d_out)
            d_ok = (d_pred == target_letter)
        except Exception:
            d_pred, d_ok = None, False

        # 2. Extended Thinking
        t0 = time.perf_counter()
        try:
            th_out, _, _ = query_llm(bare_prompt, max_tokens=2048, temperature=0.6, enable_thinking=True)
            th_pred = extract_answer(th_out)
            th_ok = (th_pred == target_letter)
        except Exception:
            th_pred, th_ok = None, False

        # 3. Neurosymbolic ContainerWorld
        cw_pred, cw_loc, ev_count, syn_ok, cw_ms = run_container_world_solver(context, question, choices)
        cw_ok = (cw_pred == target_letter)

        r = OPDiagnosticResult(
            problem_id=pid,
            target_letter=target_letter,
            target_choice=target_choice,
            direct_prediction=d_pred,
            direct_correct=d_ok,
            thinking_prediction=th_pred,
            thinking_correct=th_ok,
            extracted_events_count=ev_count,
            extraction_syntax_ok=syn_ok,
            container_world_location=cw_loc,
            container_world_prediction=cw_pred,
            container_world_correct=cw_ok,
            container_world_ms=round(cw_ms, 1),
        )
        results.append(r)

        d_str = "PASS" if d_ok else "FAIL"
        th_str = "PASS" if th_ok else "FAIL"
        cw_str = "PASS" if cw_ok else ("SYN_ERR" if not syn_ok else "FAIL")
        print(f"Direct: {d_str} | Think: {th_str} | ContainerWorld: {cw_str} ({cw_pred} vs {target_letter})", flush=True)

    # Summary
    n = len(results)
    tot_d = sum(1 for r in results if r.direct_correct)
    tot_th = sum(1 for r in results if r.thinking_correct)
    tot_cw = sum(1 for r in results if r.container_world_correct)
    syn_passed = sum(1 for r in results if r.extraction_syntax_ok)

    print("\n" + "=" * 70)
    print("=== SUMMARY: MuSR OBJECT PLACEMENTS (ContainerWorld vs Bare) ===")
    print("=" * 70)
    print(f"Total Problems (n={n}):")
    print(f"  Direct Zero-Shot:    {tot_d:2d}/{n} ({tot_d/n*100:4.1f}%)")
    print(f"  Extended Thinking:   {tot_th:2d}/{n} ({tot_th/n*100:4.1f}%)")
    print(f"  ContainerWorld:      {tot_cw:2d}/{n} ({tot_cw/n*100:4.1f}%) [Syntax Validity: {syn_passed}/{n}]")
    print("=" * 70)

    out_dir = REPO_ROOT / "logs" / "test_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"musr_op_diagnostic_{model_tag}_{int(time.time())}.json"
    report_data = {
        "benchmark": "MuSR-Object-Placements-Diagnostic",
        "model_tag": model_tag,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_problems": n,
        "direct_pct": round(tot_d / n * 100, 1),
        "thinking_pct": round(tot_th / n * 100, 1),
        "container_world_pct": round(tot_cw / n * 100, 1),
        "extraction_syntax_pct": round(syn_passed / n * 100, 1),
        "results": [asdict(r) for r in results],
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\n[+] Saved diagnostic report to: {report_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MuSR Object Placements ContainerWorld Diagnostic")
    parser.add_argument("--limit", type=int, default=10, help="Problem count (default: 10)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed (default: 42)")
    parser.add_argument("--model-tag", type=str, default="12B", help="Model tier tag (default: 12B)")
    args = parser.parse_args()

    run_diagnostic(limit=args.limit, seed=args.seed, model_tag=args.model_tag)
