#!/usr/bin/env python3
"""
Project Lucca — MuSR 3-Domain Compound Neurosymbolic Benchmark Runner (v1.38)
Evaluates complex multistep deduction across all 3 MuSR domains (N=30):
1. Murder Mystery (10 problems): Suspect Means/Motive/Opportunity structured deduction
2. Team Allocation (10 problems): Schema-Guided Python Sandbox Utility Optimization (Peer Review Q3)
3. Object Placements (10 problems): ContainerWorld Discrete Belief Simulator (v1.38 initial_world)

Compares:
- Arm A: Direct Non-Thinking (T=0.0)
- Arm B: Native Extended Thinking (T=0.6)
- Arm C: Lucca v1.38 Compound Neurosymbolic Engine
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.sandbox.container_world import ContainerWorld
from lucca.sandbox.preflight import extract_python_code
from lucca.sandbox.rpc import DockerRPCTransport

DATA_DIR: Final[Path] = REPO_ROOT / "data" / "benchmarks"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0


@dataclass
class MuSRCompoundResult:
    problem_id: str
    domain: str
    target_letter: str
    direct_pred: str | None
    direct_ok: bool
    thinking_pred: str | None
    thinking_ok: bool
    compound_pred: str | None
    compound_ok: bool
    compound_lobe: str
    compound_latency_s: float


def query_llm_messages(
    messages: list[dict[str, str]],
    max_tokens: int = 512,
    temperature: float = 0.0,
    enable_thinking: bool = False,
) -> tuple[str, str, int]:
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
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
        if content.strip() and reasoning.strip():
            text = f"{content}\n[REASONING]\n{reasoning}"
        else:
            text = content if content.strip() else reasoning
        return text, finish_reason, completion_tokens


def extract_answer(text: str) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    m = re.search(
        r"(?:answer|choice|option|conclusion)(?:\s+is)?[:\s]*\(?([A-E])\)?",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return f"({m.group(1).upper()})"

    m_tail = re.search(r"\(([A-E])\)\s*$", cleaned)
    if m_tail:
        return f"({m_tail.group(1).upper()})"

    matches = re.findall(r"\(([A-E])\)", cleaned)
    if matches:
        return f"({matches[-1].upper()})"

    matches_bare = re.findall(r"\b([A-E])\b", cleaned)
    if matches_bare:
        return f"({matches_bare[-1].upper()})"
    return None


def match_choice_fuzzy(sim_ans: str, choices: list[str], letters: list[str]) -> str | None:
    s_clean = sim_ans.strip().lower()
    if not s_clean or s_clean == "unknown":
        return None
    for idx, c in enumerate(choices):
        if c.strip().lower() == s_clean:
            return letters[idx]
    for idx, c in enumerate(choices):
        c_clean = c.strip().lower()
        if c_clean in s_clean or s_clean in c_clean:
            return letters[idx]
    s_words = {w for w in re.findall(r"[a-z0-9]+", s_clean) if w not in {"the", "a", "an", "in", "on", "at", "of"}}
    best_idx = -1
    best_score = 0.0
    for idx, c in enumerate(choices):
        c_words = {w for w in re.findall(r"[a-z0-9]+", c.lower()) if w not in {"the", "a", "an", "in", "on", "at", "of"}}
        if not c_words:
            continue
        overlap = len(s_words & c_words) / max(len(s_words), len(c_words))
        if overlap > best_score:
            best_score = overlap
            best_idx = idx
    if best_idx >= 0 and best_score >= 0.5:
        return letters[best_idx]
    return None


def solve_object_placement_compound(
    context: str,
    question: str,
    choices: list[str],
    letters: list[str],
    thinking_fallback_pred: str | None,
) -> tuple[str | None, str]:
    sys_prompt = (
        "You are an Event Log Extractor for a Discrete Epistemic Belief Simulator (ContainerWorld).\n"
        "Read the narrative and extract a JSON object with:\n"
        "1. 'events': chronological list of object placement/movement events.\n"
        "   - First extract ALL initial starting locations from the opening paragraph using:\n"
        "     {\"action\": \"initial\", \"item\": \"<item_name>\", \"to_loc\": \"<starting_location>\"}\n"
        "   - Then extract every subsequent move/placement event using:\n"
        "     {\"action\": \"move\", \"actor\": \"<person>\", \"item\": \"<item_name>\", \"to_loc\": \"<exact_choice_location>\", \"observed_by\": [\"<person1>\", ...]}\n"
        "   - CRITICAL LINE-OF-SIGHT RULE: Include an agent in 'observed_by' ONLY IF they are in the exact same room/area, watching, or explicitly told about the move. If they are in another room, busy elsewhere, asleep, or distracted, DO NOT include them in 'observed_by'.\n"
        "   - Map 'to_loc' to the exact phrasing in the multiple-choice options whenever possible.\n"
        "2. 'query_agent': the name of the person whose belief is asked about in the question.\n"
        "3. 'query_item': the item asked about in the question.\n"
        "Output ONLY valid JSON inside ```json ... ```."
    )
    user_p = (
        f"Story:\n{context}\n\n"
        f"Question: {question}\n"
        f"Candidate Location Choices: {json.dumps(choices)}\n\n"
        "Extract the JSON event log:"
    )
    try:
        raw, _, _ = query_llm_messages(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_p}],
            max_tokens=1024,
            temperature=0.0,
            enable_thinking=False,
        )
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        j_str = m.group(1) if m else raw[raw.find("{") : raw.rfind("}") + 1]
        parsed = json.loads(j_str)
        cw = ContainerWorld()
        sim_res = cw.simulate(
            events=parsed.get("events", []),
            query_agent=str(parsed.get("query_agent", "")),
            query_item=str(parsed.get("query_item", "")),
        )
        believed = str(sim_res.get("believed_location", "unknown"))
        matched = match_choice_fuzzy(believed, choices, letters)
        if matched:
            return matched, "ContainerWorld_v138"
    except Exception:
        pass
    return thinking_fallback_pred, "ContainerWorld_Fallback_Thinking"


def solve_team_allocation_compound(
    context: str,
    question: str,
    choices: list[str],
    letters: list[str],
    rpc: DockerRPCTransport,
    thinking_fallback_pred: str | None,
) -> tuple[str | None, str]:
    """
    Peer Review Q3 Schema-Guided Formalization for MuSR Team Allocation:
    1. Extracts each person's skill rating (1=bad/poor, 2=okay/moderate, 3=good/great)
       on Task 1 and Task 2, plus pairwise cooperation rating (1=bad/conflict, 2=okay/good, 3=great)
       into an executable Python script that scores choices (A), (B), (C).
    """
    choices_block = "\n".join(f"{letters[i]} {choices[i]}" for i in range(len(choices)))
    sys_prompt = (
        "You are a Neurosymbolic Optimization Compiler solving MuSR Team Allocation problems.\n"
        "In every story, 3 people are assigned to 2 tasks: one person works solo on Task 1, and two people work together as a pair on Task 2.\n"
        "Follow this exact scoring schema:\n"
        "- Skill score for a person on a task: 1 = bad / poor / afraid / allergic / unqualified; 2 = okay / moderate / decent; 3 = good / great / enthusiastic / experienced.\n"
        "- Cooperation score for the two people assigned together on Task 2: 1 = bad / conflict / grudge / avoids / tension; 2 = okay / friendly / gets along well; 3 = great.\n"
        "- Total Score of an allocation = skill(solo_person, Task1) + skill(pair_person1, Task2) + skill(pair_person2, Task2) + cooperation(pair_person1, pair_person2).\n"
        "Write a short Python script that defines the extracted integer scores (1, 2, or 3), computes the Total Score for each choice (A), (B), (C), and prints ONLY the winning choice letter like (A), (B), or (C).\n"
        "Output ONLY ```python ... ```."
    )
    user_p = (
        f"Story:\n{context}\n\n"
        f"Question: {question}\n"
        f"Choices:\n{choices_block}\n\n"
        "Write the Python scoring script:"
    )
    try:
        raw, _, _ = query_llm_messages(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_p}],
            max_tokens=768,
            temperature=0.0,
            enable_thinking=False,
        )
        code = extract_python_code(raw)
        if code:
            res = rpc.execute(
                call_id=f"musr-ta-{time.time_ns()}",
                tool="run_python",
                args={"code": code},
                timeout_s=10.0,
            )
            if res.ok and res.content:
                pred = extract_answer(str(res.content).strip())
                if pred in letters:
                    return pred, "Schema_Python_Optimizer"
    except Exception:
        pass
    return thinking_fallback_pred, "Optimizer_Fallback_Thinking"


def solve_murder_mystery_compound(
    context: str,
    question: str,
    choices: list[str],
    letters: list[str],
) -> tuple[str | None, str]:
    choices_block = "\n".join(f"{letters[i]} {choices[i]}" for i in range(len(choices)))
    sys_prompt = (
        "You are an expert forensic detective. To identify the murderer accurately:\n"
        "For each suspect in the choices, check all three requirements from the story:\n"
        "1. MEANS (access to the murder weapon or knowledge to use it)\n"
        "2. MOTIVE (financial, personal, revenge, or secret to protect)\n"
        "3. OPPORTUNITY (lack of verified alibi at the time/place of the crime)\n"
        "The true killer is the ONLY suspect who satisfies all three (or has the most suspicious contradicted alibi). "
        "State your final answer clearly as (A) or (B)."
    )
    user_p = (
        f"Story:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Choices:\n{choices_block}\n\n"
        f"Analyze Means, Motive, and Opportunity for each suspect and conclude with {', '.join(letters)}."
    )
    try:
        out, _, _ = query_llm_messages(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_p}],
            max_tokens=2048,
            temperature=0.4,
            enable_thinking=True,
        )
        pred = extract_answer(out)
        if pred in letters:
            return pred, "Structured_MMO_Thinking"
    except Exception:
        pass
    return None, "MMO_Failed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-tag", type=str, default="12B_V138")
    args = parser.parse_args()

    domains = [
        ("murder_mystery", DATA_DIR / "musr_murder_mystery.json"),
        ("team_allocation", DATA_DIR / "musr_team_allocation.json"),
        ("object_placements", DATA_DIR / "musr_object_placements.json"),
    ]

    rpc = DockerRPCTransport(container_name="lucca-file-sandbox")
    if not rpc.is_container_running():
        rpc.ensure_container_running()

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: MuSR 3-DOMAIN COMPOUND NEUROSYMBOLIC BENCHMARK ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()} | Model: {args.model_tag} | N={args.limit*3}\n", flush=True)

    results: list[MuSRCompoundResult] = []

    for dom_name, path in domains:
        print(f"--- [Domain: {dom_name} (n={args.limit})] ---", flush=True)
        raw_items = json.loads(path.read_text(encoding="utf-8"))
        rng = random.Random(args.seed)
        rng.shuffle(raw_items)
        items = raw_items[: args.limit]

        for idx, it in enumerate(items, start=1):
            pid = f"{dom_name}_{idx:02d}"
            context = it["context"].strip()
            q_obj = it["questions"][0]
            question = q_obj["question"].strip()
            choices = q_obj["choices"]
            ans_idx = q_obj["answer"]

            letters = ["(A)", "(B)", "(C)", "(D)", "(E)"][: len(choices)]
            target_letter = letters[ans_idx]
            choices_str = "\n".join(f"{letters[i]} {choices[i]}" for i in range(len(choices)))
            base_prompt = (
                f"Story:\n{context}\n\n"
                f"Question: {question}\n\n"
                f"Choices:\n{choices_str}\n\n"
                f"Conclude with your final answer as {', '.join(letters)}."
            )
            base_msgs = [
                {
                    "role": "system",
                    "content": "You are an expert logical detective and analytical reasoner. Read the story carefully, analyze all clues, and state your final answer as (A), (B), (C), or (D).",
                },
                {"role": "user", "content": base_prompt},
            ]

            print(f"[{idx:02d}/{len(items):02d}] {pid}... ", end="", flush=True)

            # 1. Direct
            try:
                d_out, _, _ = query_llm_messages(base_msgs, max_tokens=512, temperature=0.0, enable_thinking=False)
                d_pred = extract_answer(d_out)
                d_ok = d_pred == target_letter
            except Exception:
                d_pred, d_ok = None, False

            # 2. Thinking
            try:
                th_out, _, _ = query_llm_messages(base_msgs, max_tokens=2048, temperature=0.6, enable_thinking=True)
                th_pred = extract_answer(th_out)
                th_ok = th_pred == target_letter
            except Exception:
                th_pred, th_ok = None, False

            # 3. Compound Neurosymbolic
            t_comp = time.perf_counter()
            if dom_name == "object_placements":
                c_pred, lobe = solve_object_placement_compound(context, question, choices, letters, th_pred)
            elif dom_name == "team_allocation":
                c_pred, lobe = solve_team_allocation_compound(context, question, choices, letters, rpc, th_pred)
            else:
                c_pred, lobe = solve_murder_mystery_compound(context, question, choices, letters)
                if not c_pred:
                    c_pred = th_pred
            c_sec = time.perf_counter() - t_comp
            c_ok = c_pred == target_letter

            results.append(
                MuSRCompoundResult(
                    problem_id=pid,
                    domain=dom_name,
                    target_letter=target_letter,
                    direct_pred=d_pred,
                    direct_ok=d_ok,
                    thinking_pred=th_pred,
                    thinking_ok=th_ok,
                    compound_pred=c_pred,
                    compound_ok=c_ok,
                    compound_lobe=lobe,
                    compound_latency_s=round(c_sec, 2),
                )
            )
            print(
                f"Direct={'PASS' if d_ok else 'FAIL'}({d_pred}) | "
                f"Think={'PASS' if th_ok else 'FAIL'}({th_pred}) | "
                f"Compound={'PASS' if c_ok else 'FAIL'}({c_pred} via {lobe}) [GT:{target_letter}]",
                flush=True,
            )

    print("\n==========================================================================", flush=True)
    print("MuSR 3-DOMAIN COMPOUND BENCHMARK SUMMARY", flush=True)
    print("==========================================================================", flush=True)
    for dom_name, _ in domains:
        dom_r = [r for r in results if r.domain == dom_name]
        d_p = sum(1 for r in dom_r if r.direct_ok) / len(dom_r) * 100.0
        t_p = sum(1 for r in dom_r if r.thinking_ok) / len(dom_r) * 100.0
        c_p = sum(1 for r in dom_r if r.compound_ok) / len(dom_r) * 100.0
        print(f"Domain [{dom_name:<18}] (n={len(dom_r)}): Direct={d_p:5.1f}% | Thinking={t_p:5.1f}% | Compound={c_p:5.1f}%", flush=True)

    n = len(results)
    tot_d = sum(1 for r in results if r.direct_ok)
    tot_t = sum(1 for r in results if r.thinking_ok)
    tot_c = sum(1 for r in results if r.compound_ok)
    print("-" * 74, flush=True)
    print(
        f"OVERALL (N={n}): Direct={tot_d}/{n} ({tot_d/n*100:.1f}%) | "
        f"Thinking={tot_t}/{n} ({tot_t/n*100:.1f}%) | "
        f"Compound={tot_c}/{n} ({tot_c/n*100:.1f}%)",
        flush=True,
    )
    print("==========================================================================", flush=True)

    out_file = REPO_ROOT / "logs" / "test_reports" / f"musr_compound_benchmark_{args.model_tag}_{int(time.time())}.json"
    out_file.write_text(
        json.dumps(
            {
                "benchmark": "MuSR_3Domain_Compound_Neurosymbolic",
                "model_tag": args.model_tag,
                "evaluated_at": datetime.now(UTC).isoformat(),
                "total_problems": n,
                "direct_passed": tot_d,
                "direct_pct": round(tot_d / n * 100.0, 1),
                "thinking_passed": tot_t,
                "thinking_pct": round(tot_t / n * 100.0, 1),
                "compound_passed": tot_c,
                "compound_pct": round(tot_c / n * 100.0, 1),
                "results": [asdict(r) for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[+] Report written to: {out_file}", flush=True)


if __name__ == "__main__":
    main()
