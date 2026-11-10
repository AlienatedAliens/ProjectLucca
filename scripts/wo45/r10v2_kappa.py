#!/usr/bin/env python3
"""
WO-45 REVIEW_G3 Requirement 4 (`scripts/wo45/r10v2_kappa.py`):
Standalone inter-rater reliability (Cohen's kappa) calculator that reads ONLY
the two judge/rater JSONL files, verifies their SHA-256 hashes are distinct,
verifies provenance fields (`judge_model`, `temperature`, `timestamp_utc`, `rationale`)
on every row, and prints Cohen's kappa and any disagreed blind_ids.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def cohen_kappa(labels_1: list[str], labels_2: list[str], classes: list[str]) -> dict[str, float | int]:
    assert len(labels_1) == len(labels_2)
    n = len(labels_1)
    agree = sum(1 for a, b in zip(labels_1, labels_2, strict=True) if a == b)
    p_o = agree / n if n > 0 else 0.0
    c1 = Counter(labels_1)
    c2 = Counter(labels_2)
    p_e = sum((c1[c] / n) * (c2[c] / n) for c in classes) if n > 0 else 0.0
    kappa = 1.0 if abs(1.0 - p_e) < 1e-12 else (p_o - p_e) / (1.0 - p_e)
    return {
        "n": n,
        "agreed": agree,
        "disagreed": n - agree,
        "raw_agreement_pct": round(p_o * 100.0, 2),
        "expected_agreement_pct": round(p_e * 100.0, 2),
        "cohen_kappa": round(kappa, 4),
    }


def load_and_verify_jsonl(path: Path) -> tuple[str, dict[str, dict[str, object]]]:
    raw_bytes = path.read_bytes()
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    rows: dict[str, dict[str, object]] = {}
    for line_no, line in enumerate(raw_bytes.decode("utf-8").splitlines(), 1):
        line_s = line.strip()
        if not line_s:
            continue
        obj = json.loads(line_s)
        bid = str(obj.get("blind_id", ""))
        if not bid:
            raise ValueError(f"{path}:{line_no} missing blind_id")
        if bid in rows:
            raise ValueError(f"{path}:{line_no} duplicate blind_id {bid}")
        for req_key in ("judge_model", "temperature", "timestamp_utc", "rationale"):
            if req_key not in obj or obj[req_key] in (None, "", {}):
                raise ValueError(f"{path}:{line_no} ({bid}) missing or empty required field '{req_key}'")
        rows[bid] = obj
    return sha256_hex, rows


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: uv run python scripts/wo45/r10v2_kappa.py <judge1.jsonl> <judge2.jsonl>")
        sys.exit(2)

    p1 = Path(sys.argv[1])
    p2 = Path(sys.argv[2])
    sha1, r1 = load_and_verify_jsonl(p1)
    sha2, r2 = load_and_verify_jsonl(p2)

    if sha1 == sha2:
        raise RuntimeError(
            f"FATAL (F-1 check): {p1} and {p2} have identical SHA-256 ({sha1})!"
        )

    ids1 = sorted(r1.keys())
    ids2 = sorted(r2.keys())
    if ids1 != ids2:
        raise ValueError(f"Blind ID mismatch between {p1} ({len(ids1)}) and {p2} ({len(ids2)})")

    models_1 = sorted({str(v["judge_model"]) for v in r1.values()})
    models_2 = sorted({str(v["judge_model"]) for v in r2.values()})

    sample = r1[ids1[0]]
    results: dict[str, object] = {
        "file_1": str(p1),
        "file_1_sha256": sha1,
        "file_1_judge_models": models_1,
        "file_2": str(p2),
        "file_2_sha256": sha2,
        "file_2_judge_models": models_2,
        "hashes_distinct": sha1 != sha2,
        "n_items": len(ids1),
    }

    if "D1" in sample:
        dims = {
            "D1": ["ACCURATE", "OVERCONFIDENT", "UNDERCONFIDENT"],
            "D2": ["CORRECT", "INCORRECT", "NO_ANSWER"],
            "D3": ["YES", "NO", "N/A"],
            "D4": ["YES", "NO", "N/A"],
        }
        dim_kappas: dict[str, object] = {}
        disagreed_by_dim: dict[str, list[str]] = {}
        for d_key, classes in dims.items():
            l1 = [str(r1[bid][d_key]) for bid in ids1]
            l2 = [str(r2[bid][d_key]) for bid in ids1]
            dim_kappas[d_key] = cohen_kappa(l1, l2, classes)
            disagreed_by_dim[d_key] = [bid for bid in ids1 if str(r1[bid][d_key]) != str(r2[bid][d_key])]

        sem1 = [
            "PASS"
            if (r1[bid]["D1"] == "ACCURATE" and r1[bid]["D2"] == "CORRECT" and r1[bid]["D3"] != "YES")
            else "FAIL"
            for bid in ids1
        ]
        sem2 = [
            "PASS"
            if (r2[bid]["D1"] == "ACCURATE" and r2[bid]["D2"] == "CORRECT" and r2[bid]["D3"] != "YES")
            else "FAIL"
            for bid in ids1
        ]
        dim_kappas["composite_semantic_pass"] = cohen_kappa(sem1, sem2, ["PASS", "FAIL"])
        disagreed_by_dim["composite_semantic_pass"] = [
            bid for bid, s1, s2 in zip(ids1, sem1, sem2, strict=True) if s1 != s2
        ]
        results["dimensions"] = dim_kappas
        results["disagreed_blind_ids"] = disagreed_by_dim
    elif "rater_label" in sample:
        classes = ["low", "medium", "high"]
        l1 = [str(r1[bid]["rater_label"]).lower() for bid in ids1]
        l2 = [str(r2[bid]["rater_label"]).lower() for bid in ids1]
        results["hazard_3class_kappa"] = cohen_kappa(l1, l2, classes)
        results["disagreed_blind_ids"] = [
            bid for bid in ids1 if str(r1[bid]["rater_label"]).lower() != str(r2[bid]["rater_label"]).lower()
        ]
    else:
        raise ValueError(f"Unrecognized schema in {p1}")

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
