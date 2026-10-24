# Release Plan: Project Lucca v1.35.7 — Epistemic Integrity & Semantic Verification

```yaml
doc_status: canonical
as_of: 2026-10-08
target_release: v1.35.7
supersedes: []
superseded_by: []
verification: code-cited
```

**Target Release:** Project Lucca v1.35.7  
**Prerequisites Satisfied:** v1.35.6 stable release (`dd14034`, `54640f9`, `ddb5efa`); 1,243 passed tests; 24 static gates; results ledger 32 rows / 0 mismatches.  
**Hardware Budget Constraint:** $\Delta\text{VRAM} = 0\,\text{MB}$ (GPU reserved exclusively for primary LLM / `llama-server`), Host CPU / NPU only (Intel Core Ultra via OpenVINO FP16), $\Delta\text{RAM} \le 600\,\text{MB}$, latency budget $\le 25\,\text{ms}$ on fast path.

---

## 1. Executive Summary & Purpose

During the v1.35.6 audit, an in-depth investigation into autobiographical memory corruption revealed that Project Lucca's epistemic core and reflection pipeline relied heavily on **brittle lexical heuristics** (FTS keyword overlap, naive substring checks, and token Jaccard similarity). 

This plan formally specifies **Release v1.35.7**, which delivers:
1. **Core Pipeline Hygiene:** Fixes four hardcoded logic defects in `belief_service.py`, `reflection.py`, `cascade.py`, and `induction.py`.
2. **Sub-25ms Semantic Verifier Gate (`SemanticVerifierPort`):** Deploys an OpenVINO-accelerated NLI / factual consistency engine on CPU/NPU with 0 MB VRAM overhead.
3. **Model-Agnostic Post-Turn Distiller:** A GBNF-constrained JSON distillation loop using the active `SpeechLLMPort` (Gemma E2B, E4B, or 12B — the validated tiers) running post-turn (0 ms speech/audio latency impact). Distilled propositions are admitted to memory only under a `DerivedFactSigner` envelope (`USER_DERIVED`).

---

## 2. Four Critical Pipeline Defects Remediated

