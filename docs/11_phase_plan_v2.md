# 11 — Phase Plan v2 (Phase 0 spikes, human gates, deferred scope)

Supersedes the phase table in `00_original_build_brief.md` where they differ. AGENTS.md invariant #3 stands: **do not start phase N+1 until phase N's bundle in [`10_testing_matrix_v2.md`](10_testing_matrix_v2.md) §4 is green** and the sign-off report exists. Human gates are the only place where "green" can wait on the calendar.

## Implementer protocol (for the weaker model)

1. Read [`13_decisions_log.md`](13_decisions_log.md) and [`07_contradiction_register.md`](07_contradiction_register.md) first. They win over docs 00–05.
2. For each task below, the deliverable is: code + Tier 0–2 tests green + (where marked) `hw` report file. **Never** edit a threshold in a spec to make a test pass; if a threshold is wrong, stop and write it in `docs/14_blockers.md` with the measured number.
3. If a fact is marked *estimate* anywhere, measure it and replace the estimate in the spec with the measurement + date.
4. Keep `pyproject.toml` and `uv.lock` in sync every commit.

## Phase 0 — Feasibility spikes (≤ 3 working days total, sequential)

| # | Spike | Exit condition | Fallback if fails |
|---|---|---|---|
| 0.1 | Environment: MSHybrid set, CUDA 12.8 runtime, WSL2 `.wslconfig` per register §C, Docker CE in Ubuntu, `sqlite-vec` loads, OpenVINO sees NPU | `lucca-admin env-check` all green | none — fix environment |
| 0.2 | `llama-server` + Ultravox Q6_K + mmproj (ADR-001 S1–S10) | S1–S3, S6, S8 pass; numbers in `phase0_llm.json` | transcript mode primary (D-01) |
| 0.3 | Whisper-large-v3-turbo on NPU via OpenVINO GenAI (T-ASR-01/02/05) | WER ≤ 8 %, 3 s clip ≤ 300 ms p95 | GPU → CPU distil-whisper |
| 0.4 | Kokoro device ladder (T-TTS-01/04) | first-chunk ≤ 180 ms on the selected device; device recorded | CPU is always acceptable |
| 0.5 | MiniLM on NPU static 128 (T-embed) | ≤ 15 ms/embedding | CPU ONNX |

Output: `docs/14_phase0_results.md` — a table of every *estimate* in the specs replaced by a measured value.

## Phase 1 — Ears + Voice (ADR-001/008, specs 01, 07, 08, 10)

Build: four processes + supervisor; PTT (right-Ctrl); capture/playback rings; VAD; ASR proxy; LLM client with demux; chunker; TTS with ladder; playback with jitter buffer; barge-in; trace; UI idle/listening/speaking states with RMS lip-flap.
**Acceptance (all from reports, both modes):** latency e2e median ≤ 600 / p95 ≤ 800 (audio mode) or ≤ 800 / 1 000 (transcript mode, reported as such); VRAM ≤ 9.5 GB, slope ≤ 20 MB/turn; TTS device reported with `EXECUTION_DEVICES`; 10 consecutive turns no crash/desync; barge-in gates; T-SOAK-01.
**Not weakened, made honest:** "Kokoro confirmed on NPU" → "TTS device measured and reported; NPU preferred".

## Phase 2 — Hands (ADR-003/004, spec 09, spec 12)

Build: file-sandbox and web-sandbox images + specs; `docker exec` RPC; `validate_rel_path`; tools table; launcher whitelist; confirm flow; egress script + positive-controlled verify; workspace lifecycle under `C:\ProjectLucca\workspace`; risk policy; forbidden sequences.
**Acceptance:** T-SBX-01..18 green; egress table with positive control in `sandbox_verify_*.md`; "summarise the files in my inbox" end-to-end (fixtures copied into workspace) speaks a summary; `open calculator` requires confirmation and launches; `hard_kill_and_recreate` leaves an empty workspace.

## Phase 3 — Memory (ADR-002/006, specs 03, 04)

