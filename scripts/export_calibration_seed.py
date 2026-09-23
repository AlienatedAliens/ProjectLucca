"""
Project Lucca — Calibration Seed Exporter
WO-15 Phase 4.1 (§6.1)
Exports calibration decisions to tests/fixtures/router/calibration_seed.jsonl
either from live memory.sqlite (if >= 60 labelled rows exist) or by routing
tests/fixtures/router/router_fixtures.jsonl through an unguarded HeuristicRouter.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from lucca.memory.db import DatabaseManager
from lucca.router.calibration import load_labelled_decisions
from lucca.router.heuristic import HeuristicRouter

LIVE_DB_PATHS = [
    Path("C:/ProjectLucca/data/memory.sqlite"),
    Path("data/memory.sqlite"),
]

ROUTER_FIXTURES_PATH = Path("tests/fixtures/router/router_fixtures.jsonl")
SEED_OUTPUT_PATH = Path("tests/fixtures/router/calibration_seed.jsonl")

RULE_INTENTS = frozenset({"launch_app", "file_read", "file_write", "web_fetch"})


def main() -> None:
    SEED_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    iso_date = datetime.datetime.now(datetime.UTC).isoformat()

    # 1. Check live DB candidates
    live_db: DatabaseManager | None = None
    for p in LIVE_DB_PATHS:
        if p.exists():
            try:
                db_candidate = DatabaseManager(p)
                probs, labels, raw = load_labelled_decisions(db_candidate)
                if len(labels) >= 60:
                    live_db = db_candidate
                    break
            except Exception:  # noqa: BLE001
                continue

    if live_db is not None:
        probs, labels, raw = load_labelled_decisions(live_db)
        n = len(labels)
        header = {"_provenance": f"exported from live data/memory.sqlite on {iso_date}, n={n}"}
        lines = [json.dumps(header)]
        for r in raw:
            row_data = {
                "decision_id": r.get("decision_id", ""),
                "transcript": r.get("transcript", ""),
                "intent": r.get("intent", ""),
                "action": r.get("action", ""),
                "probabilities": r.get("probabilities", {}),
                "tool_ok": r.get("tool_ok", 1),
                "user_interrupted": r.get("user_interrupted", 0),
                "fallback_applied": r.get("fallback_applied", 0),
            }
            lines.append(json.dumps(row_data))
        SEED_OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Exported {n} rows from live DB. Header: {header}")
        return

    # 2. Otherwise generate synthetically from router_fixtures.jsonl
    router = HeuristicRouter()
    fixture_lines = [
        line.strip()
        for line in ROUTER_FIXTURES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records: list[dict[str, object]] = []
    for idx, f_line in enumerate(fixture_lines):
        f = json.loads(f_line)
        transcript = f["transcript"]
        expected_intent = f["expected_intent"]
        has_rule = expected_intent in RULE_INTENTS
        if has_rule:
            act = "RULE"
        elif expected_intent == "clarify":
            act = "CLARIFY"
        else:
            act = "LLM"

        dec = router.route(transcript, has_registered_rule=has_rule)
        records.append(
            {
                "decision_id": f"seed-synth-{idx:03d}",
                "transcript": transcript,
                "intent": expected_intent,
                "action": act,
                "probabilities": dec.probabilities,
                "tool_ok": 1,
                "user_interrupted": 0,
                "fallback_applied": 0,
            }
        )

    n = len(records)
    header = {
        "_provenance": (
            f"synthetic: router_fixtures.jsonl routed through unguarded "
            f"HeuristicRouter on {iso_date}, n={n}"
        )
    }
    out_lines = [json.dumps(header)]
    for r in records:
        out_lines.append(json.dumps(r))

    SEED_OUTPUT_PATH.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Generated {n} synthetic rows from router_fixtures. Header: {header}")


if __name__ == "__main__":
    main()