| Component | File & Lines | Defect Discovered | Remediated Behavior (v1.35.7) |
|---|---|---|---|
| **Belief Conflict** | `src/lucca/core/belief_service.py:193` | `is_conflict_top=False` hardcoded. System mathematically incapable of registering Belnap $\top$ conflict. | Pass real candidate evaluation signal; enable true $\top$ resolution. |
| **Topic Review** | `src/lucca/core/belief_service.py:194` | `topic=None` hardcoded. Topic review falls back to `kind="belief"`, bypassing operator topic locks. | Pass candidate belief's actual `topic` attribute to `ReflectionEngine`. |
| **Verbatim Ingestion** | `src/lucca/memory/reflection.py:205` | Commits `new_content` (the user's raw conversational speech) directly as an `ASSISTANT_BELIEF`. | Banned. Raw user transcripts are never stored as assistant beliefs. Only canonical propositions admitted. |
| **Belnap Polarity** | `src/lucca/core/cascade.py:1542, 1562, 1627, 1669` | `told_false=False` hardcoded at **four** evidence-assertion sites. Negative statements (*"We do NOT support X"*) treated as positive evidence $\mathbf{T}$. | Semantic Verifier assigns `told_true=True` on entailment, `told_false=True` on contradiction at every site. |
| **Rule Corruption** | `src/lucca/reasoning/induction.py:98–131` (`cluster_phrasings`) | Jaccard threshold $0.60$ merges opposite rules (*"always single quotes"* vs *"never single quotes"* = $3/5 = 0.60$). | Clustered via bidirectional entailment; pairs with contradiction flagged as Rule Conflicts. |

---

## 3. Architecture: The Two-Tier Verifier & Distiller

```
┌────────────────────────────────────────────────────────────────────────┐
│                        THE HARDWARE-OPTIMIZED SPLIT                    │
├────────────────────────────────────────────────────────────────────────┤
│  INTEL CORE ULTRA NPU / CPU (via OpenVINO FP16)                        │
│  • ModernBERT-base-nli (~149M, ~600MB) or Vectara HHEM 2.1 (~250M)    │
│  • Latency: 12–25ms | VRAM Cost: 0 MB (Does not touch dGPU)            │
│  • Tasks: Belnap polarity, belief candidate gate, claim entailment     │
├────────────────────────────────────────────────────────────────────────┤
│  NVIDIA RTX GPU (llama-server Port 8080)                               │
│  • Active Primary LLM (Gemma 4 E2B / E4B / 12B)                       │
│  • Post-Turn Distillation: GBNF-constrained JSON schema (< 100ms)      │
│  • Tasks: Spoken reasoning, macro planning, proposition distillation   │
└────────────────────────────────────────────────────────────────────────┘
```

### Three Technical Traps Explicitly Guarded Against

1. **Trap 1: OpenVINO NPU Operator Compilation Failure:**
   - *Risk:* ModernBERT's unpadding and dynamic attention kernels can fail compilation on Intel NPU drivers.
   - *Invariant:* The runtime adapter in `src/lucca/senses/verifier.py` defaults to `device="CPU"` with an automatic fallback if NPU compilation fails. On Intel Core Ultra, AVX2/VNNI CPU execution completes in $< 20\,\text{ms}$.
2. **Trap 2: Python Tokenizer Serialization Jitter:**
   - *Risk:* Calling pure-Python tokenizers on every turn introduces 5–10 ms of GIL locking.
   - *Invariant:* Pre-load the fast Rust `tokenizers` backend once at startup in `VerifierWorker.__init__`, or compile `openvino_tokenizers` into the OpenVINO graph.
3. **Trap 3: Hypothesis Directionality Inversion:**
   - *Risk:* NLI is strictly asymmetric ($P \models H \not\equiv H \models P$). Reversing premise and hypothesis breaks verification.
   - *Invariant:* `SemanticVerifierPort` enforces keyword-only arguments:
     ```python
     def check_consistency(self, *, premise: str, hypothesis: str) -> VerificationResult: ...
     ```

---

## 4. Work Breakdown & Implementation Phases

### Phase 1: Core Pipeline Hygiene (Zero Dependencies)
- Fix `belief_service.py` L193 (`is_conflict_top`) and L194 (`topic`).
- Ban raw user transcripts in `reflection.py` L205.
- Update `cascade.py` L1542, L1562, L1627, L1669 (all four hardcoded `told_false=False` sites) to stop defaulting `told_false = False`.
- Fix `induction.py` `cluster_phrasings` (L98–L131) to guard against Jaccard false-merging of opposing rules.
- Test gate: Full regression suite passes green (1,243 unit tests + 24 static gates).

### Phase 2: OpenVINO Semantic Verifier Engine
- Add `SemanticVerifierPort` protocol to `src/lucca/ports.py`; `VerificationResult` as a strict Pydantic v2 model in `src/lucca/core/schemas.py` (project convention: protocols in `ports.py`, cross-boundary contracts in `schemas.py` per D-SEC-04; Zero-`Any` invariant D-AUD-01 applies).
- **Verifier decision policy (pre-registered):** entailment/contradiction labels come from the NLI softmax with a fixed decision threshold $\tau = 0.50$; scores in $[0.40, 0.60]$ are labeled `UNCERTAIN` and treated as **no-signal** (neither `told_true` nor `told_false` is set) — the verifier never forces a binary on ambiguous pairs.
- **Failure policy (fail-open, never silent):** if the verifier raises or times out (>50 ms), the call site degrades to the existing lexical behavior and logs `verifier_degraded` via the structured logger; a degraded turn never admits a *new* polarity assignment, only the pre-v1.35.7 behavior.
- **Pair cache:** bounded LRU (1,024 pairs, keyed by `(premise, hypothesis)` NFC-normalized) inside `VerifierWorker`; belief-audit loops re-verify repeated pairs and the cache keeps repeat inference at $< 1\,\text{ms}$.
- **Pinned model:** export `ModernBERT-base-nli` (~149M) to OpenVINO FP16 in `C:\ProjectLucca\models\verifier\`. Vectara HHEM 2.1 is a documented fallback only, not a runtime choice. Register the exported artifact's sha256 in `models\MANIFEST.json` (required by `env_check`).
- Implement `VerifierWorker` in `src/lucca/senses/verifier.py` supporting `check_consistency(*, premise, hypothesis)`.
- **Process topology:** `VerifierWorker` runs in-process inside `lucca-core`, model loaded once at supervisor startup. No fifth process is introduced; the ADR-008 four-process + ZeroMQ topology is preserved.
- Unit test: Benchmark inference latency on host CPU/NPU ($\le 25\,\text{ms}$).

### Phase 3: Wire Semantic Verification Across the 7 Subsystems
- **Belief Contradiction (`belief_service.py`):** Candidate beliefs whose verifier label **is** `CONTRADICTION` are routed to conflict handling (Belnap $\top$ via the now-real `is_conflict_top` signal) instead of being admitted as positive evidence; only non-contradicting candidates proceed to normal admission.
- **Belnap Cascade (`cascade.py`):** True `told_false = True` assignment on contradiction; `told_true = True` on entailment.
- **Functional Coherence (`coherence.py`):** Tool receipt premise entails narration hypothesis.
- **Rule Induction (`induction.py`):** Bidirectional entailment for clustering; contradiction for quarantine.
- **Fact Extraction (`memory_commit_service.py`):** Candidate triples verified for entailment against user transcript.
- **Analogy Corroboration (`corroboration.py`, CQ1 ~L1159):** Replace the keyword-list "relevant similarity" check (`"false equivalence"`, `"no similarity"`, `"unlike"`) with bidirectional entailment via `SemanticVerifierPort`: cases share relevant similarity iff a shared entailed premise exists between case descriptions.
- **Self-Diagnosis Symptom Matching (`self_diagnosis.py`, ~L190):** Replace raw token-overlap symptom matching (tokens $\ge 4$ chars) with verifier-scored entailment of observation text against symptom descriptions.
- **D-REAS-06 preservation invariant:** bidirectional-entailment clustering may change only *merge grouping* in `induction.py`. Induced rules remain registered strictly into `QUARANTINE`; the 5-distinct-cluster / 0-error promotion gate and `lucca-admin` explicit approval are untouched. WO-30's macro-mining loop (`RuleLifecycleManager`) consumes the same lifecycle and must observe identical semantics.
- **Cross-work-order note (WO-33):** the ratified ladder re-sequencing assigns Module 10 "Belnap latent investigator" to WO-33 (trigger-gated). v1.35.7 lays the `SemanticVerifierPort` groundwork that WO-33 consumes; it must not implement competing Belnap semantics. WO-33's envelope will cite this plan as its substrate.
- **Output supervision boundary:** NLI verification is **complementary to, not a replacement of**, `TruthInReceiptMatcher` (21-verb action supervision in `sandbox/output_supervisor.py`). The 70/70 Truth-in-Receipt battery and its claims remain defined over the unchanged supervisor; Phase 3 adds a second, orthogonal evidence channel (post-turn coherence), and the existing deferral hook (`output_supervisor.py:813`, "recollection/hallucination deferred to post-turn coherence check") is the integration point.
- **Latency budget note:** the two new sites add at most 2 verifier calls per turn; both are off the audio fast path (post-turn consolidation), so the $\le 25\,\text{ms}$ per-pair budget and fast-path latency are unaffected.
- **Benchmark recalibration note:** corroboration schemes feed analogy probes in `SPEC-BENCH-100`. After Phase 3 lands, the battery is re-run and the new pass rate recorded in `RESULTS.md` as a distinct row (`spec-bench-100-v1.0-nli`); prior rows remain comparable to the pre-NLI substrate and are NOT retroactively amended.

### Phase 4: Model-Agnostic Post-Turn Distiller
- Add `config/grammars/belief_distill.gbnf` for constrained JSON output.
- Create `src/lucca/reasoning/distill.py` calling active `SpeechLLMPort`.
- Wire into post-turn consolidation loop: confirmed contradictions distilled into clean third-person declarative propositions.
- **Provenance invariant (ADR-006):** distilled propositions are `LLM_NARRATION` at origin and are therefore rejected by the `ProvenanceGate` as-is. They must be re-signed by `DerivedFactSigner` (`USER_DERIVED`, derived from the signed contradiction pair) before any memory commit; unsigned distillates are never memory-eligible.
- **Rejection retention:** distillates rejected by the `ProvenanceGate` or by verifier `UNCERTAIN` labels are persisted to the SQLite `memory_quarantine` table (D-MEM-05) with their rejection reason, never silently discarded — rejected propositions remain auditable by `lucca-admin`.
- **Negative test (required fixture):** `test_v1357_provenance_negative.py` asserts an unsigned distillate is rejected by `ProvenanceGate` (mirrors the `test_d_reas_06_negative.py` convention).

### Phase 5: Documentation & Milestone Release
- Ratify `D-MEM-08` in `luccadocs/DECISIONS.md`.
- Bump `__version__ = "1.35.7"` in `src/lucca/__init__.py`.
- Document in `CHANGELOG.md` under `[1.35.7]`.
- Update `luccadocs/V2_BACKLOG.md` (active work-order tracking) and `plans/AUDIT_REGISTER.md` (register counts cited in the prerequisites line must stay honest as new findings close).
- Cross-link WO-33's envelope to this plan (Belnap substrate) per the cross-work-order note in §4 Phase 3.

---

## 5. Pre-Registered Acceptance Gates

*   **`G-V1357-HYGIENE`**: 0 instances of hardcoded `is_conflict_top=False`, `topic=None`, `content=new_content` (user transcript), or `told_false=False` at the four `cascade.py` evidence sites in production belief code paths.
*   **`G-V1357-LATENCY`**: OpenVINO Verifier single-pair latency $\le 25\,\text{ms}$ on host hardware (Intel Core Ultra CPU/NPU).
*   **`G-V1357-BELNAP`**: A negative memory assertion (*"The API does not support X"*) queried with *"Does the API support X?"* assigns `told_false=True` and evaluates to `BelnapValue.FALSE`, not `TRUE`.
*   **`G-V1357-RULE`**: Opposing rule candidate pair (*"always use single quotes"*, *"never use single quotes"*) is rejected from single-cluster merging. **Negative fixture:** a near-paraphrase pair (*"always use single quotes"* vs *"prefer single quotes"*) is NOT flagged as a Rule Conflict (verifier must not over-fire contradiction on entailment-compatible pairs).
*   **`G-V1357-VERIFIER-NEG`**: Near-paraphrase pairs score as ENTAILMENT, not CONTRADICTION; scores within $[0.40, 0.60]$ produce `UNCERTAIN` and set neither epistemic bit; a forced verifier timeout degrades to lexical behavior with `verifier_degraded` logged and no new polarity admitted.
*   **`G-V1357-DISTILL`**: Confirmed contradiction converts into third-person canonical proposition without user conversational filler.
*   **`G-V1357-ANALOGY`**: A pair of cases with no shared entailed premise (keyword-overlap false positive, e.g. differing only in negation cues) is rejected by CQ1; a pair sharing an entailed causal premise is accepted. Fixture corpus extended in `tests/fixtures/contrastive/probes.jsonl`.
*   **`G-V1357-DIAG`**: An observation text that lexically overlaps a symptom description but does not entail it (e.g. "temperature is normal" vs "overheating") does not match that symptom; a genuinely entailing observation does.
*   **`G-V1357-REGRESS`**: All 1,243 existing unit/regression tests and 24 static gates pass green. Behavior changes at `corroboration.py` and `self_diagnosis.py` must be attributed to their own new gates; existing `test_corroboration.py` / `test_self_diagnosis.py` fixtures that encode the old keyword/token behavior are updated in the same commit and the delta recorded.

---

## 6. NLI Application Sites Audit (Complete Sweep)

All lexical-heuristic decision sites in the codebase were enumerated. **Integrated into v1.35.7:** the seven Phase 3 sites, including `corroboration.py` CQ1 (keyword list → bidirectional entailment) and `self_diagnosis.py` symptom matching (token overlap → verifier entailment), each with its own acceptance gate (`G-V1357-ANALOGY`, `G-V1357-DIAG`).

**Deliberately NOT replaced (invariants that must hold):**

*   `src/lucca/memory/extraction.py` (~L55): subject/object grounding uses `rapidfuzz partial_ratio >= 90`. **Not replaced:** Spec 03 §5.2 grounding is a provenance guarantee and must stay exact-substring/fuzzy-local; NLI there would weaken provenance.
*   `src/lucca/eval/contrastive_grader.py` (~L185): substring grading. **Not replaced:** grades must remain deterministic and recomputable from run artifacts (register C-05).
*   `src/lucca/router/heuristic.py` (~L382): already uses 384-D embedding cosine anchors; no change needed.
*   `src/lucca/reasoning/smt_verifier.py`, `prims.py` (AABB overlap), `trace.py`, `kokoclone.py`: substring/overlap uses there are geometric, path-safety, or acoustic — not semantic relations; NLI does not apply.

---

## 7. What Is NOT Claimed in v1.35.7

*   Does not replace primary reasoning LLMs (Gemma 4 remains primary conversational / tool reasoning engine).
*   Does not claim zero latency for post-turn distillation; distillation is strictly asynchronous and off the audio playback path.
*   Does not replace SMT formal verification (Z3 SMT solver continues to handle mathematical and code invariants in WO-30).
