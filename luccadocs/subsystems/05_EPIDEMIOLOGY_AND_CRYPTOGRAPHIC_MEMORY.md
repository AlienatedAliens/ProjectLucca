# Subsystem Reference Manual: 05 — Cryptographic Memory & Bi-Temporal Epistemology

**Subsystem:** `src/lucca/memory/`  
**Version:** 1.3.0  
**Architectural Tier:** Autobiographical Memory & Provenance Governance  
**Hardware Placement:** SQLite WAL (`data/memory.sqlite`), Intel AI Boost NPU (`sqlite-vec`), Host CPU  

---

## 1. Subsystem Architecture Overview

The `memory` subsystem provides Project Lucca with long-term autobiographical continuity while mathematically preventing hallucinated knowledge persistence. Every memory entry is cryptographically sealed with a domain-specific digital signature, indexed into a hybrid vector-lexical store, prioritized under a strict multi-factor hierarchy, and governed by bi-temporal supersession rules.

```mermaid
flowchart TD
    subgraph IngestionBoundary ["Memory Ingestion Boundary"]
        US["User Speech (USER_EXPLICIT)"] --> SG1["UserSpeechSigner"]
        FD["User Derived Fact (USER_DERIVED)"] --> SG2["DerivedFactSigner"]
        TR["Tool Action / Receipt (ASSISTANT_ACTION)"] --> SG3["ToolResultSigner"]
        LA["MicroScheme Assertion (LISP_ASSERTION)"] --> SG4["LispAssertionSigner"]
        AU["Assistant Speech (ASSISTANT_UTTERANCE)"] --> SG5["AssistantUtteranceSigner"]
        UN["Unverified LLM Narration (LLM_NARRATION)"] --> NO_SIG["NO SIGNER EXISTS"]
    end

    subgraph SecurityGate ["Provenance Gate (src/lucca/memory/gate.py)"]
        SG1 & SG2 & SG3 & SG4 & SG5 --> PG["ProvenanceGate Validator"]
        NO_SIG -->|REJECTED (ADR-006)| DROP["Dropped with ProvenanceViolation"]
        PG -->|Cryptographic Envelope Verified| SE["Segregate Grounding Eligibility"]
    end

    subgraph GroundingSegregation ["Grounding vs Continuity Segregation (D-MEM-04)"]
        SE -->|Actions / Facts / Receipts| GE1["grounding_eligible = 1<br>(Axiomatic Evidence)"]
        SE -->|Assistant Utterances| GE0["grounding_eligible = 0<br>(Continuity Only)"]
    end

    subgraph HybridStorage ["Hybrid SQLite Engine (data/memory.sqlite)"]
        GE1 & GE0 --> WAL["SQLite WAL Table: memories"]
        WAL --> VEC["sqlite-vec (384-D OpenVINO Embeddings on Intel NPU)"]
        WAL --> FTS["FTS5 BM25 Lexical Inverted Index"]
    end

    subgraph RetrievalLayer ["Retrieval & Fusion Layer (retrieval.py)"]
        VEC & FTS --> RRF["Reciprocal Rank Fusion (RRF K=60)"]
        RRF --> MF["Multi-Factor Prioritization (2,048-Token Quota)"]
        MF --> CONT["Frontier Context Injection"]
    end
```

---

## 2. Cryptographic Provenance Matrix (`ADR-006`)

Unverified language model generation is prohibited from creating persistent memories. The `ProvenanceGate` strictly enforces that every written entry carries an authentic digital signature:

| Provenance Tier | Authorized Domain Signer | Verification Requirement | `grounding_eligible` |
| :--- | :--- | :--- | :---: |
| **`USER_EXPLICIT`** | `UserSpeechSigner` | ASR transcript signed from physical microphone turn. | **1** |
| **`USER_DERIVED`** | `DerivedFactSigner` | Verbatim quote verified against signed user transcript. | **1** |
| **`TOOL_VERIFIED`** | `ToolResultSigner` | Signed container RPC output receipt. | **1** |
| **`LISP_ASSERTION`**| `LispAssertionSigner` | MicroScheme pure rule assertion `(assert ...)`. | **1** |
| **`ASSISTANT_ACTION`**| `ToolResultSigner` | Verifiable executed tool receipt. | **1** |
| **`ASSISTANT_UTTERANCE`**| `AssistantUtteranceSigner` | Lucca's own spoken words (Rung A1 autobiographical memory). | **0** |
| **`ASSISTANT_BELIEF`**| `AssistantUtteranceSigner` | Explicit belief statement; requires evidence pointer. | **0** |
| **`LLM_NARRATION`** | **None** | **Strictly rejected.** Freeform hallucinated facts cannot be committed. | **N/A** |

### 2.1 The Epistemic Grounding Invariant (`D-MEM-04`)
To prevent the model's past speech from becoming "ground truth" that corrupts future inferences:
- **`memory_eligible = 1`:** Allows Lucca to remember what she previously said for conversational retrospection (*"What did you tell me earlier about Python?"*).
- **`grounding_eligible = 0`:** Excludes past speech from Belnap evidential truth calculations. Her past words can never be used as evidence to prove a factual claim.

---

## 3. Hybrid Storage Topology: `sqlite-vec` + `FTS5` BM25

All memory records reside in `data/memory.sqlite` operated in Write-Ahead Logging (WAL) mode:

