# 13 — Decisions Log

Authoritative record of architectural decisions taken during the 2026-09-17 final review. Each entry states the decision, the evidence or preference behind it, what it supersedes in docs 00–05, and which ADR/spec elaborates it. **If any later document conflicts with this log, this log wins until the conflict is resolved here.**

Status vocabulary: `DECIDED` (user-approved), `EVIDENCE` (settled by verified research, user-approved), `DEFAULT` (reviewer default, user did not object), `SPIKE` (decided pending a measured Phase 0 result with a pre-declared fallback).

---

## D-01 Inference engine — `llama-server` natively on Windows, Ultravox Q6_K GGUF + `mmproj` — `EVIDENCE`

- **Decision:** Serve Ultravox v0.5 (Llama-3.1-8B backbone) with `llama-server` (llama.cpp, CUDA 12.8+ build for `sm_120`) running as a native Windows process. Weights: `ultravox-v0_5-llama-3_1-8b-Q6_K.gguf` (~6.6 GB) + `mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf` (~0.74 GB). All layers offloaded (`-ngl 99`).
- **Fallback (mandatory, pre-wired):** Cascade — same `llama-server`, same backbone quant, `--mmproj` omitted, Whisper transcript sent as text instead of audio. Switch is a config flag, not a rewrite.
- **Retired:** vLLM inside WSL2. vLLM cannot load Ultravox from GGUF (multimodal projector unsupported); FP8 alternative needs ~10.5 GB weights and ~2.5–3.8 GB host RAM inside the 4.5 GB WSL2 clamp, which collides with the sandbox.
- **Supersedes:** doc 00 §Architecture ("vLLM"), doc 03 Domain B launch script, doc 05 inference section, `pyproject.toml` vLLM dependency, all WSL2 RAM tables that include vLLM.
- **Evidence:** research report 1.1, 1.3, 1.4, 2.1 (grade A); review notes.
- **Phase 0 spike must measure:** TTFT for 3 s audio, decode tok/s, host RSS, VRAM at 8 k context, tool-call + grammar + audio concurrency, `/slots/{id}?action=release` abort latency.
- **Elaborated in:** ADR-001.

## D-02 Whisper ASR is a first-class critical-path component — `EVIDENCE`

- Ultravox emits no transcript (report 3.2). The router, `USER_EXPLICIT` provenance, and multi-turn history all need text. Therefore Whisper runs on **every** turn, on the Intel NPU via OpenVINO GenAI `WhisperPipeline` (report 4.2), in parallel with the LLM request (speculative dispatch).
- Model: `whisper-large-v3-turbo` stateful OpenVINO IR on NPU; CPU `distil-whisper-small` via faster-whisper as fallback if NPU compile fails.
- **Supersedes:** every place Whisper is described as a "background logging pass"; RAM tables that omit it.
- **Elaborated in:** spec 07 (audio), spec 10 (latency budgets), ADR-001 §consequences.

## D-03 Docker CE inside Ubuntu WSL2, not Docker Desktop — `EVIDENCE`

- Desktop runs containers in its own `docker-desktop` distro; `DOCKER-USER` iptables rules written in Ubuntu have no effect on it (report 7.4). Docker CE is required for the egress policy to be enforceable. WSL2 networking mode stays `nat` (mirrored breaks Docker bridge — report 7.3).
- **Supersedes:** doc 03 Domain C which is silent on the distinction.
- **Elaborated in:** spec 09, ADR-003.

## D-04 WSL2 hosts **only** the sandbox — `EVIDENCE` (consequence of D-01)

- `.wslconfig`: `memory=4608MB`, `processors=4`, `swap=0`, `autoMemoryReclaim=gradual`, `pageReporting=true` (was `false` — wrong, report 7.2), `networkingMode=nat`.
- With inference removed, the sandbox budget is: dockerd ~0.3 GB + kernel/base ~0.5 GB + sandbox container ≤ 1.5 GB → ~2.3 GB peak, leaving ~2.3 GB headroom. Chromium remains **off by default** (see D-12).
- **Elaborated in:** spec 09, spec 11 (RAM table).

## D-05 Laptop GPU mode — MSHybrid — `EVIDENCE` (verify)

- Set MSI Center to **MSHybrid** so the Windows desktop composites on the Intel iGPU and dGPU baseline VRAM ≈ 0. Environment check must assert `nvidia-smi` baseline used-VRAM < 300 MB before starting `llama-server`; otherwise warn that Discrete mode is stealing ~0.6–0.9 GB.
- **Elaborated in:** spec 11 (startup checks), `scripts/verify_environment.py` requirement.

