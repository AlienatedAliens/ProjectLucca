# Changelog

All notable changes to **Project Lucca** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and the **Zero-Estimate Principle** (all silicon performance numbers derived from live physical workstation execution).

---

## [0.2.5] — 2026-09-25

### Added
- **Hybrid Semantic Intent Routing (`HeuristicRouter` & `EmbedWorker`, D-ROUT-01):**
  - Integrated OpenVINO embedding centroid projection in `heuristic.py`. When regex pattern matching returns `unknown` or low confidence, the router projects user utterances into embedding space and computes cosine similarity against semantic intent anchors (`SEMANTIC_INTENT_ANCHORS`).
  - Wired `EmbedWorker` into `Orchestrator` startup to power zero-latency semantic classification without LLM overhead.
- **OpenVINO Inference Concurrency Protection (`_infer_lock`, D-SENSE-01):**
  - Added thread synchronization (`threading.Lock()`) around OpenVINO `infer()` calls in `senses/embed.py`, resolving the `RuntimeError: Infer Request is busy` crash caused by simultaneous execution across background memory tasks and foreground turn routing.
- **Stalling Research Promise Interceptor & Prompt Mandates (`OutputSupervisor` & `PromptBuilder`, D-SUPER-01):**
  - Expanded `STALLING_RESEARCH_PATTERN` in `sandbox/output_supervisor.py` to intercept conversational filler promises (*"Let me dive back into the deep end..."*, *"Switching over to that spelling..."*), suppressing audio emission to Kokoro TTS and flagging `turn_has_stalled`.
  - Added autonomous recovery re-prompt in `orchestrator.py` commanding immediate tool execution when stalling occurs.
  - Injected strict `[PROACTIVE FACTUAL RESEARCH DIRECTIVES]` in `prompt_builder.py` forbidding verbal promises without tool calls.
- **Turn State & History Forwarding in Turn Pipeline (`TurnPipeline` & `Orchestrator`):**
  - Fixed parameter dropping in `turn_pipeline.py` by forwarding `last_tool` and `last_tool_ok` into `router.route()` kwargs.
  - Forwarded `last_tool` in `_build_rule_state`, enabling single-word entity follow-ups (*"Factoriza"*) to refine active searches rather than misrouting to `clarify`.
- **Epistemic Cascade Grammar & Substrate Isolation (`EpistemicSearchCascade`, D-CASC-01):**
  - Corrected pronoun shift in `cascade.extract_clean_topic` (`"have you"` $\to$ `"have I"`, eliminating ungrammatical phrases like *"have me searched"*).
  - Filtered self-history queries (*"which websites have you searched"*) from triggering external web searches, routing them to session history introspection.
- **Live Flow Verification & Interactive Testing Harness (`scripts/test_session_flow.py`):**
  - Created dedicated testing script with `--interactive` terminal REPL and `--auto` 4-turn replay against the live `llama-server`.

---

## [0.2.4] — 2026-09-24

### Added
- **Work Order 17: System Remediation & Modernization:**
  - **Open-Predicate Knowledge Graph (Solution B, D-MEM-02):** Superseded closed 23-item predicate list with validated snake_case slugs (`PREDICATE_SLUG_REGEX`), automatic synonym canonicalization, ~200-demonym lexicon for `nationality_is`, and strict negation/attribution extraction guards.
  - **Runtime Memory Wiring:** Embedded CPU fallback `EmbedWorker` in `senses/embed.py`, auto-initialized `DatabaseManager` + `MemoryStore` in `Orchestrator` and `main.py`, and introduced a single persistent `_commit_executor` thread pool.
  - **Frictionless Memory Commits:** Stripped voice confirmation for clean memory commits; required confirmation only when memory input is tainted with `UNTRUSTED_WEB`. Enhanced `parse_confirmation_response` with token matching and fail-closed safety (D-SEC-03).
  - **Deterministic Math Tool (`calc_math`) & Confirmation Provenance Split (D-SEC-02):** Added AST-based `calc_math` tool (19th native tool in registry) under `Risk.READ`. Separated internal component confirmation (`confirmed`) from explicit human voice/UI grants (`human_confirmed`) in `SandboxService` and `SequenceGuard`.
  - **Timezone-Aware System Telemetry:** Included `timestamp`, `utc_offset`, `utc_offset_hours`, and `timezone_name` in `get_system_metrics()`.
  - **Audio Queue Stability & Coherence:** Expanded `_tts_queue` maxsize from 8 to 32 with drop-oldest overflow policy and telemetry logging; added drain-and-retry sentinel protection for `FLAG_EOS`; excluded analytical idioms from `coherence.py`.

