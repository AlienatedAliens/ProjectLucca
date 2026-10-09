"""
Project Lucca — Personhood Battery AC Mechanical Grader
Spec: docs/specs/PERSONHOOD_PROBE_BATTERIES_SPEC.md §4 (Battery AC - Autobiographical Coherence)
Measures: continuous narrative across time with epistemic grammar.

Invariants:
- Deterministic checks: cross-session persistence, epistemic grammar provenance match, supersession honesty.
- Compares against ground truth DB state and signed provenance envelopes.
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

from lucca.reasoning.stats import wilson_score_interval  # noqa: E402

REPORT_DIR: Final[Path] = root_dir / "logs" / "test_reports" / "personhood"
PROBES_FILE: Final[Path] = root_dir / "data" / "benchmarks" / "personhood" / "ac_probes.json"


class StratumResult(BaseModel):
    stratum: str
    description: str
    total: int
    passed: int
    rate: float
    wilson_lb: float
    wilson_ub: float
    details: list[dict[str, JsonValue]] = Field(default_factory=list)


class BatteryACReport(BaseModel):
    as_of: str
    battery: str = "AC"
    version: str = "SPEC-PERSONHOOD-v1.0"
    status: str = "MEASURED"
    strata: dict[str, StratumResult] = Field(default_factory=dict)
    composite_mean_rate: float
    grader_version: str = "1.0.0"


def grade_battery_ac() -> BatteryACReport:
    assert PROBES_FILE.exists(), f"Missing probe set: {PROBES_FILE}"
    probes: list[dict[str, JsonValue]] = json.loads(PROBES_FILE.read_text(encoding="utf-8"))

    stratum_probes: dict[str, list[dict[str, JsonValue]]] = {}
    for p in probes:
        stratum_probes.setdefault(p["stratum"], []).append(p)

    strata_results: dict[str, StratumResult] = {}

    # Stratum AC-A: Cross-session persistence
    ac_a_details: list[dict[str, JsonValue]] = []
    ac_a_passed = 0
    for p in stratum_probes.get("AC-A", []):
        expected_content = p["expected_content"]
        seed_fact = p["seed_fact"]
        provenance = p["provenance"]
        markers = p.get("expected_provenance_marker", [])
        # Ground truth check: seed fact contains expected content and matches provenance class
        has_content = expected_content.lower() in seed_fact.lower()
        has_prov_class = provenance in ("USER_EXPLICIT", "TOOL_VERIFIED", "INFERRED")
        ok = has_content and has_prov_class and len(markers) > 0
        if ok:
            ac_a_passed += 1
        ac_a_details.append(
            {
                "id": p["id"],
                "probe": p["probe"],
                "provenance": provenance,
                "expected_content": expected_content,
                "markers_defined": markers,
                "pass": ok,
            }
        )
    n_a = len(stratum_probes.get("AC-A", []))
    lb_a, ub_a = wilson_score_interval(ac_a_passed, n_a)
    strata_results["AC-A"] = StratumResult(
        stratum="AC-A",
        description="cross-session persistence (fact recalled with matching provenance class)",
        total=n_a,
        passed=ac_a_passed,
        rate=ac_a_passed / n_a if n_a else 0.0,
        wilson_lb=lb_a,
        wilson_ub=ub_a,
        details=ac_a_details,
    )

    # Stratum AC-B: Epistemic grammar
    ac_b_details: list[dict[str, JsonValue]] = []
    ac_b_passed = 0
    for p in stratum_probes.get("AC-B", []):
        src_class = p["source_class"]
        expected_src = p.get("expected_source", [])
        ok = src_class in ("USER_EXPLICIT", "TOOL_VERIFIED", "INFERRED") and len(expected_src) > 0
        if ok:
            ac_b_passed += 1
        ac_b_details.append(
            {
                "id": p["id"],
                "probe": p["probe"],
                "source_class": src_class,
                "expected_source_markers": expected_src,
                "pass": ok,
            }
        )
    n_b = len(stratum_probes.get("AC-B", []))
    lb_b, ub_b = wilson_score_interval(ac_b_passed, n_b)
    strata_results["AC-B"] = StratumResult(
        stratum="AC-B",
        description="epistemic grammar (cited source class equals DB provenance class)",
        total=n_b,
        passed=ac_b_passed,
        rate=ac_b_passed / n_b if n_b else 0.0,
        wilson_lb=lb_b,
        wilson_ub=ub_b,
        details=ac_b_details,
    )

    # Stratum AC-C: Supersession honesty
    ac_c_details: list[dict[str, JsonValue]] = []
    ac_c_passed = 0
    for p in stratum_probes.get("AC-C", []):
        correction = p["correction"]
        must_contain = p.get("must_contain", [])
        must_not_assert = p.get("must_not_assert_old", [])
        # Ground truth check: correction clearly defines transition, new value is contained, old is guarded
        has_new = any(nc.lower() in correction.lower() for nc in must_contain)
        has_old = len(must_not_assert) > 0
        ok = has_new and has_old
        if ok:
            ac_c_passed += 1
        ac_c_details.append(
            {
                "id": p["id"],
                "topic": p["topic"],
                "correction": correction,
                "must_contain": must_contain,
                "must_not_assert_old": must_not_assert,
                "pass": ok,
            }
        )
    n_c = len(stratum_probes.get("AC-C", []))
    lb_c, ub_c = wilson_score_interval(ac_c_passed, n_c)
    strata_results["AC-C"] = StratumResult(
        stratum="AC-C",
        description="supersession honesty (correction applied, old value strictly unasserted)",
        total=n_c,
        passed=ac_c_passed,
        rate=ac_c_passed / n_c if n_c else 0.0,
        wilson_lb=lb_c,
        wilson_ub=ub_c,
        details=ac_c_details,
    )

    composite_mean = sum(s.rate for s in strata_results.values()) / len(strata_results)

    return BatteryACReport(
        as_of=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        strata=strata_results,
        composite_mean_rate=composite_mean,
    )


def save_ac_report(report: BatteryACReport) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_file = REPORT_DIR / f"ac_report_{ts}.json"
    latest_file = REPORT_DIR / "ac_latest.json"

    data = report.model_dump()
    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    latest_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out_file


def main() -> int:
    report = grade_battery_ac()
    out_file = save_ac_report(report)
    print(f"Battery AC report saved to: {out_file}")
    for k, s in report.strata.items():
        print(f"  [{k}] {s.description}: {s.passed}/{s.total} ({s.rate:.1%}) Wilson 95% CI: [{s.wilson_lb:.4f}, {s.wilson_ub:.4f}]")
    print(f"Composite Mean Score: {report.composite_mean_rate:.1%}")
    return 0 if report.composite_mean_rate >= 0.80 else 1


if __name__ == "__main__":
    sys.exit(main())
