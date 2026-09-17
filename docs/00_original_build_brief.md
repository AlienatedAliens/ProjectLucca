# Project Lucca — Local Desktop Companion Agent
## Design Document & Build Brief

---

## 0. Instructions for the Building Agent

You are implementing this system phase by phase, in the order given in Section 5. **Do not begin a phase until the previous phase's acceptance criteria (Section 6) are fully met and demonstrated with a passing test, not just "code written."** If a phase's acceptance criteria cannot be met after reasonable effort, stop and report why rather than silently weakening the criteria or skipping ahead. Flag any irreversible or destructive action (deleting data, overwriting a persistent memory volume, rebuilding core toolchain versions) before taking it. Where this document says "must," treat it as a hard requirement, not a suggestion.

---

## 1. Vision

A local-first, sandboxed desktop companion ("Lucca") that:
- Listens via push-to-talk, responds with natural TTS speech and a 2D sprite avatar
- Remembers facts and preferences persistently across restarts
- Executes a bounded set of desktop tools (file read/write, read-only web browsing, app launching) inside an isolated sandbox
- Develops reusable, inspectable domain-specific reasoning shortcuts over time (compiled LISP rules) rather than re-deriving the same reasoning from scratch every time
- Is modular: every sense and every brain component communicates through a defined interface (audio→text, text→typed decision, state→plan) so any one piece can be swapped or upgraded without breaking the rest

## 2. Explicit Non-Goals (this build)

- **No idle self-practice / self-play loop.** Deferred to a future phase once Phases 1-6 are stable and trusted in real use. Do not build scaffolding for this now.
- No Twitch/chat integration, no content moderation or safety-filter layer (single-user, local, unfiltered by design).
- No multi-user support.
- No cloud dependency for the core loop (vision API fallback is the one permitted exception, called only as an explicit tool).
- No attempt to exceed the hardware budget in Section 3 "just to see."

## 3. Hardware Target & Budget

**Host:** MSI Vector 16 HX AI (Core Ultra 9 275HX / Arrow Lake-HX, RTX 5080 16GB VRAM, 16GB system RAM)

| Compute engine | Real capability | Do NOT put here |
|---|---|---|
| dGPU (16GB VRAM) | Ultravox 8B Q6 (brain) — only occupant | TTS, memory, tree models |
| NPU (13 TOPS, dedicated INT8/FP16 MAC, no XMX needed) | Kokoro TTS, Whisper (logging pass), embedding generation, small encoder classifiers (quantized) | XGBoost/LightGBM or any tree-ensemble model — **OpenVINO does not support ONNX TreeEnsembleClassifier/ZipMap ops; this will fail to load, confirmed via open OpenVINO GitHub issues** |
| iGPU (Xe-LPG, 4 cores/64 EU, **DP4a only — no XMX matrix units**) | OCR/screen-vision, overflow if NPU queue is contended, general parallel compute | Do not assume it is "just a weaker GPU" — for AI inference specifically it is not more capable than the NPU |
| CPU (24 cores, 8P+16E) | Orchestrator, VAD, JSON tool-call dispatch, ChromaDB vector search (native), XGBoost/LightGBM inference, the LISP interpreter itself (symbolic, not neural — belongs here regardless of NPU/iGPU load) | Heavy model inference |

**Known compatibility risk:** RTX 5080 is Blackwell (compute capability sm_120), requiring CUDA 12.8+. Several ecosystem packages (llama-cpp-python prebuilt wheels, some TTS repos) are pinned to CUDA 12.4. Expect to rebuild `llama-cpp-python` from source against a newer CUDA/PyTorch pair early in Phase 1. This is expected friction, not a blocker.

**System RAM (16GB total, shared across NPU/iGPU/CPU and the host OS):** keep every NPU/iGPU-resident model small and quantized. Do not treat this as three separate 16GB pools — it is one pool with three engines drawing from it.

## 4. Architecture Overview

