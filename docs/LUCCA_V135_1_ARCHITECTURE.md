# Project Lucca — Version 1.35.1 System Architecture Specification
## Sovereign Compound Neurosymbolic Edge Architecture & Multi-Scale Cognitive Substrate

**Title:** Project Lucca v1.35.1 System Architecture & Technical Specification  
**Version:** 1.35.1-stable  
**Release Tag:** `v1.35.1-stable`  
**Git Commit:** `f5d4910`  
**Date:** October 4, 2026  
**Authors:** Project Lucca Architecture Notes  
**Target Platform:** Sovereign Consumer Edge (NVIDIA GeForce RTX 5080 Laptop GPU, 16,303 MiB GDDR7 VRAM, Headless Compute)  
**Status:** Canonical System Architecture  

---

## 1. Executive Summary & Design Principles

Project Lucca is an autonomous, sovereign personal systems companion and research engineer designed to execute on consumer hardware with zero telemetry leaks, subscription APIs, or external cloud compute dependencies.

Version 1.35.1 establishes the **Multi-Scale Compound Neurosymbolic Edge Architecture**, focusing on controlled empirical validation, deterministic supervision, and cryptographic memory safety:
1. **Cryptographic Memory Verification at Read-Time:** Replaces unkeyed SHA-256 column checks with a two-stage HMAC-SHA256 verification pipeline in `HybridRetriever`. SQLite row mutations are detected via constant-time HMAC comparison over canonical JSON payloads and surfaced via `RuntimeError` rather than silently dropped.
2. **Deterministic Output & Claim Supervision:** Hardens the `TruthInReceiptMatcher` against false aborts across analytical idioms, possessive determinations, and epistemic hedges, verified across a 40-sentence formal battery with 100% test pass rate (71/71 tests in suite).
3. **The 12B Scale Inversion Under Greedy Decoding:** Documents that under greedy decoding ($T=0.0$), extended unslotted thinking scratchpads degrade Gemma 4 12B on competition mathematics (dropping from 90.0% direct to 58.0% thinking, McNemar $p = 4.66 \times 10^{-10}$, 32:0 discordant ratio), whereas direct raw generation solves 90.0% of problems in 12.9s.
4. **Edge Truncation Isolation:** Demonstrates that doubling the PAL code token cap from 1,024 to 2,048 tokens rescues edge models from premature AST termination, lifting E2B strict accuracy from 70.0% to 77.0% ($p=0.0156$) and E4B strict accuracy from 73.0% to 83.0% (and 92.0% lenient), achieving parity with Thinking Mode with 40% token savings.
5. **Controlled Held-Out Generalization:** Validates the task router on $n=100$ fresh, unseen competition mathematics problems ([`data/benchmarks/math_fresh_heldout_500.jsonl`](file:///c:/Projects/ProjectLucca/data/benchmarks/math_fresh_heldout_500.jsonl)) with Gemma 4 E4B, achieving **88.0% strict CAS accuracy** [95% Wilson CI: 79.6%, 93.4%] with only 2.0% truncations, showing no statistically detectable drop from the dev split.

---

## 2. Multi-Scale Neural Substrate

Project Lucca v1.35.1 supports three validated, headless neural deployment tiers served via `llama-server.exe` with flash attention, unslotted greedy decoding, and embedded Jinja templating:

| Attribute | Gemma 4 12B Unified | Gemma 4 E4B Sovereign Core | Gemma 4 E2B Ultra-Edge |
| :--- | :--- | :--- | :--- |
| **Model Weight File** | `gemma-4-12b-heretic-Q6_K.gguf` | `gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf` | `Gemma4-E2B-Heretic-Sinhala.i1-Q6_K.gguf` |
| **Parameter Scale** | 12.0 Billion Effective Parameters | 4.5 Billion Effective Parameters | 2.0 Billion Effective Parameters |
| **Quantization** | 6-bit K-quants (`Q6_K`) | 6-bit K-quants (`Q6_K`) | 6-bit K-quants (`Q6_K`) |
| **Active VRAM Footprint** | **9,972 MiB (61.2%)** | **4,382 MiB (26.9%)** | **2,260 MiB (13.9%)** |
| **Free VRAM Headroom** | 6,331 MiB (38.8%) | **11,921 MiB (73.1%)** | **14,043 MiB (86.1%)** |
| **Time-to-First-Token (P50)**| 286.9 ms | **86.1 ms** | **73.2 ms** |
| **Sustained Throughput** | 37.18 tok/s | **80.76 – 103.0 tok/s** | **126.1 – 169.1 tok/s** |
| **Native Context Length** | 16,384 tokens | 16,384 tokens | 16,384 tokens |
| **Target Role** | Complex symbolic escalation | Default sovereign desktop core | Ambient listener & low-power companion |

```bash
# Canonical Daemon Invocation Template
llama-server.exe \
  --model <MODEL_PATH> \
  --n-gpu-layers 99 \
  --ctx-size 16384 \
  --flash-attn on \
  --jinja \
  --host 127.0.0.1 \
  --port 8080 \
  --no-webui
```

---

## 3. Cryptographic Memory & Provenance Substrate

### 3.1 Two-Stage Read-Time HMAC Verification Pipeline
In Lucca v1.35.1, the memory retrieval pathway ([`src/lucca/memory/retrieval.py`](file:///C:/projects/projectlucca/src/lucca/memory/retrieval.py)) enforces tamper evidence across all vector (dense KNN) and lexical (BM25 FTS) memory hits before returning records to the orchestrator:

```
[RetrievalQuery] 
       │
       ▼
[Hybrid Search: Dense KNN + BM25 FTS via Reciprocal Rank Fusion]
       │
       ▼
For each candidate memory record:
       │
       ├─► [Stage 1: Content SHA-256 Fast-Fail]
       │     SHA256(memories.content) == provenance_envelopes.content_sha256?
       │     ├── NO  ──► Emit "stage=content_sha256" error ──► RAISE RuntimeError
       │     └── YES ──► Proceed to Content Match Gate
       │
       ├─► [Content Match Gate]
       │     memories.content == payload_json.content?
       │     ├── NO  ──► Emit "stage=payload_content_mismatch" ──► RAISE RuntimeError
       │     └── YES ──► Proceed to Cryptographic HMAC
       │
       └─► [Stage 2: Constant-Time HMAC-SHA256 Verification]
             1. Key Derivation: derived_key = HKDF(master_key, salt="lucca-v2", info="prov/" + provenance)
             2. Canonical Bytes: JSON(canonical_dict, sort_keys=True, compact_separators)
             3. Expected Signature: Base64(HMAC-SHA256(derived_key, canonical_bytes))
             4. hmac.compare_digest(stored_signature, expected_signature)?
                   ├── NO  ──► Emit "stage=hmac" error ──► RAISE RuntimeError
                   └── YES ──► Memory Hit Verified ──► Surface to Agent
```

### 3.2 Non-Silent Tamper Surfacing
Unlike prior versions which silently suppressed corrupted rows (hiding database injection attacks from the operator), v1.35.1 immediately halts the search operation with an explicit exception:
```python
raise RuntimeError(
    f"Memory integrity violation detected for memory_id={mid}. "
    f"The record may have been tampered with. Retrieval aborted."
)
```
Verified across 5 deterministic unit tests in [`tests/test_memory_hmac_tamper.py`](file:///C:/projects/projectlucca/tests/test_memory_hmac_tamper.py).

---

## 4. Output Supervision & Deontic Grounding Substrate

### 4.1 Truth-In-Receipt Matcher Architecture
The supervisor ([`src/lucca/sandbox/output_supervisor.py`](file:///C:/projects/projectlucca/src/lucca/sandbox/output_supervisor.py)) performs sub-millisecond per-clause AST verification on streaming assistant tokens before spoken TTS chunk emission.

```mermaid
flowchart TD
    TokenStream["Streaming Model Tokens"] --> ClauseSplitter["Clause Boundary Detection (:;,.\n)"]
    ClauseSplitter --> ClauseEval["evaluate_clause() Engine"]
    
    ClauseEval --> Step1{"Future / Intentional?<br/>(I will, I plan to, I'm about to)"}
    Step1 -- Yes --> Pass["Pass (Not completed action)"]
    Step1 -- No --> Step2{"Analytical / Idiomatic Non-Action?<br/>(ran a check, moved mountains, took care of)"}
    
    Step2 -- Yes --> Pass
    Step2 -- No --> Step3{"Epistemic Hedge Present?<br/>(I think I, I believe I, might have)"}
    
    Step3 -- Yes --> Pass
    Step3 -- No --> Step4{"Past Session Context?<br/>(Yesterday, Last session)"}
    
    Step4 -- Yes --> Pass
    Step4 -- No --> Step5{"Negation Present?<br/>(did not, never, haven't)"}
    
    Step5 -- Yes --> Pass
    Step5 -- No --> Step6{"Stem Match in ACTION_VERBS?<br/>(create, delete, save, send, move)"}
    
    Step6 -- No --> Pass
    Step6 -- Yes --> ReceiptCheck{"ToolReceipt Present in Session<br/>matching (tool, target, status=OK)?"}
    
    ReceiptCheck -- Yes --> Pass
    ReceiptCheck -- No --> Abort["TRIGGER Mid-Utterance Abort<br/>Drop TTS Queue, Record Breach"]
```

### 4.2 Pattern Widening & Battery Verification
v1.35.1 formalizes coverage across:
- **21 Action Verbs:** `create`, `delete`, `remove`, `write`, `save`, `send`, `upload`, `move`, `copy`, `execute`, `modify`, `update`, `install`, `post`, `run`, `start`, `stop`, `close`, `build`, `compile`, `deploy`.
- **Hedge Suppression Regex:** `(?:i\s+think\s+i|i\s+believe\s+i|not\s+(?:entirely\s+)?certain|might\s+have|could\s+have|may\s+have)`.
- **Idiomatic Non-Actions:** Covers analytical idioms (`ran a check`), possessives (`placed my trust in`), and physical metaphors (`closed her eyes`).
- **Formal 40-Sentence Battery:** 10 grounded, 10 ungrounded, 10 paraphrases, 10 honest/hedged/negated sentences verified in [`tests/test_truth_in_receipt_battery.py`](file:///C:/projects/projectlucca/tests/test_truth_in_receipt_battery.py) (**66/66 unit tests passing**).

---

## 5. Dynamic Task Router & Neurosymbolic Execution

### 5.1 Formal Routing Specification
The task router enforces the following empirical dispatch logic:

$$\text{Router}(M, T) = \begin{cases} 
\text{Direct Raw Generation (R0)} & \text{if } M = \text{12B} \\ 
\text{PAL in Docker (P2 @ 2,048 cap)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Arithmetic/Word} \\ 
\text{PAL in Docker (P2 @ 2,048 cap)} & \text{if } M = \text{E4B} \land T = \text{Competition Math (Efficiency)} \\ 
\text{Thinking Mode (R1 @ 6,144 cap)} & \text{if } M = \text{E4B} \land T = \text{Competition Math (Peak Strict)} \\ 
\text{Thinking Mode (R1 @ 6,144 cap)} & \text{if } M = \text{E2B} \land T = \text{Competition Math} 
\end{cases}$$

### 5.2 Mechanistic Rationales & Trade-Offs
1. **For 12B Unified:** Raw generation achieves 90.0% strict accuracy with 660 tokens in 12.9s. Under greedy decoding ($T=0.0$), unconstrained thinking triggers circular re-verification loops that crash accuracy to 58.0% (32:0 McNemar discordant ratio, $p = 4.66 \times 10^{-10}$).
2. **For E4B / E2B Arithmetic (GSM-Symbolic):** PAL in Docker absorbs parameter contraction, equalizing 2B/4.5B models with 12B (91%–94% vs. 95%).
3. **The E4B Competition Math Trade-Off:**
   - **PAL @ 2,048 cap:** 83.0% strict / 92.0% lenient, 1,070 tokens/item, 10.1s latency (40% fewer tokens, 1.6× faster, ties thinking mode strict with $p=0.7905$). Pareto-optimal for resource-constrained deployment.
   - **Thinking Mode @ 6k cap:** 85.0%–88.0% strict / 86.0%–92.0% lenient, ~1,785–2,066 tokens/item, ~16.4–19.3s latency. Preferred when maximizing strict CAS accuracy regardless of compute budget.
4. **For E2B Competition Math:** Thinking Mode @ 6k leads PAL @ 2k by 7 points strict (84.0% vs. 77.0%), justifying the higher token expenditure on ultra-edge silicon.
5. **Redundancy of P3 (PAL + Thinking):** Pre-thinking before synthesizing Python code provides zero additive lift (76% vs 77%), while consuming 2.4× more tokens and running 2.5× slower.

---

## 6. Comprehensive Benchmark Scorecard

```
========================================================================================================================
CONSOLIDATED BENCHMARK MATRIX ACROSS THE 3 PARAMETER SCALES (PROJECT LUCCA v1.35.1)
========================================================================================================================
Benchmark Suite             Metric / Arm               Gemma 4 12B          Gemma 4 E4B          Gemma 4 E2B
------------------------------------------------------------------------------------------------------------------------
Spec 100 System Suite        Overall Accuracy (Mean)    84.0% (82–86%)*      85.0%                81.0%
                             Tool Precision / Recall    15 / 15 (100.0%)     15 / 15 (100.0%)     10 / 15 (100% P / 67% R)
                             OS / Host Guardrails       10 / 10 (100.0%)     10 / 10 (100.0%)     10 / 10 (100.0%)
                             Content Safety Refusal**   9 / 10 (90.0%)       3 / 10 (30.0%)       6 / 10 (60.0%)
                             Throughput (P50)           37.18 tok/s          80.76 tok/s          126.1 tok/s

GSM-Symbolic (100-strat)     PAL P2 Accuracy (Docker)   95.0%                94.0%                91.0%
                             Direct R0 Accuracy         93.0%                91.0%                81.0%
                             PAL Lift (Delta)           +2.0 pp (NS)         +3.0 pp (NS)         +10.0 pp (p = 0.021)

HumanEval Canonical 164      Raw Pass@1                 155 / 164 (94.5%)    144 / 164 (87.8%)    123 / 164 (75.0%)
                             Assisted Pass@1            154 / 164 (93.9%)    141 / 164 (86.0%)    126 / 164 (76.8%)

MATH-500 Dev (100 items)    Direct R0 (Strict / Len)   90.0% / 93.0%        50.0% / 50.0%        51.0% / 51.0%***
                             PAL P2 @ 1k (Historical)   85.0% / 87.0%        73.0% / 77.0%        70.0% / 75.0%
                             PAL P2 @ 2k (Uncapped Code) —                   83.0% / 92.0%        77.0% / 85.0%
                             PAL P3 (PAL + Thinking)    —                    —                    76.0% / 84.0%
                             Thinking R1 @ 4k           —                    85.0% / 86.0%        81.0% / 82.0%
                             Thinking R1 @ 6k           58.0% / 59.0%        —                    84.0% / 85.0%

MATH-500 Fresh Held-Out      Strict CAS Equivalence     Not Run              88.0% [79.6, 93.4]†  Not Run
(Unseen 100, Step 5)         Lenient Normalization      Not Run              92.0% [84.4, 96.2]   Not Run
                             Active Arm                 —                    Thinking R1 @ 6k     —
                             Truncation Rate            —                    2.0% (2 / 100)       —
========================================================================================================================
* 12B Spec 100: 4 runs yielded 86%, 82%, 84%, 84% (mean 84.0% ± 2.0 pp noise floor under T=0.6).
** Content safety reflects compliance on uncensored fine-tunes; E4B refuses only 30% of general content safety probes.
*** E2B R0 was capped at 1,536 tokens and truncated 26% of items; part of the baseline gap reflects token starvation.
† Held-out evaluation was executed exclusively on Gemma 4 E4B; 12B and E2B were not evaluated on the held-out split.
```

---

## 7. Configuration & File Manifest

### Core Modules
* [`src/lucca/memory/retrieval.py`](file:///C:/projects/projectlucca/src/lucca/memory/retrieval.py): Two-stage HMAC verification and hybrid search.
* [`src/lucca/memory/store.py`](file:///C:/projects/projectlucca/src/lucca/memory/store.py): Memory store coordinator passing `master_key` to retriever.
* [`src/lucca/memory/signers.py`](file:///C:/projects/projectlucca/src/lucca/memory/signers.py): HKDF key derivation and payload canonicalization.
* [`src/lucca/sandbox/output_supervisor.py`](file:///C:/projects/projectlucca/src/lucca/sandbox/output_supervisor.py): TruthInReceiptMatcher and deontic lookahead engine.
* [`scripts/run_pal_off_ablation.py`](file:///C:/projects/projectlucca/scripts/run_pal_off_ablation.py): Comprehensive factorial ablation harness.

### Test Suites
* [`tests/test_memory_hmac_tamper.py`](file:///C:/projects/projectlucca/tests/test_memory_hmac_tamper.py): 5/5 HMAC tamper and verification tests.
* [`tests/test_truth_in_receipt_battery.py`](file:///C:/projects/projectlucca/tests/test_truth_in_receipt_battery.py): 40-sentence supervisor test battery.
* [`tests/test_output_supervisor.py`](file:///C:/projects/projectlucca/tests/test_output_supervisor.py): 26 deontic and session unit tests.
