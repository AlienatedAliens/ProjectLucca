# `epistemic-guard`

**Signed tool receipts, Ed25519 memory write-gating, and RAG source deduplication for Python agents.**  
Runs locally on CPU, GPU, or NPU in **3–11 ms**. Zero LLM API calls. MIT License.

---

## The Three Production Bugs This Library Fixes

1. **Phantom tool claims in assistant prose:** Your tool threw an HTTP 500 or was never called, yet the LLM replies *"I refunded order #8821 and emailed the receipt."* Pre-execution MCP/tool firewalls never see this because no tool call happened.
2. **Memory self-poisoning & prompt injection:** Naive agent memory stores (`vector_db.add(assistant_reply)`) let model hallucinations and untrusted web pages write durable facts into long-term memory.
3. **Syndicated RAG echo chambers:** Three retrieved URLs repeating the same wire-service paragraph get counted as "3 independent sources" on medical, legal, or security queries.

---

## Quickstart

```bash
pip install epistemic-guard

# Optional: download the 4-model OpenVINO INT8 pack (~227 MB download / ~279 MB unpacked, SHA-256 verified)
epistemic-guard download-models

# Run the live 4-part verification demo on CPU
epistemic-guard demo
```

### 1. Catch Phantom Actions (`@signed_tool` + `ReceiptSupervisor` + Streaming)

```python
import os
from epistemic_guard import (
    MerkleReceiptLog,
    ProvenanceGate,
    ReceiptRecorder,
    ReceiptSupervisor,
    SignerFactory,
)

factory = SignerFactory.from_master_key(os.urandom(32))
gate = ProvenanceGate(factory.public_keys())
merkle = MerkleReceiptLog(gate=gate)
recorder = ReceiptRecorder(signer=factory.tool_verified(), merkle_log=merkle)


@recorder.tool  # Works on both sync and async functions (MCP, OpenAI, PydanticAI, LangGraph)
def write_file(path: str, content: str) -> str:
    return f"wrote {len(content)} bytes"


write_file("notes.txt", "release checklist")

sup = ReceiptSupervisor(device="CPU")
verdict = sup.verify_narration(
    "I saved your checklist to notes.txt; I also deleted staging.db.",
    receipts=recorder.receipts,
    user_prompt="Save the checklist to notes.txt.",
)

assert verdict.is_valid is False
print(verdict.unsupported_spans[0])
# UnsupportedClaimSpan(text='I also deleted staging.db.', start_char=37, end_char=63, claimed_family='CLAIM_DELETE', ...)

# Ready-to-send correction prompt for automatic LLM retry loops:
print(verdict.to_retry_prompt(recorder.receipts))
```

For SSE chat or voice pipelines, `sup.stream(receipts=...)` checks each clause the moment `.`, `!`, `?`, `;`, or `\n` arrives so you can abort mid-generation before trailing tokens reach the user. You can also pass standard OpenAI/Anthropic message lists directly to `verify_chat_turn(messages)`.

### 2. Cryptographic Memory Write-Gating (`ProvenanceGate` + `SQLiteProvenanceStore`)

`ProvenanceGate` holds **only Ed25519 public keys**. Even if prompt injection hijacks the agent loop, the runtime holds no private key capable of forging a `USER_EXPLICIT` or `TOOL_VERIFIED` memory record, and `LLM_NARRATION` is rejected by construction.

```python
import os
from epistemic_guard import Provenance, ProvenanceGate, SQLiteProvenanceStore, SignerFactory

factory = SignerFactory.from_master_key(os.urandom(32))
gate = ProvenanceGate(factory.public_keys())  # Public keys only — zero private keys in gate
store = SQLiteProvenanceStore("agent_memory.sqlite", gate)  # Append-only SQLite triggers + hash chain

env = factory.user_explicit().sign("Deploy freeze starts Friday 18:00 UTC.", trace_id="turn-42")
store.append(env, expected_provenance=Provenance.USER_EXPLICIT)

assert len(store.list_verified()) == 1
assert store.verify_chain() == 1
store.close()
```

### 3. Multi-Source RAG Deduplication & Hazard Scaling (`corroborate_sources`)

```python
from epistemic_guard import corroborate_sources

wire_copy = (
    "Clinical guidance notes that initial adult warfarin dosing typically starts at "
    "2 mg to 5 mg once daily with INR monitoring."
)
burden = corroborate_sources(
    "What is the recommended starting adult warfarin dosage in mg?",
    [
        {"url": "https://reuters-health.org/a", "snippet": wire_copy},
        {"url": "https://clinical-digest.net/b", "snippet": wire_copy},
        {"url": "https://pharma-bulletin.io/c", "snippet": wire_copy},
    ],
    device="CPU",
)

assert burden.deduplicated_duplicates_collapsed == 2
assert burden.independent_sources_count == 1
assert burden.meets_casual_burden is False  # High-hazard query requires >=3 independent sources
```

