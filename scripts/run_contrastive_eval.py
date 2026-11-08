"""
Project Lucca — High-Power Contrastive Companion Battery v2 Runner (WO-43 Phase 5)
Spec: plans/wo43_refactor_and_power/05_PHASE5_STATISTICAL_POWER_EXPANSION_SPEC.md §3.1

Evaluates all 3 arms across N=300 probes (100 Recall, 100 Introspection, 100 Abstention):
  - Arm A (Bare LLM):      Direct chat completion against llama-server (no memory, no tools).
  - Arm B (Compound):      Full Lucca turn pipeline via HW Orchestrator with per-probe DB isolation.
  - Arm C (RAG Baseline):  Top-5 hybrid retrieval (k=5, include_superseded=True) injected into prompt.

Uses the frozen contrastive_grader.py (SHA-256 f015710f...27c2) and computes per-stratum
exact 95% Wilson CIs and paired exact McNemar p-values with Holm-Bonferroni correction.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lucca.core.config import get_config  # noqa: E402
from lucca.core.schemas import RetrievalQuery  # noqa: E402
from lucca.eval.contrastive_grader import (  # noqa: E402
    THRESHOLD_ABSTENTION,
    THRESHOLD_INTROSPECTION,
    THRESHOLD_RECALL,
    Grade,
    grade_probe,
    grader_sha256,
    stratum_invalid,
)
from lucca.reasoning.stats import mcnemar_test, wilson_score_interval  # noqa: E402
from tests.test_a1_live_hw import (  # noqa: E402
    _invoke_text_turn,
    _make_hw_orchestrator,
    _seed_a1_history,
)

EXPECTED_GRADER_SHA: Final[str] = "e9ce6f5245561b605c7578ebf31d3fed9c2fdaeb1f27f8a91dba799446fd5e0d"

LLM_ONLY_SYSTEM_PROMPT: Final[str] = (
    "You are a helpful desktop assistant. Answer the user's question directly and concisely."
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def check_llm_server(client: httpx.Client, base_url: str) -> None:
    try:
        resp = client.get(f"{base_url}/health", timeout=5.0)
        if resp.status_code != 200:
            raise RuntimeError(f"llama-server unhealthy at {base_url} (HTTP {resp.status_code})")
    except Exception as exc:
        raise RuntimeError(f"llama-server unreachable at {base_url}: {exc}") from exc


def query_llm_direct(
    client: httpx.Client,
    base_url: str,
    system_prompt: str,
    user_question: str,
) -> str:
    """Bare non-streaming chat completion with enable_thinking=False."""
    try:
        resp = client.post(
            f"{base_url}/v1/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_question},
                ],
                "temperature": 0.0,
                "max_tokens": 160,
                "seed": 42,
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
        return str(choices[0].get("message", {}).get("content", "")).strip()
    except Exception as exc:
        print(f"    [!] Error querying direct LLM: {exc}")
        return ""


def holm_bonferroni(p_values: list[float]) -> list[float]:
    """Computes Holm-Bonferroni step-down multiplicity-adjusted p-values."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, (orig_idx, p_val) in enumerate(indexed):
        adj = min(1.0, p_val * float(m - rank))
        running_max = max(running_max, adj)
        adjusted[orig_idx] = running_max
    return adjusted


