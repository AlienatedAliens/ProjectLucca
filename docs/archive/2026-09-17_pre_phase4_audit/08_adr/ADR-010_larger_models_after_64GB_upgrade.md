# ADR-010 — Larger / MoE models after the 64 GB system-RAM upgrade (incl. predictive expert-paging runtimes)

**Status:** Proposed (not accepted). Evaluate as **Phase 0.6** once 64 GB is installed. Does not change Phases 1–3.
**Context owner:** user upgrading MSI Vector 16 HX AI from 16 GB to 64 GB (2 × 32 GB DDR5-5600 SO-DIMM).

## 1. What 64 GB changes — and what it does not

| Constraint | 16 GB | 64 GB |
|---|---|---|
| Host RAM pressure (Windows + 4 Lucca processes + WSL2 clamp) | ≈ 12.5 GB of 16 — tight, thrash risk | trivial; WSL2 clamp can rise to 8–12 GB; Chromium-by-default becomes affordable |
| Models resident in RAM (Whisper, Kokoro, embeddings, compile caches) | budgeted to the MB | irrelevant |
| **VRAM** | 16 GB | **still 16 GB** |
| **Per-token weight bandwidth** | GPU ≈ 960 GB/s (VRAM) | GPU ≈ 960 GB/s (VRAM); **CPU DDR5-5600 dual-channel ≈ 90 GB/s theoretical, ~55–65 GB/s achieved** |

The second row is the point: system RAM is where you *keep* weights cheaply; VRAM is where you *run* them fast. Any bytes fetched from system RAM on every token are ~15× slower than the same bytes from VRAM. Lucca's latency budget (spec 10) tolerates roughly 60+ tok/s decode and ≤ 200 ms TTFT; that puts a hard ceiling on how much per-token weight traffic can come from DDR5.

## 2. The three model shapes, honestly

### A. Dense model larger than 8B (e.g. 14B–32B)
Q4 of a 14B ≈ 8.5 GB → fits VRAM alongside encoder/KV; 32B Q4 ≈ 19 GB → does **not** fit; partial CPU offload makes decode bandwidth-bound (~10–20 tok/s). **Verdict:** 14B-class dense fits and is a real quality step; 32B dense is out for the live path.

### B. MoE with experts offloaded to CPU RAM ("keep active path on GPU")
For a model with *A* active parameters per token, each token fetches ≈ `A × bytes/param` from wherever the experts live. Example Qwen3-30B-A3B at Q4: ~3 B active → ~1.7 GB per token from DDR5 → ceiling ≈ 30–35 tok/s **before** GPU work — marginal against the budget, and worse under thermal load. Bigger MoEs (e.g. ~120 B-total / ~5 B-active in 4-bit ≈ 60 GB) do not fit in 64 GB beside Windows and Lucca at all. **Verdict:** CPU-offloaded experts buy *capacity you cannot use in the live voice path*. Useful for the offline brain (§4), not for turns.

### C. MoE small enough to sit **entirely in VRAM**
This is the shape that actually helps live latency: total quantised weights ≤ ~12–13 GB (leaving KV + encoder + CUDA context), few billion active → decode speed of a small model with quality of a much larger one. Candidates to benchmark (sizes approximate, verify on download):

| Model | Total / active | 4-bit-class size | Fits 16 GB VRAM w/ 8 k ctx? | Notes |
|---|---|---|---|---|
| `gpt-oss-20b` (MXFP4) | ~21 B / ~3.6 B | ≈ 12 GB | yes | strong tool use/reasoning; text-only |
| `Qwen3-30B-A3B` | 30 B / 3 B | Q4 ≈ 18 GB (no); IQ3/UD-Q3 ≈ 13 GB (tight) | only at ~3-bit | quality loss at 3-bit must be measured |
| 14B dense (e.g. `Qwen3-14B`, `Phi-4`) Q4 | 14 B / 14 B | ≈ 8.5–9 GB | yes | slower decode (~40–50 tok/s) but simplest |

**None of these can hear.** Ultravox exists for Llama-3.1-8B (and 70B/1B/Gemma/Qwen variants), not for these. Switching the live brain to any of them means running Lucca in **transcript mode** (ADR-001 fallback D): Whisper on the NPU first, then the text model. That adds ~100–200 ms of serial ASR to every turn — partially or fully offset if the new model's TTFT and decode are faster than Ultravox-8B Q6. It also *removes* the audio-native benefits (tone perception feeding affect, §ADR-009).

### D. Predictive expert paging (e.g. "FreeToken"-style runtimes) — VRAM-resident hot set, RAM spillover, per-request prefetch

