"""
Project Lucca — Full Apple GSM-Symbolic Evaluation Harness
============================================================
Evaluates all GSM-Symbolic variants (Mirzadeh et al., Oct 2024) in two modes:

  Mode A — Bare CoT (no tools):
    Direct LLM chain-of-thought using Apple's official 8-shot prompt template.
    Establishes what the raw 12B neural core achieves without tool assistance.
    Documents the "symbolic slip" degradation curve on NoOp distractors.

  Mode B — Compound PAL (Docker Python execution):
    Program-Aided Language: LLM writes Python, Docker sandbox executes it.
    Irrelevant distractor clauses in NoOp variants are never assigned to
    variables → they vanish during code synthesis → expected 0% degradation.

Datasets (all in data/benchmarks/, Apple repo + HuggingFace):
  GSM_symbolic.jsonl     — 5,000 items (base, 100 templates × 50 instances)
  GSM_p1.jsonl           — 5,000 items (P1: +1 extra clause, harder)
  GSM_p2.jsonl           — 2,500 items (P2: +2 extra clauses, hardest)
  GSM_noop_100.jsonl     — 945 items  (NoOp: irrelevant distractor injected)
  GSM_noop_100_filtered.jsonl — 338 items (Claude Opus-audited clean distractors)

Published baselines (Apple paper, Table 1 — GPT-4o greedy):
  GSM-Symbolic:     95.2%
  GSM-Symbolic-P1:  93.5%
  GSM-Symbolic-P2:  90.7%
  GSM-NoOp:         ~77% (catastrophic distractor-trap failures in CoT)

Usage:
  uv run python scripts/run_full_gsm_symbolic.py
  uv run python scripts/run_full_gsm_symbolic.py --variant noop
  uv run python scripts/run_full_gsm_symbolic.py --variant symbolic p1 p2 noop
  uv run python scripts/run_full_gsm_symbolic.py --mode cot --variant noop
  uv run python scripts/run_full_gsm_symbolic.py --samples 100
  uv run python scripts/run_full_gsm_symbolic.py --no-resume
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DATA_DIR = REPO_ROOT / "data" / "benchmarks"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = REPO_ROOT / "logs" / "test_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Variant Registry
# ---------------------------------------------------------------------------

VARIANT_META: dict[str, dict] = {
    "symbolic": {
        "key": "symbolic",
        "label": "GSM-Symbolic (Base)",
        "filename": "GSM_symbolic.jsonl",
        "download_url": "https://raw.githubusercontent.com/apple/ml-gsm-symbolic/main/generated_data/GSM_symbolic.jsonl",
        "has_distractor": False,
        "instances_per_template": 50,
        "description": "Base symbolic variant. Parameter names/values perturbed from GSM8K originals.",
    },
    "p1": {
        "key": "p1",
        "label": "GSM-Symbolic-P1",
        "filename": "GSM_p1.jsonl",
        "download_url": "https://raw.githubusercontent.com/apple/ml-gsm-symbolic/main/generated_data/GSM_p1.jsonl",
        "has_distractor": False,
        "instances_per_template": 50,
        "description": "Harder: 1 additional clause added to each problem, increasing complexity.",
    },
    "p2": {
        "key": "p2",
        "label": "GSM-Symbolic-P2",
        "filename": "GSM_p2.jsonl",
        "download_url": "https://raw.githubusercontent.com/apple/ml-gsm-symbolic/main/generated_data/GSM_p2.jsonl",
        "has_distractor": False,
        "instances_per_template": 50,
        "description": "Hardest: 2 additional clauses added. Maximum complexity increase.",
    },
    "noop": {
        "key": "noop",
        "label": "GSM-NoOp (All)",
        "filename": "GSM_noop_100.jsonl",
        "download_url": "https://huggingface.co/datasets/Experimental-Orange/gsm-noop-audited/raw/main/distractors/GSM_noop_100.jsonl",
        "has_distractor": True,
        "instances_per_template": None,
        "description": "NoOp distractor: semantically irrelevant clause injected. Compound PAL should show 0% degradation.",
    },
    "noop_filtered": {
        "key": "noop_filtered",
        "label": "GSM-NoOp (Filtered — Unambiguous)",
        "filename": "GSM_noop_100_filtered.jsonl",
        "download_url": "https://huggingface.co/datasets/Experimental-Orange/gsm-noop-audited/raw/main/distractors/GSM_noop_100_filtered_opus.jsonl",
        "has_distractor": True,
        "instances_per_template": None,
        "description": "Claude Opus-audited subset: only distractors confirmed unambiguously irrelevant.",
    },
}

ALL_VARIANT_KEYS = list(VARIANT_META.keys())

# Apple's official 8-shot GSM8K CoT prompt (from lm-evaluation-harness)
# Abbreviated to 4 shots here to reduce context usage at 32K
APPLE_COT_SHOTS = """As an expert problem solver, solve step by step the following mathematical questions.

