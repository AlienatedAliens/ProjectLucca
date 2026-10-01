"""
Download Apple GSM-Symbolic benchmark dataset files from the official repository
at a pinned commit and verify their cryptographic SHA-256 checksums.
"""

import hashlib
import urllib.request
from pathlib import Path

PINNED_COMMIT = "3b645c25d200bf950fb84e8cdcbfeccd91d6a8af"
BASE_URL = f"https://raw.githubusercontent.com/apple/ml-gsm-symbolic/{PINNED_COMMIT}/generated_data"

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "benchmarks"
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXPECTED_FILES = {
    "GSM_symbolic.jsonl": "945055837b232bd9b56827b1e3a5aa019075f29e8ba4669d9a9df8b4439a291f",
    "GSM_p1.jsonl": "5478fe81b9cdc5d9447514ca68b0dfbb6cb01b7227fefadf143469b103b592ac",
    "GSM_p2.jsonl": "f7d6701619f824f4fedd0a914b1cfbc0fd31f61617887aa7fe318d018dda3f29",
}


def download_and_verify():
    print(f"Downloading Apple GSM-Symbolic dataset from pinned commit: {PINNED_COMMIT[:8]}")
    for filename, expected_sha in EXPECTED_FILES.items():
        dest = DATA_DIR / filename
        if dest.exists():
            data = dest.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if sha == expected_sha:
                print(f"[OK] {filename} exists with matching SHA-256: {sha[:12]}...")
                continue
            else:
                print(f"[WARN] {filename} hash mismatch ({sha[:12]} vs {expected_sha[:12]}); re-downloading...")

        url = f"{BASE_URL}/{filename}"
        print(f"Fetching {filename} from {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        sha = hashlib.sha256(data).hexdigest()
        assert sha == expected_sha, f"Checksum verification failed for {filename}: got {sha}, expected {expected_sha}"
        dest.write_bytes(data)
        print(f"[OK] Successfully verified and saved {filename} ({len(data)} bytes, sha256: {sha[:12]}...)")


if __name__ == "__main__":
    download_and_verify()
