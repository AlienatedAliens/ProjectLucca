#!/usr/bin/env python3
"""
Post-Remediation v2.3 Evaluation of ActionClaimGrammarSupervisor, OutputSupervisorSession,
coherence.py, and SOAC Frame Gate against Blinded Frontier-LLM Semantic Ground Truth:
  1. N=1,000 Held-Out Matcher Sensitivity Dataset (4 models: 26B-A4B, 12B, E4B, E2B)
     + N=750 3-Model Preregistered Core
  2. N=720 Paper 2 Study V1 & V2 Completions (Gemma 4 26B-A4B across 6 arms)

Preserves all frozen v2.2 baseline artifacts untouched and writes post-remediation
v2.3 reports to:
  - logs/test_reports/post_remediation_matcher_v2_3_1000.json
  - logs/test_reports/post_remediation_matcher_v2_3_summary.json
  - logs/test_reports/post_remediation_paper2_v2_3_720.json
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from eval_deontic_supervision import evaluate_soac_contract  # noqa: E402
from lucca.core.coherence import detect_ungrounded_action_claims  # noqa: E402
from lucca.reasoning.stats import wilson_score_interval  # noqa: E402
from lucca.sandbox.output_supervisor import (  # noqa: E402
    ActionClaimGrammarSupervisor,
    OutputSupervisorSession,
    TruthInReceiptMatcher,
)
from score_prereg_matcher_750 import (  # noqa: E402
    KEY_26B_PATH,
    KEY_750_PATH,
    LABEL_CLASSES,
    LEGACY_SCRIPT_LABELS_PATH,
    LLM_SEMANTIC_LABELS_1000_PATH,
    MODELS_3,
    MODELS_4,
    RATER2_150_PATH,
    RATER2_26B_50_PATH,
    score_subset,
    split_clauses,
)

HELD_DIR = REPO_ROOT / "data" / "benchmarks" / "supervision_heldout"
P2_LABELS_720_PATH = HELD_DIR / "blinded_paper2_v1_v2_semantic_labels_720.jsonl"

OUT_MATCHER_1000_PATH = REPO_ROOT / "logs" / "test_reports" / "post_remediation_matcher_v2_3_1000.json"
OUT_MATCHER_SUMMARY_PATH = REPO_ROOT / "logs" / "test_reports" / "post_remediation_matcher_v2_3_summary.json"
OUT_PAPER2_720_PATH = REPO_ROOT / "logs" / "test_reports" / "post_remediation_paper2_v2_3_720.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt_metric_2dec(k: int, n: int) -> dict[str, Any]:
    if n == 0:
        return {
            "flagged": 0,
            "total": 0,
            "rate_pct": 0.0,
            "wilson_95_ci_pct": [0.0, 0.0],
            "summary_with_ci": "0/0 (n/a)",
        }
    pct = round(100.0 * k / n, 2)
    lo, hi = wilson_score_interval(k, n)
    return {
        "flagged": k,
        "total": n,
        "rate_pct": pct,
        "wilson_95_ci_pct": [round(100.0 * lo, 2), round(100.0 * hi, 2)],
        "summary_with_ci": f"{k}/{n} ({pct:.2f}%) [{100.0*lo:.2f}%, {100.0*hi:.2f}%]",
    }


def evaluate_matcher_1000() -> dict[str, Any]:
    key_750_data = json.loads(KEY_750_PATH.read_text(encoding="utf-8"))
    key_26b_data = json.loads(KEY_26B_PATH.read_text(encoding="utf-8"))
    mapping: dict[str, dict[str, Any]] = {
        **key_750_data["mapping"],
        **key_26b_data["mapping"],
    }

    rows_1000 = [
        json.loads(line)
        for line in LLM_SEMANTIC_LABELS_1000_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows_1000) == 1000

    r2_150 = {
        r["worksheet_id"]: r
        for line in RATER2_150_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for r in [json.loads(line)]
    }
    r2_26b = {
        r["worksheet_id"]: r
        for line in RATER2_26B_50_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for r in [json.loads(line)]
    }
    rater2_all = {**r2_150, **r2_26b}
    legacy_map = {
        r["worksheet_id"]: r
        for line in LEGACY_SCRIPT_LABELS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for r in [json.loads(line)]
    }

    grammar_sup = ActionClaimGrammarSupervisor()
    legacy_sup = TruthInReceiptMatcher(enable_grammar_channel=False)

    grammar_lats_us: list[float] = []
    legacy_lats_us: list[float] = []
    evaluated_turns_1000: list[dict[str, Any]] = []

    for ws_row in rows_1000:
        ws_id = ws_row["worksheet_id"]
        meta = mapping[ws_id]
        completion = ws_row["model_completion"]
        clauses = split_clauses(completion)

        grammar_breaches: list[dict[str, Any]] = []
        for c in clauses:
            res = grammar_sup.evaluate_clause(c, verified_receipts=[], stale_before=None)
            grammar_lats_us.append(res.elapsed_us)
            if res.is_breach:
                grammar_breaches.append(
                    {
                        "clause": c,
                        "breach_type": res.breach_type,
                        "matched_text": res.matched_text,
                        "reason": res.reason,
                    }
                )
        col1_grammar_flag = len(grammar_breaches) > 0

        session: OutputSupervisorSession[int] = OutputSupervisorSession()
        session.reset_turn()
        col2_hard_abort = False
        for idx, c in enumerate(clauses):
            _, aborted = session.feed_chunk(idx, c, verified_receipts=[])
            if aborted:
                col2_hard_abort = True
                break
        if not col2_hard_abort:
            _, flush_aborted = session.flush()
            if flush_aborted:
                col2_hard_abort = True

        coh_claims = detect_ungrounded_action_claims(completion, receipts=[], verifier=None)
        ungrounded_coh = [c for c in coh_claims if not c.grounded]
        col3_coherence_flag = len(ungrounded_coh) > 0

        e2e_union_flag = bool(col1_grammar_flag or col2_hard_abort or col3_coherence_flag)

        legacy_breaches: list[dict[str, Any]] = []
        for c in clauses:
            l_res = legacy_sup.evaluate_clause(c, verified_receipts=[], stale_before=None)
            legacy_lats_us.append(l_res.elapsed_us)
            if l_res.is_breach:
                legacy_breaches.append(
                    {
                        "clause": c,
                        "matched_text": l_res.matched_text,
                        "reason": l_res.reason,
                    }
                )
        legacy_flag = len(legacy_breaches) > 0

        leg_row = legacy_map.get(ws_id)
        r2_row = rater2_all.get(ws_id)

        evaluated_turns_1000.append(
            {
                "worksheet_id": ws_id,
                "prompt_id": ws_row["prompt_id"],
                "model": meta["model"],
                "model_file": meta["model_file"],
                "raw_category": meta["raw_category"],
                "verb_stratum": meta["verb_stratum"],
                "verb": meta["verb"],
                "label": ws_row["label"],
                "label_reason": ws_row["label_reason"],
                "rater2_label": r2_row["label"] if r2_row else None,
                "rater2_reason": r2_row["rationale"] if r2_row else None,
                "legacy_script_label": leg_row["label"] if leg_row else None,
                "legacy_script_reason": leg_row["label_reason"] if leg_row else None,
                "prompt_text": ws_row["prompt_text"],
                "model_completion": completion,
                "col1_grammar_soft_flag": col1_grammar_flag,
                "col1_breaches": grammar_breaches,
                "col2_hard_abort": col2_hard_abort,
                "col3_coherence_flag": col3_coherence_flag,
                "col3_claims": [c.model_dump() for c in ungrounded_coh],
                "e2e_union_flag": e2e_union_flag,
                "legacy_flag": legacy_flag,
            }
        )

    model_order = {"gemma-4-26b-a4b": 0, "gemma-4-12b": 1, "gemma-4-e4b": 2, "gemma-4-e2b": 3}
    evaluated_turns_1000.sort(key=lambda r: (model_order.get(r["model"], 99), r["prompt_id"]))
    evaluated_turns_750 = [r for r in evaluated_turns_1000 if r["model"] in MODELS_3]

    channels = [
        ("col1_grammar_soft_flag", "Column 1: ActionClaimGrammarSupervisor v2.3"),
        ("col2_hard_abort", "Column 2: OutputSupervisorSession In-Stream Hard Abort"),
        ("col3_coherence_flag", "Column 3: Post-Turn coherence.py v2.3 Audit"),
        ("e2e_union_flag", "End-to-End Union (Col 1 OR Col 2 OR Col 3)"),
        ("legacy_flag", "Baseline Legacy TruthInReceiptMatcher"),
    ]

    per_model_results: dict[str, dict[str, Any]] = {}
    for m_tag in MODELS_4:
        m_rows = [r for r in evaluated_turns_1000 if r["model"] == m_tag]
        fac_inv = [r for r in m_rows if r["label"] in ("FAC_STRICT", "FAC_BROAD") and r["verb_stratum"] == "in_vocab"]
        fac_ood = [r for r in m_rows if r["label"] in ("FAC_STRICT", "FAC_BROAD") and r["verb_stratum"] == "out_of_dev"]
        per_model_results[m_tag] = {
            "n_turns": len(m_rows),
            "label_counts": {lbl: sum(1 for r in m_rows if r["label"] == lbl) for lbl in LABEL_CLASSES},
            "fac_by_stratum": {
                "in_vocab_total": len(fac_inv),
                "in_vocab_strict": sum(1 for r in fac_inv if r["label"] == "FAC_STRICT"),
                "in_vocab_broad": sum(1 for r in fac_inv if r["label"] == "FAC_BROAD"),
                "out_of_dev_total": len(fac_ood),
                "out_of_dev_strict": sum(1 for r in fac_ood if r["label"] == "FAC_STRICT"),
                "out_of_dev_broad": sum(1 for r in fac_ood if r["label"] == "FAC_BROAD"),
            },
            "channels": {
                ch_key: score_subset(m_rows, ch_key, label_field="label", include_ci=True)
                for ch_key, _ in channels
            },
        }

    def build_pooled(turns_sub: list[dict[str, Any]], desc: str) -> dict[str, Any]:
        return {
            "n_turns": len(turns_sub),
            "models_included": desc,
            "label_counts": {lbl: sum(1 for r in turns_sub if r["label"] == lbl) for lbl in LABEL_CLASSES},
            "channels": {
                ch_key: score_subset(turns_sub, ch_key, label_field="label", include_ci=False)
                for ch_key, _ in channels
            },
        }

    pooled_1000 = build_pooled(evaluated_turns_1000, "26B-A4B, 12B, E4B, E2B (N=1,000)")
    pooled_750 = build_pooled(evaluated_turns_750, "E4B, E2B, 12B (N=750)")

    missed_fac = [
        r for r in evaluated_turns_1000
        if r["label"] in ("FAC_STRICT", "FAC_BROAD") and not r["col1_grammar_soft_flag"]
    ]
    false_positives_col1 = [
        {
            "worksheet_id": r["worksheet_id"],
            "prompt_id": r["prompt_id"],
            "model": r["model"],
            "raw_category": r["raw_category"],
            "verb_stratum": r["verb_stratum"],
            "verb": r["verb"],
            "label": r["label"],
            "label_reason": r["label_reason"],
            "matched_clause": r["col1_breaches"][0]["clause"] if r["col1_breaches"] else "",
            "reason": r["col1_breaches"][0]["reason"] if r["col1_breaches"] else "",
            "completion_excerpt": r["model_completion"][:220],
        }
        for r in evaluated_turns_1000
        if r["label"] in ("CLEAN", "INTENT") and r["col1_grammar_soft_flag"]
    ]

    def latency_summary(lats: list[float]) -> dict[str, Any]:
        s = sorted(lats)
        p95 = s[int(0.95 * (len(s) - 1))] if s else 0.0
        return {
            "clauses_evaluated": len(s),
            "mean_us": round(statistics.fmean(s), 2) if s else 0.0,
            "p95_us": round(p95, 2),
            "max_us": round(max(s), 2) if s else 0.0,
            "budget_1000_us_pass": (p95 <= 1000.0),
        }

    summary_base = {
        "protocol_id": "POST-REMEDIATION-MATCHER-SENSITIVITY-v2.3",
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": (
            "Post-audit v2.3 evaluation against the frozen blinded frontier-LLM semantic labels "
            "(blinded_llm_semantic_labels_1000.jsonl). Pre-registered v2.2 baseline artifacts "
            "remain frozen at prereg_matcher_sensitivity_v2_2_*.json."
        ),
        "remediated_code_sha256": {
            "output_supervisor_py_sha256": sha256_file(REPO_ROOT / "src" / "lucca" / "sandbox" / "output_supervisor.py"),
            "coherence_py_sha256": sha256_file(REPO_ROOT / "src" / "lucca" / "core" / "coherence.py"),
            "action_claim_gbnf_sha256": sha256_file(REPO_ROOT / "config" / "grammars" / "action_claim.gbnf"),
            "blinded_llm_semantic_labels_1000_sha256": sha256_file(LLM_SEMANTIC_LABELS_1000_PATH),
        },
        "latency_profile_cpu": {
            "ActionClaimGrammarSupervisor_v2_3": latency_summary(grammar_lats_us),
            "TruthInReceiptMatcher_legacy": latency_summary(legacy_lats_us),
        },
        "per_model_primary_units": per_model_results,
        "pooled_1000_summary": pooled_1000,
        "pooled_750_summary": pooled_750,
        "escape_taxonomy_col1": {
            "total_missed_fac": len(missed_fac),
            "missed_in_vocab_count": sum(1 for r in missed_fac if r["verb_stratum"] == "in_vocab"),
            "missed_out_of_dev_count": sum(1 for r in missed_fac if r["verb_stratum"] == "out_of_dev"),
            "missed_items": [
                {
                    "worksheet_id": r["worksheet_id"],
                    "prompt_id": r["prompt_id"],
                    "model": r["model"],
                    "verb_stratum": r["verb_stratum"],
                    "verb": r["verb"],
                    "label": r["label"],
                    "label_reason": r["label_reason"],
                    "completion_excerpt": r["model_completion"][:220],
                }
                for r in missed_fac
            ],
        },
        "false_positives_col1": {
            "total_non_claim_fp": len(false_positives_col1),
            "items": false_positives_col1,
        },
    }

    OUT_MATCHER_1000_PATH.write_text(
        json.dumps({**summary_base, "turns": evaluated_turns_1000}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    OUT_MATCHER_SUMMARY_PATH.write_text(
        json.dumps(summary_base, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary_base


def evaluate_paper2_720() -> dict[str, Any]:
    rows_720 = [
        json.loads(line)
        for line in P2_LABELS_720_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows_720) == 720

    grammar_sup = ActionClaimGrammarSupervisor()
    re_evaluated: list[dict[str, Any]] = []

    for r in rows_720:
        prose = r["prose_completion"]
        raw_comp = r["raw_completion"]
        clauses_prose = split_clauses(prose)
        clauses_raw = split_clauses(raw_comp)

        v23_grammar_prose_flag = any(
            grammar_sup.evaluate_clause(c, verified_receipts=[], stale_before=None).is_breach
            for c in clauses_prose
        )
        v23_grammar_raw_flag = any(
            grammar_sup.evaluate_clause(c, verified_receipts=[], stale_before=None).is_breach
            for c in clauses_raw
        )
        v23_coh_prose_flag = any(
            not c.grounded
            for c in detect_ungrounded_action_claims(prose, receipts=[], verifier=None)
        )
        v23_soac_frame_flag, _, _ = evaluate_soac_contract(raw_comp, receipts=[])

        re_evaluated.append(
            {
                **r,
                "v23_grammar_prose_flagged": v23_grammar_prose_flag,
                "v23_grammar_raw_flagged": v23_grammar_raw_flag,
                "v23_coherence_prose_flagged": v23_coh_prose_flag,
                "v23_soac_frame_flagged": v23_soac_frame_flag,
                "v23_e2e_union_flagged": bool(
                    v23_grammar_raw_flag or v23_coh_prose_flag or v23_soac_frame_flag
                ),
            }
        )

    arms_summary: dict[str, Any] = {}
    for arm_key in [
        "v1_natural",
        "v1_soac",
        "v2_natural",
        "v2_soac",
        "v2_soac_gbnf",
        "v2_natural_gbnf",
    ]:
        sub = [r for r in re_evaluated if r["arm"] == arm_key]
        tempt = [r for r in sub if r["cohort"] in ("action_temptation", "temptation")]
        ctrl = [r for r in sub if r["cohort"] == "honest_control"]
        idiom = [
            r for r in sub
            if r["cohort"] in ("idiom_metaphor", "figurative_idiom", "idiom_control", "idiom")
        ]
        non_tempt = ctrl + idiom

        fac_all = [r for r in sub if r["label"] in ("FAC_STRICT", "FAC_BROAD")]
        fac_strict = [r for r in sub if r["label"] == "FAC_STRICT"]
        non_claims = [r for r in sub if r["label"] in ("CLEAN", "INTENT")]

        arms_summary[arm_key] = {
            "n_turns": len(sub),
            "semantic_label_counts": {
                lbl: sum(1 for r in sub if r["label"] == lbl) for lbl in LABEL_CLASSES
            },
            "soac_frame_gate_v2_2_vs_v2_3": {
                "v2_2_temptation_frames": fmt_metric_2dec(
                    sum(1 for r in tempt if r["has_soac_frame"]), len(tempt)
                ),
                "v2_3_temptation_frames": fmt_metric_2dec(
                    sum(1 for r in tempt if r["v23_soac_frame_flagged"]), len(tempt)
                ),
                "v2_2_honest_control_spurious_frames": fmt_metric_2dec(
                    sum(1 for r in ctrl if r["has_soac_frame"]), len(ctrl)
                ),
                "v2_3_honest_control_spurious_frames": fmt_metric_2dec(
                    sum(1 for r in ctrl if r["v23_soac_frame_flagged"]), len(ctrl)
                ),
                "v2_2_idiom_spurious_frames": fmt_metric_2dec(
                    sum(1 for r in idiom if r["has_soac_frame"]), len(idiom)
                ),
                "v2_3_idiom_spurious_frames": fmt_metric_2dec(
                    sum(1 for r in idiom if r["v23_soac_frame_flagged"]), len(idiom)
                ),
            },
            "grammar_supervisor_col1_v2_2_vs_v2_3": {
                "v2_2_broad_recall": fmt_metric_2dec(
                    sum(1 for r in fac_all if r["post_hardening_grammar_flagged"]), len(fac_all)
                ),
                "v2_3_broad_recall": fmt_metric_2dec(
                    sum(1 for r in fac_all if r["v23_grammar_prose_flagged"]), len(fac_all)
                ),
                "v2_2_strict_recall": fmt_metric_2dec(
                    sum(1 for r in fac_strict if r["post_hardening_grammar_flagged"]), len(fac_strict)
                ),
                "v2_3_strict_recall": fmt_metric_2dec(
                    sum(1 for r in fac_strict if r["v23_grammar_prose_flagged"]), len(fac_strict)
                ),
                "v2_2_non_claim_fpr": fmt_metric_2dec(
                    sum(1 for r in non_claims if r["post_hardening_grammar_flagged"]), len(non_claims)
                ),
                "v2_3_non_claim_fpr": fmt_metric_2dec(
                    sum(1 for r in non_claims if r["v23_grammar_prose_flagged"]), len(non_claims)
                ),
                "v2_3_controls_idioms_fpr": fmt_metric_2dec(
                    sum(1 for r in non_tempt if r["v23_grammar_prose_flagged"]), len(non_tempt)
                ),
            },
            "e2e_union_v2_3": {
                "broad_recall_on_prose_fac": fmt_metric_2dec(
                    sum(1 for r in fac_all if r["v23_e2e_union_flagged"]), len(fac_all)
                ),
                "non_claim_prose_fpr": fmt_metric_2dec(
                    sum(1 for r in non_claims if r["v23_grammar_prose_flagged"] or r["v23_coherence_prose_flagged"]),
                    len(non_claims),
                ),
                "controls_idioms_total_fpr_including_soac_frames": fmt_metric_2dec(
                    sum(1 for r in non_tempt if r["v23_e2e_union_flagged"]), len(non_tempt)
                ),
            },
        }

    # Pooled across all 720 turns
    all_fac = [r for r in re_evaluated if r["label"] in ("FAC_STRICT", "FAC_BROAD")]
    all_strict = [r for r in re_evaluated if r["label"] == "FAC_STRICT"]
    all_non_claims = [r for r in re_evaluated if r["label"] in ("CLEAN", "INTENT")]
    all_non_tempt = [
        r for r in re_evaluated
        if r["cohort"] in ("honest_control", "idiom_metaphor", "figurative_idiom", "idiom_control", "idiom")
    ]

    pooled_720 = {
        "n_turns": len(re_evaluated),
        "total_fac": len(all_fac),
        "total_strict_fac": len(all_strict),
        "total_non_claims": len(all_non_claims),
        "v2_2_grammar_broad_recall": fmt_metric_2dec(
            sum(1 for r in all_fac if r["post_hardening_grammar_flagged"]), len(all_fac)
        ),
        "v2_3_grammar_broad_recall": fmt_metric_2dec(
            sum(1 for r in all_fac if r["v23_grammar_prose_flagged"]), len(all_fac)
        ),
        "v2_2_grammar_strict_recall": fmt_metric_2dec(
            sum(1 for r in all_strict if r["post_hardening_grammar_flagged"]), len(all_strict)
        ),
        "v2_3_grammar_strict_recall": fmt_metric_2dec(
            sum(1 for r in all_strict if r["v23_grammar_prose_flagged"]), len(all_strict)
        ),
        "v2_2_grammar_non_claim_fpr": fmt_metric_2dec(
            sum(1 for r in all_non_claims if r["post_hardening_grammar_flagged"]), len(all_non_claims)
        ),
        "v2_3_grammar_non_claim_fpr": fmt_metric_2dec(
            sum(1 for r in all_non_claims if r["v23_grammar_prose_flagged"]), len(all_non_claims)
        ),
        "v2_2_non_temptation_spurious_soac_frames": fmt_metric_2dec(
            sum(1 for r in all_non_tempt if r["has_soac_frame"]), len(all_non_tempt)
        ),
        "v2_3_non_temptation_spurious_soac_frames": fmt_metric_2dec(
            sum(1 for r in all_non_tempt if r["v23_soac_frame_flagged"]), len(all_non_tempt)
        ),
    }

    p2_report = {
        "audit_id": "POST-REMEDIATION-PAPER2-V2-3-720",
        "timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_evaluated": "gemma-4-26B-A4B-it-heretic.Q6_K.gguf",
        "pooled_720_summary": pooled_720,
        "arms_summary": arms_summary,
    }
    OUT_PAPER2_720_PATH.write_text(
        json.dumps(p2_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return p2_report


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    m_res = evaluate_matcher_1000()
    p2_res = evaluate_paper2_720()

    print("=" * 100)
    print("POST-REMEDIATION v2.3 — 1,000-TURN 4-MODEL MATCHER EVALUATION")
    print("=" * 100)
    for m_tag in MODELS_4:
        mr = m_res["per_model_primary_units"][m_tag]
        c1 = mr["channels"]["col1_grammar_soft_flag"]
        c3 = mr["channels"]["col3_coherence_flag"]
        cu = mr["channels"]["e2e_union_flag"]
        print(
            f"\n[{m_tag}] N={mr['n_turns']} | Labels={mr['label_counts']} | "
            f"All 3 Primary Thresholds Pass={c1['thresholds_check']['all_three_primary_passed']}"
        )
        print(
            f"  Col 1 Grammar v2.3: Broad={c1['primary_broad_sensitivity']['summary_with_ci']} | "
            f"Strict={c1['primary_strict_sensitivity']['summary_with_ci']} | "
            f"Non-Claim FPR={c1['primary_non_claim_fpr']['summary_with_ci']} | "
            f"Controls FPR={c1['secondary_controls_fpr']['summary_with_ci']}"
        )
        print(
            f"    -> In-Vocab Broad={c1['secondary_in_vocab_broad_sensitivity']['summary_with_ci']} | "
            f"Out-of-Dev Broad={c1['secondary_out_of_dev_broad_sensitivity']['summary_with_ci']} | "
            f"Progressive={c1['secondary_progressive_only_sensitivity']['summary_with_ci']}"
        )
        print(
            f"  Col 3 Coherence v2.3: Broad={c3['primary_broad_sensitivity']['summary_with_ci']} | "
            f"Non-Claim FPR={c3['primary_non_claim_fpr']['summary_with_ci']}"
        )
        print(
            f"  End-to-End Union v2.3: Broad={cu['primary_broad_sensitivity']['summary_with_ci']} | "
            f"Non-Claim FPR={cu['primary_non_claim_fpr']['summary_with_ci']}"
        )

    for title, pr in [
        ("POOLED 4-MODEL (N=1,000)", m_res["pooled_1000_summary"]),
        ("POOLED 3-MODEL PREREG CORE (N=750)", m_res["pooled_750_summary"]),
    ]:
        c1 = pr["channels"]["col1_grammar_soft_flag"]
        c3 = pr["channels"]["col3_coherence_flag"]
        cu = pr["channels"]["e2e_union_flag"]
        print(f"\n--- {title} ---")
        print(
            f"  Col 1 Grammar v2.3: Broad={c1['primary_broad_sensitivity']['summary_str']} | "
            f"Strict={c1['primary_strict_sensitivity']['summary_str']} | "
            f"Progressive={c1['secondary_progressive_only_sensitivity']['summary_str']} | "
            f"In-Vocab={c1['secondary_in_vocab_broad_sensitivity']['summary_str']} | "
            f"Out-of-Dev={c1['secondary_out_of_dev_broad_sensitivity']['summary_str']} | "
            f"Non-Claim FPR={c1['primary_non_claim_fpr']['summary_str']} | "
            f"Controls FPR={c1['secondary_controls_fpr']['summary_str']}"
        )
        print(
            f"  Col 3 Coherence v2.3: Broad={c3['primary_broad_sensitivity']['summary_str']} | "
            f"Strict={c3['primary_strict_sensitivity']['summary_str']} | "
            f"Non-Claim FPR={c3['primary_non_claim_fpr']['summary_str']}"
        )
        print(
            f"  End-to-End Union v2.3: Broad={cu['primary_broad_sensitivity']['summary_str']} | "
            f"Strict={cu['primary_strict_sensitivity']['summary_str']} | "
            f"Non-Claim FPR={cu['primary_non_claim_fpr']['summary_str']}"
        )

    print(f"\nRemaining Missed FACs (N=1,000): {m_res['escape_taxonomy_col1']['total_missed_fac']}")
    print(f"Remaining Non-Claim FPs (N=1,000): {m_res['false_positives_col1']['total_non_claim_fp']}")

    print("\n" + "=" * 100)
    print("POST-REMEDIATION v2.3 — PAPER 2 STUDY V1 & V2 (720 COMPLETIONS, GEMMA 4 26B-A4B)")
    print("=" * 100)
    p720 = p2_res["pooled_720_summary"]
    print(
        f"Pooled 720 Turns: Grammar Broad Recall: v2.2={p720['v2_2_grammar_broad_recall']['summary_with_ci']} -> "
        f"v2.3={p720['v2_3_grammar_broad_recall']['summary_with_ci']}"
    )
    print(
        f"Pooled 720 Turns: Grammar Strict Recall: v2.2={p720['v2_2_grammar_strict_recall']['summary_with_ci']} -> "
        f"v2.3={p720['v2_3_grammar_strict_recall']['summary_with_ci']}"
    )
    print(
        f"Pooled 720 Turns: Grammar Non-Claim FPR: v2.2={p720['v2_2_grammar_non_claim_fpr']['summary_with_ci']} -> "
        f"v2.3={p720['v2_3_grammar_non_claim_fpr']['summary_with_ci']}"
    )
    print(
        f"Pooled 420 Non-Temptation Turns: Spurious SOAC Frames: "
        f"v2.2={p720['v2_2_non_temptation_spurious_soac_frames']['summary_with_ci']} -> "
        f"v2.3={p720['v2_3_non_temptation_spurious_soac_frames']['summary_with_ci']}"
    )
    for arm_k, arm_v in p2_res["arms_summary"].items():
        g = arm_v["grammar_supervisor_col1_v2_2_vs_v2_3"]
        s = arm_v["soac_frame_gate_v2_2_vs_v2_3"]
        print(
            f"  [{arm_k}] Grammar Recall: v2.2={g['v2_2_broad_recall']['summary_with_ci']} -> "
            f"v2.3={g['v2_3_broad_recall']['summary_with_ci']} | "
            f"Non-Claim FPR: v2.2={g['v2_2_non_claim_fpr']['summary_with_ci']} -> "
            f"v2.3={g['v2_3_non_claim_fpr']['summary_with_ci']} | "
            f"Idiom Spurious Frames: v2.2={s['v2_2_idiom_spurious_frames']['summary_with_ci']} -> "
            f"v2.3={s['v2_3_idiom_spurious_frames']['summary_with_ci']} | "
            f"Ctrl Spurious Frames: v2.2={s['v2_2_honest_control_spurious_frames']['summary_with_ci']} -> "
            f"v2.3={s['v2_3_honest_control_spurious_frames']['summary_with_ci']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
