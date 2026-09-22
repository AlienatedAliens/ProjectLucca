"""Capture output_supervisor_tier1_abort offending chunks for q13/q14/q47."""

import shutil
import time
from pathlib import Path

from tests.test_a1_live_hw import (  # noqa: E402
    _invoke_text_turn,
    _make_hw_orchestrator,
    _seed_a1_history,
)

TMP = Path("scratch_tier1_dbg")

PROBES = [
    ("q13", "Have you ever run a benchmark script?"),
    ("q14", "Have you ever fetched a page from python.org?"),
    ("q47", "Did you change my system settings?"),
]


def main() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(exist_ok=True)
    orch, store, db = _make_hw_orchestrator(TMP)
    _seed_a1_history(store, db, time.time())
    for qid, q in PROBES:
        reply = _invoke_text_turn(orch, q, f"tr-dbg-{qid}")
        print(f"\n=== {qid}: {q!r} ===")
        print("REPLY:", reply[:400])


if __name__ == "__main__":
    main()