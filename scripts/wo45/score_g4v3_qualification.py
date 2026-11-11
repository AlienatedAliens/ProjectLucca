"""Score candidate non-Google judges on the RM-2 106-item qualification set (`REVIEW_G4.md:53-59`).

Checks:
  1. D4 accuracy >= 90.0% (on N=66 v2 disputed items, reply-only input) and D4 YES rate in [5%, 95%].
  2. D2 accuracy >= 90.0% (on N=40 v2 non-disputed items) and D2 YES rate in [5%, 95%].
  3. Pairwise Cohen's kappa >= 0.60 on D4 across all pairs of qualified judges from 3 distinct
     non-Google families.
  4. Pilot D1 3-class and binary (`ACCURATE` vs rest) pairwise Cohen's kappa across qualified judges
     (`REVIEW_G4.md:50`: D1 becomes co-primary iff pilot kappa >= 0.60, else remains secondary).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.wo45.g4_kappa import cohen_kappa, load_jsonl_by_id  # noqa: E402

WO45_DIR = REPO_ROOT / "logs" / "test_reports" / "wo45"
QUAL_SET_PATH = WO45_DIR / "g4v3_judge_qualification_set.jsonl"
DEFAULT_REPORT_OUT = WO45_DIR / "g4v3_judge_qualification_report.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def score_single_judge(
    gold_rows: list[dict[str, Any]], judge_path: Path
) -> dict[str, Any]:
    pred_map = load_jsonl_by_id(judge_path)
    d4_gold = [r for r in gold_rows if r["eval_target"] == "D4"]
    d2_gold = [r for r in gold_rows if r["eval_target"] == "D2"]
    d1_gold = [r for r in gold_rows if r.get("gold_D1_pilot") is not None]

    d4_correct = 0
    d4_yes = 0
    d4_errors: list[dict[str, str]] = []
    for r in d4_gold:
        bid = str(r["blind_id"])
        p = str(pred_map[bid]["D4"])
        g = str(r["gold_D4"])
        if p == "YES":
            d4_yes += 1
        if p == g:
            d4_correct += 1
        else:
            d4_errors.append({"blind_id": bid, "gold": g, "pred": p, "note": str(r["construction_note"])})

    d2_correct = 0
    d2_yes = 0
    no_ans_correct = 0
    d2_errors: list[dict[str, str]] = []
    for r in d2_gold:
        bid = str(r["blind_id"])
        p = str(pred_map[bid]["D2"])
        p_na = str(pred_map[bid]["NO_ANSWER"])
        g = str(r["gold_D2"])
        g_na = str(r["gold_NO_ANSWER"])
        if p == "YES":
            d2_yes += 1
        if p == g:
            d2_correct += 1
        else:
            d2_errors.append({"blind_id": bid, "gold": g, "pred": p, "note": str(r["construction_note"])})
        if p_na == g_na:
            no_ans_correct += 1

    d1_correct = 0
    for r in d1_gold:
        bid = str(r["blind_id"])
        if str(pred_map[bid]["D1"]) == str(r["gold_D1_pilot"]):
            d1_correct += 1

    sample_row = next(iter(pred_map.values()))
    n_d4 = len(d4_gold)
    n_d2 = len(d2_gold)
    n_d1 = len(d1_gold)
    d4_acc = 100.0 * d4_correct / n_d4
    d2_acc = 100.0 * d2_correct / n_d2
    d4_yes_pct = 100.0 * d4_yes / n_d4
    d2_yes_pct = 100.0 * d2_yes / n_d2

    passes_individual = (
        d4_acc >= 90.0
        and d2_acc >= 90.0
        and 5.0 <= d4_yes_pct <= 95.0
        and 5.0 <= d2_yes_pct <= 95.0
    )

    return {
        "file": str(judge_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "file_sha256": sha256_file(judge_path),
        "judge_model": str(sample_row["judge_model"]),
        "judge_family": str(sample_row["judge_family"]),
        "model_sha256": str(sample_row["model_sha256"]),
        "provenance_source": str(sample_row["provenance_source"]),
        "D4": {
            "n": n_d4,
            "correct": d4_correct,
            "accuracy_pct": round(d4_acc, 2),
            "yes_count": d4_yes,
            "yes_rate_pct": round(d4_yes_pct, 2),
            "errors": d4_errors,
        },
        "D2": {
            "n": n_d2,
            "correct": d2_correct,
            "accuracy_pct": round(d2_acc, 2),
            "yes_count": d2_yes,
            "yes_rate_pct": round(d2_yes_pct, 2),
            "no_answer_correct": no_ans_correct,
            "no_answer_accuracy_pct": round(100.0 * no_ans_correct / n_d2, 2),
            "errors": d2_errors,
        },
        "D1_pilot": {
            "n": n_d1,
            "correct": d1_correct,
            "accuracy_pct": round(100.0 * d1_correct / n_d1, 2),
        },
        "passes_individual_bars": passes_individual,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("judge_files", nargs="+", type=Path)
    parser.add_argument("--qual-jsonl", type=Path, default=QUAL_SET_PATH)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_REPORT_OUT)
    args = parser.parse_args()

    gold_rows = [
        json.loads(ln)
        for ln in args.qual_jsonl.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    d4_ids = [str(r["blind_id"]) for r in gold_rows if r["eval_target"] == "D4"]
    d2_ids = [str(r["blind_id"]) for r in gold_rows if r["eval_target"] == "D2"]
    d1_ids = [str(r["blind_id"]) for r in gold_rows if r.get("gold_D1_pilot") is not None]

    candidates: list[dict[str, Any]] = []
    maps_by_model: dict[str, dict[str, dict[str, object]]] = {}
    for jf in args.judge_files:
        sc = score_single_judge(gold_rows, jf)
        candidates.append(sc)
        maps_by_model[sc["judge_model"]] = load_jsonl_by_id(jf)

    individually_qualified = [c for c in candidates if c["passes_individual_bars"]]
    pairwise_kappa: list[dict[str, Any]] = []
    for c1, c2 in combinations(individually_qualified, 2):
        m1 = maps_by_model[c1["judge_model"]]
        m2 = maps_by_model[c2["judge_model"]]
        d4_k = cohen_kappa([str(m1[i]["D4"]) for i in d4_ids], [str(m2[i]["D4"]) for i in d4_ids])
        d2_k = cohen_kappa([str(m1[i]["D2"]) for i in d2_ids], [str(m2[i]["D2"]) for i in d2_ids])
        d1_3c = cohen_kappa([str(m1[i]["D1"]) for i in d1_ids], [str(m2[i]["D1"]) for i in d1_ids])
        d1_bin = cohen_kappa(
            ["1" if str(m1[i]["D1"]) == "ACCURATE" else "0" for i in d1_ids],
            ["1" if str(m2[i]["D1"]) == "ACCURATE" else "0" for i in d1_ids],
        )
        pairwise_kappa.append(
            {
                "judge_a": c1["judge_model"],
                "family_a": c1["judge_family"],
                "judge_b": c2["judge_model"],
                "family_b": c2["judge_family"],
                "distinct_families": c1["judge_family"] != c2["judge_family"],
                "D4_kappa": d4_k,
                "D2_kappa": d2_k,
                "D1_pilot_3class_kappa": d1_3c,
                "D1_pilot_binary_kappa": d1_bin,
                "passes_d4_kappa_060": float(str(d4_k["cohen_kappa"])) >= 0.60,
            }
        )

    # Select top 3 distinct non-Google families that satisfy all pairwise D4 kappa >= 0.60
    selected_panel: list[dict[str, Any]] = []
    d1_promoted = False
    for trio in combinations(individually_qualified, 3):
        fams = {t["judge_family"] for t in trio}
        if len(fams) < 3:
            continue
        names = {t["judge_model"] for t in trio}
        trio_pairs = [
            pk
            for pk in pairwise_kappa
            if pk["judge_a"] in names and pk["judge_b"] in names
        ]
        if len(trio_pairs) == 3 and all(pk["passes_d4_kappa_060"] for pk in trio_pairs):
            selected_panel = [
                {
                    "role": f"Judge_{idx + 1}",
                    "judge_model": t["judge_model"],
                    "judge_family": t["judge_family"],
                    "model_sha256": t["model_sha256"],
                    "D4_accuracy_pct": t["D4"]["accuracy_pct"],
                    "D2_accuracy_pct": t["D2"]["accuracy_pct"],
                }
                for idx, t in enumerate(trio)
            ]
            d1_promoted = all(
                float(str(pk["D1_pilot_3class_kappa"]["cohen_kappa"])) >= 0.60
                for pk in trio_pairs
            )
            break

    report = {
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "qualification_set_path": str(args.qual_jsonl.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "qualification_set_sha256": sha256_file(args.qual_jsonl),
        "candidates_tested": candidates,
        "qualified_pairwise_kappa": pairwise_kappa,
        "selected_3_family_panel": selected_panel,
        "three_distinct_non_google_families_qualified": len(selected_panel) == 3,
        "D1_pilot_decision": (
            "PROMOTED_TO_CO_PRIMARY" if d1_promoted else "REMAINS_SECONDARY_PER_G4_1"
        ),
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
