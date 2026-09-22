"""Reproduce the 'not enough values to unpack' crash in the A1 contradiction path.

Uses the same harness as tests/test_a1_live_hw.py against the live llama-server.
"""

import shutil
import traceback
from pathlib import Path

from tests.test_a1_live_hw import (  # noqa: E402
    _invoke_text_turn,
    _make_hw_orchestrator,
    _seed_a1_history,
)

TMP = Path("scratch_debug_hw")


def main() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(exist_ok=True)
    orch, store, db = _make_hw_orchestrator(TMP)
    import time

    now = time.time()
    _seed_a1_history(store, db, now)
    try:
        reply = _invoke_text_turn(orch, "Have you ever been wrong about config format?", "tr-debug-1")
        print("REPLY:", reply)
    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
