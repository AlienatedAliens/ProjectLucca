"""
Project Lucca — Full Big-Bench Hard (BBH) Evaluation Harness (All 27 Subsets)
==============================================================================

Evaluates all 27 canonical BBH subsets from Suzgun et al. (2022).
Each subset is annotated with its evaluation MODE:
  - ALGORITHMIC : Tool-friendly; compound execution via Python sandbox should help.
  - LANGUAGE    : Pure language/world-knowledge; bare 12B neural weights only.

Published external baseline (Google DeepMind, June 2026):
  Gemma 4 12B Unified (bare):   BigBench Extra Hard = 53.0%
  Gemma 4 31B Dense (bare):     BigBench Extra Hard = 74.4%
  Gemma 4 26B A4B MoE (bare):   BigBench Extra Hard = 64.8%
  Gemma 4 E4B Edge (bare):      BigBench Extra Hard = 33.1%

Usage:
  uv run python scripts/run_full_bbh.py
  uv run python scripts/run_full_bbh.py --samples 50
  uv run python scripts/run_full_bbh.py --subsets boolean_expressions snarks
  uv run python scripts/run_full_bbh.py --mode algorithmic
  uv run python scripts/run_full_bbh.py --mode language
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
# Subset Registry — all 27 canonical BBH tasks
# mode:
#   ALGORITHMIC = compound execution (Docker Python) should provide leverage
#   LANGUAGE    = bare neural weights; Python doesn't help
# grader:
#   OPTION_LETTER  : extract (A)/(B)/... from response
#   BOOLEAN        : extract True/False
#   SEQUENCE       : compare full sequence on final line (Dyck)
#   NUMERIC        : extract last integer
#   FREE_TEXT      : case-insensitive last-line comparison
# ---------------------------------------------------------------------------
BBH_SUBSETS: list[dict] = [
    # --- Algorithmic / Tool-Friendly (14 subsets) --------------------------
    {
        "key": "boolean_expressions",
        "title": "Boolean Logic Evaluation",
        "mode": "ALGORITHMIC",
        "grader": "BOOLEAN",
        "description": "Evaluate multi-operator boolean expressions to True or False.",
    },
    {
        "key": "multistep_arithmetic_two",
        "title": "Multi-Step Arithmetic",
        "mode": "ALGORITHMIC",
        "grader": "NUMERIC",
        "description": "Multi-step arithmetic with nested parentheses and mixed operations.",
    },
    {
        "key": "logical_deduction_three_objects",
        "title": "Logical Deduction (3 Objects)",
        "mode": "ALGORITHMIC",
        "grader": "OPTION_LETTER",
        "description": "Deduce ordering constraints over 3 objects from clue sentences.",
    },
    {
        "key": "logical_deduction_five_objects",
        "title": "Logical Deduction (5 Objects)",
        "mode": "ALGORITHMIC",
        "grader": "OPTION_LETTER",
        "description": "Deduce ordering constraints over 5 objects from clue sentences.",
    },
    {
        "key": "logical_deduction_seven_objects",
        "title": "Logical Deduction (7 Objects)",
        "mode": "ALGORITHMIC",
        "grader": "OPTION_LETTER",
        "description": "Deduce ordering constraints over 7 objects from clue sentences.",
    },
    {
        "key": "dyck_languages",
        "title": "Dyck Bracket Completion",
        "mode": "ALGORITHMIC",
        "grader": "SEQUENCE",
        "description": "Complete a sequence of nested closing brackets/symbols.",
    },
    {
        "key": "navigate",
        "title": "Navigation Trace",
        "mode": "ALGORITHMIC",
        "grader": "BOOLEAN",
        "description": "Follow a sequence of steps and determine if you return to the origin.",
    },
    {
        "key": "web_of_lies",
        "title": "Web of Lies",
        "mode": "ALGORITHMIC",
        "grader": "BOOLEAN",
        "description": "Track truth/lie chains and determine the truth value of a final claim.",
    },
    {
        "key": "object_counting",
        "title": "Object Counting",
        "mode": "ALGORITHMIC",
        "grader": "NUMERIC",
        "description": "Count objects from a natural language description.",
    },
    {
        "key": "word_sorting",
        "title": "Word Sorting",
        "mode": "ALGORITHMIC",
        "grader": "SEQUENCE",
        "description": "Sort a list of words into alphabetical order.",
    },
    {
        "key": "tracking_shuffled_objects_three_objects",
        "title": "Object Tracking (3 Objects)",
        "mode": "ALGORITHMIC",
        "grader": "OPTION_LETTER",
        "description": "Track the final positions of 3 objects through a shuffle sequence.",
    },
    {
        "key": "tracking_shuffled_objects_five_objects",
        "title": "Object Tracking (5 Objects)",
        "mode": "ALGORITHMIC",
        "grader": "OPTION_LETTER",
        "description": "Track the final positions of 5 objects through a shuffle sequence.",
    },
    {
        "key": "tracking_shuffled_objects_seven_objects",
        "title": "Object Tracking (7 Objects)",
        "mode": "ALGORITHMIC",
        "grader": "OPTION_LETTER",
        "description": "Track the final positions of 7 objects through a shuffle sequence.",
    },
    {
        "key": "temporal_sequences",
        "title": "Temporal Sequence Scheduling",
        "mode": "ALGORITHMIC",
        "grader": "OPTION_LETTER",
        "description": "Determine when an activity could take place given scheduling constraints.",
    },
    # --- Language / World-Knowledge (13 subsets) ---------------------------
    {
        "key": "date_understanding",
        "title": "Date Understanding",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Infer a specific date from a description involving relative time references.",
    },
    {
        "key": "causal_judgement",
        "title": "Causal Judgement",
        "mode": "LANGUAGE",
        "grader": "BOOLEAN",
        "description": "Determine whether an agent caused an event (yes/no).",
    },
    {
        "key": "disambiguation_qa",
        "title": "Disambiguation QA",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Disambiguate a pronoun reference given context.",
    },
    {
        "key": "formal_fallacies",
        "title": "Formal Fallacies",
        "mode": "LANGUAGE",
        "grader": "BOOLEAN",
        "description": "Determine whether an argument is valid or invalid (valid/invalid).",
    },
    {
        "key": "geometric_shapes",
        "title": "Geometric Shapes",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Identify a geometric shape from its SVG path description.",
    },
    {
        "key": "hyperbaton",
        "title": "Hyperbaton",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Identify which of two adjective-orderings sounds more natural.",
    },
    {
        "key": "movie_recommendation",
        "title": "Movie Recommendation",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Recommend a movie from a list given a description of preferences.",
    },
    {
        "key": "penguins_in_a_table",
        "title": "Penguins in a Table",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Answer questions about a small structured table of penguin attributes.",
    },
    {
        "key": "reasoning_about_colored_objects",
        "title": "Reasoning About Colored Objects",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Determine the color/position of an object from a description.",
    },
    {
        "key": "ruin_names",
        "title": "Ruin Names",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Choose which of two band name puns is the actual humorous ruin name.",
    },
    {
        "key": "salient_translation_error_detection",
        "title": "Translation Error Detection",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Identify the type of translation error in a German-to-English sentence pair.",
    },
    {
        "key": "snarks",
        "title": "Snarks",
        "mode": "LANGUAGE",
        "grader": "OPTION_LETTER",
        "description": "Identify which of two statements is sarcastic.",
    },
    {
        "key": "sports_understanding",
        "title": "Sports Understanding",
        "mode": "LANGUAGE",
        "grader": "BOOLEAN",
        "description": "Determine whether a sports-related statement is plausible (yes/no).",
    },
]

# Map for quick lookup
SUBSET_META: dict[str, dict] = {s["key"]: s for s in BBH_SUBSETS}


# ---------------------------------------------------------------------------
# Dataset Fetcher
# ---------------------------------------------------------------------------

def get_bbh_subset(key: str) -> list[dict]:
    """Load a BBH subset from cache or download from GitHub."""
    cache = DATA_DIR / f"bbh_{key}.json"
    if not cache.exists():
        url = f"https://raw.githubusercontent.com/suzgunmirac/BIG-bench-Hard/main/bbh/{key}.json"
        print(f"  Downloading BBH {key} ...", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            cache.write_bytes(resp.read())
    data = json.loads(cache.read_text(encoding="utf-8"))
    return data.get("examples", [])


# ---------------------------------------------------------------------------
# LLM Query
# ---------------------------------------------------------------------------

def query_llm(prompt: str, max_tokens: int = 512, retries: int = 2) -> str:
    """Send a prompt to llama-server and return the response text."""
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": 42,
        "cache_prompt": False,
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
                return msg.get("content") or msg.get("reasoning_content") or ""
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"   [WARN] LLM query failed: {exc}", flush=True)
                return ""
    return ""


# ---------------------------------------------------------------------------
# Per-Subset Prompt Builders
# ---------------------------------------------------------------------------

def build_prompt(key: str, inp: str) -> str:
    """Build the instruction prompt for a given BBH subset and input."""
    # Multiple-choice subsets share a common template
    MC_SUBSETS = {
        "logical_deduction_three_objects", "logical_deduction_five_objects",
        "logical_deduction_seven_objects", "tracking_shuffled_objects_three_objects",
        "tracking_shuffled_objects_five_objects", "tracking_shuffled_objects_seven_objects",
        "geometric_shapes", "temporal_sequences", "date_understanding",
        "disambiguation_qa", "hyperbaton", "movie_recommendation", "penguins_in_a_table",
        "reasoning_about_colored_objects", "ruin_names",
        "salient_translation_error_detection", "snarks",
    }
    YES_NO_SUBSETS = {
        "causal_judgement", "sports_understanding",
    }
    VALID_INVALID_SUBSETS = {
        "formal_fallacies",
    }

    if key == "boolean_expressions":
        return (
            "Evaluate the following boolean expression step by step.\n"
            "Your final answer must be exactly one word on its own line: True or False.\n\n"
            f"Expression: {inp}"
        )
    elif key == "navigate":
        return (
            "Follow the navigation steps below starting at the origin facing north.\n"
            "Determine whether you return to exactly where you started.\n"
            "Your final answer must be exactly one word on its own line: Yes or No.\n\n"
            f"{inp}"
        )
    elif key == "web_of_lies":
        return (
            "Carefully trace the chain of truth-telling and lying below.\n"
            "Your final answer must be exactly one word on its own line: Yes or No.\n\n"
            f"{inp}"
        )
    elif key in YES_NO_SUBSETS:
        return (
            f"Answer the following question with Yes or No only.\n"
            "Your final answer must be exactly one word on its own line: Yes or No.\n\n"
            f"{inp}"
        )
    elif key in VALID_INVALID_SUBSETS:
        return (
            "Determine whether the following argument is logically valid or invalid.\n"
            "Your final answer must be exactly one word on its own line: valid or invalid.\n\n"
            f"{inp}"
        )
    elif key == "dyck_languages":
        return (
            "Complete the Dyck sequence by providing the required closing brackets/symbols.\n"
            "Provide only the closing sequence separated by spaces on the final line. "
            "Do not add any explanation.\n\n"
            f"{inp}"
        )
    elif key == "word_sorting":
        return (
            "Sort the following words into alphabetical order.\n"
            "Output only the sorted words separated by spaces on the final line.\n\n"
            f"{inp}"
        )
    elif key == "object_counting":
        return (
            "Count the objects described below and provide the total as an integer.\n"
            "Your final answer must be a single integer on its own line.\n\n"
            f"{inp}"
        )
    elif key == "multistep_arithmetic_two":
        return (
            "Solve the following arithmetic expression. Show your work if needed.\n"
            "Your final answer must be a single integer on its own line.\n\n"
            f"{inp}"
        )
    elif key in MC_SUBSETS:
        return (
            "Solve the following task. Think step by step if needed.\n"
            "Your final answer must be the option letter in parentheses on its own line, "
            "e.g. (A) or (B).\n\n"
            f"{inp}"
        )
    else:
        return (
            "Solve the following task. Provide your final answer on the last line.\n\n"
            f"{inp}"
        )


# ---------------------------------------------------------------------------
# Per-Subset Answer Extractors & Graders
# ---------------------------------------------------------------------------

def _extract_option_letter(resp: str) -> str:
    """Extract the last (X) option letter from a response."""
    matches = re.findall(r"\(([A-Za-z])\)", resp)
    if matches:
        return matches[-1].upper()
    # Fallback: last bare capital letter on the last non-empty line
    for line in reversed(resp.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        m = re.findall(r"\b([A-Z])\b", line)
        if m:
            return m[-1]
        break
    return ""


def _extract_boolean(resp: str, true_word: str = "true", false_word: str = "false") -> str:
    """Extract a boolean-style answer (True/False or Yes/No or valid/invalid)."""
    lines = [l.strip() for l in resp.strip().splitlines() if l.strip()]
    # Search from the end for the answer word
    for line in reversed(lines):
        lower = line.lower()
        # Strip trailing punctuation
        lower = lower.rstrip(".!?,;:")
        if lower == true_word:
            return true_word
        if lower == false_word:
            return false_word
        # Contained anywhere on a short line
        if len(line) < 40:
            if re.search(rf"\b{true_word}\b", lower):
                return true_word
            if re.search(rf"\b{false_word}\b", lower):
                return false_word
    # Broad scan
    all_text = resp.lower()
    tw = re.findall(rf"\b{true_word}\b", all_text)
    fw = re.findall(rf"\b{false_word}\b", all_text)
    if tw and not fw:
        return true_word
    if fw and not tw:
        return false_word
    if tw and fw:
        # Return whichever appears last
        last_t = all_text.rfind(true_word)
        last_f = all_text.rfind(false_word)
        return true_word if last_t > last_f else false_word
    return ""


def _extract_sequence(resp: str) -> str:
    """Extract the last non-empty line as a sequence answer."""
    lines = [l.strip() for l in resp.strip().splitlines() if l.strip()]
    if not lines:
        return ""
    last = lines[-1]
    # Strip label prefixes like "Answer:" or "Sorted:"
    last = re.sub(r"^(?:answer|output|result|sequence|sorted)[:\s]+", "", last, flags=re.IGNORECASE).strip()
    return last


def _extract_numeric(resp: str) -> str:
    """Extract the last integer from a response."""
    lines = [l.strip() for l in resp.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        nums = re.findall(r"-?\d+", line)
        if nums:
            return nums[-1]
    return ""


def extract_and_grade(meta: dict, resp: str, target: str) -> tuple[str, bool]:
    """
    Extract the model's prediction from resp and grade against target.
    Returns (prediction_str, is_correct).
    """
    key = meta["key"]
    grader = meta["grader"]
    target_clean = target.strip()

    if grader == "BOOLEAN":
        # Detect which pair of words to use
        target_lower = target_clean.lower()
        if target_lower in ("yes", "no"):
            pred = _extract_boolean(resp, "yes", "no")
        elif target_lower in ("valid", "invalid"):
            pred = _extract_boolean(resp, "valid", "invalid")
        else:
            pred = _extract_boolean(resp, "true", "false")
        is_correct = (pred.lower() == target_lower)
        return pred, is_correct

    elif grader == "OPTION_LETTER":
        # Target is like "(A)" — extract just the letter
        target_letter = re.sub(r"[^A-Za-z]", "", target_clean).upper()
        pred_letter = _extract_option_letter(resp)
        is_correct = (pred_letter == target_letter)
        return f"({pred_letter})", is_correct

    elif grader == "SEQUENCE":
        if key == "word_sorting":
            pred = _extract_sequence(resp)
            # Normalize whitespace for comparison
            pred_norm = " ".join(pred.split())
            target_norm = " ".join(target_clean.split())
            is_correct = (pred_norm.lower() == target_norm.lower())
            return pred, is_correct
        else:
            # Dyck languages: sequence of brackets
            pred = _extract_sequence(resp)
            # Also check if target appears anywhere in response
            is_correct = (pred == target_clean) or (target_clean in resp)
            return pred, is_correct

    elif grader == "NUMERIC":
        pred = _extract_numeric(resp)
        try:
            is_correct = (int(pred) == int(target_clean))
        except (ValueError, TypeError):
            is_correct = (pred == target_clean)
        return pred, is_correct

    elif grader == "FREE_TEXT":
        pred = _extract_sequence(resp)
        is_correct = (pred.lower().strip() == target_clean.lower().strip())
        return pred, is_correct

    else:
        pred = _extract_sequence(resp)
        is_correct = (pred.lower() == target_clean.lower())
        return pred, is_correct


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
# Main Runner
# ---------------------------------------------------------------------------

def run_full_bbh(
    subsets_to_run: list[str] | None = None,
    mode_filter: str | None = None,
    samples_per_subset: int = 0,
    resume: bool = True,
) -> dict:
    """
    Run all 27 BBH subsets (or a filtered selection).

    Args:
        subsets_to_run:  List of subset keys to evaluate. None = all 27.
        mode_filter:     'algorithmic' or 'language' to run only that tier.
        samples_per_subset: 0 = full set; N = first N examples.
        resume:          If True, skip subsets already in checkpoint.
    """
    # Determine which subsets to run
    registry = BBH_SUBSETS
    if subsets_to_run:
        registry = [s for s in BBH_SUBSETS if s["key"] in subsets_to_run]
    if mode_filter:
        registry = [s for s in registry if s["mode"].lower() == mode_filter.lower()]

    if not registry:
        print("ERROR: No subsets matched the filter criteria.", flush=True)
        return {}

    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    ckpt_path = REPORTS_DIR / "bbh_full_27_checkpoint.json"
    report_path = REPORTS_DIR / f"bbh_full_27_{timestamp}.json"

    # Load any existing checkpoint
    checkpoint = load_checkpoint(ckpt_path) if resume else {}
    subset_reports: dict = checkpoint.get("subsets", {})

    total_all = 0
    passed_all = 0
    algo_total = 0
    algo_passed = 0
    lang_total = 0
    lang_passed = 0
    t_run_start = time.perf_counter()

    print("\n" + "=" * 65, flush=True)
    print(f"Project Lucca — Full Big-Bench Hard (27 Subsets)", flush=True)
    print(f"Running {len(registry)} subset(s) | samples_per_subset={samples_per_subset or 'ALL'}", flush=True)
    print("=" * 65, flush=True)

    for meta in registry:
        key = meta["key"]
        title = meta["title"]
        mode = meta["mode"]

        # Resume: skip already-complete subsets
        if resume and key in subset_reports and subset_reports[key].get("complete"):
            r = subset_reports[key]
            print(f"  [SKIP] {title} — already complete ({r['passed']}/{r['total']}, {r['accuracy_pct']}%)", flush=True)
            total_all += r["total"]
            passed_all += r["passed"]
            if mode == "ALGORITHMIC":
                algo_total += r["total"]
                algo_passed += r["passed"]
            else:
                lang_total += r["total"]
                lang_passed += r["passed"]
            continue

        print(f"\n{'=' * 65}", flush=True)
        print(f"[{mode}] {title}  ({key})", flush=True)
        print(f"{'=' * 65}", flush=True)

        examples = get_bbh_subset(key)
        if samples_per_subset > 0 and samples_per_subset < len(examples):
            examples = examples[:samples_per_subset]

        sub_passed = 0
        sub_results = []
        t_sub_start = time.perf_counter()

        for idx, ex in enumerate(examples, 1):
            inp = ex["input"]
            target = ex["target"].strip()
            prompt = build_prompt(key, inp)

            t0 = time.perf_counter()
            resp = query_llm(prompt=prompt, max_tokens=512)
            t_llm = time.perf_counter() - t0

            pred, is_correct = extract_and_grade(meta, resp, target)

            if is_correct:
                sub_passed += 1
            status = "PASS" if is_correct else "FAIL"
            print(
                f"[{idx:03d}/{len(examples)}] {status} | "
                f"pred='{str(pred)[:25]}' target='{target[:25]}' | {t_llm:.1f}s",
                flush=True,
            )

            sub_results.append({
                "idx": idx,
                "input": inp[:200],
                "target": target,
                "predicted": str(pred),
                "passed": is_correct,
                "latency_s": round(t_llm, 3),
            })

        sub_total = len(examples)
        sub_acc = (sub_passed / sub_total * 100.0) if sub_total else 0.0
        sub_elapsed = time.perf_counter() - t_sub_start

        print(
            f"\n  ✓ {title}: {sub_passed}/{sub_total} ({sub_acc:.1f}%) "
            f"in {sub_elapsed:.0f}s",
            flush=True,
        )

        subset_reports[key] = {
            "key": key,
            "title": title,
            "mode": mode,
            "total": sub_total,
            "passed": sub_passed,
            "accuracy_pct": round(sub_acc, 2),
            "elapsed_s": round(sub_elapsed, 2),
            "complete": True,
            "results": sub_results,
        }

        # Accumulate
        total_all += sub_total
        passed_all += sub_passed
        if mode == "ALGORITHMIC":
            algo_total += sub_total
            algo_passed += sub_passed
        else:
            lang_total += sub_total
            lang_passed += sub_passed

        # Save checkpoint after every subset
        checkpoint_data = {
            "timestamp": timestamp,
            "subsets_complete": sum(1 for v in subset_reports.values() if v.get("complete")),
            "total_so_far": total_all,
            "passed_so_far": passed_all,
            "subsets": subset_reports,
        }
        save_checkpoint(ckpt_path, checkpoint_data)

    # --- Final Summary -------------------------------------------------------
    total_elapsed = time.perf_counter() - t_run_start
    overall_acc = (passed_all / total_all * 100.0) if total_all else 0.0
    algo_acc = (algo_passed / algo_total * 100.0) if algo_total else 0.0
    lang_acc = (lang_passed / lang_total * 100.0) if lang_total else 0.0

    print("\n" + "=" * 65, flush=True)
    print("FULL BBH RESULTS SUMMARY", flush=True)
    print("=" * 65, flush=True)
    print(f"  Overall:           {passed_all:4d}/{total_all} = {overall_acc:.1f}%", flush=True)
    print(f"  Algorithmic tier:  {algo_passed:4d}/{algo_total} = {algo_acc:.1f}%", flush=True)
    print(f"  Language tier:     {lang_passed:4d}/{lang_total} = {lang_acc:.1f}%", flush=True)
    print(f"  Elapsed:           {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)", flush=True)
    print(f"\n  Published baselines (Gemma 4 family — BigBench Extra Hard):", flush=True)
    print(f"    Gemma 4 12B bare:  53.0%  (DeepMind, June 2026)", flush=True)
    print(f"    Gemma 4 31B bare:  74.4%", flush=True)
    print(f"    Gemma 4 26B MoE:   64.8%", flush=True)
    print(f"    Gemma 4 E4B bare:  33.1%", flush=True)
    print(f"\n  Lucca compound delta vs bare 12B: {overall_acc - 53.0:+.1f}pp", flush=True)
    print("=" * 65, flush=True)

    # Per-subset table
    print("\nPer-Subset Breakdown:", flush=True)
    print(f"  {'Subset':<44} {'Mode':<12} {'Acc':>6}  {'Pass/Total'}", flush=True)
    print(f"  {'-'*44} {'-'*12} {'-'*6}  {'-'*10}", flush=True)
    for meta in BBH_SUBSETS:
        k = meta["key"]
        if k not in subset_reports:
            continue
        r = subset_reports[k]
        print(
            f"  {r['title']:<44} {r['mode']:<12} {r['accuracy_pct']:>5.1f}%  "
            f"{r['passed']}/{r['total']}",
            flush=True,
        )

    # Build final report
    final_report = {
        "benchmark": "BigBench_Hard_Full_27",
        "timestamp": timestamp,
        "total": total_all,
        "passed": passed_all,
        "accuracy_pct": round(overall_acc, 2),
        "algorithmic_accuracy_pct": round(algo_acc, 2),
        "language_accuracy_pct": round(lang_acc, 2),
        "elapsed_s": round(total_elapsed, 2),
        "external_baseline_gemma4_12b_bare_pct": 53.0,
        "compound_delta_pp": round(overall_acc - 53.0, 2),
        "subsets": subset_reports,
    }

    report_path.write_text(json.dumps(final_report, indent=2), encoding="utf-8")
    (REPORTS_DIR / "bbh_full_27_latest.json").write_text(
        json.dumps(final_report, indent=2), encoding="utf-8"
    )
    print(f"\n  Report: {report_path}", flush=True)

    return final_report


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project Lucca — Full Big-Bench Hard (All 27 Subsets) Harness"
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=0,
        help="Number of examples per subset (0 = full set, default: 0)",
    )
    parser.add_argument(
        "--subsets",
        nargs="+",
        metavar="KEY",
        help="Run specific subset key(s) only, e.g. --subsets snarks boolean_expressions",
    )
    parser.add_argument(
        "--mode",
        choices=["algorithmic", "language"],
        default=None,
        help="Run only 'algorithmic' or 'language' tier subsets",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing checkpoint and restart from scratch",
    )
    args = parser.parse_args()

    run_full_bbh(
        subsets_to_run=args.subsets,
        mode_filter=args.mode,
        samples_per_subset=args.samples,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
