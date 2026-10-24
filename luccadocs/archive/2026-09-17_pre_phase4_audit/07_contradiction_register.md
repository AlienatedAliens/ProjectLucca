# 07 — Contradiction Register & Canonical Values

Every place where docs 00–05, `README.md`, `pyproject.toml`, or `src/` disagree with each other or with verified facts. Each row gives the **canonical value** the implementer must use. Line numbers refer to the files as of 2026-09-17.

Legend: **C** = canonical value adopted (see [`13_decisions_log.md`](13_decisions_log.md)); **FIX** = edit required in the listed file.

---

## A. Latency

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| A1 | "target 300-600ms" | [`00 L85`](00_original_build_brief.md:85) | Range, not a target. | **C:** median ≤ 475 ms target; median ≤ 600 ms hard gate; p95 ≤ 800 ms; measured PTT-release → first *non-silent* output buffer. Per-stage budgets in spec 10. |
| A2 | "sub-400 millisecond response times" | [`05 L12`](05_lucca_system_architecture_master_spec.md:12) | Contradicts A1 and A3; marketing number. | **FIX:** replace with "typically under half a second (≤ 600 ms guaranteed)". |
| A3 | `assert 300.0 <= median_latency <= 600.0` | [`04 L112`](04_deep_mechanical_testing_and_verification_matrix.md:112) | **Lower bound fails a faster system.** | **FIX:** `assert median <= 600 and p95 <= 800`. |
| A4 | Ultravox TTFT "~150–250ms" | [`02 L25`](02_systems_research_prior_art_and_alternatives.md:25) | Unsourced; conflicts with doc 01's 45 ms TTFT assumption ([`01 L67`](01_recursive_architecture_audit_and_flaw_analysis.md:67)). | **C:** treat 140–180 ms as planning estimate (research 3.3, grade B-); **measure in Phase 0**. |
| A5 | Cascade "~700–1200ms" | [`02 L28`](02_systems_research_prior_art_and_alternatives.md:28) | Outdated; streaming ASR partials change the arithmetic. | **C:** 350–500 ms planning estimate. Cascade is the mandatory fallback (D-01). **FIX** doc 02 row. |
| A6 | Kokoro "~300ms" for 7 s audio (≈ 43 ms/s) | [`01 L66`](01_recursive_architecture_audit_and_flaw_analysis.md:66) | Unsourced; doc 02 implies 35 ms/s; research 5.3 (grade C) says CPU ≈ 140 ms/s. | **C:** no number is canonical until measured. Budget uses **first-chunk latency ≤ 180 ms for a ≤ 1.5 s clause** on whichever device passes the ladder (D-07). |

## B. VRAM

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| B1 | "must stay under ~8GB for Ultravox+KV cache" | [`00 L86`](00_original_build_brief.md:86) | Not achievable with encoder + KV + CUDA context. | **C (llama-server, D-01):** Q6_K 6.6 GB + mmproj Q8_0 0.74 GB + KV 8 k ctx q8_0 ≈ 0.55 GB + compute buffers/CUDA context ≈ 0.8–1.2 GB → **≈ 8.7–9.1 GB steady**. Gate: `nvidia-smi` used ≤ **9.5 GB** after 20 turns; slope over 100 turns ≤ 20 MB/turn. |
| B2 | "Ceiling: 9.5GB VRAM" | [`03 L38`](03_enterprise_hardware_topology_and_ipc_spec.md:38) | Coincidentally matches B1 canonical, but derived for vLLM FP8. | Keep 9.5 GB as gate; re-derive rationale for llama-server. |
| B3 | `assert max_vram <= 9800` | [`04 L113`](04_deep_mechanical_testing_and_verification_matrix.md:113) | Written for vLLM preallocation; vLLM would always show ~utilization × 16 GB regardless. | **FIX:** 9500 MB, measured via `nvidia-smi --query-gpu=memory.used`, MSHybrid mode asserted first (D-05). |
| B4 | `--gpu-memory-utilization 0.62` → 10.15 GB | [`03 L89`](03_enterprise_hardware_topology_and_ipc_spec.md:89) | vLLM-specific; retired. | **FIX:** delete vLLM launch block; replace with llama-server launch (ADR-001). |
| B5 | Q6_K = "6.4 GB", encoder "1.6 GB" | [`01 L74-75`](01_recursive_architecture_audit_and_flaw_analysis.md:74) | Published GGUF is ~6.6 GB; mmproj Q8_0 is 0.74 GB / f16 1.27 GB. | **C:** 6.6 GB + 0.74 GB. |
| B6 | "fits in ~9GB VRAM in FP8" | [`02 L25`](02_systems_research_prior_art_and_alternatives.md:25) | FP8 keeps embeddings/lm_head 16-bit → ~10.5 GB weights. Moot (vLLM retired). | **FIX:** annotate row as retired path. |