---

## Measured CPU Performance & Holdout Accuracy (OpenVINO INT8)

All four optional neural classifiers run in-process via OpenVINO INT8 (`CPU`, `GPU`, or `NPU`, **English-only**) with pinned SHA-256 manifests. If weights are not installed, `epistemic-guard` emits an explicit `EpistemicModelUnavailableWarning` (or raises `ModelIntegrityError` when `require_neural=True`) rather than silently degrading.

| Component | INT8 Size | CPU p50 Latency | Held-Out Result (Sample Size & Origin Attached) | Known Failure Modes |
| :--- | :---: | :---: | :--- | :--- |
| **`web_evidence_int8` + `nli_int8`** (`corroborate_sources`) | `23.1 MB` + `91.1 MB` | `3.0 ms` / `9.9 ms` | **`47/64 (73.4%)` burden accuracy & `56/64 (87.5%)` dispute accuracy** on single-shot pre-registered live-scraped open web (`real_web_v2`, `246` archived `.html.gz` pages, 3 blinded LLM raters $\kappa = 0.91\text{–}1.00$); `60/64 (93.8%)` dispute accuracy on `real_web_v1`; `30/30 (100%)` wire/sybil collapse & `43/45 (95.6%)` dispute accuracy on synthetic `R-33`; `88/120 (73.3%)` on blinded `nli_holdout_v2_120` | Implicit cross-article disagreements between studies without lexical or single-sentence NLI opposition remain ~26.6% (`17/64`) of noisy open-web cases. |
| **`action_claim_int8`** (`ReceiptSupervisor`) | `82.7 MB` | `10.9 ms` (per clause) / `27.4 ms` (multi-sentence turn) | **`236/250 (94.4%)` across 3 strictly held-out sets** (`91/100` live organic LLM completions `H100`, `95/100` blinded multi-sentence `BLIND42_COH_100`, `50/50` locked `LOCKED_COH_50`); `297/300 (99.0%)` 10-class speech-act val (`99.7%` FP16 parity) | Fenced code blocks, markdown blockquotes, attributed dialogue, and creative/translation `user_prompt` contexts are masked automatically; unprompted first-person fiction (`user_prompt=""`) with no dialogue attribution is indistinguishable from an unreceipted claim unless `user_prompt` or `[ACTION: verb target]` tags are supplied. |
| **`hazard_int8`** (`OpenVINOHazardClassifier`) | `82.7 MB` | `3.2 ms` | **`128/130 (98.5%)` safe tier assignment** on blinded multi-clause `R-21` (2 blinded LLM raters); `44/50 (88.0%)` exact on `HZD_50` | Conservatively over-escalates ~12–15% of benign technical queries mentioning security/clinical nouns to higher proof tiers. |
| **`ProvenanceGate` (Ed25519)** | `0 MB` (crypto) | `< 0.3 ms` | **`0/100 (0.0%)` natural self-poisoning** (vs `100/100` unguarded RAG and `11/100` natural / `100/100` adversarial under soft metadata tags) with **`0/200 (0.0%)` false rejections on legitimate writes** (`100/100` factual continuity + `100/100` benign reasoning retention vs `98%–99%` loss when blanket-blocking assistant memory) | Enforces cryptographic *origin* (`USER_EXPLICIT`, `TOOL_VERIFIED`), not whether an authenticated human user typed a false statement. |

---

## Head-to-Head Action-Receipt Benchmark (`N=250` Strictly Held-Out Turns)

