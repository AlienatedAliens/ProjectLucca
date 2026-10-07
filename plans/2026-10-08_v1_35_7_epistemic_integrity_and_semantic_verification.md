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
3. **Model-Agnostic Post-Turn Distiller:** A GBNF-constrained JSON distillation loop using the active `SpeechLLMPort` (Gemma E2B, E4B, 12B, or 26B) running post-turn (0 ms speech/audio latency impact).

---

## 2. Four Critical Pipeline Defects Remediated

| Component | File & Lines | Defect Discovered | Remediated Behavior (v1.35.7) |
|---|---|---|---|
| **Belief Conflict** | `src/lucca/core/belief_service.py:193` | `is_conflict_top=False` hardcoded. System mathematically incapable of registering Belnap $\top$ conflict. | Pass real candidate evaluation signal; enable true $\top$ resolution. |
| **Topic Review** | `src/lucca/core/belief_service.py:194` | `topic=None` hardcoded. Topic review falls back to `kind="belief"`, bypassing operator topic locks. | Pass candidate belief's actual `topic` attribute to `ReflectionEngine`. |
| **Verbatim Ingestion** | `src/lucca/memory/reflection.py:205` | Commits `new_content` (the user's raw conversational speech) directly as an `ASSISTANT_BELIEF`. | Banned. Raw user transcripts are never stored as assistant beliefs. Only canonical propositions admitted. |
| **Belnap Polarity** | `src/lucca/core/cascade.py:1541, 1562` | `told_false=False` hardcoded. Negative statements (*"We do NOT support X"*) treated as positive evidence $\mathbf{T}$. | Semantic Verifier assigns `told_true=True` on entailment, `told_false=True` on contradiction. |
| **Rule Corruption** | `src/lucca/reasoning/induction.py:80` | Jaccard threshold $0.60$ merges opposite rules (*"always single quotes"* vs *"never single quotes"* = $3/5 = 0.60$). | Clustered via bidirectional entailment; pairs with contradiction flagged as Rule Conflicts. |

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
│  • Active Primary LLM (Gemma 4 E2B / E4B / 12B / 26B A4B)             │
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
- Update `cascade.py` L1451, L1541, L1562 to stop defaulting `told_false = False`.
- Fix `induction.py` L80 to guard against Jaccard false-merging of opposing rules.
- Test gate: Full regression suite passes (70+ tests).

### Phase 2: OpenVINO Semantic Verifier Engine
- Add `SemanticVerifierPort` protocol and `VerificationResult` schema to `src/lucca/ports.py`.
- Download and export `ModernBERT-base-nli` (or `Vectara HHEM 2.1`) to OpenVINO FP16 in `C:\ProjectLucca\models\verifier\`.
- Implement `VerifierWorker` in `src/lucca/senses/verifier.py` supporting `check_consistency(*, premise, hypothesis)`.
- Unit test: Benchmark inference latency on host CPU/NPU ($\le 25\,\text{ms}$).

### Phase 3: Wire Semantic Verification Across the 5 Subsystems
- **Belief Contradiction (`belief_service.py`):** Candidate beliefs dropped immediately if `label != "CONTRADICTION"`.
- **Belnap Cascade (`cascade.py`):** True `told_false = True` assignment on contradiction; `told_true = True` on entailment.
- **Functional Coherence (`coherence.py`):** Tool receipt premise entails narration hypothesis.
- **Rule Induction (`induction.py`):** Bidirectional entailment for clustering; contradiction for quarantine.
- **Fact Extraction (`memory_commit_service.py`):** Candidate triples verified for entailment against user transcript.

### Phase 4: Model-Agnostic Post-Turn Distiller
- Add `config/grammars/belief_distill.gbnf` for constrained JSON output.
- Create `src/lucca/reasoning/distill.py` calling active `SpeechLLMPort`.
- Wire into post-turn consolidation loop: confirmed contradictions distilled into clean third-person declarative propositions.

### Phase 5: Documentation & Milestone Release
- Ratify `D-MEM-08` in `docs/DECISIONS.md`.
- Bump `__version__ = "1.35.7"` in `src/lucca/__init__.py`.
- Document in `CHANGELOG.md` under `[1.35.7]`.

---

## 5. Pre-Registered Acceptance Gates

*   **`G-V1357-HYGIENE`**: 0 instances of hardcoded `is_conflict_top=False`, `topic=None`, or `content=new_content` (user transcript) in production belief code paths.
*   **`G-V1357-LATENCY`**: OpenVINO Verifier single-pair latency $\le 25\,\text{ms}$ on host hardware (Intel Core Ultra CPU/NPU).
*   **`G-V1357-BELNAP`**: A negative memory assertion (*"The API does not support X"*) queried with *"Does the API support X?"* assigns `told_false=True` and evaluates to `BelnapValue.FALSE`, not `TRUE`.
*   **`G-V1357-RULE`**: Opposing rule candidate pair (*"always use single quotes"*, *"never use single quotes"*) is rejected from single-cluster merging.
*   **`G-V1357-DISTILL`**: Confirmed contradiction converts into third-person canonical proposition without user conversational filler.
*   **`G-V1357-REGRESS`**: All 1,243 existing unit/regression tests and 24 static gates pass green.

---

## 6. What Is NOT Claimed in v1.35.7

*   Does not replace primary reasoning LLMs (Gemma 4 remains primary conversational / tool reasoning engine).
*   Does not claim zero latency for post-turn distillation; distillation is strictly asynchronous and off the audio playback path.
*   Does not replace SMT formal verification (Z3 SMT solver continues to handle mathematical and code invariants in WO-30).
