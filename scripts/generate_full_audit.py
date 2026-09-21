import json

with open('data/master_claims_list.json', 'r', encoding='utf-8') as f:
    items = json.load(f)

print(f"Loaded {len(items)} items.")

# We will classify each claim:
# - VERIFIED
# - FAILED (Naming test, Default failure test, or unmet threshold)
# - UNVERIFIABLE (SYNTHETIC ONLY) (Production row check = 0 rows)
# - CONTRADICTION (Conflicting hardware/runtime claims)

# Let's inspect contradictions:
# 1. ASR hardware placement:
# README line 95 / line 107 vs ARCH line 424 / line 466 vs DECISIONS line 61 vs TECH_MAP line 298/299.
