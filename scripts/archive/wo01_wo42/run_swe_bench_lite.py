#!/usr/bin/env python3
"""
Project Lucca — Curated SWE-bench Lite Benchmark Runner (5 tasks)
Evaluates autonomous multi-turn software engineering loops using:
- grep_tree
- view_slice
- apply_patch
- run_pytest

Measures resolver pass rate on resident Tier 0 LLM (Gemma-4-26B-A4B).
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Any, Final

import httpx

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lucca.sandbox.service import SandboxService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("swe_bench_lite")

BENCH_ROOT: Final[Path] = REPO_ROOT / "data" / "benchmarks" / "swe_bench_lite"
SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 120.0
MAX_TURNS: Final[int] = 8

SYSTEM_PROMPT: Final[str] = """You are Lucca, an expert software engineer resolving a reported bug in a Python repository.
You have access to 4 specialized code tools:
1. `grep_tree`: Search files recursively for regex pattern.
   Args: {"pattern": str, "dir_path": str, "max_hits": int}
2. `view_slice`: Read specific line range from a file.
   Args: {"path": str, "start_line": int, "end_line": int}
3. `apply_patch`: Replace an exact unique code block in a file with new code.
   Args: {"path": str, "target_chunk": str, "replacement_chunk": str}
4. `run_pytest`: Run the test suite to verify reproduction and resolution.
   Args: {"test_path": str, "cwd": str}

