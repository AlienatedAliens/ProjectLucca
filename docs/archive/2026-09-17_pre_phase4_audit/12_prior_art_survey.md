# 12 — Prior Art, Comparable Projects, and Alternatives Survey

Complements (and corrects) `02_systems_research_prior_art_and_alternatives.md`. **Verification status:** column `V` = `A` (verified in the 2026-09-17 research report with a specific URL), `B` (report cited only a repo root; details plausible, re-check), `R` (recalled from training knowledge; **must be verified by the implementer** — URL, licence, activity — before being cited in any user-facing doc). Star counts are snapshots and will drift; do not copy them into acceptance criteria.

## 1. Corrections to doc 02

| Doc 02 claim | Correction |
|---|---|
| Cascade 700–1 200 ms | 350–500 ms with streaming ASR; cascade is the mandatory fallback (ADR-001). |
| Ultravox "Apache 2.0" | Projector Apache-2.0; backbone Llama 3.1 Community License. |
| Ultravox "Llama 3.1 8B / Mistral 7B" | v0.5 8B GGUF is Llama-3.1-8B only. |
| Kokoro "Elo/MOS" | TTS-Arena Elo is a preference ranking, not MOS; do not cite as MOS. |
| "Reflection Drift" | Undefined term; replaced by the lifecycle + regression mechanics in spec 05. |
| Missing GitHub survey | §2 below. |
| Broken local-path link | Removed; all links here are URLs or repo slugs. |

## 2. Comparable projects (what Lucca can borrow, what it must not)

### 2.1 Local voice companions with avatars (closest analogues)
| Project | V | Overlap | Borrow | Don't |
|---|---|---|---|---|
| `Open-LLM-VTuber/Open-LLM-VTuber` | A | local ASR/LLM/TTS loop, Live2D, interruption, tool hooks | interruption UX patterns; config layout for pluggable ASR/TTS | its memory (no provenance); its single-process design |
| `moeru-ai/airi` | A | web-first VTuber companion, game control | UI state model | browser runtime (RAM) |
| `kimjammer/Neuro` | A | RealtimeSTT + local LLM + TTS cascade | latency tricks (streaming STT partials) | — |
| `semperai/amica` | A | 3D VRM companion, pluggable local backends | backend abstraction | 3D pipeline (Phase 7+) |

### 2.2 Voice pipeline frameworks (chunking, barge-in, VAD)
| Project | V | Borrow |
|---|---|---|
| `livekit/agents` | A | sentence aggregation heuristics; VAD-triggered interruption; per-stage metrics naming |
| `pipecat-ai/pipecat` | A | frame-based pipeline; interruption strategies; "TTS text aggregator" min/max sentence lengths |
| `KoljaB/RealtimeVoiceChat`, `RealtimeSTT`, `RealtimeTTS`, `stream2sentence` | A/R | `stream2sentence` boundary rules (abbreviations, decimals) — cross-check spec 08 against it |
| `vocodedev/vocode-core` | A | turn-taking state machine |
| `snakers4/silero-vad` | R | VAD thresholds, 32 ms windows |

### 2.3 Speech-native LLMs (alternatives behind `SpeechLLMPort`)
| Model | V | Note |
|---|---|---|
| Ultravox v0.5/v0.6 (fixie-ai) | A | chosen; GGUF via ggml-org |
| Qwen2-Audio-7B | R | llama.cpp mtmd support for some Qwen audio variants; VRAM similar; revisit Phase 7 |
| Moshi (Kyutai) | R | full-duplex; 24 GB unquantized; out of budget |
| Mini-Omni / GLM-4-Voice | R | quality or VRAM concerns; documented in doc 02 |

### 2.4 ASR / TTS tooling
| Project | V | Note |
|---|---|---|
| `SYSTRAN/faster-whisper` | A | CPU fallback ASR (CTranslate2 int8) |
| `ggml-org/whisper.cpp` | R | alternative CPU/GPU ASR; not needed if OpenVINO NPU path works |
| OpenVINO GenAI `WhisperPipeline` (NPU) | A | primary ASR |
| `huggingface/distil-whisper` | R | small CPU fallback |
| `hexgrad/kokoro`, `thewh1teagle/kokoro-onnx`, `remsky/Kokoro-FastAPI` | A | TTS; FastAPI project shows a decoupled TTS process pattern |
| `hexgrad/misaki` | R | G2P without espeak for English |

