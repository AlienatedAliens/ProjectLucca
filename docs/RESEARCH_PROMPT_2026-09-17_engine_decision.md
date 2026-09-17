# Research Prompt — Verify Facts Blocking Lucca's Inference-Engine Decision

> Paste everything below the line into a web-search-capable AI. Return its output to the architecture reviewer.

---

You are a technical researcher. I need **verified, cited, dated** answers to the questions below. For every answer:

- Cite the primary source (GitHub PR/issue/release notes, official docs, model card, or benchmark) with a URL.
- State the **date** of the source and the **software version** it applies to.
- Rate your confidence: `VERIFIED` (primary source found), `LIKELY` (secondary sources agree), `UNKNOWN` (could not find), `CONTRADICTED` (sources disagree — show both).
- Do **not** guess. If you cannot find it, say `UNKNOWN` and say what you searched.
- Prefer sources from 2025–2026. Flag anything older than 12 months.

## Context (do not re-research this)

Target machine: MSI Vector 16 HX AI laptop — Intel Core Ultra 9 275HX (Arrow Lake, 24 cores, integrated Intel NPU), NVIDIA RTX 5080 Laptop 16 GB VRAM (Blackwell, compute capability `sm_120`), 16 GB system RAM, Windows 11, WSL2 (Ubuntu) memory-clamped to 4.5 GB.

Goal: run **Ultravox** (fixie-ai, Llama-3.1-8B backbone + Whisper-large-v3-turbo encoder + projector; audio-in, text-out) locally with push-to-talk latency ≤ 600 ms to first audio, alongside Kokoro TTS and Whisper ASR on the Intel NPU via OpenVINO.

Two candidate serving stacks: **vLLM inside WSL2** vs **llama.cpp (`llama-server`) natively on Windows**. A third fallback is a cascade (Whisper → text-only Llama-3.1-8B → Kokoro).

---

## Section 1 — llama.cpp + Ultravox (decides Option B)

1.1 Does llama.cpp's multimodal layer (`libmtmd`, formerly `llava` examples) support **Ultravox** audio input? Find the PR/commit that added it, the date, and the first release tag that includes it.
1.2 Which Ultravox versions/variants are supported (v0.4, v0.5, v0.6; Llama-3.1-8B, Llama-3.2-1B, Llama-3.3-70B, Gemma, Qwen backbones)?
1.3 Are there **pre-converted GGUF files** for Ultravox on Hugging Face (e.g. by ggml-org, bartowski, unsloth, or others)? List repo names, quantization levels available (Q4_K_M, Q5_K_M, Q6_K, Q8_0), and file sizes. Is there a separate `mmproj` file for the audio encoder/projector, and what size/precision is it?
1.4 Does `llama-server` expose Ultravox audio input via its **OpenAI-compatible `/v1/chat/completions`** endpoint (`input_audio` content parts)? Or is audio only usable via `llama-mtmd-cli`? Cite docs.
1.5 Does `llama-server` support **streaming + tool/function calling** (Llama 3.1 JSON tool format) simultaneously with multimodal input? Any known issues?
1.6 Does `llama-server` support **GBNF grammar-constrained decoding** concurrently with tool calling and audio input?
1.7 Does llama.cpp support **aborting an in-flight generation** for a single request (needed for barge-in)? Via which API?
1.8 Any reported **benchmarks** of Ultravox or Llama-3.1-8B Q6_K on an RTX 5080 / RTX 5090 / RTX 5070 Ti (Blackwell) with llama.cpp CUDA: tokens/sec decode, prompt-processing speed. Is there a Blackwell-specific CUDA build requirement (CUDA 12.8+)?
1.9 What is the **host RAM** footprint of `llama-server` when all layers are offloaded to GPU (`-ngl 99`) for an 8B Q6_K model?

## Section 2 — vLLM + Ultravox (decides Option C)

