"""Deterministic stratified item selector for WO-45 Gate G4 live v3 evaluation (RM-5, `REVIEW_G4.md:74-76`).

Draws ITEMS_PER_CELL=11 items uniformly at random without replacement from each of the 12
(stratum, topology) cells in `data/benchmarks/web_evidentiary_burden_360.jsonl` AFTER excluding
all 132 items used in Gate G4 v2 (`logs/test_reports/wo45/live_v2_selected_items.json`).
Zero conditioning on any model or classifier output.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "data" / "benchmarks" / "web_evidentiary_burden_360.jsonl"
V2_SELECTED_PATH = REPO_ROOT / "logs" / "test_reports" / "wo45" / "live_v2_selected_items.json"
OUT_PATH = REPO_ROOT / "logs" / "test_reports" / "wo45" / "live_v3_selected_items.json"

SEED = 20261112
ITEMS_PER_CELL = 11  # 12 cells * 11 = 132 fresh items (19 non-v2 items available per cell -> 0 v2 overlap)
STRATA = ("LOW", "MEDIUM", "HIGH")
TOPOLOGIES = ("1_source", "2_source", "3_source", "disputed")


def select_v3_items() -> dict[str, object]:
    v2_data = json.loads(V2_SELECTED_PATH.read_text(encoding="utf-8"))
    v2_ids = set(v2_data["selected_probe_ids"])

    rows = [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_cell_fresh: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        pid = str(row["probe_id"])
        if pid in v2_ids:
            continue
        cell = (str(row["stratum"]), str(row["topology"]))
        by_cell_fresh.setdefault(cell, []).append(row)

    rng = random.Random(SEED)
    selected_ids: list[str] = []
    overlap_v2_ids: list[str] = []
    by_cell_ids: dict[str, list[str]] = {}

    for st in STRATA:
        for top in TOPOLOGIES:
            pool = sorted(by_cell_fresh[(st, top)], key=lambda r: str(r["probe_id"]))
            if len(pool) < ITEMS_PER_CELL:
                raise RuntimeError(f"Expected >= {ITEMS_PER_CELL} fresh items in {(st, top)}, got {len(pool)}")
            rng.shuffle(pool)
            chosen = sorted(pool[:ITEMS_PER_CELL], key=lambda r: str(r["probe_id"]))
            ids = [str(r["probe_id"]) for r in chosen]
            by_cell_ids[f"{st}::{top}"] = ids
            selected_ids.extend(ids)

    overlap_v2_ids = sorted(set(selected_ids) & v2_ids)
    assert len(overlap_v2_ids) == 0, f"Unexpected overlap with v2: {overlap_v2_ids}"

    payload: dict[str, object] = {
        "seed": SEED,
        "items_per_cell": ITEMS_PER_CELL,
        "n_total": len(selected_ids),
        "n_disputed": sum(len(by_cell_ids[f"{st}::disputed"]) for st in STRATA),
        "source_corpus": "data/benchmarks/web_evidentiary_burden_360.jsonl",
        "excluded_v2_selection": "logs/test_reports/wo45/live_v2_selected_items.json",
        "n_overlap_with_v2": len(overlap_v2_ids),
        "overlap_with_v2_probe_ids": overlap_v2_ids,
        "conditioning": "NONE",
        "by_cell_probe_ids": by_cell_ids,
        "selected_probe_ids": selected_ids,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    res = select_v3_items()
    print(
        f"Selected {res['n_total']} fresh v3 items ({res['items_per_cell']}/cell, "
        f"disputed={res['n_disputed']}, v2_overlap={res['n_overlap_with_v2']}) with seed={res['seed']}"
    )