1. **Dense Vector Store (`sqlite-vec`):**
   - Embeddings: 384-dimensional dense vectors generated via `all-MiniLM-L6-v2`.
   - Hardware Offload: Vector embeddings execute natively on the **Intel(R) AI Boost NPU** via OpenVINO (`device="NPU"`), consuming zero GPU VRAM.
   - Distance Metric: Cosine similarity via `vec0` virtual table.
2. **Sparse Lexical Store (`FTS5`):**
   - Full-text search with Porter stemmer and BM25 relevance scoring.
   - Accurately captures exact keywords, IDs, filenames, and numerical constants.
3. **Reciprocal Rank Fusion (RRF $K=60$):**
   $$RRF\_Score(d) = \frac{1}{60 + \text{Rank}_{vec}(d)} + \frac{1}{60 + \text{Rank}_{fts}(d)}$$

---

## 4. Multi-Factor Prioritization & 2,048-Token Quota (`D-MEM-03`)

To guarantee prompt discipline and preserve GPU KV-cache headroom, retrieved memories are clamped to a strict **2,048-token quota**. Candidate memories are ranked by composite score:

$$\text{Priority} = w_1 \cdot \text{ProvenanceScore} + w_2 \cdot \text{ValidityScore} + w_3 \cdot \text{RRF\_Score} + w_4 \cdot \text{RecencyDecay}$$

- **Provenance Score:** `USER_EXPLICIT` ($1.0$) $>$ `TOOL_VERIFIED` ($0.9$) $>$ `USER_DERIVED` ($0.8$) $>$ `ASSISTANT_ACTION` ($0.7$).
- **Validity Window:** Time-decayed half-life discounting entries with expired validity windows.
- **Recency Decay:** Exponential half-life ($t_{1/2} = 14\,\text{days}$) favoring recent interactions while preserving high-importance anchors.

---

## 5. Bi-Temporal Supersession & Human Review Queue

Real-world facts mutate over time (e.g. user changes timezone, updates a project path). Memory updates execute via bi-temporal supersession:

```mermaid
stateDiagram-v2
    [*] --> ACTIVE: "Grounded Memory Commit"
    ACTIVE --> SUPERSEDED: "supersede(old_id, new_id, reason)"
    ACTIVE --> REVIEW_QUEUE: "Trigger Safety Conflict Criteria"
    REVIEW_QUEUE --> SUPERSEDED: "Operator Approves in Settings GUI"
    REVIEW_QUEUE --> ACTIVE: "Operator Rejects (Retains Original)"
    SUPERSEDED --> ARCHIVED: "Nightly Rollup (>30 days, score < 0.2)"
    ARCHIVED --> [*]
```

### 5.1 Safety Criteria Triggering Review
Supersession requests automatically enter the Studio Review Queue if they:
1. Mutate core persona invariants or user safety preferences.
2. Overwrite an entry with high historical importance score ($\ge 0.85$).
3. Introduce an evidential contradiction ($\mathbf{B}$) in the Belnap bilattice.

---

## 6. Two-Stage HMAC-SHA256 Read-Time Verification & Persistent Quarantine (`D-MEM-05`)

As formalized in v1.35.2+, memory retrieval enforces cryptographic tamper evidence across all vector (dense KNN) and lexical (BM25 FTS) hits before returning records to the orchestrator:

```
[RetrievalQuery] 
       │
       ▼
[Hybrid Search: Dense KNN + BM25 FTS via Reciprocal Rank Fusion]
       │
       ├─► [Pre-Filter Known Quarantined IDs] ──► Exclude rows in memory_quarantine table
       ▼
For each candidate memory record:
       │
       ├─► [Stage 1: Content SHA-256 Fast-Fail]
       │     SHA256(memories.content) == provenance_envelopes.content_sha256?
       │     ├── NO  ──► Emit "stage=content_sha256" error ──► Quarantine row to DB & continue
       │     └── YES ──► Proceed to Content Match Gate
       │
       ├─► [Content Match Gate]
       │     memories.content == payload_json.content?
       │     ├── NO  ──► Emit "stage=payload_content_mismatch" ──► Quarantine row to DB & continue
       │     └── YES ──► Proceed to Cryptographic HMAC
       │
       └─► [Stage 2: Constant-Time HMAC-SHA256 Verification]
             1. Key Derivation: derived_key = HKDF(master_key, salt="lucca-v2", info="prov/" + provenance)
             2. Canonical Bytes: JSON(canonical_dict, sort_keys=True, compact_separators)
             3. Expected Signature: Base64(HMAC-SHA256(derived_key, canonical_bytes))
             4. hmac.compare_digest(stored_signature, expected_signature)?
                   ├── NO  ──► Emit "stage=hmac" error ──► Quarantine row to DB & continue
                   └── YES ──► Memory Hit Verified ──► Return to Orchestrator
```

### 6.1 Persistent Quarantine & Non-Silent Alerting
1. **Persistent DB Quarantine:** Corrupted rows are inserted into the SQLite `memory_quarantine` table `(memory_id, entry_id, reason, stage, quarantined_at)`. Quarantined IDs are loaded on boot and excluded from subsequent searches.
2. **Integrity Surfacing API:** Programmatically surfaced via `HybridRetriever.get_integrity_status_report()`, avoiding silent data corruption while maintaining turn availability.
3. **Master Key Persistence:** Master keys are generated via `secrets.token_bytes(32)` and persisted to `data/keys/master.key` with `0600` permissions.
4. **Key Migration Tool:** Supported via `lucca-admin memory migrate-keys` to re-sign records when rotating keys without data loss.