```
SENSES                          BRAIN                              VOICE
─────────────────────           ─────────────────────────          ─────────────────
Push-to-talk mic  ──┐            Ultravox 8B (LLM core, GPU) ──┐    Kokoro (NPU)
Whisper (NPU, log)  │            LISP reasoning engine (CPU)   │    RVC (optional, NPU/iGPU)
Silero VAD          ├──────────► Trained classifier             ├──►Resemble Enhance (optional)
OCR/screenshot(iGPU)│              (encoder: NPU, trees: CPU)   │    DSP polish layer (CPU)
Vision API (tool)  ─┘            Working memory (RAM)           │    Sprite/lip-sync driver (CPU)
                                  Long-term memory:              │
                                    ChromaDB (vector, disk)      │
                                    Knowledge graph (disk)       │
                                  Reflection loop                │
                                  Planner (LISP, STRIPS/HTN)    ─┘
                                  Executive/router

                    SANDBOX: Docker + WSL2, GPU-PV passthrough, one mounted
                    workspace folder, persistent memory volume kept SEPARATE
                    from the ephemeral/resettable workspace, non-root user,
                    blocked local-subnet egress.
```

## 5. Build Phases

| # | Phase | Depends on |
|---|---|---|
| 1 | Ears + Voice (Ultravox ↔ Kokoro round trip) | — |
| 2 | Tools + Sandbox | 1 |
| 3 | Three-tier memory (working / vector / graph) | 2 |
| 4 | Executive router — **hand-written heuristic**, not ML yet | 3 |
| 5 | Reflection loop + LISP compilation/gating | 3, 4 |
| 6 | Trained classifier, replacing the heuristic router | 5 |
| 7 (future, out of scope) | Idle self-practice loop | 5, 6 |

## 6. Module Specs & Acceptance Criteria

### Phase 1 — Ears + Voice
**Build:** Push-to-talk capture → Ultravox 8B Q6 via vLLM → Kokoro TTS (NPU, OpenVINO int8) → speaker output.
**Acceptance criteria:**
- [ ] End-to-end round trip (release hotkey → audio starts playing) measured and logged over 20 real utterances
- [ ] Median response latency reported honestly — target 300-600ms for the 8B model; **do not report a sub-200ms figure as if achieved unless independently measured**
- [ ] VRAM usage measured at idle and under load; must stay under ~8GB for Ultravox+KV cache, leaving headroom in the 16GB budget
- [ ] Kokoro confirmed running on NPU (not silently falling back to CPU/GPU) via device utilization check
- [ ] 10 consecutive turns with no crash, memory leak (VRAM climbing turn over turn), or audio desync

### Phase 2 — Tools + Sandbox
**Build:** Docker container in WSL2 with GPU-PV, file read/write tool (path-traversal protected, scoped to one workspace dir), read-only web fetch tool (Playwright, headless), app-launcher tool.
**Acceptance criteria:**
- [ ] Attempted path traversal (`../../etc/passwd`-style) is rejected by the file tool, tested explicitly
- [ ] Container cannot reach host filesystem outside the one mounted folder — verified by attempting and failing to read a host-only file
- [ ] Local-subnet egress blocked — verified by attempting and failing to reach a host LAN IP from inside the container
- [ ] Ephemeral workspace resets on container restart; a separate named volume persists across restarts — verified by writing to both, restarting, confirming one survived and one didn't

### Phase 3 — Memory
**Build:** Working memory (typed task-state object, in-process), ChromaDB (vector), lightweight knowledge graph (`networkx` acceptable), hybrid retrieval (embedding + keyword/TF-IDF).
**Acceptance criteria:**
- [ ] **Hallucination-write test (hard requirement):** feed the system a plausible-sounding but false statement generated by the LLM's own narration (not a tool result, not an explicit user statement) and confirm it is **rejected from long-term memory** — only tool-execution results and explicit user statements may be written
- [ ] Recall test: store 20 distinct facts, query with paraphrased (not exact-match) queries, measure retrieval precision/recall
- [ ] Hybrid retrieval demonstrably outperforms pure cosine similarity on at least one exact-term case (e.g. a specific error code or filename) in a side-by-side test
- [ ] Working memory correctly persists across a multi-step tool-use task and is discarded (not written to long-term memory) once the task closes

