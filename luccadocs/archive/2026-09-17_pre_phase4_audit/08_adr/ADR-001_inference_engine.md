# ADR-001 — Inference Engine: `llama-server` on Windows serving Ultravox Q6_K GGUF, with cascade as a config-switch fallback

**Status:** Accepted 2026-09-17 (D-01, D-02, D-04 in [`13_decisions_log.md`](../13_decisions_log.md))
**Supersedes:** doc 00 §Phase 1 "Ultravox 8B Q6 via vLLM"; doc 03 §Domain B; doc 05 inference block.

## Context

The brief specifies "Ultravox 8B Q6 via vLLM". Verified facts (research report, review-graded A):

1. vLLM's GGUF loader handles text backbones only; `UltravoxModel` (audio projector + Whisper encoder) cannot be constructed from GGUF. vLLM would require BF16 (~16 GB, doesn't fit) or runtime FP8 (~10.5 GB weights because embeddings and `lm_head` stay 16-bit).
2. vLLM is Linux-only → WSL2 → 2.5–3.8 GB host RSS inside a 4.5 GB clamp shared with the Docker sandbox → OOM.
3. llama.cpp supports Ultravox audio input (`libmtmd`, PR #13623) and `llama-server` accepts OpenAI `input_audio` content parts (PR #13714). `ggml-org` publishes `ultravox-v0_5-llama-3_1-8b-GGUF` at Q4_K_M…Q8_0 with a separate `mmproj` (Q8_0 ≈ 743 MB, f16 ≈ 1.27 GB).
4. Ultravox emits **no user transcript**; a separate ASR pass is required for routing, `USER_EXPLICIT` provenance, and multi-turn history in every design.

## Decision

### Primary — Option B

Run `llama-server` as a **native Windows process** (CUDA 12.8+ build, `sm_120`), loading:

```
C:\ProjectLucca\models\llm\ultravox-v0_5-llama-3_1-8b-Q6_K.gguf        (~6.6 GB)
C:\ProjectLucca\models\llm\mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf (~0.74 GB)
```

Canonical launch (parameters are the spec; the implementer wraps this in `lucca-core`'s supervisor, see spec 11):

```powershell
llama-server.exe `
  --model  "$env:LUCCA_HOME\models\llm\ultravox-v0_5-llama-3_1-8b-Q6_K.gguf" `
  --mmproj "$env:LUCCA_HOME\models\llm\mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf" `
  --n-gpu-layers 99 `
  --ctx-size 8192 `
  --cache-type-k q8_0 --cache-type-v q8_0 `
  --parallel 1 `
  --flash-attn `
  --host 127.0.0.1 --port 8080 `
  --no-webui `
  --jinja `
  --log-format json
```

Notes on each flag:

| Flag | Why | Phase 0 check |
|---|---|---|
| `--n-gpu-layers 99` | Full offload; host RSS stays ~0.4–0.7 GB. | Measure RSS. |
| `--ctx-size 8192` | Memories + history + system prompt + ~375 audio tokens/30 s. | Fits KV budget below. |
| `--cache-type-k/v q8_0` | KV ≈ 0.55 GB vs 1.07 GB f16 at 8 k. **Requires `--flash-attn`** (V-cache quantisation is only supported with flash attention in llama.cpp). | Verify tool-call JSON validity rate unchanged vs f16 over 50 fixture prompts; else revert to f16. |
| `--parallel 1` | Single user; one slot; barge-in uses slot release. | — |
| `--flash-attn` | Lower compute-buffer VRAM. | Confirm no `sm_120` kernel error. |
| `--jinja` | Enables the model's chat template incl. Llama 3.1 tool-call format. | Tool call round-trip test. |
| `--host 127.0.0.1` | Never bind externally. | Threat model (spec 12). |

**Barge-in / abort:** close the HTTP stream **and** `POST /slots/0?action=release`. Measured abort-to-idle latency must be ≤ 50 ms (spec 10).

**Structured output:** GBNF via the `grammar` request field (used by the reflection loop to force S-expressions, spec 05). Must be tested **together with** tools + audio in one request (research 1.6 was an inference, not a citation).

### Mandatory fallback — Option D (cascade), pre-wired

Same binary, same backbone quantization, different config:

| | B (audio-native) | D (cascade) |
|---|---|---|
| `--mmproj` | present | **absent — same model file.** Ultravox trains only the projector with the Llama-3.1-8B-Instruct backbone frozen, so the Q6_K backbone GGUF *is* a text-only Llama-3.1-8B-Instruct; no second 6.6 GB download is needed. (**Verify in spike S10**: if v0.5 turns out to have LoRA-tuned the backbone, run the text-mode quality check below; a separate `text_model` GGUF is then optional, not assumed.) |
| User turn payload | `input_audio` (wav base64, 16 kHz) + text history | Whisper transcript as text |
| Whisper | runs in parallel (speculative), result used for routing/memory | runs **first**, on critical path |
| Extra VRAM | +0.74 GB mmproj | 0 |
| Expected latency delta | baseline | +100–200 ms (ASR must finish before LLM starts) |

Switch = `config\lucca.toml → [llm] mode = "audio" | "transcript"`. At startup, if `mmproj` fails to load or the Phase 0 gate fails, `lucca-core` starts in `transcript` mode and speaks a one-line notice (O-4).

### Retired — Option C (vLLM in WSL2)

Removed from all docs, `pyproject.toml`, and WSL2 budgets. Do not re-introduce without a new ADR.

## Consequences

**Positive**
- Matches the brief's model and quantization literally.
- WSL2 now hosts only the sandbox (D-04); the 4.5 GB clamp becomes comfortable.
- No Linux GPU driver path, no vLLM-on-Blackwell build risk.
- Host RSS for the LLM server ≈ 0.5 GB instead of ≈ 3 GB.
- B↔D switching is trivial, so the Phase 1 acceptance gate can be met by D if B under-performs, **without silently weakening the criteria** — the mode is reported.

**Negative / risks**
- llama.cpp's OpenAI-compat layer is less battle-tested than vLLM's for tool calling + grammar + multimodal simultaneously. **Mitigation:** Phase 0 spike test matrix below; `SpeechLLMPort` isolates the adapter.
- `llama-server` prompt caching is per-slot prefix reuse; re-sent audio invalidates it. **Mitigation:** system prompt + memory block are placed *before* the audio so the text prefix stays cached; only the current turn's audio is ever sent (research 3.6).
- Q6_K quality < FP8. Accepted; the brief specified Q6.
- Windows process supervision (crash → restart) must be built (spec 11).

## Phase 0 spike — exit criteria (all must be recorded in `logs\phase0_llm.json`)

| # | Measurement | Method | Pass |
|---|---|---|---|
| S1 | Model loads with `mmproj`; `GET /health` OK | startup | ≤ 60 s cold, ≤ 15 s warm |
| S2 | TTFT for a 3 s 16 kHz wav + 600-token text prefix | 20 runs, `t_first_token − t_request_sent` | median ≤ 200 ms, p95 ≤ 300 ms |
| S3 | Decode throughput | 20 runs × 64 tokens | ≥ 60 tok/s median |
| S4 | VRAM steady after 20 turns | `nvidia-smi` | ≤ 9.5 GB; slope ≤ 20 MB/turn |
| S5 | Host RSS of `llama-server.exe` | Task Manager / `Get-Process` | ≤ 800 MB |
| S6 | Tool call from audio ("open the calculator") returns valid Llama-3.1 JSON tool call | 20 fixture clips | ≥ 18/20 valid JSON, correct tool name |
| S7 | `grammar` + `tools` + `input_audio` in one request | 10 runs | 10/10 grammar-conformant output |
| S8 | Abort latency (`/slots/0?action=release`) | 10 runs mid-generation | ≤ 50 ms to slot idle |
| S9 | 30.5 s clip | 1 run | Rejected with a clean error (not a crash); client enforces 29.5 s cap |
| S10 | Cascade mode end-to-end with same server, `mmproj` unloaded, **same backbone file** | 10 runs + 20 text tool-call fixtures | Works; latency delta recorded; tool-call validity ≥ 18/20 (confirms backbone is usable as a text model) |

If S1–S3, S6, S8 pass → **B is primary**. If any fail after one day of effort → **D is primary**, B remains an optional mode, and phase plan 11 records the switch with the measured numbers. Neither outcome changes any other ADR.

## Alternatives considered

| Option | Why not |
|---|---|
| vLLM WSL2 FP8 | GGUF impossible; RAM collision; sm_120 kernel instability. |
| vLLM natively on Windows | Not supported. |
| Ollama | Wraps llama.cpp; multimodal audio support lagged; extra layer with no benefit. |
| TensorRT-LLM | No Ultravox support; heavy build. |
| Ultravox v0.5 Llama-3.2-1B | Reserve as a low-VRAM emergency mode only; reasoning quality inadequate for tool use. |
| Moshi / Mini-Omni / Qwen2-Audio | VRAM (Moshi), quality (Mini-Omni), or no verified GGUF audio path (Qwen2-Audio in llama.cpp is supported for some variants — revisit in Phase 7+). |