2.1 Does vLLM support loading Ultravox from **GGUF**? Check vLLM's GGUF-supported-architectures list. Is `UltravoxModel` among them? Cite docs/issue.
2.2 Which quantizations does vLLM support for Ultravox in practice: BF16, FP8 (`--quantization fp8` dynamic), AWQ/GPTQ INT4? Are there **pre-quantized Ultravox checkpoints** on Hugging Face (FP8, AWQ, GPTQ, compressed-tensors)? List them.
2.3 Does vLLM's **FP8 path work on consumer Blackwell `sm_120`** (RTX 50-series)? Look for issues about FP8 / `cutlass` / `flashinfer` kernels on `sm_120` vs datacenter `sm_100`. Which vLLM version first ships working `sm_120` wheels (CUDA 12.8 / cu128)? Any remaining known breakages?
2.4 Does vLLM need to be **built from source** for RTX 50-series today, or do official PyPI wheels work? Cite the installation docs and the relevant release.
2.5 Does vLLM's **`--kv-cache-dtype fp8`** work with Ultravox / Llama-3.1 on Blackwell?
2.6 Does vLLM's **prefix caching** work with multimodal (audio) inputs? Any restrictions?
2.7 What is Ultravox's **maximum audio length per request** in vLLM (tied to Whisper's 30 s window)? Does vLLM chunk longer audio or reject it? What is `limit-mm-per-prompt` behaviour for audio?
2.8 Does vLLM support **structured output / guided grammar (EBNF)** via xgrammar or outlines for Llama-3.1-8B in current releases? Can it be combined with tool calling (`--tool-call-parser llama3_json`) and multimodal input in the same request?
2.9 Measured **host RAM** usage of a vLLM server process serving an 8B model (with and without `--enforce-eager`). Any reports of vLLM running inside WSL2 with ≤ 4.5–5 GB RAM?
2.10 Measured impact of **`--enforce-eager`** on decode throughput for 8B models at batch size 1.

## Section 3 — Ultravox model facts (both options)

3.1 Latest Ultravox release and model cards: which Whisper encoder does each version use (large-v3 vs large-v3-turbo), encoder parameter count, projector parameter count.
3.2 Does Ultravox produce a **transcript** of the user's speech as part of its output, or only a response? Is there any official "transcribe mode"?
3.3 Published **latency benchmarks** for Ultravox (time-to-first-token) on any consumer GPU.
3.4 Ultravox **tool-calling** accuracy or support statements from fixie-ai (does the model card claim function-calling works from audio input?).
3.5 **Licence**: confirm Ultravox weights/code licence and the Llama 3.1 Community License obligations for the backbone.
3.6 Does any Ultravox version support **multi-turn with audio history** without resending past audio (e.g. via text transcripts)? What does fixie-ai recommend?

## Section 4 — Cascade alternative (decides Option D)

4.1 Current best **low-latency streaming ASR** options on Windows for a 275HX CPU / Intel NPU: faster-whisper (CTranslate2), whisper.cpp, OpenVINO GenAI Whisper pipeline on NPU, `distil-whisper`, `whisper-large-v3-turbo`. Report measured latency to final transcript for a ~3 s utterance where available, and word-error-rate on LibriSpeech clean.
4.2 Does **OpenVINO GenAI's `WhisperPipeline`** run on Intel **NPU** (not just CPU/GPU) in current releases? Which Whisper sizes are supported on NPU? Cite the OpenVINO docs page and version. Any restrictions (static shapes, max audio length, decoder on CPU)?
4.3 Realistic **end-to-end latency** reports for a local cascade (streaming Whisper → 8B LLM → streaming TTS) on consumer hardware in 2025–2026 (e.g. RealtimeVoiceChat, Pipecat local examples, LiveKit local examples). Report the number and the hardware.

## Section 5 — Kokoro TTS on Intel NPU (independent Phase-1 risk)

