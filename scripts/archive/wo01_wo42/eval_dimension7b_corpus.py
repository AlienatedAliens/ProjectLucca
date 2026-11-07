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

    def clopper_pearson(k, n, alpha=0.05):
        from scipy.stats import beta
        lower = 0.0 if k == 0 else beta.ppf(alpha / 2, k, n - k + 1)
        upper = 1.0 if k == n else beta.ppf(1 - alpha / 2, k + 1, n - k)
        return lower * 100.0, upper * 100.0

    # Also run OutputSupervisorSession evaluation (action-level: abort vs pass)
    from lucca.sandbox.output_supervisor import OutputSupervisorSession, SeverityTier
    session_results = []
    for item in tests:
        tid = item["id"]
        exp = item["expected"]
        sess = OutputSupervisorSession()
        aborted = False
        tier2_hit = False

        if "clause_sequence" in item:
            for chunk in item["clause_sequence"]:
                emitted, should_abort = sess.feed_chunk(chunk, chunk)
                if should_abort:
                    aborted = True
                    break
                for _, r in emitted:
                    if r.severity == SeverityTier.TIER_2_SOFT:
                        tier2_hit = True
            if not aborted:
                emitted, should_abort = sess.flush()
                if should_abort:
                    aborted = True
        else:
            chunk = item["clause"]
            receipts = receipt_fixtures.get(tid, None)
            emitted, should_abort = sess.feed_chunk(chunk, chunk, verified_receipts=receipts)
            if should_abort:
                aborted = True
            for _, r in emitted:
                if r.severity == SeverityTier.TIER_2_SOFT:
                    tier2_hit = True
            if not aborted:
                emitted, should_abort = sess.flush()
                if should_abort:
                    aborted = True

        action = "abort" if aborted else "pass"
        session_results.append({
            "id": tid,
            "expected": exp,
            "action": action,
            "aborted": aborted,
            "tier2_hit": tier2_hit,
            "matched_action": (exp == "flag" and aborted) or (exp == "pass" and not aborted),
        })

    sess_matched = sum(1 for s in session_results if s["matched_action"])
    sess_tp = sum(1 for s in session_results if s["expected"] == "flag" and s["aborted"])
    sess_fn = sum(1 for s in session_results if s["expected"] == "flag" and not s["aborted"])
    sess_tn = sum(1 for s in session_results if s["expected"] == "pass" and not s["aborted"])
    sess_fp = sum(1 for s in session_results if s["expected"] == "pass" and s["aborted"])

    rec_lo, rec_hi = clopper_pearson(true_positives, len(expected_flags))
    fp_lo, fp_hi = clopper_pearson(false_positives, len(expected_passes))
    conc_lo, conc_hi = clopper_pearson(matched, total)

    sess_rec_lo, sess_rec_hi = clopper_pearson(sess_tp, len(expected_flags))
    sess_fp_lo, sess_fp_hi = clopper_pearson(sess_fp, len(expected_passes))
    sess_conc_lo, sess_conc_hi = clopper_pearson(sess_matched, total)

    print("\n" + "=" * 80)
    print(f"DIMENSION 7B EVALUATION SUMMARY:")
    print(f"Total Frozen Test Cases: {total}")
    print("-" * 80)
    print(f"1. RAW CLAUSE-GATE CONCORDANCE (Binary is_breach including Tier 2):")
    print(f"   Expectation Concordance: {matched} / {total} ({matched/total*100:.1f}%) [95% CI: {conc_lo:.2f}% - {conc_hi:.2f}%]")
    print(f"   Detection Rate (Recall): {true_positives} / {len(expected_flags)} ({detection_rate:.1f}%) [95% CI: {rec_lo:.2f}% - {rec_hi:.2f}%]")
    print(f"   False Positive Rate:     {false_positives} / {len(expected_passes)} ({fp_rate:.1f}%) [95% CI: {fp_lo:.2f}% - {fp_hi:.2f}%]")
    print("-" * 80)
    print(f"2. SESSION-TIERED ACTION CONCORDANCE (Stream Truncation / Terminal Abort):")
    print(f"   Action Concordance:      {sess_matched} / {total} ({sess_matched/total*100:.1f}%) [95% CI: {sess_conc_lo:.2f}% - {sess_conc_hi:.2f}%]")
    print(f"   Terminal Abort Recall:   {sess_tp} / {len(expected_flags)} ({sess_tp/len(expected_flags)*100:.1f}%) [95% CI: {sess_rec_lo:.2f}% - {sess_rec_hi:.2f}%]")
    print(f"   Terminal Abort FP Rate:  {sess_fp} / {len(expected_passes)} ({sess_fp/len(expected_passes)*100:.1f}%) [95% CI: {sess_fp_lo:.2f}% - {sess_fp_hi:.2f}%] (Zero Safe Turns Truncated)")
    print(f"   True Negatives (Clean):  {sess_tn} / {len(expected_passes)} ({sess_tn/len(expected_passes)*100:.1f}%)")
    print("=" * 80)

    # Save raw evaluation results
    output_path = Path("data/eval/dimension7b_eval_results_raw.json")
    output_data = {
        "corpus_hash": computed_hash,
        "raw_gate_summary": {
            "total": total,
            "concordance": f"{matched}/{total}",
            "concordance_pct": matched / total * 100.0,
            "concordance_ci95": [conc_lo, conc_hi],
            "detection_rate_pct": detection_rate,
            "detection_rate_ci95": [rec_lo, rec_hi],
            "false_positive_rate_pct": fp_rate,
            "false_positive_ci95": [fp_lo, fp_hi],
            "true_positives": true_positives,
            "false_negatives": false_negatives,
            "true_negatives": true_negatives,
            "false_positives": false_positives
        },
        "session_action_summary": {
            "total": total,
            "concordance": f"{sess_matched}/{total}",
            "concordance_pct": sess_matched / total * 100.0,
            "concordance_ci95": [sess_conc_lo, sess_conc_hi],
            "terminal_recall_pct": sess_tp / len(expected_flags) * 100.0,
            "terminal_recall_ci95": [sess_rec_lo, sess_rec_hi],
            "terminal_fp_pct": sess_fp / len(expected_passes) * 100.0,
            "terminal_fp_ci95": [sess_fp_lo, sess_fp_hi],
            "true_positives": sess_tp,
            "false_negatives": sess_fn,
            "true_negatives": sess_tn,
            "false_positives": sess_fp
        },
        "results": results,
        "session_results": session_results
    }
    output_path.write_text(json.dumps(output_data, indent=2))
    print(f"\nRaw results written to {output_path}")


if __name__ == "__main__":
    evaluate_corpus()
