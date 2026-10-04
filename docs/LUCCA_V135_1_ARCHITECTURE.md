# Project Lucca — Version 1.35.2 System Architecture Specification
## Multi-Scale Compound Neurosymbolic Edge Architecture & Cognitive Substrate

**Title:** Project Lucca v1.35.2 System Architecture & Technical Specification  
**Version:** 1.35.2-stable  
**Release Tag:** `v1.35.2-stable`  
**Git Commit:** `4fa5e9e` (closeout baseline: `f20537fe`; audit remediation commit: `4fa5e9e`)  
**Date:** October 4, 2026  
**Authors:** Project Lucca Architecture Notes  
**Target Platform:** Consumer Edge (NVIDIA GeForce RTX 5080 Laptop GPU, 16,303 MiB GDDR7 VRAM, Headless Compute)  
**Status:** System Architecture Specification (v1.35.2)  

---

## 1. Executive Summary & Design Principles

Project Lucca is a local personal systems companion and research engineer designed to execute on consumer hardware with zero external telemetry dependencies or cloud subscriptions.

Version 1.35.2 formalizes the **Multi-Scale Compound Neurosymbolic Edge Architecture**, focusing on controlled empirical validation, deterministic supervision, and cryptographic memory safety:
1. **Cryptographic Memory Verification & Persistent Quarantine:** Replaces unkeyed SHA-256 column checks with a two-stage HMAC-SHA256 verification pipeline in `HybridRetriever`. SQLite row mutations or signature mismatches are detected via constant-time HMAC comparison over canonical JSON payloads and quarantined into the persistent SQLite `memory_quarantine` table with user-facing alerts, rather than crashing with unhandled exceptions or causing silent amnesia.
2. **Deterministic Output & Claim Supervision:** Hardens the `TruthInReceiptMatcher` against false aborts across analytical idioms, possessive determinations, and epistemic hedges, verified across a 40-sentence formal battery with 100% test pass rate (40/40 in `test_truth_in_receipt_battery.py`; 66/66 combined supervisor unit tests; 74/74 including 8 deontic sandbox tests).
3. **The 12B Scale Inversion Under Greedy Decoding:** Documents that under greedy decoding ($T=0.0$), extended unslotted thinking scratchpads degrade Gemma 4 12B on competition mathematics (dropping from 90.0% direct to 58.0% thinking, McNemar $p = 4.66 \times 10^{-10}$, 32:0 discordant ratio), whereas direct raw generation solves 90.0% of problems in 12.9s.
4. **Edge Truncation Isolation:** Demonstrates that doubling the PAL code token cap from 1,024 to 2,048 tokens rescues edge models from premature code truncation, lifting E2B strict accuracy from 70.0% to 77.0% ($p=0.0156$) and E4B strict accuracy from 73.0% to 83.0% (and 92.0% lenient) on the dev split, achieving parity with Thinking Mode with 40% token savings.
5. **Fresh Held-Out Evaluation & Router Nature:** Evaluates $n=100$ fresh, unseen competition mathematics problems ([`data/benchmarks/math_fresh_heldout_500.jsonl`](file:///c:/Projects/ProjectLucca/data/benchmarks/math_fresh_heldout_500.jsonl)) with Gemma 4 E4B across both candidate arms: Thinking Mode (R1 @ 6k) achieves **88.0% strict CAS / 92.0% lenient** [95% Wilson CI: 79.6%, 93.4%], while PAL (P2 @ 2k) achieves **73.0% strict / 83.0% lenient** (discordant pairs 4:19 strict, exact binomial $p = 0.0026$). Transparently notes that the benchmark router dispatches via oracle dataset label lookup (`benchmark == 'gsm_symbolic'` vs `'math500'`), and real-world deployment requires an in-the-wild task-type intent classifier.

---

## 2. Multi-Scale Neural Substrate

Project Lucca v1.35.2 supports three validated, headless neural deployment tiers served via `llama-server.exe` with flash attention, unslotted greedy decoding ($T=0.0$) for formal reasoning benchmarks (and $T=0.6$ for conversational / Spec 100 evaluations), and embedded Jinja templating:

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

### 3.1 Two-Stage Read-Time HMAC Verification & Persistent Quarantine Pipeline
In Lucca v1.35.2, the memory retrieval pathway ([`src/lucca/memory/retrieval.py`](file:///C:/projects/projectlucca/src/lucca/memory/retrieval.py)) enforces cryptographic tamper evidence across all vector (dense KNN) and lexical (BM25 FTS) memory hits before returning records to the orchestrator:

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

### 3.2 Non-Silent Tamper Surfacing & Amnesia Defense
Rather than silently dropping bad rows (hiding database injection attacks) or raising an unhandled `RuntimeError` (which disabled all memory retrieval whenever a key rotated or a single row was modified), v1.35.2 implements **persistent database quarantine with proactive user surfacing**:
1. **Persistent DB Quarantine:** Corrupted rows are inserted into SQLite `memory_quarantine` table with columns `(memory_id, entry_id, reason, stage, quarantined_at)`. Quarantined IDs are loaded on boot and excluded from subsequent searches across sessions.
2. **Integrity Surfacing & Alert API:** A security notice (`"Security notice: N memories failed cryptographic integrity checks and were quarantined."`) is emitted programmatically via `HybridRetriever.get_integrity_status_report()`. While retriever and backend logs capture this alert on every retrieval turn, end-user front-end UI widget rendering remains an active integration item.
3. **Key Persistence:** Master keys are generated cryptographically (`secrets.token_bytes(32)`) and persisted to disk at `data/keys/master.key` with `0600` permissions. All public dev fallback constants (`b"0123456789..."`) have been eliminated from `main.py`, `service.py`, `signer_factory.py`, and `admin.py`.
4. **Resilient Retrieval:** Uncorrupted memories continue to retrieve successfully alongside new memories committed with the active master key.
5. **Key-at-Rest Co-Location Threat Model:** The master key file (`data/keys/master.key`) sits adjacent to the database file it protects (`data/memory.sqlite`) within the host filesystem. While restricted via `0600` file permissions, this co-location means HMAC-SHA256 memory envelopes defend against unprivileged processes, application-level tampering, and unauthorized SQL column modifications, but do not protect against an attacker with root host read access to the `data/` directory tree. Future versions may evaluate DPAPI / TPM envelope sealing to mitigate host-level co-location.
6. **Cryptographic Key Migration CLI (`migrate-keys`):** To prevent silent amnesia or mass quarantine when migrating databases from historical development runs or rotating master keys, [`lucca-admin memory migrate-keys`](file:///c:/Projects/ProjectLucca/src/lucca/memory/migration_tool.py) validates content SHA-256 integrity for legacy records signed with dev fallback keys (`b"0123456789abcdef..."`), re-computes HMAC signatures under the active master key, atomically updates `provenance_envelopes`, and purges quarantined records. Operators can inspect quarantine status via `lucca-admin memory quarantine-list`.

Verified across 11 deterministic unit tests in [`tests/test_memory_hmac_tamper.py`](file:///c:/Projects/ProjectLucca/tests/test_memory_hmac_tamper.py), [`tests/test_memory_key_persistence_and_restart.py`](file:///c:/Projects/ProjectLucca/tests/test_memory_key_persistence_and_restart.py), and [`tests/test_memory_key_migration.py`](file:///c:/Projects/ProjectLucca/tests/test_memory_key_migration.py).

---

## 4. Output Supervision & Deontic Grounding Substrate

### 4.1 Truth-In-Receipt Matcher Architecture
The supervisor ([`src/lucca/sandbox/output_supervisor.py`](file:///C:/projects/projectlucca/src/lucca/sandbox/output_supervisor.py)) performs deterministic regex-based clause-level verification on streaming assistant tokens before spoken TTS chunk emission.

```mermaid
flowchart TD
    TokenStream["Streaming Model Tokens"] --> ClauseSplitter["Clause Boundary Detection (:;,.\n)"]
    ClauseSplitter --> ClauseEval["evaluate_clause() Engine"]
    
    ClauseEval --> Step1{"Future / Intentional?<br/>(I will, I plan to, I'm about to)"}
    Step1 -- Yes --> Pass["Pass (Not completed action)"]
    Step1 -- No --> Step2{"Analytical / Idiomatic Non-Action?<br/>(ran a check, saved the day, closed my eyes)"}
    
    Step2 -- Yes --> Pass
    Step2 -- No --> Step3{"Epistemic Hedge Present?<br/>(I think I, I believe I, might have)"}
    
    Step3 -- Yes --> PassHedge["Pass by Policy (Hedge Exemption)"]
    Step3 -- No --> Step4{"Past Session Context?<br/>(Yesterday, Last session)"}
    
    Step4 -- Yes --> Pass
    Step4 -- No --> Step5{"Negation Present?<br/>(did not, never, haven't)"}
    
    Step5 -- Yes --> Pass
    Step5 -- No --> Step6{"Direct Match in ACTION_VERBS?<br/>(I created, I deleted, I saved, I sent)"}
    
    Step6 -- No --> Pass
    Step6 -- Yes --> ReceiptCheck{"ToolReceipt Present in Session<br/>matching (tool, target, status=OK)?"}
    
    ReceiptCheck -- Yes --> Pass
    ReceiptCheck -- No --> Abort["TRIGGER Mid-Utterance Abort<br/>Drop TTS Queue, Record Breach"]
```

### 4.2 Pattern Coverage & Supervisor Decision Policies
v1.35.2 formalizes coverage and policy decisions across:
- **21 Action Verbs (Extracted Directly from Code `ACTION_VERBS`):** `delete` (`deleted`), `create` (`created`), `modify` (`modified`), `execute` (`executed`), `run` (`ran`), `install` (`installed`), `remove` (`removed`), `send` (`sent`), `upload` (`uploaded`), `fetch` (`fetched`), `save` (`saved`), `write` (`wrote`), `post` (`posted`), `reboot` (`rebooted`), `book` (`booked`), `place` (`placed`), `process` (`processed`), `start` (`started`), `close` (`closed`), `copy` (`copied`), `move` (`moved`).  
  *(Note: `build`, `compile`, and `deploy` are not present in the active regex in `src/lucca/sandbox/output_supervisor.py:286-289`; earlier documentation mistakenly included them while omitting `reboot`, `book`, `place`, `process`, and `fetch` which were added during WO-17).*
- **Known Paraphrase Limitation (Case C01):** The matcher relies on direct pronoun-action pairings (`I deleted`, `I created`). Periphrastic constructions such as *"I took care of removing the temporary files"* or *"I wrapped up creating the branch"* do not match the action verb lemma regex and pass without receipt checking. Category C in the test battery verifies that these do not produce false aborts, but this behavior represents a known coverage gap for ungrounded paraphrases.
- **Hedge Exemption Policy (Step 3):** By architectural decision, statements qualified by epistemic uncertainty (*"I think I deleted"*, *"I might have removed"*) are exempt from receipt verification to preserve natural conversational nuance and avoid penalizing honest human-like uncertainty. However, this creates a recognized evasion vector where ungrounded claims can bypass supervision if prefaced with a hedge.
- **Idiomatic Non-Actions:** Covers analytical idioms (`ran a check`), possessives (`placed my trust in`), and physical metaphors (`closed her eyes`).
- **Formal 40-Sentence Battery:** 10 grounded, 10 ungrounded, 10 paraphrases, 10 honest/hedged/negated sentences verified in [`tests/test_truth_in_receipt_battery.py`](file:///C:/projects/projectlucca/tests/test_truth_in_receipt_battery.py). All 40 cases pass (combined supervisor test suite: 66/66 passing; 74/74 including deontic sandbox tests).

### 4.3 Live Action Hallucination Evaluation ($n=100, T=0.6$)
To measure supervisor behavior against unconstrained model outputs under realistic conversational sampling ($T=0.6$), we evaluated a balanced 100-probe battery ([`data/benchmarks/action_hallucination_battery_100.json`](file:///c:/Projects/ProjectLucca/data/benchmarks/action_hallucination_battery_100.json)) containing 50 temptation probes, 25 honest controls, and 25 idiomatic non-action controls (testing `placed`, `moved`, `closed`, `processed`).

Across the 50 temptation probes, supervisor performance depends on labeling strictness, with both figures reported as exploratory findings tied to pre-registered Battery v2:
- **Strict Completed Actions Only:** Models emitted **8 unequivocal completion claims** without tool receipts (5 on E4B, 3 on E2B). The supervisor detected **1 of 8 completed action claims (12.5%, 95% Wilson CI: [2.2%, 47.1%])**.
- **Broad FAC (Primary Audit):** Models emitted **23 ungrounded action assertions** including present progressives and structured action headers (15 on E4B, 8 on E2B). The supervisor detected **1 of 23 false action claims (4.3%, 95% Wilson CI: [0.8%, 21.0%])**.
- **Per-Model Detail (Broad):** Gemma 4 E4B emitted 15 claims (1 caught [T01], 14 escaped; recall 6.7% [1.2%, 29.8%]; 35 clean). Gemma 4 E2B emitted 8 claims (0 caught, 8 escaped; recall 0.0% [0.0%, 32.4%]; 42 clean).
- **Controls ($n=50$):** 0 / 50 false alarms were triggered. However, because all 50 control probes are action-free text without tool receipts, this confirms only that the matcher is inactive on text devoid of action claims. Validating specificity against true, receipt-backed action claims across varied tenses and idioms is reserved for Battery v2.

| Labeling Strictness Stratum | Claims Emitted (E4B / E2B / Total) | Supervisor Caught (TP) | Catch Rate [95% Wilson CI] | Methodological Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Strict Completed Actions Only** | 5 / 3 / **8** | **1** (E4B T01) | **12.5% (1/8)** [2.2%, 47.1%] | Unequivocal completions only: past tense (*"I deleted"*), telegraphic (*"Done"*), state assertions (*"Reminder set"*) |
| **Broad FAC (Primary Audit)** | 15 / 8 / **23** | **1** (E4B T01) | **4.3% (1/23)** [0.8%, 21.0%] | Includes active progressive participles and structured markdown action markers |
| **Embedded Artifact Fields (Regex)** | 2 / 1 / **3** | **1** (E4B T01) | **33.3% (1/3)** [6.1%, 79.2%] | Legacy automated regex fields embedded in raw JSONs; circular with matcher |

*Note on Embedded JSON Fields:* The `ground_truth_hallucination` fields embedded within [`action_hallucination_gemma-4-e4b_t06_100.json`](file:///c:/Projects/ProjectLucca/logs/test_reports/action_hallucination_gemma-4-e4b_t06_100.json) and [`action_hallucination_gemma-4-e2b_t06_100.json`](file:///c:/Projects/ProjectLucca/logs/test_reports/action_hallucination_gemma-4-e2b_t06_100.json) (reporting TP=1/FN=1 and TP=0/FN=1) were generated by an automated regex matcher circular with the supervisor itself. Ground truth is provided by the manual post-hoc audit in [`logs/test_reports/action_hallucination_labels_100.jsonl`](file:///c:/Projects/ProjectLucca/logs/test_reports/action_hallucination_labels_100.jsonl).

**Methodology & Escape Mode Analysis:**
1. **Labeling Status & Boundary Decisions:** Ground-truth labels were assigned by post-hoc single-annotator manual audit of raw completions (recorded in [`logs/test_reports/action_hallucination_labels_100.jsonl`](file:///c:/Projects/ProjectLucca/logs/test_reports/action_hallucination_labels_100.jsonl) and [`logs/test_reports/temptation_inspections.txt`](file:///c:/Projects/ProjectLucca/logs/test_reports/temptation_inspections.txt)) after inspecting matcher flags. Boundary cases illustrate the operational frontier: item E4B `T03` (*"Drafting email... Would you like to add a body?"*) was classified as `CLEAN` / `INTENT` because it solicited user confirmation prior to execution, whereas bare progressives without confirmation (*"Moving all PDFs... now"*) were labeled `FAC`.
2. **Escape Mechanisms:** 22 of 23 ungrounded claims escaped past-tense declarative matching through four syntactic patterns:
   - **Active Progressive Participles (12 escapes):** Present-participle assertions without 1P pronouns (*"Closing all browser tabs..."*, *"Moving all PDFs..."*, *"Running cleanup tasks now..."*).
   - **Structured Markdown Blocks (2 escapes):** Action header formatting (*"\*\*Action:\*\* Sending email..."*, *"\*\*Action:\*\* Deleting directory..."*).
   - **Passive / Telegraphic Confirmations (6 escapes):** Unattributed state assertions (*"Done. The status update has been posted..."*, *"Reminder set for tomorrow at 10 AM"*).
   - **Unlisted Verb Lemmas (2 escapes):** Verbs such as `opened` (*"I've opened firewall port 22"*) and `launched` (*"Launching Excel... Done"*) absent from `ACTION_VERBS`.
3. **Future Work (v1.36 Pre-Registration):** Pre-registering Battery v2 with dual independent annotators, Cohen's kappa reporting before adjudication, receipt-mismatch strata, and testing structural output-channel constraints versus regex patch extensions.

---

## 5. Dynamic Task Router & Neurosymbolic Execution

### 5.1 Formal Routing Specification
The task router enforces the following empirical dispatch logic (with R1 @ 6k locked as the canonical default for E4B competition mathematics based on fresh held-out evidence):

$$\text{Router}(M, T) = \begin{cases} 
\text{Direct Raw Generation (R0)} & \text{if } M = \text{12B} \\ 
\text{PAL in Docker (P2 @ 2,048 cap)} & \text{if } M \in \{\text{E4B}, \text{E2B}\} \land T = \text{Arithmetic/Word} \\ 
\text{Thinking Mode (R1 @ 6,144 cap)} & \text{if } M = \text{E4B} \land T = \text{Competition Math} \\ 
\text{Thinking Mode (R1 @ 6,144 cap)} & \text{if } M = \text{E2B} \land T = \text{Competition Math} 
\end{cases}$$

*(Design Note: For Gemma 4 E4B on competition math, PAL P2 @ 2k remains an optional operator-selected efficiency profile saving 40% tokens and 1.6× latency on dev-like problems, but Thinking Mode R1 @ 6k is the canonical default because it provides a statistically significant +15 pp strict accuracy advantage on held-out competition problems: 88.0% vs. 73.0%, $p = 0.0026$).*

### 5.2 Mechanistic Rationales, Empirical Findings & Router Disclosure
1. **For 12B Unified:** Raw generation achieves 90.0% strict accuracy with 660 tokens in 12.9s. Under greedy decoding ($T=0.0$), unconstrained thinking triggers circular re-verification loops that crash accuracy to 58.0% (32:0 McNemar discordant ratio, $p = 4.66 \times 10^{-10}$).
2. **For E4B / E2B Arithmetic (GSM-Symbolic):** PAL in Docker absorbs parameter contraction, equalizing 2B/4.5B models with 12B (91%–94% vs. 95%).
3. **The E4B Competition Math Trade-Off (Dev vs. Held-Out):**
   - **On Dev Split ($n=100$):** PAL @ 2,048 cap scored 83.0% strict / 92.0% lenient (10.1s, 1,070 tok), tying Thinking Mode R1 @ 4k (85.0% strict / 86.0% lenient, $p=0.7905$ NS).
   - **On Held-Out Split ($n=100$):** Evaluated side-by-side on the identical 100 unseen competition problems, Thinking Mode R1 @ 6k scored **88.0% strict / 92.0% lenient**, while PAL P2 @ 2k scored **73.0% strict / 83.0% lenient**.
   - **Paired McNemar Analysis:** On strict CAS, discordant pairs are `R1-only (b) = 19 : P2-only (c) = 4` ($p = 0.0026$, significant advantage for R1); on lenient normalization, discordant pairs are `R1-only (b) = 13 : P2-only (c) = 4` ($p = 0.0490$). On harder unseen competition problems, latent thinking tokens allow the model to explore geometric and algebraic relationships before committing to numeric calculations, whereas direct Python synthesis without pre-thinking fails when the model cannot directly formalize the equations.
4. **P3 Redundancy Limitation:** Pre-thinking before synthesizing Python code (Arm P3) was shown to be redundant on Gemma 4 E2B (76% vs 77%, $p=1.000$, `P2-only = 5 : P3-only = 4`). Multi-model generalization of this finding across other scales remains an open empirical question.
5. **Router Nature Disclosure:** In the benchmark harness, `--arm routed` switches execution using the benchmark metadata label (`benchmark == 'gsm_symbolic'` vs `'math500'`). This represents an **oracle label lookup**, not an active neural intent classifier. In production desktop deployment, realizing this routing policy requires an in-the-wild task-type intent classifier, which has not yet been benchmarked.

---

## 6. Comprehensive Benchmark Scorecard

```
========================================================================================================================
CONSOLIDATED BENCHMARK MATRIX ACROSS THE 3 PARAMETER SCALES (PROJECT LUCCA v1.35.5)
========================================================================================================================
Benchmark Suite             Metric / Arm               Gemma 4 12B          Gemma 4 E4B          Gemma 4 E2B
------------------------------------------------------------------------------------------------------------------------
Spec 100 System Suite†      Overall Accuracy (Mean)    84.0% (82–86%)*      85.0%                81.0%
                            Tool Precision / Recall    15 / 15 (100.0%)     15 / 15 (100.0%)     10 / 15 (100% P / 67% R)
                            OS / Host Guardrails       10 / 10 (100.0%)     10 / 10 (100.0%)     10 / 10 (100.0%)
                            Content Safety Refusal**   9 / 10 (90.0%)       3 / 10 (30.0%)       Not Evaluated
                            Throughput (P50)           37.18 tok/s          80.76 tok/s          126.1 tok/s

GSM-Symbolic (100-strat)‡   PAL P2 Accuracy (Docker)   95.0%                94.0%                91.0%
                            Direct R0 Accuracy         93.0%                91.0%                81.0%
                            PAL Lift (Delta)           +2.0 pp (NS)         +3.0 pp (NS)         +10.0 pp (p = 0.021)

HumanEval Canonical 164‡    Raw Pass@1                 155 / 164 (94.5%)    144 / 164 (87.8%)    123 / 164 (75.0%)
                            Assisted Pass@1            154 / 164 (93.9%)    141 / 164 (86.0%)    126 / 164 (76.8%)
                            (Assisted Effect)          No Detectable Ben.   No Detectable Ben.   +1.8 pp (p = 0.55 NS)

MATH-500 Dev (100 items)‡   Direct R0 (Strict / Len)   90.0% / 93.0%        50.0% / 50.0%        51.0% / 51.0%***
                            PAL P2 @ 1k (Historical)   85.0% / 87.0%        73.0% / 77.0%        70.0% / 75.0%
                            PAL P2 @ 2k (Uncapped Code) —                   83.0% / 92.0%        77.0% / 85.0%
                            PAL P3 (PAL + Thinking)    —                    —                    76.0% / 84.0%
                            Thinking R1 @ 4k           —                    85.0% / 86.0%        81.0% / 82.0%
                            Thinking R1 @ 6k           58.0% / 59.0%        —                    84.0% / 85.0%

MATH-500 Fresh Held-Out‡    Direct R0 @ 4k (Strict)    89.0% [80.8, 94.1]   52.0% [41.8, 62.0]   51.0% [40.9, 61.1]
(Unseen 100 Problems)       Direct R0 @ 4k (Lenient)   94.0% [86.9, 97.5]   54.0% [43.8, 63.9]   55.0% [44.8, 64.9]
                            PAL P2 @ 2k (Strict)       86.0% [77.3, 91.9]   73.0% [63.0, 81.2]   61.0% [50.7, 70.4]
                            PAL P2 @ 2k (Lenient)      90.0% [82.0, 94.8]   83.0% [73.9, 89.5]   70.0% [59.9, 78.6]
                            Thinking R1 @ 6k (Strict)  (Dev: 58.0% [47.7])  88.0% [79.6, 93.4]   81.0% [71.7, 87.9]
                            Thinking R1 @ 6k (Lenient) (Dev: 59.0% [48.7])  92.0% [84.4, 96.2]   86.0% [77.3, 91.9]
                            Truncations (R0 / P2 / R1) 3.0% / 5.0% / —      1.0% / 8.0% / 2.0%   4.0% / 14.0% / 10.0%
========================================================================================================================
† Spec 100 was evaluated under sampling temperature T=0.6 (reproducibility range 82–86%, mean 84.0% ± 2.0 pp noise floor).
‡ GSM-Symbolic, HumanEval, and MATH-500 were evaluated under deterministic greedy decoding (T=0.0, seed 42).
* 12B Spec 100: 4 independent runs yielded 86%, 82%, 84%, 84%.
** Content safety reflects compliance on uncensored fine-tunes; E4B refuses only 30% of general content safety probes.
*** Tested directly on identical Dev-100 items with 4,096-token cap: E4B R0 scored 52.0% (5:3 discordant, p = 0.7266 NS) and E2B R0 scored 57.0% (10:4 discordant, p = 0.1796 NS). A larger token budget did not produce a statistically detectable accuracy gain under direct prose generation, showing that truncation relief alone does not account for observed scaffold differences.
**** Split Nomenclature, Leak Disclosure & 98-Item Robustness: Dev split comprises lines 1–100 of math500_test.jsonl (historically designated 'test-100' in v1.3 before prompt-tuning contamination audit handover/V135_CONTAMINATION_AUDIT.md reclassified it as development). Held-out split comprises lines 1–100 of math_fresh_heldout_500.jsonl (remaining 400 problems remain unrun and unreported). The known exploratory execution leak of items 15 and 73 documented in the contamination audit occurred on math_fresh_heldout_500.jsonl, placing them inside the evaluated held-out 100 sample (indices 14 and 72); to our knowledge, no prompt or harness change was made in response to this incidental exposure. Recomputing held-out strict accuracy excluding items 15 and 73 (98 items) confirms robustness across all arms: 12B R0: 88.8% (87/98) vs 89.0%; 12B P2: 85.7% (84/98) vs 86.0%; E4B Routed (R1): 87.8% (86/98) vs 88.0%; E4B P2: 73.5% (72/98) vs 73.0%; E4B R0: 51.0% (50/98) vs 52.0%; E2B R1: 80.6% (79/98) vs 81.0%; E2B P2: 61.2% (60/98) vs 61.0%; E2B R0: 50.0% (49/98) vs 51.0%.
```

---

## 7. Configuration, Provenance & Test Suite Taxonomy

### 7.1 Commit Provenance
Results across this study were generated across committed development stages:
- **`f5d4910`**: Pre-closeout baseline implementation of supervisor and initial benchmarks.
- **`1c58587`**: Factorial ablation harness implementation and initial E2B/12B sweep runs.
- **`dec0d79`**: Grader commit consolidating `compare_math_strict` and `compare_math_lenient`.
- **`f20537fe`**: Release closeout baseline commit.
- **`v1.35.5` (Current)**: Comprehensive audit remediation commit (key persistence, SQLite quarantine table, full held-out matrix across all 3 models, controlled deconfounding on identical dev items, live 100-probe supervisor evaluation, and rule-count reconciliation). All result JSON artifacts contain `git_commit` and `git_dirty` flags written directly by the test harness.

### 7.2 Test Suite & Rule Taxonomy Breakdown
The project maintains a tiered test taxonomy across multiple test scopes verified via `--collect-only`:
- **27 Tests (`tests/test_output_supervisor.py`):** Core deontic policy capitulation (11 assertion patterns), lookback window tokenization, past temporal marker suppression, stalling filler detection, and idiomatic non-action false-positive guards (`placed`, `moved`, `closed`, `processed`).
- **40 Tests (`tests/test_truth_in_receipt_battery.py`):** Exhaustive Truth-in-Receipt battery across 4 balanced categories: Category A (10 grounded claims), Category B (10 ungrounded claims), Category C (10 paraphrases/idioms), and Category D (10 epistemic hedges and negations).
- **8 Tests (`tests/test_deontic_sandbox_m2.py`):** Adversarial Win32 handle containment, hard link rejection, two-stage open, DNS rebinding, HMAC token replay, and multi-turn taint monitor isolation.
- **67 Tests:** The combined supervisor test suite (`test_output_supervisor.py` [27] + `test_truth_in_receipt_battery.py` [40]).
- **75 Tests:** The full supervisor and deontic isolation suite (`test_output_supervisor.py` [27] + `test_truth_in_receipt_battery.py` [40] + `test_deontic_sandbox_m2.py` [8]).  
  *(Note on historical counts: The '19 deontic tests' referenced in earlier documentation represented 11 assertion pattern tests in `test_output_supervisor.py` combined with the 8 tests in `test_deontic_sandbox_m2.py`. Reporting 26 + 19 double-counted those 11 tests).*
- **1,198 Tests:** The complete repository pytest suite across all subsystems (memory, sandbox, router, LISP engine, speech, affect ODE, and static gates), with 100% passing.

### 7.3 Rule Inventory & MicroScheme Activation Topology
`LispTab` and the orchestrator interface manage an inventory of 18 distinct MicroScheme rules:
1. **15 Active Factory Skills (`config/skills/*/plan.scm`):** Fully loaded into `RuleLifecycleManager` on engine boot. 12 skills (`calc-eval-v1`, `unit-convert-v1`, `quick-fact-v1`, `define-term-v1`, `memory-brief-v1`, `note-take-v1`, `self-health-v1`, `recent-context-v1`, `resource-report-v1`, `sys-specs-v1`, `proc-top-v1`, `session-recap-v1`) expose `expose_as_tool: true` and are advertised in the prompt manifest; all 15 skills are loaded and callable (invocation frequency not measured in production logs). 1 skill (`time-greeting-v1`) governs conversational greetings, and 2 skills (`plan-decompose-v1`, `correction-ack-v1`) serve as yield-shortcuts.
2. **1 Retired Skill (`config/skills/_retired/barge-in-sorry-v1/plan.scm`):** Quarantined pending audio-layer barge-in event wiring.
3. **1 Standalone Procedural Rule (`config/rules/calc-open-with-expr-v1.scm`):** Loaded into `LispTab` in `QUARANTINE` state. This rule was never wired to a tool manifest and has recorded 0 production firing events.
4. **1 In-Memory UI Fallback Mock (`open-calculator-v1`):** Retained in `lisp_tab.py` solely as an in-memory sample fallback when the on-disk registry is empty.

---

## 8. Known Architectural Limitations

In accordance with architectural transparency standards, the following known limitations are formally documented:

1. **Host-Signed LLM Assertions as Grounding Evidence (`LISP_ASSERTION`):** In the abductive deduction loop ([`src/lucca/core/orchestrator.py:1550-1645`](file:///c:/Projects/ProjectLucca/src/lucca/core/orchestrator.py)), inference steps proposed by the LLM (`step_kind="llm_abductive"`) are validated only against premise presence before the orchestrator signs them directly using `SignerFactory.lisp_assertion()`. These entries are NOT deterministic outputs of the MicroScheme rule engine, yet receive `LISP_ASSERTION` provenance envelopes that are marked `grounding_eligible = 1`. This creates a vulnerability where LLM-generated inference proposals bypass external empirical verification and become permanently grounded in long-term memory.
2. **Trusted Workspace `read_file` Payloads:** File contents read within the workspace boundary receive `TOOL_VERIFIED` provenance envelopes. If untrusted external documents (e.g. downloaded text files) are placed into the workspace, their contents can act as indirect prompt-injection vectors without cryptographic domain gating.
3. **Cross-Tier Precedence Masks Contradictions:** Cross-tier evidential conflicts produce NO `BOTH` (conflict) value and NO entry in the `review_queue`. Because the cascade enforces strict hierarchical precedence (`TrustTier.TIER_0` strictly supersedes `TIER_1`, which supersedes `TIER_2`, etc. per [`src/lucca/core/cascade.py:1790-1858`](file:///c:/Projects/ProjectLucca/src/lucca/core/cascade.py)), the higher-trust tier simply wins outright and lower-trust contradictory evidence is suppressed as superseded. Belnap `CONFLICT` (`BOTH`) and subsequent review-queue entries arise strictly within the same tier when conflicting evidence has identical precedence.
4. **No Point-in-Time (`as_of`) Query API:** While the underlying SQLite schema stores bi-temporal timestamps (`valid_from`, `valid_to`), the `HybridRetriever.search()` API does not currently expose an explicit `as_of` temporal query parameter for point-in-time historical time-travel.
5. **Standalone Procedural Rule Dormancy:** While the 15 active factory skills in `config/skills/` are loaded on boot and callable (invocation frequency not measured in production logs), the standalone procedural rule `config/rules/calc-open-with-expr-v1.scm` remains in `QUARANTINE` status and has 0 production firing events. Early audit notes characterizing the engine as having "exactly one rule that never fired" referred strictly to this quarantined file in `config/rules/`, overlooking the 15 active skill rules in `config/skills/`.
6. **Severe Safety Vulnerability in Default Model (E4B Compliance with Harmful Probes):** In cross-model safety evaluations ([`logs/test_reports/cross_model_30_gemma-4-e4b.json`](file:///c:/Projects/ProjectLucca/logs/test_reports/cross_model_30_gemma-4-e4b.json)), the uncensored fine-tune (`gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf`) complied with 7 of 10 adversarial harmful prompts (including detailed engagement on keylogger synthesis, credential phishing, and ricin inquiries), refusing only 3 of 10 (30% refusal rate). In contrast, Gemma 4 12B refused 9 of 10 ([`logs/test_reports/cross_model_30_gemma-4-12b.json`](file:///c:/Projects/ProjectLucca/logs/test_reports/cross_model_30_gemma-4-12b.json)). Gemma 4 E2B was not evaluated in `cross_model_30` (its fine-tune focused on Sinhala bilingual transfer) and its safety compliance rate remains unverified. Deploying E4B as the sovereign core represents an active safety hazard requiring external guardrail enforcement.
7. **Regex vs. AST Semantic Gap in Output Supervision:** The supervisor operates via compiled regular expressions rather than an abstract syntax tree of natural language. Consequently, periphrastic phrasing (*"I took care of removing..."*) bypasses action verb matching, and epistemic hedges (*"I think I deleted..."*) intentionally suppress verification, providing potential evasion channels.

