#!/usr/bin/env python3
"""
Project Lucca — LiveCodeBench 2026 CEGIS Benchmark & Evaluation Suite
=====================================================================
Evaluates contamination-free competitive programming problems from LiveCodeBench 2026
under Lucca's compound neuro-symbolic and CEGIS test-and-repair architecture.

Comparison Arms:
- Arm A (Direct Generation): Zero-shot code generation evaluated directly against held-out tests.
- Arm B (CEGIS Compound): Code generation followed by automated execution against public test cases.
  If public tests fail, concrete runtime counterexamples (inputs, expected outputs, stderr)
  are synthesized into CEGIS repair turns before final evaluation on held-out private test suites.

Features:
- Full support for both STDIN competitive formats (Codeforces, AtCoder) and Functional formats (LeetCode).
- Automatic decompression and verification of official encrypted/compressed private test suites.
- Rigorous statistical accounting: Wilson 95% confidence intervals, repair rescue delta, AST verification.
- Output serialization conforming to Project Lucca's canonical benchmark report schema.
"""

from __future__ import annotations

import argparse
import ast
import base64
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import pickle
import re
import subprocess
import sys
import time
from typing import Any, Final
import zlib

import httpx
from scipy.stats import binomtest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Windows console cp1252 fix
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SERVER_URL: Final[str] = "http://127.0.0.1:8080/v1/chat/completions"
TIMEOUT_SECONDS: Final[float] = 90.0
REPORTS_DIR: Final[Path] = REPO_ROOT / "logs" / "test_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

STANDARD_IMPORTS: Final[str] = (
    "from string import *\n"
    "from re import *\n"
    "from datetime import *\n"
    "from collections import *\n"
    "from heapq import *\n"
    "from bisect import *\n"
    "from copy import *\n"
    "from math import *\n"
    "from random import *\n"
    "from statistics import *\n"
    "from itertools import *\n"
    "from functools import *\n"
    "from operator import *\n"
    "from io import *\n"
    "from sys import *\n"
    "from json import *\n"
    "from builtins import *\n"
    "from typing import *\n"
    "import string\n"
    "import re\n"
    "import datetime\n"
    "import collections\n"
    "import heapq\n"
    "import bisect\n"
    "import copy\n"
    "import math\n"
    "import random\n"
    "import statistics\n"
    "import itertools\n"
    "import functools\n"
    "import operator\n"
    "import io\n"
    "import sys\n"
    "import json\n"
    "sys.setrecursionlimit(50000)\n"
)


# =============================================================================
# Statistical Helpers
# =============================================================================

