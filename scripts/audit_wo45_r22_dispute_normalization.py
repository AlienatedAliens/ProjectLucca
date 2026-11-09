#!/usr/bin/env python3
"""
WO-45 Task R-22: Post-hoc audit and ablation of dispute-detection normalization
patterns in `src/lucca/core/proof_policy.py:424-443` on the WO-44 corpus
(`data/benchmarks/web_evidentiary_burden_360.jsonl`) and the prior N=60 dev set
(`data/benchmarks/web_evidentiary_burden_60.jsonl`).

Analysis Label: post-hoc analysis on the WO-44 corpus.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from lucca.core.coherence import ToolReceipt  # noqa: E402
from lucca.core.corroboration import (  # noqa: E402
    CQAnswer,
    Scheme,
    adjust_confidence,
    critical_questions,
)
from lucca.core.proof_policy import (  # noqa: E402
    _QUESTION_FILLER_TOKENS,
    _extract_source_domain,
    _select_query_aligned_sentence,
    _tokenize_proposition,
    standard_for_confidence,
)
from lucca.core.schemas import InferenceStep  # noqa: E402

SPECIAL_PATTERNS: list[tuple[str, str, str, str, str]] = [
    (
        "flag_no_prefix",
        r"--no-[a-z0-9-]+",
        "safeguard-flag",
        "--no-",
        "CLI flags beginning with --no-* (e.g., --no-preserve-root in WEB_HIGH_010 in prior N=60 dev set)",
    ),
    (
        "to_prevent",
        r"\bto\s+prevent\b",
        "for safety",
        r"to\s+prevent",
        "Safety rationale phrase 'to prevent' (WEB_HIGH_009, WEB_HIGH_010 in prior N=60 dev set; WEB360_LOW_081 in N=360)",
    ),
    (
        "do_not_exceed",
        r"\bdo\s+not\s+exceed\b",
        "for safety",
        r"do\s+not\s+exceed",
        "Dosage limit phrase 'do not exceed' (WEB_HIGH_009 in prior N=60 dev set; LIVE_HIGH_01 in N=6 live web slice)",
    ),
    (
        "cannot_be_undone_without",
        r"\bcannot\s+be\s+undone\s+without\b",
        "for safety",
        r"cannot\s+be\s+undone",
        "Irreversibility warning 'cannot be undone without' (WEB_HIGH_003 in prior N=60 dev set)",
    ),
    (
        "takes_no_c",
        r"\btakes\s+no\s+c\w*\b",
        "for safety",
        r"takes\s+no\s+c",
        "Scraped live web snippet phrase in N=6 live web sample slice (LIVE_LOW_02 / LIVE_MED_01)",
    ),
    (
        "that_are_not_part_of",
        r"\bthat\s+are\s+not\s+part\s+of\b",
        "for safety",
        r"that\s+are\s+not\s+part",
        "Scraped RFC 8259 live web snippet phrase in N=6 live web sample slice (LIVE_MED_02: 'that are not part of')",
    ),
    (
        "bom_is_forbidden",
        r"\bbom\s+is\s+forbidden\b",
        "for safety",
        r"bom\s+is\s+forbidden",
        "Scraped RFC 8259 §8.1 live web snippet phrase in N=6 live web sample slice (LIVE_MED_02: 'UTF-8... BOM is forbidden')",
    ),
]

BROAD_NEGATION_STRIP_RE = (
    r"\b(?:not|no|never|none|neither|nor|cannot|without|"
    r"alternativ\w+|countervail\w+|competing|conflicting|contrary|"
    r"disparit\w+|distinguish\w+|outweigh\w+|prevent\w*|throttl\w+|"
    r"side\s+effect\w*|adverse|drawback\w*|fallback|split|"
    r"differs?|difference\w*|distinct\w*)\b"
)

AUTH_DISPUTE_RE = re.compile(
    r"\b(?:disput\w*|refut\w*|contradict\w*|debunk\w*|false|untrue|hoax|myth|"
    r"invalid\w*|forbidden|contraindicated|insecure|"
    r"(?:is|was|are|were|does|did|do|must|should|can|will)\s+not|"
    r"never\s+(?:announced|requires|sufficient|supported|released))\b",
    re.IGNORECASE,
)


def git_introducing_commit(search_term: str) -> str:
    res = subprocess.run(
        [
            "git",
            "log",
            "-S",
            search_term,
            "--reverse",
            "--format=%h %ad %s",
            "--date=iso",
            "--",
            "src/lucca/core/proof_policy.py",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
    return lines[0] if lines else "unknown"


def evaluate_walton_with_ablation(
    item: dict[str, object],
    disabled_pattern_names: set[str],
    disable_broad_negation_strip: bool = False,
) -> tuple[bool, bool, list[str]]:
    """Returns (walton_std_ok, is_disputed, matched_pattern_names_on_item)."""
    query_text = str(item["query"])
    search_results = item["search_results"]
    assert isinstance(search_results, list)

    raw_items: list[tuple[str, str, str]] = []
    for idx, r in enumerate(search_results, 1):
        if not isinstance(r, dict):
            continue
        url = str(r.get("url", "") or r.get("source_url", "") or "").strip()
        raw_dom = str(r.get("domain", "") or r.get("source", "") or url).strip()
        dom = _extract_source_domain(raw_dom, idx)
        title = str(r.get("title", "") or "").strip()
        snip = str(r.get("snippet", "") or "").strip()
        preview = str(
            r.get("content_preview", "") or r.get("content", "") or r.get("output", "") or ""
        ).strip()
        body = f"{snip}. {preview}" if (snip and preview and snip not in preview) else (preview or snip)
        combined = f"{title}. {body}".strip(". ") if title and title not in body else (body or title)
        if combined:
            raw_items.append((dom, url or f"https://{dom}", combined))

    q_toks = [t for t in _tokenize_proposition(query_text) if t not in _QUESTION_FILLER_TOKENS]
    q_tok_set = set(q_toks)
    primary_dom, _primary_url, primary_raw = raw_items[0]
    primary_sent = _select_query_aligned_sentence(primary_raw, q_tok_set)
    p_toks = [t for t in _tokenize_proposition(primary_sent) if t not in _QUESTION_FILLER_TOKENS]
    subj_tokens = q_toks[:4] if q_toks else p_toks[:3]
    subj_set = set(subj_tokens)
    obj_tokens = [t for t in p_toks if t not in subj_set][:4]
    if not obj_tokens:
        obj_tokens = q_toks[4:7] if len(q_toks) > 4 else p_toks[:3]

    step_s = " ".join(subj_tokens) if subj_tokens else "topic"
    step_o = " ".join(obj_tokens) if obj_tokens else "verified"
    core_claim = f"{step_s} {step_o}".strip()

    matched_patterns: list[str] = []
    receipts: list[ToolReceipt] = []
    for idx, (dom, url, text) in enumerate(raw_items, 1):
        aligned_sent = _select_query_aligned_sentence(text, q_tok_set | set(obj_tokens))
        norm_sent = aligned_sent
        for p_name, p_regex, p_repl, _git_s, _origin in SPECIAL_PATTERNS:
            if re.search(p_regex, aligned_sent, flags=re.IGNORECASE):
                if p_name not in matched_patterns:
                    matched_patterns.append(p_name)
            if p_name not in disabled_pattern_names:
                norm_sent = re.sub(p_regex, p_repl, norm_sent, flags=re.IGNORECASE)

        is_genuine_dispute = idx > 1 and bool(AUTH_DISPUTE_RE.search(norm_sent))
        if not is_genuine_dispute and not disable_broad_negation_strip:
            norm_sent = re.sub(BROAD_NEGATION_STRIP_RE, "", norm_sent, flags=re.IGNORECASE)

        receipts.append(
            ToolReceipt(
                tool="search_web",
                tool_name="search_web",
                ok=True,
                call_id=f"web-rcpt-{idx}",
                args={"url": url, "domain": dom, "query": query_text},
                output=f"Report from {dom}: {norm_sent}",
            )
        )

    step = InferenceStep(
        s=step_s,
        p="asserts",
        o=step_o,
        premises=[f"{primary_dom} asserts {core_claim}"],
        confidence=0.70,
        rationale="web_evidence_burden",
    )
    q_results = critical_questions(
        scheme=Scheme.AUTHORITY,
        step=step,
        store=None,
        receipts=receipts,
        verifier=None,
    )
    q2 = next(
        (
            q
            for q in q_results
            if "corroborated" in q.question.lower() and q.answer == CQAnswer.SATISFIED
        ),
        None,
    )
    extra_indep_count = q2.count if q2 is not None else 0
    extra_indep_domains = list(q2.sources) if q2 is not None else []
    disputes = [
        q
        for q in q_results
        if ("dispute" in q.question.lower() or "disputed" in q.question.lower())
        and q.answer == CQAnswer.SATISFIED
    ]
    is_disputed = len(disputes) > 0
    all_indep_domains: list[str] = [primary_dom]
    for dom in extra_indep_domains:
        if dom not in all_indep_domains:
            all_indep_domains.append(dom)
    total_indep = len(all_indep_domains)

    if is_disputed:
        base_conf = 0.70
    elif extra_indep_count >= 2:
        base_conf = 0.85
    else:
        base_conf = 0.70
    eff_conf, _ = adjust_confidence(base_conf, q_results, scheme=Scheme.AUTHORITY)
    achieved_std = standard_for_confidence(eff_conf)

    std_ok = (
        achieved_std.value == item["expected_standard"]
        and abs(eff_conf - float(item["expected_confidence"])) < 1e-6
        and total_indep == int(item["expected_independent_sources"])
        and is_disputed is bool(item["expected_disputed"])
    )
    return std_ok, is_disputed, matched_patterns


def main() -> None:
    path_360 = REPO_ROOT / "data/benchmarks/web_evidentiary_burden_360.jsonl"
    path_60 = REPO_ROOT / "data/benchmarks/web_evidentiary_burden_60.jsonl"
    items_360 = [json.loads(ln) for ln in path_360.read_text(encoding="utf-8").splitlines() if ln.strip()]
    items_60 = [json.loads(ln) for ln in path_60.read_text(encoding="utf-8").splitlines() if ln.strip()]

    # Find which items in the N=60 dev set match each pattern
    dev60_matches_by_pattern: dict[str, list[str]] = {p[0]: [] for p in SPECIAL_PATTERNS}
    for it60 in items_60:
        pid60 = str(it60.get("probe_id", ""))
        full_txt = " ".join(
            f"{r.get('title', '')} {r.get('snippet', '')}"
            for r in it60.get("search_results", [])
            if isinstance(r, dict)
        )
        for p_name, p_regex, _, _, _ in SPECIAL_PATTERNS:
            if re.search(p_regex, full_txt, flags=re.IGNORECASE):
                dev60_matches_by_pattern[p_name].append(pid60)

    # Baseline (all patterns enabled) on 360
    base_results: dict[str, tuple[bool, bool, list[str]]] = {}
    pattern_matches_360: dict[str, list[str]] = {p[0]: [] for p in SPECIAL_PATTERNS}
    for it in items_360:
        pid = str(it["probe_id"])
        std_ok, is_disp, matched = evaluate_walton_with_ablation(it, set(), False)
        base_results[pid] = (std_ok, is_disp, matched)
        for m in matched:
            pattern_matches_360[m].append(pid)

    base_pass_count = sum(1 for v in base_results.values() if v[0])

    ablation_rows: list[dict[str, object]] = []
    for p_name, p_regex, p_repl, git_s, origin_note in SPECIAL_PATTERNS:
        commit_info = git_introducing_commit(git_s)
        changed_ids: list[str] = []
        pass_count = 0
        for it in items_360:
            pid = str(it["probe_id"])
            std_ok, is_disp, _ = evaluate_walton_with_ablation(it, {p_name}, False)
            if std_ok:
                pass_count += 1
            if (std_ok, is_disp) != (base_results[pid][0], base_results[pid][1]):
                changed_ids.append(pid)

        ablation_rows.append(
            {
                "pattern_name": p_name,
                "regex": p_regex,
                "replacement": p_repl,
                "source_location": "src/lucca/core/proof_policy.py:424-431",
                "introducing_commit": commit_info,
                "matched_items_in_360_count": len(pattern_matches_360[p_name]),
                "matched_items_in_360_ids": pattern_matches_360[p_name],
                "items_changing_verdict_when_disabled_count": len(changed_ids),
                "items_changing_verdict_when_disabled_ids": changed_ids,
                "walton_conformance_when_disabled": f"{pass_count}/{len(items_360)}",
                "matched_items_in_prior_dev_60_count": len(dev60_matches_by_pattern[p_name]),
                "matched_items_in_prior_dev_60_ids": dev60_matches_by_pattern[p_name],
                "present_in_prior_dev_set_or_live_6_slice": True,
                "origin_explanation": origin_note,
            }
        )

    # Disable all 7 special patterns simultaneously
    all_special_names = {p[0] for p in SPECIAL_PATTERNS}
    all_special_changed: list[str] = []
    all_special_pass = 0
    for it in items_360:
        pid = str(it["probe_id"])
        std_ok, is_disp, _ = evaluate_walton_with_ablation(it, all_special_names, False)
        if std_ok:
            all_special_pass += 1
        if (std_ok, is_disp) != (base_results[pid][0], base_results[pid][1]):
            all_special_changed.append(pid)

    # Also test disabling the broad negation/contrast strip at lines 433-443 (with and without special patterns)
    broad_strip_changed: list[str] = []
    broad_strip_pass = 0
    for it in items_360:
        pid = str(it["probe_id"])
        std_ok, is_disp, _ = evaluate_walton_with_ablation(it, set(), True)
        if std_ok:
            broad_strip_pass += 1
        if (std_ok, is_disp) != (base_results[pid][0], base_results[pid][1]):
            broad_strip_changed.append(pid)

    all_disabled_changed: list[str] = []
    all_disabled_pass = 0
    for it in items_360:
        pid = str(it["probe_id"])
        std_ok, is_disp, _ = evaluate_walton_with_ablation(it, all_special_names, True)
        if std_ok:
            all_disabled_pass += 1
        if (std_ok, is_disp) != (base_results[pid][0], base_results[pid][1]):
            all_disabled_changed.append(pid)

    payload = {
        "task_id": "R-22",
        "analysis_label": "post-hoc analysis on the WO-44 corpus",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "dataset_path": "data/benchmarks/web_evidentiary_burden_360.jsonl",
        "dataset_sha256": hashlib.sha256(path_360.read_bytes()).hexdigest(),
        "prior_dev_dataset_path": "data/benchmarks/web_evidentiary_burden_60.jsonl",
        "prior_dev_dataset_sha256": hashlib.sha256(path_60.read_bytes()).hexdigest(),
        "baseline_walton_conformance": f"{base_pass_count}/{len(items_360)}",
        "per_pattern_ablation": ablation_rows,
        "combined_ablations": {
            "all_7_special_patterns_disabled": {
                "walton_conformance": f"{all_special_pass}/{len(items_360)}",
                "items_changing_verdict_count": len(all_special_changed),
                "items_changing_verdict_ids": all_special_changed,
            },
            "broad_negation_strip_433_443_disabled_only": {
                "introducing_commit": git_introducing_commit("countervail"),
                "walton_conformance": f"{broad_strip_pass}/{len(items_360)}",
                "items_changing_verdict_count": len(broad_strip_changed),
                "items_changing_verdict_ids": broad_strip_changed,
            },
            "all_normalizations_424_443_disabled": {
                "walton_conformance": f"{all_disabled_pass}/{len(items_360)}",
                "items_changing_verdict_count": len(all_disabled_changed),
                "items_changing_verdict_ids": all_disabled_changed,
            },
        },
    }

    out_path = REPO_ROOT / "logs/test_reports/wo45/r22_dispute_normalization_ablation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {out_path}")
    for row in ablation_rows:
        print(
            f"  Pattern {row['pattern_name']}: commit='{row['introducing_commit']}' | "
            f"matched_360={row['matched_items_in_360_ids']} | "
            f"changed_360={row['items_changing_verdict_when_disabled_ids']} | "
            f"dev_60={row['matched_items_in_prior_dev_60_ids']}"
        )
    print("Combined all 7 special disabled:", payload["combined_ablations"]["all_7_special_patterns_disabled"])
    print("Broad negation strip disabled:", payload["combined_ablations"]["broad_negation_strip_433_443_disabled_only"])
    print("All 424-443 disabled:", payload["combined_ablations"]["all_normalizations_424_443_disabled"])


if __name__ == "__main__":
    main()