**Status of knowledge:** the user reports a runtime ("FreeToken") that profiles the machine, loads as much of a MoE as fits in VRAM, spills the rest to system RAM, and *predictively swaps experts* into VRAM per request. The reviewer has **not verified** this tool (name, licence, API surface, benchmarks). Treat every claim about it as `UNKNOWN` until the research checklist in §7 is done. The analysis below is about what any such design can and cannot do on this laptop; it holds regardless of vendor.

**Why it is smarter than plain CPU offload.** With expert paging, a miss costs a **PCIe copy** of that expert into VRAM (then GPU compute at full speed) instead of CPU compute from DDR5. Expert routing has strong locality within a conversation, so a well-managed cache can serve most activations from VRAM. This genuinely beats option B when the *spill is small relative to the hot set*.

**The bounds it cannot escape (numbers are order-of-magnitude, to be measured):**

| Quantity | Value on this laptop |
|---|---|
| PCIe link, laptop RTX 5080 (Gen4/Gen5 ×8 typical) | ~25–50 GB/s achieved |
| Expert size, 30B-A3B class at 4-bit (128 experts × 48 layers) | ≈ 2.5 MB each; ≈ 1 GB of expert weights *touched per token* |
| Expert size, ~120B/5B-active class at 4-bit | ≈ 60 GB total; ≈ 2.5 GB touched per token; spill ≈ 48 GB |

- **Decode:** cost per token ≈ (miss rate × bytes touched) / PCIe bandwidth + GPU time. For 30B-A3B with ~2–5 GB spilled, a 15–30 % miss rate → ~150–300 MB/token → +5–10 ms/token → **plausibly 35–60 tok/s** — inside the budget *if* prefetch overlaps compute. For a 120B-class model with 48 GB spilled, miss rates are high, PCIe dominates → **single-digit to low-teens tok/s** regardless of prediction quality. Prediction cannot beat the fact that most of the model is not in VRAM.
- **Prefill (TTFT) is the killer.** A 600–900-token prompt (spec 10 §4) activates a large fraction of *all* experts in every layer. Whatever is spilled must cross PCIe **once per request**, during the stage where Lucca's budget is tightest (S2 ≤ 200 ms median). 3 GB spilled ≈ +60–120 ms TTFT; 20 GB ≈ +0.5–1 s. "Per-request predictive swap" is precisely a prefill-time cost. Any accepted configuration must show `t_llm_sent → t_llm_first_token` ≤ 300 ms p95 with the *real* Lucca prompt, not a short benchmark prompt.
- **Thermals and contention:** PCIe traffic + GPU compute + Whisper on NPU + Kokoro simultaneously; measure under the soak test, not in isolation.
- **Still cannot hear.** Same transcript-mode consequence as A–C.

**Integration risks specific to a third-party runtime (must be answered before adoption):**
1. Does it expose an OpenAI-compatible `/v1/chat/completions` with **streaming, tool calls, grammar-constrained output, and per-request abort**? Lucca's `SpeechLLMPort` needs all four (ADR-001 spike S5–S8).
2. Is it open source, offline, telemetry-free, and bindable to `127.0.0.1` only? (spec 12 TM-17; local-first invariant.)
3. Does it coexist with `llama-server` holding Ultravox in VRAM? Almost certainly **not** — VRAM is the contested resource. Adopting it for the live path means replacing llama-server, not adding to it.
4. Windows-native? (The NPU pipeline requires the host to stay Windows; a Linux-only runtime would push inference back into WSL2 — the exact failure mode ADR-001 removed.)
5. Does its profiler make decisions at start-up only, or continuously? Start-up-only profiling can be fooled by Lucca's own memory footprint changing after boot.

**Where it plausibly fits:** (i) a **30B-A3B-class MoE in transcript mode for the live brain**, if the §3 rule passes with the real prompt; (ii) a **much larger MoE as the reflective brain** (§4), where prefill seconds and 10 tok/s are perfectly acceptable and its paging makes a 60 GB model usable on this machine at all. (ii) is the more valuable and lower-risk fit.

## 3. Decision rule (what would make the switch worth it)

Switch the live brain **only if all** hold on the real laptop:

1. Model fits entirely in VRAM with `-c 8192` and steady-state ≤ 9.5 GB VRAM after 20 turns (same gate as ADR-001).
2. Transcript-mode end-to-end latency (spec 10 §5 harness) median ≤ 600 ms, p95 ≤ 800 ms — i.e. the new model must *earn back* the ASR serialisation.
3. Tool-call validity on the 20-clip fixture ≥ Ultravox's measured number, and the 40-item reasoning/instruction fixture (to be created) scores at least +15 % over Ultravox-8B on a blind pairwise judge or exact-match tasks.
4. Regression suites for promoted rules still pass (rules are model-independent, but reflection prompts are not).

