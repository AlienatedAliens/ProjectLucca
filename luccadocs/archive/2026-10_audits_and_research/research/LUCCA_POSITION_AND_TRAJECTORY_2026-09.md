# Project Lucca — Position & Trajectory Assessment

**Status:** Analytical assessment (not a ratified ADR)
**Date:** 2026-09-25
**Provenance:** Compiled from a multi-session external review exchange (frontier-model reviewer, "Sonnet"), direct codebase verification, and live literature searches via Nia. Every claim herein is marked **[VERIFIED]** (checked against code/tests this session), **[DOCUMENTED]** (asserted in canonical docs, not re-verified this session), or **[SEARCHED]** (checked against live literature via Nia, free-plan quick search — absence of a counterexample is weak evidence, not proof).

---

## Part 1 — Where Project Lucca Is

### 1.1 Verified System Inventory (as of 2026-09-25)

| Subsystem | State | Evidence |
|---|---|---|
| Source base | 100 Python modules, ~32,800 lines under `src/lucca/` | **[VERIFIED]** filesystem count |
| Test base | 94 test files, 648 test functions under `tests/` | **[VERIFIED]** AST count; [DOCUMENTED] 649 non-HW passing per `docs/audit/findings/V1_RELEASE_AUDIT.md` |
| Native tool registry | 19 tools, `MAX_REGISTRY_TOOLS = 19` (raised 18→19 by WO-17 `calc_math`) | **[VERIFIED]** `src/lucca/core/capabilities.py:33` |
| LISP skill library | 15 shipped MicroScheme skills; 12 model-callable (`expose_as_tool=True`), 3 reactive-only | **[VERIFIED]** `config/skills/*/meta_info.json` |
| Grounded `memory_commit` | Live since WO-9 A2 (ADR-010); commits `USER_DERIVED` facts grounded in the current turn's signed `USER_EXPLICIT` transcript; refuses model-authored content by design | **[VERIFIED]** `src/lucca/core/orchestrator.py:2813`, 21 tests in `tests/test_grounded_memory_commit.py` |
| Epistemic cascade | 8 substrates, Belnap FOUR bilattice, honest abstention (⊥) | **[DOCUMENTED]** `D-CASC-01`; `src/lucca/core/cascade.py` |
| Conformal routing abstention | Split-conformal guard fitted from DB history; abstention precision 96.08%, Wilson LB 0.8541 at N=100 | **[DOCUMENTED]** `V1_RELEASE_AUDIT.md`, `tests/test_c1_abstention_acceptance.py` |
| Rule induction | E-graph anti-unification (first-order, Plotkin LGG + Stitch compression metric), Z3 SMT verification, QUARANTINE-only registration, 5-cluster/0-error/operator promotion | **[DOCUMENTED]** `D-REAS-06/07/08`; **0 production rows** (synthetic fixtures only) |
| Affect | 3D PAD leaky-integrator ODE, Lyapunov gain clipping, Schmitt-trigger stance quantization, epistemic quarantine invariant (0.0 evidential weight, test-enforced) | **[DOCUMENTED]** `D-AFF-01`, `tests/test_affect_quarantine.py` |
| Sandbox | Docker CE in WSL2, `use_direct_fallback = False`, Pydantic arg schemas, risk classes, taint tracking, shell ban | **[DOCUMENTED]** `D-AUD-13`, `D-SEC-04`; egress wiring **unverified this session** (see §1.4) |
| Autobiographical memory | `ASSISTANT_UTTERANCE`/`ASSISTANT_BELIEF` (memory-eligible, non-grounding), `ASSISTANT_ACTION` receipts, `COHERENCE_BREACH` (grounding-eligible negative evidence), evidence-gated belief revision with 5-flag review queue | **[DOCUMENTED]** `D-MEM-04`, WO-12 closing audit |
| Voice pipeline | PTT, Faster-Whisper ASR every turn, Kokoro TTS, streaming output supervisor with physical WASAPI abort (20–50 ms), barge-in contract | **[DOCUMENTED]** ADR-0009, `D-SUP-01` |

### 1.2 What the External Review Established

A skeptical frontier-model reviewer examined the project across several rounds (docs + live web search, never hands-on). The exchange converged on:

