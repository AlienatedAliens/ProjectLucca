"""Check which user-guide fixes have landed."""

from pathlib import Path

text = Path("docs/USER_GUIDE_WHAT_LUCCA_DOES.md").read_text(encoding="utf-8")
dec = Path("docs/DECISIONS.md").read_text(encoding="utf-8")

checks = [
    "test_sandbox_rpc.py", "test_persistent_rpc.py",
    "memory/embeddings.py", "senses/embed.py",
    "launch_server.ps1", "server_ctl.py",
    "DEFAULT_CONFIDENCE_THRESHOLD", "confidence_threshold=0.60",
    "MIN_CALIBRATION_SAMPLES", "min_samples=30",
    "MAX_REASONING_ROUNDS", "max_rounds=8",
    "ACTIVE_SKILL_LIMIT", "2 recorded decisions", "20 decisions",
    "MIN_FREQUENCY_THRESHOLD", "time-greeting-v1", "Grounded commit",
]
for c in checks:
    print(("HIT  " if c in text else "miss ") + c)

print("\nDECISIONS.md:")
for c in ["REASONING=3", "WEB=3, ABSTENTION=4", "names corrected 2026-09-25"]:
    print(("HIT  " if c in dec else "miss ") + c)