Q: There are 15 trees in the grove. Grove workers will plant trees in the grove today. After they are done, there will be 21 trees. How many trees did the grove workers plant today?
A: Let's think step by step. There are 15 trees originally. Then there were 21 trees after some more were planted. So there must have been 21 - 15 = 6. The final answer is 6.

Q: If there are 3 cars in the parking lot and 2 more cars arrive, how many cars are in the parking lot?
A: Let's think step by step. There are originally 3 cars. 2 more cars arrive. 3 + 2 = 5. The final answer is 5.

Q: Leah had 32 chocolates and her sister had 42. If they ate 35, how many pieces do they have left in total?
A: Let's think step by step. Originally, Leah had 32 chocolates. Her sister had 42. So in total they had 32 + 42 = 74. After eating 35, they had 74 - 35 = 39. The final answer is 39.

Q: Jason had 20 lollipops. He gave Denny some lollipops. Now Jason has 12 lollipops. How many lollipops did Jason give to Denny?
A: Let's think step by step. Jason started with 20 lollipops. Then he had 12 after giving some to Denny. So he gave Denny 20 - 12 = 8. The final answer is 8.

Q: Shawn has five toys. For Christmas, he got two toys each from his mom and dad. How many toys does he have now?
A: Let's think step by step. Shawn started with 5 toys. If he got 2 toys each from his mom and dad, then that is 4 more toys. 5 + 4 = 9. The final answer is 9.

Q: There were nine computers in the server room. Five more computers were installed each day, from Monday to Thursday. How many computers are now in the server room?
A: Let's think step by step. There were originally 9 computers. For each of 4 days, 5 more computers were added. So 5 * 4 = 20 computers were added. 9 + 20 = 29. The final answer is 29.

Q: Michael had 58 golf balls. On Tuesday, he lost 23 golf balls. On Wednesday, he lost 2 more. How many golf balls did he have at the end of Wednesday?
A: Let's think step by step. Michael started with 58 golf balls. After losing 23 on Tuesday, he had 58 - 23 = 35. After losing 2 more on Wednesday, he had 35 - 2 = 33. The final answer is 33.

Q: Olivia has $23. She bought five bagels for $3 each. How much money does she have left?
A: Let's think step by step. Olivia had 23 dollars. 5 bagels for 3 dollars each will be 5 x 3 = 15 dollars. So she has 23 - 15 = 8 dollars left. The final answer is 8.

"""


# ---------------------------------------------------------------------------
# Dataset Loaders
# ---------------------------------------------------------------------------

def load_dataset(variant_key: str) -> list[dict]:
    """Load a GSM-Symbolic variant from cache or download."""
    meta = VARIANT_META[variant_key]
    cache = DATA_DIR / meta["filename"]
    if not cache.exists():
        print(f"  Downloading {meta['label']} from {meta['download_url']} ...", flush=True)
        req = urllib.request.Request(meta["download_url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            cache.write_bytes(resp.read())
        print(f"  Saved: {cache.name} ({cache.stat().st_size:,} bytes)", flush=True)

    lines = [l for l in cache.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


# ---------------------------------------------------------------------------
# LLM Query
# ---------------------------------------------------------------------------

def query_llm(prompt: str, max_tokens: int = 768, retries: int = 2) -> str:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": 42,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msg = data["choices"][0]["message"]
                return (msg.get("content") or msg.get("reasoning_content") or "").strip()
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"   [WARN] LLM query failed: {exc}", flush=True)
                return ""
    return ""


# ---------------------------------------------------------------------------
# Answer Extraction
# ---------------------------------------------------------------------------

def extract_ground_truth(item: dict, variant_key: str) -> float | None:
    """Extract gold numeric answer from a dataset item."""
    # NoOp variants have a pre-parsed gold_answer field
    if variant_key in ("noop", "noop_filtered") and "gold_answer" in item:
        try:
            return float(item["gold_answer"])
        except (ValueError, TypeError):
            pass
    # Standard GSM format: last line is "#### <number>"
    answer_str = item.get("answer", "")
    if "####" in answer_str:
        raw = answer_str.split("####")[-1].strip().replace(",", "").replace("$", "")
        m = re.search(r"[-+]?\d*\.?\d+", raw)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                pass
    return None


def extract_cot_answer(text: str) -> float | None:
    """
    Extract final numeric answer from CoT response using Apple's official heuristic:
    Remove commas, find the last number in the response.
    """
    # Stop generation if model starts a new question (few-shot hallucination)
    for stop in ("Q:", "\nQ ", "Question:", "<eos>"):
        if stop in text:
            text = text[: text.index(stop)]
    text = text.replace(",", "")
    nums = re.findall(r"-?\d+\.?\d*", text)
    if nums:
        try:
            return float(nums[-1])
        except ValueError:
            pass
    return None


def extract_pal_answer(stdout: str) -> float | None:
    """Extract numeric answer from Docker Python stdout."""
    cleaned = (stdout or "").strip().replace(",", "").replace("$", "")
    tokens = cleaned.split()
    if tokens:
        m = re.search(r"[-+]?\d*\.?\d+", tokens[-1])
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                pass
    return None


def extract_python_code(text: str) -> str:
    """Extract Python code from markdown fenced blocks or bare code."""
    # Fenced block
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Generic fence
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        code = m.group(1).strip()
        if any(kw in code for kw in ("def ", "import ", "print(", "=")):
            return code
    return text.strip()


def answers_match(pred: float | None, gold: float | None) -> bool:
    if pred is None or gold is None:
        return False
    return abs(pred - gold) < 1e-4


# ---------------------------------------------------------------------------
# Prompt Builders
# ---------------------------------------------------------------------------

def build_cot_prompt(question: str) -> str:
    """Apple's official 8-shot CoT prompt template."""
    return f"{APPLE_COT_SHOTS}Q: {question}\nA: Let's think step by step."


