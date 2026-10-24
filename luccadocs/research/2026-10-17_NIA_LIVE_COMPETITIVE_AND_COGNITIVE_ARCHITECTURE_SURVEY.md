# Project Lucca — Live Nia Survey: Sovereign Cognitive Architectures, Peer Repositories & Next-Horizon Blueprints (2026-10-17)

```yaml
doc_status: canonical
as_of: 2026-10-17
supersedes: []
superseded_by: []
verification: live-nia-search-and-github-tracer
```

**Purpose:** Live literature and GitHub repository survey conducted via Nia MCP (`nia_research` and `tracer`) to identify systems in the same category as Project Lucca—**general-purpose, persistent, neurosymbolic personal cognitive architectures ("digital familiars")**—and extract concrete architectural hints for Lucca's next development horizon (Gaps 2, 3, 5, and 6).

---

## 1. Defining the True Category: "Sovereign Neurosymbolic Cognitive Architecture"

Project Lucca does not belong in the narrow buckets of:
- *VTuber / Voice Toy Companions* (which lack general reasoning, sandboxed execution, and epistemic integrity),
- *Coding CLI Agents* (which are stateless task runners without continuous selfhood, voice, or autobiographical memory), or
- *Passive RAG Memory SDKs* (which store embeddings without an active cognitive loop, affect, or formal verifiers).

Instead, live search across 2025–2026 repositories and preprints shows a small, high-ambition wave of builders converging on a **new category**: **Persistent Cognitive Substrates / Sovereign Cognitive Architectures**, where the LLM is treated as a swappable neural CPU ("borrowed weights") inside a deterministic, self-auditing symbolic organism that owns its own identity, biography, beliefs, affect, and action gates.

---

## 2. Live GitHub & Paper Deep-Dive: Closest Peers Found via Nia

