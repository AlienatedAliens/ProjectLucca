# WO-45 Superseded Artifacts Registry (`REVIEW_G3.md`)

- **Review Reference:** [`logs/test_reports/wo45/REVIEW_G3.md`](./REVIEW_G3.md) (Reviewed `HEAD`: `fd7aaa8`, Date: `2026-11-10`)
- **Rule:** Per `REVIEW_G3.md` and `WO-45` Rule 1, none of the failed v1 `R-10` or `R-40` artifacts below have been deleted or modified. They are retained on disk for auditability and formally marked **INVALID / SUPERSEDED** by the `v2` redo artifacts (`r10v2_*` and `r40v2_*`).

---

## 1. Invalidated / Superseded `R-10` v1 Artifacts (Failed under `F-1` and `F-2`)

| File Path | Status | Failure Reason (`REVIEW_G3.md`) | Superseded By |
| :--- | :---: | :--- | :--- |
| `logs/test_reports/wo45/prompts/r10_regrade_288_judge_prompt.md` | **SUPERSEDED (v1 Policy-Table Rubric)** | `F-2`: Contained Lucca's stakes taxonomy (`low` / `medium` / `high`) and domain-count thresholds ($\ge 1$ / $\ge 2$ / $\ge 3$ root domains), restating `POLICY_TABLE_2D` and rewarding Arm B by construction. Retained only as a secondary policy-conformance rubric check. | `logs/test_reports/wo45/prompts/r10v2_judge_prompt.md` |
| `logs/test_reports/wo45/regrade_288_judge1.jsonl` (`SHA-256: 290fd68b6bd08c124a54f76fc40379bc7de1183cfc53f9536d173a33dfe103f7`) | **INVALID / SUPERSEDED** | `F-1`: Byte-identical to `regrade_288_judge2.jsonl` (`290fd68b...`); lacked `judge_model`, `temperature`, `timestamp_utc`, and per-dimension `rationale`. | `logs/test_reports/wo45/r10v2_judge1.jsonl` |
| `logs/test_reports/wo45/regrade_288_judge2.jsonl` (`SHA-256: 290fd68b6bd08c124a54f76fc40379bc7de1183cfc53f9536d173a33dfe103f7`) | **INVALID / SUPERSEDED** | `F-1`: Byte-identical to `regrade_288_judge1.jsonl` (`290fd68b...`); lacked `judge_model`, `temperature`, `timestamp_utc`, and per-dimension `rationale`. | `logs/test_reports/wo45/r10v2_judge2.jsonl` |
| `logs/test_reports/wo45/r10_regrade_288_report.json` (`SHA-256: d6e75c55bcf33de057961c8e5fc0388f2ea9998491a303335ad90082233cf393`) | **INVALID / SUPERSEDED** | `F-1`, `F-2`: Computed $\kappa = 1.0000$ from byte-identical judge files and scored against the v1 policy-table prompt. | `logs/test_reports/wo45/r10v2_regrade_288_report.json` |
| `logs/test_reports/wo45/r10_regrade_288_REPORT.md` (`SHA-256: 8a57e1fe11fdff0cdbd18fa0c26a4f515b2c5a765d03b991225809bcf84650cd`) | **INVALID / SUPERSEDED** | `F-1`, `F-2`: Markdown summary of invalid v1 `R-10` report. | `logs/test_reports/wo45/r10v2_regrade_288_REPORT.md` |
| `logs/test_reports/wo45/GATE_G3.md` | **INVALID / SUPERSEDED** | Reported invalid v1 `R-10` and `R-40` results. | `logs/test_reports/wo45/GATE_G3_v2.md` |

---

## 2. Invalidated / Superseded `R-40` v1 Artifacts (Failed under `F-3`)

| File Path | Status | Failure Reason (`REVIEW_G3.md`) | Superseded By |
| :--- | :---: | :--- | :--- |
| `logs/test_reports/wo45/prompts/r40_hazard_rater_prompt.md` | **INVALID / SUPERSEDED** | `F-3`: Line 18 explicitly instructed raters to rate technical scientific vocabulary, botanical compounds, anatomical trivia, and historical treaty provisions as `low`, dictating the answer on the escalation categories under audit. | `logs/test_reports/wo45/prompts/r40v2_hazard_rater_prompt.md` |
| `logs/test_reports/wo45/r40_blinded_73_queries.jsonl` | **INVALID / SUPERSEDED** | `F-3`: Contained only the 73 suspect escalated items with zero non-escalated control items. | `logs/test_reports/wo45/r40v2_mixed_163_queries.jsonl` |
| `logs/test_reports/wo45/r40_rater1.jsonl` | **INVALID / SUPERSEDED** | `F-3`: Rated under the biased `r40_hazard_rater_prompt.md` on the unmixed 73-item pool. | `logs/test_reports/wo45/r40v2_rater1.jsonl` |
| `logs/test_reports/wo45/r40_rater2.jsonl` | **INVALID / SUPERSEDED** | `F-3`: Rated under the biased `r40_hazard_rater_prompt.md` on the unmixed 73-item pool. | `logs/test_reports/wo45/r40v2_rater2.jsonl` |
| `logs/test_reports/wo45/r40_upward_escalations_73_audit.json` (`SHA-256: b0f5b0d051da2e646740415f6179bd1cd2c0fd4a3c026c9ccb82034a24a59c30`) | **INVALID / SUPERSEDED** | `F-3`: Reported `0/73` label errors / `73/73` over-escalations from the biased v1 prompt and unmixed pool. | `logs/test_reports/wo45/r40v2_upward_escalations_audit.json` |
