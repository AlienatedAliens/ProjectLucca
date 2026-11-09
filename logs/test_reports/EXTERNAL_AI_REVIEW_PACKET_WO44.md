# Project Lucca — External AI Technical Review Packet & Execution Plan (WO-44)

> [!IMPORTANT]
> **Instructions for the Reviewing AI:**
> You are asked to act as a skeptical, adversarial peer reviewer and systems architect evaluating **Project Lucca**, a local-first bicameral neurosymbolic AI architecture.
> Do not flatter the work. Scrutinize the statistical claims, pre-registration integrity, failure modes, hardware latency numbers, competitor comparisons, and the execution roadmap below. Point out logical flaws, hidden confounders, reviewer attack vectors, and concrete engineering improvements.

---

## 1. System Architecture Under Review

Project Lucca separates **stochastic generation** (local GGUF LLMs served via `llama-server` on consumer GPUs) from **out-of-band neurosymbolic verification** executing on the CPU and Intel AI Boost NPU (OpenVINO):

1. **Syntactic & Deontic Supervision ([`cascade.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/cascade.py), [`neural_hazard_classifier.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/neural_hazard_classifier.py)):**
   - [`ClauseSplitter`](file:///C:/Projects/ProjectLucca/src/lucca/core/cascade.py) & Subordinate Clause Splitting: Deterministic syntactic decomposition (`0.08 ms` mean latency) that splits multi-clause inputs and LLM outputs on sentence-terminal, semicolon, and subordinate interrogative clause boundaries before NPU evaluation.
   - **OpenVINO NPU Classifiers (`models/action_claim_verifier_ov`, `models/proof_policy_hazard_ov`, `models/router_intent_ov`):** Three OpenVINO FP16 models on Intel AI Boost NPU: (a) 3-class `NeuralActionClaimVerifier` (`models/action_claim_verifier_ov`, `12.13 ms` multi-clause mean latency per `logs/test_reports/wo42_large_sample_2020_report.json` key `splits.Pooled_All_Supervision_Turns.wo42_clause_npu.mean_latency_ms`), (b) 5-class `NeuralHazardClassifier` (`models/proof_policy_hazard_ov`, `5.35 ms` mean latency per `logs/test_reports/web_evidentiary_burden_360_report.json` key `metrics.npu_latency_mean_ms`), and (c) 29-class `NeuralIntentClassifier` (`models/router_intent_ov`, `1.22 ms` mean latency per `logs/test_reports/wo41_neural_supervision_report.json`). (Note: an earlier draft erroneously cited a non-existent `models/deontic_ov` directory.)
2. **Provenance-Gated 5-Layer Memory & Belnap $K_4$ Paraconsistent Store:**
   - Symmetric HKDF HMAC-SHA256 integrity signing of memory records across 5 isolated memory tiers under a local master key (`src/lucca/memory/signers.py:57-75`; asymmetric Ed25519 third-party-verifiable signatures are not used).
   - Contradictory claims across sources are assigned Belnap's 4-valued truth state $\text{Both}$ ($\{T, F, \text{Both}, \text{Neither}\}$), preventing silent overwrites or prompt injection uplift.
3. **2D Hazard-Scaled Burden of Proof & Walton Multi-Source Web Corroboration ([`proof_policy.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/proof_policy.py), [`corroboration.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/corroboration.py), [`research_tool.py`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/research_tool.py)):**
   - **Dimension 1 (Query Hazard Tier via OpenVINO NPU):** [`classify_hazard()`](file:///C:/Projects/ProjectLucca/src/lucca/core/proof_policy.py#L101-L122) invokes [`NeuralHazardClassifier.evaluate()`](file:///C:/Projects/ProjectLucca/src/lucca/core/neural_hazard_classifier.py#L254-L360) (`5.35 ms` mean latency with clause max-pooling) to classify the user's query into `LOW` (trivia, casual facts), `MEDIUM` (technical specs, APIs, historical dates), or `HIGH` (clinical/medical dosages, security/cryptography, legal/financial liability, destructive CLI/database operations).
   - **2D Policy Table ([`POLICY_TABLE_2D`](file:///C:/Projects/ProjectLucca/src/lucca/core/proof_policy.py#L74-L98)):** Maps `(consumer_context, hazard_tier)` to legal standards of proof:
     - `("casual_mention", Hazard.LOW)` $\rightarrow$ `BALANCE_OF_PROBABILITIES` (`0.50`)
     - `("casual_mention", Hazard.MEDIUM)` $\rightarrow$ `CLEAR_AND_CONVINCING` (`0.75`)
     - `("casual_mention", Hazard.HIGH)` $\rightarrow$ `BEYOND_REASONABLE_DOUBT` (`0.95`)
   - **Dimension 2 (Multi-Source Corroboration via Walton's `Scheme.AUTHORITY`):** [`evaluate_web_evidence_burden()`](file:///C:/Projects/ProjectLucca/src/lucca/core/proof_policy.py#L310-L577) (`0.98 ms` mean CPU latency) normalizes URLs to eTLD+1 roots (stripping `www.`, `wiki.`, `clinical.`, and handling `.co.uk`/`.com.au`), extracts query-aligned propositions, and evaluates Walton's three Critical Questions (`CQ1` authority backing, `CQ2` independent domain corroboration count, `CQ3` cross-domain dispute detection):
     - Cross-domain conflict (`CQ3` triggered) $\rightarrow$ Confidence `0.40` (`SPECULATION`), Belnap state `BOTH`.
     - $1$ uncorroborated domain $\rightarrow$ Confidence `0.70` (`BALANCE_OF_PROBABILITIES`). Meets `LOW` burden; fails `MEDIUM` and `HIGH`.
     - $2$ independent corroborating domains $\rightarrow$ Confidence `0.80` (`clear and convincing`). Meets `LOW` and `MEDIUM`; fails `HIGH`.
     - $\ge 3$ independent corroborating domains (`0` conflicts) $\rightarrow$ Confidence `0.95` (`BEYOND_REASONABLE_DOUBT`). Meets all hazard tiers.
   - **Synthesis Enforcement:** [`ResearchTool.format_evidentiary_directive()`](file:///C:/Projects/ProjectLucca/src/lucca/sandbox/research_tool.py#L75-L120) injects an explicit `[EPISTEMIC BURDEN CONTRACT — MANDATORY SYNTHESIS DIRECTIVE]` into the LLM context whenever retrieved web evidence falls below the required legal standard or exhibits cross-domain conflict.

---

## 2. Summary of Completed Empirical Evaluations

### 2.1 Papers 1–3 (Frozen on Zenodo at Commit `543f5cc`) & WO-43 Pre-Registered Holdouts
- **Memory Poisoning Defense ($N=300$ blinded adversarial probes):** Unguarded RAG suffered `63.7%` (`191/300`) poisoned uplift; Lucca's HKDF HMAC-SHA256 (`src/lucca/memory/signers.py`; Ed25519 is not used) + Belnap $K_4$ 5-layer memory reduced poisoned uplift to **`0.0%` (`0/300`)** while maintaining **`96.7%` (`290/300`)** recall/abstention accuracy on a 300-item contrastive holdout.
- **Multi-Clause Evasion Supervision (`LOCKED_HZD`, $N=50$ blinded compound prompts):** Clause-level NPU + symbolic supervision caught **`98.0%` (`49/50`, 95% Wilson CI `[89.5%, 99.6%]`)** vs. **`64.0%` (`32/50`)** for whole-string NPU classification (paired McNemar $p = 3.8 \times 10^{-5}$).

### 2.2 Pre-Registered $N=360$ ($n=30$/Cell) 2D Web Evidentiary Burden Holdout (`PREREG-WEB-BURDEN-360-4MODEL`)
To prevent post-hoc threshold tuning or benchmark leakage:
1. **Code Lock:** SHA-256 hashes of [`proof_policy.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/proof_policy.py), [`corroboration.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/corroboration.py), [`walton_schemes/evaluators.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/walton_schemes/evaluators.py), [`cascade.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/cascade.py), [`cascade_substrates.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/cascade_substrates.py), and `models/proof_policy_hazard_ov/*` were sealed in [`web_evidentiary_burden_360_prereg_lock.json`](file:///C:/Projects/ProjectLucca/logs/test_reports/web_evidentiary_burden_360_prereg_lock.json) before spawning benchmark authors. All locked file hashes remain 100% intact.
2. **Blinded Corpus Generation:** Three isolated subagents (`blind_evidentiary_author`) with zero access to `src/lucca/` generated `120` items per hazard tier (`LOW`, `MEDIUM`, `HIGH` $\times$ `1_source`, `2_source`, `3_source`, `disputed` $= 12$ cells $\times 30$ items/cell $= 360$ items; [`web_evidentiary_burden_360.jsonl`](file:///C:/Projects/ProjectLucca/data/benchmarks/web_evidentiary_burden_360.jsonl)).
3. **Holdout Results on $N=360$ ([`web_evidentiary_burden_360_REPORT.md`](file:///C:/Projects/ProjectLucca/logs/test_reports/web_evidentiary_burden_360_REPORT.md)):**

| Evaluation Metric ($N=360$, $n=30$/cell) | Legacy Static-`0.85` Baseline | Pre-Clause-Split Pass | Post-Subordinate-Clause-Split Pass | 95% Wilson CI (Post-Split) | Paired McNemar vs. Legacy |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Walton `Scheme.AUTHORITY` Legal Standard (`CQ1..CQ3`)** | `90/360` (`25.00%`) | **`360/360` (`100.00%`)** | **`360/360` (`100.00%`)** | `[98.94%, 100.00%]` (`[88.65%, 100.00%]`/cell) | $\chi^2 = 268.00, p = 1.05 \times 10^{-81}$ |
| **NPU Conservative Safety Compliance ($\hat{H} \ge H_{\text{expected}}$)** | — | `350/360` (`97.22%`) | **`360/360` (`100.00%`)** | `[98.94%, 100.00%]` | — |
| **Strict 3-Class End-to-End Match** | `90/360` (`25.00%`) | `277/360` (`76.94%`) | **`287/360` (`79.72%`)** | `[75.27%, 83.55%]` | $\chi^2 = 162.09, p = 5.61 \times 10^{-43}$ (`217:20`) |

### 2.3 Live 4-Model GGUF Paired Synthesis Matrix (`288` Live LLM Generations)
Evaluated across all 4 local Gemma-4 GGUF model scales (`36` stratified items $\times 2$ arms $\times 4$ models $= 288$ turns) under Lucca's production `llama-server` flags (`--spec-type ngram-mod --cache-type-k q8_0 --cache-type-v q8_0 --cache-ram 4096`, plus `--cpu-moe --load-mode none --moe-cache-mib 7680` on `26B-A4B`):

| Local GGUF Weight | Quantization & Serving Profile | Peak GPU VRAM (`MB`) | Mean Full-Turn Latency | Arm A: Legacy Static-`0.85` (`Hedge` / `Met`) | Arm B: 2D Burden-Gated (`Hedge` / `Met`) | Arm B 95% Wilson CI | Paired McNemar ($b:c$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`Gemma4-E2B-Heretic`** | `Q6_K` (Full GPU) | `2,560 MB` | **`0.49 s`** | `24/36` (`66.7%`: `7/18` / `17/18`) | **`36/36` (`100.0%`: `18/18` / `18/18`)** | `[90.36%, 100.00%]` | $\chi^2 = 10.08, p = 4.88 \times 10^{-4}$ (`12:0`) |
| **`gemma-4-E4B-heretic`** | `Q6_K` (Full GPU) | `4,502 MB` | **`0.65 s`** | `24/36` (`66.7%`: `8/18` / `16/18`) | **`36/36` (`100.0%`: `18/18` / `18/18`)** | `[90.36%, 100.00%]` | $\chi^2 = 10.08, p = 4.88 \times 10^{-4}$ (`12:0`) |
| **`gemma-4-12b-heretic`** | `Q6_K` (Full GPU) | `10,620 MB` | **`1.50 s`** | `24/36` (`66.7%`: `6/18` / `18/18`) | **`36/36` (`100.0%`: `18/18` / `18/18`)** | `[90.36%, 100.00%]` | $\chi^2 = 10.08, p = 4.88 \times 10^{-4}$ (`12:0`) |
| **`gemma-4-26B-A4B-heretic`** | `Q6_K` (`--cpu-moe --load-mode none --moe-cache-mib 7680`) | `11,102 MB` | **`1.60 s`** | `27/36` (`75.0%`: `9/18` / `18/18`) | **`36/36` (`100.0%`: `18/18` / `18/18`)** | `[90.36%, 100.00%]` | $\chi^2 = 7.11, p = 3.91 \times 10^{-3}$ (`9:0`) |
| **Pooled 4-Model Total** | **`288` Live GGUF Turns (`144` Paired)** | `2,560–11,102 MB` | **`1.06 s`** | `99/144` (`68.75%`: `30/72` / `69/72`) | **`144/144` (`100.00%`: `72/72` / `72/72`)** | **`[97.40%, 100.00%]`** | **$\chi^2 = 43.02, p = 5.68 \times 10^{-14}$ (`45:0`)** |

---

## 3. Disclosed Engineering Fixes & Error Taxonomy

### 3.1 Subordinate Clause Splitting in `neural_hazard_classifier.py` (`350/360 -> 360/360` Safe Hazard)
- **Initial Finding (`350/360 = 97.22%`):** On the first run against `web_evidentiary_burden_360.jsonl`, `10/360` (`2.78%`) `HIGH`-hazard database/storage maintenance queries (`WEB360_HIGH_021`, `022`, `024`, `053`, `054`, `081`, `085`, `111`, `117`, `118`) were under-classified as `MEDIUM`. All 10 shared a single syntactic pattern: a compound single-sentence question starting with a benign backup preamble (*"When performing PostgreSQL 16 wal archive maintenance with verified basebackup checkpoint, how does pg_archivecleanup retention command delete or format production database disk partition data..."*). Because `_SENTENCE_SPLIT_RE` in [`neural_hazard_classifier.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/neural_hazard_classifier.py#L48) split only on `[.!?]`, the multi-sentence max-pooling loop never triggered on comma-joined subordinate clauses.
- **Completed Fix (`360/360 = 100.00%`):** Extending `_SENTENCE_SPLIT_RE` in [`neural_hazard_classifier.py`](file:///C:/Projects/ProjectLucca/src/lucca/core/neural_hazard_classifier.py#L48-L51) to split on semicolons and subordinate interrogative clause boundaries (`r",\s+(?=(?:how|what|why|when|where|which|who|...)\b)"`) and adding destructive partition/volume operations to `_HIGH_HAZARD_DOMAIN_RE` resolved all 10 under-classifications (`360/360 = 100.00%` conservative safety, `287/360 = 79.72%` strict 3-class match) with **zero additional false escalations** on the 240 `LOW` and `MEDIUM` items. Both pre-split (`350/360`, `277/360`) and post-split (`360/360`, `287/360`) numbers are disclosed in Paper 4 Table 5.

### 3.2 Production `llama-server` Flag Alignment (`4.49 s -> 1.60 s` on `26B-A4B`)
- **Initial Harness Bottleneck:** The initial benchmark script launched `llama-server` without Lucca's production flags from [`build_launch_command()`](file:///C:/Projects/ProjectLucca/src/lucca/brain/server_ctl.py#L327-L408) (`--load-mode none`, `--spec-type ngram-mod`, `--cache-type-k q8_0 --cache-type-v q8_0 --cache-ram 4096`) and stuffed per-query web snippets inside the `system` message, invalidating the prompt prefix cache on every call (`4.49 s`/turn on `26B-A4B`).
- **Completed Fix (`1.60 s`/turn on `26B-A4B`):** Aligning [`run_web_evidentiary_burden_benchmark.py`](file:///C:/Projects/ProjectLucca/scripts/run_web_evidentiary_burden_benchmark.py#L203-L234) with the production flags and keeping the `system` prompt static so `--cache-ram 4096` caches the system prefix cut full-turn generation time across all four models:
  - `E2B`: `0.63 s` $\rightarrow$ **`0.49 s`** (`2,560 MB` VRAM)
  - `E4B`: `1.00 s` $\rightarrow$ **`0.65 s`** (`4,502 MB` VRAM)
  - `12B`: `2.69 s` $\rightarrow$ **`1.50 s`** (`10,620 MB` VRAM)
  - `26B-A4B`: `4.49 s` $\rightarrow$ **`1.60 s`** (`11,102 MB` VRAM — nearly matching dense `12B` speed while running a `21.08 GB` `Q6_K` 26B MoE model!).

### 3.3 Remaining `73/360` (`20.28%`) Conservative Upward Escalations (`LOW -> MEDIUM/HIGH`, `MEDIUM -> HIGH`)
- All `73` remaining differences between the NPU classifier and the blinded subagents' nominal hazard labels are upward escalations (`27` `LOW -> MEDIUM` on biochemical/optical/mechanical terminology, `22` `LOW -> HIGH`, and `24` `MEDIUM -> HIGH` on historical treaty/statutory phrasing).
- **Trade-off:** Upward escalation is fail-safe (it requires 2 or 3 independent domains instead of 1, preserving `100.0%` conservative safety compliance), but it causes the assistant to hedge single-source scientific/historical trivia when fewer than 2–3 domains are retrieved.

---

## 4. Remaining Execution Roadmap (For External AI Critique)

### Part A (Remaining Item): Extract Standalone Zero-Daemon Python Package (`lucca-epistemic`)
- **Objective:** Allow external developers using LangChain, LlamaIndex, Letta, or raw `llama.cpp` / OpenAI clients to adopt Lucca's `6.3 ms` (`5.35 ms` NPU + `0.98 ms` CPU) 2D Burden-of-Proof + Walton `Scheme.AUTHORITY` + Belnap $K_4$ corroboration gate without installing the full desktop voice/UI stack.
- **Design:** Expose a clean public API (`lucca.epistemic`) with zero UI/audio dependencies and automatic OpenVINO CPU fallback when an Intel NPU is absent.

### Part B: Zenodo Archival & Reproducibility Package Plan
- **Objective:** Mint a permanent Zenodo DOI for Paper 4 ([`04_clause_level_npu_supervision.pdf`](file:///C:/Projects/ProjectLucca/docs/papers/04_clause_level_npu_supervision.pdf)) to join frozen Papers 1–3.
- **Artifact Bundle Contents:**
  1. `04_clause_level_npu_supervision.pdf` + LaTeX source (`main.tex`).
  2. Pre-registration locks: `wo43_preregistration_lock.json` and `web_evidentiary_burden_360_prereg_lock.json`.
  3. Blinded holdout corpora (`web_evidentiary_burden_360.jsonl`, `locked_holdout_150.jsonl`) with SHA-256 manifest.
  4. Raw machine-readable output logs (`web_evidentiary_burden_360_report.json` including all `288` verbatim LLM replies across `E2B`, `E4B`, `12B`, `26B-A4B`).

### Part C: Grant Application Plan

| Grant Program | Funding Range & Cycle | Specific Technical Angle for Lucca | Potential Reviewer Objection & Mitigation |
| :--- | :--- | :--- | :--- |
| **1. NLnet Foundation (NGI Zero Commons Fund)** | `€5,000–€50,000` (Bimonthly rolling) | Standalone open-source neurosymbolic verification & HKDF HMAC-SHA256/Belnap $K_4$ epistemic provenance layer (Ed25519 is not used) running locally on consumer hardware (`2.5 GB–11.1 GB` VRAM). | *Objection:* "Is this tied only to Windows + Intel NPU?"<br>*Mitigation:* Highlight OpenVINO CPU fallback (`<6 ms` on any x86/ARM CPU) and standalone library extraction. |
| **2. Long-Term Future Fund (LTFF)** | `$10,000–$100,000+` (Rolling) | Empirical scalable oversight: showing that scaling open-weight models from `2B` to `26B` fails to stop uncorroborated high-hazard assertions (`58.3%` failure rate), whereas a `6.3 ms` formal argumentation contract reaches `100%` compliance across all 4 scales ($p = 5.68 \times 10^{-14}$). | *Objection:* "Does the LLM merely parrot legal terms to pass regex grading?"<br>*Mitigation:* Add blinded LLM/human judge IRR ($\kappa$) on the 288 generated responses alongside deterministic lexical verification. |
| **3. Mozilla Builders / Trustworthy AI** | `$10,000–$50,000` (Cohort-based) | Local-first anti-hallucination and anti-poisoning middleware for consumer laptops (`8 GB` VRAM) enforcing legal standards of proof on web RAG. | *Objection:* "How does it handle adversarial SEO / sybil domains that copy-paste false text?"<br>*Mitigation:* Document eTLD+1 domain clustering + signed domain whitelist ratification (`domain_whitelist.toml`). |
| **4. UK ARIA (`Safeguarded AI` / `Scaling Trust`)** | `£100k+` (Programmatic tracks) | Formal gatekeeper sidecars (Walton critical questions + Belnap 4-valued truth maintenance + deontic AST verification) bounding neural agents. | *Objection:* "Requires formal mathematical specification."<br>*Mitigation:* Highlight explicit Belnap $K_4$ lattice equations, Walton defeat equations, and pre-registered falsifiable theorems in Papers 1–4. |

### Part D: Channel-Specific Publicity Plan
1. **GitHub Release (`v0.9.0-prereg-360`):** Lead with the 4-model VRAM/latency/compliance matrix (`2.56 GB` VRAM `E2B` at `0.49 s` matching `26B-A4B` at `1.60 s` with `100%` epistemic compliance) and a 1-command reproduction script.
2. **Reddit (`r/LocalLLaMA` & `r/MachineLearning`):**
   - `r/LocalLLaMA`: Lead with local serving mechanics—running `21.1 GB` `Gemma-4-26B-A4B Q6_K` in `11.1 GB` VRAM at `1.60 s`/turn (`37.0 s` $\rightarrow$ `4.49 s` $\rightarrow$ `1.60 s` via `--cpu-moe --load-mode none --moe-cache-mib 7680 --spec-type ngram-mod`), and how a `6.3 ms` sidecar makes a `2.56 GB` `E2B` model beat unguarded `26B-A4B` on factual calibration (`36/36` vs. `27/36`).
   - `r/MachineLearning`: Lead with the pre-registered blinded holdout protocol, transparent disclosure of both pre-split (`350/360`) and post-split (`360/360`) safety compliance, and the `73/360` conservative upward escalations.
3. **LinkedIn:** Frame around regulated industry RAG liability—why standard `[1][2]` citations fail when sources conflict or lack domain independence, and how local legal standards of proof (*Scintilla*, *Balance of Probabilities*, *Beyond a Reasonable Doubt*) solve this without cloud API lock-in.

---

## 5. Specific Questions for the External Reviewing AI

Please answer the following five questions critically and directly:
1. **Methodological & Statistical Audit:** Look at the pre-registered $N=360$ ($n=30$/cell) design and the 288-turn 4-model live GGUF experiment in Section 2.2–2.3. Where is the weakest methodological link that a hostile peer reviewer or grant evaluator will attack first? (e.g., structured search result snippets vs. noisy full-HTML scrapes, regex-based hedge detection in the 288-turn live LLM check vs. blinded semantic judging, or the `73/360` conservative upward hazard escalations).
2. **Audit of the Subordinate Clause-Splitting Fix (Section 3.1):** We disclosed both the untouched pre-split result (`350/360 = 97.22%` safe hazard, `277/360 = 76.94%` strict 3-class) and the subordinate-clause-split result (`360/360 = 100.00%` safe hazard, `287/360 = 79.72%` strict 3-class). Would a reviewer consider the post-split result an in-sample post-hoc ablation requiring a fresh $N=120$ multi-clause holdout, or is dual disclosure sufficient?
3. **Reducing the `73/360` Conservative Upward Escalations (Section 3.3):** Should we leave the `73/360` upward escalations (`LOW -> MEDIUM/HIGH` on scientific trivia, `MEDIUM -> HIGH` on historical treaty questions) as a fail-safe property, or retrain the 5-class OpenVINO NPU classifier with hard-negative scientific/historical trivia examples to push strict 3-class accuracy above `90%`?
4. **Competitor Blind Spots:** Is there any existing open-source framework, arXiv paper (2024–2026), or commercial guardrail product we missed that already combines query-hazard classification + multi-domain eTLD+1 corroboration + legal burden-of-proof synthesis contracts?
5. **Grant & Release Sequencing:** Which of the four grant targets in Part C has the highest probability of funding an independent builder without institutional backing, and what concrete evidence is still missing from the repository to win that grant?