### 2.5 Agent memory
| Project | V | Relevance |
|---|---|---|
| `letta-ai/letta` (MemGPT) | A | tiered memory (core/recall/archival) ≈ working/episodic/semantic; **no provenance** |
| `mem0ai/mem0` | A | fact extraction + dedupe/supersede prompts — compare with spec 03 §5.2 grounding |
| `getzep/graphiti` | A | **bi-temporal edges (`valid_at/invalid_at`)** — spec 04 mirrors this |
| `OSU-NLP-Group/HippoRAG` | R (report mis-attributed) | PPR over KG for multi-hop recall; Phase 7 candidate for graph expansion beyond 1 hop |
| Generative Agents (Park et al. 2023) | R | memory stream + **reflection** — the closest published analogue to Lucca's reflection loop; importance scoring idea → `memories.importance` |
| CoALA (Sumers et al. 2023) | R | cognitive-architecture vocabulary (working/episodic/semantic/procedural) — Lucca's rules = procedural memory |
| RRF (Cormack et al. 2009), BM25/FTS5, ColBERT | R | fusion constant 60 standard |

### 2.6 Symbolic / rule learning (prior art for "compiled reasoning")
| Work | V | Relevance |
|---|---|---|
| Soar chunking; ACT-R production compilation | R | the classic mechanism of turning repeated deliberate steps into a production rule — Lucca's promotion gate is a conservative version with statistical thresholds |
| Voyager (Wang et al. 2023) | R | LLM-written skill library with verification before storage |
| Reflexion (Shinn et al. 2023) | R | verbal self-reflection stored as memory; Lucca stores *rules*, not narration |
| DreamCoder | R | library learning; wake/sleep ≈ live/reflection |
| Popper, ILASP (ILP) | R | learning rules from positive/negative examples — a future replacement for LLM rule proposal |
| PDDL planners (Fast Downward), HTN (`pyhop`/`GTPyhop`) | R | if plans grow beyond 1–2 tool calls |
| Norvig `lis.py`, `hissp`, `hy`, `sexpdata` | R | Scheme-in-Python references; Lucca's DSL is deliberately smaller |

### 2.7 Routing, calibration, small-N classification
| Work | V | Relevance |
|---|---|---|
| RouteLLM, FrugalGPT, Hybrid LLM | R | routing between cheap/expensive paths; Lucca's RULE/LLM split |
| MAPIE, `CalibratedClassifierCV`, netcal, Venn-Abers | R | conformal + calibration libraries; spec 06 implements split-conformal by hand (10 lines) to avoid deps, MAPIE acceptable |
| Rasa DIET, SetFit | R | few-shot intent classifiers; SetFit is the recommended alternative if LightGBM under-performs at N≈600 |

### 2.8 Sandboxing
| Project | V | Relevance |
|---|---|---|
| `All-Hands-AI/OpenHands` | A | Docker tool sandbox, event stream |
| `e2b-dev/E2B` | A | Firecracker microVM sandboxes (cloud); semantics reference |
| gVisor, Firecracker, nsjail, bubblewrap | R | stronger isolation; not usable in stock WSL2 kernel (gVisor) or overkill; Phase 7+ |
| Docker `DOCKER-USER` docs; WSL2 mirrored networking docs | A | ADR-003 basis |

### 2.9 Platform
| Item | V |
|---|---|
| Intel NPU static-shape requirement (OpenVINO docs) | A |
| OpenVINO lacks `TreeEnsembleClassifier` (issues #21168, #23778) | A |
| `.wslconfig` `pageReporting`/`autoMemoryReclaim` | A |
| `asg017/sqlite-vec` | A |
| llama.cpp PRs #13623 (Ultravox mtmd), #13714 (server `input_audio`) | A |

## 3. Alternatives considered and rejected (index)

| Area | Chosen | Rejected (see ADR) |
|---|---|---|
| Engine | llama-server Windows | vLLM WSL2 (ADR-001), Ollama, TensorRT-LLM |
| Storage | SQLite+FTS5+sqlite-vec | Chroma, LanceDB, FAISS, Neo4j (ADR-002) |
| Egress | ordered DOCKER-USER + default drop | proxy container (Phase 7), gVisor (ADR-003) |
| Sandbox | split file/web | single container (ADR-004) |
| UI | PyQt6 | Pygame, Raylib, Electron (ADR-005) |
| Provenance | capability signers + tiers | single HMAC (ADR-006) |
| Rules | pure State→Plan | side-effecting rules (ADR-007) |
| Topology | 4 processes + ZMQ | single process/threads (ADR-008) |
| PTT | right-Ctrl Win32 hook | caps-lock pynput (D-10) |
| Web fetch | httpx+trafilatura | Playwright default (D-12) |

## 4. Verification checklist for the implementer

Before Phase 1 sign-off, fill `docs/12a_prior_art_verification.md` with, for every `B`/`R` row used in a spec: URL, licence, last commit date, the specific fact relied upon, and whether it still holds. Rows not relied upon by any spec may be left unverified but must be marked so.