If (2) fails but (3) passes strongly, the model is a candidate for §4 instead.

## 4. The genuinely good use of 64 GB: a second, slower brain for reflection

Lucca already separates the **live** path (latency-critical) from **reflection/extraction** (idle-time, latency-irrelevant). With 64 GB you can keep a much larger text model *memory-mapped in RAM* and bring it up only when idle:

- Live brain: Ultravox-8B Q6 in VRAM (unchanged).
- Reflective brain: e.g. a 30B–32B dense Q4 or a large MoE with CPU-offloaded experts, run at 5–20 tok/s during idle reflection, extraction grounding review, and rule proposal. Quality of proposed rules and extracted facts goes up; nothing in the voice path slows down.
- Mechanics: second `llama-server` instance on another port, started by the supervisor when `idle ≥ 60 s` and stopped on `ptt.pressed` (it must release VRAM within ~1 s, so keep its GPU layers at 0–8 and let it live in RAM; or run it CPU-only). Reflection already aborts on PTT (spec 05 §10).
- Provenance is unaffected: the reflective brain's output is still `LLM_NARRATION` → rules go to quarantine, facts need grounding.

This is the closest analogue to the "wake/sleep" split in DreamCoder and the reflection tier in Generative Agents (doc 12 §2.5–2.6), and it is the recommendation.

## 5. What to do now

- Keep ADR-001 as-is for Phases 1–3.
- After the upgrade: raise `.wslconfig` `memory` to 8192 MB (sandbox headroom, Chromium allowed by default), re-baseline the RAM table in spec 11 §4.
- Phase 0.6 spike (1 day): benchmark `gpt-oss-20b` and one 14B dense in transcript mode against the §3 rule; benchmark one 30B-class model CPU/RAM-resident for the reflective role (tok/s, load time, RSS).
- Accept or reject this ADR on measured numbers; if accepted for §4 only, add "reflective brain" to spec 05 §10 and spec 11 config (`[llm.reflective] enabled, model, gpu_layers, port`).

## 6. Alternatives considered

| Option | Why not (for the live path) |
|---|---|
| Ultravox-70B with CPU-offloaded experts | Dense, not MoE; 70B Q4 ≈ 40 GB streamed per token → single-digit tok/s. Reflective-brain candidate only. |
| Two GPUs / eGPU | Laptop; no. |
| Cloud fallback for the big model | Violates local-first. |
| Speculative decoding (small draft + big target) | Target still needs its weights per accepted token; helps ~1.5–2×, not 15×. Revisit if a 14B target is adopted. |

## 7. Research checklist for a predictive expert-paging runtime ("FreeToken" or similar) — run before Phase 0.6

Hand to a web-capable researcher with the same rules as `RESEARCH_PROMPT_2026-09-17_engine_decision.md` (URL, date, version, confidence grade per answer):

1. Exact project name, repository, licence, maintainer, last release date. Open source? Windows-native binary?
2. Serving API: OpenAI-compatible chat completions? Streaming SSE? Tool/function-call parsing for Llama-3/Qwen/gpt-oss formats? Grammar/JSON-schema constrained decoding? Per-request cancel/abort endpoint?
3. Telemetry/network behaviour: any outbound connections at runtime? Can it bind to `127.0.0.1` only?
4. Supported model formats (GGUF? safetensors? its own?) and which MoE families are tested (Qwen3-30B-A3B, gpt-oss-20b/120b, Mixtral, DeepSeek-V2/V3-lite, Llama-4-Scout).
5. Published benchmarks on **16 GB VRAM + 64 GB RAM consumer laptops**: tok/s decode **and TTFT for ≥ 600-token prompts** (not short prompts), per model, with miss-rate or PCIe-traffic figures if available.
6. Paging policy: profile-at-start-up vs continuous; how it behaves when VRAM shrinks after start (another process allocates); eviction/prefetch algorithm description.
7. Coexistence: can it share the GPU with another CUDA process holding ~9 GB (llama-server + Ultravox)? Does it support GPU-layer limits so it can run as the *reflective* brain without evicting the live brain?
8. Failure modes reported by users: stalls, VRAM fragmentation, driver resets on RTX 50-series, Windows-specific issues.
9. Comparable academic/OSS systems for cross-check: MoE-Infinity, PowerInfer/PowerInfer-2, Fiddler, ktransformers, MoE-Lightning, llama.cpp `--override-tensor` — how does its reported speed compare on similar hardware?

Acceptance for **live-brain** use = §3 rule with the real Lucca prompt, plus answers 2, 3, 7 satisfactory. Acceptance for **reflective-brain** use = answers 1–4 satisfactory and a measured ≥ 5 tok/s with ≤ 15 s cold start for the chosen large MoE.
