"""Deterministic stratified item selector for WO-45 Gate G4 live v2 evaluation (R-12, R-15).

Draws ITEMS_PER_CELL items uniformly at random without replacement from each of the 12
(stratum, topology) cells in data/benchmarks/web_evidentiary_burden_360.jsonl using a fixed
PRNG seed, with zero conditioning on any model or prediction output.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPO_ROOT / "data" / "benchmarks" / "web_evidentiary_burden_360.jsonl"
OUT_PATH = REPO_ROOT / "logs" / "test_reports" / "wo45" / "live_v2_selected_items.json"

SEED = 20261111
ITEMS_PER_CELL = 11  # 12 cells * 11 = 132 items (>=89% power for delta=15pp up to psi=0.30; >=24 escalated subgroup)
STRATA = ("LOW", "MEDIUM", "HIGH")
TOPOLOGIES = ("1_source", "2_source", "3_source", "disputed")


def select_items() -> dict[str, object]:
    rows = [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_cell: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        cell = (str(row["stratum"]), str(row["topology"]))
        by_cell.setdefault(cell, []).append(row)

    rng = random.Random(SEED)
    selected_ids: list[str] = []
    by_cell_ids: dict[str, list[str]] = {}
    for st in STRATA:
        for top in TOPOLOGIES:
            pool = sorted(by_cell[(st, top)], key=lambda r: str(r["probe_id"]))
            rng.shuffle(pool)
            chosen = sorted(pool[:ITEMS_PER_CELL], key=lambda r: str(r["probe_id"]))
            ids = [str(r["probe_id"]) for r in chosen]
            by_cell_ids[f"{st}::{top}"] = ids
            selected_ids.extend(ids)

    payload: dict[str, object] = {
        "seed": SEED,
        "items_per_cell": ITEMS_PER_CELL,
        "n_total": len(selected_ids),
        "source_corpus": "data/benchmarks/web_evidentiary_burden_360.jsonl",
        "conditioning": "NONE",
        "by_cell_probe_ids": by_cell_ids,
        "selected_probe_ids": selected_ids,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    res = select_items()
    print(f"Selected {res['n_total']} items ({res['items_per_cell']}/cell) with seed={res['seed']}")
