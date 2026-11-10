#!/usr/bin/env python3
"""
WO-45 REVIEW_G3 Requirement 5 (`scripts/wo45/r10v2_source_check.py`):
Verifies that every `blind_id` in the R-10 v2 key (and blinded JSONL pool) maps
1-to-1 to a `turn_records` entry in the FROZEN R-00 report
`logs/test_reports/web_evidentiary_burden_360_report.json`
(`SHA-256: d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad`),
and does NOT match the v2 report (`web_evidentiary_burden_360_v2_report.json`).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_EXPECTED_SHA = "d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad"


def verify_key_against_frozen(key_path: Path, pool_path: Path, is_redacted: bool = False) -> dict[str, object]:
    frozen_path = REPO_ROOT / "logs/test_reports/web_evidentiary_burden_360_report.json"
    v2_path = REPO_ROOT / "logs/test_reports/web_evidentiary_burden_360_v2_report.json"

    frozen_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    assert frozen_sha == FROZEN_EXPECTED_SHA, f"Frozen report hash mismatch: {frozen_sha}"

    frozen_data = json.loads(frozen_path.read_text(encoding="utf-8"))
    frozen_turns = frozen_data["live_4model_matrix"]["turn_records"]
    assert len(frozen_turns) == 144

    # Build lookup (model, probe_id, arm) -> reply text in frozen report
    frozen_lookup: dict[tuple[str, str, str], tuple[int, str]] = {}
    for idx, tr in enumerate(frozen_turns):
        frozen_lookup[(str(tr["model"]), str(tr["probe_id"]), "Arm_A")] = (idx, str(tr["arm_a_reply"]))
        frozen_lookup[(str(tr["model"]), str(tr["probe_id"]), "Arm_B")] = (idx, str(tr["arm_b_reply"]))

    v2_lookup: dict[tuple[str, str, str], str] = {}
    if v2_path.exists():
        v2_data = json.loads(v2_path.read_text(encoding="utf-8"))
        for tr in v2_data["live_4model_matrix"]["turn_records"]:
            v2_lookup[(str(tr["model"]), str(tr["probe_id"]), "Arm_A")] = str(tr["arm_a_reply"])
            v2_lookup[(str(tr["model"]), str(tr["probe_id"]), "Arm_B")] = str(tr["arm_b_reply"])

    key_map = json.loads(key_path.read_text(encoding="utf-8"))
    pool_rows = {
        obj["blind_id"]: obj
        for obj in (json.loads(ln) for ln in pool_path.read_text(encoding="utf-8").splitlines() if ln.strip())
    }
    assert len(key_map) == 288, f"Expected 288 key entries, got {len(key_map)}"
    assert len(pool_rows) == 288, f"Expected 288 pool rows, got {len(pool_rows)}"

    seen_triples: set[tuple[str, str, str]] = set()
    exact_frozen_matches = 0
    differ_from_v2 = 0

    for bid, meta in sorted(key_map.items()):
        assert bid in pool_rows, f"Missing {bid} in {pool_path}"
        triple = (str(meta["model"]), str(meta["probe_id"]), str(meta["arm"]))
        assert triple in frozen_lookup, f"{bid} triple {triple} not found in frozen report"
        assert triple not in seen_triples, f"Duplicate triple {triple}"
        seen_triples.add(triple)

        f_idx, f_reply = frozen_lookup[triple]
        assert int(meta["turn_record_index"]) == f_idx
        assert str(meta["reply"]) == f_reply, f"Reply text mismatch on {bid} vs frozen report"
        if not is_redacted:
            assert str(pool_rows[bid]["reply"]) == f_reply, f"Pool reply mismatch on {bid}"
        else:
            assert str(pool_rows[bid]["reply"]) == str(meta["redacted_reply"])
        exact_frozen_matches += 1

        if triple in v2_lookup and v2_lookup[triple] != f_reply:
            differ_from_v2 += 1

    return {
        "key_file": str(key_path.name),
        "pool_file": str(pool_path.name),
        "pool_sha256": hashlib.sha256(pool_path.read_bytes()).hexdigest(),
        "frozen_report_sha256": frozen_sha,
        "total_blind_ids_verified": len(key_map),
        "unique_model_probe_arm_triples": len(seen_triples),
        "exact_byte_matches_to_frozen_report": exact_frozen_matches,
        "replies_differing_from_v2_report": differ_from_v2,
        "status": "PASS (100% mapped to frozen R-00 report d335733f...)",
    }


def main() -> None:
    wo45 = REPO_ROOT / "logs/test_reports/wo45"
    scratch = Path(r"C:\Users\seatr\.gemini\antigravity\brain\3fe97321-70aa-47a9-a0ac-ff3544cdc5d6\scratch")

    k1 = (wo45 / "r10v2_blinded_288_key.json") if (wo45 / "r10v2_blinded_288_key.json").exists() else (scratch / "r10v2_blinded_288_key.json")
    k2 = (wo45 / "r10v2_redacted_288_key.json") if (wo45 / "r10v2_redacted_288_key.json").exists() else (scratch / "r10v2_redacted_288_key.json")

    out = {
        "r10v2_primary_unredacted": verify_key_against_frozen(
            k1, wo45 / "r10v2_blinded_288_replies.jsonl", is_redacted=False
        ),
        "r10v2_secondary_redacted": verify_key_against_frozen(
            k2, wo45 / "r10v2_redacted_288_replies.jsonl", is_redacted=True
        ),
    }
    print(json.dumps(out, indent=2))
    if len(sys.argv) > 1 and sys.argv[1] == "--save":
        (wo45 / "r10v2_source_check_output.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
