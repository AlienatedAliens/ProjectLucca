"""
Project Lucca — Modern 2024-2025 Frontier Academic Benchmark Battery
Evaluates:
  1. GSM-Symbolic (Apple, Oct 2024): Grade-school math under parameter/name perturbation
     and distractor clause insertion. Tested in PAL mode via Docker sandbox.
  2. HumanEval-Plus (EvalPlus, 2024): 164 canonical coding tasks subjected to 80x more
     adversarial inputs via differential testing in Docker against canonical oracle.
  3. MATH-500 (2024): Competition mathematics (AMC/AIME level) in PAL mode.

Usage:
  uv run python scripts/run_modern_2024_benchmarks.py --benchmark gsm-symbolic --samples 50
  uv run python scripts/run_modern_2024_benchmarks.py --benchmark humaneval-plus --samples 50
  uv run python scripts/run_modern_2024_benchmarks.py --benchmark math500 --samples 50
  uv run python scripts/run_modern_2024_benchmarks.py --benchmark all --samples 30
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.sandbox.rpc import DockerRPCTransport
from lucca.sandbox.service import SandboxService

DATA_DIR = REPO_ROOT / "data" / "benchmarks"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = REPO_ROOT / "logs" / "test_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# Dataset Fetchers
# ===========================================================================

def get_gsm_symbolic_dataset(subset: str = "symbolic") -> list[dict]:
    """
    Fetch Apple GSM-Symbolic dataset.
    Subsets: 'symbolic', 'p1' (1 distractor clause), 'p2' (2 distractor clauses).
    """
    filename_map = {
        "symbolic": "GSM_symbolic.jsonl",
        "p1": "GSM_p1.jsonl",
        "p2": "GSM_p2.jsonl",
    }
    filename = filename_map.get(subset, "GSM_symbolic.jsonl")
    cache_file = DATA_DIR / filename
    if not cache_file.exists():
        print(f"Downloading Apple GSM-Symbolic ({subset}) from GitHub repository...")
        url = f"https://raw.githubusercontent.com/apple/ml-gsm-symbolic/main/generated_data/{filename}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            cache_file.write_bytes(resp.read())
        print(f"  [OK] Saved GSM-Symbolic ({subset}) dataset to {cache_file}")

    lines = cache_file.read_text(encoding="utf-8").splitlines()
    data = [json.loads(line) for line in lines if line.strip()]
    return data


def get_humaneval_plus_dataset() -> list[dict]:
    """Fetch EvalPlus HumanEvalPlus dataset."""
    cache_file = DATA_DIR / "HumanEvalPlus.jsonl"
    if not cache_file.exists():
        print("Downloading HumanEvalPlus dataset (v0.1.10) from EvalPlus release...")
        url = "https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            decompressed = gzip.decompress(resp.read())
            cache_file.write_bytes(decompressed)
        print(f"  [OK] Saved HumanEvalPlus dataset to {cache_file}")

    lines = cache_file.read_text(encoding="utf-8").splitlines()
    data = [json.loads(line) for line in lines if line.strip()]
    return data


def get_math500_dataset() -> list[dict]:
    """Fetch HuggingFaceH4 MATH-500 test set."""
    cache_file = DATA_DIR / "math500_test.jsonl"
    if not cache_file.exists():
        print("Downloading MATH-500 dataset from HuggingFace...")
        url = "https://huggingface.co/datasets/HuggingFaceH4/MATH-500/raw/main/test.jsonl"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            cache_file.write_bytes(resp.read())
        print(f"  [OK] Saved MATH-500 dataset to {cache_file}")

    lines = cache_file.read_text(encoding="utf-8").splitlines()
    data = [json.loads(line) for line in lines if line.strip()]
    return data


# ===========================================================================
# LLM Interface
# ===========================================================================

def query_llm(prompt: str, max_tokens: int = 2048, enable_thinking: bool = False, retries: int = 2) -> str:
    """Query the local llama-server OpenAI-compatible endpoint with retry."""
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msg = data["choices"][0]["message"]
                return msg.get("content") or ""
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"   [WARN] LLM query failed after {retries} attempts: {exc}")
                return ""
    return ""


def extract_python_code(text: str) -> str:
    """Extract code from markdown blocks (closed or unclosed) or bare python."""
    code = ""
    # 1. Closed code block
    m = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        code = m.group(1).strip()
    elif (m := re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)):
        code = m.group(1).strip()
    # 2. Unclosed code block (e.g. truncated generation)
    elif "```python" in text:
        after = text.split("```python", 1)[1]
        code = after.split("```")[0].strip()
    elif "```" in text:
        after = text.split("```", 1)[1]
        code = after.split("```")[0].strip()
    else:
        # 3. Bare python lines (only if explicitly valid python lines)
        lines = text.strip().splitlines()
        code_lines = []
        for l in lines:
            trimmed = l.strip()
            if not trimmed:
                continue
            if any(trimmed.startswith(k) for k in ("import ", "from ", "def ", "class ", "print(", "return ", "if ", "elif ", "else:", "for ", "while ", "try:", "except")):
                code_lines.append(l)
        if len(code_lines) >= 2 or (len(code_lines) == 1 and any(code_lines[0].strip().startswith(k) for k in ("print(", "import "))):
            code = "\n".join(code_lines).strip()
        else:
            return ""

    if not code:
        return ""

    # Automatic syntax repair for unclosed docstrings
    if code.count('"""') % 2 != 0:
        code += '\n"""\n'
    if code.count("'''") % 2 != 0:
        code += "\n'''\n"

    return code