5.1 Has anyone run **Kokoro-82M** (StyleTTS2-based, ISTFTNet vocoder) on an **Intel NPU via OpenVINO**? Search GitHub issues/discussions in `hexgrad/kokoro`, `thewh1teagle/kokoro-onnx`, `openvinotoolkit/openvino`, `openvinotoolkit/openvino_notebooks`. Report whether dynamic shapes were an obstacle and whether static-shape bucketing was used.
5.2 Does the Intel NPU OpenVINO plugin support **dynamic input shapes** in the current release, or only static? Cite the docs page and version.
5.3 Measured Kokoro **real-time factor** on: CPU (ONNX Runtime int8/fp32), Intel Arc iGPU via OpenVINO, NVIDIA GPU. Any numbers for Arrow Lake / Core Ultra.
5.4 Does Kokoro or `kokoro-onnx` expose **per-phoneme durations / timestamps** usable for lip-sync? Cite API or issue.

## Section 6 — Other embedding/classifier models on Intel NPU

6.1 Do `bge-small-en-v1.5` or `all-MiniLM-L6-v2` run on Intel NPU via OpenVINO with static-shape padding? Any measured latency at seq len 128?
6.2 Does **ModernBERT** compile for Intel NPU via OpenVINO (RoPE, unpadding, flash-attention concerns)? Any reports? If not, do DistilBERT/MiniLM classifiers?
6.3 Confirm OpenVINO does **not** support ONNX `TreeEnsembleClassifier` (XGBoost/LightGBM) on NPU or at all.

## Section 7 — Platform facts

7.1 MSI Vector 16 HX AI (2025, RTX 5080): does it have a **MUX switch / discrete-GPU mode** and Advanced Optimus? In hybrid mode, does the Windows desktop composite on the Intel iGPU (leaving dGPU VRAM free)? How much VRAM does Windows typically consume on the dGPU in discrete mode?
7.2 WSL2 `.wslconfig`: current documented semantics of `autoMemoryReclaim=gradual|dropcache`, `pageReporting`, `sparseVhd`. Does `pageReporting=false` prevent returning memory to Windows? Cite Microsoft docs.
7.3 WSL2 **mirrored networking mode**: documented effects on Docker bridge networking, iptables `DOCKER-USER` chain, and IPv6. Any Docker-CE-in-WSL2 known issues with mirrored mode.
7.4 Docker Desktop (WSL2 backend) vs Docker CE installed inside Ubuntu WSL2: can the user's `DOCKER-USER` iptables rules in the Ubuntu distro affect Docker Desktop containers? (Expected: no — Desktop uses its own `docker-desktop` distro.) Cite.
7.5 Intel NPU driver + OpenVINO: is the NPU usable from **inside WSL2** at all? (Expected: no.) Cite.
7.6 `sqlite-vec`: current release, Windows wheel availability for Python 3.12, and whether it can be loaded alongside FTS5 in the stock Python `sqlite3` module (extension loading enabled?).

## Section 8 — Comparable open-source projects (GitHub survey)

For each project below, report: URL, stars (approx), licence, last commit date, and a one-line note on what it does that overlaps with Lucca (local voice companion with avatar, memory, tool sandbox, learned rules). Add any others you find that match "local-first desktop voice companion with avatar and memory".

Open-LLM-VTuber; AIRI (moeru-ai); kimjammer/Neuro; Amica (semperai); RealtimeVoiceChat (KoljaB); RealtimeSTT / RealtimeTTS (KoljaB); Pipecat (pipecat-ai); LiveKit Agents; Vocode; Letta (MemGPT); mem0; Zep Graphiti; HippoRAG; kokoro-onnx; Kokoro-FastAPI; OpenHands; E2B; sqlite-vec.

---

## Output format

Return a single Markdown document with:

1. **Executive summary (≤ 15 lines):** for each of Options B (llama.cpp), C (vLLM), D (cascade), state GO / NO-GO / UNCERTAIN with the one decisive fact.
2. **Answer table**: one row per question ID (1.1 … 8.x) with columns `Answer`, `Confidence`, `Source URL`, `Source date`, `Version`.
3. **Contradictions found** (if any).
4. **Questions you could not answer** and what you searched.