---

## [0.2.3] — 2026-09-21

### Added
- **Deterministic ASR Spelled-Word Normalization (`normalize_spelled_words`):**
  - Regex-based preprocessor in `orchestrator.py` detecting letter-by-letter spelling sequences (`F-A-W-K-N-E-R`, `F A W K N E R`, `F. A. W. K. N. E. R.`) and assembling them into verified title-cased tokens (`Fawkner`).
  - Automatically prepends an authoritative system grounding notice (`[User Explicit Spelling Correction: The target entity is 'Fawkner'...]`), eliminating reliance on model phonetic guessing.
- **In-Place History Token Neutralization (`_neutralize_context_attractors`):**
  - Computes Levenshtein edit distance against recent history tokens to identify and rewrite phonetic/orthographic corruptions (`Faulkner` $\to$ `Fawkner`) in-place across prompt history.
  - Destroys Transformer self-attention repetition attractor wells without pruning conversation turns, preserving pronoun antecedents and complete conversational context.
- **Factual Inquiry Intent Expansion & Tool Gating Hardening (`HeuristicRouter` & `Orchestrator`):**
  - Reordered intent evaluation so `memory_query` and `chit_chat` are evaluated before `web_fetch`, preserving personal memory queries (`"what is my brother's name"`) while achieving 0.987 Macro-F1 on adversarial router fixtures.
  - Expanded `web_pattern` to classify common factual question openings (`where is`, `who is`, `what is`, `tell me about`, `facts about`, `how about`) as actionable `web_fetch` intents.
  - Removed `"unknown"` and `"clarify"` from `TOOLLESS_INTENTS` in `orchestrator.py`, guaranteeing factual inquiries and research affirmations (`yes`, `sure`, `okay`, `do it`, `where is`, `tell me more`) never have tools stripped.
- **Corrective Search Query Injection & Category Grounding (`_handle_tool_call`):**
  - When spelled targets or location/category context (`suburb`, `judge`, `court`, `victoria`, `australia`, `philippines`) appear in the turn context, automatically validates and enriches `search_web` queries (e.g. `search_web("Fawkner" suburb Victoria)`), preventing DuckDuckGo semantic drift toward famous authors or unrelated entities.
- **Output Supervisor Stalling Clamp & Autonomous Research Loop (`OutputSupervisorSession` & `_stream_llm_speech`):**
  - Added `STALLING_RESEARCH_PATTERN` in `output_supervisor.py` to suppress lazy rhetorical interrogation clauses (*"Would you like me to look into...?"*, *"Shall I look up...?"*) from voice TTS emission.
  - Implemented an autonomous multi-round recovery loop: if the model emits a stalling question without calling tools, the orchestrator intercepts the evasion, injects an autonomous research directive, and re-prompts for immediate tool execution.

---

## [0.2.2] — 2026-09-21

### Added
- **Native Document Ingestion & PDF Extraction (`fetch_url` / `pypdf`):**
  - Integrated `pypdf` parsing inside `SandboxService.fetch_url`, enabling Lucca to autonomously download, extract, and ground responses in real-world PDF documents (government appointment rosters, legal schedules, whitepapers).
  - Added configurable `max_chars` extraction limit with defensive truncation and metadata extraction.
  - Extracted embedded hyperlinks found inside document text and PDF layers, automatically populating `structured["embedded_links"]` to allow legitimate citation of internal references without false-positive supervisor aborts.
- **Cryptographic TLS Integrity via Native OS Certificate Store (`truststore`):**
  - Integrated `truststore.inject_into_ssl()` leveraging Windows CryptoAPI (`crypt32.dll`) to validate public government and enterprise portals that omit intermediate CAs via native Authority Information Access (AIA) intermediate chasing.
  - Completely eliminated all insecure `verify=False` retries and hardcoded domain whitelists, enforcing 100% strict TLS verification across all requests.