def run_contrastive_evaluation(
    battery_path: Path,
    output_path: Path,
    arms_to_run: list[str],
    resume: bool = True,
) -> dict[str, object]:
    current_grader_sha = grader_sha256()
    print(f"[*] Verifying frozen contrastive grader SHA: {current_grader_sha}")
    if current_grader_sha != EXPECTED_GRADER_SHA:
        raise ValueError(
            f"Grader hash mismatch! Expected {EXPECTED_GRADER_SHA}, got {current_grader_sha}."
        )

    cfg = get_config()
    base_url = f"http://{cfg.llm.host}:{cfg.llm.port}"

    probes = [
        json.loads(line)
        for line in battery_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    n_total = len(probes)
    print(f"[*] Loaded {n_total} probes from {battery_path}")

    existing_by_id: dict[str, dict[str, object]] = {}
    if resume and output_path.exists():
        try:
            prev_data = json.loads(output_path.read_text(encoding="utf-8"))
            prev_results = prev_data.get("results", [])
            if isinstance(prev_results, list):
                for item in prev_results:
                    if isinstance(item, dict) and "id" in item:
                        # Keep only if all requested arms have non-ERROR grades
                        if all(
                            item.get(f"{a}_grade") in (Grade.PASS.value, Grade.FAIL.value)
                            for a in arms_to_run
                        ):
                            existing_by_id[str(item["id"])] = item
            if existing_by_id:
                print(f"[*] Resuming: {len(existing_by_id)}/{n_total} probes already completed.")
        except Exception as exc:
            print(f"[!] Could not load existing checkpoint ({exc}); starting fresh.")

    git_commit = get_git_commit()
    battery_sha = sha256_file(battery_path)
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with (
        httpx.Client(timeout=90.0) as http_client,
        tempfile.TemporaryDirectory() as tmp_dir,
    ):
        print(f"[*] Checking llama-server at {base_url}...")
        check_llm_server(http_client, base_url)

        tmp_path = Path(tmp_dir)
        print("[*] Initializing HW Orchestrator and seeding memory...")
        orch, store, db = _make_hw_orchestrator(tmp_path)
        try:
            _seed_a1_history(store, db, time.time())
            with db.read_cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(memory_id), 0) FROM memories")
                max_seeded_mid = int(cur.fetchone()[0])
                cur.execute("SELECT COALESCE(MAX(created_at), 0.0) FROM provenance_envelopes")
                max_seeded_ts = float(cur.fetchone()[0])
                cur.execute(
                    "SELECT memory_id, valid_to, superseded_by, forgotten_at "
                    "FROM memories WHERE memory_id <= ?",
                    (max_seeded_mid,),
                )
                seeded_state = [(int(r[0]), r[1], r[2], r[3]) for r in cur.fetchall()]

            def _restore_seeded_state() -> None:
                orch.history.clear()
                orch.pending_spoken_updates.clear()
                orch.current_turn_receipts.clear()
                getattr(orch, "current_turn_historical_receipts", []).clear()
                orch.current_turn_tool_calls.clear()
                orch.executed_tools.clear()
                orch.prev_decision_record = None
                orch.prev_turn_ts = None
                conn = db.get_writer()
                conn.execute("PRAGMA foreign_keys = OFF")
                try:
                    for mid_s, v_to, sup_by, forg_at in seeded_state:
                        conn.execute(
                            "UPDATE memories SET valid_to = ?, superseded_by = ?, forgotten_at = ? "
                            "WHERE memory_id = ?",
                            (v_to, sup_by, forg_at, mid_s),
                        )
                    conn.execute(
                        "UPDATE memories SET superseded_by = NULL WHERE memory_id > ?",
                        (max_seeded_mid,),
                    )
                    conn.execute("DELETE FROM vec_memories WHERE memory_id > ?", (max_seeded_mid,))
                    conn.execute(
                        "DELETE FROM memory_sources WHERE memory_id > ?", (max_seeded_mid,)
                    )
                    conn.execute("DELETE FROM memories WHERE memory_id > ?", (max_seeded_mid,))
                    conn.execute(
                        "DELETE FROM provenance_envelopes WHERE created_at > ?",
                        (max_seeded_ts + 0.001,),
                    )
                    conn.execute(
                        "DELETE FROM decision_labels WHERE decision_id IN "
                        "(SELECT decision_id FROM decisions WHERE ts > ?)",
                        (max_seeded_ts + 0.001,),
                    )
                    conn.execute("DELETE FROM decisions WHERE ts > ?", (max_seeded_ts + 0.001,))
                    conn.commit()
                finally:
                    conn.execute("PRAGMA foreign_keys = ON")

            results: list[dict[str, object]] = []
            t0 = time.time()

            for idx, probe in enumerate(probes, 1):
                pid = str(probe["id"])
                if pid in existing_by_id:
                    cached = dict(existing_by_id[pid])
                    q_c = str(cached.get("question", probe["question"]))
                    m_c = str(cached.get("expect_mode", probe["expect_mode"]))
                    raw_e_c = cached.get("expect_any", probe.get("expect_any", []))
                    e_c = [str(x) for x in raw_e_c] if isinstance(raw_e_c, list) else []
                    for arm_k in arms_to_run:
                        rep_k = str(cached.get(f"{arm_k}_reply", ""))
                        g_k, r_k = grade_probe(m_c, e_c, q_c, rep_k)
                        cached[f"{arm_k}_grade"] = g_k.value
                        cached[f"{arm_k}_pass"] = g_k == Grade.PASS
                        cached[f"{arm_k}_reason"] = r_k
                    results.append(cached)
                    continue

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

                # Arm A: Bare LLM
                if "arm_a" in arms_to_run:
                    reply_a = query_llm_direct(
                        http_client, base_url, LLM_ONLY_SYSTEM_PROMPT, question
                    )
                    grade_a, reason_a = grade_probe(expect_mode, expect_any, question, reply_a)
                    row["arm_a_reply"] = reply_a
                    row["arm_a_grade"] = grade_a.value
                    row["arm_a_pass"] = grade_a == Grade.PASS
                    row["arm_a_reason"] = reason_a

                # Arm B: Compound Orchestrator (with clean per-probe seeded state)
                if "arm_b" in arms_to_run:
                    _restore_seeded_state()
                    reply_b = _invoke_text_turn(orch, question, f"contrastive-b-{pid}")
                    grade_b, reason_b = grade_probe(expect_mode, expect_any, question, reply_b)
                    row["arm_b_reply"] = reply_b
                    row["arm_b_grade"] = grade_b.value
                    row["arm_b_pass"] = grade_b == Grade.PASS
                    row["arm_b_reason"] = reason_b

                # Arm C: RAG Baseline (top-5 hybrid retrieval, include_superseded=True)
                if "arm_c" in arms_to_run:
                    _restore_seeded_state()
                    q = RetrievalQuery(
                        query_text=question,
                        k=5,
                        include_superseded=True,
                    )
                    hits = store.search(q)
                    context_lines = [f"- {h.content}" for h in hits]
                    context_str = "\n".join(context_lines) if context_lines else "None."
                    rag_prompt = (
                        "You are a helpful desktop assistant. Answer the user's question directly and concisely "
                        "based on the following retrieved context. If the context does not contain the answer, "
                        "state clearly that you do not know or have no record.\n\n"
                        f"Context:\n{context_str}"
                    )
                    reply_c = query_llm_direct(http_client, base_url, rag_prompt, question)
                    grade_c, reason_c = grade_probe(expect_mode, expect_any, question, reply_c)
                    row["arm_c_reply"] = reply_c
                    row["arm_c_grade"] = grade_c.value
                    row["arm_c_pass"] = grade_c == Grade.PASS
                    row["arm_c_reason"] = reason_c

                results.append(row)
                if idx % 5 == 0 or idx == n_total:
                    elapsed = time.time() - t0
                    print(
                        f"[{idx:03d}/{n_total:03d}] {pid} ({stratum}) | "
                        f"A={row.get('arm_a_grade')} B={row.get('arm_b_grade')} C={row.get('arm_c_grade')} | "
                        f"{elapsed:.1f}s"
                    )
                    output_path.write_text(
                        json.dumps({"results": results}, indent=2), encoding="utf-8"
                    )

            elapsed_total = time.time() - t0
            print(f"[*] All {n_total} probes completed in {elapsed_total:.1f}s")
        finally:
            db.close()

    strata = ("recall", "receipt_introspection", "abstention")
    summaries: dict[str, dict[str, dict[str, object]]] = {}

    for arm in arms_to_run:
        arm_sum: dict[str, dict[str, object]] = {}
        for stratum in strata:
            s_rows = [r for r in results if r["stratum"] == stratum]
            n_strat = len(s_rows)
            n_pass = sum(1 for r in s_rows if r.get(f"{arm}_grade") == Grade.PASS.value)
            n_fail = sum(1 for r in s_rows if r.get(f"{arm}_grade") == Grade.FAIL.value)
            n_error = sum(1 for r in s_rows if r.get(f"{arm}_grade") == Grade.ERROR.value)

            is_invalid = stratum_invalid(n_error, n_strat)
            valid_n = n_strat - n_error
            rate = (n_pass / valid_n) if valid_n > 0 else 0.0
            wilson_lb, wilson_ub = (
                wilson_score_interval(n_pass, valid_n) if valid_n > 0 else (0.0, 0.0)
            )

            arm_sum[stratum] = {
                "n_total": n_strat,
                "n_pass": n_pass,
                "n_fail": n_fail,
                "n_error": n_error,
                "valid_n": valid_n,
                "pass_rate": round(rate, 4),
                "wilson_lb": round(wilson_lb, 4),
                "wilson_ub": round(wilson_ub, 4),
                "stratum_invalid": is_invalid,
            }
        summaries[arm] = arm_sum

    mcnemar_stats: list[dict[str, object]] = []
    arm_pairs: list[tuple[str, str]] = []
    if "arm_b" in arms_to_run and "arm_a" in arms_to_run:
        arm_pairs.append(("arm_b", "arm_a"))
    if "arm_b" in arms_to_run and "arm_c" in arms_to_run:
        arm_pairs.append(("arm_b", "arm_c"))
    if "arm_c" in arms_to_run and "arm_a" in arms_to_run:
        arm_pairs.append(("arm_c", "arm_a"))

    raw_p_vals: list[float] = []
    for arm1, arm2 in arm_pairs:
        for stratum in strata:
            s_rows = [r for r in results if r["stratum"] == stratum]
            b_count = 0
            c_count = 0
            for r in s_rows:
                g1 = r.get(f"{arm1}_grade") == Grade.PASS.value
                g2 = r.get(f"{arm2}_grade") == Grade.PASS.value
                if g1 and not g2:
                    b_count += 1
                elif not g1 and g2:
                    c_count += 1
            p_val = mcnemar_test(b_count, c_count, exact=True)
            raw_p_vals.append(p_val)
            r1 = float(summaries[arm1][stratum]["pass_rate"])  # type: ignore[arg-type]
            r2 = float(summaries[arm2][stratum]["pass_rate"])  # type: ignore[arg-type]
            mcnemar_stats.append(
                {
                    "stratum": stratum,
                    "comparison": f"{arm1} vs {arm2}",
                    "arm1": arm1,
                    "arm2": arm2,
                    "arm1_rate": r1,
                    "arm2_rate": r2,
                    "delta_pp": round((r1 - r2) * 100.0, 2),
                    "discordant_b": b_count,
                    "discordant_c": c_count,
                    "p_value": p_val,
                    "significant_unadjusted": p_val < 0.05,
                }
            )

    adj_p_vals = holm_bonferroni(raw_p_vals)
    for m_entry, p_adj in zip(mcnemar_stats, adj_p_vals, strict=True):
        m_entry["p_value_holm_bonferroni"] = p_adj
        m_entry["significant"] = p_adj < 0.05

    report_payload: dict[str, object] = {
        "battery": "contrastive_battery_v2_300",
        "protocol_id": "prereg-wo43-power-300",
        "timestamp": timestamp,
        "as_of": datetime.date.today().isoformat(),
        "git_commit": git_commit,
        "grader_sha256": current_grader_sha,
        "probes_file": str(battery_path.relative_to(REPO_ROOT))
        if battery_path.is_relative_to(REPO_ROOT)
        else str(battery_path),
        "probes_sha256": battery_sha,
        "n_probes": n_total,
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

    output_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    print(f"[*] Saved final JSON report to {output_path}")

    md_path = output_path.with_name(f"{output_path.stem}_REPORT.md")
    md_lines = [
        "# Contrastive Companion Battery v2 Report ($N = 300$, Frozen Grader)",
        f"**Date:** {datetime.date.today().isoformat()} | **Timestamp:** {timestamp}",
        f"**Git Commit:** `{git_commit}` | **Protocol Tag:** `prereg-wo43-power-300`",
        f"**Probes Dataset:** `{battery_path.name}` ($N={n_total}$, SHA-256 `{battery_sha}`)",
        f"**Frozen Grader SHA-256:** `{current_grader_sha}`",
        "",
        "## 1. Scorecard by Arm and Stratum ($n = 100$ per stratum)",
        "",
        "| Arm | Stratum | Pass / Valid | Pass Rate (%) | 95% Wilson CI | Errors | Status |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
    ]
    for arm in arms_to_run:
        arm_title = {
            "arm_a": "Arm A (Bare LLM)",
            "arm_b": "Arm B (Compound Lucca)",
            "arm_c": "Arm C (RAG Baseline)",
        }.get(arm, arm)
        for stratum in strata:
            s_data = summaries[arm][stratum]
            status = "INVALID (>20% err)" if s_data["stratum_invalid"] else "VALID"
            if arm == "arm_b" and status == "VALID":
                thresh = {
                    "recall": THRESHOLD_RECALL,
                    "receipt_introspection": THRESHOLD_INTROSPECTION,
                    "abstention": THRESHOLD_ABSTENTION,
                }[stratum]
                rate_val = float(s_data["pass_rate"])  # type: ignore[arg-type]
                status = (
                    f"PASSED (>= {thresh:.0%})"
                    if rate_val >= thresh
                    else f"FAILED (< {thresh:.0%})"
                )
            md_lines.append(
                f"| **{arm_title}** | {stratum} | {s_data['n_pass']}/{s_data['valid_n']} | "
                f"{float(s_data['pass_rate']):.1%} | "  # type: ignore[arg-type]
                f"[{float(s_data['wilson_lb']):.1%}, {float(s_data['wilson_ub']):.1%}] | "  # type: ignore[arg-type]
                f"{s_data['n_error']} | {status} |"
            )

    md_lines.extend(
        [
            "",
            "## 2. Paired Exact McNemar Tests (with Holm-Bonferroni Correction)",
            "",
            "| Comparison | Stratum | Arm 1 | Arm 2 | $\\Delta$ (pp) | Discordant ($b : c$) | Exact $p$ | Holm-Bonferroni $p_{\\text{adj}}$ | Sig ($p_{\\text{adj}} < 0.05$) |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for m in mcnemar_stats:
        md_lines.append(
            f"| **{m['comparison']}** | {m['stratum']} | {float(m['arm1_rate']):.1%} | "  # type: ignore[arg-type]
            f"{float(m['arm2_rate']):.1%} | {float(m['delta_pp']):+.1f} | "  # type: ignore[arg-type]
            f"{m['discordant_b']} : {m['discordant_c']} | {float(m['p_value']):.4e} | "  # type: ignore[arg-type]
            f"{float(m['p_value_holm_bonferroni']):.4e} | "  # type: ignore[arg-type]
            f"{'**YES**' if m['significant'] else 'No'} |"
        )

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"[*] Saved Markdown report to {md_path}")
    return report_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run WO-43 Phase 5 Contrastive Companion Battery v2 (N=300)"
    )
    parser.add_argument(
        "--battery",
        "--probes",
        dest="battery",
        type=Path,
        default=REPO_ROOT / "data" / "benchmarks" / "contrastive_battery_v2_300.jsonl",
        help="Path to contrastive battery v2 JSONL (N=300)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "logs" / "test_reports" / "contrastive_v2_300_results.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--arms",
        type=str,
        default="arm_a,arm_b,arm_c",
        help="Comma-separated arms to run: arm_a,arm_b,arm_c",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing checkpoint and run all probes from scratch",
    )
    args = parser.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    run_contrastive_evaluation(args.battery, args.output, arms, resume=not args.no_resume)


if __name__ == "__main__":
    main()
