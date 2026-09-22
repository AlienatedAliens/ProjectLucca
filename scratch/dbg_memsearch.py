"""Verify MemoryManager.list_memories tokenized fallback (F-WO8-22)."""

import shutil
import time
from pathlib import Path

from tests.test_a1_live_hw import (  # noqa: E402
    MASTER_KEY,
    _make_hw_orchestrator,
    _seed_a1_history,
)

TMP = Path("scratch_memsearch_dbg")

QUERIES = [
    "Did you read any files last session?",
    "Did you delete any files last session?",
    "What was the content of the last file you read?",
    "Have you ever fetched a page from python.org?",
]


def main() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(exist_ok=True)
    orch, store, db = _make_hw_orchestrator(TMP)
    _seed_a1_history(store, db, time.time())

    from lucca.memory.manager import MemoryManager

    mgr = MemoryManager(db=db, master_key=MASTER_KEY)
    for q in QUERIES:
        hits = mgr.list_memories(search=q)
        print(f"\n=== {q!r} -> {len(hits)} hits ===")
        for h in hits[:5]:
            print(f"  [{h['kind']}] {h['content'][:90]}")


if __name__ == "__main__":
    main()