- **Dual-Path Web Capabilities & Hardened Headless Browser (`HeadlessBrowserTool`):**
  - Path 1: Fast HTTP/HTTPS scraping via `httpx` with Link Triage & SERP Re-Ranking (`classify_link_followability`) demoting login walls (`facebook.com`, `linkedin.com`, `x.com`) and prioritizing followable HTML and PDF assets.
  - Path 2: Real-time headless Chromium automation via Playwright with strict TLS verification (`ignore_https_errors=False`) and socket-level host resolver rules (`--host-resolver-rules="MAP 127.* 0.0.0.0, MAP 10.* 0.0.0.0, MAP 172.16.* 0.0.0.0, MAP 192.168.* 0.0.0.0, MAP 169.254.* 0.0.0.0, MAP ::1 0.0.0.0"`), mathematically barring TOCTOU DNS rebinding directly in the browser network stack.
  - Added dynamic `--no-sandbox`, `--disable-gpu`, `--disable-dev-shm-usage` hardened headless browser process isolation with reliable context/browser lifecycle disposal in `finally` blocks.
- **Raw-Stream Citation Provenance Guard & Epistemic Abstention (`CitationProvenanceMatcher`):**
  - Session-scoped URL whitelist seeded dynamically from conversation history, Substrate 2 memory, tool execution receipts, and document-embedded links.
  - Evaluates un-sanitized raw tokens (`TTSChunk.raw_text`) before speech normalisation strips URLs to `"a link"`, preventing ungrounded hallucinated URL citations.
  - Tightened subpath provenance matching, preventing root-level grants from permitting fabricated subpaths while preserving local developer port discussions.
  - Expanded URL extraction regex to extract scheme-less FQDNs ending in common public suffixes (`.com`, `.net`, `.org`, `.gov`, `.ph`, `.io`, `.ai`).
  - Automatically trips Belnap epistemic abstention (`_trigger_supervisor_abort`), replacing confabulated URLs with calibrated refusal: *"I apologize, but I do not have a verified source for that citation and won't guess."*
- **Forced Final Synthesis & Natural Spoken Attribution (`Orchestrator` & `PromptBuilder`):**
  - Enforced final synthesis boundary stripping tool definitions when reaching `max_rounds` so the model always synthesizes grounding into speech rather than emitting trailing tool calls.
  - Un-suppressed tools on challenge and follow-up turns ("Are you sure?", "Tell me more") allowing active re-verification.
  - Added persona directives instructing the model to speak citations naturally by organization/title (e.g. *"According to the Supreme Court roster..."*) rather than reciting raw `https://` URLs phonetically in Kokoro TTS.
- **Zero-Mock Verification & Chaining Test Fixtures (`tests/test_tool_chaining.py`):**
  - 15 formal unit and integration tests covering multi-round chaining, SSRF interception, followability classification, PDF extraction, host-resolver rules, and citation provenance enforcement.
  - Live zero-mock test harness (`scripts/verify_live_web_and_pdf.py`) validating physical DuckDuckGo querying, live government PDF parsing with strict TLS, Playwright browser rendering, and real-time supervisor aborts.

---

## [0.2.1] — 2026-09-21

### Added
- **5-Line Fixed-Geometry Paginated Speech Bubble (`SpeechBubble`):**
  - Replaced unbounded dynamic ballooning (84px $\to$ 894px) with a stable, fixed 5-line height dialogue window (`460x188px`).
  - Implemented `_paginate()` using `QTextLayout` wrapped at character boundary to cleanly paginate long explanations into discrete 5-line pages.
  - Added interactive Chrono Trigger-themed pager controls (`btn_prev` `◀`, `lbl_page` `[ 1 / N ]`, `btn_next` `▶`) in footer.
  - Added header close button (`✕`) and removed the 7-second auto-dismiss timer; dialogue persists until dismissed or replaced.
  - Completely eliminated Win32 High-DPI layout fighting (`QWindowsWindow::setGeometry: Unable to set geometry`), resolving GUI event-loop starvation and speech stuttering.
- **Responsive Scrollable Settings Dialog (`SettingsDialog`):**
  - Wrapped all 11 configuration tabs (`tab_persona`, `tab_voice`, `tab_llm`, `tab_tools`, `tab_lisp`, `tab_ptt`, `tab_dsp`, `tab_memory`, `tab_diag`, `tab_manual`, `tab_about`) in `QScrollArea` with retro-styled scrollbars.
  - Implemented screen containment and auto-centering (`center_on_screen()`) clamping window geometry within `availableGeometry()`, guaranteeing the titlebar is never positioned off-screen or unmovable on multi-monitor / laptop setups.
  - Reduced minimum window size from 880x640 to 760x520 for high-DPI scaling (125%–175%).