def extract_math_answer_from_text(text: str) -> str:
    """Extract final mathematical answer from model's textual response."""
    # 1. Look for \boxed{...}
    idx = text.rfind(r"\boxed{")
    if idx != -1:
        idx += len(r"\boxed{")
        depth = 1
        end_idx = idx
        while end_idx < len(text) and depth > 0:
            if text[end_idx] == "{":
                depth += 1
            elif text[end_idx] == "}":
                depth -= 1
            end_idx += 1
        return text[idx : end_idx - 1].strip()

    # 2. Look for numeric or symbolic equality (e.g. "answer is 28", "x = 28", "= 28")
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return ""

    for l in reversed(lines[-5:]):
        m = re.search(r"(?:the (?:final )?answer is|therefore,?\s*(?:x\s*=)?|x\s*=|finally,?\s*)\s*[:=]?\s*[$]?\s*([-+]?\d+(?:\.\d+)?(?:/\d+)?|[a-zA-Z\\]+)\s*[$]?", l, re.IGNORECASE)
        if m:
            ans = m.group(1).strip()
            if ans and ans.lower() not in ("the", "a", "an", "is", "this", "that", "equal", "equals", "angle", "line"):
                return ans

    # 3. Look for the last standalone number or token on the last line
    last_line = lines[-1].replace("$", "").strip()
    m_num = re.search(r"[-+]?\d+(?:\.\d+)?(?:/\d+)?", last_line)
    if m_num:
        return m_num.group(0)

    return ""


def extract_gsm_ground_truth(answer_str: str) -> float | None:
    """Extract numeric answer following ####."""
    if "####" in answer_str:
        num_part = answer_str.split("####")[-1].strip().replace(",", "").replace("$", "")
        # Remove units if any
        m = re.search(r"[-+]?\d*\.?\d+", num_part)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                pass
    return None


def extract_math500_ground_truth(solution_str: str) -> str:
    """Extract answer from \\boxed{...} in LaTeX solution."""
    # Find last \boxed{...}
    idx = solution_str.rfind(r"\boxed{")
    if idx == -1:
        return solution_str.strip()
    idx += len(r"\boxed{")
    depth = 1
    end_idx = idx
    while end_idx < len(solution_str) and depth > 0:
        if solution_str[end_idx] == "{":
            depth += 1
        elif solution_str[end_idx] == "}":
            depth -= 1
        end_idx += 1
    return solution_str[idx : end_idx - 1].strip()