### Phase 4 — Executive Router (heuristic)
**Build:** Hand-written rule-based router deciding: direct-to-LLM / check-LISP-first / call-compiled-tool. All decisions logged as `[state, chosen_action, outcome]` tuples — this log is the training data for Phase 6.
**Acceptance criteria:**
- [ ] Every routing decision is logged with enough context to later compute whether it was correct
- [ ] At least 100 real logged decisions exist before proceeding to Phase 5

### Phase 5 — Reflection + LISP
**Build:** Periodic reflection synthesis (LLM proposes an insight from recent logs), LISP interpreter (Hy or a minimal Scheme), rule promotion gate, regression test harness, demotion path.
**Acceptance criteria:**
- [ ] **Promotion gate enforced:** a candidate rule is not compiled until it has succeeded on N ≥ 5 distinct real logged cases with zero failures — hardcode this check, do not allow single-success promotion
- [ ] **Regression suite enforced:** any new or modified rule must pass the accumulated regression suite of previously-validated cases before it supersedes or extends a parent rule
- [ ] **Demotion path tested:** manually inject evidence contradicting a promoted rule, confirm it gets flagged/demoted rather than silently continuing to fire
- [ ] **Reflection "apply rate" explicitly tracked and reported, not assumed.** Report the ratio of reflection-worker-runs to actually-applied-insights. If this ratio is nearly zero over a real usage period, treat it as a bug, not a quiet success (this is a documented real failure mode in comparable systems — a worker can run and do nothing while looking "done")
- [ ] At least one rule successfully promoted from a real (not synthetic) repeated interaction pattern, with a human-readable diff of what was compiled

### Phase 6 — Trained Classifier
**Build:** Encoder classifier (DistilBERT/ModernBERT, NPU) for semantic/text-heavy decisions; XGBoost/LightGBM (CPU) for structured/tabular decisions; calibration via Platt scaling or isotonic regression; optional conformal prediction wrapper.
**Acceptance criteria:**
- [ ] Trained only on real logged data from Phases 4-5 (no synthetic/invented training examples)
- [ ] Calibration verified quantitatively (Brier score or expected calibration error reported, not eyeballed)
- [ ] Classifier only replaces the Phase 4 heuristic router **after** beating the heuristic's accuracy on a held-out slice of the real logged data — report both numbers side by side
- [ ] Low-confidence predictions correctly fall back to the safe default (ask the user / escalate to full LLM reasoning) rather than acting — tested explicitly with a deliberately ambiguous input

## 7. Cross-Cutting Guardrails (apply throughout, not just at the end of a phase)

1. Never promote the LLM's own freeform narration text directly into long-term memory. Only tool results, explicit user statements, and LISP/classifier-verified facts qualify.
2. Never compile a LISP rule from a single success. The promotion gate in Phase 5 is non-negotiable.
3. Report latency and resource numbers as measured, not as targeted or estimated.
4. Any module should be replaceable by swapping its interface implementation (e.g., a different TTS engine, a different embedding model) without touching unrelated modules. If a change to one module requires touching three others, flag that as a design smell.

## 8. Known Risks (carry forward, don't re-litigate)

- Blackwell/CUDA version mismatch across the ecosystem (Section 3)
- iGPU has no matrix acceleration (DP4a only) — don't route tree models or heavy inference there
- OpenVINO cannot run tree-ensemble models at all, on any device
- Reflection can silently no-op while appearing to run (Phase 5 acceptance criteria exists specifically to catch this)
- The self-practice loop (Phase 7) has no clean ground-truth signal for "did this self-generated attempt actually succeed" — this is why it is deferred, not because it's unimportant
