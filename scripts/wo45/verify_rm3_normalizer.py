"""End-to-end verification of RM-3 arm-identical normalizer (`REVIEW_G4.md:61-65`).

Runs:
  1. Acceptance Check 1: Forbidden lexicon scan across all 1,980 normalized v2 replies (must be 0 hits).
  2. Acceptance Check 2: Qualified judge (`qwen3.8-27b`) arm-guess test on 150 normalized replies
     (50 per arm across A, B, C; 10 per model x arm, shuffled) asking "Was this reply given special
     instructions?". Checks raw accuracy and balanced accuracy (must be <= 60.0%).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.wo45.g4_kappa import load_jsonl_by_id  # noqa: E402
from scripts.wo45.normalize_g4v3_replies import (  # noqa: E402
    normalize_reply,
    scan_forbidden_lexicon,
)

WO45_DIR = REPO_ROOT / "logs" / "test_reports" / "wo45"
V2_RAW_PATH = WO45_DIR / "g4_live_v2_raw_generations.json"
SAMPLE_150_BLINDED = WO45_DIR / "g4v3_arm_guess_150_blinded.jsonl"
JUDGE_150_OUT = WO45_DIR / "g4v3_arm_guess_150_qwen38_27b.jsonl"
REPORT_OUT = WO45_DIR / "g4v3_normalizer_verification.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge-profile", default="qwen3.8-27b")
    parser.add_argument("--skip-judge-run", action="store_true")
    args = parser.parse_args()

    raw_data = json.loads(V2_RAW_PATH.read_text(encoding="utf-8"))
    turns = raw_data["turn_records"]

    # Acceptance Check 1: 0 lexicon hits across all 1,980 normalized replies
    before_by_arm: dict[str, dict[str, int]] = {}
    after_by_arm: dict[str, dict[str, int]] = {}
    for arm in ("A", "B", "C"):
        raw_texts = [str(t["reply"]) for t in turns if str(t["arm"]) == arm]
        norm_texts = [normalize_reply(x) for x in raw_texts]
        before_by_arm[arm] = scan_forbidden_lexicon(raw_texts)
        after_by_arm[arm] = scan_forbidden_lexicon(norm_texts)
    total_after_hits = sum(sum(v.values()) for v in after_by_arm.values())

    # Build 150-item stratified sample (10 non-empty items per (model, arm) -> 50 per arm)
    # Use matched probe_ids across A, B, C within each model so question difficulty is identical!
    rng = random.Random(20261112)
    by_model_probe: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for t in turns:
        key = (str(t["model"]), str(t["probe_id"]))
        by_model_probe.setdefault(key, {})[str(t["arm"])] = t

    models = sorted({str(t["model"]) for t in turns})
    sampled_records: list[dict[str, Any]] = []
    for m in models:
        valid_probes = sorted(
            pid
            for (mod, pid), amap in by_model_probe.items()
            if mod == m and all(str(amap[a]["reply"]).strip() for a in ("A", "B", "C"))
        )
        rng.shuffle(valid_probes)
        chosen_10 = sorted(valid_probes[:10])
        for pid in chosen_10:
            for arm in ("A", "B", "C"):
                rec = by_model_probe[(m, pid)][arm]
                sampled_records.append(
                    {
                        "arm": arm,
                        "model": m,
                        "probe_id": pid,
                        "topology": str(rec["topology"]),
                        "question": str(rec["question"]),
                        "retrieved_snippets": rec["retrieved_snippets"],
                        "normalized_reply": normalize_reply(str(rec["reply"])),
                    }
                )

    assert len(sampled_records) == 150
    rng.shuffle(sampled_records)

    blinded_rows: list[dict[str, Any]] = []
    key_by_blind_id: dict[str, dict[str, Any]] = {}
    for idx, rec in enumerate(sampled_records, 1):
        bid = f"ARMGUESS_{idx:03d}"
        blinded_rows.append(
            {
                "blind_id": bid,
                "question": rec["question"],
                "retrieved_snippets": rec["retrieved_snippets"],
                "reply": rec["normalized_reply"],
            }
        )
        key_by_blind_id[bid] = rec

    SAMPLE_150_BLINDED.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in blinded_rows) + "\n",
        encoding="utf-8",
    )

    if not args.skip_judge_run:
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "wo45" / "run_wo45_v3_judge.py"),
            "--profile",
            args.judge_profile,
            "--mode",
            "arm_guess",
            "--input-jsonl",
            str(SAMPLE_150_BLINDED),
            "--output-jsonl",
            str(JUDGE_150_OUT),
            "--workers",
            "4",
            "--shard-size",
            "200",
        ]
        subprocess.run(cmd, check=True)

    pred_map = load_jsonl_by_id(JUDGE_150_OUT)
    yes_by_arm = {"A": 0, "B": 0, "C": 0}
    n_by_arm = {"A": 0, "B": 0, "C": 0}
    correct_3way = 0
    confusion_3way: dict[str, dict[str, int]] = {
        a: {"A": 0, "B": 0, "C": 0} for a in ("A", "B", "C")
    }
    for bid, meta in key_by_blind_id.items():
        arm = str(meta["arm"])
        n_by_arm[arm] += 1
        if str(pred_map[bid]["special_instructions"]) == "YES":
            yes_by_arm[arm] += 1
        guessed = str(pred_map[bid].get("guessed_arm", ""))
        if guessed in ("A", "B", "C"):
            confusion_3way[arm][guessed] += 1
            if guessed == arm:
                correct_3way += 1

    acc_3way_pct = round(100.0 * correct_3way / 150.0, 2)

    # Definition 1: Arm B = YES (50), Arms A & C = NO (100)
    correct_b_only = yes_by_arm["B"] + (n_by_arm["A"] - yes_by_arm["A"]) + (n_by_arm["C"] - yes_by_arm["C"])
    raw_acc_b_only_pct = round(100.0 * correct_b_only / 150.0, 2)
    tpr_b = yes_by_arm["B"] / 50.0
    tnr_ac = ((50 - yes_by_arm["A"]) + (50 - yes_by_arm["C"])) / 100.0
    bal_acc_b_vs_ac_pct = round(100.0 * 0.5 * (tpr_b + tnr_ac), 2)

    # Definition 2: Arms B & C = YES (100), Arm A = NO (50)
    correct_bc = yes_by_arm["B"] + yes_by_arm["C"] + (n_by_arm["A"] - yes_by_arm["A"])
    raw_acc_bc_pct = round(100.0 * correct_bc / 150.0, 2)
    bal_acc_bc_vs_a_pct = round(
        100.0 * 0.5 * (((yes_by_arm["B"] + yes_by_arm["C"]) / 100.0) + ((50 - yes_by_arm["A"]) / 50.0)),
        2,
    )

    # Pairwise 50-vs-50 balanced accuracies
    acc_b_vs_a_pct = round(100.0 * (yes_by_arm["B"] + (50 - yes_by_arm["A"])) / 100.0, 2)
    acc_b_vs_c_pct = round(100.0 * (yes_by_arm["B"] + (50 - yes_by_arm["C"])) / 100.0, 2)

    report = {
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "normalizer_script": "scripts/wo45/normalize_g4v3_replies.py",
        "normalizer_sha256": sha256_file(REPO_ROOT / "scripts" / "wo45" / "normalize_g4v3_replies.py"),
        "acceptance_check_1_lexicon_scan": {
            "n_turns_scanned": len(turns),
            "before_hits_by_arm": before_by_arm,
            "after_hits_by_arm": after_by_arm,
            "total_after_hits": total_after_hits,
            "passed": total_after_hits == 0,
        },
        "acceptance_check_2_arm_guess_150": {
            "judge_profile": args.judge_profile,
            "judge_output_path": "logs/test_reports/wo45/g4v3_arm_guess_150_qwen38_27b.jsonl",
            "judge_output_sha256": sha256_file(JUDGE_150_OUT),
            "n_per_arm": n_by_arm,
            "special_instructions_yes_count_by_arm": yes_by_arm,
            "special_instructions_yes_rate_pct_by_arm": {
                a: round(100.0 * yes_by_arm[a] / 50.0, 2) for a in ("A", "B", "C")
            },
            "three_way_guessed_arm_confusion": confusion_3way,
            "three_way_guessed_arm_accuracy_pct": acc_3way_pct,
            "raw_accuracy_B_is_YES_AC_are_NO_pct": raw_acc_b_only_pct,
            "balanced_accuracy_B_vs_AC_pct": bal_acc_b_vs_ac_pct,
            "raw_accuracy_BC_are_YES_A_is_NO_pct": raw_acc_bc_pct,
            "balanced_accuracy_BC_vs_A_pct": bal_acc_bc_vs_a_pct,
            "pairwise_accuracy_B_vs_A_100_pct": acc_b_vs_a_pct,
            "pairwise_accuracy_B_vs_C_100_pct": acc_b_vs_c_pct,
            "passed_three_way_le_60": acc_3way_pct <= 60.0,
            "passed_balanced_le_60": (
                bal_acc_b_vs_ac_pct <= 60.0
                and acc_b_vs_a_pct <= 60.0
                and acc_b_vs_c_pct <= 60.0
            ),
            "passed_raw_BC_is_YES_le_60": raw_acc_bc_pct <= 60.0,
        },
    }
    REPORT_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