- **Dedicated SSRF-Hardened Web Search Tool (`search_web`):**
  - Integrated `ddgs` with Rust-backed `primp` browser TLS/JA3/JA4 fingerprint impersonation and HTTP/2 handshakes, eliminating Cloudflare/DuckDuckGo `anomaly-modal` bot detection blocks.
  - Eliminated dangerous silent Wikipedia fallback that returned irrelevant entities and caused hallucinations on regional/people queries.
  - Added transparent failure reporting with explicit `ok=False` and structured error receipts (`bot_challenge`, `no_results`).
  - Added calibrated honest epistemic abstention returning structured receipts to prevent parametric hallucination loops.
- **Unified Dynamic Capability Registry (`CapabilityRegistry`):**
  - Authoritative single source of truth for tool schemas, approved application whitelists (`calc.exe`, `notepad.exe`, `wt.exe`, `taskmgr.exe`, `msedge.exe`), and MicroScheme LISP rules.
  - Zero-`Any` typed interface complying with strict static architecture gates.
- **4 Permanent Committed Negative Regression Test Fixtures:**
  - `tests/test_d_reas_07_negative.py`: Enforces that unmodeled MicroScheme predicates fail closed in Z3 SMT prover.
  - `tests/test_d_reas_08_negative.py`: Enforces that empty production data blocks macro synthesis claims.
  - `tests/test_d_reas_06_negative.py`: Enforces that zero telemetry blocks rule induction promotion.
  - `tests/test_d_aud_11_negative.py`: Enforces that data volume gates fail closed on 0-row SQLite databases.

### Changed
- **Z3 SMT Prover Fail-Closed Invariant (`smt_verifier.py`):**
  - Changed `_translate_expr` fallthrough from silent `z3.BoolVal(True)` (fail-open) to `raise ValueError(...)`.
  - Added `UNMODELED_PREDICATE` verification status in `verify_rule()` to prevent unmodeled operators from being admitted into quarantine.
- **Multi-Round Context Preservation (`orchestrator.py`):**
  - Fixed Round 2 context loss where `current_text` was set to `None`, preserving user utterance alongside tool traces in narration turns.
- **Voice Markdown Sanitization (`sanitize_for_voice`):**
  - Strips markdown asterisks, backticks, bullet dashes, raw URLs, and headers before passing tokens to Kokoro-82M TTS.
- **Full 138-Claim Documentation Alignment:**
  - `README.md`: Corrected hardware placement table to reflect that only embeddings run on NPU; ASR runs on dGPU CUDA float16 (+555 MiB VRAM); TTS/VAD run on CPU. Separated regex classification ($6.4\,\mu\text{s}$) from physical WASAPI audio abort ($20\text{--}50\,\text{ms}$).
  - `docs/ARCHITECTURE.md`: Clarified normative stage budgets with explicit footnotes; aligned ASR running baseline to CUDA float16; downgraded fixture-only induction and telemetry claims to `Enforced (Unit Tested; 0 Production Rows)`.
  - `docs/specs/TECHNICAL_RESPONSE_AND_CAPABILITY_STATUS_MAP.md`: Updated capability statuses to reflect tested reality.
  - `docs/DECISIONS.md`: Aligned canonical decision records (D-AUD-11, D-AUD-15, D-REAS-06, D-REAS-07, D-SUP-01).

### Verified
- **Full Pytest Regression Suite:** 418 passed in 86.24s (100% green).
- **Master Claims Audit:** 138 / 138 claims verified (0 failed, 0 unverifiable, 0 contradictions, 0 regressions).

---

## [0.2.0] — 2026-09-20

### Added
- **Milestone 7: Standalone Frozen PyInstaller Packaging (`Lucca.exe`):**
  - Bundled standalone Windows executable distribution (`dist/Lucca/Lucca.exe`, 25.9 MB) bundling Python 3.12, PyQt6, libz3, ONNX Runtime, OpenVINO dynamic plugins, Kokoro voice models, and sqlite-vec.
  - Dual-mode console & GUI subsystem lifecycle (`console=False` with dynamic `AttachConsole(-1)` stdio binding).
  - CLI diagnostic flags: `--version`, `--help`, `--check` (7-point native hardware audit), `--headless`.
  - Persistent `QSystemTrayIcon` companion with cognitive state tooltips and graceful multi-process exit.