Build: SQLite schema + migrations; signers; gate; extraction with grounding; hybrid retrieval; supersession; forget; backups; admin export.
**Acceptance:** T-PROV-01..12 (incl. end-to-end hallucination test with FakeLLM **and** with the real LLM in `hw`); retrieval benchmarks with numbers (Hit@1 ≥ 0.93, MRR delta ≥ 0.20, Recall@3 ≥ 0.90, P@1 ≥ 0.85); T-MEM-06/07 supersession & forget; T-MEM-14 positive-controlled discard; concurrency and crash tests.

## Phase 4 — Executive router + logging (spec 06 §1–4)

Build: heuristic router with word-boundary lexicon and fixtures; `DecisionRecord` persistence (SQLite + JSONL); labeling function; speculative dispatch + abort; counterfactual rule-fired flag.
**Mechanical acceptance:** T-RTR-01..05; every turn yields a decision row and, after next turn/60 s, a label.
**HUMAN GATE H-4:** ≥ 100 labelled decisions from live use or replay of recorded sessions (D-09). Implementer stops here and reports; a human (or a later session) runs the dogfooding protocol below.

## Phase 5 — Compiled reasoning (ADR-007, spec 05)

Build: MicroScheme v2 lexer/parser/evaluator; `RuleState`; static validation; shadow comparison; cluster distinctness; lifecycle; regression suite; reflection with GBNF grammar; promotion notice + pretty diff; "stop doing that".
**Mechanical acceptance:** T-LISP-*, T-RULE-*, T-REFL-*; a seeded synthetic session set (in `tests/fixtures/sessions/`) produces ≥ 1 promoted rule through the real pipeline with fakes.
**HUMAN GATE H-5:** ≥ 1 rule promoted from **real or replayed-real** usage; user hears the promotion notice and can retire it by voice.

## Phase 6 — Learned routing (spec 06 §5–8)

**Pre-condition (data floor):** ≥ 600 labelled decisions, ≥ 30 per class in test split, ≥ 20 sessions, ≥ 14 days. `lucca-admin router report` says "eligible". Until then Phase 6 is **blocked**, not "done with less data".
Build: feature pipeline (NPU encoder + hand features); LightGBM (CPU); temperature scaling; `ConformalGuard.fit`; chronological split; report with CIs; weekly recalibration job; router switch by config.
**Acceptance:** macro-F1 gain ≥ 0.05 with McNemar p < 0.05 or bootstrap CI excluding 0; ECE_5bin ≤ 0.08 (CI upper ≤ 0.12); coverage ≥ 1−α−1/√n; avg set size ≤ 1.30; T-RTR-06..11.
**HUMAN GATE H-6:** the data floor itself.

## Human-gate protocol (dogfooding) — `docs/15_dogfooding_protocol.md` to be filled by the human

- 4 sessions on different days, ≥ 25 varied utterances each, covering every intent ≥ 5 times, including ≥ 5 deliberate corrections ("no, not that") and ≥ 3 barge-ins.
- Sessions are **recorded** (`data\audio\`, traces, decisions) so they can be replayed deterministically (`lucca-admin replay <session_id>`) with `FakeClock/FakeRandom` — replay counts as "real" for H-4/H-5 (D-09).
- Fabricated or LLM-generated utterances **never** count.

## Deferred to Phase 7+ (explicitly out of scope for 1–6)

Vision/OCR/screenshot tools; iGPU overflow scheduling; phoneme-accurate visemes; Live2D/VRM avatar; embedding-based rule matching; coreference/entity merging across turns; Ultravox raw-audio multi-turn history; SQLCipher at rest; gVisor runtime; egress proxy container; non-English TTS/ASR; RVC/voice conversion; dual-ASR agreement; Qwen2-Audio/other speech LLMs behind `SpeechLLMPort`.

## Timeline reality check

Phases 0–3 are purely mechanical (an implementer can finish them without waiting on a human). Phases 4–6 contain calendar-bound gates; plan for **≥ 3 weeks of real usage** between the end of Phase 4 mechanics and Phase 6 eligibility. The implementer should build Phase 5 mechanics while H-4 data accumulates.