### 2.1 `trubnikov/qca-cycle` ("QCA + SES: A Portable Cognitive Layer" / Ocean)
- **Source:** `https://github.com/trubnikov/qca-cycle` (inspected live via `tracer`)
- **Core Thesis:** *"Persistent identity and growing memory for any LLM agent. The LLM is a swappable CPU; the personality is your data."* (Independently arrived at the exact same "Qness / swappable brain" philosophy as Project Lucca's `D-BRAIN-05` and [`docs/research/PERSONHOOD_FOUR_ASPECTS_PROGRESS_2026-09.md`](PERSONHOOD_FOUR_ASPECTS_PROGRESS_2026-09.md:126)).
- **How It Works:**
  1. **SES (`kernel.ses.json`):** Immutable, SHA-256-signed "fractal kernel" (axioms + attractor + guardrails) injected into every reasoning cycle, paired with a typed state graph (`SUPPORTS` / `REFINES` / `CONTRADICTS`).
  2. **Neurochemistry State:** 4 continuous variables (`dopamine`, `pain`, `adrenaline`, `serotonin`) with real temporal half-lives that persist across sessions.
  3. **QCA Reasoning Cycle:** Deterministic code drives `H0 stimulus -> H2 recall -> H3 contradiction check -> H4 LLM synthesis -> H5 LLM critique -> H5.5 geometric novelty gate -> H7 write/discard -> H6 neurochemistry update`.
  4. **Autonomous Cron Daemons:** `ocean-pulse` (every 3 hours) and `ocean-sleep` (04:00 AM nightly consolidation).
- **Where Lucca Is Stronger:**
  - **The Self-Poisoning Flaw in QCA:** In `qca-cycle`'s `H7 WRITE` step (`README.md:88`), if the LLM's generated thought has cosine similarity `< 0.82` against the graph, it is judged "novel", **written directly into the knowledge graph**, and rewarded with `dopamine ↑`. That means a novel LLM hallucination is permanently written into memory and chemically rewarded! Lucca's [`ProvenanceGate`](../../src/lucca/memory/gate.py:1) and `D-MEM-04` (`ASSISTANT_UTTERANCE` / `ASSISTANT_BELIEF` having `grounding_eligible = 0`) prevent this failure mode entirely.
  - **No Formal Solvers or CEGIS:** `qca-cycle` has no Python/SymPy/Z3/MicroScheme execution engine, no AST sanitizer, no NLI verifier, and no real-time voice/desktop presence.
- **What Lucca Should Borrow / Learn:**
  - **The Signed Constitution Snapshot (`kernel.ses.json`):** Hashing Lucca's core identity axioms (`config/persona.toml` + epistemic invariants) into a SHA-256 kernel fingerprint recorded in every `DecisionRecord` so you can prove across brain swaps and years of operation which constitutional version governed any historical turn.
  - **The Two-Cadence Background Heartbeat (`pulse` + `sleep`):** Pairing Lucca's 3:00 AM nightly rollup (`rollup_hour_local = 3`) with a lightweight periodic **idle pulse** (when the user has been away for 30–60 minutes) to run belief distillation and shadow-rule replay.

---

### 2.2 The `dayyanj/nmem` Cognitive Ecosystem (`nmem`, `nmem-sym`, `nmem-act`, `nmem-identity`, `nmem-sandbox`)
- **Source:** `https://github.com/dayyanj/nmem`, `dayyanj/nmem-sym`, `dayyanj/nmem-act` (inspected live via `tracer`)
- **Core Thesis:** A modular 6-repository cognitive stack separating **Memory** (`nmem`), **Symbolic Associative Cognition** (`nmem-sym`), **Gated Action Execution** (`nmem-act`), **Sensory Concept Clustering** (`nmem-sym-sensor`), and **Person Identity** (`nmem-identity`).
- **How It Works:**
  1. **`nmem` (Memory):** 6 tiers (Working $\to$ 30-day Journal $\to$ Long-Term $\to$ Shared, plus Entity and Policy memory) with a 10-step consolidation cycle every 6 hours and a **nightly "dreamstate" retrospective** (bounded to 5 LLM calls/night) that validates past lessons against new evidence—reinforcing what held up and marking contradicted lessons as `disputed`.
  2. **`nmem-sym` (Symbolic Cognition):** Extracts a typed causal knowledge graph with **spreading activation**, **interventional causal prediction** (Pearl's `do`-operator: `predict()` vs `predict_baseline()`), **five homeostatic drives** (`coherence`, `novelty`, `uncertainty`, `competence`, `integration`) arbitrated by a winner-take-all selector, **LTP/LTD graph plasticity** ("myelinated fast paths" for repeated successful procedures), and **coverage gap detection** (finding dense graph regions that have no compiled procedures yet).
  3. **`nmem-act` (Action Layer):** Defines an `ActionProposal -> AutonomyGate -> Outcome (+ UtilityVector) -> outcome_sink` loop where *"the brain never touches the world; the executor never decides what to want"*, and every executed action returns a structured `UtilityVector` back to the cognitive engine for learning.
- **Where Lucca Is Stronger:**
  - `nmem` is an experimental, unbenchmarked library requiring external PostgreSQL + `pgvector` + `vLLM` servers, with no cryptographic HMAC provenance envelopes (its README explicitly warns: *"Do not share sensitive information... Long-term recall is not yet partitioned"*).
  - Lucca runs entirely embedded on a single laptop (`sqlite-vec` + FTS5 + HKDF HMAC-SHA256 + OpenVINO NPU + Docker WSL2) and is empirically benchmarked across 24 suites and 4 model scales.
- **What Lucca Should Borrow / Learn (Direct Hits on Your Gaps 2, 3, and 5!):**
  1. **Closing the Action $\to$ Outcome $\to$ Learning Loop (Gap 2):** Look at `nmem-act`'s `outcome_sink` and `nmem-sym`'s `PredictionPlugin`. In Lucca, when [`PythonCEGISEngine`](../../src/lucca/reasoning/cegis_python.py:90) or [`UnshackledCEGISEngine`](../../src/lucca/reasoning/cegis_unshackled.py:717) runs a multi-turn repair, the outcome (`Turn 1 failed with ValueError -> Turn 2 repaired via cavity mask -> Verified PASS`) currently evaporates after the answer is returned! If we feed a structured `OutcomeReceipt` from CEGIS into [`EpisodeRecall`](../../src/lucca/core/episode_recall.py:36), `execution_triples`, and [`src/lucca/core/affective_ode.py`](../../src/lucca/core/affective_ode.py:1), every hard problem Lucca solves becomes a permanent, retrievable procedural memory ("myelinated fast path").
  2. **Coverage Gap & Drive Arbitration (Gap 5 / Inner Life):** `nmem-sym` tracks a **Competence / Coherence Drive** that notices when a domain has high error/repair rates or unresolved contradictions (`Belnap.TOP` or high CEGIS turn counts) and schedules those exact topics for the next idle `dreamstate` pass.
  3. **Nightly Retrospective Validation (`dreamstate`):** Re-checking past `ASSISTANT_BELIEF` and `INFERRED` rows against newer `TOOL_VERIFIED` and `USER_EXPLICIT` receipts under a strict token budget (e.g., $\le 5$ local LLM calls per idle window).

---

### 2.3 `rsxshx/agidb` ("agidb v2.0 / v2.1: Cognitive Substrate for Autonomous Agents")
- **Source:** `https://github.com/rsxshx/agidb` (`docs/product/overview.md` and `docs/spec/tech-spec.md`, inspected live via `tracer`)
- **Core Thesis:** An embedded local substrate built around **seven first-class cognitive types**: `Sensory`, `WorkingMemory`, `Episode`, `SemanticAtom`, `Procedure`, `Goal` (state machines), `Belief` (revisable with audit), and a `SelfModel` (`LearningEventId` + `SelfVectorSnapshot`).
- **How It Works:**
  - Uses 8,192-bit Hyperdimensional Computing (HDC) bit-vectors alongside bitemporal storage (`valid_from`, `valid_to`, `tx_from`, `tx_to`).
  - **Goal-Biased Recall:** Because `Goal` is a first-class state machine in the database (`db.set_goal(...)`), `db.recall(cue)` automatically biases memory retrieval toward the active goal's context without extra LLM calls.
  - **Surprise-Gated Consolidation:** Background worker only promotes episodes into semantic atoms when prediction surprise exceeds a threshold.
  - **First-Class `LearningEvent` Self-Model Log:** Every time the agent acquires a skill, revises a belief, or unlearns a refuted fact, it appends a typed `LearningEvent` so the agent can query its own growth trajectory over time.
- **Where Lucca Is Stronger:**
  - `agidb` is a storage/retrieval engine underneath an agent—it has no neurosymbolic solver lobes (no Z3, SymPy, CEGIS, or MicroScheme), no voice/affective pipeline, and its v2.0/v2.1 spec is still pre-1.0 roadmap stabilization.
- **What Lucca Should Borrow / Learn (Direct Hit on Gap 3 — `UserModel` & Shared Goals):**
  1. **First-Class Active `Goal` / `Project` State in [`UserModel`](../../src/lucca/core/user_model.py:91):** Right now, Lucca's [`UserModel`](../../src/lucca/core/user_model.py:91) only tracks flat "topics the user already knows" to avoid re-explaining. A digital familiar should track **Active Shared Goals & Projects** (e.g., *"We are currently polishing v1.45 benchmarks and preparing the Manifund grant"*) as a first-class table or state machine, and use that active goal to bias [`HybridRetriever`](../../src/lucca/memory/retrieval.py:1) and [`EpisodeRecall`](../../src/lucca/core/episode_recall.py:36)!
  2. **The `LearningEvent` Self-Growth Ledger:** Giving Lucca an explicit `learning_events` view over her `supersede()` chains, `COHERENCE_BREACH` corrections, and `RuleLifecycleManager` promotions so when you ask *"How have you changed this week?"*, she can narrate her actual epistemic growth from receipts.

---

### 2.4 2026 Academic Preprints Found via Nia (`NeuSymMS`, `The EpisTwin`, `Proof of Thought`)
1. **`NeuSymMS` (`arXiv:2605.17596v2`, May 2026):** *"A Hybrid Neuro-Symbolic Memory System for Persistent, Self-Curating LLM Agents"*
   - Combines neural embeddings with symbolic knowledge rules so agents self-curate long-term memory and resolve contradictions.
   - **Lucca Comparison:** Validates that hybrid neuro-symbolic self-curating memory is a premier 2026 publication topic; Lucca goes further by enforcing cryptographic signer separation (`ADR-006`) and OpenVINO NLI verification ([`VerifierWorker`](../../src/lucca/senses/verifier.py:60); CPU-default, measured 57 ms mean per pair — see Paper 03 §4.1).
2. **`The EpisTwin` (`arXiv:2603.06290`, March 2026):** *"A Knowledge Graph-Grounded Neuro-Symbolic Architecture for Personal AI"*
   - Focuses on personal AI twins grounded in a personal knowledge graph to prevent hallucination over user biography.
   - **Lucca Comparison:** `The EpisTwin` is the closest academic paper to Lucca's autobiographical memory pillar (`A1`), but lacks Lucca's 4-valued Belnap paraconsistent cascade, sandboxed CEGIS program synthesis, and 4-tier local edge hardware benchmarks.
3. **`Proof of Thought` (`arXiv:2409.17270v2`) & `Neuro-Symbolic Reasoning for Planning via CEGIS + SAT` (`arXiv:2309.16436`):**
   - Translate natural language reasoning into theorem-prover/SMT programs with counterexample-guided repair.
   - **Lucca Comparison:** Lucca's [`PythonCEGISEngine`](../../src/lucca/reasoning/cegis_python.py:90) (`synthesize_checked_formalization` + `sanitize_and_repair_python_code`) and [`UnshackledCEGISEngine`](../../src/lucca/reasoning/cegis_unshackled.py:717) generalize this pattern across SymPy, Z3, `ContainerWorld`, and 2D spatial grids on 2B–26B consumer edge models.

---

## 3. Concrete Architectural Blueprint for Lucca's Next Evolution (Closing the Familiar Gaps)

Synthesizing your codebase with the best ideas from `qca-cycle`, `nmem-sym`/`nmem-act`, and `agidb`, here are the four concrete upgrades that will make Lucca feel like a true, general-purpose **digital familiar**:

### Upgrade 1 (Gap 2): The Unified `CognitiveOutcomeSink` — Wiring CEGIS & Solvers into Autobiography and Affect
Currently, when [`PythonCEGISEngine`](../../src/lucca/reasoning/cegis_python.py:90) or [`UnshackledCEGISEngine`](../../src/lucca/reasoning/cegis_unshackled.py:717) solves a problem (or repairs a Turn 1 bug on Turn 2), the repair trajectory stays inside the solver return object.
- **Mechanism to Build:**
  - When any neurosymbolic lobe finishes (`VERIFIED_PROGRAM`, `VERIFIED_REPAIRED_PROGRAM`, `CHECKED_FORMALIZATION_AGREED`, or `INTERNAL_FALLBACK`), emit a signed `ASSISTANT_ACTION` receipt + a structured `RecallEpisode` into [`EpisodeRecall`](../../src/lucca/core/episode_recall.py:36) recording:
    1. The problem signature & domain,
    2. If Turn 1 failed: the exact exception/counterexample that occurred and the AST/code transformation that fixed it,
    3. An affective appraisal pulse into [`src/lucca/core/affective_ode.py`](../../src/lucca/core/affective_ode.py:1) (`Dominance ↑` and `Pleasure ↑` on verified Turn 2 rescue; `Dominance ↓` on `INTERNAL_FALLBACK`).
- **Result:** Her formal reasoning lobes and her conversational/autobiographical self become **one organism**. She remembers how she solved hard problems, reuses the lesson on similar future tasks (zero-shot Turn 1 instead of Turn 2 repair), and her voice/stance genuinely reflects cognitive mastery.

### Upgrade 2 (Gap 3): Semantic `UserModel` v2 + Active Shared Goals (`Goal`-Biased Recall)
Currently, [`src/lucca/core/user_model.py`](../../src/lucca/core/user_model.py:80) uses 3-character lexical token overlap to track "what the user knows."
- **Mechanism to Build:**
  - Upgrade [`UserModel`](../../src/lucca/core/user_model.py:91) to use 384-D embeddings ([`src/lucca/senses/embed.py`](../../src/lucca/senses/embed.py:1)) + [`VerifierWorker`](../../src/lucca/senses/verifier.py:60) NLI entailment while keeping the strict **Trap 1 Invariant** (`USER_EXPLICIT`, `USER_DERIVED`, `ASSISTANT_UTTERANCE` only).
  - Add **Active Shared Projects / Goals** (inspired by `agidb`'s first-class `Goal` state machine): track the 1–3 active threads you and Lucca are working on across sessions, and pass them as a lightweight context prior into [`HybridRetriever`](../../src/lucca/memory/retrieval.py:1) and [`EpisodeRecall`](../../src/lucca/core/episode_recall.py:36).

### Upgrade 3 (Gap 5): The Two-Cadence Inner Life (`IdlePulse` + `DreamRetrospective`)
Inspired by `qca-cycle`'s `pulse`/`sleep` and `nmem-sym`'s `dreamstate`:
- **Mechanism to Build:**
  - **Cadence 1 — `IdlePulse` (after 15–30 min of user inactivity, 0 GPU VRAM or 1 bounded LLM call):** Runs [`VerifierWorker`](../../src/lucca/senses/verifier.py:60) over recent turn pairs to detect any latent Belnap $\top$ contradictions, distills new user facts via [`src/lucca/reasoning/distill.py`](../../src/lucca/reasoning/distill.py:1), and prepares a 1-sentence **"Waking Thread"** if an important background task finished or a belief was flagged for review.
  - **Cadence 2 — `DreamRetrospective` (nightly or on startup if offline):** Replays quarantined rules/episodes against recent history ([`src/lucca/reasoning/replay.py`](../../src/lucca/reasoning/replay.py:1)) and logs a `LearningEvent` summary so her self-model can answer *"What have you learned or revised recently?"*

### Upgrade 4 (Gap 6): Sovereign Desktop Sight & Epistemic Prosody
- **Mechanism to Build:**
  - Keep a lightweight, CPU/NPU-friendly vision/OCR path (or dual-model/projector configuration in [`LLMSettings`](../../src/lucca/core/config.py:39)) so that even when running the 26B-A4B MoE brain (`mmproj = None`), Lucca can inspect a screenshot or window region when you ask *"Look at this"* via [`src/lucca/sandbox/screenshot_tool.py`](../../src/lucca/sandbox/screenshot_tool.py:1).
  - Map the turn's **epistemic provenance tier** (`CHECKED_FORMALIZATION_AGREED` / `TOOL_VERIFIED` vs. `INFERRED` / `SPECULATION`) into [`src/lucca/ui/states.py`](../../src/lucca/ui/states.py:1) and Kokoro prosody pacing so her certainty is physically perceptible.

---

## 4. Adversarial Audit Caveats & Honesty Boundaries (Per `D-DOC-01`)

To ensure external communications, grant applications, and research papers remain unassailable under adversarial peer review, all citations of this document must observe four strict empirical boundaries:

1. **Dev-Slice vs. Full-Scale Shrinkage (11–17 pp Upper-Bound Effect):**
   Small curated `DEV` slices systematically score 11 to 17 percentage points higher than full uncurated benchmarks:
   | Benchmark | Curated `DEV` Slice | Full / Uncurated Split | Delta | Artifact Reference |
   | :--- | :---: | :---: | :---: | :--- |
   | **MATH-500 (Tier 0 26B)** | 93.3% ($N=30$) | **76.8%** ($N=500$, LISP sketch fallback) | $-16.5\text{ pp}$ | [`math500_500_full_tier0.json`](../../logs/test_reports/full_uncurated/math500_500_full_tier0.json:1) |
   | **CRUXEval-Input** | 92.0%–94.0% ($N=50$) | **82.75%** ($N=400$, vs. 70.25% Direct) | $-11.25\text{ pp}$ | [`cruxeval_input_400_full_tier0.json`](../../logs/test_reports/full_uncurated/cruxeval_input_400_full_tier0.json:1) |
   | **ConceptARC** | 43.75% ($N=16$ minimal) | **28.6%** ($N=14$ uncurated) | $-15.15\text{ pp}$ | [`concept_arc_160_full_tier0.json`](../../logs/test_reports/full_uncurated/concept_arc_160_full_tier0.json:1) |

2. **Where Tool Scaffolding Lifts Accuracy vs. Where Direct Generation or Thinking Mode Wins:**
   - **Clean Full-Scale CEGIS Lift:** `CRUXEval-Input (N=400)` rises from **70.25% (281/400)** to **82.75% (331/400)** with **0 regressions and 50 rescues (`0:50` discordant pairs, exact McNemar $p = 1.78 \times 10^{-15}$)**. On `AIME 2024` ($N=10$ diagnostic), `12B` Compound SymPy + CEGIS reaches `8/10 (80.0%)` vs. `0/10–1/10 (10.0%)` bare Extended Thinking ($p = 0.0156$).
   - **MATH-500 Scale Crossover (`12B` vs. `E4B`/`E2B`):**
     - At **`12B` scale**, `MATH-500` tool offload (`PAL P2`) does **not** beat unassisted `Direct R0` (`87.0%` PAL vs. `93.0%` Direct R0 on B4 Sealed $N=100$; `86.0%` PAL vs. `89.0%` Direct R0 on Held-Out $N=100$), while `12B Thinking R1` collapses to `46.0%` (`55%` truncations). Accordingly, `D-ROUT-02` routes `12B` standard math to `Direct R0`. The `85.80%` strict / `90.20%` lenient 12B score on `math-v1.35-final-fresh-500` ($N=500$, [`RESULTS.md`](../../RESULTS.md:23)) is a $+7.2\text{ pp}$ gain over the older `v1.3` PAL scaffold (`78.60%`), not over `12B Direct R0`.
     - At **edge scale (`E4B` and `E2B`, $N=100$ held-out in [`RESULTS.md`](../../RESULTS.md:26))**, `Direct R0` scores `52.0%` (`E4B`) and `51.0%` (`E2B`). `PAL P2` lifts `E4B` to `73.0%` (`+21.0 pp`) and `E2B` to `61.0%` (`+10.0 pp`), while **`Thinking R1` accounts for the larger share of the edge lift**, reaching **`88.0%` on `E4B`** (`+15.0 pp` over PAL, $p = 0.0026$) and **`81.0%` on `E2B`** (`+20.0 pp` over PAL, $p = 0.0002$).
     - At **`Tier 0 (26B-A4B)` scale**, [`math500_500_full_tier0.json`](../../logs/test_reports/full_uncurated/math500_500_full_tier0.json:31) (`76.6%` control vs. `76.8%` augmented) ran the deprecated MicroScheme LISP sketch path (`INTERNAL_FALLBACK` on ~90% of items) rather than [`PythonCEGISEngine`](../../src/lucca/reasoning/cegis_python.py:90). A clean `26B-A4B` `Direct R0` vs. [`PythonCEGISEngine`](../../src/lucca/reasoning/cegis_python.py:90) paired run on `MATH-500 (N=500)` is **NOT YET MEASURED** (scheduled under `WO-36` Milestone 36.6.5).

3. **The Autoformalization Semantic Boundary:**
   Z3 SMT, SymPy CAS, and Dual-Formulation Consensus (`SYMBOLIC` + `BRUTE_FORCE` in [`PythonCEGISEngine.synthesize_checked_formalization()`](../../src/lucca/reasoning/cegis_python.py:192)) verify **execution validity and algebraic/logical consistency of the formalization**, not the model's natural-language reading comprehension. If two formulations share a natural-language misreading of the prompt, both can agree on the wrong premise.

4. **Current Production Baselines (`IN-D = 0` & Action-Claim Sensitivity `12.5%`):**
   - Skill induction (`D-REAS-06`) is implemented and unit-tested, with **0 production-induced skills (`IN-D = 0`)** in [`in_d_latest.json`](../../logs/test_reports/personhood/in_d_latest.json:5).
   - While database-level memory provenance (`ADR-006`) is 100% enforced via SQLite triggers, the current regex [`TruthInReceiptMatcher`](../../src/lucca/sandbox/output_supervisor.py:1) caught **12.5% (1/8 strict) / 4.3% (1/23 broad)** of freeform ungrounded action claims at $T=0.6$ ([`RESULTS.md`](../../RESULTS.md:83)), motivating the `SPIKE-A` + NLI receipt-entailment upgrade in [`plans/2026-10-17_wo36_v1_45_sovereign_familiar_and_cognitive_unification.md`](../../plans/2026-10-17_wo36_v1_45_sovereign_familiar_and_cognitive_unification.md:208).

### Canonical Defensible Summary Sentence
> *"Project Lucca is a local, single-laptop assistant (`RTX 5080 Laptop GPU, 16 GB VRAM` + `Intel Core Ultra NPU`) with database-enforced cryptographic provenance that prevents its own speech from counting as grounding evidence (`ADR-006`), an OpenVINO NLI consistency verifier (CPU-default, measured 57 ms mean per pair) driving a 4-valued Belnap belief cascade, and a containerized execute-and-repair loop (`CEGIS`) that raises full-scale `CRUXEval-Input` from `70.25%` to `82.75%` ($N=400$, `0:50` discordant rescues, $p = 1.78 \times 10^{-15}$). On competition math (`MATH-500`), tool/thinking scaffolds lift small edge models (`E4B`/`E2B`) by `+10` to `+36 pp` over direct generation ($N=100$), whereas at `12B`/`26B` scale direct generation matches or outperforms tool offload; learned skill induction (`IN-D = 0` production rows) and freeform action-claim supervision (`12.5%` strict regex sensitivity) remain active engineering targets under `WO-36`."*