- **Milestone 6: Neurosymbolic Reasoning Tier (MicroScheme & E-Graphs):**
  - Autonomous rule induction mining execution telemetry clusters ($N \ge 3$) strictly into `QUARANTINE`.
  - Babble/Stitch first-order syntactic anti-unification macro synthesis within E-Graph congruence closure representation (`EGraph`) enforcing compression metric $\Delta \text{size} \ge 1$.
  - Z3 SMT Formal Invariant Verifier (`SMTVerifier`): automated SAT satisfiability, non-tautology contingency, and deontic path traversal safety proofs in $\le 25\,\text{ms}$.
- **Milestone 5: Continuous 3D PAD Affective Dynamics & KV-Cache Suffix:**
  - Analytical closed-form discrete differential equations for Mehrabian 3D Pleasure-Arousal-Dominance space ($t_{1/2}=45\text{s}, 300\text{s}, 900\text{s}$).
  - Global Lyapunov asymptotic stability clamp on cognitive feedback gain ($\text{gain} \le 0.0005$).
  - Prompt Frontier Suffix KV-Cache Optimization: quantized stance tokens appended exclusively at prompt tail, achieving **$8.58\times$ faster prefill** ($46.84\,\text{ms}$ vs. $402.05\,\text{ms}$ on RTX 5080 dGPU).
  - Real-time arousal-modulated speech rate in Kokoro-82M ($1.0 \pm 0.10$).
- **Milestone 4: Speculative BDI Validation & Streaming Supervision:**
  - `SpeculativeBDIValidator`: pre-dispatch deontic policy check intercepting candidate tool calls in **$2.9\text{--}32.0\,\mu\text{s}$** (budget $\le 200\,\mu\text{s}$).
  - Cognitive bus arbitration via MicroScheme signals: `(yield-to-core)` and `(interrupt-core)`.
  - Streaming Output Supervision (Dimension 7B): compiled grammar rules and DFA capitulation detection ($P_{50} = 6.4\,\mu\text{s}$) with WASAPI audio buffer drain.
- **Milestone 3: 5-Substrate Epistemic Search Cascade:**
  - Prioritized cascade (Substrate 0 Telemetry $\to$ Substrate 1 Workspace $\to$ Substrate 2 Memory $\to$ Substrate 3 Web Floor $\to$ Substrate 4 Abstention).
  - Belnap $\mathcal{FOUR}$ evidential bilattice ($\mathbf{T}, \mathbf{F}, \mathbf{B}, \bot$) yielding $0 / 25$ hallucinations (100% adherence) in live confabulation testing.
  - Sub-millisecond pre-rendered PCM audio floor cues written directly to shared memory ring buffer ($3.1\,\mu\text{s}$).
- **Milestone 2: Deontic Sandboxing & Persistent Docker RPC:**
  - Long-lived persistent daemon (`lucca-toolsrv --loop`) inside WSL2 container achieving **$6.87\,\text{ms}$ P50 RPC turnaround** (83x speedup).
  - In-container zombie process reaping inspecting `/proc/*/cmdline`.
  - Hardened Win32 handle containment (`verify_and_open_workspace_file`) with two-stage non-destructive handle resolution and reparse point jailing.
  - Bidirectional persistent taint tracking (`TaintFlags`) preventing data exfiltration.
  - Temporal spoken confirmation tokens with HMAC-SHA256 session binding.
- **Milestone 1: Empirical Silicon Baseline Profiling:**
  - Full acoustic loopback ear-to-ear latency measured at **$707.55\,\text{ms}$ P50** on CUDA float16.
  - LLM Time-to-First-Token (TTFT) on Mistral NeMo 12B Q6_K: **$44.5\,\text{ms}$ median** (10,748 MiB resident VRAM clamp on RTX 5080).
  - SQLite vector search (`sqlite-vec`) P50: $8\text{--}15\,\text{ms}$ over 384-D embeddings.

---

## [0.1.0] — 2026-09-18

### Added
- Initial release of Project Lucca architecture.
- 4-process topology: Audio IO, Core Orchestrator, LLM Brain (`llama-server.exe`), and WSL2 Container Sandbox.
- MicroScheme LISP symbolic evaluation engine with 1,000 gas limit.
- Kokoro-82M ONNX TTS engine with 24 kHz anime voice shaping DSP chain.
- Silero VAD and Faster-Whisper ASR pipeline.
- SQLite WAL hybrid storage with `sqlite-vec` vector retrieval and FTS5 BM25 search.
- Chrono Trigger-themed PyQt6 desktop companion interface and HUD.
