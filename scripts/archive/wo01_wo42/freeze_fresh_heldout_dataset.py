"""
Freeze Fresh Held-Out Benchmark Dataset for WO-28
Drawn from HuggingFaceTB/MATH test partitions, strictly excluding the 500 problems of MATH-500.
Deterministic frozen seed: 20260930
"""

from __future__ import annotations

import hashlib
import json
import random
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "benchmarks"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MATH500_FILE = DATA_DIR / "math500_test.jsonl"
OUT_FILE = DATA_DIR / "math_fresh_heldout_500.jsonl"

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


def normalize_text(t: str) -> str:
    return " ".join(t.strip().split())


def main() -> None:
    print("=== Freezing Fresh Held-Out Benchmark Dataset (WO-28) ===")

    # 1. Load MATH-500 problems to exclude
    if not MATH500_FILE.exists():
        raise FileNotFoundError(f"Missing {MATH500_FILE}")
    math500_problems = set()
    with open(MATH500_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                math500_problems.add(normalize_text(item["problem"]))
    print(f"Loaded {len(math500_problems)} existing MATH-500 problems to strictly exclude.")

    # 2. Download and pool candidate problems across the 7 subjects
    candidates_by_subject: dict[str, list[dict]] = {s: [] for s in SUBJECTS}
    total_candidates = 0

    for s in SUBJECTS:
        url = f"{BASE_URL}/{s}_test.jsonl"
        print(f"Fetching {s} from {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
        for line in content.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            norm_prob = normalize_text(item["problem"])
            if norm_prob not in math500_problems:
                item["subject"] = s
                candidates_by_subject[s].append(item)
                total_candidates += 1

    print(f"Total candidate fresh problems outside MATH-500: {total_candidates}")
    for s, items in candidates_by_subject.items():
        print(f"  - {s}: {len(items)} items")

    # 3. Stratified random sample of 500 problems with frozen seed
    rng = random.Random(20260930)
    target_sample_size = 500
    per_subject = target_sample_size // len(SUBJECTS)  # 71 per subject
    remainder = target_sample_size % len(SUBJECTS)     # 3 extra

    selected: list[dict] = []
    for i, s in enumerate(SUBJECTS):
        k = per_subject + (1 if i < remainder else 0)
        items = candidates_by_subject[s]
        rng.shuffle(items)
        selected.extend(items[:k])

    # Final shuffle across subjects so presentation order is mixed
    rng.shuffle(selected)
    print(f"\nSampled {len(selected)} fresh held-out problems.")

    # 4. Save to JSONL
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for idx, item in enumerate(selected):
            item["fresh_heldout_id"] = f"FRESH-MATH-{idx+1:04d}"
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 5. Compute SHA256 checksum
    data = OUT_FILE.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    print(f"[OK] Saved to: {OUT_FILE}")
    print(f"[OK] File size: {len(data)} bytes")
    print(f"[OK] SHA256: {sha256}")
    print(f"[OK] Seed: 20260930")


if __name__ == "__main__":
    main()