## D-06 Memory store — SQLite (WAL) + FTS5 + `sqlite-vec` — `EVIDENCE`

- Replaces ChromaDB + `rank-bm25` + pickled networkx. One file, one transaction boundary for vectors, full-text, graph edges, provenance envelopes, decision log, rule store. `sqlite-vec` ships Windows py3.12 wheels (report 7.6). networkx is an in-memory *view* only. Chroma retained as a documented alternative adapter behind `VectorStorePort`.
- **Supersedes:** doc 05 memory section, doc 03 storage, `pyproject.toml` chromadb/rank-bm25.
- **Elaborated in:** ADR-002, spec 04.

## D-07 Kokoro TTS device — NPU as time-boxed Phase 1a spike, iGPU → CPU ladder — `SPIKE`

- NPU plugin requires static shapes (report 5.2); Kokoro has dynamic phoneme-length input and duration-dependent output. Spike: static-shape bucketing (64/128/256 phonemes) via OpenVINO reshape; exit condition = measured RTF and first-chunk latency for a 1.2 s clause. **Fallback ladder:** Intel Arc iGPU via OpenVINO GPU plugin (dynamic shapes OK) → CPU int8 ONNX Runtime. Acceptance criterion rewritten from "Kokoro confirmed on NPU" to "TTS device measured and reported; NPU preferred; ladder step permitted if NPU first-chunk > 180 ms or compile fails". Device is asserted via OpenVINO `EXECUTION_DEVICES`, never Task Manager.
- **Supersedes:** doc 00/01 hard "Kokoro on NPU" criterion; unsourced "35 ms/s" and "85 MB NPU SRAM" figures.
- **Elaborated in:** spec 07, phase plan 11.

## D-08 Runtime filesystem root `C:\ProjectLucca` — `DECIDED`

- **User requirement:** everything Lucca reads/writes lives under one install root; never touch OneDrive-redirected Windows user folders (`Downloads`, `Documents`, `Desktop`).
- **Layout (`LUCCA_HOME`, default `C:\ProjectLucca`):**

  ```
  C:\ProjectLucca\
    app\            installed package / venv / launcher scripts
    config\         lucca.toml, .env (secrets), tool_whitelist.toml, ptt.toml
    models\
      llm\          ultravox-*.gguf, mmproj-*.gguf, llama-3.1-8b text GGUF (cascade)
      asr\          whisper-large-v3-turbo OpenVINO IR (stateful), distil-whisper fallback
      tts\          kokoro ONNX / OpenVINO IR, voices
      embed\        MiniLM / bge-small OpenVINO IR
      router\       classifier artefacts (.pkl/.txt), conformal calibration .json
    data\
      memory.sqlite         (vectors, FTS, graph, provenance, decisions, rules)
      memory.sqlite-wal
      backups\              rotating snapshots (see spec 04)
      audio\                retained PTT clips (retention policy, spec 12)
    workspace\      the ONLY directory mounted into the sandbox as /workspace
    inbox\          user drops files here to hand them to Lucca (copied into workspace per task)
    logs\           structured JSONL logs + latency traces
    cache\          OpenVINO NPU compile cache, HF cache, llama.cpp KV snapshots
    tmp\
  ```