## C. Host RAM / WSL2

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| C1 | `memory=4608MB` | [`03 L65`](03_enterprise_hardware_topology_and_ipc_spec.md:65) | Other docs say 4.5 GB / 5 GB / 4 GB informally. | **C:** `memory=4608MB`. All prose says "4.5 GB (4608 MB)". |
| C2 | `swap=2048MB` | [`03 L71`](03_enterprise_hardware_topology_and_ipc_spec.md:71) | Swap inside a clamped VM causes disk thrash exactly when latency matters; the only tenant is now the sandbox. | **C:** `swap=0`. Sandbox OOM → container killed → recreated (fail-fast, already a tested path). |
| C3 | `pageReporting=false` "to prevent sudden memory spikes" | [`03 L73-74`](03_enterprise_hardware_topology_and_ipc_spec.md:73) | Prevents Windows from reclaiming guest memory (research 7.2, grade A); contradicts `autoMemoryReclaim=gradual`. | **C:** `pageReporting=true`, `autoMemoryReclaim=gradual`, `sparseVhd=true`. **FIX** doc 03 + `scripts/setup_wslconfig.ps1`. |
| C4 | vLLM 2.5 GB inside WSL2 + Docker sandbox 1.5 GB + Chromium | [`01 L41-42`](01_recursive_architecture_audit_and_flaw_analysis.md:41), [`03 L187`](03_enterprise_hardware_topology_and_ipc_spec.md:187) | Sums to > clamp; never reconciled. | **C:** inference leaves WSL2 (D-01/D-04). WSL2 tenants: dockerd + one sandbox ≤ 1.5 GB (Chromium off by default, D-12). |
| C5 | Host RAM table omits Whisper, embedding model, OpenVINO runtime | review doc L66-70 | Missing 1.5–2.5 GB. | **C:** canonical table in spec 11 §RAM. Target steady-state host total ≤ 12.5 GB of 16 GB; alarm at 13.5 GB. |
| C6 | Windows idle "4.2–5.1 GB" | [`01 L28`](01_recursive_architecture_audit_and_flaw_analysis.md:28) | Reasonable; keep. | **C:** budget 4.5 GB for OS + shell. |

## D. Model format / engine

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| D1 | "Ultravox 8B Q6 via vLLM" | [`00 L82`](00_original_build_brief.md:82), [`01 L52`](01_recursive_architecture_audit_and_flaw_analysis.md:52) | vLLM cannot load multimodal GGUF (research 2.1, grade A). | **C:** `llama-server` on Windows, Q6_K + mmproj (ADR-001). |
| D2 | "NVFP8 / Q6_K GGUF" as if interchangeable | [`03 L38`](03_enterprise_hardware_topology_and_ipc_spec.md:38), [`05 L46`](05_lucca_system_architecture_master_spec.md:46) | Two incompatible paths conflated. | **FIX:** remove NVFP8 references. |
| D3 | `--enforce-eager` recommended | [`01 L42`](01_recursive_architecture_audit_and_flaw_analysis.md:42), [`03 L92`](03_enterprise_hardware_topology_and_ipc_spec.md:92) | 25–40 % decode penalty never weighed. Moot. | **FIX:** delete with vLLM block. |
| D4 | `--max-model-len 4096` | [`03 L90`](03_enterprise_hardware_topology_and_ipc_spec.md:90) | Too small once memories + history + system prompt + audio tokens compete. | **C:** llama-server `-c 8192`, KV cache `-ctk q8_0 -ctv q8_0` (verify quality in Phase 0; fall back to f16 KV if WER of tool-call JSON rises). |
| D5 | Ultravox licence "Apache 2.0" | [`02 L25`](02_systems_research_prior_art_and_alternatives.md:25) | Backbone is Llama 3.1 Community License. | **FIX:** "Apache-2.0 (projector) + Llama 3.1 Community License (backbone)". |
| D6 | "Llama 3.1 8B / Mistral 7B" backbone | [`02 L25`](02_systems_research_prior_art_and_alternatives.md:25) | v0.5 8B GGUF is Llama-3.1-8B only. | **FIX.** |

