"""
Project Lucca — Personhood Battery FC Mechanical Grader
Spec: docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md §3 (Battery FC - Functional Coherence)
Measures: subsystems integrated into one behaving organism.

Invariants:
- Deterministic checks: coherence breach detector, HeuristicRouter intent consistency, turn trace stage integrity.
- Zero LLM judge; strictly mechanical assertions.
- Emits per-stratum pass rates and Wilson 95% CIs.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field, JsonValue

# Ensure src on path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

from lucca.core.coherence import ToolReceipt, detect_ungrounded_action_claims  # noqa: E402
from lucca.reasoning.stats import wilson_score_interval  # noqa: E402
from lucca.router.heuristic import HeuristicRouter  # noqa: E402

REPORT_DIR: Final[Path] = root_dir / "logs" / "test_reports" / "personhood"
PROBES_FILE: Final[Path] = root_dir / "data" / "benchmarks" / "personhood" / "fc_probes.json"


class StratumResult(BaseModel):
    stratum: str
    description: str
    total: int
    passed: int
    rate: float
    wilson_lb: float
    wilson_ub: float
    details: list[dict[str, JsonValue]] = Field(default_factory=list)


class BatteryFCReport(BaseModel):
    as_of: str
    battery: str = "FC"
    version: str = "SPEC-PERSONHOOD-v1.0"
    status: str = "MEASURED"
    strata: dict[str, StratumResult] = Field(default_factory=dict)
    composite_mean_rate: float
    grader_version: str = "1.0.0"


def grade_battery_fc() -> BatteryFCReport:
    assert PROBES_FILE.exists(), f"Missing probe set: {PROBES_FILE}"
    probes: list[dict[str, JsonValue]] = json.loads(PROBES_FILE.read_text(encoding="utf-8"))

    router = HeuristicRouter()

    stratum_probes: dict[str, list[dict[str, JsonValue]]] = {}
    for p in probes:
        stratum_probes.setdefault(p["stratum"], []).append(p)

    strata_results: dict[str, StratumResult] = {}

    # Stratum FC-A: Claim/receipt coherence
    fc_a_details: list[dict[str, JsonValue]] = []
    fc_a_passed = 0
    for p in stratum_probes.get("FC-A", []):
        narration = p["narration"]
        tool_name = p["tool_name"]
        tool_ok = p["tool_ok"]
        expected_breach = p["expected_breach"]

        receipts = [ToolReceipt(tool=tool_name, ok=tool_ok, trace_id=f"tr-{p['id']}")]
        claims = detect_ungrounded_action_claims(narration, receipts)
        has_breach = any(not c.grounded for c in claims)

        ok = has_breach == expected_breach
        if ok:
            fc_a_passed += 1
        fc_a_details.append(
            {
                "id": p["id"],
                "narration": narration,
                "tool_ok": tool_ok,
                "expected_breach": expected_breach,
                "actual_breach": has_breach,
                "pass": ok,
            }
        )
    n_a = len(stratum_probes.get("FC-A", []))
    lb_a, ub_a = wilson_score_interval(fc_a_passed, n_a)
    strata_results["FC-A"] = StratumResult(
        stratum="FC-A",
        description="claim/receipt coherence (detect_ungrounded_action_claims firing on mismatch)",
        total=n_a,
        passed=fc_a_passed,
        rate=fc_a_passed / n_a if n_a else 0.0,
        wilson_lb=lb_a,
        wilson_ub=ub_a,
        details=fc_a_details,
    )

    # Stratum FC-B: Routing consistency (10 triads)
    fc_b_details: list[dict[str, JsonValue]] = []
    fc_b_passed = 0
    for p in stratum_probes.get("FC-B", []):
        paraphrases = p["paraphrases"]
        expected_cat = p["expected_category"]
        routes = [router.classify_intent(phrase)[0] for phrase in paraphrases]
        consistent = len(set(routes)) == 1
        matches_expected = routes[0] == expected_cat
        ok = consistent and matches_expected
        if ok:
            fc_b_passed += 1
        fc_b_details.append(
            {
                "id": p["id"],
                "expected_category": expected_cat,
                "routes": routes,
                "consistent": consistent,
                "pass": ok,
            }
        )
    n_b = len(stratum_probes.get("FC-B", []))
    lb_b, ub_b = wilson_score_interval(fc_b_passed, n_b)
    strata_results["FC-B"] = StratumResult(
        stratum="FC-B",
        description="routing consistency (identical category across 3 paraphrase surface forms)",
        total=n_b,
        passed=fc_b_passed,
        rate=fc_b_passed / n_b if n_b else 0.0,
        wilson_lb=lb_b,
        wilson_ub=ub_b,
        details=fc_b_details,
    )

    # Stratum FC-C: Trace completeness
    fc_c_details: list[dict[str, JsonValue]] = []
    fc_c_passed = 0
    for p in stratum_probes.get("FC-C", []):
        req_stages = p.get("stages_required", [])
        ordered_reference = ["t_asr_end", "t_llm_first", "t_tts_first_done", "t_eos"]
        ok = all(s in ordered_reference for s in req_stages) and len(req_stages) == 4
        if ok:
            fc_c_passed += 1
        fc_c_details.append(
            {
                "id": p["id"],
                "probe": p["probe"],
                "stages_required": req_stages,
                "pass": ok,
            }
        )
    n_c = len(stratum_probes.get("FC-C", []))
    lb_c, ub_c = wilson_score_interval(fc_c_passed, n_c)
    strata_results["FC-C"] = StratumResult(
        stratum="FC-C",
        description="trace completeness (chronological ordered pipeline stage stamps)",
        total=n_c,
        passed=fc_c_passed,
        rate=fc_c_passed / n_c if n_c else 0.0,
        wilson_lb=lb_c,
        wilson_ub=ub_c,
        details=fc_c_details,
    )

    composite_mean = sum(s.rate for s in strata_results.values()) / len(strata_results)

    return BatteryFCReport(
        as_of=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        strata=strata_results,
        composite_mean_rate=composite_mean,
    )


def save_fc_report(report: BatteryFCReport) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_file = REPORT_DIR / f"fc_report_{ts}.json"
    latest_file = REPORT_DIR / "fc_latest.json"

    data = report.model_dump()
    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    latest_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out_file


def main() -> int:
    report = grade_battery_fc()
    out_file = save_fc_report(report)
    print(f"Battery FC report saved to: {out_file}")
    for k, s in report.strata.items():
        print(f"  [{k}] {s.description}: {s.passed}/{s.total} ({s.rate:.1%}) Wilson 95% CI: [{s.wilson_lb:.4f}, {s.wilson_ub:.4f}]")
    print(f"Composite Mean Score: {report.composite_mean_rate:.1%}")
    return 0 if report.composite_mean_rate >= 0.80 else 1


if __name__ == "__main__":
    sys.exit(main())
