"""
Natural Language Inference (NLI) Inter-Annotator Agreement Scorer
Compares a completed second-annotator worksheet against the ground truth labels in pairs_v1.jsonl.
Computes:
- Percentage Agreement (Raw Accuracy)
- Cohen's Kappa (chance-adjusted agreement)
- Per-Class Precision, Recall, and F1
- Full 3x3 Confusion Matrix
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

CLASSES = ["ENTAILMENT", "CONTRADICTION", "NEUTRAL"]


def load_gold_labels(gold_path: Path) -> dict[str, str]:
    gold_map: dict[str, str] = {}
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        gold_map[item["id"]] = item["gold"].strip().upper()
    return gold_map


def load_second_annotations(input_path: Path) -> dict[str, str]:
    annot_map: dict[str, str] = {}
    if input_path.suffix.lower() == ".csv":
        with open(input_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get("pair_id", "").strip()
                lbl = row.get("annotator_label", "").strip().upper()
                if pid and lbl:
                    annot_map[pid] = lbl
    else:
        for line in input_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            pid = item.get("pair_id", item.get("id", "")).strip()
            lbl = item.get("annotator_label", item.get("label", item.get("gold", ""))).strip().upper()
            if pid and lbl:
                annot_map[pid] = lbl
    return annot_map


def compute_cohens_kappa(gold: list[str], pred: list[str]) -> float:
    n = len(gold)
    if n == 0:
        return 0.0

    # Observed agreement
    p_o = sum(1 for g, p in zip(gold, pred) if g == p) / n

    # Expected agreement
    gold_counts = Counter(gold)
    pred_counts = Counter(pred)
    all_classes = set(gold_counts.keys()) | set(pred_counts.keys())

    p_e = sum((gold_counts.get(c, 0) / n) * (pred_counts.get(c, 0) / n) for c in all_classes)

    if p_e >= 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score second annotator agreement for NLI pairs.")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to completed annotator worksheet (.csv or .jsonl)",
    )
    parser.add_argument(
        "--gold",
        type=Path,
        default=Path("data/benchmarks/nli_eval/pairs_v1.jsonl"),
        help="Path to gold pairs_v1.jsonl",
    )
    args = parser.parse_args()

    if not args.gold.exists():
        print(f"Error: Gold file not found at {args.gold}", file=sys.stderr)
        sys.exit(1)

    if not args.input.exists():
        print(f"Error: Annotator input not found at {args.input}", file=sys.stderr)
        sys.exit(1)

    gold_map = load_gold_labels(args.gold)
    annot_map = load_second_annotations(args.input)

    common_ids = [pid for pid in gold_map if pid in annot_map]
    if not common_ids:
        print("Error: No overlapping pair IDs found between gold and annotator files.", file=sys.stderr)
        sys.exit(1)

    gold_list = [gold_map[pid] for pid in common_ids]
    annot_list = [annot_map[pid] for pid in common_ids]
    n = len(common_ids)

    # Basic accuracy
    correct = sum(1 for g, a in zip(gold_list, annot_list) if g == a)
    acc = correct / n
    kappa = compute_cohens_kappa(gold_list, annot_list)

    print("=" * 70)
    print("NLI INTER-ANNOTATOR AGREEMENT REPORT")
    print("=" * 70)
    print(f"Total Evaluated Pairs: {n} / {len(gold_map)}")
    print(f"Raw Percent Agreement: {acc * 100:.2f}% ({correct}/{n})")
    print(f"Cohen's Kappa (kappa):     {kappa:.4f}")

    interpretation = (
        "Almost Perfect Agreement (kappa >= 0.81)"
        if kappa >= 0.81
        else "Substantial Agreement (0.61 - 0.80)"
        if kappa >= 0.61
        else "Moderate Agreement (0.41 - 0.60)"
        if kappa >= 0.41
        else "Fair to Poor Agreement (kappa <= 0.40)"
    )
    print(f"Landis & Koch Rating:  {interpretation}")
    print("-" * 70)

    # Per-class metrics
    print(f"{'Class':<15} {'Gold':<8} {'Annotated':<10} {'Precision':<12} {'Recall':<12} {'F1-Score':<10}")
    print("-" * 70)
    for c in CLASSES:
        tp = sum(1 for g, a in zip(gold_list, annot_list) if g == c and a == c)
        fp = sum(1 for g, a in zip(gold_list, annot_list) if g != c and a == c)
        fn = sum(1 for g, a in zip(gold_list, annot_list) if g == c and a != c)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        gold_n = sum(1 for g in gold_list if g == c)
        pred_n = sum(1 for a in annot_list if a == c)
        print(f"{c:<15} {gold_n:<8} {pred_n:<10} {prec:<12.3f} {rec:<12.3f} {f1:<10.3f}")

    print("-" * 70)
    print("Confusion Matrix (Rows: Gold, Columns: Second Annotator):")
    print(f"{'Gold \\\\ Annot':<16} {'ENTAIL':<10} {'CONTRA':<10} {'NEUTRAL':<10}")
    for g_cls in CLASSES:
        row_str = f"{g_cls:<16}"
        for a_cls in CLASSES:
            cnt = sum(1 for g, a in zip(gold_list, annot_list) if g == g_cls and a == a_cls)
            row_str += f" {cnt:<10}"
        print(row_str)
    print("=" * 70)


if __name__ == "__main__":
    main()
