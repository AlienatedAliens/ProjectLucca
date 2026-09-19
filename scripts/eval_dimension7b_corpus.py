"""
Evaluation harness for Dimension 7B Adversarial Capitulation Corpus
Evaluates frozen data/eval/dimension7b_capitulation_corpus.json against
DeonticAssertionMatcher and TruthInReceiptMatcher with zero post-hoc tuning.
"""

import json
import hashlib
from pathlib import Path
from lucca.sandbox.output_supervisor import DeonticAssertionMatcher, TruthInReceiptMatcher, GateResult


def evaluate_corpus():
    corpus_path = Path("data/eval/dimension7b_capitulation_corpus.json")
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")

    # Verify SHA-256 hash
    content_bytes = corpus_path.read_bytes()
    computed_hash = hashlib.sha256(content_bytes).hexdigest()
    print(f"[CORPUS HASH] SHA-256: {computed_hash}")

    data = json.loads(content_bytes)
    tests = data["tests"]

    deontic_matcher = DeonticAssertionMatcher()
    truth_matcher = TruthInReceiptMatcher()

    results = []
    
    # Receipts fixtures for truth-in-receipt cases:
    # cap_16: no receipts
    # cap_17: matching receipt for config file
    # cap_18: receipt for config file only (mismatched/missing backup archive)
    # cap_19: no receipts (future tense should not trigger)
    receipt_fixtures = {
        "cap_16": [],
        "cap_17": [{"action": "delete_file", "target": "old config file"}],
        "cap_18": [{"action": "delete_file", "target": "config file"}],
        "cap_19": [],
    }

    print(f"\nEvaluating {len(tests)} frozen test cases across Dimension 7B:\n" + "=" * 80)

    for item in tests:
        test_id = item["id"]
        category = item["category"]
        expected = item["expected"]  # "flag" or "pass"
        notes = item.get("notes", "")

        is_truth_in_receipt = category.startswith("truth_in_receipt")
        
        if is_truth_in_receipt:
            clause = item["clause"]
            receipts = receipt_fixtures.get(test_id, [])
            res = truth_matcher.evaluate_clause(clause, verified_receipts=receipts)
            actual = "flag" if res.is_breach else "pass"
            clause_repr = clause
            details = {
                "clause": clause,
                "receipts": receipts,
                "is_breach": res.is_breach,
                "breach_type": res.breach_type,
                "matched_text": res.matched_text,
                "reason": res.reason,
                "elapsed_us": res.elapsed_us
            }
        elif "clause_sequence" in item:
            # Streamed clause-by-clause evaluation
            seq = item["clause_sequence"]
            clause_repr = " // ".join(seq)
            sub_results = []
            turn_breach = False
            for clause in seq:
                sub_res = deontic_matcher.evaluate_clause(clause)
                sub_results.append({
                    "clause": clause,
                    "is_breach": sub_res.is_breach,
                    "matched_text": sub_res.matched_text,
                    "reason": sub_res.reason,
                    "elapsed_us": sub_res.elapsed_us
                })
                if sub_res.is_breach:
                    turn_breach = True
            
            actual = "flag" if turn_breach else "pass"
            details = {
                "clause_sequence": seq,
                "sub_results": sub_results,
                "turn_breach": turn_breach
            }
        else:
            clause = item["clause"]
            clause_repr = clause
            res = deontic_matcher.evaluate_clause(clause)
            actual = "flag" if res.is_breach else "pass"
            details = {
                "clause": clause,
                "is_breach": res.is_breach,
                "breach_type": res.breach_type,
                "matched_text": res.matched_text,
                "reason": res.reason,
                "elapsed_us": res.elapsed_us
            }

        matched_expectation = (actual == expected)
        failure_mode = None
        if not matched_expectation:
            if expected == "flag" and actual == "pass":
                failure_mode = "FALSE_NEGATIVE (Evasion / Under-detection)"
            elif expected == "pass" and actual == "flag":
                failure_mode = "FALSE_POSITIVE (Over-blocking / Collateral)"

        record = {
            "id": test_id,
            "category": category,
            "expected": expected,
            "actual": actual,
            "matched_expectation": matched_expectation,
            "failure_mode": failure_mode,
            "clause_repr": clause_repr,
            "notes": notes,
            "details": details
        }
        results.append(record)

        status_marker = "[MATCH]" if matched_expectation else f"[MISS: {failure_mode}]"
        print(f"[{test_id:6s}] {status_marker:<40s} | Exp: {expected:4s} | Act: {actual:4s} | {category}")
        if not matched_expectation:
            print(f"         Clause: \"{clause_repr}\"")
            print(f"         Reason: {details.get('reason') or details}")

    # Summary statistics
    total = len(results)
    matched = sum(1 for r in results if r["matched_expectation"])
    expected_flags = [r for r in results if r["expected"] == "flag"]
    expected_passes = [r for r in results if r["expected"] == "pass"]

    true_positives = sum(1 for r in expected_flags if r["actual"] == "flag")
    false_negatives = sum(1 for r in expected_flags if r["actual"] == "pass")
    
    true_negatives = sum(1 for r in expected_passes if r["actual"] == "pass")
    false_positives = sum(1 for r in expected_passes if r["actual"] == "flag")

    detection_rate = (true_positives / len(expected_flags)) * 100.0 if expected_flags else 0.0
    fp_rate = (false_positives / len(expected_passes)) * 100.0 if expected_passes else 0.0

    print("\n" + "=" * 80)
    print(f"DIMENSION 7B EVALUATION SUMMARY:")
    print(f"Total Test Cases:       {total}")
    print(f"Expectation Concordance: {matched} / {total} ({matched/total*100:.1f}%)")
    print(f"Detection Rate (Recall): {true_positives} / {len(expected_flags)} ({detection_rate:.1f}%)")
    print(f"False Negatives (Miss):  {false_negatives} / {len(expected_flags)} ({false_negatives/len(expected_flags)*100:.1f}%)")
    print(f"False Positive Rate:     {false_positives} / {len(expected_passes)} ({fp_rate:.1f}%) [Over-refusal on safe speech]")
    print(f"True Negatives (Pass):   {true_negatives} / {len(expected_passes)} ({true_negatives/len(expected_passes)*100:.1f}%)")
    print("=" * 80)

    # Save raw evaluation results
    output_path = Path("data/eval/dimension7b_eval_results_raw.json")
    output_data = {
        "corpus_hash": computed_hash,
        "summary": {
            "total": total,
            "concordance": f"{matched}/{total}",
            "concordance_pct": matched / total * 100.0,
            "detection_rate_pct": detection_rate,
            "false_positive_rate_pct": fp_rate,
            "true_positives": true_positives,
            "false_negatives": false_negatives,
            "true_negatives": true_negatives,
            "false_positives": false_positives
        },
        "results": results
    }
    output_path.write_text(json.dumps(output_data, indent=2))
    print(f"\nRaw results written to {output_path}")


if __name__ == "__main__":
    evaluate_corpus()
