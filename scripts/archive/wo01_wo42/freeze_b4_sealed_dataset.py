"""Freeze the B4 sealed held-out dataset (Phase 3 prep, criticism remediation).

Draws from the same HuggingFaceTB/MATH test partitions used by
scripts/freeze_fresh_heldout_dataset.py, but STRICTLY excludes every problem
in BOTH previously-run files (math500_test.jsonl and
math_fresh_heldout_500.jsonl), so no item in the output has ever been run,
inspected, or used for tuning (see data/benchmarks/EXPOSURE.yaml).

The output is SEALED: hash recorded in EXPOSURE.yaml; no run until the B4
protocol is pre-registered and approved. Deterministic frozen seed: 20261006.
"""

from __future__ import annotations

import hashlib
import json
import random
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "benchmarks"

MATH500_FILE = DATA_DIR / "math500_test.jsonl"
FRESH500_FILE = DATA_DIR / "math_fresh_heldout_500.jsonl"
OUT_FILE = DATA_DIR / "math_b4_sealed_100.jsonl"

SUBJECTS = [
    "algebra",
    "counting_and_probability",
    "geometry",
    "intermediate_algebra",
    "number_theory",
    "prealgebra",
    "precalculus",
]

BASE_URL = "https://huggingface.co/datasets/HuggingFaceTB/MATH/raw/main/data"
SEED = 20261006
TARGET_N = 100  # matches the established held-out-100 protocol for comparability


def normalize_text(t: str) -> str:
    return " ".join(t.strip().split())


def load_problems(path: Path) -> set[str]:
    problems: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                problems.add(normalize_text(json.loads(line)["problem"]))
    return problems


def main() -> int:
    print("=== Freezing B4 SEALED held-out dataset (criticism remediation Phase 3) ===")

    excluded = load_problems(MATH500_FILE) | load_problems(FRESH500_FILE)
    print(f"Exclusion set: {len(excluded)} normalized problems from math500_test + math_fresh_heldout_500")

    candidates_by_subject: dict[str, list[dict]] = {s: [] for s in SUBJECTS}
    total_candidates = 0
    for s in SUBJECTS:
        url = f"{BASE_URL}/{s}_test.jsonl"
        print(f"Fetching {s} from {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read().decode("utf-8")
        for line in content.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            norm = normalize_text(item["problem"])
            if norm in excluded:
                continue
            item["subject"] = s
            candidates_by_subject[s].append(item)
            total_candidates += 1

    print(f"Candidate pool untouched by any prior run: {total_candidates}")
    for s, items in candidates_by_subject.items():
        print(f"  - {s}: {len(items)}")

    rng = random.Random(SEED)
    per_subject = TARGET_N // len(SUBJECTS)
    remainder = TARGET_N % len(SUBJECTS)
    selected: list[dict] = []
    for i, s in enumerate(SUBJECTS):
        k = per_subject + (1 if i < remainder else 0)
        items = list(candidates_by_subject[s])
        rng.shuffle(items)
        selected.extend(items[:k])
    rng.shuffle(selected)
    print(f"Sampled {len(selected)} sealed problems (seed {SEED}).")

    with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        for idx, item in enumerate(selected):
            item["b4_sealed_id"] = f"B4-SEALED-{idx + 1:04d}"
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    data = OUT_FILE.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    print(f"[OK] Saved to: {OUT_FILE}")
    print(f"[OK] Items: {len(selected)}")
    print(f"[OK] SHA256: {sha256}")
    print(f"[OK] Seed: {SEED}")
    print("[OK] STATUS: SEALED — do not run until the B4 protocol is pre-registered and approved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
