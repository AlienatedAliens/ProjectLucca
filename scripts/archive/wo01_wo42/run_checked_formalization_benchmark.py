#!/usr/bin/env python3
"""
Project Lucca — Expanded Checked Formalization & Shared Workspace Benchmark (N=10)
Addresses Peer-Review Directive Q1.2 & Q3:
  "Have two independently produced formulations (algebraic and brute-force on small cases)
   that must agree before an answer is accepted. Disagreement triggers more sampling.
   This addresses your Class 2 failures directly."

Compares 3 Arms across 10 competition math & hybrid neurosymbolic problems:
- Arm A: Bare Direct LLM (Mental calculation, T=0.0)
- Arm B: Single-Formulation Greedy Python Sandbox (synthesize_and_repair, N=1)
- Arm C: Checked Formalization (synthesize_checked_formalization: Symbolic + Brute-Force Cross-Check + Parallel Escalation)
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import time
from typing import Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.reasoning.cegis_python import PythonCEGISEngine

SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
REPORT_DIR: Final[Path] = REPO_ROOT / "logs" / "test_reports"


@dataclass
class CheckedFormalizationTask:
    task_id: str
    category: str
    prompt: str
    expected: str


@dataclass
class CheckedFormalizationResult:
    task_id: str
    category: str
    expected: str
    bare_pred: str
    bare_ok: bool
    single_pred: str
    single_ok: bool
    checked_pred: str
    checked_ok: bool
    checked_method: str
    checked_turns: int
    checked_ms: float


def build_tasks() -> list[CheckedFormalizationTask]:
    return [
        CheckedFormalizationTask(
            task_id="CF_MATH_01",
            category="Modular_Congruence",
            prompt="Find the smallest positive integer n such that n % 3 == 2, n % 5 == 3, and n % 7 == 2. Print ONLY the integer.",
            expected="23",
        ),
        CheckedFormalizationTask(
            task_id="CF_MATH_02",
            category="Divisor_Number_Theory",
            prompt="How many positive integers less than or equal to 1000 are multiples of 3 or 5, but NOT multiples of 15? Print ONLY the integer.",
            expected="401",
        ),
        CheckedFormalizationTask(
            task_id="CF_MATH_03",
            category="Combinatorics_Digits",
            prompt="Find the sum of all 3-digit positive integers (from 100 to 999 inclusive) whose digits sum to 10. Print ONLY the integer.",
            expected="22815",
        ),
        CheckedFormalizationTask(
            task_id="CF_MATH_04",
            category="Modular_Exponentiation",
            prompt="What is the remainder when 7^2026 is divided by 100? Print ONLY the integer.",
            expected="49",
        ),
        CheckedFormalizationTask(
            task_id="CF_MATH_05",
            category="Diophantine_Counting",
            prompt="How many ordered pairs of positive integers (x, y) satisfy 3*x + 5*y = 100? Print ONLY the integer.",
            expected="6",
        ),
        CheckedFormalizationTask(
            task_id="CF_MATH_06",
            category="Euler_Totient_Coprime",
            prompt="How many positive integers k <= 360 are relatively prime to 360 (i.e., gcd(k, 360) == 1)? Print ONLY the integer.",
            expected="96",
        ),
        CheckedFormalizationTask(
            task_id="CF_MATH_07",
            category="Prime_Gap_Sum",
            prompt="Find the sum of all prime numbers p such that 50 <= p <= 150. Print ONLY the integer.",
            expected="1948",
        ),
        CheckedFormalizationTask(
            task_id="CF_MATH_08",
            category="Factorial_Trailing_Zeros",
            prompt="How many trailing zeros does 2026! (2026 factorial) have in base 10? Print ONLY the integer.",
            expected="505",
        ),
        CheckedFormalizationTask(
            task_id="CF_HYBRID_09",
            category="ContainerWorld_SymPy",
            prompt=(
                "Use `from container_world import ContainerWorld` and `import sympy` in one Python script:\n"
                "1. Create `cw = ContainerWorld()`.\n"
                "2. Alice places 'ledger' in 'drawer_5' (`observed_by=['Alice', 'Bob']`).\n"
                "3. While Bob is away, Alice moves 'ledger' to 'drawer_12' (`observed_by=['Alice']`).\n"
                "4. Query where Bob believes 'ledger' is (`cw.query('Bob', 'ledger')`), extract the integer drawer number N from that location string, and print the N-th prime number using `sympy.prime(N)`."
            ),
            expected="11",
        ),
        CheckedFormalizationTask(
            task_id="CF_HYBRID_10",
            category="Z3_SymPy_Composition",
            prompt=(
                "Use `import z3` and `import sympy` in one Python script:\n"
                "Find the unique integers x > 0 and y > 0 such that x + y == 25 and 2*x - y == 11. "
                "Then compute and print `sympy.totient(x * y)` (Euler's totient function of x*y). Print ONLY the integer."
            ),
            expected="48",
        ),
    ]


def query_bare_llm(prompt: str) -> str:
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "Solve the problem mentally and output ONLY the final integer answer at the very end.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 384,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(SERVER_URL, json=payload)
            resp.raise_for_status()
            text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
            nums = re.findall(r"-?\d+", text)
            return nums[-1] if nums else ""
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-tag", type=str, default="12B_V138")
    args = parser.parse_args()

    tasks = build_tasks()
    engine = PythonCEGISEngine(
        container_name="lucca-file-sandbox",
        timeout_s=15.0,
        max_turns=3,
        num_candidates=3,
        server_url=SERVER_URL,
    )

    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: CHECKED FORMALIZATION & HYBRID BENCHMARK (N=10) ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()} | Model: {args.model_tag}\n", flush=True)

    results: list[CheckedFormalizationResult] = []
    for idx, t in enumerate(tasks, start=1):
        print(f"[{idx:02d}/{len(tasks):02d}] {t.task_id} ({t.category}, GT={t.expected})... ", end="", flush=True)

        # Arm A: Bare Direct LLM
        b_pred = query_bare_llm(t.prompt)
        b_ok = b_pred == t.expected

        # Arm B: Single-Formulation Greedy Python
        s_res = engine.synthesize_and_repair(
            task_prompt=t.prompt,
            system_prompt="Write a concise Python script that computes and prints ONLY the final integer answer inside ```python ... ```.",
            output_pattern=r"(-?\d+)",
            temperature=0.0,
            max_tokens=512,
        )
        s_pred = (s_res.predicted_output or "").strip()
        s_ok = s_pred == t.expected

        # Arm C: Checked Formalization (Symbolic + Brute-Force Agreement + Escalation)
        c_res = engine.synthesize_checked_formalization(
            task_prompt=t.prompt,
            output_pattern=r"(-?\d+)",
        )
        c_pred = (c_res.predicted_output or "").strip()
        c_ok = c_pred == t.expected

        results.append(
            CheckedFormalizationResult(
                task_id=t.task_id,
                category=t.category,
                expected=t.expected,
                bare_pred=b_pred,
                bare_ok=b_ok,
                single_pred=s_pred,
                single_ok=s_ok,
                checked_pred=c_pred,
                checked_ok=c_ok,
                checked_method=c_res.method,
                checked_turns=c_res.turns_taken,
                checked_ms=round(c_res.total_elapsed_ms, 1),
            )
        )
        print(
            f"Bare={'PASS' if b_ok else 'FAIL'}({b_pred}) | "
            f"SinglePy={'PASS' if s_ok else 'FAIL'}({s_pred}) | "
            f"Checked={'PASS' if c_ok else 'FAIL'}({c_pred} via {c_res.method}) [{c_res.total_elapsed_ms:.0f}ms]",
            flush=True,
        )

    n = len(results)
    b_tot = sum(1 for r in results if r.bare_ok)
    s_tot = sum(1 for r in results if r.single_ok)
    c_tot = sum(1 for r in results if r.checked_ok)
    agreed_tot = sum(1 for r in results if r.checked_method == "CHECKED_FORMALIZATION_AGREED")

    print("\n==========================================================================", flush=True)
    print(f"Bare Mental LLM:                  {b_tot}/{n} ({b_tot/n*100:.1f}%)", flush=True)
    print(f"Single-Formulation Greedy Python: {s_tot}/{n} ({s_tot/n*100:.1f}%)", flush=True)
    print(f"Checked Formalization (v1.38):    {c_tot}/{n} ({c_tot/n*100:.1f}%) [Dual-Agreed: {agreed_tot}/{n}]", flush=True)
    print("==========================================================================", flush=True)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = REPORT_DIR / f"checked_formalization_{args.model_tag}_{int(time.time())}.json"
    out_file.write_text(
        json.dumps(
            {
                "benchmark": "Checked_Formalization_Expanded_v138",
                "model_tag": args.model_tag,
                "evaluated_at": datetime.now(UTC).isoformat(),
                "total": n,
                "bare_passed": b_tot,
                "bare_pct": round(b_tot / n * 100.0, 1),
                "single_python_passed": s_tot,
                "single_python_pct": round(s_tot / n * 100.0, 1),
                "checked_passed": c_tot,
                "checked_pct": round(c_tot / n * 100.0, 1),
                "dual_agreed_count": agreed_tot,
                "results": [asdict(r) for r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[+] Report written to: {out_file}", flush=True)


if __name__ == "__main__":
    main()