def build_pal_prompt(question: str) -> str:
    """PAL prompt: instruct the model to write executable Python."""
    return (
        "You are a precise mathematical assistant. Solve the following word problem by "
        "writing a clean Python script that computes the answer and prints ONLY the final "
        "numeric value as the last output.\n"
        "Put all Python code inside a single ```python ... ``` block.\n"
        "Define all variables with meaningful names matching the problem.\n"
        "Only assign variables for quantities that are actually relevant to the final answer.\n\n"
        f"Problem: {question}\n"
    )


# ---------------------------------------------------------------------------
# Checkpoint I/O
# ---------------------------------------------------------------------------

def load_checkpoint(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_checkpoint(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core Evaluation Runner (single variant, single mode)
# ---------------------------------------------------------------------------

def run_variant(
    variant_key: str,
    mode: str,
    samples: int = 0,
    resume_data: dict | None = None,
    transport=None,
) -> dict:
    """
    Run a single (variant, mode) combination.
    mode: 'cot' (Bare CoT) or 'pal' (Compound PAL via Docker)
    """
    if mode == "pal" and transport is None:
        raise ValueError("PAL mode requires a DockerRPCTransport instance.")

    meta = VARIANT_META[variant_key]
    dataset = load_dataset(variant_key)
    if samples > 0 and samples < len(dataset):
        dataset = dataset[:samples]

    run_key = f"{variant_key}_{mode}"
    already_done = (resume_data or {}).get(run_key, {}).get("results", [])
    already_idx = {r["idx"] for r in already_done}
    resume_results = list(already_done)

    print(f"\n{'='*65}", flush=True)
    print(f"[{mode.upper()}] {meta['label']}  ({variant_key})", flush=True)
    print(f"  Distractor: {'YES — NoOp clause injected' if meta['has_distractor'] else 'No'}", flush=True)
    print(f"  Total problems: {len(dataset)} | Already done: {len(already_idx)}", flush=True)
    print(f"{'='*65}", flush=True)

    passed = sum(1 for r in resume_results if r["passed"])
    t_start = time.perf_counter()

    for idx, item in enumerate(dataset, 1):
        if idx in already_idx:
            continue

        question = item["question"]
        gold = extract_ground_truth(item, variant_key)

        if mode == "cot":
            prompt = build_cot_prompt(question)
            t0 = time.perf_counter()
            resp = query_llm(prompt, max_tokens=512)
            t_llm = time.perf_counter() - t0
            pred = extract_cot_answer(resp)
            code = None
            stdout = None
            distractor_triggered = False

            # Distractor trap detection for CoT: check if model used distractor number
            if meta["has_distractor"] and "added_clause" in item:
                # Extract numbers from added_clause; check if they appear in response
                clause_nums = re.findall(r"\d+\.?\d*", item.get("added_clause", ""))
                resp_nums = re.findall(r"\d+\.?\d*", resp)
                distractor_triggered = any(n in resp_nums for n in clause_nums) and not answers_match(pred, gold)

        else:  # pal
            prompt = build_pal_prompt(question)
            t0 = time.perf_counter()
            resp = query_llm(prompt, max_tokens=1024)
            t_llm = time.perf_counter() - t0
            code = extract_python_code(resp)
            exec_res = transport.execute(f"gsm-sym-{run_key}-{idx}", "run_python", {"code": code}, timeout_s=15)
            stdout = exec_res.content or ""
            pred = extract_pal_answer(stdout) if exec_res.exit_code == 0 else None
            distractor_triggered = False  # PAL never triggers distractor traps

        is_pass = answers_match(pred, gold)
        if is_pass:
            passed += 1

        status = "PASS" if is_pass else "FAIL"
        trap_tag = " [TRAP]" if distractor_triggered else ""
        print(
            f"[{idx:03d}/{len(dataset)}] {status}{trap_tag} | "
            f"pred={pred} gold={gold} | {t_llm:.1f}s",
            flush=True,
        )

        result_entry: dict = {
            "idx": idx,
            "id": item.get("id"),
            "instance": item.get("instance"),
            "question": question[:200],
            "gold": gold,
            "pred": pred,
            "passed": is_pass,
            "latency_s": round(t_llm, 3),
        }
        if meta["has_distractor"]:
            result_entry["added_clause"] = item.get("added_clause", "")
            result_entry["why_irrelevant"] = item.get("why_irrelevant", "")
            result_entry["distractor_triggered"] = distractor_triggered
        if mode == "pal":
            result_entry["code_snippet"] = (code or "")[:300]
            result_entry["stdout"] = (stdout or "")[:200]

        resume_results.append(result_entry)

    total = len(resume_results)
    final_passed = sum(1 for r in resume_results if r["passed"])
    acc = (final_passed / total * 100.0) if total else 0.0
    elapsed = time.perf_counter() - t_start

    # Distractor trap stats for NoOp variants
    distractor_traps = 0
    if meta["has_distractor"] and mode == "cot":
        distractor_traps = sum(1 for r in resume_results if r.get("distractor_triggered"))

    print(f"\n  {meta['label']} [{mode.upper()}]: {final_passed}/{total} ({acc:.1f}%)", flush=True)
    if meta["has_distractor"] and mode == "cot":
        trap_rate = (distractor_traps / total * 100.0) if total else 0.0
        print(f"  Distractor trap rate: {distractor_traps}/{total} ({trap_rate:.1f}%)", flush=True)

    return {
        "variant": variant_key,
        "mode": mode,
        "label": meta["label"],
        "has_distractor": meta["has_distractor"],
        "total": total,
        "passed": final_passed,
        "accuracy_pct": round(acc, 2),
        "elapsed_s": round(elapsed, 2),
        "distractor_traps": distractor_traps if meta["has_distractor"] else None,
        "complete": True,
        "results": resume_results,
    }


# ---------------------------------------------------------------------------
# Full Suite Runner
# ---------------------------------------------------------------------------

def run_full_gsm_symbolic(
    variants: list[str],
    modes: list[str],
    samples: int = 0,
    resume: bool = True,
) -> dict:
    """
    Run all requested (variant × mode) combinations.
    modes: subset of ['cot', 'pal']
    """
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    ckpt_path = REPORTS_DIR / "gsm_symbolic_full_checkpoint.json"
    report_path = REPORTS_DIR / f"gsm_symbolic_full_{timestamp}.json"

    checkpoint = load_checkpoint(ckpt_path) if resume else {}
    run_results: dict = checkpoint.get("runs", {})

    # Init transport for PAL mode
    transport = None
    if "pal" in modes:
        try:
            from lucca.sandbox.rpc import DockerRPCTransport
            transport = DockerRPCTransport()
            if not transport.is_docker_available():
                print("[WARN] Docker not available — PAL mode skipped.", flush=True)
                modes = [m for m in modes if m != "pal"]
                transport = None
        except ImportError:
            print("[WARN] lucca.sandbox.rpc not importable — PAL mode skipped.", flush=True)
            modes = [m for m in modes if m != "pal"]

    print("\n" + "=" * 65, flush=True)
    print("Project Lucca — Full GSM-Symbolic Evaluation", flush=True)
    print(f"Variants: {variants}  |  Modes: {modes}", flush=True)
    print(f"Samples per variant: {'ALL' if not samples else samples}", flush=True)
    print("=" * 65, flush=True)

    for variant_key in variants:
        if variant_key not in VARIANT_META:
            print(f"[SKIP] Unknown variant: {variant_key}", flush=True)
            continue
        for mode in modes:
            run_key = f"{variant_key}_{mode}"
            if resume and run_key in run_results and run_results[run_key].get("complete"):
                r = run_results[run_key]
                print(f"  [SKIP] {r['label']} [{mode.upper()}] — already complete ({r['passed']}/{r['total']}, {r['accuracy_pct']}%)", flush=True)
                continue

            result = run_variant(
                variant_key=variant_key,
                mode=mode,
                samples=samples,
                resume_data={"runs": run_results},
                transport=transport,
            )
            run_results[run_key] = result

            # Save checkpoint after every run
            save_checkpoint(ckpt_path, {"timestamp": timestamp, "runs": run_results})

    # --- Summary -------------------------------------------------------------
    print("\n" + "=" * 65, flush=True)
    print("FULL GSM-SYMBOLIC RESULTS SUMMARY", flush=True)
    print("=" * 65, flush=True)
    print(f"  {'Run Key':<32} {'Mode':<6} {'Acc':>7}  {'Pass/Total'}", flush=True)
    print(f"  {'-'*32} {'-'*6} {'-'*7}  {'-'*10}", flush=True)
    for run_key, r in run_results.items():
        print(
            f"  {r['label']:<32} {r['mode'].upper():<6} {r['accuracy_pct']:>6.1f}%  "
            f"{r['passed']}/{r['total']}",
            flush=True,
        )

    # Compute NoOp delta if both modes present
    for vk in ("noop", "noop_filtered"):
        cot_key = f"{vk}_cot"
        pal_key = f"{vk}_pal"
        if cot_key in run_results and pal_key in run_results:
            delta = run_results[pal_key]["accuracy_pct"] - run_results[cot_key]["accuracy_pct"]
            traps = run_results[cot_key].get("distractor_traps", 0) or 0
            cot_total = run_results[cot_key]["total"]
            print(f"\n  NoOp Distractor Immunity ({vk}):", flush=True)
            print(f"    Bare CoT accuracy:     {run_results[cot_key]['accuracy_pct']:.1f}%", flush=True)
            print(f"    Compound PAL accuracy: {run_results[pal_key]['accuracy_pct']:.1f}%", flush=True)
            print(f"    Delta (PAL - CoT):     {delta:+.1f}pp", flush=True)
            print(f"    Distractor traps (CoT): {traps}/{cot_total} ({traps/cot_total*100:.1f}%)", flush=True)

    print("\n  Published Apple paper baselines (GPT-4o greedy):", flush=True)
    print("    GSM-Symbolic:    95.2%", flush=True)
    print("    GSM-Symbolic-P1: 93.5%", flush=True)
    print("    GSM-Symbolic-P2: 90.7%", flush=True)
    print("    GSM-NoOp (CoT):  ~77%  (catastrophic distractor-trap degradation)", flush=True)
    print("=" * 65, flush=True)

    final_report = {
        "benchmark": "GSM_Symbolic_Full",
        "timestamp": timestamp,
        "variants_run": variants,
        "modes_run": modes,
        "runs": {k: {kk: vv for kk, vv in v.items() if kk != "results"} for k, v in run_results.items()},
        "runs_with_results": run_results,
    }

    report_path.write_text(json.dumps(final_report, indent=2), encoding="utf-8")
    (REPORTS_DIR / "gsm_symbolic_full_latest.json").write_text(
        json.dumps(final_report, indent=2), encoding="utf-8"
    )
    print(f"\n  Report: {report_path}", flush=True)

    return final_report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project Lucca — Full GSM-Symbolic Evaluation (All Variants)"
    )
    parser.add_argument(
        "--variant",
        nargs="+",
        choices=ALL_VARIANT_KEYS,
        default=ALL_VARIANT_KEYS,
        metavar="VARIANT",
        help=f"Variant(s) to evaluate. Choices: {ALL_VARIANT_KEYS}. Default: all.",
    )
    parser.add_argument(
        "--mode",
        nargs="+",
        choices=["cot", "pal"],
        default=["cot", "pal"],
        help="Evaluation mode(s): 'cot' (Bare CoT) and/or 'pal' (Compound PAL). Default: both.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=0,
        help="Number of problems per variant (0 = all). Default: 0.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore checkpoint and restart from scratch.",
    )
    args = parser.parse_args()

    run_full_gsm_symbolic(
        variants=args.variant,
        modes=args.mode,
        samples=args.samples,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