## E. Audio

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| E1 | "Standardized to 24,000 Hz or 16,000 Hz with zero-copy linear interpolation" | [`03 L151`](03_enterprise_hardware_topology_and_ipc_spec.md:151) | Resampling is never zero-copy; linear interpolation aliases. | **C:** two independent streams: capture 16 kHz mono int16; playback 24 kHz mono int16. **No resampling.** |
| E2 | `audio_sample_rate: int = 24000` (single field) | [`config.py L25`](../src/lucca/core/config.py:25) vs `AudioPacket.sample_rate=16000` [`05 L78`](05_lucca_system_architecture_master_spec.md:78) | One field, two meanings. | **FIX:** `capture_sample_rate=16000`, `playback_sample_rate=24000`. |
| E3 | Silero VAD on NPU | [`01 L24`](01_recursive_architecture_audit_and_flaw_analysis.md:24) (rule list) vs CPU [`00 L38`](00_original_build_brief.md:38), [`03 L19`](03_enterprise_hardware_topology_and_ipc_spec.md:19) | 1.8 MB model; NPU pointless. | **C:** CPU (ONNX Runtime). Role: trim leading/trailing silence, reject empty PTT presses. |
| E4 | PTT key `caps_lock` via pynput | `config.py` / doc 03 hotkey section | Toggles OS caps state; hooks fail under elevated windows. | **C:** right-Ctrl hold-to-talk, Win32 hook, configurable (D-10). **FIX** `pyproject.toml` L20 (`pynput` → remove or keep only as fallback). |
| E5 | MMCSS via `AvSetMmThreadCharacteristicsW` | doc 03 §4.2 | PortAudio WASAPI already applies MMCSS Pro Audio to its callback thread. | **C:** not required; document as no-op unless a custom thread is used. |

