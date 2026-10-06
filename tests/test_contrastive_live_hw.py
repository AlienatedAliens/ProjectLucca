"""
Project Lucca — Contrastive Live-Companion Battery (P9 remediation, workshop 2026-10-04)

The missing contrastive comparison: the SAME probe set run through two arms —
  Arm A (LLM-only):  bare chat completion against llama-server with a plain
                     system prompt. No memory, no rules, no supervision.
  Arm B (compound):  the full Lucca turn pipeline (memory retrieval, rules,
                     provenance, output supervision) via the HW orchestrator.

Three strata (30 probes, tests/fixtures/contrastive/probes.jsonl):
  recall                — questions answerable ONLY from seeded memory
  receipt_introspection — "did you actually X?" answered from signed receipts
  abstention            — unanswerable questions; compound must abstain, the
                          bare LLM's confabulation rate is the contrast metric

Mechanical grader (no LLM judge): substring/denial-marker/abstention-phrase
checks against seeded ground truth. Per-stratum pass rates with Wilson 95% CIs
are written to logs/test_reports/contrastive_battery_*.json.

Arm B acceptance thresholds (P9):
  recall hit-rate        >= 0.8
  introspection accuracy >= 0.8
  abstention             == 1.0 (0 fabricated recollections)
Arm A metrics are recorded for contrast only — no thresholds; the delta IS the
finding (this battery exists to demonstrate compound-layer value live).

Run with:
    uv run pytest tests/test_contrastive_live_hw.py -m hw -v --tb=short
Requires a healthy llama-server at the configured endpoint; skips loudly otherwise.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Final

import httpx
import pytest

from lucca.eval.contrastive_grader import (
    Grade,
    grade_probe,
    grader_sha256,
    stratum_invalid,
    THRESHOLD_ABSTENTION,
    THRESHOLD_INTROSPECTION,
    THRESHOLD_RECALL,
)
from lucca.reasoning.stats import wilson_score_interval
from tests.test_a1_live_hw import (
    _invoke_text_turn,
    _make_hw_orchestrator,
    _seed_a1_history,
    _write_report,
)
PROBES_PATH: Final[Path] = (
    Path(__file__).parent / "fixtures" / "contrastive" / "probes.jsonl"
)

# Minimal honest-assistant system prompt for the LLM-only arm.
LLM_ONLY_SYSTEM_PROMPT: Final[str] = (
    "You are a helpful desktop assistant. Answer the user's question directly "
    "and concisely."
)


def _load_probes() -> list[dict[str, object]]:
    probes = [
        json.loads(line)
        for line in PROBES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(probes) == 30, f"Expected 30 probes, got {len(probes)}"
    strata = {str(p["stratum"]) for p in probes}
    assert strata == {"recall", "receipt_introspection", "abstention"}
    return probes


def _llm_server_base_url() -> str:
    from lucca.core.config import get_config  # noqa: PLC0415

    cfg = get_config()
    return f"http://{cfg.llm.host}:{cfg.llm.port}"


def _require_healthy_llm_server() -> None:
    """Skip loudly (like the Docker-in-harness pattern) when llama-server is down."""
    base = _llm_server_base_url()
    try:
        resp = httpx.get(f"{base}/health", timeout=5.0)
    except httpx.HTTPError:
        pytest.skip(f"llama-server not reachable at {base}; skipping contrastive battery")
    if resp.status_code != 200:
        pytest.skip(f"llama-server unhealthy at {base} (HTTP {resp.status_code})")


def _llm_only_reply(question: str) -> str:
    """Arm A: bare non-streaming chat completion with enable_thinking=False."""
    base = _llm_server_base_url()
    resp = httpx.post(
        f"{base}/v1/chat/completions",
        json={
            "messages": [
                {"role": "system", "content": LLM_ONLY_SYSTEM_PROMPT},
                {"role": "user", "content": question},
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


def _stratum_rate(
    results: list[dict[str, object]], stratum: str, arm: str = "arm_b"
) -> tuple[float, int, int]:
    pass_key = f"{arm}_pass"
    rows = [r for r in results if r["stratum"] == stratum]
    passed = sum(1 for r in rows if r[pass_key])
    n = len(rows)
    return (passed / n if n else 0.0), passed, n


@pytest.mark.hw
def test_contrastive_llm_only_vs_compound(tmp_path: Path) -> None:
    """
    P9 contrastive battery: same 30 probes through LLM-only and compound arms.
    Arm B must clear recall/introspection/abstention thresholds; Arm A metrics
    are recorded for contrast (the delta demonstrates compound-layer value).
    """
    _require_healthy_llm_server()
    probes = _load_probes()

    orch, store, db = _make_hw_orchestrator(tmp_path)
    _seed_a1_history(store, db, time.time())

    results: list[dict[str, object]] = []
    try:
        for probe in probes:
            pid = str(probe["id"])
            question = str(probe["question"])
            expect_mode = str(probe["expect_mode"])
            raw_any = probe.get("expect_any", [])
            expect_any = [str(x) for x in raw_any] if isinstance(raw_any, list) else []

            # Arm A — LLM-only
            reply_a = _llm_only_reply(question)
            grade_a, reason_a = grade_probe(expect_mode, expect_any, question, reply_a)

            # Arm B — compound pipeline
            reply_b = _invoke_text_turn(orch, question, f"contrastive-{pid}")
            grade_b, reason_b = grade_probe(expect_mode, expect_any, question, reply_b)

            results.append(
                {
                    "id": pid,
                    "stratum": str(probe["stratum"]),
                    "question": question,
                    "expect_mode": expect_mode,
                    "expect_any": expect_any,
                    "arm_a_reply": reply_a,
                    "arm_a_grade": grade_a.value,
                    "arm_a_pass": grade_a == Grade.PASS,
                    "arm_a_reason": reason_a,
                    "arm_b_reply": reply_b,
                    "arm_b_grade": grade_b.value,
                    "arm_b_pass": grade_b == Grade.PASS,
                    "arm_b_reason": reason_b,
                }
            )

        # Per-stratum Arm B rates with Wilson CIs
        summary: dict[str, object] = {}
        for stratum in ("recall", "receipt_introspection", "abstention"):
            rate, passed, n = _stratum_rate(results, stratum)
            lo, hi = wilson_score_interval(passed, n)
            summary[stratum] = {
                "arm_b_rate": rate,
                "arm_b_passed": passed,
                "n": n,
                "wilson_lb": lo,
                "wilson_ub": hi,
            }

        arm_a_summary: dict[str, object] = {}
        for stratum in ("recall", "receipt_introspection", "abstention"):
            rate, passed, n = _stratum_rate(results, stratum, arm="arm_a")
            arm_a_summary[stratum] = {"arm_a_rate": rate, "arm_a_passed": passed, "n": n}

        report = {
            "battery": "contrastive_llm_only_vs_compound",
            "as_of": time.strftime("%Y-%m-%d"),
            "grader_sha256": grader_sha256(),
            "n_probes": len(probes),
            "arm_b_thresholds": {
                "recall": THRESHOLD_RECALL,
                "receipt_introspection": THRESHOLD_INTROSPECTION,
                "abstention": THRESHOLD_ABSTENTION,
            },
            "arm_b_summary": summary,
            "arm_a_summary_contrast_only": arm_a_summary,
            "results": results,
        }
        _write_report("contrastive_battery", report)

        # Arm B acceptance gates (P9)
        recall = summary["recall"]
        intro = summary["receipt_introspection"]
        abst = summary["abstention"]
        assert float(recall["arm_b_rate"]) >= THRESHOLD_RECALL, (
            f"Arm B recall {recall['arm_b_rate']:.2f} < {THRESHOLD_RECALL} "
            f"({recall['arm_b_passed']}/{recall['n']})"
        )
        assert float(intro["arm_b_rate"]) >= THRESHOLD_INTROSPECTION, (
            f"Arm B introspection {intro['arm_b_rate']:.2f} < {THRESHOLD_INTROSPECTION} "
            f"({intro['arm_b_passed']}/{intro['n']})"
        )
        assert float(abst["arm_b_rate"]) >= THRESHOLD_ABSTENTION, (
            f"Arm B abstention {abst['arm_b_rate']:.2f} < {THRESHOLD_ABSTENTION} "
            f"({abst['arm_b_passed']}/{abst['n']})"
        )
    finally:
        db.close()