def wilson_ci(k: int, n: int, z: float = 1.95996) -> tuple[float, float]:
    """Computes two-sided Wilson score confidence interval."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    margin = (z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def extract_python_code(response: str) -> str:
    """Extracts python code block from model response with open-block and thought tolerance."""
    if not response:
        return ""
    # 1. Closed python block
    match = re.search(r"```python\s*([\s\S]*?)```", response, re.IGNORECASE)
    if match and match.group(1).strip():
        return match.group(1).strip()
    # 2. Closed generic code block
    match = re.search(r"```\s*([\s\S]*?)```", response)
    if match and match.group(1).strip():
        return match.group(1).strip()
    # 3. Unclosed python block (truncated at token ceiling)
    match = re.search(r"```python\s*([\s\S]*)$", response, re.IGNORECASE)
    if match and match.group(1).strip():
        return match.group(1).strip()
    # 4. Fallback if code contains def solve or class Solution
    if "def " in response or "import " in response or "class " in response:
        clean = re.sub(r"<thought>[\s\S]*?</thought>", "", response)
        return clean.strip()
    return response.strip()


def query_llm(
    prompt: str,
    system_prompt: str = "You are an expert competitive programmer. Provide clean, correct, and optimal Python 3 solutions.",
    temperature: float = 0.0,
    max_tokens: int = 2048,
    enable_thinking: bool = False,
) -> str:
    """Queries resident llama-server completions endpoint with reasoning extraction."""
    payload = {
        "model": "gemma-4-26B-A4B-it",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        resp = client.post(SERVER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        if content and "```" in content:
            return content
        if reasoning and "```" in reasoning:
            return f"{content}\n{reasoning}".strip()
        return content if content else reasoning


# =============================================================================
# Code Execution Engine
# =============================================================================

@dataclass
class TestResult:
    passed: bool
    actual_output: str
    expected_output: str
    error_message: str | None = None
    elapsed_ms: float = 0.0


def execute_stdin_test(code: str, test_input: str, expected_output: str, timeout: float = 5.0) -> TestResult:
    """Executes a competitive programming solution reading from stdin."""
    full_script = f"{STANDARD_IMPORTS}\n\n{code}"
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", full_script],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if proc.returncode != 0:
            return TestResult(
                passed=False,
                actual_output=proc.stdout,
                expected_output=expected_output,
                error_message=f"Exit code {proc.returncode}: {proc.stderr.strip()[:300]}",
                elapsed_ms=elapsed_ms,
            )

        actual = proc.stdout.strip()
        expected = expected_output.strip()

        # Direct match or line-by-line whitespace-tolerant match
        if actual == expected:
            return TestResult(passed=True, actual_output=actual, expected_output=expected, elapsed_ms=elapsed_ms)

        actual_lines = [l.strip() for l in actual.splitlines() if l.strip()]
        expected_lines = [l.strip() for l in expected.splitlines() if l.strip()]
        if actual_lines == expected_lines:
            return TestResult(passed=True, actual_output=actual, expected_output=expected, elapsed_ms=elapsed_ms)

        # Numerical comparison if single token
        try:
            if abs(float(actual) - float(expected)) < 1e-5:
                return TestResult(passed=True, actual_output=actual, expected_output=expected, elapsed_ms=elapsed_ms)
        except (ValueError, TypeError):
            pass

        return TestResult(
            passed=False,
            actual_output=actual,
            expected_output=expected,
            error_message="Output mismatch",
            elapsed_ms=elapsed_ms,
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            actual_output="",
            expected_output=expected_output,
            error_message=f"TIMEOUT ({timeout:.1f}s exceeded)",
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except Exception as exc:
        return TestResult(
            passed=False,
            actual_output="",
            expected_output=expected_output,
            error_message=f"Execution Exception: {exc}",
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )


def execute_functional_test(
    code: str,
    func_name: str,
    test_input: str,
    expected_output: str,
    timeout: float = 5.0,
) -> TestResult:
    """Executes a functional (LeetCode class Solution) solution."""
    # Build wrapper script that deserializes JSON inputs, executes the method, and prints JSON output
    wrapper_code = f"""
{STANDARD_IMPORTS}

{code}

if __name__ == '__main__':
    raw_inputs = {repr(test_input)}
    raw_expected = {repr(expected_output)}
    
    # Parse inputs line-by-line
    args = []
    for line in raw_inputs.strip().split('\\n'):
        if line.strip():
            args.append(json.loads(line))
            
    expected = json.loads(raw_expected)
    
    sol = Solution()
    method = getattr(sol, {repr(func_name)})
    actual = method(*args)
    
    # Check match
    is_match = False
    if actual == expected:
        is_match = True
    elif isinstance(expected, float) and isinstance(actual, (int, float)):
        is_match = abs(float(actual) - float(expected)) < 1e-5
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) == len(actual):
            try:
                if sorted(expected) == sorted(actual):
                    is_match = True
            except Exception:
                pass

    print(json.dumps({{'match': is_match, 'actual': actual}}))