## F. Sandbox / network

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| F1 | iptables ruleset A: `-I … REJECT` ×4 then `-I … ACCEPT 80,443` and `ACCEPT udp 53` | [`03 L203-210`](03_enterprise_hardware_topology_and_ipc_spec.md:203) | `-I` prepends → **ACCEPTs evaluated first** → container reaches `192.168.1.1:443` and any LAN DNS. No final DROP → port 22 etc. to internet open. `172.28.0.0/16` ⊂ `172.16.0.0/12`. | **C:** ruleset in spec 09 §Egress: `-A` order; ACCEPT established; ACCEPT DNS **only** to Docker embedded resolver; REJECT RFC1918 + link-local + CGNAT + multicast; ACCEPT tcp 80/443 to remainder; final `DROP`; IPv6 disabled on the network; rules re-applied at WSL start. |
| F2 | iptables ruleset B: `-I DOCKER-USER -i br-lucca -d … -j DROP` ×4, DNS only to 1.1.1.1 | [`01 L125-130`](01_recursive_architecture_audit_and_flaw_analysis.md:125) | Two different rulesets in two docs (REJECT vs DROP; `-s` vs `-i`; DNS policy differs). Same `-I` ordering bug. | Superseded by F1 canonical. **FIX** both docs to point at spec 09. |
| F3 | Egress test = `curl --connect-timeout 2` fails | doc 04 sandbox suite | Vacuous: unreachable host fails identically. | **C:** positive control required (listener on LAN IP reachable from WSL2, blocked from container) — testing matrix v2. |
| F4 | `--pids-limit=64` | [`03 L189`](03_enterprise_hardware_topology_and_ipc_spec.md:189) | Counts threads; Chromium needs 100s. | **C:** 256 for default sandbox (no Chromium); 1024 for on-demand web-sandbox. |
| F5 | `--tmpfs /tmp:…,noexec,size=64m` + `--read-only` + Playwright | [`03 L190`](03_enterprise_hardware_topology_and_ipc_spec.md:190) | Chromium needs writable `/dev/shm`, home, larger tmp. | **C:** Chromium moved to separate on-demand container (D-12, ADR-004). |
| F6 | Docker Desktop vs Docker CE unspecified | doc 03 Domain C | Desktop ignores Ubuntu iptables (research 7.4). | **C:** Docker CE inside Ubuntu WSL2 (D-03). |
| F7 | GPU-PV passthrough into sandbox | [`00`](00_original_build_brief.md) architecture overview | Tools need no GPU; exposes dGPU. | **C:** no `--gpus` on any sandbox container. |
| F8 | Ephemeral workspace as bind mount | doc 03 mount, doc 04 `hard_kill_and_recreate` test | Bind mounts persist across restarts → test would fail. | **C:** host orchestrator wipes `C:\ProjectLucca\workspace` at task close (D-08). |
| F9 | Workspace = user's Downloads | [`00`](00_original_build_brief.md) "downloads summary" example | OneDrive-redirected folders; user rejected. | **C:** `C:\ProjectLucca\workspace` only; `inbox\` for hand-offs (D-08). |

## G. Memory / storage

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| G1 | ChromaDB + rank-bm25 + networkx pickle | [`00 L99`](00_original_build_brief.md:99), [`05`](05_lucca_system_architecture_master_spec.md), [`pyproject L16-18`](../pyproject.toml:16) | RAM overhead, SQLite locking ([`01 L153-154`](01_recursive_architecture_audit_and_flaw_analysis.md:153)), telemetry, first-run download, pickle RCE ([`01 L148`](01_recursive_architecture_audit_and_flaw_analysis.md:148)), IDF degeneracy ([`01 L152`](01_recursive_architecture_audit_and_flaw_analysis.md:152)). | **C:** SQLite WAL + FTS5 + sqlite-vec (D-06, ADR-002). **FIX** pyproject. |
| G2 | Embedding model unspecified in 05; `bge-small`/`MiniLM` only in review doc L196 | — | — | **C:** `all-MiniLM-L6-v2` (384-d) OpenVINO IR, NPU static seq 128, CPU fallback. |
| G3 | README: doc 01 contains "k ≤ 2 raw audio turns" compaction strategy | `README.md` | Not present in doc 01. | **C:** current turn audio only; prior user turns as Whisper text (research 3.6). **FIX** README. |
| G4 | `Dict[str, Any]` in schemas | [`schemas.py L48,84,93`](../src/lucca/core/schemas.py:48), [`05 L113,152,161`](05_lucca_system_architecture_master_spec.md:113) | Violates AGENTS.md zero-`Any`. | **FIX:** `dict[str, JsonValue]` (pydantic) or typed sub-models. |
| G5 | `DecisionRecord` dataclass vs Pydantic; `embedding` field | doc 03 vs 05 vs code | Inconsistent. | **C:** single Pydantic model (spec 06); embeddings in `vec_decisions` table, never inline. |

