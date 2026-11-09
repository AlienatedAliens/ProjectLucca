# WO-45 Gate G0 Report

## A. Integrity
- Baseline hashes (`R-00`) commit: `c9706a1` (`logs/test_reports/wo45/baseline_hashes.json`)
- End-of-gate re-hash of baseline files: identical (`yes`, 0 bytes changed across all 5 tracked files)
- All WO-45 commits in order:
  - `c9706a1 | wo45(R-00): record baseline SHA-256 snapshot of WO-44 artifacts | G0`
- Lock commits precede corpus/result commits: `N/A` (G0 records baseline hashes only)
- External timestamps: `N/A` (G0)

## B. Per-task status
| ID | Status (DONE/PARTIAL/BLOCKED) | Artifact paths | Key numbers (k/N, %, CI) | Deviations from WO |
| :--- | :--- | :--- | :--- | :--- |
| `R-00` | `DONE` | `logs/test_reports/wo45/baseline_hashes.json` (SHA-256: computed below) | `(5/5, 100.0%)` baseline files hashed and frozen | None |

### Return Block for `R-00`
- **Commit SHA:** `c9706a1`
- **Baseline File List & SHA-256 Hashes (`logs/test_reports/wo45/baseline_hashes.json`):**
  - `logs/test_reports/web_evidentiary_burden_360_report.json`: `d335733fe566336e43fd5b38ba7d4d1edc0200a70a8c6affe3092a19278403ad`
  - `logs/test_reports/web_evidentiary_burden_360_REPORT.md`: `e90b4ceccb5faf1876457a9b5667bdf8d06e7518a6a11ce184955f38a8f8c9be`
  - `logs/test_reports/web_evidentiary_burden_360_prereg_lock.json`: `aeabb67c05ca8fb63bd933656e9bc017e0033fef58eea4a6434ce2b8dabd81eb`
  - `data/benchmarks/web_evidentiary_burden_360.jsonl`: `db685e70e65b40ba42be0e3ea2bbf54ac00b72ec6c69546faeabcff3b5574e13`
  - `scripts/run_web_evidentiary_burden_benchmark.py`: `e5131fb19c6dcd279709591cfb87d9c3018f2096c5c0d3b973f1070f3181c8c5`

## C. Headline results (old vs new, side by side)
| Claim | WO-44 value | WO-45 value | Artifact | Method |
| :--- | :--- | :--- | :--- | :--- |
| Baseline artifact snapshot | Unrecorded | `(5/5, 100.0%)` SHA-256 hashes recorded | `logs/test_reports/wo45/baseline_hashes.json` | SHA-256 file digest |

## D. Negative / unexpected results
None in G0.

## E. Subagent prompts
None in G0.

## F. Reproduction
```powershell
.\.venv\Scripts\python.exe -c "import hashlib, json, pathlib; d = json.loads(pathlib.Path('logs/test_reports/wo45/baseline_hashes.json').read_text()); [print(k, hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest() == v) for k, v in d['frozen_measured_artifacts'].items()]"
```

## G. Open issues
None. Proceeding to Gate G1 (`R-01`, `R-02`, `R-03`, `R-04`, `R-07`, `R-08`, `R-09`, `R-20`, `R-23` disclosure, `R-30` wording).
