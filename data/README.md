# Benchmark Datasets & Provenance

This directory stores benchmark evaluation files used across Project Lucca evaluation tracks.

## Upstream Datasets & Verification

### Apple GSM-Symbolic
* **Source Repository**: [`apple/ml-gsm-symbolic`](https://github.com/apple/ml-gsm-symbolic)
* **Pinned Upstream Commit**: `3b645c25d200bf950fb84e8cdcbfeccd91d6a8af`
* **Fetch Script**: `scripts/fetch_gsm_symbolic.py`
* **License**: Apple Software License (Code) / CC BY-NC-ND 4.0 (Dataset)

| Dataset File | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `data/benchmarks/GSM_symbolic.jsonl` | 6,233,677 | `945055837b232bd9b56827b1e3a5aa019075f29e8ba4669d9a9df8b4439a291f` |
| `data/benchmarks/GSM_p1.jsonl` | 7,012,956 | `5478fe81b9cdc5d9447514ca68b0dfbb6cb01b7227fefadf143469b103b592ac` |
| `data/benchmarks/GSM_p2.jsonl` | 3,995,468 | `f7d6701619f824f4fedd0a914b1cfbc0fd31f61617887aa7fe318d018dda3f29` |

### Competition Mathematics
* **Source Repository**: `HuggingFaceTB/MATH` (commit `140a673`)
* `data/benchmarks/math_fresh_heldout_500.jsonl`: SHA-256 `834405faef2b3059a92a728450850280d188a06412008007be3b91f9831bc308` *(v1.35+ normalized; initial v1.3 pre-normalization export had SHA-256 `834405fa038936ef114b0358e0a4f5b5c928ce60170067a9cf60759f27918a38`, see `data/benchmarks/MANIFEST.yaml` `drift_note`)*
* `data/benchmarks/math_b4_sealed_100.jsonl`: SHA-256 `14c8af21a5172473cb50e858eb839a66554f4cddde9730e953e2989ce282100b`
* `data/benchmarks/math500_test.jsonl`: SHA-256 `989cf8b975bc5d888126b86df2206ef4507b5db50426b3e70cfebf47b2c0f6f4`