## H. Rules / router / code-vs-doc drift

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| H1 | Four rule DSLs (`rule`/`call-tool`/`emit-speech`, `cond`/`matches?`, `intent-matches`/`user-authorized`, `$1.head`) | docs 01, 02, 05 examples | None parse in `micro_scheme.py`. | **C:** one grammar in spec 05. |
| H2 | Distinctness "Δt ≥ 15 min OR cosine ≥ 0.25 AND state hash" vs three ORs | doc 01 vs doc 03 | Precedence undefined. | **C:** spec 05 §Distinctness (deterministic `cluster_id`). |
| H3 | `register_quarantine_rule(candidate_rule)` | [`04 L211`](04_deep_mechanical_testing_and_verification_matrix.md:211) vs [`promotion_gate.py L24`](../src/lucca/reasoning/promotion_gate.py:24) `(rule_id, s_expression)` | Test ≠ code. | **C:** API in spec 05; regenerate doc 04 tests. |
| H4 | `quantile_threshold=0.82` hard-coded; conftest uses `0.80` | [`conformal_guard.py L10`](../src/lucca/router/conformal_guard.py:10), [`conftest.py L32`](../tests/conftest.py:32) | Not conformal; two different magic numbers. | **C:** `fit()` computes q̂ from calibration set (spec 06). |
| H5 | `verify_regression_suite` returns `True` | [`promotion_gate.py L68`](../src/lucca/reasoning/promotion_gate.py:68) | Vacuous gate. | **FIX** per spec 05. |
| H6 | `List[Dict[str, Any]]` with `Any` unimported | [`promotion_gate.py L22`](../src/lucca/reasoning/promotion_gate.py:22) | `NameError` at instantiation. | **FIX.** |
| H7 | Acceptance "≥100 real logged decisions" for Phase 4; classifier gates in Phase 6 | doc 00 phases | Statistically insufficient for conformal/ECE claims. | **C:** Phase 6 needs ≥ 600 labelled decisions, ≥ 30/class (spec 06). Phase 4 keeps 100 as a *pipeline* gate only. |

## I. Repository hygiene

| # | Claim | Location | Problem | Canonical |
|---|---|---|---|---|
| I1 | `.vscode/settings.json`, `tasks.json`, `launch.json` | README §3 | Files **exist** (verified 2026-09-17); their contents were not audited against the README's description (tasks referencing vLLM/Chroma would now be stale). | **FIX:** audit the three files in Phase 1 skeleton work; align tasks with `lucca-admin` / new test tiers. |
| I2 | `python -m lucca.main` | `.agents/skills/lucca-pipeline/SKILL.md` | Module absent. | **FIX:** create `src/lucca/main.py` entry point (spec 11) or update SKILL. |
| I3 | `brain/`, `senses/`, `ui/` without `__init__.py` | `src/lucca/` | Not packages. | **FIX.** |
| I4 | Dependencies missing (`httpx`, `pydantic-settings`, `kokoro-onnx`, `openvino`, `openvino-genai`, `sqlite-vec`, `docker`, `pyzmq`, `PyQt6`, `lightgbm`, `scikit-learn`, `hypothesis`, `pytest-timeout`, `import-linter`); present but retired (`chromadb`, `rank-bm25`, `vllm` refs, `pynput`) | `pyproject.toml` | — | **FIX** per spec 11 §Dependencies. Generate `uv.lock`. |

---

## Canonical numbers — single source of truth

| Quantity | Value | Origin |
|---|---|---|
| Latency: median target / median gate / p95 gate | 475 / 600 / 800 ms | A1 |
| VRAM steady-state gate | ≤ 9.5 GB; slope ≤ 20 MB/turn over 100 turns | B1 |
| dGPU baseline before launch (MSHybrid) | < 300 MB | D-05 |
| WSL2 clamp | 4608 MB, 4 CPUs, swap 0, pageReporting on, reclaim gradual, nat | C1–C3 |
| Host RAM steady-state | ≤ 12.5 GB total; alarm 13.5 GB | C5 |
| LLM context | 8192 tokens; KV q8_0 (verify) | D4 |
| Capture / playback sample rate | 16 kHz / 24 kHz, int16 mono, no resampling | E1 |
| PTT | right-Ctrl hold; 29.5 s auto-release | D-10 |
| TTS first-chunk gate | ≤ 180 ms for ≤ 1.5 s clause | A6 |
| Sandbox container | ≤ 1536 MB RAM, 2 CPUs, pids 256, read-only root, cap-drop ALL, no GPU | F4–F7 |
| Phase 6 data floor | ≥ 600 labelled decisions, ≥ 30 per class | H7 |
