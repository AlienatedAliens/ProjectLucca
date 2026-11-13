# Model Weights & Third-Party Notices

All Python source code in `epistemic-guard` is licensed under the **MIT License** (see [`LICENSE`](LICENSE)).

When optional OpenVINO INT8 neural weights are downloaded via `epistemic_guard.download_models()` (`epistemic-guard download-models`), the fine-tuned and quantized OpenVINO IR weights derive from the following permissive (`Apache-2.0`) upstream base checkpoints:

## 1. `action_claim_int8` & `hazard_int8`
- **Upstream Base Checkpoint:** [`cross-encoder/nli-MiniLM2-L6-H768`](https://huggingface.co/cross-encoder/nli-MiniLM2-L6-H768) (Sentence-Transformers / Nils Reimers & UKP Lab, TU Darmstadt; distilled from Microsoft MiniLMv2 / RoBERTa).
- **Upstream License:** Apache License 2.0 (`Apache-2.0`).
- **Modifications by Sean Maxwell (2026):**
  - `action_claim_int8`: Fine-tuned 10-class classification head and transformer layers on `(user_request, assistant_clause)` speech-act pairs, exported to static `[1, 192]` OpenVINO IR, and quantized to INT8 via NNCF SmoothQuant + Fast Bias Correction.
  - `hazard_int8`: Fine-tuned 5-class classification head and transformer layers with 5:1 asymmetric ordinal cost-weighted risk loss, exported to static `[1, 64]` OpenVINO IR, and quantized to INT8 via NNCF.

## 2. `web_evidence_int8`
- **Upstream Base Checkpoint:** [`cross-encoder/ms-marco-MiniLM-L-6-v2`](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2) (Sentence-Transformers / Nils Reimers; based on Microsoft MiniLM).
- **Upstream License:** Apache License 2.0 (`Apache-2.0`).
- **Modifications by Sean Maxwell (2026):**
  - Replaced single-logit ranking head with a 3-class `(query, passage) -> {CORROBORATES, IRRELEVANT, DISPUTES}` head, fine-tuned across all 6 transformer layers on disjoint open-web search/passage pairs, exported to static `[1, 192]` OpenVINO IR, and quantized to INT8 via NNCF.

## 3. `nli_int8`
- **Upstream Base Checkpoint:** [`cross-encoder/nli-deberta-v3-xsmall`](https://huggingface.co/cross-encoder/nli-deberta-v3-xsmall) (Sentence-Transformers / Nils Reimers, `Apache-2.0`; fine-tuned from [`microsoft/deberta-v3-xsmall`](https://huggingface.co/microsoft/deberta-v3-xsmall), `MIT`).
- **Upstream License:** Apache License 2.0 (`Apache-2.0`) / MIT License (`MIT`).
- **Modifications by Sean Maxwell (2026):**
  - Exported 3-class `(premise, hypothesis) -> {contradiction, entailment, neutral}` cross-encoder to static `[1, 128]` OpenVINO IR and quantized to INT8 via NNCF SmoothQuant + Fast Bias Correction.

---

Licensed under the Apache License, Version 2.0 (the "License"); you may obtain a copy of the Apache-2.0 License at:
https://www.apache.org/licenses/LICENSE-2.0
