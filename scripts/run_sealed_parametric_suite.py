#!/usr/bin/env python3
"""
Project Lucca — Sealed Parametric Reasoning Benchmark Evaluator
Evaluates the 125 freshly generated, programmatically ground-truthed tasks from
data/benchmarks/sealed_parametric_v138_suite.json across three distinct arms:

Arm A: Direct Baseline (T=0.0, max_tokens=1024, enable_thinking=False)
Arm B: Extended Thinking Baseline (T=0.6, max_tokens=2048, enable_thinking=True)
Arm C: Lucca v1.38 Compound Neurosymbolic Workspace (Router -> Shared Docker Python Workspace -> CEGIS)

Supports:
--limit-per-suite <int> (e.g. 5 for rapid verification, 25 for full master evaluation)
--suite <str> (e.g. 'all', 'single_lobe_epistemic', 'single_lobe_smt', etc.)
--repeats <int> (default: 1)
--model-tag <str> (default: "12B_V138")
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from math import comb
from pathlib import Path
import re
import sys
import time
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.reasoning.cegis_python import PythonCEGISEngine
from lucca.router.heuristic import HeuristicRouter
from lucca.sandbox.rpc import DockerRPCTransport

DATA_FILE: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "sealed_parametric_v138_suite.json"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0


def exact_mcnemar_two_sided(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


@dataclass
class TaskEvalResult:
    task_id: str
    suite: str
    family: str
    ground_truth: str
    # Arm A
    direct_pred: str | None
    direct_ok: bool
    direct_ms: float
    # Arm B
    thinking_pred: str | None
    thinking_ok: bool
    thinking_ms: float
    # Arm C
    compound_pred: str | None
    compound_ok: bool
    compound_method: str
    compound_turns: int
    compound_ms: float


def query_llm(
    prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    enable_thinking: bool = False,
) -> tuple[str, str, int]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert problem-solving assistant with access to advanced mathematics and logic. "
                "Solve the problem carefully and conclude with your final answer on the last line."
            ),
        },
        {"role": "user", "content": prompt},
    ]
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
        tokens = data.get("usage", {}).get("completion_tokens", 0)
        msg = choice["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        if content.strip() and reasoning.strip():
            text = f"{content}\n[REASONING]\n{reasoning}"
        else:
            text = content if content.strip() else reasoning
        return text, finish_reason, tokens


def extract_answer(text: str, family: str) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    if not cleaned:
        return None

    # For container_world: look for location string
    if family == "container_world":
        lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
        last_line = lines[-1] if lines else ""
        m = re.search(r"(?:look (?:in|for|at)|is (?:in|at)|location is|answer is)[:\s]*['\"]?([a-z0-9_]+)['\"]?", last_line, re.IGNORECASE)
        if m:
            return m.group(1).lower().strip()
        words = re.findall(r"\b[a-z0-9_]+\b", last_line.lower())
        return words[-1] if words else None

    # For math/smt: extract integer
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    for ln in reversed(lines):
        matches = re.findall(r"-?\d+", ln)
        if matches:
            return matches[-1]
    return None


def evaluate_task_compound(
    prompt: str,
    family: str,
    required_lobes: list[str],
    router: HeuristicRouter,
    engine: PythonCEGISEngine,
) -> tuple[str | None, str, int, float]:
    t0 = time.perf_counter()

    # Determine code prompt based on required lobes
    import_header = []
    if "container_world" in required_lobes:
        import_header.append("from container_world import ContainerWorld, World, Agent")
    if "sympy" in required_lobes:
        import_header.append("import sympy\nfrom sympy import *")
    if "z3" in required_lobes:
        import_header.append("import z3\nfrom z3 import *")

    header_str = "\n".join(import_header)
    instructions = (
        f"You are Project Lucca's neurosymbolic synthesis engine. Solve the following problem by writing a clean, "
        f"executable Python script.\n"
        f"Available modules: {', '.join(required_lobes) if required_lobes else 'standard library'}.\n"
        f"Write ONLY executable Python code inside a ```python ``` code block. "
        f"Do NOT write multi-line docstrings or narrative explanations. "
        f"Print ONLY the final answer on stdout with print(final_answer).\n\n"
        f"Problem:\n{prompt}\n"
    )

    pattern = r"[a-z0-9_]+" if family == "container_world" else r"-?\d+"
    s_res = engine.synthesize_and_repair(
        task_prompt=instructions,
        prelude=header_str,
        test_harness=None,
        output_pattern=pattern,
        max_turns=3,
        temperature=0.0,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    pred = str(s_res.output).strip().lower() if s_res.output is not None else None
    return pred, s_res.method, s_res.turns_taken, elapsed_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Sealed Parametric Reasoning Benchmark Evaluator")
    parser.add_argument("--dataset", type=Path, default=DATA_FILE, help="Path to benchmark JSON dataset")
    parser.add_argument("--limit-per-suite", type=int, default=5, help="Tasks per suite (default: 5, max: 25)")
    parser.add_argument("--suite", type=str, default="all", help="Target suite name or 'all'")
    parser.add_argument("--model-tag", type=str, default="12B_V138", help="Model evaluation tag")
    parser.add_argument(
        "--arms",
        choices=["all", "compound", "direct_compound"],
        default="all",
        help="Evaluation arms: 'all' (Direct+Thinking+Compound), 'compound' (Compound only), or 'direct_compound'",
    )
    args = parser.parse_args()

    data_path = args.dataset if args.dataset.is_absolute() else REPO_ROOT / args.dataset

    print("==========================================================================")
    print("=== PROJECT LUCCA: SEALED PARAMETRIC REASONING MASTER BENCHMARK ===")
    print("==========================================================================")
    print(f"Timestamp: {datetime.now(UTC).isoformat()} | Model: {args.model_tag}")
    print(f"Dataset: {data_path.name} (limit={args.limit_per_suite} per suite, target_suite={args.suite})\n")

    data = json.load(open(data_path, encoding="utf-8"))
    all_tasks = data.get("tasks", [])

    suites = [
        "single_lobe_epistemic",
        "single_lobe_smt",
        "single_lobe_cas",
        "two_lobe_composed",
        "formalization_translation",
    ]
    if args.suite != "all":
        suites = [args.suite]

    selected: list[dict[str, Any]] = []
    for s in suites:
        sub = [t for t in all_tasks if t["suite"] == s][:args.limit_per_suite]
        selected.extend(sub)

    print(f"[+] Loaded {len(selected)} total sealed tasks across {len(suites)} suites.\n")

    # Initialize Lucca neurosymbolic substrate & pre-warm worker
    router = HeuristicRouter()
    engine = PythonCEGISEngine(server_url=SERVER_URL, container_name="lucca-file-sandbox")
    print("[*] Pre-warming Docker RPC worker...")
    engine.transport.warmup()
    print("[+] Docker RPC worker warm and ready.\n")

    results: list[TaskEvalResult] = []

    for idx, t in enumerate(selected, start=1):
        tid = t["task_id"]
        suite = t["suite"]
        family = t["family"]
        gt = str(t["ground_truth"]).strip().lower()

        print(f"[{idx:02d}/{len(selected):02d}] [{suite}] {tid} (GT={gt})... ", end="", flush=True)

        # 1. Arm A: Direct Baseline
        run_direct = args.arms in ("all", "direct_compound")
        t0 = time.perf_counter()
        if run_direct:
            try:
                d_out, _, _ = query_llm(t["prompt"], max_tokens=1024, temperature=0.0, enable_thinking=False)
                d_ms = (time.perf_counter() - t0) * 1000.0
                d_pred = extract_answer(d_out, family)
                d_ok = (d_pred == gt)
            except Exception:
                d_pred, d_ok, d_ms = None, False, 0.0
        else:
            d_pred, d_ok, d_ms = None, False, 0.0

        # 2. Arm B: Extended Thinking Baseline
        run_thinking = (args.arms == "all")
        t0 = time.perf_counter()
        if run_thinking:
            try:
                th_out, _, _ = query_llm(t["prompt"], max_tokens=2048, temperature=0.6, enable_thinking=True)
                th_ms = (time.perf_counter() - t0) * 1000.0
                th_pred = extract_answer(th_out, family)
                th_ok = (th_pred == gt)
            except Exception:
                th_pred, th_ok, th_ms = None, False, 0.0
        else:
            th_pred, th_ok, th_ms = None, False, 0.0

        # 3. Arm C: Compound Neurosymbolic Workspace
        run_compound = args.arms in ("all", "compound", "direct_compound")
        if run_compound:
            try:
                c_pred, c_method, c_turns, c_ms = evaluate_task_compound(
                    prompt=t["prompt"],
                    family=family,
                    required_lobes=t["required_lobes"],
                    router=router,
                    engine=engine,
                )
                c_ok = (c_pred == gt)
            except Exception as exc:
                c_pred, c_method, c_turns, c_ms, c_ok = None, f"ERROR: {exc}", 0, 0.0, False
        else:
            c_pred, c_method, c_turns, c_ms, c_ok = None, "SKIPPED", 0, 0.0, False

        res = TaskEvalResult(
            task_id=tid,
            suite=suite,
            family=family,
            ground_truth=gt,
            direct_pred=d_pred,
            direct_ok=d_ok,
            direct_ms=round(d_ms, 1),
            thinking_pred=th_pred,
            thinking_ok=th_ok,
            thinking_ms=round(th_ms, 1),
            compound_pred=c_pred,
            compound_ok=c_ok,
            compound_method=c_method,
            compound_turns=c_turns,
            compound_ms=round(c_ms, 1),
        )
        results.append(res)

        print(
            f"Direct={'PASS' if d_ok else 'FAIL'}({d_pred}) | "
            f"Think={'PASS' if th_ok else 'FAIL'}({th_pred}) | "
            f"Compound={'PASS' if c_ok else 'FAIL'}({c_pred} via {c_method}) [{c_ms:.0f}ms]",
            flush=True,
        )

    # -------------------------------------------------------------
    # Summary by Suite & Overall
    # -------------------------------------------------------------
    print("\n" + "=" * 78)
    print(f"SEALED PARAMETRIC BENCHMARK SUMMARY (N={len(results)})")
    print("=" * 78)
    print(f"{'Suite':<28} {'N':<4} {'Direct':<12} {'Thinking':<12} {'Compound':<12} {'Lift vs Dir':<12}")
    print("-" * 78)

    for s in suites:
        s_res = [r for r in results if r.suite == s]
        n_s = len(s_res)
        if n_s == 0:
            continue
        d_p = sum(1 for r in s_res if r.direct_ok)
        th_p = sum(1 for r in s_res if r.thinking_ok)
        c_p = sum(1 for r in s_res if r.compound_ok)
        lift = (c_p - d_p) / n_s * 100
        print(
            f"{s:<28} {n_s:<4} {d_p}/{n_s} ({d_p/n_s*100:4.1f}%) "
            f"{th_p}/{n_s} ({th_p/n_s*100:4.1f}%) "
            f"{c_p}/{n_s} ({c_p/n_s*100:4.1f}%) "
            f"{lift:+5.1f} pp"
        )

    total_n = len(results)
    tot_d = sum(1 for r in results if r.direct_ok)
    tot_th = sum(1 for r in results if r.thinking_ok)
    tot_c = sum(1 for r in results if r.compound_ok)
    tot_lift = (tot_c - tot_d) / total_n * 100

    b_dir = sum(1 for r in results if r.direct_ok and not r.compound_ok)
    c_dir = sum(1 for r in results if not r.direct_ok and r.compound_ok)
    p_dir = exact_mcnemar_two_sided(b_dir, c_dir)

    b_th = sum(1 for r in results if r.thinking_ok and not r.compound_ok)
    c_th = sum(1 for r in results if not r.thinking_ok and r.compound_ok)
    p_th = exact_mcnemar_two_sided(b_th, c_th)

    print("-" * 78)
    print(
        f"{'TOTAL OVERALL':<28} {total_n:<4} {tot_d}/{total_n} ({tot_d/total_n*100:4.1f}%) "
        f"{tot_th}/{total_n} ({tot_th/total_n*100:4.1f}%) "
        f"{tot_c}/{total_n} ({tot_c/total_n*100:4.1f}%) "
        f"{tot_lift:+5.1f} pp"
    )
    print(f"Compound vs Direct McNemar:   b={b_dir}, c={c_dir}, exact two-sided p={p_dir:.6f}")
    print(f"Compound vs Thinking McNemar: b={b_th}, c={c_th}, exact two-sided p={p_th:.6f}")
    print("=" * 78)

    # Save JSON report
    out_file = REPO_ROOT / "logs" / "test_reports" / f"sealed_parametric_{args.model_tag}_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "Sealed_Parametric_Reasoning_Master_Benchmark",
        "model_tag": args.model_tag,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_tasks": total_n,
        "direct_passed": tot_d,
        "direct_pct": round(tot_d / total_n * 100, 1),
        "thinking_passed": tot_th,
        "thinking_pct": round(tot_th / total_n * 100, 1),
        "compound_passed": tot_c,
        "compound_pct": round(tot_c / total_n * 100, 1),
        "lift_pp": round(tot_lift, 1),
        "mcnemar_direct": {"b": b_dir, "c": c_dir, "p_two_sided": round(p_dir, 6)},
        "mcnemar_thinking": {"b": b_th, "c": c_th, "p_two_sided": round(p_th, 6)},
        "results": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[+] Saved evaluation report to: {out_file}")


if __name__ == "__main__":
    main()
