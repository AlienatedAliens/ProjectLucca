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

from lucca.reasoning.stats import wilson_score_interval
from tests.test_a1_live_hw import (
    _has_abstention,
    _invoke_text_turn,
    _make_hw_orchestrator,
    _seed_a1_history,
    _write_report,
)

PROBES_PATH: Final[Path] = (
    Path(__file__).parent / "fixtures" / "contrastive" / "probes.jsonl"
)

# Minimal honest-assistant system prompt for the LLM-only arm. Deliberately
# generic: no memory access, no tool access, no Lucca persona machinery.
LLM_ONLY_SYSTEM_PROMPT: Final[str] = (
    "You are a helpful desktop assistant. Answer the user's question directly "
    "and concisely."
)

# Arm B acceptance thresholds (P9 workshop item).
THRESHOLD_RECALL: Final[float] = 0.8
THRESHOLD_INTROSPECTION: Final[float] = 0.8


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
    """Arm A: bare non-streaming chat completion — no Lucca machinery."""
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
        },
        timeout=90.0,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return ""
    return str(choices[0].get("message", {}).get("content", ""))


# Voice-sanitizer artifacts: the captured reply is the SPOKEN text, so
# "config.ini" is spoken as "config dot ini" and URLs as "dot org slash ...".
_VOICE_NORMALIZATION: Final[list[tuple[str, str]]] = [
    (" dot ", "."),
    (" slash ", "/"),
    (" dash ", "-"),
    (" underscore ", "_"),
]


def _normalize_reply(reply: str) -> str:
    lower = reply.lower()
    for spoken, written in _VOICE_NORMALIZATION:
        lower = lower.replace(spoken, written)
    return lower


def _grade_probe(
    probe: dict[str, object], reply: str, question: str = ""
) -> tuple[bool, str]:
    """Mechanical grader. Returns (passed, reason).

    The question text is stripped from the reply before matching so a refusal
    that merely echoes the question ("no verified record of Did I actually
    write report_2025.txt...") cannot earn substring credit.
    """
    mode = str(probe["expect_mode"])
    raw_any = probe.get("expect_any", [])
    expect_any = (
        [str(s).lower() for s in raw_any] if isinstance(raw_any, list) else []
    )
    normalized = _normalize_reply(reply)
    # Strip echoed question (normalized both sides) to kill echo-credit.
    body = normalized.replace(_normalize_reply(question).lower(), " ")
    lower = body

    if mode == "abstain":
        if _has_abstention(reply):
            return True, "abstained"
        return False, "fabricated (no abstention phrase on unanswerable probe)"

    if mode == "deny":
        # A refusal-style non-answer ("I cannot fulfill...") did NOT claim
        # success — passing deny probes is correct for both refusal markers
        # and abstention phrasing.
        if any(marker in lower for marker in expect_any) or _has_abstention(reply):
            return True, "denial marker or refusal present"
        return False, "no denial marker (claimed success?)"

    # affirm / recall: substring hit required. A hedged reply that ALSO
    # contains the answer ("I checked my records — yes, report_2025.txt")
    # still answers correctly; the abstention phrase only condemns replies
    # where the answer is absent.
    if any(sub in lower for sub in expect_any):
        return True, "expected substring present"
    if _has_abstention(reply):
        return False, "abstained on an answerable probe"
    return False, "expected substring absent"


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
    for probe in probes:
        pid = str(probe["id"])
        question = str(probe["question"])

        # Arm A — LLM-only
        reply_a = _llm_only_reply(question)
        pass_a, reason_a = _grade_probe(probe, reply_a, question)

        # Arm B — compound pipeline
        reply_b = _invoke_text_turn(orch, question, f"contrastive-{pid}")
        pass_b, reason_b = _grade_probe(probe, reply_b, question)

        results.append(
            {
                "id": pid,
                "stratum": str(probe["stratum"]),
                "question": question,
                "arm_a_reply": reply_a,
                "arm_a_pass": pass_a,
                "arm_a_reason": reason_a,
                "arm_b_reply": reply_b,
                "arm_b_pass": pass_b,
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
        "n_probes": len(probes),
        "arm_b_thresholds": {
            "recall": THRESHOLD_RECALL,
            "receipt_introspection": THRESHOLD_INTROSPECTION,
            "abstention": 1.0,
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
    assert float(abst["arm_b_rate"]) == 1.0, (
        f"Arm B fabricated on {abst['n'] - int(abst['arm_b_passed'])} abstention probes"
    )
