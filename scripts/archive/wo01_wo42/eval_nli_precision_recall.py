#!/usr/bin/env python3
"""NLI precision/recall evaluation harness for the Lucca semantic verifier.

Runs the OpenVINO VerifierWorker (src/lucca/senses/verifier.py) over a
hand-labeled premise/hypothesis pair set (pairs_v1.jsonl) and reports
per-class precision, recall, and F1, plus a confusion matrix.

Artifacts written to the output directory:
  - predictions.jsonl : one record per pair (gold, predicted, probabilities)
  - summary.json      : aggregate metrics (per-class P/R/F1, macro, accuracy)
  - worksheet.md      : human-readable results worksheet

Usage:
  uv run python scripts/eval_nli_precision_recall.py \
      --pairs data/benchmarks/nli_eval/pairs_v1.jsonl \
      --device CPU \
      --output-dir data/benchmarks/nli_eval/results
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

# Allow running from repo root without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.senses.verifier import VerifierWorker  # noqa: E402

CLASSES = ["ENTAILMENT", "CONTRADICTION", "NEUTRAL"]
# UNCERTAIN (degraded / low-confidence) is treated as "not the gold class"
# for every class in the one-vs-rest computation; it is reported separately.
NON_CLASS = "UNCERTAIN"


def load_pairs(path: Path) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            for field in ("id", "premise", "hypothesis", "gold"):
                if field not in rec:
                    raise ValueError(f"{path}:{line_no} missing field '{field}'")
            if rec["gold"] not in CLASSES:
                raise ValueError(
                    f"{path}:{line_no} invalid gold label '{rec['gold']}'"
                )
            pairs.append(rec)
    return pairs


def one_vs_rest(golds: list[str], preds: list[str], cls: str) -> dict[str, float]:
    tp = sum(1 for g, p in zip(golds, preds) if g == cls and p == cls)
    fp = sum(1 for g, p in zip(golds, preds) if g != cls and p == cls)
    fn = sum(1 for g, p in zip(golds, preds) if g == cls and p != cls)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pairs",
        type=Path,
        default=REPO_ROOT / "data/benchmarks/nli_eval/pairs_v1.jsonl",
        help="Path to hand-labeled JSONL pair set",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="CPU",
        help="OpenVINO device (CPU, NPU, GPU). Default CPU.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data/benchmarks/nli_eval/results",
        help="Directory for predictions/summary/worksheet artifacts",
    )
    parser.add_argument(
        "--timeout-ms",
        type=float,
        default=50.0,
        help="Verifier timeout in milliseconds",
    )
    args = parser.parse_args()

    pairs = load_pairs(args.pairs)
    print(f"Loaded {len(pairs)} pairs from {args.pairs}")

    worker = VerifierWorker(device=args.device, timeout_ms=args.timeout_ms)
    print(f"Verifier device: {worker.device} (model_dir={worker.model_dir})")
    if worker.compiled is None or worker.tokenizer is None:
        print(
            "ERROR: verifier model or tokenizer unavailable; "
            "cannot run evaluation. Check DEFAULT_VERIFIER_DIR.",
            file=sys.stderr,
        )
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = args.output_dir / "predictions.jsonl"

    golds: list[str] = []
    preds: list[str] = []
    latencies: list[float] = []
    degraded_count = 0
    cached_count = 0

    with predictions_path.open("w", encoding="utf-8") as out_fh:
        for i, pair in enumerate(pairs, start=1):
            result = worker.check_consistency(
                premise=pair["premise"], hypothesis=pair["hypothesis"]
            )
            golds.append(pair["gold"])
            preds.append(result.label.value)
            latencies.append(result.latency_ms)
            if result.degraded:
                degraded_count += 1
            if result.cached:
                cached_count += 1

            record = {
                "id": pair["id"],
                "domain": pair.get("domain", ""),
                "gold": pair["gold"],
                "predicted": result.label.value,
                "correct": result.label.value == pair["gold"],
                "entailment_prob": round(result.entailment_prob, 4),
                "contradiction_prob": round(result.contradiction_prob, 4),
                "neutral_prob": round(result.neutral_prob, 4),
                "confidence": round(result.confidence, 4),
                "latency_ms": result.latency_ms,
                "degraded": result.degraded,
                "cached": result.cached,
            }
            out_fh.write(json.dumps(record, ensure_ascii=False) + "\n")

            marker = "OK " if record["correct"] else "MISS"
            print(
                f"[{i:3d}/{len(pairs)}] {marker} gold={pair['gold']:<13s} "
                f"pred={result.label.value:<13s} p_e={record['entailment_prob']:.3f} "
                f"p_c={record['contradiction_prob']:.3f} p_n={record['neutral_prob']:.3f} "
                f"lat={result.latency_ms:.1f}ms"
            )

    # ---- Aggregate metrics ----
    per_class = {cls: one_vs_rest(golds, preds, cls) for cls in CLASSES}
    macro_f1 = sum(per_class[c]["f1"] for c in CLASSES) / len(CLASSES)
    accuracy = sum(1 for g, p in zip(golds, preds) if g == p) / len(golds)
    confusion = Counter(zip(golds, preds))
    confusion_matrix = {
        g: {p: confusion.get((g, p), 0) for p in CLASSES + [NON_CLASS]} for g in CLASSES
    }

    summary = {
        "dataset": str(args.pairs),
        "num_pairs": len(pairs),
        "device": worker.device,
        "model_dir": str(worker.model_dir),
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": confusion_matrix,
        "gold_distribution": dict(Counter(golds)),
        "predicted_distribution": dict(Counter(preds)),
        "degraded_count": degraded_count,
        "cached_count": cached_count,
        "latency_ms_mean": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "latency_ms_p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 2)
        if latencies
        else 0.0,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # ---- Worksheet ----
    ws_lines = [
        "# NLI Precision/Recall Worksheet",
        "",
        f"- Dataset: `{args.pairs}` ({len(pairs)} hand-labeled pairs)",
        f"- Device: `{worker.device}`",
        f"- Timestamp: {summary['timestamp_utc']}",
        "",
        "## Headline metrics",
        "",
        f"- Accuracy: {accuracy:.3f}",
        f"- Macro F1: {macro_f1:.3f}",
        f"- Mean latency: {summary['latency_ms_mean']:.1f} ms | p95: {summary['latency_ms_p95']:.1f} ms",
        f"- Degraded (UNCERTAIN) results: {degraded_count}",
        "",
        "## Per-class one-vs-rest metrics",
        "",
        "| Class | Precision | Recall | F1 | TP | FP | FN |",
        "|---|---|---|---|---|---|---|",
    ]
    for cls in CLASSES:
        m = per_class[cls]
        ws_lines.append(
            f"| {cls} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} "
            f"| {m['tp']} | {m['fp']} | {m['fn']} |"
        )
    ws_lines += [
        "",
        "## Confusion matrix (rows = gold, cols = predicted)",
        "",
        "| gold \\ pred | " + " | ".join(CLASSES + [NON_CLASS]) + " |",
        "|---|" + "---|" * (len(CLASSES) + 1),
    ]
    for g in CLASSES:
        row = confusion_matrix[g]
        ws_lines.append(
            f"| {g} | " + " | ".join(str(row[p]) for p in CLASSES + [NON_CLASS]) + " |"
        )
    ws_lines += [
        "",
        "## Labeling-gate caveat",
        "",
        "pairs_v1.jsonl is a 100-pair hand-labeled set authored by a single",
        "annotator (the project developer) and is not drawn from an independent",
        "public benchmark (e.g., SNLI/MNLI held-out splits). Numbers here are",
        "directional engineering evidence for the verifier's precision/recall on",
        "Lucca-style premise/hypothesis pairs, not a claim of general NLI",
        "benchmark parity. A second-annotator agreement pass is required before",
        "citing these figures as benchmark results.",
        "",
    ]
    worksheet_path = args.output_dir / "worksheet.md"
    worksheet_path.write_text("\n".join(ws_lines), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(f"Accuracy : {accuracy:.3f}")
    print(f"Macro F1 : {macro_f1:.3f}")
    for cls in CLASSES:
        m = per_class[cls]
        print(
            f"{cls:<13s} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f}"
        )
    print(f"Mean latency: {summary['latency_ms_mean']:.1f} ms (p95 {summary['latency_ms_p95']:.1f} ms)")
    print(f"Degraded: {degraded_count} | Cached: {cached_count}")
    print(f"\nArtifacts written to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
