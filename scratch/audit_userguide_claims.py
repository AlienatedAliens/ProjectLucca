"""User-guide truth audit: mechanically verify every checkable claim in
docs/USER_GUIDE_WHAT_LUCCA_DOES.md against the live tree."""

import re
from pathlib import Path

ROOT = Path(".")

def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK  " if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))

def file_has(path: str, *patterns: str) -> tuple[bool, str]:
    p = ROOT / path
    if not p.exists():
        return False, f"{path} does not exist"
    text = p.read_text(encoding="utf-8")
    missing = [pat for pat in patterns if not re.search(pat, text)]
    if missing:
        return False, f"missing: {missing}"
    return True, ""

# --- Path citations ---
check("config/skills/good-morning-v1/plan.scm exists", (ROOT / "config/skills/good-morning-v1/plan.scm").exists())
check("config/skills/time-greeting-v1/plan.scm exists", (ROOT / "config/skills/time-greeting-v1/plan.scm").exists())
check("tests/test_sandbox_rpc.py exists", (ROOT / "tests/test_sandbox_rpc.py").exists())
check("tests/test_persistent_rpc.py exists", (ROOT / "tests/test_persistent_rpc.py").exists())
check("src/lucca/memory/embeddings.py exists", (ROOT / "src/lucca/memory/embeddings.py").exists())
check("src/lucca/senses/embed.py exists", (ROOT / "src/lucca/senses/embed.py").exists())
check("launch_server.ps1 exists", (ROOT / "launch_server.ps1").exists() or len(list(ROOT.glob("**/launch_server.ps1"))) > 0)
check("models/MANIFEST.json exists", (ROOT / "models/MANIFEST.json").exists())
check("config/rules/calc-open-with-expr-v1.scm exists", (ROOT / "config/rules/calc-open-with-expr-v1.scm").exists())
check("config/skills/_retired/barge-in-sorry-v1 exists", (ROOT / "config/skills/_retired/barge-in-sorry-v1").exists())

# --- Constant citations ---
ok, d = file_has("src/lucca/router/heuristic.py", r"DEFAULT_CONFIDENCE_THRESHOLD\s*=\s*([\d.]+)")
if ok:
    m = re.search(r"DEFAULT_CONFIDENCE_THRESHOLD\s*=\s*([\d.]+)", (ROOT / "src/lucca/router/heuristic.py").read_text(encoding="utf-8"))
    check("DEFAULT_CONFIDENCE_THRESHOLD == 0.60", m is not None and m.group(1) == "0.6", f"actual={m.group(1) if m else '?'}")
else:
    check("DEFAULT_CONFIDENCE_THRESHOLD == 0.60", False, d)

ok, d = file_has("src/lucca/router/calibration.py", r"MIN_CALIBRATION_SAMPLES\s*=\s*(\d+)")
if ok:
    m = re.search(r"MIN_CALIBRATION_SAMPLES\s*=\s*(\d+)", (ROOT / "src/lucca/router/calibration.py").read_text(encoding="utf-8"))
    check("MIN_CALIBRATION_SAMPLES == 30", m is not None and m.group(1) == "30", f"actual={m.group(1) if m else '?'}")
else:
    check("MIN_CALIBRATION_SAMPLES == 30", False, d)

ok, d = file_has("src/lucca/router/heuristic.py", r"EMERGENCY_REFLEX_PATTERN")
check("EMERGENCY_REFLEX_PATTERN in heuristic.py", ok, d)

ok, d = file_has("src/lucca/core/capabilities.py", r"MAX_REGISTRY_TOOLS:\s*Final\[int\]\s*=\s*19")
check("MAX_REGISTRY_TOOLS == 19", ok, d)

ok, d = file_has("src/lucca/reasoning/lifecycle.py", r"SHADOW_PROMOTION_THRESHOLD")
check("SHADOW_PROMOTION_THRESHOLD in lifecycle.py", ok, d)

ok, d = file_has("src/lucca/reasoning/induction.py", r"MIN_PATTERN_SUPPORT")
check("MIN_PATTERN_SUPPORT in induction.py", ok, d)

ok, d = file_has("src/lucca/memory/store.py", r"RETRIEVAL_TOKEN_BUDGET")
check("RETRIEVAL_TOKEN_BUDGET in store.py", ok, d)

ok, d = file_has("src/lucca/core/orchestrator.py", r"MAX_REASONING_ROUNDS")
check("MAX_REASONING_ROUNDS cited in orchestrator.py", ok, d)

ok, d = file_has("src/lucca/core/cascade.py", r"MAX_RESEARCH_ROUNDS")
check("MAX_RESEARCH_ROUNDS cited in cascade.py", ok, d)

# --- EpistemicSubstrate member names (guide lists TELEMETRY, WORKSPACE, MEMORY, WEB,
#     ABSTENTION, SELF, CAPABILITIES, SELF_HISTORY; DECISIONS.md says REASONING/SENSES/SYSTEM/WEB_FLOOR) ---
ok, d = file_has("src/lucca/core/cascade.py", r"class EpistemicSubstrate")
if ok:
    text = (ROOT / "src/lucca/core/cascade.py").read_text(encoding="utf-8")
    m = re.search(r"class EpistemicSubstrate[^:]*:(.*?)(?=\nclass |\n\ndef )", text, re.DOTALL)
    body = m.group(1) if m else ""
    members = re.findall(r"(\w+)\s*=", body)
    print(f"       EpistemicSubstrate members: {members}")
    guide_names = {"TELEMETRY", "WORKSPACE", "MEMORY", "WEB", "ABSTENTION", "SELF", "CAPABILITIES", "SELF_HISTORY"}
    check("guide substrate names match code", guide_names == set(members), f"code={sorted(members)}")

# --- memory_commit staleness ---
ok, d = file_has("src/lucca/core/orchestrator.py", r"def _handle_memory_commit")
check("grounded memory_commit handler exists (guide says 'refuses every call')", ok, d)

# --- admin commands ---
ok, d = file_has("src/lucca/admin.py", r"memory", r"forget")
check("admin memory list/forget commands exist", ok, d)

# --- env-check count ---
ok, d = file_has("src/lucca/admin.py", r"env.check|env_check")
check("admin env-check exists", ok, d)

# --- calc_math ---
ok, d = file_has("src/lucca/core/capabilities.py", r'"calc_math"')
check("calc_math tool registered", ok, d)

# --- 30-cap in lifecycle ---
ok, d = file_has("src/lucca/reasoning/lifecycle.py", r"30")
check("30-rule cap referenced in lifecycle.py", ok, d)

# --- decisions count (guide says '2 recorded decisions') ---
import sqlite3
db = ROOT / "data/memory.sqlite"
if db.exists():
    con = sqlite3.connect(str(db))
    try:
        n = con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        check("guide's '2 recorded decisions' still accurate", n == 2, f"actual={n}")
    except Exception as e:
        check("decisions table readable", False, str(e))
    finally:
        con.close()

# --- MANIFEST gemma pin ---
ok, d = file_has("models/MANIFEST.json", r"gemma-4-12b-heretic")
check("MANIFEST pins gemma-4-12b-heretic", ok, d)

# --- skill count ---
skills = [p for p in (ROOT / "config/skills").iterdir() if p.is_dir() and p.name != "_retired"]
check("15 skill directories", len(skills) == 15, f"actual={len(skills)}")

# --- MiniLM citation ---
ok, d = file_has("src/lucca/senses/embed.py", r"MiniLM|all-MiniLM")
check("all-MiniLM-L6-v2 in senses/embed.py", ok, d)