**Conceded by the reviewer:**
- Among deployed local companions (Dunoon Daemon, Local AI Companion, Aura, Operit, and by extension Open-LLM-VTuber/AIRI/Neuro/Amica), none advertises provenance-typed memory, formal rule verification, a non-grounding class for the agent's own speech, or a quarantine→promotion skill lifecycle. Lucca is "the only one that treats trustworthiness as an architectural property rather than a persona feature."
- After correction, the raw execution surface (Docker-backed arbitrary Python) is comparable to Operit's embedded Ubuntu, not smaller. The differentiator is governance of that surface, not its size.
- No system was found combining all of: Belnap-fused abstention cascade, verified rule induction with human promotion, receipt-backed autobiographical memory with a non-grounding class, affect dynamics quarantined from evidence, and streaming speech supervision.

**Legitimate criticisms (confirmed this session):**
- **Version drift**: `pyproject.toml` says `0.2.0`; docs say v1.0.0/v2.0.0. **[VERIFIED]**
- **Tool-count drift**: WO-17 raised the cap to 19; `docs/README.md:86`, `docs/specs/STUDIO_CAPABILITY_ROADMAP.md`, `V1_RELEASE_AUDIT.md:51`, and two lines of the user guide still say 18. **[VERIFIED]** — and `tests/test_static_gates.py` does not cross-check doc-claimed counts against the registry constant. Gap in the static gates.
- **Orchestrator size**: `src/lucca/core/orchestrator.py` is 3,213 lines, the largest file in the tree. Real debt. **[VERIFIED]**
- **Evidence base is internal**: all validation is self-authored; the induction loop has zero production rows.

