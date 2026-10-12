#!/usr/bin/env python3
"""
Project Lucca — Frontier Benchmark Dataset Downloader
Fetches official, canonical datasets used on frontier models:
1. GPQA Diamond (OpenAI simple-evals canonical CSV, n=198)
2. IFEval (Google Research instruction_following_eval input_data.jsonl, n=541)
3. SimpleQA (OpenAI factual calibration benchmark CSV, n=4326)
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "benchmarks"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = {
    "gpqa_diamond.csv": "https://openaipublic.blob.core.windows.net/simple-evals/gpqa_diamond.csv",
    "ifeval_input_data.jsonl": "https://raw.githubusercontent.com/google-research/google-research/master/instruction_following_eval/data/input_data.jsonl",
    "simple_qa_test_set.csv": "https://openaipublic.blob.core.windows.net/simple-evals/simple_qa_test_set.csv",
}


def download_datasets() -> None:
    for filename, url in DATASETS.items():
        out_file = DATA_DIR / filename
        if out_file.exists():
            print(f"[EXISTS] {filename} ({out_file.stat().st_size:,} bytes)")
            continue

        print(f"[DOWNLOADING] {filename} from {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        out_file.write_bytes(data)
        print(f"  [OK] Saved {filename} ({len(data):,} bytes)")


if __name__ == "__main__":
    download_datasets()