- **Sandbox mount:** `C:\ProjectLucca\workspace` → WSL2 `/mnt/c/ProjectLucca/workspace` (drvfs, mounted with `metadata,uid=1000,gid=1000,umask=022`) → bind-mounted into the container at `/workspace`. Known caveats documented in spec 09: drvfs is slower than ext4 (acceptable for text/small files), and ownership must be forced via mount options or the container user cannot write.
- **Ephemeral semantics:** the **host orchestrator wipes `workspace\`** at task close (and on `hard_kill_and_recreate`), which fixes the bind-mount-persists bug identified in the review. `inbox\` is never mounted; files are copied from `inbox\` into `workspace\` at task start when the user asks.
- **Dev vs runtime:** repository at `C:\Projects\ProjectLucca` (dev); `LUCCA_HOME` env var overrides the root (dev default `<repo>\.lucca_home\`). `LuccaConfig` must not hard-code any absolute path (review finding).
- **Supersedes:** doc 00 "downloads summary" example (rewritten to "summarise the files in my inbox"); doc 03 workspace mount path.
- **Elaborated in:** spec 11 (config), spec 09 (mount), spec 12 (retention).

## D-09 Human-usage gates satisfied by scripted replay of recorded real sessions — `DEFAULT`

- Phases 4–6 acceptance criteria that require "real logged decisions" / "real repeated pattern" are **HUMAN GATES**. Implementer deliverable = code + tests on synthetic fixtures + verified capture pipeline. "Real" data may be produced by (a) live dogfooding per the protocol in phase plan 11, or (b) deterministic replay of *previously recorded* live sessions (audio + trace). Fabricated/synthetic data never satisfies a human gate.
- **Elaborated in:** phase plan 11 §Human gates.

## D-10 Push-to-talk — right-Ctrl, hold-to-talk — `DEFAULT`

- Replaces `caps_lock` (toggles OS state; pynput hooks fail under elevated windows). Key is configurable in `config\ptt.toml`. 30 s hard cap with auto-release at 29.5 s (Whisper/Ultravox window). Implementation via Win32 low-level keyboard hook or `RegisterHotKey`, timestamped from the OS event.
- **Elaborated in:** spec 07.

## D-11 Provenance model — two-tier user provenance + content/structure split — `DEFAULT`

- `USER_EXPLICIT` = verbatim ASR transcript span (with audio hash + ASR confidence; low-confidence flagged). `USER_DERIVED` = LLM-extracted structure that must pass quote-grounding against a `source_entry_id`. `TOOL_VERIFIED` = structural facts of tool execution only. `TOOL_CONTENT_UNTRUSTED` = bodies/page text; memory-eligible only after confirmation. `LLM_NARRATION` rejected (invariant unchanged). HMAC replaced by per-provenance capability signers; host signs, container never holds a key.
- **Elaborated in:** ADR-006, spec 03.

## D-12 Sandbox web tool — HTTP fetch + readability by default; Chromium on-demand only — `DEFAULT`

- `httpx` + `trafilatura` (~50 MB) is the default fetch path; Playwright/Chromium is spawned only for JS-required pages, in a separate short-lived container, and torn down after. Split-container model (file-sandbox with no network; web-sandbox with no files) adopted — ADR-004.

## D-13 Rules are pure `State → Plan` functions — `DEFAULT`

- Rule condition = pure, gas-metered boolean. Rule action = data-only `Plan` (list of `ToolCall` descriptors). Orchestrator executes plans under the risk policy (READ auto; WRITE/LAUNCH confirm). Shadow mode = structural diff of planned vs executed. One canonical DSL replaces the four inconsistent examples in docs 01/02/05.
- **Elaborated in:** ADR-007, spec 05.

## D-14 Process topology — four host processes + NPU server isolation — `DEFAULT`

- `lucca-audio` (capture/playback/PTT), `lucca-core` (orchestrator, router, memory, rules, LLM client, sandbox client), `lucca-npu` (OpenVINO: Whisper, Kokoro, embeddings, classifier encoder), `lucca-ui` (PyQt6 avatar). ZeroMQ over localhost with Pydantic-validated, length-prefixed JSON; shared-memory ring buffer for PCM. `llama-server` is a fifth, external process.
- **Elaborated in:** ADR-008, spec 01.

## D-15 UI framework — PyQt6 — `DEFAULT`

- Transparent, click-through, always-on-top 2D sprite overlay; RMS-envelope 3-state lip flap in Phase 1. ADR-005.

## D-16 Scope deferrals — `DEFAULT`

- Vision API fallback, OCR/screenshot, phoneme-accurate visemes, embedding-based rule matching, Ultravox multi-turn raw-audio history → **Phase 7+**. Listed in phase plan 11 §Deferred.

---

## Open items still requiring a user answer (non-blocking; defaults applied)

| # | Question | Default applied |
|---|---|---|
| O-1 | Which Ultravox variant if v0.6 GGUFs exist for a stronger backbone? | v0.5 Llama-3.1-8B (verified GGUFs exist). |
| O-2 | Retain raw PTT audio clips on disk? For how long? | Retain 7 days in `data\audio\`, then delete; transcripts kept. Configurable. |
| O-3 | Voice confirmation phrase for WRITE/LAUNCH actions | "yes, do it" / "no" via Whisper; any other utterance = cancel. |
| O-4 | Should the cascade (D) be run as an automatic runtime fallback if `mmproj` load fails, or only as a manual config switch? | Automatic at startup with a spoken notice ("running in transcript mode"). |
