# Review Notes on `RESEARCH_REPORT_2026-09-17_engine_decision.md`

**Reviewer stance:** The report claims 36/36 `VERIFIED`, zero `UNKNOWN`. That is statistically implausible for questions like "measured RTF on a Core Ultra 9 275HX" and is treated here as **over-claiming**. Each answer was re-graded below on citation quality. Decision-critical facts survive; several supporting numbers are downgraded.

## Grading key

- **A** — specific primary source (PR number, model-card URL, docs page, issue number). Usable as-is.
- **B** — plausible and consistent with prior knowledge, but cited only to a repo root, `/issues`, `/discussions`, or "benchmark logs" with no identifier. Usable as a *planning estimate*; **must be re-verified by measurement or a real link before being written into an acceptance criterion**.
- **C** — cited to a source that cannot contain the claimed fact, or contains a factual error. Do not rely on it.

## Re-graded table

| ID | Grade | Note |
|---|---|---|
| 1.1 | A | PR #13623 — consistent with prior knowledge (Ultravox mtmd support, May 2025). Decision-critical. **Implementer: open the PR URL and confirm before Phase 0.** |
| 1.2 | A- | Discussion #13759 cited. Backbone list plausible (v0.6 added Gemma-3/Qwen variants). |
| 1.3 | A | `ggml-org/ultravox-v0_5-llama-3_1-8b-GGUF` with `mmproj` files — consistent with ggml-org's practice. Sizes plausible (Q6_K ≈ 6.6 GB; mmproj Q8_0 ≈ 743 MB, f16 ≈ 1.27 GB). Decision-critical. |
| 1.4 | A | PR #13714 (`input_audio` in `/v1/chat/completions`). Decision-critical. |
| 1.5 | B+ | Cited to server README (real file). Caveat "schemas must be supplied" is vague; test it. |
| 1.6 | B+ | Grammars README is real; concurrency of grammar + tools + audio in one request is an *inference*, not documented. **Test in Phase 0.** |
| 1.7 | A- | `/slots/{id}?action=release|erase` exists in server README; connection-drop cancellation is standard. |
| 1.8 | **B** | Cited to `/issues` root. "82–95 tok/s on RTX 5080 Laptop" is a plausible estimate (≈ 960 GB/s ÷ 6.6 GB ≈ 145 tok/s theoretical; 60 % efficiency ≈ 87) but **not a citation**. Treat as estimate; measure. CUDA 12.8+ requirement for sm_120 is correct. |
| 1.9 | **B** | Cited to `/discussions` root. 400–700 MB RSS with `-ngl 99` is plausible (mmap'd weights are not resident). Measure. |
| 2.1 | A | vLLM supported-models docs; Ultravox absent from GGUF list. Decision-critical, and consistent with prior analysis. |
| 2.2 | A- | Model card cited; "no AWQ/GPTQ Ultravox checkpoints exist" is a negative claim — likely true but unprovable from one URL. |
| 2.3 | **B** | `/issues` root. sm_120 kernel breakage is well-known; "cu128 wheels deprecated" and "requires CUDA 12.9+/13.0" are version-timeline claims that **may be stale or wrong** depending on when the implementer reads this. Irrelevant now that Option C is NO-GO for the independent GGUF reason. |
| 2.4 | B | Installation docs cited (real page), but the "wheels removed" claim is not something that page would state permanently. Same disposition as 2.3. |
| 2.5 | A | FP8 KV cache docs. Numbers match our own calculation (1.07 GB → 0.54 GB at 8k). |
| 2.6 | B | `/issues` root. Claim matches known behaviour (APC caches text prefix; multimodal blocks keyed by hash, re-sent audio ≠ cache hit). |
| 2.7 | A- | Multimodal docs; 30 s Whisper window is a model fact. `split_audio` naming unverified. |
| 2.8 | A | Structured-outputs docs. |
| 2.9 | B | `/issues` root; numbers consistent with prior analysis (2.5–3.8 GB RSS). |
| 2.10 | B+ | Performance docs page exists; 25–40 % figure matches prior estimate. |
| 3.1 | A | Model card. large-v3-turbo encoder ~637 M, projector ~38 M. |
| 3.2 | A | Repo README. **Confirms the central architectural finding: Ultravox emits no transcript → independent ASR mandatory.** |
| 3.3 | **B-** | "Fixie Benchmark" with repo-root URL and a 2024 date that cannot include an RTX 5080. 140–180 ms TTFT is plausible; treat as estimate. |
| 3.4 | **B-** | Blog URL plausible but unverified; "within ~3 % of text tool-calling" is a specific number with no locatable source. Do not put in acceptance criteria. |
| 3.5 | A | Model card / Llama licence. Corrects doc 02's "Apache 2.0" error. |
| 3.6 | B | `/issues` root; recommendation (text transcripts for history, audio for current turn only) matches our proposed strategy. |
| 4.1 | B+ | faster-whisper repo real; latency numbers for *this CPU* cannot be in that repo. WER figures (~2–3 % LibriSpeech clean) are published model facts. |
| 4.2 | A | OpenVINO GenAI guide; Whisper on NPU with stateful static-shape models — consistent with OpenVINO 2024.5+ notes. |
| 4.3 | B | RealtimeVoiceChat repo real; "350–480 ms" is the project's own claim on *its author's* hardware, not ours. Planning estimate only. |
| 5.1 | **B-** | Cited to `openvino_notebooks` root. No known official Kokoro-on-NPU notebook. The *constraint* (static bucketing required) is correct by 5.2; the *existence proof* is unverified. **Kokoro-on-NPU remains a Phase 1a spike, not a settled fact.** |
| 5.2 | A | NPU device docs: static shapes required. |
| 5.3 | **C** | "RTF 0.12–0.15 on Core Ultra 9 275HX" cited to `hexgrad/kokoro` "Benchmark Logs" — that repo has no per-CPU benchmark logs for this chip. Numbers are plausible extrapolations; **measure**. |
| 5.4 | A- | kokoro-onnx emits audio only; native `kokoro` exposes token/duration objects. RMS lip-sync recommendation stands. |
| "5.5" (= 6.1) | B | Mis-numbered. NPU latency 4–7 ms at seq 128 for MiniLM/bge-small is plausible; repo-root cite. |
| 6.2 | B | `/issues` root; ModernBERT-on-NPU immaturity is consistent with RoPE/unpadding concerns. Use MiniLM/DistilBERT. |
| 6.3 | A | Issue #23778 (and #21168) — TreeEnsemble unsupported. Confirms AGENTS.md invariant. |
| 7.1 | **B-** | MSI product page cannot state DWM VRAM usage. MUX/MSHybrid existence is right; "600–900 MB in discrete mode" is a typical-value estimate. **Action: set MSHybrid and verify dGPU baseline VRAM ≈ 0 with `nvidia-smi`.** |
| 7.2 | A | Microsoft `.wslconfig` docs. Confirms `pageReporting=false` must go. |
| 7.3 | B+ | Microsoft networking docs real; Docker-under-mirrored-mode issues are widely reported. Use `nat`. |
| 7.4 | A | Docker Desktop WSL docs. Confirms: **Docker CE inside Ubuntu is mandatory.** |
| 7.5 | A | NPU docs; no WSL2 passthrough. Confirms AGENTS.md invariant. |
| 7.6 | A | PyPI `sqlite-vec` wheel; loads via `sqlite_vec.load(conn)` with `enable_load_extension(True)`. **Caveat:** stock python.org Windows builds *do* ship with extension loading; some conda/embedded builds do not — verify at env-check. |
| 8.1–8.12, 8.14–8.18 | B | Star counts / versions / dates are snapshot values that will drift; licences and one-line descriptions are consistent with prior knowledge. Implementer re-checks before citing. |
| 8.13 | **C** | **Factual error:** HippoRAG is `OSU-NLP-Group/HippoRAG`, not `SylphAI-Inc`. This single error is why the report's blanket `VERIFIED` cannot be trusted without the re-grading above. |

## What survives for Decision 1

Decision-critical facts are all grade A and mutually consistent:

1. llama.cpp supports Ultravox audio (1.1) via server OpenAI API (1.4) with published Q6_K + mmproj GGUFs (1.3).
2. vLLM cannot load Ultravox from GGUF (2.1); FP8-on-WSL2 collides with the RAM clamp (our own arithmetic, corroborated by 2.9).
3. Ultravox emits no transcript (3.2) → Whisper ASR is mandatory in **every** option → the cascade's "transcript for free" advantage is neutralised (both options pay for Whisper), and Option B's only remaining cost vs D is a second audio encoder on the GPU (+~0.75 GB VRAM for mmproj Q8_0).
4. Whisper runs on the Intel NPU via OpenVINO GenAI (4.2).
5. Docker CE, not Desktop (7.4). NPU is host-only (7.5). `pageReporting=false` is wrong (7.2). sqlite-vec is available on Windows (7.6).

## Resulting recommendation

- **Option C (vLLM/WSL2): NO-GO.** Retire from the architecture. Remove vLLM from `pyproject.toml`, docs 03/05 launch scripts, and the WSL2 RAM budget.
- **Option B (llama-server on Windows, Ultravox Q6_K + mmproj): PRIMARY.** Matches the brief's model and quantization; frees WSL2 for the sandbox alone.
- **Option D (cascade, same `llama-server` with a text-only Llama-3.1-8B Q6_K GGUF): MANDATORY FALLBACK.** Because both B and D use the *same server binary, same backbone quant, same Whisper NPU pass, same Kokoro*, switching is a config change (`--mmproj` present or absent + whether the transcript or the audio is sent to the LLM). This collapses the "bake-off" to a **one-day Phase 0 spike** that measures B on the real machine and confirms D as a switch.
- **The bake-off between B and C is cancelled** (C is dead on the GGUF fact alone).

## Facts the implementer must still measure in Phase 0 (grade B/C items used in budgets)

| Quantity | Report's estimate | Where it feeds |
|---|---|---|
| llama-server decode tok/s, Ultravox Q6_K, RTX 5080 Laptop | 82–95 | latency budget stage "first token → first chunk" |
| llama-server TTFT for 3 s audio | 140–180 ms | stage "send → first token" |
| llama-server host RSS `-ngl 99` | 400–700 MB | host RAM table |
| Whisper-large-v3-turbo on NPU, 3 s clip, to final text | 140–180 ms | router critical path; ASR budget |
| Kokoro RTF CPU int8 / iGPU / NPU-bucketed | 0.12–0.15 / 0.05 / unknown | TTS fallback ladder gate |
| dGPU baseline VRAM in MSHybrid mode | ~0 MB | VRAM ceiling |
| MiniLM NPU latency seq 128 | 4–7 ms | embedding budget |
