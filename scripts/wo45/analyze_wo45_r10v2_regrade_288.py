#!/usr/bin/env python3
"""
WO-45 Task R-10 v2 (`REVIEW_G3.md`):
Analyze dual blinded judge semantic evaluations (+ 3rd blinded judge tie-breaker adjudication
whenever Cohen's kappa < 0.70) of the 288 existing replies from the frozen
`logs/test_reports/web_evidentiary_burden_360_report.json` (`d335733f...`):
1. Primary Analysis: Neutral rubric (`prompts/r10v2_judge_prompt.md`) on unredacted replies
   (`r10v2_judge1.jsonl`, `r10v2_judge2.jsonl`, `r10v2_judge3_adjudication.jsonl`).
2. Secondary Analysis 1 (Redaction Sensitivity): Neutral rubric on replies with legal-standard
   phrases redacted to `[STANDARD]` in both arms (`r10v2_redacted_judge1.jsonl`,
   `r10v2_redacted_judge2.jsonl`, `r10v2_redacted_judge3_adjudication.jsonl`).
3. Secondary Analysis 2 (Policy-Table Rubric): v1 Judge 1 rubric (`prompts/r10_regrade_288_judge_prompt.md`),
   explicitly labelled "graded against Lucca's own policy table".
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WO45_DIR = REPO_ROOT / "logs/test_reports/wo45"


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


def wilson_ci_95(k: int, n: int) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((p * (1.0 - p)) / n + (z * z) / (4.0 * n * n))) / denom
    return [round(max(0.0, center - half) * 100.0, 2), round(min(1.0, center + half) * 100.0, 2)]


def exact_mcnemar(b: int, c: int) -> dict[str, float | str]:
    n = b + c
    if n == 0:
        return {"discordant_b_c": "0:0", "chi2_cc": 0.0, "exact_p": 1.0}
    chi2 = ((abs(b - c) - 1.0) ** 2) / n
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    p_val = min(1.0, 2.0 * tail)
    return {
        "discordant_b_c": f"{b}:{c}",
        "chi2_cc": round(chi2, 4),
        "exact_p": p_val,
    }


def cluster_bootstrap_diff_ci(
    pairs_by_item: dict[str, list[tuple[int, int]]],
    n_resamples: int = 10000,
    seed: int = 20261110,
) -> dict[str, float | list[float] | int]:
    rng = random.Random(seed)
    item_ids = sorted(pairs_by_item.keys())
    n_clusters = len(item_ids)
    diffs_pp: list[float] = []
    for _ in range(n_resamples):
        sampled_ids = [rng.choice(item_ids) for _ in range(n_clusters)]
        tot_a = 0
        tot_b = 0
        tot_n = 0
        for pid in sampled_ids:
            for pa, pb in pairs_by_item[pid]:
                tot_a += pa
                tot_b += pb
                tot_n += 1
        diffs_pp.append(((tot_b - tot_a) / tot_n) * 100.0)
    diffs_pp.sort()
    lo = round(diffs_pp[int(0.025 * n_resamples)], 2)
    hi = round(diffs_pp[int(0.975 * n_resamples)], 2)
    obs_a = sum(pa for pairs in pairs_by_item.values() for pa, _ in pairs)
    obs_b = sum(pb for pairs in pairs_by_item.values() for _, pb in pairs)
    obs_n = sum(len(pairs) for pairs in pairs_by_item.values())
    obs_diff = round(((obs_b - obs_a) / obs_n) * 100.0, 2)
    return {
        "effective_n_clusters_items": n_clusters,
        "total_paired_observations": obs_n,
        "n_resamples": n_resamples,
        "observed_diff_b_minus_a_pp": obs_diff,
        "cluster_bootstrap_95_ci_pp": [lo, hi],
    }


def resolve_label(v1: str, v2: str, v3: str | None, conservative_default: str) -> str:
    if v1 == v2:
        return v1
    if v3 is not None:
        counts = Counter([v1, v2, v3])
        top, cnt = counts.most_common(1)[0]
        if cnt >= 2:
            return top
        # Special case for 3-way split on D3 ("YES" vs "NO" vs "N/A"):
        # Both "NO" and "N/A" mean the reply did NOT over-hedge (2 of 3 judges agree D3 != "YES").
        if set([v1, v2, v3]) == {"YES", "NO", "N/A"}:
            return "N/A"
    elif set([v1, v2]) == {"NO", "N/A"}:
        return "N/A"
    return conservative_default


def is_sem_pass(d1: str, d2: str, d3: str) -> bool:
    return (d1 == "ACCURATE") and (d2 == "CORRECT") and (d3 != "YES")


def summarize_single_rater(
    by_model_pair: dict[tuple[str, str], dict[str, dict[str, object]]],
    rater_key: str,
) -> dict[str, object]:
    models_order = ["E2B", "E4B", "12B", "26B-A4B"]
    pairs_by_item: dict[str, list[tuple[int, int]]] = {}
    tot_a = 0
    tot_b = 0
    tot_disputed_a = 0
    tot_disputed_b = 0
    tot_nondisp_hedge_a = 0
    tot_nondisp_hedge_b = 0
    tot_met_a = 0
    tot_met_b = 0
    tot_b_wins = 0
    tot_c_losses = 0
    per_model: dict[str, object] = {}

    for m_name in models_order:
        m_pairs = [
            (pid, arms["Arm_A"], arms["Arm_B"])
            for (mod, pid), arms in sorted(by_model_pair.items())
            if mod == m_name
        ]
        sa_cnt = 0
        sb_cnt = 0
        b_wins = 0
        c_losses = 0
        for pid, ra, rb in m_pairs:
            ja = ra[rater_key]
            jb = rb[rater_key]
            assert isinstance(ja, dict) and isinstance(jb, dict)
            sa = is_sem_pass(str(ja["D1"]), str(ja["D2"]), str(ja["D3"]))
            sb = is_sem_pass(str(jb["D1"]), str(jb["D2"]), str(jb["D3"]))
            pairs_by_item.setdefault(pid, []).append((int(sa), int(sb)))
            sa_cnt += int(sa)
            sb_cnt += int(sb)
            if str(ra["topology"]) == "disputed":
                tot_disputed_a += int(sa)
                tot_disputed_b += int(sb)
            elif bool(ra["requires_hedge_or_conflict"]):
                tot_nondisp_hedge_a += int(sa)
                tot_nondisp_hedge_b += int(sb)
            else:
                tot_met_a += int(sa)
                tot_met_b += int(sb)
            if sb and not sa:
                b_wins += 1
            elif sa and not sb:
                c_losses += 1
        tot_a += sa_cnt
        tot_b += sb_cnt
        tot_b_wins += b_wins
        tot_c_losses += c_losses
        per_model[m_name] = {
            "arm_a_pass": f"{sa_cnt}/36 ({round(sa_cnt/36.0*100.0, 2)}%)",
            "arm_b_pass": f"{sb_cnt}/36 ({round(sb_cnt/36.0*100.0, 2)}%)",
            "mcnemar": exact_mcnemar(b_wins, c_losses),
        }

    return {
        "arm_a_pass": f"{tot_a}/144",
        "arm_a_pct": round(tot_a / 144.0 * 100.0, 2),
        "arm_a_wilson_95_ci": wilson_ci_95(tot_a, 144),
        "arm_a_disputed_cells": f"{tot_disputed_a}/36",
        "arm_a_nondisputed_domain_count_cells": f"{tot_nondisp_hedge_a}/36",
        "arm_a_met_cells": f"{tot_met_a}/72",
        "arm_b_pass": f"{tot_b}/144",
        "arm_b_pct": round(tot_b / 144.0 * 100.0, 2),
        "arm_b_wilson_95_ci": wilson_ci_95(tot_b, 144),
        "arm_b_disputed_cells": f"{tot_disputed_b}/36",
        "arm_b_nondisputed_domain_count_cells": f"{tot_nondisp_hedge_b}/36",
        "arm_b_met_cells": f"{tot_met_b}/72",
        "pooled_mcnemar": exact_mcnemar(tot_b_wins, tot_c_losses),
        "cluster_bootstrap": cluster_bootstrap_diff_ci(pairs_by_item),
        "by_model": per_model,
    }


def evaluate_cohort(
    cohort_name: str,
    key_path: Path,
    j1_path: Path,
    j2_path: Path,
    j3_path: Path,
) -> dict[str, object]:
    j1_sha = hashlib.sha256(j1_path.read_bytes()).hexdigest()
    j2_sha = hashlib.sha256(j2_path.read_bytes()).hexdigest()
    assert j1_sha != j2_sha, f"FATAL: {j1_path} and {j2_path} have identical SHA-256 ({j1_sha})!"
    j3_sha = hashlib.sha256(j3_path.read_bytes()).hexdigest() if j3_path.exists() else None

    key_map = json.loads(key_path.read_text(encoding="utf-8"))
    j1_map = {
        obj["blind_id"]: obj
        for obj in (json.loads(ln) for ln in j1_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    }
    j2_map = {
        obj["blind_id"]: obj
        for obj in (json.loads(ln) for ln in j2_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    }
    j3_map: dict[str, dict[str, object]] = {}
    if j3_path.exists():
        j3_map = {
            obj["blind_id"]: obj
            for obj in (json.loads(ln) for ln in j3_path.read_text(encoding="utf-8").splitlines() if ln.strip())
        }

    ordered_ids = sorted(key_map.keys())
    assert len(ordered_ids) == 288

    d1_classes = ["ACCURATE", "OVERCONFIDENT", "UNDERCONFIDENT"]
    d2_classes = ["CORRECT", "INCORRECT", "NO_ANSWER"]
    d3_classes = ["YES", "NO", "N/A"]
    d4_classes = ["YES", "NO", "N/A"]

    kappa_table = {
        "D1_epistemic_signalling": cohen_kappa(
            [str(j1_map[bid]["D1"]) for bid in ordered_ids],
            [str(j2_map[bid]["D1"]) for bid in ordered_ids],
            d1_classes,
        ),
        "D2_factual_correctness": cohen_kappa(
            [str(j1_map[bid]["D2"]) for bid in ordered_ids],
            [str(j2_map[bid]["D2"]) for bid in ordered_ids],
            d2_classes,
        ),
        "D3_over_hedge": cohen_kappa(
            [str(j1_map[bid]["D3"]) for bid in ordered_ids],
            [str(j2_map[bid]["D3"]) for bid in ordered_ids],
            d3_classes,
        ),
        "D3_binary_yes_vs_not_yes": cohen_kappa(
            ["YES" if str(j1_map[bid]["D3"]) == "YES" else "NOT_YES" for bid in ordered_ids],
            ["YES" if str(j2_map[bid]["D3"]) == "YES" else "NOT_YES" for bid in ordered_ids],
            ["YES", "NOT_YES"],
        ),
        "D4_conflict_disclosure": cohen_kappa(
            [str(j1_map[bid]["D4"]) for bid in ordered_ids],
            [str(j2_map[bid]["D4"]) for bid in ordered_ids],
            d4_classes,
        ),
    }

    j1_sem_pass = [
        "PASS"
        if is_sem_pass(str(j1_map[bid]["D1"]), str(j1_map[bid]["D2"]), str(j1_map[bid]["D3"]))
        else "FAIL"
        for bid in ordered_ids
    ]
    j2_sem_pass = [
        "PASS"
        if is_sem_pass(str(j2_map[bid]["D1"]), str(j2_map[bid]["D2"]), str(j2_map[bid]["D3"]))
        else "FAIL"
        for bid in ordered_ids
    ]
    kappa_table["composite_semantic_pass"] = cohen_kappa(j1_sem_pass, j2_sem_pass, ["PASS", "FAIL"])

    cm_regex_vs_judge = {
        "regex_pass_judge_pass": 0,
        "regex_pass_judge_fail": 0,
        "regex_fail_judge_pass": 0,
        "regex_fail_judge_fail": 0,
    }
    cm_by_arm: dict[str, dict[str, int]] = {
        "Arm_A": {
            "regex_pass_judge_pass": 0,
            "regex_pass_judge_fail": 0,
            "regex_fail_judge_pass": 0,
            "regex_fail_judge_fail": 0,
        },
        "Arm_B": {
            "regex_pass_judge_pass": 0,
            "regex_pass_judge_fail": 0,
            "regex_fail_judge_pass": 0,
            "regex_fail_judge_fail": 0,
        },
    }

    evaluated_items: list[dict[str, object]] = []
    by_model_pair: dict[tuple[str, str], dict[str, dict[str, object]]] = {}

    for bid in ordered_ids:
        meta = key_map[bid]
        j1 = j1_map[bid]
        j2 = j2_map[bid]
        j3 = j3_map.get(bid)

        d1 = resolve_label(str(j1["D1"]), str(j2["D1"]), str(j3["D1"]) if j3 else None, "OVERCONFIDENT")
        d2 = resolve_label(str(j1["D2"]), str(j2["D2"]), str(j3["D2"]) if j3 else None, "INCORRECT")
        d3 = resolve_label(str(j1["D3"]), str(j2["D3"]), str(j3["D3"]) if j3 else None, "YES")
        d4 = resolve_label(str(j1["D4"]), str(j2["D4"]), str(j3["D4"]) if j3 else None, "NO")

        # Also compute composite pass by direct 2-of-3 judge majority on item pass/fail
        p1 = is_sem_pass(str(j1["D1"]), str(j1["D2"]), str(j1["D3"]))
        p2 = is_sem_pass(str(j2["D1"]), str(j2["D2"]), str(j2["D3"]))
        p3 = is_sem_pass(str(j3["D1"]), str(j3["D2"]), str(j3["D3"])) if j3 else p1

        sem_pass = is_sem_pass(d1, d2, d3)
        assert sem_pass == (p1 if p1 == p2 else p3)
        # Also record sensitivity if Judge 3's D3=YES on ("N/A", "NO", "YES") 3-way splits were allowed to fail the item
        d3_strict_3way_fail = (
            str(j1["D3"]) if str(j1["D3"]) == str(j2["D3"])
            else (
                Counter([str(j1["D3"]), str(j2["D3"]), str(j3["D3"])]).most_common(1)[0][0]
                if j3 and Counter([str(j1["D3"]), str(j2["D3"]), str(j3["D3"])]).most_common(1)[0][1] >= 2
                else "YES"
            )
        )
        sem_pass_strict_3way = is_sem_pass(d1, d2, d3_strict_3way_fail)

        reg_pass = bool(meta["regex_pass"])
        arm = str(meta["arm"])

        if reg_pass and sem_pass:
            cm_regex_vs_judge["regex_pass_judge_pass"] += 1
            cm_by_arm[arm]["regex_pass_judge_pass"] += 1
        elif reg_pass and not sem_pass:
            cm_regex_vs_judge["regex_pass_judge_fail"] += 1
            cm_by_arm[arm]["regex_pass_judge_fail"] += 1
        elif (not reg_pass) and sem_pass:
            cm_regex_vs_judge["regex_fail_judge_pass"] += 1
            cm_by_arm[arm]["regex_fail_judge_pass"] += 1
        else:
            cm_regex_vs_judge["regex_fail_judge_fail"] += 1
            cm_by_arm[arm]["regex_fail_judge_fail"] += 1

        rec = {
            "blind_id": bid,
            "model": meta["model"],
            "arm": arm,
            "probe_id": meta["probe_id"],
            "stratum": meta["stratum"],
            "topology": meta["topology"],
            "requires_hedge_or_conflict": bool(meta["requires_hedge_or_conflict"]),
            "regex_pass": reg_pass,
            "judge1": {
                "D1": j1["D1"],
                "D2": j1["D2"],
                "D3": j1["D3"],
                "D4": j1["D4"],
                "judge_model": j1["judge_model"],
                "rationale": j1["rationale"],
            },
            "judge2": {
                "D1": j2["D1"],
                "D2": j2["D2"],
                "D3": j2["D3"],
                "D4": j2["D4"],
                "judge_model": j2["judge_model"],
                "rationale": j2["rationale"],
            },
            "judge3": j3,
            "adjudicated": {"D1": d1, "D2": d2, "D3": d3, "D4": d4},
            "adjudicated_strict_3way_d3_fail": {"D1": d1, "D2": d2, "D3": d3_strict_3way_fail, "D4": d4},
            "semantic_pass": sem_pass,
            "semantic_pass_strict_3way_d3_fail": sem_pass_strict_3way,
            "reply": meta.get("redacted_reply", meta["reply"]),
        }
        evaluated_items.append(rec)
        by_model_pair.setdefault((str(meta["model"]), str(meta["probe_id"])), {})[arm] = rec

    regex_labels = ["PASS" if r["regex_pass"] else "FAIL" for r in evaluated_items]
    sem_labels = ["PASS" if r["semantic_pass"] else "FAIL" for r in evaluated_items]
    regex_vs_judge_stats = {
        **cohen_kappa(regex_labels, sem_labels, ["PASS", "FAIL"]),
        "confusion_matrix_pooled_288": cm_regex_vs_judge,
        "confusion_matrix_by_arm": cm_by_arm,
    }

    models_order = ["E2B", "E4B", "12B", "26B-A4B"]
    per_model_results: dict[str, dict[str, object]] = {}
    pairs_by_item_sem: dict[str, list[tuple[int, int]]] = {}

    pooled_sem_a = 0
    pooled_sem_b = 0
    pooled_sem_disputed_a = 0
    pooled_sem_disputed_b = 0
    pooled_sem_nondisp_hedge_a = 0
    pooled_sem_nondisp_hedge_b = 0
    pooled_sem_hedge_a = 0
    pooled_sem_hedge_b = 0
    pooled_sem_met_a = 0
    pooled_sem_met_b = 0
    pooled_sem_b_wins = 0
    pooled_sem_c_losses = 0

    pooled_reg_a = 0
    pooled_reg_b = 0
    pooled_reg_b_wins = 0
    pooled_reg_c_losses = 0

    pooled_d1_counts: dict[str, Counter[str]] = {"Arm_A": Counter(), "Arm_B": Counter()}
    pooled_d2_counts: dict[str, Counter[str]] = {"Arm_A": Counter(), "Arm_B": Counter()}
    pooled_over_hedge_met: dict[str, int] = {"Arm_A": 0, "Arm_B": 0}
    pooled_conflict_disclosed: dict[str, int] = {"Arm_A": 0, "Arm_B": 0}

    for m_name in models_order:
        m_pairs = [
            (pid, arms["Arm_A"], arms["Arm_B"])
            for (mod, pid), arms in sorted(by_model_pair.items())
            if mod == m_name
        ]
        assert len(m_pairs) == 36

        sem_a = 0
        sem_b = 0
        sem_hedge_a = 0
        sem_hedge_b = 0
        sem_met_a = 0
        sem_met_b = 0
        sem_b_wins = 0
        sem_c_losses = 0

        reg_a = 0
        reg_b = 0
        reg_b_wins = 0
        reg_c_losses = 0

        over_hedge_a = 0
        over_hedge_b = 0
        conflict_disc_a = 0
        conflict_disc_b = 0

        for pid, ra, rb in m_pairs:
            sa = bool(ra["semantic_pass"])
            sb = bool(rb["semantic_pass"])
            rga = bool(ra["regex_pass"])
            rgb = bool(rb["regex_pass"])
            req_h = bool(ra["requires_hedge_or_conflict"])
            top = str(ra["topology"])

            pairs_by_item_sem.setdefault(pid, []).append((int(sa), int(sb)))

            sem_a += int(sa)
            sem_b += int(sb)
            reg_a += int(rga)
            reg_b += int(rgb)

            if req_h:
                sem_hedge_a += int(sa)
                sem_hedge_b += int(sb)
                if top == "disputed":
                    pooled_sem_disputed_a += int(sa)
                    pooled_sem_disputed_b += int(sb)
                else:
                    pooled_sem_nondisp_hedge_a += int(sa)
                    pooled_sem_nondisp_hedge_b += int(sb)
            else:
                sem_met_a += int(sa)
                sem_met_b += int(sb)
                if ra["adjudicated"]["D3"] == "YES":  # type: ignore[index]
                    over_hedge_a += 1
                    pooled_over_hedge_met["Arm_A"] += 1
                if rb["adjudicated"]["D3"] == "YES":  # type: ignore[index]
                    over_hedge_b += 1
                    pooled_over_hedge_met["Arm_B"] += 1

            if top == "disputed":
                if ra["adjudicated"]["D4"] == "YES":  # type: ignore[index]
                    conflict_disc_a += 1
                    pooled_conflict_disclosed["Arm_A"] += 1
                if rb["adjudicated"]["D4"] == "YES":  # type: ignore[index]
                    conflict_disc_b += 1
                    pooled_conflict_disclosed["Arm_B"] += 1

            pooled_d1_counts["Arm_A"][str(ra["adjudicated"]["D1"])] += 1  # type: ignore[index]
            pooled_d1_counts["Arm_B"][str(rb["adjudicated"]["D1"])] += 1  # type: ignore[index]
            pooled_d2_counts["Arm_A"][str(ra["adjudicated"]["D2"])] += 1  # type: ignore[index]
            pooled_d2_counts["Arm_B"][str(rb["adjudicated"]["D2"])] += 1  # type: ignore[index]

            if sb and not sa:
                sem_b_wins += 1
            elif sa and not sb:
                sem_c_losses += 1

            if rgb and not rga:
                reg_b_wins += 1
            elif rga and not rgb:
                reg_c_losses += 1

        pooled_sem_a += sem_a
        pooled_sem_b += sem_b
        pooled_sem_hedge_a += sem_hedge_a
        pooled_sem_hedge_b += sem_hedge_b
        pooled_sem_met_a += sem_met_a
        pooled_sem_met_b += sem_met_b
        pooled_sem_b_wins += sem_b_wins
        pooled_sem_c_losses += sem_c_losses

        pooled_reg_a += reg_a
        pooled_reg_b += reg_b
        pooled_reg_b_wins += reg_b_wins
        pooled_reg_c_losses += reg_c_losses

        per_model_results[m_name] = {
            "n_items": 36,
            "semantic_arm_a_pass": f"{sem_a}/36",
            "semantic_arm_a_pct": round(sem_a / 36.0 * 100.0, 2),
            "semantic_arm_a_wilson_95_ci": wilson_ci_95(sem_a, 36),
            "semantic_arm_a_hedge_cells": f"{sem_hedge_a}/18",
            "semantic_arm_a_met_cells": f"{sem_met_a}/18",
            "semantic_arm_b_pass": f"{sem_b}/36",
            "semantic_arm_b_pct": round(sem_b / 36.0 * 100.0, 2),
            "semantic_arm_b_wilson_95_ci": wilson_ci_95(sem_b, 36),
            "semantic_arm_b_hedge_cells": f"{sem_hedge_b}/18",
            "semantic_arm_b_met_cells": f"{sem_met_b}/18",
            "semantic_mcnemar": exact_mcnemar(sem_b_wins, sem_c_losses),
            "over_hedge_on_met_cells_arm_a": f"{over_hedge_a}/18",
            "over_hedge_on_met_cells_arm_b": f"{over_hedge_b}/18",
            "conflict_disclosed_on_disputed_cells_arm_a": f"{conflict_disc_a}/9",
            "conflict_disclosed_on_disputed_cells_arm_b": f"{conflict_disc_b}/9",
            "regex_arm_a_pass": f"{reg_a}/36",
            "regex_arm_a_pct": round(reg_a / 36.0 * 100.0, 2),
            "regex_arm_b_pass": f"{reg_b}/36",
            "regex_arm_b_pct": round(reg_b / 36.0 * 100.0, 2),
            "regex_mcnemar": exact_mcnemar(reg_b_wins, reg_c_losses),
        }

    cluster_boot = cluster_bootstrap_diff_ci(pairs_by_item_sem)

    return {
        "cohort_name": cohort_name,
        "judge1_path": str(j1_path.relative_to(REPO_ROOT)),
        "judge1_sha256": j1_sha,
        "judge2_path": str(j2_path.relative_to(REPO_ROOT)),
        "judge2_sha256": j2_sha,
        "judge3_adjudication_path": str(j3_path.relative_to(REPO_ROOT)) if j3_path.exists() else None,
        "judge3_adjudication_sha256": j3_sha,
        "judge3_n_adjudicated": len(j3_map),
        "hashes_distinct": j1_sha != j2_sha,
        "inter_rater_reliability_kappa": kappa_table,
        "regex_vs_judge_agreement": regex_vs_judge_stats,
        "judge1_standalone_summary": summarize_single_rater(by_model_pair, "judge1"),
        "judge2_standalone_summary": summarize_single_rater(by_model_pair, "judge2"),
        "strict_3way_d3_fail_sensitivity_summary": summarize_single_rater(
            by_model_pair, "adjudicated_strict_3way_d3_fail"
        ),
        "pooled_summary_144_pairs": {
            "semantic_arm_a_pass": f"{pooled_sem_a}/144",
            "semantic_arm_a_pct": round(pooled_sem_a / 144.0 * 100.0, 2),
            "semantic_arm_a_wilson_95_ci": wilson_ci_95(pooled_sem_a, 144),
            "semantic_arm_a_hedge_cells": f"{pooled_sem_hedge_a}/72",
            "semantic_arm_a_disputed_cells": f"{pooled_sem_disputed_a}/36",
            "semantic_arm_a_nondisputed_domain_count_cells": f"{pooled_sem_nondisp_hedge_a}/36",
            "semantic_arm_a_met_cells": f"{pooled_sem_met_a}/72",
            "semantic_arm_b_pass": f"{pooled_sem_b}/144",
            "semantic_arm_b_pct": round(pooled_sem_b / 144.0 * 100.0, 2),
            "semantic_arm_b_wilson_95_ci": wilson_ci_95(pooled_sem_b, 144),
            "semantic_arm_b_hedge_cells": f"{pooled_sem_hedge_b}/72",
            "semantic_arm_b_disputed_cells": f"{pooled_sem_disputed_b}/36",
            "semantic_arm_b_nondisputed_domain_count_cells": f"{pooled_sem_nondisp_hedge_b}/36",
            "semantic_arm_b_met_cells": f"{pooled_sem_met_b}/72",
            "semantic_pooled_mcnemar_secondary": exact_mcnemar(pooled_sem_b_wins, pooled_sem_c_losses),
            "semantic_cluster_bootstrap_primary": cluster_boot,
            "d1_distribution": {
                "Arm_A": dict(pooled_d1_counts["Arm_A"]),
                "Arm_B": dict(pooled_d1_counts["Arm_B"]),
            },
            "d2_distribution": {
                "Arm_A": dict(pooled_d2_counts["Arm_A"]),
                "Arm_B": dict(pooled_d2_counts["Arm_B"]),
            },
            "over_hedge_on_met_cells_r16": {
                "Arm_A": f"{pooled_over_hedge_met['Arm_A']}/72 ({round(pooled_over_hedge_met['Arm_A']/72.0*100.0, 2)}%)",
                "Arm_B": f"{pooled_over_hedge_met['Arm_B']}/72 ({round(pooled_over_hedge_met['Arm_B']/72.0*100.0, 2)}%)",
            },
            "conflict_disclosed_on_disputed_cells": {
                "Arm_A": f"{pooled_conflict_disclosed['Arm_A']}/36 ({round(pooled_conflict_disclosed['Arm_A']/36.0*100.0, 2)}%)",
                "Arm_B": f"{pooled_conflict_disclosed['Arm_B']}/36 ({round(pooled_conflict_disclosed['Arm_B']/36.0*100.0, 2)}%)",
            },
            "regex_arm_a_pass": f"{pooled_reg_a}/144",
            "regex_arm_a_pct": round(pooled_reg_a / 144.0 * 100.0, 2),
            "regex_arm_b_pass": f"{pooled_reg_b}/144",
            "regex_arm_b_pct": round(pooled_reg_b / 144.0 * 100.0, 2),
            "regex_pooled_mcnemar": exact_mcnemar(pooled_reg_b_wins, pooled_reg_c_losses),
        },
        "by_model": per_model_results,
        "evaluated_turns_288": evaluated_items,
    }


def main() -> None:
    primary = evaluate_cohort(
        "primary_neutral_rubric_unredacted",
        WO45_DIR / "r10v2_blinded_288_key.json",
        WO45_DIR / "r10v2_judge1.jsonl",
        WO45_DIR / "r10v2_judge2.jsonl",
        WO45_DIR / "r10v2_judge3_adjudication.jsonl",
    )
    redacted = evaluate_cohort(
        "secondary_neutral_rubric_redacted_standard_tokens",
        WO45_DIR / "r10v2_redacted_288_key.json",
        WO45_DIR / "r10v2_redacted_judge1.jsonl",
        WO45_DIR / "r10v2_redacted_judge2.jsonl",
        WO45_DIR / "r10v2_redacted_judge3_adjudication.jsonl",
    )

    v1_rep = json.loads((WO45_DIR / "r10_regrade_288_report.json").read_text(encoding="utf-8"))
    secondary_policy_rubric = {
        "note": "Secondary analysis graded against Lucca's own POLICY_TABLE_2D thresholds (v1 Judge 1 rubric; superseded as primary metric per REVIEW_G3 F-2)",
        "pooled_summary_144_pairs": v1_rep["pooled_summary_144_pairs"],
        "by_model": v1_rep["by_model"],
    }

    payload = {
        "task_id": "R-10-v2",
        "gate": "G3-v2",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_report_path": "logs/test_reports/web_evidentiary_burden_360_report.json",
        "source_report_sha256": "d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad",
        "neutral_prompt_path": "logs/test_reports/wo45/prompts/r10v2_judge_prompt.md",
        "primary_neutral_unredacted": primary,
        "secondary_neutral_redacted": redacted,
        "secondary_v1_policy_table_rubric": secondary_policy_rubric,
    }

    out_json = WO45_DIR / "r10v2_regrade_288_report.json"
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    out_sha = hashlib.sha256(out_json.read_bytes()).hexdigest()
    print(f"Saved {out_json} (SHA-256: {out_sha})")


if __name__ == "__main__":
    main()
