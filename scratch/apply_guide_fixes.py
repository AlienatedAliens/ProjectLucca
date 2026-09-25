"""Apply remaining user-guide truth fixes deterministically (exact replace + count asserts)."""

from pathlib import Path

GUIDE = Path("docs/USER_GUIDE_WHAT_LUCCA_DOES.md")
DEC = Path("docs/DECISIONS.md")

guide_fixes = [
    (
        "(`src/lucca/sandbox/rpc.py`, `tests/test_sandbox_rpc.py`)",
        "(`src/lucca/sandbox/rpc.py`, `tests/test_persistent_rpc.py`)",
    ),
    (
        "(`all-MiniLM-L6-v2` per `src/lucca/memory/embeddings.py`), RRF fusion, 2,048-token retrieval quota (`src/lucca/memory/store.py:RETRIEVAL_TOKEN_BUDGET`).",
        "(`all-MiniLM-L6-v2` per `src/lucca/senses/embed.py`), RRF fusion, 2,048-token retrieval quota (`format_memory_context(max_tokens=2048)` in `src/lucca/memory/retrieval.py`).",
    ),
    (
        "16K ctx per `launch_server.ps1`",
        "16K ctx default per `src/lucca/brain/server_ctl.py`",
    ),
    (
        "(`src/lucca/router/heuristic.py:DEFAULT_CONFIDENCE_THRESHOLD`)",
        "(`confidence_threshold=0.60` in `src/lucca/router/heuristic.py:HeuristicRouter.__init__`)",
    ),
    (
        "(`src/lucca/router/calibration.py:MIN_CALIBRATION_SAMPLES`)",
        "(`min_samples=30` in `src/lucca/router/calibration.py:fit_guard_from_db`)",
    ),
    (
        "`FULL_LOOP` (model with up to 4 tool rounds per `D-BRAIN-05 v2`, `src/lucca/core/orchestrator.py:MAX_REASONING_ROUNDS`, or up to 8 research rounds per `src/lucca/core/cascade.py:MAX_RESEARCH_ROUNDS`). 15 active rules are capped at 30 in `src/lucca/reasoning/lifecycle.py`.",
        "`FULL_LOOP` (model with up to 8 tool rounds — `max_rounds=8` in `src/lucca/core/orchestrator.py:_stream_llm_speech`). 15 active rules are capped at 30 (`ACTIVE_SKILL_LIMIT` in `src/lucca/reasoning/skills.py`).",
    ),
    (
        "15 active MicroScheme rules (`config/skills/`, capped at 30 in `src/lucca/reasoning/lifecycle.py`)",
        "15 active MicroScheme rules (`config/skills/`, capped at 30 per `ACTIVE_SKILL_LIMIT` in `src/lucca/reasoning/skills.py`)",
    ),
    (
        "It has never completed on real usage because there is almost no real usage yet (2 recorded decisions).",
        "It has never completed on real usage; as of 2026-09-25 the production log holds 20 decisions, so the N>=3 induction floor is now crossed and live induction is possible.",
    ),
]

text = GUIDE.read_text(encoding="utf-8")
for old, new in guide_fixes:
    n = text.count(old)
    if n != 1:
        print(f"SKIP ({n}x): {old[:70]}")
        continue
    text = text.replace(old, new)
    print(f"OK: {old[:70]}")
GUIDE.write_text(text, encoding="utf-8")

dec = DEC.read_text(encoding="utf-8")
old_dec = "(`TELEMETRY=0`, `WORKSPACE=1`, `MEMORY=2`, `REASONING=3`, `SENSES=4`, `SYSTEM=5`, `WEB_FLOOR=6`, `SELF_HISTORY=7` per `cascade.py:EpistemicSubstrate`)"
new_dec = "(`TELEMETRY=0`, `WORKSPACE=1`, `MEMORY=2`, `WEB=3`, `ABSTENTION=4`, `SELF=5`, `CAPABILITIES=6`, `SELF_HISTORY=7` per `cascade.py:EpistemicSubstrate`; names corrected 2026-09-25 per `docs/audit/findings/USER_GUIDE_TRUTH_AUDIT_2026-09.md` X1)"
n = dec.count(old_dec)
if n == 1:
    dec = dec.replace(old_dec, new_dec)
    DEC.write_text(dec, encoding="utf-8")
    print("OK: DECISIONS.md D-CASC-01 substrate names")
else:
    print(f"SKIP ({n}x): DECISIONS.md substrate line")