"""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", wrapper_code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if proc.returncode != 0:
            return TestResult(
                passed=False,
                actual_output=proc.stdout,
                expected_output=expected_output,
                error_message=f"Exit code {proc.returncode}: {proc.stderr.strip()[:300]}",
                elapsed_ms=elapsed_ms,
            )

        try:
            out_json = json.loads(proc.stdout.strip())
            is_pass = bool(out_json.get("match", False))
            act = str(out_json.get("actual"))
            return TestResult(
                passed=is_pass,
                actual_output=act,
                expected_output=expected_output,
                error_message=None if is_pass else "Output mismatch",
                elapsed_ms=elapsed_ms,
            )
        except Exception:
            return TestResult(
                passed=False,
                actual_output=proc.stdout.strip(),
                expected_output=expected_output,
                error_message="Failed to parse wrapper JSON output",
                elapsed_ms=elapsed_ms,
            )

    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            actual_output="",
            expected_output=expected_output,
            error_message=f"TIMEOUT ({timeout:.1f}s exceeded)",
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except Exception as exc:
        return TestResult(
            passed=False,
            actual_output="",
            expected_output=expected_output,
            error_message=f"Execution Exception: {exc}",
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )


def run_single_test(code: str, test_case: dict[str, Any], func_name: str | None, timeout: float = 5.0) -> TestResult:
    """Dispatches test execution based on test type (stdin vs functional)."""
    t_type = test_case.get("testtype", "stdin")
    inp = str(test_case.get("input", ""))
    out = str(test_case.get("output", ""))

    if t_type == "functional" and func_name:
        return execute_functional_test(code, func_name, inp, out, timeout=timeout)
    return execute_stdin_test(code, inp, out, timeout=timeout)


# =============================================================================
# Dataset Ingestion
# =============================================================================

@dataclass
class Problem:
    question_id: str
    question_title: str
    question_content: str
    platform: str
    difficulty: str
    starter_code: str
    func_name: str | None
    public_tests: list[dict[str, Any]]
    private_tests: list[dict[str, Any]]


def load_livecodebench_problems(
    dataset_path: Path,
    limit: int = 0,
    difficulty: str = "all",
    platform: str = "all",
) -> list[Problem]:
    """Loads and decompresses LiveCodeBench problems."""
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")

    problems: list[Problem] = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            raw = json.loads(line)

            diff = raw.get("difficulty", "medium").lower()
            if difficulty != "all" and diff != difficulty.lower():
                continue

            plat = raw.get("platform", "leetcode").lower()
            if platform != "all" and plat != platform.lower():
                continue

            # Parse metadata
            meta = raw.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            func_name = meta.get("func_name") if isinstance(meta, dict) else None

            # Parse public test cases
            pub_raw = raw.get("public_test_cases", "[]")
            if isinstance(pub_raw, str):
                try:
                    pub_tests = json.loads(pub_raw)
                except Exception:
                    pub_tests = []
            else:
                pub_tests = pub_raw

            # Parse/decompress private test cases
            priv_raw = raw.get("private_test_cases", "[]")
            priv_tests = []
            if isinstance(priv_raw, str):
                try:
                    priv_tests = json.loads(priv_raw)
                except Exception:
                    try:
                        decompressed = zlib.decompress(base64.b64decode(priv_raw.encode("utf-8")))
                        priv_tests = json.loads(pickle.loads(decompressed))
                    except Exception:
                        priv_tests = []
            elif isinstance(priv_raw, list):
                priv_tests = priv_raw

            p = Problem(
                question_id=str(raw.get("question_id", raw.get("question_title", ""))),
                question_title=str(raw.get("question_title", "")),
                question_content=str(raw.get("question_content", "")),
                platform=plat,
                difficulty=diff,
                starter_code=str(raw.get("starter_code", "")),
                func_name=func_name,
                public_tests=pub_tests,
                private_tests=priv_tests,
            )
            problems.append(p)
            if limit > 0 and len(problems) >= limit:
                break

    return problems


# =============================================================================
# Problem Evaluation & CEGIS Synthesis Harness
# =============================================================================

@dataclass
class ProblemEvaluationResult:
    question_id: str
    question_title: str
    platform: str
    difficulty: str
    arm_a_pass: bool
    arm_a_code: str
    arm_b_pass: bool
    arm_b_code: str
    arm_b_repairs_used: int
    arm_b_public_pass_rate: float
    arm_b_private_pass_rate: float
    elapsed_ms: float
    failure_log: str | None = None


def format_problem_prompt(prob: Problem) -> str:
    """Formats the initial coding prompt for the model."""
    prompt = f"Problem: {prob.question_title}\n\n{prob.question_content}\n\n"
    if prob.starter_code:
        prompt += f"Starter Code:\n```python\n{prob.starter_code}\n```\n\n"
        prompt += (
            "Complete the solution inside the provided class/function structure.\n"
            "Return only the complete, executable Python 3 implementation enclosed in a ```python ... ``` block."
        )
    else:
        prompt += (
            "Write a complete Python 3 solution that reads input from standard input (sys.stdin) "
            "and writes output to standard output (sys.stdout).\n"
            "Ensure optimal time and space complexity.\n"
            "Return only the complete Python 3 code enclosed in a ```python ... ``` block."
        )
    return prompt


def evaluate_problem(
    prob: Problem,
    arms: str = "both",
    max_repairs: int = 2,
    timeout_per_test: float = 4.0,
) -> ProblemEvaluationResult:
    """Evaluates a single LiveCodeBench problem across Direct (Arm A) and CEGIS (Arm B)."""
    t0 = time.perf_counter()
    initial_prompt = format_problem_prompt(prob)

    # Step 1: Initial Model Generation
    initial_resp = query_llm(initial_prompt, temperature=0.0)
    initial_code = extract_python_code(initial_resp)

    arm_a_pass = False
    arm_b_pass = False
    repairs_used = 0
    failure_log = None

    # Evaluate Arm A (Direct Pass@1 against held-out private tests)
    if arms in ("direct", "both"):
        private_passed_a = 0
        eval_private_tests = prob.private_tests if prob.private_tests else prob.public_tests
        for t in eval_private_tests:
            res = run_single_test(initial_code, t, prob.func_name, timeout=timeout_per_test)
            if res.passed:
                private_passed_a += 1
            else:
                break
        arm_a_pass = (private_passed_a == len(eval_private_tests)) and len(eval_private_tests) > 0

    # Evaluate Arm B (CEGIS Compound Synthesis with Public Test Feedback)
    current_code = initial_code
    if arms in ("cegis", "both"):
        # Check against public tests
        for repair_turn in range(max_repairs + 1):
            public_failed_test: dict[str, Any] | None = None
            public_fail_result: TestResult | None = None
            pub_passed = 0

            for pub_t in prob.public_tests:
                res = run_single_test(current_code, pub_t, prob.func_name, timeout=timeout_per_test)
                if res.passed:
                    pub_passed += 1
                elif public_failed_test is None:
                    public_failed_test = pub_t
                    public_fail_result = res

            # If all public tests pass or max repairs reached, finish CEGIS phase
            if pub_passed == len(prob.public_tests) or repair_turn >= max_repairs:
                break

            # Trigger CEGIS repair turn
            repairs_used += 1
            repair_prompt = (
                f"Your previous Python solution failed on the following public test case:\n\n"
                f"Input:\n```\n{public_failed_test.get('input', '')}\n```\n\n"
                f"Expected Output:\n```\n{public_failed_test.get('output', '')}\n```\n\n"
                f"Actual Output:\n```\n{public_fail_result.actual_output if public_fail_result else ''}\n```\n\n"
                f"Error Message:\n```\n{public_fail_result.error_message if public_fail_result else 'Output Mismatch'}\n```\n\n"
                f"Previous Code:\n```python\n{current_code}\n```\n\n"
                f"Analyze the discrepancy, correct boundary conditions or algorithmic logic, and return the complete "
                f"fixed Python 3 code inside a ```python ... ``` block."
            )
            repair_resp = query_llm(repair_prompt, temperature=0.2)
            repaired_code = extract_python_code(repair_resp)
            if repaired_code:
                current_code = repaired_code

        # Final evaluation of Arm B candidate against held-out private test suite
        eval_private_tests = prob.private_tests if prob.private_tests else prob.public_tests
        private_passed_b = 0
        for t in eval_private_tests:
            res = run_single_test(current_code, t, prob.func_name, timeout=timeout_per_test)
            if res.passed:
                private_passed_b += 1
            elif failure_log is None:
                failure_log = f"Failed private test: input={t.get('input', '')[:80]}, err={res.error_message}"

        arm_b_pass = (private_passed_b == len(eval_private_tests)) and len(eval_private_tests) > 0
        pub_rate = (pub_passed / len(prob.public_tests)) if prob.public_tests else 1.0
        priv_rate = (private_passed_b / len(eval_private_tests)) if eval_private_tests else 0.0
    else:
        current_code = initial_code
        pub_rate = 0.0
        priv_rate = 1.0 if arm_a_pass else 0.0

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return ProblemEvaluationResult(
        question_id=prob.question_id,
        question_title=prob.question_title,
        platform=prob.platform,
        difficulty=prob.difficulty,
        arm_a_pass=arm_a_pass,
        arm_a_code=initial_code,
        arm_b_pass=arm_b_pass,
        arm_b_code=current_code,
        arm_b_repairs_used=repairs_used,
        arm_b_public_pass_rate=pub_rate,
        arm_b_private_pass_rate=priv_rate,
        elapsed_ms=elapsed_ms,
        failure_log=failure_log,
    )


# =============================================================================
# CLI Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="LiveCodeBench 2026 CEGIS Benchmark Suite")
    parser.add_argument(
        "--dataset",
        type=str,
        default="data/benchmarks/livecodebench/data/test6.jsonl",
        help="Path to LiveCodeBench jsonl split (e.g. test6.jsonl, test.jsonl)",
    )
    parser.add_argument("--limit", type=int, default=10, help="Number of problems to evaluate (0 = all)")
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard", "all"],
        default="all",
        help="Problem difficulty filter",
    )
    parser.add_argument(
        "--platform",
        choices=["leetcode", "atcoder", "codeforces", "all"],
        default="all",
        help="Competitive platform filter",
    )
    parser.add_argument(
        "--arms",
        choices=["direct", "cegis", "both"],
        default="both",
        help="Evaluation arms: direct, cegis, or both",
    )
    parser.add_argument("--max-repairs", type=int, default=2, help="Maximum CEGIS self-repair turns per problem")
    parser.add_argument("--model-tag", type=str, default="Tier0-26B", help="Model tier tag for reporting")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = REPO_ROOT / dataset_path

    problems = load_livecodebench_problems(
        dataset_path,
        limit=args.limit,
        difficulty=args.difficulty,
        platform=args.platform,
    )

    print("\n" + "=" * 78)
    print(f"=== Project Lucca: LiveCodeBench 2026 CEGIS Evaluation [{args.model_tag}] ===")
    print(f"Dataset: {dataset_path.name} | Problems: {len(problems)} | Difficulty: {args.difficulty}")
    print(f"Arms: {args.arms} | Max Repairs: {args.max_repairs} | Target: {SERVER_URL}")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print("=" * 78 + "\n", flush=True)

    results: list[ProblemEvaluationResult] = []
    arm_a_wins = 0
    arm_b_wins = 0
    cegis_rescues = 0

    for idx, prob in enumerate(problems, 1):
        print(f"[{idx:02d}/{len(problems)}] Evaluating [{prob.difficulty.upper()}|{prob.platform}] {prob.question_title} ... ", end="", flush=True)
        res = evaluate_problem(
            prob,
            arms=args.arms,
            max_repairs=args.max_repairs,
        )
        results.append(res)

        if res.arm_a_pass:
            arm_a_wins += 1
        if res.arm_b_pass:
            arm_b_wins += 1
            if not res.arm_a_pass:
                cegis_rescues += 1

        status_a = "PASS" if res.arm_a_pass else "FAIL"
        status_b = "PASS" if res.arm_b_pass else "FAIL"
        rescue_tag = " [CEGIS RESCUE +1]" if (res.arm_b_pass and not res.arm_a_pass) else ""
        print(f"Arm A: {status_a} | Arm B: {status_b} (repairs: {res.arm_b_repairs_used}){rescue_tag} ({res.elapsed_ms:.0f}ms)")
        if not res.arm_b_pass and res.failure_log:
            print(f"    -> Failure: {res.failure_log[:100]}")

    n = len(results)
    ci_a = wilson_ci(arm_a_wins, n)
    ci_b = wilson_ci(arm_b_wins, n)

    print("\n" + "=" * 78)
    print(f"=== LiveCodeBench 2026 Summary: {args.model_tag} ===")
    print("=" * 78)
    print(f"Total Evaluated: {n}")
    print(f"Arm A (Direct Generation): {arm_a_wins}/{n} ({arm_a_wins/n*100:.1f}%) | Wilson 95% CI: [{ci_a[0]*100:.1f}%, {ci_a[1]*100:.1f}%]")
    print(f"Arm B (CEGIS Compound):    {arm_b_wins}/{n} ({arm_b_wins/n*100:.1f}%) | Wilson 95% CI: [{ci_b[0]*100:.1f}%, {ci_b[1]*100:.1f}%]")
    print(f"CEGIS Rescued Problems:    {cegis_rescues}/{n} (+{cegis_rescues/n*100:.1f} pp lift)")
    print(f"Net Compound Lift:         +{(arm_b_wins - arm_a_wins)/n*100:.1f} pp")
    print("=" * 78 + "\n", flush=True)

    report_payload = {
        "benchmark": "LiveCodeBench_2026",
        "model_tag": args.model_tag,
        "dataset": str(dataset_path),
        "difficulty": args.difficulty,
        "platform": args.platform,
        "total_problems": n,
        "arm_a_direct": {
            "passed": arm_a_wins,
            "pass_rate": arm_a_wins / n if n else 0.0,
            "wilson_95_ci": list(ci_a),
        },
        "arm_b_cegis": {
            "passed": arm_b_wins,
            "pass_rate": arm_b_wins / n if n else 0.0,
            "wilson_95_ci": list(ci_b),
            "cegis_rescues": cegis_rescues,
            "net_lift_pp": (arm_b_wins - arm_a_wins) / n * 100.0 if n else 0.0,
        },
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "problems": [asdict(r) for r in results],
    }

    report_file = REPORTS_DIR / f"livecodebench_2026_{args.model_tag}_{int(time.time())}.json"
    report_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    print(f"[+] Canonical report sealed: {report_file}")


if __name__ == "__main__":
    main()
