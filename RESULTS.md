# Project Lucca: Experimental Results Ledger

> **Honesty Note**: Historical v1.3 results were produced from a working tree that contained uncommitted changes. `v1.3-frozen` is the nearest reproducible snapshot. `v1.3-frozen` did not reproduce bit-for-bit (20 of 25 predictions matched). Run-to-run variance is being measured.

| Run ID | Code Commit | Grader Version | Dataset File | Dataset SHA-256 | n | Passed | Strict Score | Lenient Score | Wilson 95% CI | Artifact Path |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `math-v1.3-fresh-500` | `4de6451` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 500 | 420 | 79.20% (396/500) | 86.60% (433/500) | [80.53%, 86.95%] | `logs/test_reports/checkpoint_math500_v1.3-final-fresh-500.json` |
| `math-v1.3-test-25-rep` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 20 | 80.00% (20/25) | 80.00% (20/25) | [60.87%, 91.14%] | `logs/test_reports/checkpoint_math500_test-25-reproduce.json` |
| `math-v1.3-test-25-rep-A` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 21 | 84.00% (21/25) | 84.00% (21/25) | [65.35%, 93.60%] | `logs/test_reports/checkpoint_math500_rep-A.json` |
| `math-v1.3-test-25-rep-B` | `55d1a1f` | v1.3-cas-3stage | `data/benchmarks/math_fresh_heldout_500.jsonl` | `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38` | 25 | 19 | 76.00% (19/25) | 76.00% (19/25) | [56.57%, 88.50%] | `logs/test_reports/checkpoint_math500_rep-B.json` |
