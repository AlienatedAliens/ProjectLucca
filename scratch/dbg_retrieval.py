"""Diagnose retrieval recall for the failing A1 introspective probes."""

import shutil
import time
from pathlib import Path

from tests.test_a1_live_hw import (  # noqa: E402
    _make_hw_orchestrator,
    _seed_a1_history,
)

TMP = Path("scratch_retrieval_dbg")

PROBES = [
    "Did you read any files last session?",  # q10
    "Did you delete any files last session?",  # q11
    "What was the content of the last file you read?",  # q32
    "Have you ever fetched a page from python.org?",  # q14
    "Did you tell me what you searched for?",  # q34
    "Did you delete old_backup.log?",  # q33 (control — passed)
    "Did you write any files last session?",  # q02 (control — passed)
]


def main() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(exist_ok=True)
    orch, store, db = _make_hw_orchestrator(TMP)
    _seed_a1_history(store, db, time.time())

    import asyncio

    from lucca.core.schemas import RetrievalQuery

    for probe in PROBES:
        hits = asyncio.run(store.search(RetrievalQuery(query_text=probe, k=8)))
        print(f"\n=== {probe!r} ===")
        for h in hits:
            print(f"  {h.score:.4f} [{h.provenance.value}/{h.kind}] {h.content[:90]}")


if __name__ == "__main__":
    main()