def normalize_math_str(s: str) -> str:
    """Normalize LaTeX and plain mathematical expressions for robust equivalence checking."""
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\left\(", "(", s)
    s = re.sub(r"\\right\)", ")", s)
    s = re.sub(r"\\left\[", "[", s)
    s = re.sub(r"\\right\]", "]", s)
    s = re.sub(r"\\left\\{", "{", s)
    s = re.sub(r"\\right\\}", "}", s)
    s = re.sub(r"\\left\b", "", s)
    s = re.sub(r"\\right\b", "", s)
    s = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"\1/\2", s)
    s = re.sub(r"\\sqrt\{([^}]*)\}", r"sqrt(\1)", s)
    s = re.sub(r"(\d+)\s*\*\s*sqrt", r"\1sqrt", s)
    s = re.sub(r"\\pi\b", "pi", s)
    s = re.sub(r"^[a-zA-Z]\s*=\s*", "", s)
    s = s.strip("[]")
    s = re.sub(r"\bI\b", "i", s)
    s = re.sub(r"\*i\b", "i", s)
    s = re.sub(r"(\d+)\.0\b", r"\1", s)
    s = s.replace(" ", "").replace("$", "").replace("\\", "").rstrip(".")
    return s


def compare_math_results(pred_str: str, expected_ans: str) -> bool:
    """Check mathematical equivalence between predicted and expected solutions."""
    p_norm = normalize_math_str(pred_str)
    e_norm = normalize_math_str(expected_ans)
    if not p_norm or not e_norm:
        return False
    if p_norm == e_norm:
        return True

    # 1. Check comma-separated sets (e.g. roots '-2, 1' vs '1, -2')
    if "," in p_norm and "," in e_norm:
        p_set = {x.strip() for x in p_norm.split(",") if x.strip()}
        e_set = {x.strip() for x in e_norm.split(",") if x.strip()}
        if p_set == e_set:
            return True

    # 2. Arithmetic and complex evaluation
    try:
        import math
        context = {"sqrt": math.sqrt, "pi": math.pi}
        p_val = eval(p_norm.replace("i", "*1j"), {"__builtins__": None}, context)
        e_val = eval(e_norm.replace("i", "*1j"), {"__builtins__": None}, context)
        if abs(p_val - e_val) < 1e-4:
            return True
    except Exception:
        pass

    return False


# ===========================================================================
# Benchmark Runners
# ===========================================================================

def run_gsm_symbolic(transport: DockerRPCTransport, subset: str = "symbolic", samples: int = 50, offset: int = 0) -> dict:
    """Evaluate Apple GSM-Symbolic in PAL Mode (Docker Python execution)."""
    dataset = get_gsm_symbolic_dataset(subset=subset)
    if offset > 0:
        dataset = dataset[offset:]
    if samples > 0 and samples < len(dataset):
        dataset = dataset[:samples]

    print(f"\n=======================================================")
    print(f"Running Apple GSM-Symbolic [{subset}] in PAL Mode ({len(dataset)} problems)")
    print(f"Method: Program-Aided Language (Docker Python Execution)")
    print(f"=======================================================")

    results = []
    passed_count = 0
    t_start = time.perf_counter()

    for idx, item in enumerate(dataset, 1):
        q = item["question"]
        gt_raw = item["answer"]
        gt_val = extract_gsm_ground_truth(gt_raw)

        prompt = (
            "You are a precise mathematical assistant. Solve the following word problem by writing "
            "a clean Python script that computes the answer and prints ONLY the final numeric value.\n"
            "Put all Python code inside a single ```python ... ``` block. Define all necessary variables.\n\n"
            f"Problem: {q}\n"
        )

        t0 = time.perf_counter()
        resp = query_llm(prompt=prompt, max_tokens=1024, enable_thinking=False)
        t_llm = time.perf_counter() - t0

        code = extract_python_code(resp)
        exec_res = transport.execute(f"gsm-sym-{idx}", "run_python", {"code": code}, timeout_s=15)

        pred_val = None
        output_text = exec_res.content or ""
        if exec_res.exit_code == 0 and output_text:
            stdout_clean = output_text.strip().replace(",", "").replace("$", "")
            tokens = stdout_clean.split()
            if tokens:
                m = re.search(r"[-+]?\d*\.?\d+", tokens[-1])
                if m:
                    try:
                        pred_val = float(m.group(0))
                    except ValueError:
                        pass

        is_pass = False
        if gt_val is not None and pred_val is not None:
            is_pass = abs(gt_val - pred_val) < 1e-4

        if is_pass:
            passed_count += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"

        print(f"[{idx:03d}/{len(dataset)}] {status_str} | Pred: {pred_val} | Expected: {gt_val} | Latency: {t_llm:.2f}s", flush=True)
        if not is_pass and code:
            snippet = code.replace("\n", " ")[:60]
            print(f"   Code snippet: {snippet}...", flush=True)

        results.append({
            "idx": idx,
            "id": item.get("id"),
            "instance": item.get("instance"),
            "question": q,
            "generated_code": code,
            "stdout": exec_res.content,
            "stderr": exec_res.stderr,
            "pred_val": pred_val,
            "expected_val": gt_val,
            "passed": is_pass,
            "llm_latency_s": round(t_llm, 3),
        })

    elapsed = time.perf_counter() - t_start
    acc = (passed_count / len(dataset)) * 100.0 if dataset else 0.0

    print(f"\n--- GSM-Symbolic [{subset}] PAL Summary ---", flush=True)
    print(f"Total: {len(dataset)} | Passed: {passed_count} | Accuracy: {acc:.1f}% | Elapsed: {elapsed:.1f}s\n", flush=True)

    return {
        "benchmark": f"GSM_Symbolic_{subset}",
        "total": len(dataset),
        "passed": passed_count,
        "accuracy_pct": round(acc, 2),
        "elapsed_s": round(elapsed, 2),
        "results": results,
    }


def run_humaneval_plus(transport: DockerRPCTransport, samples: int = 50, offset: int = 0) -> dict:
    """
    Evaluate EvalPlus HumanEval-Plus pass@1 via Docker differential testing.
    Runs both base_input and plus_input (adversarial test cases) against canonical_solution.
    """
    dataset = get_humaneval_plus_dataset()
    if offset > 0:
        dataset = dataset[offset:]
    if samples > 0 and samples < len(dataset):
        dataset = dataset[:samples]

    print(f"\n=======================================================")
    print(f"Running HumanEval-Plus ({len(dataset)} coding tasks)")
    print(f"Method: pass@1 via Docker Differential Execution (Base + 80x Plus Inputs)")
    print(f"=======================================================")

    results = []
    passed_count = 0
    t_start = time.perf_counter()
    sandbox_service = SandboxService()

    for idx, item in enumerate(dataset, 1):
        task_id = item["task_id"]
        prompt = item["prompt"]
        entry_point = item["entry_point"]
        canonical_solution = item["canonical_solution"]
        atol = item.get("atol", 1e-6)
        base_inputs = item.get("base_input", [])
        plus_inputs = item.get("plus_input", [])
        all_inputs = base_inputs + plus_inputs

        instruction = (
            "Complete the following Python function. Provide only the valid Python implementation.\n"
            "Do not include explanation text; put the completed code inside a ```python ... ``` block.\n\n"
            f"{prompt}"
        )

        t0 = time.perf_counter()
        resp = query_llm(prompt=instruction, max_tokens=1024, enable_thinking=False)
        t_llm = time.perf_counter() - t0

        completion_code = extract_python_code(resp)
        if prompt.strip() in completion_code:
            candidate_code = completion_code
        else:
            candidate_code = f"{prompt}\n{completion_code}"

        # Phase 4 Autonomous Preflight Verification Loop (Docker Self-Correction)
        try:
            preflight_res = sandbox_service.preflight_verify_code(candidate_code)
            if not preflight_res.success and preflight_res.error_msg and preflight_res.assertions_run > 0:
                print(f"   [Preflight Triggered] Task {task_id} failed docstrings ({preflight_res.assertions_run} tested) -> Self-correcting...")
                correction_prompt = (
                    f"The following implementation for `{entry_point}` was tested in the execution sandbox "
                    f"and failed specification docstring assertions:\n\n"
                    f"```python\n{candidate_code}\n```\n\n"
                    f"Execution Error / Assertion Failure:\n{preflight_res.error_msg}\n\n"
                    f"Please fix the implementation so that it passes all specification assertions. "
                    f"Provide ONLY the completed code in a ```python ... ``` block."
                )
                t_corr0 = time.perf_counter()
                corrected_resp = query_llm(prompt=correction_prompt, max_tokens=1024, enable_thinking=False)
                t_llm += (time.perf_counter() - t_corr0)
                corrected_code = extract_python_code(corrected_resp)
                if corrected_code:
                    if prompt.strip() in corrected_code:
                        candidate_code = corrected_code
                    else:
                        candidate_code = f"{prompt}\n{corrected_code}"
        except Exception as pf_exc:
            print(f"   [Preflight Warn] Preflight execution failed: {pf_exc}")

        # Build differential testing runner in python for Docker
        # Serializes inputs and runs comparison in-process
        runner_script = f"""
import sys
import math
import copy
import json

true = True
false = False
null = None

{candidate_code}

# Rename candidate function
candidate_fn = {entry_point}

# Define oracle reference
{prompt}
{canonical_solution}
canonical_fn = {entry_point}

atol = {atol}
inputs = {json.dumps(all_inputs)}

def are_equal(a, b, atol=1e-6):
    if a == b:
        return True
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, abs_tol=atol)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
        return all(are_equal(x, y, atol) for x, y in zip(a, b))
    return False

failures = 0
for i, inp in enumerate(inputs):
    try:
        inp_copy1 = copy.deepcopy(inp)
        inp_copy2 = copy.deepcopy(inp)
        actual = candidate_fn(*inp_copy2)
        if "{entry_point}" == "find_zero":
            if abs(poly(inp_copy2[0], actual)) > 1e-2:
                print(f"ROOT FAILURE at input {{i}}: poly({{actual}}) = {{poly(inp_copy2[0], actual)}}")
                failures += 1
                break
        else:
            expected = canonical_fn(*inp_copy1)
            if not are_equal(actual, expected, atol):
                print(f"MISMATCH at input {{i}}: expected {{expected!r}}, got {{actual!r}}")
                failures += 1
                break
    except Exception as exc:
        print(f"EXCEPTION at input {{i}}: {{exc}}")
        failures += 1
        break

if failures == 0:
    print(f"ALL {{len(inputs)}} TESTS PASSED")
    sys.exit(0)
else:
    sys.exit(1)
"""

        exec_res = transport.execute(f"he-plus-{idx}", "run_python", {"code": runner_script}, timeout_s=30)
        is_pass = (exec_res.exit_code == 0)

        if is_pass:
            passed_count += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"

        print(f"[{idx:03d}/{len(dataset)}] {status_str} | Task: {task_id} | Entry: {entry_point} | Inputs: {len(all_inputs)} | Latency: {t_llm:.2f}s", flush=True)
        out_text = exec_res.content or ""
        if not is_pass and out_text:
            first_err = out_text.strip().splitlines()[0] if out_text.strip() else ""
            print(f"   Failure detail: {first_err[:120]}", flush=True)
        elif not is_pass and exec_res.stderr:
            print(f"   Stderr: {exec_res.stderr.strip()[:120]}", flush=True)

        results.append({
            "task_id": task_id,
            "entry_point": entry_point,
            "inputs_tested": len(all_inputs),
            "passed": is_pass,
            "candidate_code": candidate_code,
            "exit_code": exec_res.exit_code,
            "stdout": exec_res.content,
            "stderr": exec_res.stderr,
            "llm_latency_s": round(t_llm, 3),
        })

    elapsed = time.perf_counter() - t_start
    pass_rate = (passed_count / len(dataset)) * 100.0 if dataset else 0.0

    print(f"\n--- HumanEval-Plus Summary ---", flush=True)
    print(f"Total: {len(dataset)} | Passed: {passed_count} | Pass@1: {pass_rate:.1f}% | Elapsed: {elapsed:.1f}s\n", flush=True)

    return {
        "benchmark": "HumanEvalPlus",
        "total": len(dataset),
        "passed": passed_count,
        "pass_at_1_pct": round(pass_rate, 2),
        "elapsed_s": round(elapsed, 2),
        "results": results,
    }


def run_math500_pal(transport: DockerRPCTransport, samples: int = 50, offset: int = 0) -> dict:
    """Evaluate MATH-500 competition math in PAL mode via Docker Python/SymPy."""
    dataset = get_math500_dataset()
    if offset > 0:
        dataset = dataset[offset:]
    if samples > 0 and samples < len(dataset):
        dataset = dataset[:samples]

    print(f"\n=======================================================")
    print(f"Running MATH-500 in PAL Mode ({len(dataset)} competition math problems)")
    print(f"Method: Program-Aided Language (Docker SymPy / Python Execution)")
    print(f"=======================================================")

    results = []
    passed_count = 0
    t_start = time.perf_counter()

    for idx, item in enumerate(dataset, 1):
        problem = item["problem"]
        solution = item["solution"]
        expected_ans = extract_math500_ground_truth(solution)
        subject = item.get("subject", "math")
        level = item.get("level", 0)

        prompt = (
            f"You are a competition mathematician and computer algebra expert. Solve the following problem by writing "
            f"a complete Python script using SymPy or arithmetic that computes and prints ONLY the final exact answer.\n"
            f"Rules:\n"
            f"1. Start directly with ```python and provide all your code and comments inside the code block.\n"
            f"2. Simplify all expressions completely before printing. Print only the exact mathematical value, without labels (e.g. print `5`, not `x = 5`).\n"
            f"3. For complex numbers, print in standard form a + b*I. For multiple values, print comma-separated.\n\n"
            f"Problem: {problem}\n"
        )

        t0 = time.perf_counter()
        resp = query_llm(prompt=prompt, max_tokens=2048, enable_thinking=False)
        t_llm = time.perf_counter() - t0

        code = extract_python_code(resp)
        pred_str = ""
        exec_res_exit = 0
        exec_res_stderr = ""
        if code:
            exec_res = transport.execute(f"math500-{idx}", "run_python", {"code": code}, timeout_s=20)
            exec_res_exit = exec_res.exit_code
            exec_res_stderr = exec_res.stderr or ""
            math_out = exec_res.content or ""
            if exec_res.exit_code == 0 and math_out:
                lines = [l.strip() for l in math_out.strip().splitlines() if l.strip()]
                if lines:
                    pred_str = lines[-1]

        # Robust text fallback if code failed or no code was produced
        if not pred_str:
            pred_str = extract_math_answer_from_text(resp)

        # Use robust mathematical equivalence comparison
        is_pass = compare_math_results(pred_str, expected_ans)

        if is_pass:
            passed_count += 1
            status_str = "PASS"
        else:
            status_str = "FAIL"

        print(f"[{idx:03d}/{len(dataset)}] {status_str} | Subj: {subject} (L{level}) | Pred: {pred_str[:30]} | Expected: {expected_ans[:30]} | Latency: {t_llm:.2f}s", flush=True)
        if not is_pass and exec_res_stderr:
            print(f"   Stderr: {exec_res_stderr.strip()[:100]}", flush=True)

        results.append({
            "idx": idx,
            "subject": subject,
            "level": level,
            "problem": problem,
            "expected_ans": expected_ans,
            "predicted_ans": pred_str,
            "passed": is_pass,
            "generated_code": code,
            "exit_code": exec_res_exit,
            "stderr": exec_res_stderr,
            "llm_latency_s": round(t_llm, 3),
        })

    elapsed = time.perf_counter() - t_start
    acc = (passed_count / len(dataset)) * 100.0 if dataset else 0.0

    print(f"\n--- MATH-500 PAL Summary ---")
    print(f"Total: {len(dataset)} | Passed: {passed_count} | Accuracy: {acc:.1f}% | Elapsed: {elapsed:.1f}s\n")

    return {
        "benchmark": "MATH-500",
        "total": len(dataset),
        "passed": passed_count,
        "accuracy_pct": round(acc, 2),
        "elapsed_s": round(elapsed, 2),
        "results": results,
    }


# ===========================================================================
# Main Entry Point
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Run 2024-2025 Modern Academic Benchmarks")
    parser.add_argument(
        "--benchmark",
        choices=["gsm-symbolic", "gsm-p1", "humaneval-plus", "math500", "all"],
        default="all",
        help="Benchmark to evaluate",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=50,
        help="Number of samples to evaluate (0 for full dataset)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Offset index in dataset to start from",
    )
    args = parser.parse_args()

    print("Initializing DockerRPCTransport...")
    transport = DockerRPCTransport(container_name="lucca-file-sandbox")
    transport.ensure_container_running()

    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    final_report = {
        "timestamp": timestamp,
        "model": "gemma-4-12b-heretic-Q6_K.gguf",
        "benchmarks": {},
    }

    if args.benchmark in ("gsm-symbolic", "all"):
        final_report["benchmarks"]["gsm_symbolic"] = run_gsm_symbolic(transport, subset="symbolic", samples=args.samples, offset=args.offset)

    if args.benchmark == "gsm-p1":
        final_report["benchmarks"]["gsm_p1"] = run_gsm_symbolic(transport, subset="p1", samples=args.samples, offset=args.offset)

    if args.benchmark in ("humaneval-plus", "all"):
        final_report["benchmarks"]["humaneval_plus"] = run_humaneval_plus(transport, samples=args.samples, offset=args.offset)

    if args.benchmark in ("math500", "all"):
        final_report["benchmarks"]["math500"] = run_math500_pal(transport, samples=args.samples, offset=args.offset)

    report_file = REPORTS_DIR / f"modern_benchmarks_2024_{timestamp}.json"
    report_file.write_text(json.dumps(final_report, indent=2), encoding="utf-8")
    print(f"\n[OK] Modern 2024 benchmark report saved to: {report_file}")


if __name__ == "__main__":
    main()
