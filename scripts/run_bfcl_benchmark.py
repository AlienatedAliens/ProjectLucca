#!/usr/bin/env python3
"""
Project Lucca — Berkeley Function Calling Leaderboard (BFCL V3) Benchmark Runner
Evaluates:
1. Tool Invocation Accuracy (25 items from BFCL exec_simple): Correct function & argument extraction
2. Tool Irrelevance Abstention (25 items from BFCL irrelevance): Proper abstention without tool hallucination
Total n=50 evaluated on resident E2B compound system.
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
sys.path.insert(0, str(REPO_ROOT))

DATA_DIR: Final[Path] = REPO_ROOT / "data" / "benchmarks"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0


@dataclass
class BFCLResult:
    item_id: str
    category: str
    user_prompt: str
    ground_truth: str | None
    predicted_call: str | None
    passed: bool
    latency_s: float
    finish_reason: str = "unknown"
    completion_tokens: int = 0
    error_note: str | None = None


def compare_arg_values(pred_v: Any, gt_v: Any) -> bool:
    """Semantic comparison tolerant to sequence container types and numeric types."""
    if pred_v is None and gt_v is None:
        return True
    if pred_v is None or gt_v is None:
        return False

    # Sequence comparison (tuples vs lists)
    if isinstance(pred_v, (list, tuple)) and isinstance(gt_v, (list, tuple)):
        if len(pred_v) != len(gt_v):
            return False
        return all(compare_arg_values(p, g) for p, g in zip(pred_v, gt_v))

    # Numeric comparison (ints vs floats)
    try:
        p_num = float(pred_v)
        g_num = float(gt_v)
        return abs(p_num - g_num) < 1e-4
    except (ValueError, TypeError):
        pass

    # String / boolean / enum fallback
    p_str = str(pred_v).strip().lower()
    g_str = str(gt_v).strip().lower()
    return p_str == g_str


def parse_ground_truth_call(gt_str: str) -> tuple[str, dict[str, Any]]:
    """Parse 'func_name(a=1, b=2)' into (func_name, dict)."""
    m = re.match(r"^(\w+)\((.*)\)$", gt_str.strip())
    if not m:
        return gt_str.strip(), {}
    fn_name, args_str = m.group(1), m.group(2)
    args_dict = {}
    if args_str.strip():
        parts = [p.strip() for p in re.split(r",\s*(?=[a-zA-Z_]\w*=)", args_str) if p.strip()]
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                k = k.strip()
                v = v.strip()
                try:
                    args_dict[k] = json.loads(v)
                except Exception:
                    # Handle unquoted tuples like '(32.71, -117.16)'
                    if v.startswith("(") and v.endswith(")"):
                        try:
                            args_dict[k] = list(json.loads("[" + v[1:-1] + "]"))
                        except Exception:
                            args_dict[k] = v.strip("\"'")
                    else:
                        args_dict[k] = v.strip("\"'")
    return fn_name, args_dict


def query_llm_tools(
    messages: list[dict[str, str]],
    tools: list[dict[str, Any]],
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> tuple[dict[str, Any], str, int]:
    payload = {
        "messages": messages,
        "tools": [{"type": "function", "function": f} for f in tools],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        res = client.post(SERVER_URL, json=payload)
        res.raise_for_status()
        data = res.json()
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason") or "unknown"
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        return choice["message"], finish_reason, completion_tokens


def run_bfcl_benchmark(limit_per_category: int = 25, seed: int = 42, model_tag: str = "E2B") -> None:
    print("==========================================================================", flush=True)
    print("=== PROJECT LUCCA: BERKELEY FUNCTION CALLING LEADERBOARD (BFCL) ===", flush=True)
    print("==========================================================================", flush=True)
    print(f"Timestamp: {datetime.now(UTC).isoformat()}", flush=True)
    print(f"Categories: exec_simple ({limit_per_category}), irrelevance ({limit_per_category})\n", flush=True)

    simple_path = DATA_DIR / "BFCL_v3_exec_simple.json"
    irrel_path = DATA_DIR / "BFCL_v3_irrelevance.json"

    simple_items = [json.loads(l) for l in simple_path.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
    irrel_items = [json.loads(l) for l in irrel_path.read_text(encoding="utf-8").strip().split("\n") if l.strip()]

    rng = random.Random(seed)
    rng.shuffle(simple_items)
    rng.shuffle(irrel_items)

    selected_simple = simple_items[:limit_per_category]
    selected_irrel = irrel_items[:limit_per_category]

    results: list[BFCLResult] = []

    # 1. Exec Simple
    print(f"--- [Category: exec_simple (n={len(selected_simple)})] ---", flush=True)
    for idx, it in enumerate(selected_simple, start=1):
        item_id = it["id"]
        turns = it["question"]
        tools = it["function"]
        gt_raw = it.get("ground_truth", [""])[0]

        # Extract user prompt
        user_msg = turns[0][0]["content"] if isinstance(turns[0], list) else turns[0]["content"]
        messages = [{"role": "user", "content": user_msg}]

        print(f"[{idx:02d}/{len(selected_simple):02d}] {item_id}... ", end="", flush=True)
        t0 = time.perf_counter()
        pred_str = None
        ok = False
        err = None
        try:
            msg, finish, tok = query_llm_tools(messages, tools)
            sec = time.perf_counter() - t0
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                pred_str = "NO_TOOL_CALLED"
                err = "Expected tool call but assistant replied with text"
            else:
                tc = tool_calls[0]["function"]
                fn_name = tc.get("name", "")
                args_json = tc.get("arguments", "{}")
                try:
                    args = json.loads(args_json) if isinstance(args_json, str) else args_json
                except Exception:
                    args = {}
                arg_pairs = ", ".join(f"{k}={v}" for k, v in sorted(args.items()))
                pred_str = f"{fn_name}({arg_pairs})"

                # Match against ground truth
                gt_name, gt_args = parse_ground_truth_call(gt_raw)
                if fn_name == gt_name:
                    all_match = True
                    for k, v in gt_args.items():
                        pred_v = args.get(k)
                        if not compare_arg_values(pred_v, v):
                            all_match = False
                            break
                    ok = all_match
                    if not ok:
                        err = f"Arg mismatch: pred={args} vs gt={gt_args}"
                else:
                    err = f"Name mismatch: pred={fn_name} vs gt={gt_name}"
        except Exception as exc:
            sec = time.perf_counter() - t0
            finish, tok = "error", 0
            err = str(exc)

        res = BFCLResult(
            item_id=item_id,
            category="exec_simple",
            user_prompt=user_msg[:120],
            ground_truth=gt_raw,
            predicted_call=pred_str,
            passed=ok,
            latency_s=round(sec, 2),
            finish_reason=finish,
            completion_tokens=tok,
            error_note=err,
        )
        results.append(res)
        flag = f"[TRUNC:{tok}]" if finish == "length" else f"[{tok}tok]"
        print(f"{'PASS' if ok else 'FAIL'} (Pred: {pred_str} | GT: {gt_raw}) {flag} [{sec:.2f}s]", flush=True)

    # 2. Irrelevance
    print(f"\n--- [Category: irrelevance (n={len(selected_irrel)})] ---", flush=True)
    for idx, it in enumerate(selected_irrel, start=1):
        item_id = it["id"]
        turns = it["question"]
        tools = it["function"]

        user_msg = turns[0][0]["content"] if isinstance(turns[0], list) else turns[0]["content"]
        messages = [{"role": "user", "content": user_msg}]

        print(f"[{idx:02d}/{len(selected_irrel):02d}] {item_id}... ", end="", flush=True)
        t0 = time.perf_counter()
        pred_str = None
        ok = False
        err = None
        try:
            msg, finish, tok = query_llm_tools(messages, tools)
            sec = time.perf_counter() - t0
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                ok = True
                pred_str = "ABSTAIN_CORRECT"
            else:
                tc = tool_calls[0]["function"]
                fn_name = tc.get("name", "")
                pred_str = f"HALLUCINATED_CALL: {fn_name}"
                err = f"Model invoked tool {fn_name} when query was irrelevant"
        except Exception as exc:
            sec = time.perf_counter() - t0
            finish, tok = "error", 0
            err = str(exc)

        res = BFCLResult(
            item_id=item_id,
            category="irrelevance",
            user_prompt=user_msg[:120],
            ground_truth="NO_TOOL_CALL",
            predicted_call=pred_str,
            passed=ok,
            latency_s=round(sec, 2),
            finish_reason=finish,
            completion_tokens=tok,
            error_note=err,
        )
        results.append(res)
        flag = f"[TRUNC:{tok}]" if finish == "length" else f"[{tok}tok]"
        print(f"{'PASS' if ok else 'FAIL'} ({pred_str}) {flag} [{sec:.2f}s]", flush=True)

    # Summary
    print("\n" + "=" * 60)
    print("BFCL V3 BENCHMARK SUMMARY")
    print("=" * 60)
    simple_res = [r for r in results if r.category == "exec_simple"]
    irrel_res = [r for r in results if r.category == "irrelevance"]
    s_acc = sum(1 for r in simple_res if r.passed) / len(simple_res) * 100
    i_acc = sum(1 for r in irrel_res if r.passed) / len(irrel_res) * 100
    total_acc = sum(1 for r in results if r.passed) / len(results) * 100

    print(f"exec_simple (Tool Invocation Accuracy): {sum(1 for r in simple_res if r.passed)}/{len(simple_res)} ({s_acc:.1f}%)")
    print(f"irrelevance (Abstention / Anti-Hallucination): {sum(1 for r in irrel_res if r.passed)}/{len(irrel_res)} ({i_acc:.1f}%)")
    print("-" * 60)
    print(f"OVERALL BFCL ACCURACY: {sum(1 for r in results if r.passed)}/{len(results)} ({total_acc:.1f}%)")
    print("=" * 60)

    out_name = f"bfcl_v3_benchmark_{model_tag}_{int(time.time())}.json" if model_tag else f"bfcl_v3_benchmark_{int(time.time())}.json"
    out_file = REPO_ROOT / "logs" / "test_reports" / out_name
    out_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "BFCL_V3_Berkeley_Function_Calling",
        "model_tag": model_tag or "E2B",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "total_items": len(results),
        "exec_simple_passed": sum(1 for r in simple_res if r.passed),
        "exec_simple_pct": round(s_acc, 1),
        "irrelevance_passed": sum(1 for r in irrel_res if r.passed),
        "irrelevance_pct": round(i_acc, 1),
        "overall_passed": sum(1 for r in results if r.passed),
        "overall_pct": round(total_acc, 1),
        "results": [asdict(r) for r in results],
    }
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report written to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BFCL V3 Benchmark Runner")
    parser.add_argument("--limit", type=int, default=25, help="Items per category (default: 25)")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    parser.add_argument("--model-tag", type=str, default="E2B", help="Model tier tag (e.g. E2B, E4B, 12B)")
    args = parser.parse_args()
    run_bfcl_benchmark(limit_per_category=args.limit, seed=args.seed, model_tag=args.model_tag)
