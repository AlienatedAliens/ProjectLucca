"""Pre-registered head-to-head NLI Verifier v2 evaluation (`verifier_minilm` vs `verifier_deberta_v3_xsmall_ov`).

Verifies SHA-256 hashes in `logs/test_reports/nli_verifier_v2_prereg_lock.json` BEFORE running
single-shot evaluation on:
  1. `data/benchmarks/nli_holdout_v2_120.jsonl` (pre-registered blinded out-of-sample N=120 holdout)
  2. `data/benchmarks/nli_eval/pairs_v1.jsonl` (historical WO-37 N=100 reference benchmark, if present)
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.senses.verifier import VerifierWorker  # noqa: E402

LOCK_PATH = REPO_ROOT / "logs" / "test_reports" / "nli_verifier_v2_prereg_lock.json"
HOLDOUT_V2_PATH = REPO_ROOT / "data" / "benchmarks" / "nli_holdout_v2_120.jsonl"
PAIRS_V1_PATH = REPO_ROOT / "data" / "benchmarks" / "nli_eval" / "pairs_v1.jsonl"
OUT_REPORT_PATH = REPO_ROOT / "logs" / "test_reports" / "nli_verifier_v2_report.json"

CLASSES = ("ENTAILMENT", "CONTRADICTION", "NEUTRAL")
PRED_CLASSES = ("ENTAILMENT", "CONTRADICTION", "NEUTRAL", "UNCERTAIN")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wilson_ci_95(k: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def exact_mcnemar_two_sided(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    return round(min(1.0, 2.0 * tail), 8)


def resolve_model_dir(name: str) -> Path:
    candidates = (
        REPO_ROOT / "models" / name,
        Path(r"C:\ProjectLucca\models") / name,
    )
    for cand in candidates:
        if (cand / "openvino_model.xml").exists():
            return cand
    raise FileNotFoundError(f"Model directory {name} not found in repo or C:\\ProjectLucca\\models")


def verify_lock(lock_data: dict[str, Any]) -> dict[str, str]:
    verified: dict[str, str] = {}
    for rel_path, expected_sha in lock_data["locked_files_sha256"].items():
        fpath = REPO_ROOT / rel_path
        if not fpath.exists():
            alt = Path(r"C:\ProjectLucca") / rel_path
            fpath = alt if alt.exists() else fpath
        actual_sha = sha256_file(fpath)
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"Pre-registration lock hash mismatch for {rel_path}: "
                f"expected={expected_sha} actual={actual_sha}"
            )
        verified[rel_path] = actual_sha
    return verified


def load_pairs(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        row = json.loads(line)
        assert row["gold"] in CLASSES, f"Unexpected gold label {row['gold']} in {path}"
        items.append(row)
    return items


def evaluate_model_on_dataset(
    worker: VerifierWorker,
    items: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    worker.check_consistency(premise="Warmup premise.", hypothesis="Warmup hypothesis.")
    worker._cache.clear()

    confusion: dict[str, dict[str, int]] = {g: dict.fromkeys(PRED_CLASSES, 0) for g in CLASSES}
    gold_dist: dict[str, int] = dict.fromkeys(CLASSES, 0)
    pred_dist: dict[str, int] = dict.fromkeys(PRED_CLASSES, 0)

    latencies: list[float] = []
    records: list[dict[str, Any]] = []
    degraded_count = 0

    for row in items:
        worker._cache.clear()
        t0 = time.perf_counter()
        res = worker.check_consistency(premise=row["premise"], hypothesis=row["hypothesis"])
        wall_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(wall_ms)

        gold = str(row["gold"])
        pred = str(res.label.value).upper()
        gold_dist[gold] += 1
        pred_dist[pred] = pred_dist.get(pred, 0) + 1
        confusion[gold][pred] += 1
        if res.degraded:
            degraded_count += 1

        records.append(
            {
                "id": row["id"],
                "domain": row.get("domain", ""),
                "gold": gold,
                "pred": pred,
                "correct": pred == gold,
                "entailment_prob": res.entailment_prob,
                "contradiction_prob": res.contradiction_prob,
                "neutral_prob": res.neutral_prob,
                "latency_ms": round(wall_ms, 2),
                "degraded": res.degraded,
            }
        )

    n_total = len(items)
    n_correct = sum(1 for r in records if r["correct"])
    accuracy = round(n_correct / n_total, 4)

    per_class: dict[str, Any] = {}
    f1s: list[float] = []
    for cls in CLASSES:
        tp = confusion[cls][cls]
        fp = sum(confusion[other][cls] for other in CLASSES if other != cls)
        fn = gold_dist[cls] - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
        per_class[cls] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "recall_wilson_95_ci": list(wilson_ci_95(tp, gold_dist[cls])),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    polarity_inversions = (
        confusion["ENTAILMENT"]["CONTRADICTION"] + confusion["CONTRADICTION"]["ENTAILMENT"]
    )
    sorted_lat = sorted(latencies)
    p50_ms = sorted_lat[int(len(sorted_lat) * 0.50)]
    p95_ms = sorted_lat[min(len(sorted_lat) - 1, int(len(sorted_lat) * 0.95))]

    summary = {
        "num_pairs": n_total,
        "device": worker.device,
        "model_dir": str(worker.model_dir),
        "accuracy": accuracy,
        "accuracy_counts": f"{n_correct}/{n_total}",
        "accuracy_wilson_95_ci": list(wilson_ci_95(n_correct, n_total)),
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "polarity_inversions_ent_con": polarity_inversions,
        "per_class": per_class,
        "confusion_matrix": confusion,
        "gold_distribution": gold_dist,
        "predicted_distribution": pred_dist,
        "degraded_count": degraded_count,
        "latency_ms_mean": round(sum(latencies) / len(latencies), 2),
        "latency_ms_p50": round(p50_ms, 2),
        "latency_ms_p95": round(p95_ms, 2),
        "latency_ms_max": round(max(latencies), 2),
    }
    return summary, records


def paired_comparison(
    base_records: list[dict[str, Any]],
    v2_records: list[dict[str, Any]],
) -> dict[str, Any]:
    assert len(base_records) == len(v2_records)
    v2_wins_all = sum(
        1
        for b, v in zip(base_records, v2_records, strict=True)
        if v["correct"] and not b["correct"]
    )
    base_wins_all = sum(
        1
        for b, v in zip(base_records, v2_records, strict=True)
        if b["correct"] and not v["correct"]
    )

    ent_pairs = [
        (b, v) for b, v in zip(base_records, v2_records, strict=True) if b["gold"] == "ENTAILMENT"
    ]
    v2_wins_ent = sum(1 for b, v in ent_pairs if v["correct"] and not b["correct"])
    base_wins_ent = sum(1 for b, v in ent_pairs if b["correct"] and not v["correct"])

    return {
        "overall_accuracy_discordant_v2_vs_minilm": f"{v2_wins_all}:{base_wins_all}",
        "overall_accuracy_mcnemar_p_two_sided": exact_mcnemar_two_sided(v2_wins_all, base_wins_all),
        "entailment_recall_discordant_v2_vs_minilm": f"{v2_wins_ent}:{base_wins_ent}",
        "entailment_recall_mcnemar_p_two_sided": exact_mcnemar_two_sided(
            v2_wins_ent, base_wins_ent
        ),
    }


def main() -> None:
    lock_data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    verified_hashes = verify_lock(lock_data)
    print(f"[LOCK VERIFIED] {len(verified_hashes)} pre-registered files match SHA-256 lock.")

    if not HOLDOUT_V2_PATH.exists():
        raise FileNotFoundError(f"Missing holdout corpus: {HOLDOUT_V2_PATH}")

    minilm_dir = resolve_model_dir("verifier_minilm")
    deberta_dir = resolve_model_dir("verifier_deberta_v3_xsmall_ov")

    worker_minilm = VerifierWorker(model_dir=minilm_dir, timeout_ms=50.0)
    worker_deberta = VerifierWorker(model_dir=deberta_dir, timeout_ms=50.0)

    holdout_items = load_pairs(HOLDOUT_V2_PATH)
    holdout_sha = sha256_file(HOLDOUT_V2_PATH)

    minilm_holdout_sum, minilm_holdout_rec = evaluate_model_on_dataset(worker_minilm, holdout_items)
    deberta_holdout_sum, deberta_holdout_rec = evaluate_model_on_dataset(
        worker_deberta, holdout_items
    )

    datasets_out: dict[str, Any] = {
        "nli_holdout_v2_120": {
            "dataset_path": "data/benchmarks/nli_holdout_v2_120.jsonl",
            "dataset_sha256": holdout_sha,
            "verifier_minilm": minilm_holdout_sum,
            "verifier_deberta_v3_xsmall_ov": deberta_holdout_sum,
            "paired_comparison": paired_comparison(minilm_holdout_rec, deberta_holdout_rec),
        }
    }

    if PAIRS_V1_PATH.exists():
        v1_items = load_pairs(PAIRS_V1_PATH)
        minilm_v1_sum, minilm_v1_rec = evaluate_model_on_dataset(worker_minilm, v1_items)
        deberta_v1_sum, deberta_v1_rec = evaluate_model_on_dataset(worker_deberta, v1_items)
        datasets_out["pairs_v1_100"] = {
            "dataset_path": "data/benchmarks/nli_eval/pairs_v1.jsonl",
            "dataset_sha256": sha256_file(PAIRS_V1_PATH),
            "verifier_minilm": minilm_v1_sum,
            "verifier_deberta_v3_xsmall_ov": deberta_v1_sum,
            "paired_comparison": paired_comparison(minilm_v1_rec, deberta_v1_rec),
        }

    report = {
        "evaluation_id": "WO45-STEP4A-NLI-VERIFIER-V2",
        "evaluated_at_utc": datetime.now(UTC).isoformat(),
        "prereg_lock_path": "logs/test_reports/nli_verifier_v2_prereg_lock.json",
        "prereg_lock_sha256": sha256_file(LOCK_PATH),
        "verified_locked_files_sha256": verified_hashes,
        "decision_policy": {
            "uncertainty_band": [0.40, 0.60],
            "dominant_prob_threshold": 0.60,
            "timeout_ms": 50.0,
        },
        "datasets": datasets_out,
    }
    OUT_REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[REPORT WRITTEN] {OUT_REPORT_PATH}")
    for dname, dval in datasets_out.items():
        m_acc = dval["verifier_minilm"]["accuracy"]
        m_ent = dval["verifier_minilm"]["per_class"]["ENTAILMENT"]["recall"]
        d_acc = dval["verifier_deberta_v3_xsmall_ov"]["accuracy"]
        d_ent = dval["verifier_deberta_v3_xsmall_ov"]["per_class"]["ENTAILMENT"]["recall"]
        d_p95 = dval["verifier_deberta_v3_xsmall_ov"]["latency_ms_p95"]
        print(
            f"  {dname}: MiniLM acc={m_acc:.1%} ent_rec={m_ent:.1%} -> "
            f"DeBERTa-v3-xsmall acc={d_acc:.1%} ent_rec={d_ent:.1%} (p95={d_p95:.2f}ms)"
        )


if __name__ == "__main__":
    main()