Evaluated across `LOCKED_COH_50` (`50`), `BLIND42_COH_100` (`100`), and `Organic_Heldout_H100` (`100` live organic LLM completions; `0` training or discovery items; [`external_baselines_benchmark.json`](https://github.com/AlienatedAliens/ProjectLucca/blob/main/logs/test_reports/epistemic_guard/external_baselines_benchmark.json)) on `Core Ultra 9 275HX` + `RTX 5080 Laptop GPU`:

| System | Hardware & Resident Memory | Overall Accuracy (`[95% Wilson CI]`) | Recall / FPR | Multi-Sentence Turn p50 Latency | `Organic_Heldout_H100` |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`epistemic-guard` (`action_claim_int8`)** | **CPU (`0 MiB` GPU VRAM, `82.7 MB` RAM)** | **`236/250 (94.4% [90.8%, 96.6%])`** | `96.7%` / `7.8%` | **`27.4 ms`** | **`91/100 (91.0%)`** |
| **`Mistral-Nemo-Instruct-12B` (`Q5_K_M` LLM Judge)** | GPU (`8,844 MiB` VRAM) | `217/250 (86.8% [82.0%, 90.4%])` | `87.7%` / `14.1%` | `77.9 ms` | `84/100 (84.0%)` |
| **`Microsoft Phi-4-14B` (`Q6_K` LLM Judge)** | GPU (`12,214 MiB` VRAM) | `216/250 (86.4% [81.6%, 90.1%])` | **`100.0%`** / `26.6%` | `75.1 ms` | `79/100 (79.0%)` |
| **Off-the-shelf `DeBERTa-v3-xsmall` NLI** | CPU (`0 MiB` GPU VRAM, `91.1 MB` RAM) | `132/250 (52.8% [46.6%, 58.9%])` | `24.6%` / `20.3%` | `27.5 ms` | `51/100 (51.0%)` |

- **Why off-the-shelf SNLI/MNLI (`52.8%`) fails here:** Standard NLI scores `"Zero tools ran"` vs `"I saved checklist_backup.md"` as `NEUTRAL` rather than `CONTRADICTION` on 75% of phantom actions.
- **Tradeoff vs LLM judges:** `Phi-4-14B` achieved `100.0%` recall (`0` false negatives vs `4` for `epistemic-guard`), at the cost of `12.2 GiB` VRAM, `2.7x` latency, and a `26.6%` false-positive rate on benign offers and figurative idioms. Cloud frontier judges (`GPT-4o`, `Claude`) have **not** been benchmarked here.

---

## Related Ecosystem & Evaluation Disclosures

- **How this differs from adjacent tools:**
  - **[NabaOS](https://github.com/nabaos/nabaos):** Full self-hosted Rust agent operating system with OS process isolation, <10 ms cache routing, and Ed25519-signed static *constitutions*. `epistemic-guard` is a drop-in Python library (`pip install`) for existing Python stacks (`LangGraph`, `PydanticAI`, `MCP`, `OpenAI`) focused on post-generation prose-vs-`ToolReceipt` supervision and RAG syndication deduplication rather than a full OS runtime.
  - **Pre-execution firewalls (`NeMo Guardrails`, `LlamaFirewall`, `Guardrails AI`):** Enforce policy *before* a tool executes; `epistemic-guard` catches post-generation prose claiming a failed or uncalled tool succeeded.
  - **RAG summary faithfulness (`Vectara HHEM`, `Bespoke-MiniCheck`, `Patronus Lynx`):** Score summary-to-chunk entailment (`epistemic-guard` has not been benchmarked head-to-head on RAG summarization leaderboards).
  - **Receipt schemas (`Agent Receipt Standard`, `Nobulex`):** Define portable signed receipt envelopes; `epistemic-guard` pairs Merkle-logged receipts with in-process neural prose checking.
- **Methodology disclosures:** Neural models are **English-only**. All benchmarks were run on a single workstation with zero external production telemetry at initial release; pre-registrations (`WO-46`) use author-administered git + OpenTimestamps SHA-256 locks, and ground-truth $\kappa$ scores reflect **blinded LLM raters**, not human crowdworkers.

---

## License

- **Source Code:** [MIT License](https://github.com/AlienatedAliens/ProjectLucca/blob/main/packages/epistemic-guard/LICENSE) (`Copyright (c) 2026 Sean Maxwell` · [ORCID `0009-0004-0133-0463`](https://orcid.org/0009-0004-0133-0463)).
- **INT8 Model Weights:** Derived from `Apache-2.0` / `MIT` upstream checkpoints (`cross-encoder/nli-MiniLM2-L6-H768`, `cross-encoder/ms-marco-MiniLM-L-6-v2`, and `cross-encoder/nli-deberta-v3-xsmall`); see [`MODEL_NOTICES.md`](https://github.com/AlienatedAliens/ProjectLucca/blob/main/packages/epistemic-guard/MODEL_NOTICES.md).
- **Preprints & Citation:** [`CITATION.cff`](https://github.com/AlienatedAliens/ProjectLucca/blob/main/CITATION.cff) · Zenodo DOIs [`10.5281/zenodo.23649049`](https://doi.org/10.5281/zenodo.23649049), [`10.5281/zenodo.23901452`](https://doi.org/10.5281/zenodo.23901452), [`10.5281/zenodo.23901605`](https://doi.org/10.5281/zenodo.23901605), [`10.5281/zenodo.23901683`](https://doi.org/10.5281/zenodo.23901683).