CRITICAL RULES:
- When you want to call a tool, output ONLY the tool invocation formatted inside a markdown block:
```tool
{"tool": "<tool_name>", "args": {<arguments>}}
```
- First inspect the test file and the implementation file to diagnose the root cause.
- Apply a minimal, surgical patch using `apply_patch`.
- Verify your fix by running `run_pytest`.
- When the test passes with exit code 0 and the issue is resolved, output:
ISSUE_RESOLVED
"""


def query_llm(messages: list[dict[str, str]], temperature: float = 0.1, max_tokens: int = 1536) -> str:
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "stop": ["```\n\n", "```\n\n```"],
    }
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        res = client.post(SERVER_URL, json=payload)
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"]


def extract_tool_call(response: str) -> tuple[str | None, dict[str, Any] | None]:
    """Extracts tool name and arguments from model response using JSONDecoder without regex."""
    if not response:
        return None, None

    decoder = json.JSONDecoder()
    pos = 0
    while True:
        idx = response.find("{", pos)
        if idx == -1:
            break
        try:
            obj, _ = decoder.raw_decode(response, idx)
            if isinstance(obj, dict) and "tool" in obj and "args" in obj:
                return str(obj["tool"]), dict(obj.get("args") or {})
            pos = idx + 1
        except json.JSONDecodeError:
            pos = idx + 1

    return None, None


def run_swe_task(task_meta: dict[str, Any]) -> dict[str, Any]:
    task_id = task_meta["task_id"]
    task_dir = BENCH_ROOT / task_id
    problem = task_meta["problem_statement"]

    logger.info("Starting SWE-bench task %s", task_id)

    # Initialize sandbox service for this workspace
    svc = SandboxService(workspace_root=str(task_dir), use_direct_fallback=True)

    # Verify baseline failure
    base_res = svc.execute_tool("baseline", "run_pytest", {}, confirmed=True)
    logger.info("Task %s initial pytest: exit_code=%d", task_id, base_res.exit_code)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"We have an issue in repo '{task_meta['repo']}':\n\n"
                f"{problem}\n\n"
                f"Repository files are in the current workspace. Start by investigating the codebase with grep_tree or view_slice."
            ),
        },
    ]

    trajectory: list[dict[str, Any]] = []
    resolved = False
    t0 = time.perf_counter()

    for turn in range(1, MAX_TURNS + 1):
        logger.info("Task %s Turn %d/%d querying LLM...", task_id, turn, MAX_TURNS)
        try:
            reply = query_llm(messages)
        except Exception as exc:
            logger.error("LLM query error on turn %d: %s", turn, exc)
            trajectory.append({"turn": turn, "error": str(exc)})
            break

        messages.append({"role": "assistant", "content": reply})
        trajectory.append({"turn": turn, "llm_reply": reply})

        if "ISSUE_RESOLVED" in reply:
            logger.info("Task %s model declared ISSUE_RESOLVED on turn %d", task_id, turn)
            break

        tool_name, tool_args = extract_tool_call(reply)
        if not tool_name or tool_args is None:
            logger.warning("Task %s no structured tool call detected in turn %d. Nudging model.", task_id, turn)
            messages.append({
                "role": "user",
                "content": (
                    "Please use one of the tools: `grep_tree`, `view_slice`, `apply_patch`, `run_pytest`. "
                    "Format your call inside a ```tool { ... } ``` block."
                ),
            })
            continue

        logger.info("Task %s Turn %d invoking tool '%s' with args %s", task_id, turn, tool_name, list(tool_args.keys()))
        t_res = svc.execute_tool(f"swe-{task_id}-t{turn}", tool_name, tool_args, confirmed=True)
        tool_output_str = t_res.content if t_res.ok else f"ERROR (exit_code {t_res.exit_code}): {t_res.stderr or t_res.content or ''}"

        trajectory[-1]["tool_call"] = {"tool": tool_name, "args": tool_args}
        trajectory[-1]["tool_result"] = {
            "ok": t_res.ok,
            "exit_code": t_res.exit_code,
            "output_preview": tool_output_str[:300],
        }

        # Feedback to assistant
        messages.append({
            "role": "user",
            "content": f"[Tool Result for '{tool_name}']:\n{tool_output_str}",
        })

    elapsed_s = time.perf_counter() - t0

    # Independent final verification
    final_test_res = svc.execute_tool("final_verify", "run_pytest", {}, confirmed=True)
    resolved = (final_test_res.exit_code == 0)
    final_out = (final_test_res.content or final_test_res.stderr or "")[:500]
    logger.info("Task %s final verification: exit_code=%d -> RESOLVED=%s (elapsed: %.1fs)", task_id, final_test_res.exit_code, resolved, elapsed_s)

    return {
        "task_id": task_id,
        "repo": task_meta["repo"],
        "resolved": resolved,
        "final_exit_code": final_test_res.exit_code,
        "final_test_output": final_out,
        "elapsed_seconds": round(elapsed_s, 2),
        "turns_used": len(trajectory),
        "trajectory": trajectory,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Curated SWE-bench Lite Benchmark")
    parser.add_argument("--tasks", nargs="*", help="Specific task IDs to run")
    args = parser.parse_args()

    manifest_file = BENCH_ROOT / "manifest.json"
    if not manifest_file.exists():
        logger.error("Manifest not found at %s. Run setup_swe_bench_lite.py first.", manifest_file)
        sys.exit(1)

    tasks: list[dict[str, Any]] = json.loads(manifest_file.read_text(encoding="utf-8"))
    if args.tasks:
        tasks = [t for t in tasks if t["task_id"] in args.tasks]

    logger.info("Running SWE-bench Lite on %d tasks...", len(tasks))

    from scripts.setup_swe_bench_lite import reset_task  # noqa: PLC0415

    results = []
    for t in tasks:
        # Reset task files before each run
        reset_task(t["task_id"])

        res = run_swe_task(t)
        results.append(res)

    solved_count = sum(1 for r in results if r["resolved"])
    total_count = len(results)
    solve_rate = (solved_count / total_count * 100.0) if total_count > 0 else 0.0

    report = {
        "benchmark": f"SWE-bench Lite Curated ({total_count} tasks)",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "model": "gemma-4-26B-A4B-it-heretic",
        "harness": "Lucca Multi-Turn Sandbox (grep_tree, view_slice, apply_patch, run_pytest)",
        "tasks_evaluated": total_count,
        "tasks_solved": solved_count,
        "solve_rate_pct": round(solve_rate, 2),
        "task_results": results,
    }

    report_dir = REPO_ROOT / "logs" / "test_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"swe_bench_lite_{int(time.time())}.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("SWE-BENCH LITE EVALUATION COMPLETE")
    print(f"Tasks: {solved_count}/{total_count} ({solve_rate:.1f}%)")
    print(f"Report: {report_file}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
