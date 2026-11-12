# `lucca-epistemic` (`v0.2.0`)

Standalone cross-platform Python library extracted from Project Lucca (`WO-45 R-51`, upgraded in `WO-46`) providing runtime epistemic verification primitives with zero UI, audio, Docker, or WSL2 dependencies:

1. **RFC 8032 Ed25519 Provenance Envelopes & Public-Key-Only `ProvenanceGate`:** Domain-separated HKDF-SHA256 seed derivation across eligible provenance tiers (`USER_EXPLICIT`, `USER_CONFIRMED`, `TOOL_VERIFIED`, `LISP_ASSERTION`, `INFERRED`), public-key-only verification, optional legacy HMAC read-migration, and Ed25519-authenticated `OperatorApprovalToken` rule promotion.
2. **2D Hazard-Scaled Standards of Proof & Open-Web Walton Corroboration (`evaluate_web_evidence_burden`):** OpenVINO hazard classification (`proof_policy_hazard_v3_ov`, `NPU -> GPU -> CPU` with explicit `device="CPU"` fallback and regulatory/pathogen/cryptographic deprecation escalation), multi-clause splitting with `HIGH > MEDIUM > LOW` lattice pooling, scraped `content_preview` anti-bot/TOC stub rejection, prohibitive consensus polarity normalization, shingle/Jaccard near-duplicate syndication deduplication, and symmetric query-aligned conflict disclosure metadata.
3. **Clause-Level Receipt Supervision (`ReceiptSupervisor`):** Decomposes assistant narrations into atomic clauses and checks completed action claims against deterministic `ToolReceipt` records.

## Installation

```bash
pip install ./packages/lucca-epistemic
```

## License

GNU Affero General Public License v3.0 or later (`AGPL-3.0-or-later`). See [LICENSE](./LICENSE).
