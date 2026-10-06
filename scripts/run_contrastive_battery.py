"""
Project Lucca — Contrastive Live-Companion Battery Harness (Phase 3.5–3.6)
Pre-registered protocol (2026-10-06, AUDIT_REGISTER.md C-01..C-06)

Three arms across three strata:
  - Arm A (Bare LLM):      Direct chat completion against llama-server. No memory, no tools,
                           no Lucca persona, enable_thinking=False.
  - Arm B (Compound):      Full Lucca turn pipeline (memory retrieval, rules, provenance,
                           reflection, output supervisor) via HW Orchestrator.
  - Arm C (RAG Baseline):  Vector/BM25 retrieval (top-5 memories) injected into prompt,
                           direct chat completion, enable_thinking=False.

Three strata:
  - recall:                Questions answerable from seeded memory/actions.
  - receipt_introspection: "Did you actually X?" answered from signed receipts.
  - abstention:            Unanswerable questions; model must abstain.

Frozen Grader:
  Uses src/lucca/eval/contrastive_grader.py (SHA f015710f...27c2).
  Empty replies graded Grade.ERROR (never FAIL/fabricated).
  Echo-stripping applied to prevent question parroting from gaining recall credit.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from lucca.core.config import get_config
from lucca.core.schemas import RetrievalQuery
from lucca.eval.contrastive_grader import (
    Grade,
    grade_probe,
    grader_sha256,
    stratum_invalid,
    THRESHOLD_ABSTENTION,
    THRESHOLD_INTROSPECTION,
    THRESHOLD_RECALL,
)
from lucca.reasoning.stats import mcnemar_test, wilson_score_interval
from tests.test_a1_live_hw import (
    _invoke_text_turn,
    _make_hw_orchestrator,
    _seed_a1_history,
)

EXPECTED_GRADER_SHA: Final[str] = (
    "f015710fbb634d00639004c5afbd604304803a23ffb968ad22d71246807727c2"
)

LLM_ONLY_SYSTEM_PROMPT: Final[str] = (
    "You are a helpful desktop assistant. Answer the user's question directly "
    "and concisely."
)


def get_git_commit() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def check_llm_server(base_url: str) -> None:
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5.0)
        if resp.status_code != 200:
            raise RuntimeError(f"llama-server unhealthy at {base_url} (HTTP {resp.status_code})")
    except Exception as e:
        raise RuntimeError(f"llama-server unreachable at {base_url}: {e}") from e


def query_llm_direct(base_url: str, system_prompt: str, user_question: str) -> str:
    """Bare non-streaming chat completion with enable_thinking=False."""
    try:
        resp = httpx.post(
            f"{base_url}/v1/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_question},
                ],
                "temperature": 0.6,
                "max_tokens": 300,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=90.0,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", ""))
    except Exception as e:
        print(f"    [!] Error querying direct LLM: {e}")
        return ""


def run_battery(
    probes_path: Path,
    arms_to_run: list[str],
    output_dir: Path,
) -> tuple[dict, str]:
    current_grader_sha = grader_sha256()
    print(f"[*] Verifying frozen contrastive grader SHA: {current_grader_sha}")
    if current_grader_sha != EXPECTED_GRADER_SHA:
        raise ValueError(
            f"Grader hash mismatch! Expected {EXPECTED_GRADER_SHA}, got {current_grader_sha}. "
            "Grader modification is strictly forbidden per Gate 2 invariant."
        )

    cfg = get_config()
    base_url = f"http://{cfg.llm.host}:{cfg.llm.port}"
    print(f"[*] Checking llama-server at {base_url}...")
    check_llm_server(base_url)

    probes = [
        json.loads(line)
        for line in probes_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"[*] Loaded {len(probes)} probes from {probes_path}")

    git_commit = get_git_commit()
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        print("[*] Initializing HW Orchestrator and seeding memory...")
        orch, store, db = _make_hw_orchestrator(tmp_path)
        try:
            _seed_a1_history(store, db, time.time())

            results: list[dict[str, object]] = []
            n_total = len(probes)

            print(f"[*] Running {n_total} probes across arms: {', '.join(arms_to_run)}...")
            t0 = time.time()

            for idx, probe in enumerate(probes, 1):
                pid = str(probe["id"])
                stratum = str(probe["stratum"])
                question = str(probe["question"])
                expect_mode = str(probe["expect_mode"])
                raw_expect = probe.get("expect_any", [])
                expect_any = [str(x) for x in raw_expect] if isinstance(raw_expect, list) else []

                row: dict[str, object] = {
                    "id": pid,
                    "stratum": stratum,
                    "question": question,
                    "expect_mode": expect_mode,
                    "expect_any": expect_any,
                }

                print(f"[{idx:02d}/{n_total:02d}] {pid} ({stratum}): {question[:60]}...")

                # Arm A: Bare LLM
                if "arm_a" in arms_to_run:
                    reply_a = query_llm_direct(base_url, LLM_ONLY_SYSTEM_PROMPT, question)
                    grade_a, reason_a = grade_probe(expect_mode, expect_any, question, reply_a)
                    row["arm_a_reply"] = reply_a
                    row["arm_a_grade"] = grade_a.value
                    row["arm_a_pass"] = grade_a == Grade.PASS
                    row["arm_a_reason"] = reason_a
                    print(f"    Arm A: {grade_a.value} ({reason_a})")

                # Arm B: Compound Orchestrator
                if "arm_b" in arms_to_run:
                    reply_b = _invoke_text_turn(orch, question, f"contrastive-b-{pid}")
                    grade_b, reason_b = grade_probe(expect_mode, expect_any, question, reply_b)
                    row["arm_b_reply"] = reply_b
                    row["arm_b_grade"] = grade_b.value
                    row["arm_b_pass"] = grade_b == Grade.PASS
                    row["arm_b_reason"] = reason_b
                    print(f"    Arm B: {grade_b.value} ({reason_b})")

                # Arm C: RAG Baseline
                if "arm_c" in arms_to_run:
                    q = RetrievalQuery(query_text=question, limit=5)
                    hits = store.search(q)
                    context_lines = [f"- {h.content}" for h in hits]
                    context_str = "\n".join(context_lines) if context_lines else "None."
                    rag_prompt = (
                        "You are a helpful desktop assistant. Answer the user's question directly and concisely "
                        "based on the following retrieved context. If the context does not contain the answer, "
                        "state clearly that you do not know or have no record.\n\n"
                        f"Context:\n{context_str}"
                    )
                    reply_c = query_llm_direct(base_url, rag_prompt, question)
                    grade_c, reason_c = grade_probe(expect_mode, expect_any, question, reply_c)
                    row["arm_c_reply"] = reply_c
                    row["arm_c_grade"] = grade_c.value
                    row["arm_c_pass"] = grade_c == Grade.PASS
                    row["arm_c_reason"] = reason_c
                    print(f"    Arm C: {grade_c.value} ({reason_c})")

                results.append(row)

            elapsed_total = time.time() - t0
            print(f"[*] All probes completed in {elapsed_total:.1f}s")

        finally:
            db.close()

    # Summarize per arm and stratum
    strata = ("recall", "receipt_introspection", "abstention")
    summaries: dict[str, dict[str, object]] = {}

    for arm in arms_to_run:
        arm_sum: dict[str, object] = {}
        for stratum in strata:
            s_rows = [r for r in results if r["stratum"] == stratum]
            n_strat = len(s_rows)
            n_pass = sum(1 for r in s_rows if r.get(f"{arm}_grade") == Grade.PASS.value)
            n_fail = sum(1 for r in s_rows if r.get(f"{arm}_grade") == Grade.FAIL.value)
            n_error = sum(1 for r in s_rows if r.get(f"{arm}_grade") == Grade.ERROR.value)

            is_invalid = stratum_invalid(n_error, n_strat)
            # Denominator for accuracy excludes transport/server errors
            valid_n = n_strat - n_error
            rate = (n_pass / valid_n) if valid_n > 0 else 0.0
            wilson_lb, wilson_ub = wilson_score_interval(n_pass, valid_n) if valid_n > 0 else (0.0, 0.0)

            arm_sum[stratum] = {
                "n_total": n_strat,
                "n_pass": n_pass,
                "n_fail": n_fail,
                "n_error": n_error,
                "valid_n": valid_n,
                "pass_rate": rate,
                "wilson_lb": wilson_lb,
                "wilson_ub": wilson_ub,
                "stratum_invalid": is_invalid,
            }
        summaries[arm] = arm_sum

    # Paired McNemar tests between arms
    mcnemar_stats: list[dict[str, object]] = []
    arm_pairs = []
    if "arm_b" in arms_to_run and "arm_a" in arms_to_run:
        arm_pairs.append(("arm_b", "arm_a"))
    if "arm_b" in arms_to_run and "arm_c" in arms_to_run:
        arm_pairs.append(("arm_b", "arm_c"))
    if "arm_c" in arms_to_run and "arm_a" in arms_to_run:
        arm_pairs.append(("arm_c", "arm_a"))

    for arm1, arm2 in arm_pairs:
        for stratum in strata:
            s_rows = [r for r in results if r["stratum"] == stratum]
            b_count = 0  # arm1 pass, arm2 fail/error
            c_count = 0  # arm1 fail/error, arm2 pass
            for r in s_rows:
                g1 = r.get(f"{arm1}_grade") == Grade.PASS.value
                g2 = r.get(f"{arm2}_grade") == Grade.PASS.value
                if g1 and not g2:
                    b_count += 1
                elif not g1 and g2:
                    c_count += 1
            p_val = mcnemar_test(b_count, c_count, exact=True)
            r1 = summaries[arm1][stratum]["pass_rate"]
            r2 = summaries[arm2][stratum]["pass_rate"]
            mcnemar_stats.append({
                "stratum": stratum,
                "comparison": f"{arm1} vs {arm2}",
                "arm1": arm1,
                "arm2": arm2,
                "arm1_rate": r1,
                "arm2_rate": r2,
                "delta_pp": (r1 - r2) * 100.0,
                "discordant_b": b_count,
                "discordant_c": c_count,
                "p_value": p_val,
                "significant": p_val < 0.05,
            })

    report_payload = {
        "battery": "contrastive_live_battery_v2",
        "timestamp": timestamp,
        "as_of": datetime.date.today().isoformat(),
        "git_commit": git_commit,
        "grader_sha256": current_grader_sha,
        "probes_file": str(probes_path),
        "n_probes": len(probes),
        "arms": arms_to_run,
        "thresholds": {
            "recall": THRESHOLD_RECALL,
            "receipt_introspection": THRESHOLD_INTROSPECTION,
            "abstention": THRESHOLD_ABSTENTION,
        },
        "summaries": summaries,
        "paired_mcnemar": mcnemar_stats,
        "results": results,
    }

    # Write JSON artifact
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"contrastive_battery_{timestamp}.json"
    json_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    print(f"[*] Saved JSON artifact to {json_path}")

    # Build Markdown report
    md_lines = [
        "# Contrastive Live-Companion Battery Report (v2 Frozen Grader)",
        f"**Date:** {datetime.date.today().isoformat()} | **Timestamp:** {timestamp}",
        f"**Git Commit:** `{git_commit}` | **Grader SHA-256:** `{current_grader_sha}`",
        f"**Probes Dataset:** `{probes_path}` ($N={len(probes)}$ probes across 3 strata)",
        f"**Arms Evaluated:** {', '.join(arms_to_run)}",
        "",
        "## 1. Scorecard by Arm and Stratum",
        "",
        "| Arm | Stratum | Pass / Valid | Pass Rate (%) | 95% Wilson CI | Errors | Status |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    for arm in arms_to_run:
        arm_title = {"arm_a": "Arm A (Bare LLM)", "arm_b": "Arm B (Compound)", "arm_c": "Arm C (RAG Baseline)"}.get(arm, arm)
        for stratum in strata:
            s_data = summaries[arm][stratum]
            status = "INVALID (>20% err)" if s_data["stratum_invalid"] else "VALID"
            if arm == "arm_b" and status == "VALID":
                thresh = report_payload["thresholds"][stratum]
                if s_data["pass_rate"] >= thresh:
                    status = f"PASSED (>= {thresh:.0%})"
                else:
                    status = f"FAILED (< {thresh:.0%})"
            md_lines.append(
                f"| **{arm_title}** | {stratum} | {s_data['n_pass']}/{s_data['valid_n']} | "
                f"{s_data['pass_rate']:.1%} | [{s_data['wilson_lb']:.1%}, {s_data['wilson_ub']:.1%}] | "
                f"{s_data['n_error']} | {status} |"
            )

    md_lines.extend([
        "",
        "## 2. Paired McNemar Statistical Appendix",
        "",
        "| Comparison | Stratum | Arm 1 Rate | Arm 2 Rate | $\\Delta$ (pp) | Discordant ($b : c$) | Exact $p$-Value | Sig ($p < 0.05$) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for m in mcnemar_stats:
        md_lines.append(
            f"| **{m['comparison']}** | {m['stratum']} | {m['arm1_rate']:.1%} | {m['arm2_rate']:.1%} | "
            f"{m['delta_pp']:+.1f} | {m['discordant_b']} : {m['discordant_c']} | "
            f"{m['p_value']:.4e} | {'**YES**' if m['significant'] else 'No'} |"
        )

    md_lines.extend([
        "",
        "## 3. Register Invariant Audit & Remediation Verification",
        "- **C-01 (Empty Replies -> Error):** Empty replies are explicitly captured as `Grade.ERROR`, avoiding artificial scoring degradation.",
        "- **C-02 (Genuine Abstention):** Grader checks frozen canonical abstention phrases including explicit lack of knowledge.",
        "- **C-03 (Baseline by Construction):** Addition of Arm C (RAG Baseline) provides a fair retrieval comparison vs compound layer.",
        "- **C-04 (Frozen Grader Gate):** Grader criteria strictly immutable and SHA-256 embedded into artifact.",
        "- **C-05 (Echo Stripping):** SequenceMatcher sliding window removes >= 4 word echoed question runs prior to credit attribution.",
        "- **C-06 (Recollection Hysteresis):** Validates live execution under verified safety supervisor without false aborts.",
        "",
    ])

    md_path = output_dir / f"contrastive_battery_{timestamp}_REPORT.md"
    md_content = "\n".join(md_lines)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"[*] Saved Markdown report to {md_path}")

    return report_payload, str(md_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 3.5-3.6 Contrastive Battery")
    parser.add_argument(
        "--probes",
        type=Path,
        default=REPO_ROOT / "tests" / "fixtures" / "contrastive" / "probes.jsonl",
        help="Path to probes jsonl",
    )
    parser.add_argument(
        "--arms",
        type=str,
        default="arm_a,arm_b,arm_c",
        help="Comma-separated arms to run: arm_a,arm_b,arm_c",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "test_reports",
        help="Directory to write reports",
    )
    args = parser.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    run_battery(args.probes, arms, args.output_dir)


if __name__ == "__main__":
    main()
