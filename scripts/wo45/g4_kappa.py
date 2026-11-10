"""Standalone inter-judge Cohen's kappa calculator for WO-45 Gate G4 (G4-2).

Reads ONLY blinded judge JSONL files (zero access to unblinding keys). Reports 3-class and
pre-registered binary indicator Cohen's kappa per dimension (D1..D4) and writes the list of
blind_ids with any disagreement on D1..D4 for third-family adjudication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

BINARY_TARGET: dict[str, str] = {
    "D1": "ACCURATE",
    "D2": "CORRECT",
    "D3": "YES",
    "D4": "YES",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> dict[str, object]:
    n = len(labels_a)
    if n == 0 or n != len(labels_b):
        raise ValueError(f"Mismatched or empty label sequences: {len(labels_a)} vs {len(labels_b)}")
    agreed = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b)
    p_o = agreed / n
    ca = Counter(labels_a)
    cb = Counter(labels_b)
    cats = sorted(set(ca.keys()) | set(cb.keys()))
    p_e = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    if abs(1.0 - p_e) < 1e-12:
        kappa = 1.0 if agreed == n else 0.0
    else:
        kappa = (p_o - p_e) / (1.0 - p_e)
    return {
        "n": n,
        "agreed": agreed,
        "disagreed": n - agreed,
        "raw_agreement_pct": round(100.0 * p_o, 2),
        "expected_agreement_pct": round(100.0 * p_e, 2),
        "cohen_kappa": round(kappa, 4),
    }


def load_jsonl_by_id(path: Path) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            obj = json.loads(ln)
            out[str(obj["blind_id"])] = obj
    return out


def compute_pair_report(file1: Path, file2: Path) -> dict[str, object]:
    sha1 = sha256_file(file1)
    sha2 = sha256_file(file2)
    m1 = load_jsonl_by_id(file1)
    m2 = load_jsonl_by_id(file2)
    common_ids = sorted(set(m1.keys()) & set(m2.keys()))
    if not common_ids:
        raise ValueError("No overlapping blind_ids between judge files.")

    dims_3class: dict[str, object] = {}
    dims_binary: dict[str, object] = {}
    for dim, pos_val in BINARY_TARGET.items():
        seq1 = [str(m1[k][dim]) for k in common_ids]
        seq2 = [str(m2[k][dim]) for k in common_ids]
        dims_3class[dim] = cohen_kappa(seq1, seq2)
        b1 = ["1" if x == pos_val else "0" for x in seq1]
        b2 = ["1" if x == pos_val else "0" for x in seq2]
        dims_binary[dim] = cohen_kappa(b1, b2)

    disagreed_ids = [
        k
        for k in common_ids
        if any(str(m1[k][d]) != str(m2[k][d]) for d in ("D1", "D2", "D3", "D4"))
    ]
    models_1 = sorted({str(m1[k].get("judge_model", "unknown")) for k in common_ids})
    models_2 = sorted({str(m2[k].get("judge_model", "unknown")) for k in common_ids})
    return {
        "file_1": str(file1),
        "file_1_sha256": sha1,
        "file_1_judge_models": models_1,
        "file_2": str(file2),
        "file_2_sha256": sha2,
        "file_2_judge_models": models_2,
        "hashes_distinct": sha1 != sha2,
        "n_overlapping_items": len(common_ids),
        "dimensions_3class": dims_3class,
        "dimensions_binary": dims_binary,
        "n_any_dimension_disagreed": len(disagreed_ids),
        "disagreed_blind_ids": disagreed_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file1", type=Path)
    parser.add_argument("file2", type=Path)
    parser.add_argument("--out-json", type=Path, default=None)
    args = parser.parse_args()

    rep = compute_pair_report(args.file1, args.file2)
    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    summary = {k: v for k, v in rep.items() if k != "disagreed_blind_ids"}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