**Stale criticisms (resolved in Lucca's favor):**
- "`memory_commit` always refuses" — pre-WO-9 information. The grounded path is implemented and tested (§1.1). **[VERIFIED]**
- "Five whitelisted apps and a Docker sandbox" — described only `launch_app`. Actual surface: 19 tools + 12 model-callable skills. **[VERIFIED]**

### 1.3 Competitive Position by Field

| Field | Representatives | Lucca's position |
|---|---|---|
| Local companions | Dunoon, Aura, Local AI Companion, Open-LLM-VTuber, AIRI, Amica | **Category leader on trust architecture.** They optimize persona/voice/avatar; none has provenance, sandboxing, verified rules, or auditable self-reports. Gap is demonstrable, not claimed — pending the head-to-head study (§2.2). |
| Agent frameworks | LangGraph, CrewAI, AutoGen | **Not a competitor — a potential dependency.** They have ecosystem breadth; Lucca has governance they don't attempt. The extracted provenance library (§2.2 item 3) is the vector. |
| Memory infrastructure | Letta, Mem0, Graphiti | **The trust layer they lack.** They store what the LLM extracts; Lucca gates it. Position: reference implementation for auditable memory. |
| Research systems | VASO, ANNEAL, MEMIR, Gubernaut | **Credible peer with one unique asset** (signed breach/receipt dataset). They have papers; Lucca has a running integrated system. |
| Frontier assistants | Claude, GPT, Gemini | **Not a rival.** Loses on capability breadth permanently at 12B scale; wins on exactly one axis — every claim locally checkable with receipts. An existence proof for a different trade-off set. |

### 1.4 Known Debt & Open Risks (honest register)

1. **Doc/code drift** (version string, tool count) — one-commit fixes plus a static-gate test asserting docs cite live constants.
2. **Orchestrator decomposition** — 3,213-line god-object; schedule as a work order.
3. **Egress verification** — an archived audit (`docs/archive/2026-09_raw_findings/sbx.md`) found `sandbox/egress.py` had no live caller at that time. Must be re-verified before "blocks RFC1918/host gateway" appears in any external claim.
4. **Zero production induction rows** — resolves only through dogfooding volume.
5. **Single-user, Windows-only, PTT-only, 12B ceiling** — structural limits, correctly deferred in `docs/V2_BACKLOG.md`.

---

## Part 2 — Where Project Lucca Can Go

### 2.1 The Strategic Frame

The review exchange and the Nia literature pass converge on one structural observation:

> **Mechanisms get scooped; integrations survive.** Every individual technique in Lucca has a near-neighbor in the 2026 literature. No found system integrates them under one invariant set — and the receipt infrastructure is the asset none of the near-neighbors can easily replicate, because it must be architected in from the start, not bolted on.

The field is converging on Lucca's territory at roughly one near-neighbor paper per month (Gubernaut, July 2026; Honest Lying, May 2026; Aegis, current). The window to be *first to document* the integration is open now and visibly closing.

### 2.2 Near-Term: Manufacturing External Evidence (weeks, not months)

Ordered by cost-to-credibility ratio:

1. **Head-to-head comparison study.** 10–15 representative requests ("what did you do last session", "remember my sister is Maya", fetch-then-write) run against Lucca, Operit/Aura, and a frontier assistant, with receipts checked. Lucca's advantage is verifiability; the study is designed so the advantage appears as measured fact. Publish transcript pairs.
2. **One external benchmark.** BFCL for tool-calling — the architecture (frozen ≤19-tool prefix + category manifest) was designed against BFCL's known failure mode (`docs/research/studio_roadmap_r2/Q4_small_model_tool_use.md`). A respectable 12B local score is both validation and a citable design result.
3. **Extract the provenance library.** `src/lucca/memory/` (gate, signers, bi-temporal store) as a standalone package with the hallucination-write benchmark as its demo. Already flagged in `docs/archive/2026-09-17_pre_phase4_audit/17_project_summary_and_positioning.md` as "a plausible standalone artefact." Adoption is the external validation that cannot be argued with.
4. **Dogfood.** Daily use generates production induction rows and decision-log volume — the literal trigger conditions for three v2 backlog items.
5. **Related-work table + short write-up.** VASO, ANNEAL, MEMIR, MemLineage, Gubernaut vs. the Lucca design. Posted where agent-security and local-model communities read.

### 2.3 Mid-Term: Novelty Candidates — Nia-Verified Scorecard

Eight candidate directions were generated from pairwise products of existing subsystems and checked against live literature (Nia quick search, 2026-09-25). Scorecard:

| # | Candidate | Verdict | Notes |
|---|---|---|---|
| 1 | Affect as risk-policy modulator (affect → confirmation thresholds/conformal α, truth channel provably closed) | **SCOOPED (general concept)** | Gubernaut (arXiv:2607.24339) — deterministic homeostatic controller for affect-regulated LLM agents; Aegis (Zenodo) — homeostatic zero-trust agent governance. **[SEARCHED]** |
| 2 | Honesty homeostat (COHERENCE_BREACH → affect → verification rigor → fewer breaches; Lyapunov argument over confabulation rate) | **DIFFERENTIABLE** | Gubernaut must be read first. If it regulates generic behavior rather than *receipt-verified* honesty, Lucca's edge is the receipt linkage Gubernaut cannot replicate without a provenance stack. **[SEARCHED]** |
| 3 | Conformal prediction over Belnap states (finite-sample guarantees on abstention correctness, not just routing) | **SURVIVES** | Search returned only pure bilattice/epistemic-logic papers (Arieli/Ginsberg FOUR lineage). No conformal × four-valued-logic work found. **Strongest novelty candidate.** **[SEARCHED]** |
| 4 | Autobiographical schema induction (e-graph anti-unification over memory contents, not just execution traces) | **UNCHECKED** | DreamCoder-over-a-life framing; second data source for the induction loop while production rows accumulate. |
| 5 | Skill provenance lineage (promoted rules cryptographically linked to the signed turns that induced them) | **UNCHECKED** | MemLineage does this for memory; doing it for *learned behavior* is the open claim. |
| 6 | Taint-aware evidential discounting (taint flags → Dempster-Shafer discount in Belnap fusion) | **UNCHECKED** | Both halves documented in-repo; the wiring is the contribution. |
| 7 | Epistemic prosody (Kokoro prosody encodes calibrated confidence class) | **HALF EXISTS** | Uncertainty prosody is established in speech synthesis (Szekely et al., Interspeech 2017). Open claim: prosody driven by a *verified* epistemic state (Belnap/conformal) rather than text-inferred uncertainty. **[SEARCHED]** |
| 8 | Verifiable inter-agent testimony (signed provenance envelopes as A2A/MCP payload; eligibility semantics applied to sender claims) | **UNCHECKED** | A2A provenance is self-asserted; Lucca's would be verifiable. Serialization exercise on existing envelopes. |

**Process note:** candidates 4–6, 8 require a full T0 citation-audit pass (the `docs/research/studio_roadmap_r2/` methodology) before any investment or public claim.

### 2.4 The v2 Backlog as Research Program

`docs/V2_BACKLOG.md` items, re-read as research opportunities rather than feature debt:

- **§1.5 C1b (Bonsai slot-2 Reflect)** — a *publishable replication* of XConf's Recall-vs-Reflect ablation on ≥100 of Lucca's own graded episodes (McNemar, p < 0.05). Replications of fresh results are scarce and valued; the trigger is already written.
- **§1.3 NLI validator on NPU** — a MiniCheck-class cross-encoder checking every memory commit in ≤30 ms on Intel NPU would be the first edge-deployed neural fact-checker in a consumer companion.
- **§1.1 Proactive meta-cognition** — the actual frontier (background reflection under a provenance regime). Correctly gated behind telemetry; do not pull forward.
- **§1.2 Pathway formation** — gated behind ≥10,000 labeled turns; dogfooding is the only path.

### 2.5 The Breach Dataset — Lucca's Unique Asset

`COHERENCE_BREACH` records (a narrated action with no receipt, signed by `CoherenceBreachSigner`, grounding-eligible as verified negative evidence) constitute a dataset no other system produces: cryptographically signed, timestamped records of an agent's own confabulations, each linked to the receipt that disproves it. The literature has hallucination-*detection* (MARCH, ACL 2026) and confabulation-*studies* (Honest Lying, arXiv:2605.29463) **[SEARCHED]**, but no signed breach/receipt paired dataset from a running system. Extensions:

- Feed breach/triple pairs into the existing contrastive shadow pipeline (ModularRSI-style) to induce honesty-preserving refinements — closing the loop from *auditable* to *self-correcting*.
- Publish the schema and (sanitized) corpus as a benchmark artifact alongside the provenance library.

### 2.6 Recommended Sequencing

| Phase | Content | Exit criterion |
|---|---|---|
| **P0 (this week)** | Fix version string; ratify 19-tool count across docs; add static-gate test for doc/citation drift; verify egress wiring live | `pytest tests/test_static_gates.py` green incl. new drift gate |
| **P1 (weeks 1–3)** | Head-to-head study; BFCL run; T0 audit of candidates #3 and #2-differentiated | Published transcript pairs; BFCL score; audit verdicts |
| **P2 (months 1–2)** | Extract provenance library + hallucination-write demo; related-work write-up; dogfooding regime begins | Package published; write-up posted; first production induction rows |
| **P3 (months 2–4)** | C1b replication (if trigger met); NLI-on-NPU spike; candidate #3 (conformal×Belnap) formal write-up if T0-clean | Replication result; ≤30 ms NPU latency measured; preprint |
| **P4 (v2.0 planning)** | Candidates #4–6, #8 through full T0 audit; breach-corpus publication; backlog triggers reviewed against telemetry | v2.0 scope ratified by ADR |

### 2.7 The Honest Ceiling

Even fully executed, this trajectory does not make Lucca "the best AI." It makes Lucca the **most verifiable personal AI in existence**: a system whose honesty is architecture rather than marketing, with external evidence, an adoptable trust layer, a published replication, a self-improvement signal no competitor possesses, and a research agenda generated by pairwise products of subsystems already proven in isolation. The durable moat is not any mechanism — it is the combinatorial space of provable interactions that only exists because the v1.0 boundaries were drawn cleanly.

---

## Appendix A — Claim Verification Log (this session)

| Claim | Method | Result |
|---|---|---|
| `MAX_REGISTRY_TOOLS = 19` | Read `src/lucca/core/capabilities.py:33` | Confirmed; comment documents 16→18→19 history |
| 15 skills, 12 exposed | Parsed `config/skills/*/meta_info.json` | Confirmed; 3 reactive-only (`correction-ack`, `plan-decompose`, `time-greeting`) |
| Grounded `memory_commit` live | Read `orchestrator.py:2813`, counted tests | Confirmed; 21 tests incl. stale-transcript and invalid-predicate refusals |
| Orchestrator 3,213 lines | Line count | Confirmed; largest file in tree |
| 648 test functions / 94 files | AST count of `tests/test_*.py` | Confirmed |
| Docs say 18 tools in ≥4 places | Regex over `docs/` | Confirmed (README, roadmap, audit, user guide ×2) |
| Conformal × Belnap novelty | Nia quick search | No counterexample found |
| Affect-homeostat novelty | Nia quick search | SCOOPED: Gubernaut (2607.24339), Aegis |
| Breach-learning novelty | Nia quick search | Crowded (MARCH, Honest Lying); differentiable on signed-receipt artifact |
| Epistemic prosody novelty | Nia quick search | Half exists (Szekely 2017); calibrated-grounding variant open |
