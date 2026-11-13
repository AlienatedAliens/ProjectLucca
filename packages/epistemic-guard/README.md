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

# Optional: download the ~188 MB OpenVINO INT8 neural pack (SHA-256 verified)
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

All three optional neural classifiers run in-process via OpenVINO INT8 (`CPU`, `GPU`, or `NPU`) with pinned SHA-256 manifests. If weights are not installed, `epistemic-guard` emits an explicit `EpistemicModelUnavailableWarning` (or raises `ModelIntegrityError` when `require_neural=True`) rather than silently degrading.

| Component | INT8 Size | CPU p50 Latency | Locked Holdout Result | Known Failure Modes |
| :--- | :---: | :---: | :--- | :--- |
| **`ProvenanceGate` (Ed25519)** | `0 MB` (crypto) | `< 0.3 ms` | `0/100 (0.0%)` natural self-poisoning vs `100/100` in unguarded RAG | Does not fact-check false statements explicitly asserted by an authenticated human user (`USER_EXPLICIT`). |
| **`action_claim_int8`** (`ReceiptSupervisor`) | `82.7 MB` | `10.9 ms` | `50/50 (100.0%)` on `LOCKED_COH_50`; `99.0%` 10-class speech-act accuracy (`99.7%` FP16 parity) | Creative fiction or translated dialogue containing first-person action verbs should pass `user_prompt` context or use `[ACTION: verb target]` tags. |
| **`hazard_int8`** (`OpenVINOHazardClassifier`) | `82.7 MB` | `3.2 ms` | `128/130 (98.5%)` safe tier assignment on multi-clause `R-21`; `44/50 (88.0%)` exact on `HZD_50` | Conservatively over-escalates ~12–15% of benign technical queries mentioning security/clinical nouns to higher proof tiers. |
| **`web_evidence_int8`** + `corroborate_sources` | `23.1 MB` | `3.0 ms` | `113/128 (88.3%)` unseen-topic 3-class stance accuracy; `46/64 (71.9%)` end-to-end burden accuracy & `56/64 (87.5%)` dispute accuracy on live-scraped open web (`real_web_v2`) | Subtle implicit directional contradictions across technical prose without explicit dispute cues remain bounded (~28% end-to-end open-web error rate). |

---

## License

- **Source Code:** [MIT License](LICENSE) (`Copyright (c) 2026 Sean Maxwell`).
- **INT8 Model Weights:** Derived from `Apache-2.0` upstream checkpoints (`cross-encoder/nli-MiniLM2-L6-H768` and `cross-encoder/ms-marco-MiniLM-L-6-v2`); see [`MODEL_NOTICES.md`](MODEL_NOTICES.md).
