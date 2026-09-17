# HANDOVER — Critical Architecture Review (Interrupted Session)

**Date:** 2026-09-17
**Status:** Analysis phase ~complete; **zero deliverable documents written yet**. Previous instance was terminated by repeated provider/API errors mid-review.
**Purpose of this file:** Allow a fresh instance to resume without re-deriving findings. Everything below was derived from reading `docs/00`–`05`, `README.md`, `pyproject.toml`, `.agents/skills/lucca-pipeline/SKILL.md`, and the scaffold code under `src/lucca/`.

---

## 0. Original Task (reconstructed)

User asked for a **critical, recursive review** of the plan and architecture docs for Project Lucca:

1. Go line-by-line through the plan/architecture for gaps, unstated assumptions, contradictions, unanswered questions.
2. Recursively re-check the review's own answers.
3. Document findings as you go; re-review those documents.
4. Produce **extensive developer documentation** with concrete metrics and testing thresholds a weaker implementer model can follow mechanically.
5. Research related systems / alternative approaches (GitHub survey of comparable projects was explicitly requested and is **missing** from `docs/02`).
6. Ensure everything stays modular and enterprise-grade.
7. Final handoff pass.

User instruction: **review thoroughly on your own before returning; minimal clarifying questions**. Unresolved items → document as open questions with reasonable default assumptions rather than block. One tight round of clarifying questions on decisions that genuinely fork the architecture is acceptable (see §7).

Mode note: the review was being done in Architect mode (markdown-only edits). All deliverables are `.md` so this is not a constraint. Current instance is in Code mode.

---

## 1. Operating Guidance for the New Instance

- **Write incrementally.** The prior instance held ~all findings in reasoning and lost them to API failures. Write each deliverable section to disk as soon as it is drafted. Prefer several medium files over one giant file.
- **Do not re-read every doc first.** Skim to verify specific line references when editing; the findings below are the baseline.
- Respect `AGENTS.md` hard invariants (provenance gate, hardware budget, phased build, N≥5 promotion, Pydantic v2 + zero `Any`).
- Hardware: MSI Vector 16 HX AI — 16 GB RAM, Core Ultra 9 275HX (24 cores, Intel NPU **Windows-only**), RTX 5080 16 GB (Blackwell `sm_120`). WSL2 clamped to 4.5 GB.

---

## 2. Cross-Document Contradictions (must be reconciled in one canonical table)

| Topic | Conflicting values | Where | Resolution proposal |
|---|---|---|---|
| Latency target (PTT release → first audio) | 300–600 ms; ≤380 ms; "sub-400 ms"; 780 ms budget | brief, 01, 04, README, test assertions | Define one **per-stage trace budget** (see §14) summing to ~475 ms target, 600 ms hard ceiling. |
| Test assertion `300 <= median <= 600` | Lower bound fails a *faster* system | 04 suite 1 | Change to `median <= 600` (+ p95 bound). |
| VRAM ceiling | <~8 GB (brief); 9.5 GB (01); 9.8 GB (04); 10.15–10.9 GB derived from `gpu-memory-utilization` (03) | all | Recompute per chosen engine (§3). vLLM **preallocates** to utilization fraction, so any test checking "<9.8 GB used" fails by construction. |
| WSL2 memory clamp | 4608 MB / 5 GB / 4 GB | `.wslconfig` refs in 01, 03, brief | Pick 4608 MB and reference one file. |
| `.wslconfig` `pageReporting=false` + `autoMemoryReclaim=gradual` | Contradictory: pageReporting=false prevents returning memory to host | 03 | Remove `pageReporting=false` or document why VM memory is pinned. |
| Kokoro speed | 35 ms per 1 s audio (02) vs ~92 ms (01) | 01, 02 | Both unsourced. Replace with measured RTF from Phase 0 spike. |
| TTFT | Differs between 01 and 02 | 01, 02 | Measure; don't assert. |
| Whisper encoder in Ultravox v0.5 | Sizes inconsistent | 01, 02, 03 | It is `whisper-large-v3-turbo` encoder, ~637 M params ≈ 1.27 GB FP16. |
| Host RAM budget | 8.4–11.6 GB (review) omits Whisper, embedding model, ModernBERT, OpenVINO runtime | 01/03 | Rebuild table; realistic total ≈ 12–12.5 GB on a 16 GB host. Tight but feasible. |
| Ultravox licence | "Apache 2.0" | 02 | Ultravox projector code is Apache-2.0; **Llama 3.1 backbone is Llama Community License**. Fix. |
| README claims doc 01 contains multi-turn audio compaction (k≤2 raw audio turns) | Content is **not in doc 01** | README | Write the strategy (§8) and fix the reference. |
| README references `.vscode/`, `lucca.main` | Neither exists | README, SKILL.md | Create or remove references. |
| `DecisionRecord` | dataclass in one doc, Pydantic in another; one has an `embedding` field removed in code | 03 vs 05 vs code | Single Pydantic model; embeddings go in a separate vector table, never inline. |
| Silero VAD device | CPU (brief) vs NPU (rule in 01) | brief, 01 | CPU. 1.8 MB model; NPU is pointless. Document VAD's role = trim leading/trailing silence + reject empty PTT presses. |
| doc 04 test method names | Don't match actual code API (e.g. `register_quarantine_rule(candidate_rule)`) | 04 vs `promotion_gate.py` | Regenerate 04 tests from the real API after the API is fixed. |

---

## 3. DECISION 1 (highest consequence): Inference Engine & Model Format

The docs conflate two **incompatible** paths:

**Path A — vLLM in WSL2 (as drafted)**
- vLLM GGUF support is architecture-limited; the Ultravox projector + Whisper encoder almost certainly **cannot load from GGUF**. The brief's "Q6 GGUF via vLLM" is unvalidated and probably impossible.
- Realistic vLLM options: BF16 (~16 GB — doesn't fit), **FP8 dynamic** (Blackwell consumer `sm_120` FP8 kernel support was shaky in early vLLM releases — many kernels target `sm_100`; verify), INT4 AWQ/GPTQ (compatibility with Ultravox unknown).
- FP8 sizing: embeddings + `lm_head` stay FP16 → ~8 GB backbone + ~1.3 GB encoder + projector ≈ **10.5–10.7 GB weights**, not 8 GB. Realistic `gpu-memory-utilization` ≈ 0.80 (13.1 GB) to leave KV room, not 0.62.
- `--enforce-eager` disables CUDA graphs → ~30–40 % slower decode (expect ~70–80 tok/s not 100–120). Docs recommend it to save host RAM without analysing the trade-off. Recommend keeping CUDA graphs on.
- KV cache: Llama-3.1-8B, 8192 tokens ≈ 1.07 GB FP16, ~0.54 GB with `--kv-cache-dtype fp8` (flag currently missing from launch plan). Recommend `max-model-len 8192` + fp8 KV.
- Requires WSL2 RAM (~2.5 GB for vLLM process) inside the 4.5 GB clamp — see §9 for why this collides with the sandbox.
- MUX switch open question: if laptop is in discrete-GPU mode, Windows desktop consumes ~0.5–1 GB VRAM on the dGPU; hybrid mode leaves it free. **Ask user / document.**

**Path B — llama.cpp (`llama-server`) natively on Windows, Q6_K GGUF**
- llama.cpp's `mtmd` branch reportedly added Ultravox support (~May 2025) — **UNVERIFIED, must confirm**. If true, this matches the brief's Q6 GGUF request exactly.
- Eliminates WSL2 from the inference path → frees the entire WSL2 RAM budget for the sandbox; avoids vLLM-on-Blackwell build risk.
- Loses vLLM's guided decoding/prefix caching maturity (llama.cpp has GBNF grammars, which are adequate for §17).

**Path C — Cascade fallback (Whisper-turbo on NPU + Llama-3.1-8B via llama.cpp + Kokoro)**
- `docs/02` dismisses cascade at 700–1200 ms; that estimate is outdated. Streaming faster-whisper can give partials during speech; post-PTT ASR ≈ 100–200 ms; total plausibly 350–500 ms.
- Yields transcripts **for free** (solves §4 and §5 problems), fits VRAM comfortably, no WSL2 dependency.
- Costs ~150–300 ms vs Ultravox best-case.

**Recommendation:** Phase 0 **bake-off spike** (time-boxed) measuring TTFT, tok/s, VRAM, host RAM for A vs B, with C as documented hedge. Ports abstraction (`SpeechLLMPort`) so the choice is swappable. Write as ADR-001 with all three options. Present to user as the one genuine fork.

---

## 4. Whisper / ASR Is on the Critical Path (unacknowledged)

- Ultravox consumes audio directly and **produces no transcript**. Yet: the heuristic router needs text; `USER_EXPLICIT` memory needs text; multi-turn history needs text. Docs treat Whisper as a "background logging pass" — impossible if the router or memory gate depends on it.
- Whisper is **absent** from: RAM budget table, topology diagram, phase plan, test matrix. Footprint ≈ 0.8–1.6 GB depending on precision.
- Options for router-transcript gap: (a) route on Whisper transcript (puts ASR latency on the critical path); (b) Ultravox self-routes via tool calls; (c) **speculative dispatch** — send audio to Ultravox immediately, run ASR + router in parallel, abort the LLM request (vLLM supports abort) if a rule fires. (c) only wins if ASR completes before LLM TTFT — unknown; measure.
- Whisper on NPU: encoder is static-shape (30 s padded mel) → NPU-friendly, but every clip is encoded as a full 30 s window (~1 s latency). Decoder is autoregressive/dynamic → needs stateful decoding support. `large-v3-turbo` ≈ 809 M params, heavy compile time. Consider `distil-whisper-small` on CPU (~150 ms) for the critical-path transcript and large-v3-turbo offline for logging.
- Ultravox's 30 s audio window (Whisper encoder) caps PTT duration → need auto-release/segmentation at 30 s.
- USER_EXPLICIT text must come from an **independent ASR**, not Ultravox's own restatement (that is LLM narration). Store audio hash + ASR confidence; low-confidence (avg logprob below threshold) → distinct `USER_EXPLICIT_LOWCONF` label or require confirmation.

---

## 5. Provenance Gate — Findings

Code: `src/lucca/core/provenance_gate.py` (or equivalent) + `schemas.py`.

1. **HMAC is security theatre in-process.** Same object signs and verifies; any code reaching `create_verified_payload` can assert any provenance. Docs' "mathematically prevents"/"cryptographically signed" claims are overstated. The real threat is *developer error* routing LLM text into a trusted path — HMAC does nothing for that.
2. **Fix: capability-object pattern.** Dedicated signers (`UserSpeechSigner`, `ToolResultSigner`, `LispAssertionSigner`), each owned by exactly one module, each restricted to one provenance type; keys derived via HKDF with the provenance label; gate verifies against the key for the *claimed* provenance. The LLM client owns **no** signer and returns a distinct `LLMNarration` type that is not convertible to a commit payload. Enforce with `import-linter` (block `lucca.brain` from importing the signer module) + an AST test that only ASR and sandbox-client modules import the payload factory.
3. Signature does **not cover** `entry_id`, `entities`, `confidence` → post-signing tampering of graph edges/confidence. Sign canonical JSON of all fields except the signature.
4. Signing string is colon-joined → canonicalization ambiguity if content contains `:`. Use canonical JSON or length-prefixing.
5. No replay/freshness check; a year-old signed payload validates. Add max-age. `entry_id` derived from timestamp lets duplicates slip; derive from content hash + source.
6. Default key `"insecure_dev_key"` → app must **fail closed** outside dev mode. Use `pydantic-settings` (not yet implemented).
7. Storage is in-memory only, no persistence/Chroma/graph integration — acceptable scaffold, must be labelled as such.
8. **Central unresolved semantic question:** what is written as USER_EXPLICIT? Verbatim transcript (fillers included) vs extracted facts. Extracting "my sister is Maya" into a triple is **LLM output**. Resolution — two-tier provenance:
   - `USER_EXPLICIT`: verbatim transcript spans (hybrid search retrieves them).
   - `USER_DERIVED`: LLM-extracted triples that **must** reference `source_entry_id` and pass a **quote-grounding check** — every entity/value string appears verbatim (or fuzzy ≥ threshold) in the source transcript. Lower trust weight.
9. `TOOL_VERIFIED` currently conflates "tool ran" with "content trustworthy". Web page text carrying indirect prompt injection would become "verified" memory. Split: `TOOL_VERIFIED` = structural facts (exit code, existence, size, hash); `TOOL_CONTENT_UNTRUSTED` = bodies/page text, memory-eligible only after quarantine or user confirmation.
10. Sandbox container must **never** hold a signing key; host-side client signs after validating the response.
11. The hallucination-write test in 04 is trivial (enum raises). Real test: end-to-end with mocked LLM emitting confident false narration + tool call; assert zero memory rows written. Working-memory discard test passes vacuously — add positive control.

---

## 6. Memory Subsystem

- **ADR-002 recommendation:** replace ChromaDB + `rank-bm25` + pickled networkx with **SQLite (WAL) + FTS5 (BM25) + `sqlite-vec`** (or numpy brute-force cosine — <5 ms at <50 k rows). One file, one lock model, one transaction boundary across vectors/FTS/graph/provenance/decision logs. Fixes: Chroma RAM overhead (onnxruntime + tokenizers), Chroma's SQLite locking issues, posthog telemetry (violates local-first unless disabled), 80 MB default-embedding download on first run (violates offline-first), and rank-bm25 IDF degeneracy on small corpora. networkx stays as an in-memory view only. Keep Chroma as documented alternative behind a `VectorStorePort`. Note FTS5 `bm25()` is negative-is-better.
- Embedding model unspecified in master spec; only 01 mentions `bge-small-en-v1.5` (384-d) / `all-MiniLM-L6-v2`. Recommend MiniLM/bge-small via ONNX Runtime CPU (fast enough; NPU static-shape padding to 128 tokens possible later). Missing from RAM budget.
- Hit@1 = 1.00 on 30 literal-identifier queries is brittle; requires tokenizer emitting whole tokens **and** sub-tokens split on `_ . -` (so `ERR_403_INVALID_TOKEN`, `file.txt` match). Relax to Hit@1 ≥ 0.93 (28/30) and MRR ≥ cosine-only + 0.20, on a **frozen** benchmark file.
- 20-fact paraphrase recall test has no threshold: set Recall@3 ≥ 0.90, Precision@1 ≥ 0.85, frozen fact set.
- Entity resolution undefined ("Maya" / "my sister" / "maya").
- **Contradiction handling missing**: bi-temporal facts (`valid_from`, `valid_to`, `recorded_at`), functional predicates (`lives_in`, `works_at`) superseded latest-wins with history preserved. Explicit user deletion ("forget that").
- Retrieval injection budget: how many memories fit in context alongside audio tokens/system prompt/history — define token budget per section at `max-model-len 8192`.
- `WorkingMemory.intermediate_tool_outputs` and `active_state: Dict[str, Any]` violate zero-`Any`. Use pydantic `JsonValue` for genuinely dynamic fields.
- Graph edges carry `source_entry_id` for traceability.
- Schema versioning/migrations and backup strategy for the persistent memory volume are unspecified.

---

## 7. MicroScheme Interpreter (`src/lucca/.../micro_scheme.py`) — Bugs

1. **Tokenizer splits on whitespace only** → quoted strings with spaces shatter into malformed symbols → `NameError`. Doc 02's own sample rule (quoted log message, `;;` comment) cannot parse. Needs regex lexer with strings/escapes/comments.
2. `and`/`or` are functions → eager evaluation, no short-circuit. Make special forms.
3. `define` mutates the shared global env → rules leak state, can redefine `+`. Evaluate each rule in a fresh child env; freeze globals.
4. `if` assumes exactly 3 parts → raw `ValueError` on 2-arm form.
5. Raw Python exceptions leak: `ZeroDivisionError`, `TypeError` (str vs int compare, `+` on str), `IndexError` on empty list, `KeyError`, calling non-callable, `NameError` from `find`. Wrap into `SchemeRuntimeError(rule_id, position)`.
6. **Memory bombs**: `(* "a" 10**9)`, `(expt 2 (expt 2 100))`, list concat. Gas counts steps not size. Add: numeric-only arithmetic, int magnitude cap, float finiteness, string/list length caps, wall-clock timeout.
7. Deep nesting blows Python recursion before gas → max nesting depth + max token count on the parser. Parser pop-from-front is O(n²).
8. No `lambda`/recursion → loops impossible today → gas only matters once lambdas are added. Document.
9. Primitives referenced in docs but absent: `cond`, `matches?`, `call-tool`, `emit-speech`, `log`, `intent-matches`, `user-authorized`, `dict`, `$1.head`. Four **inconsistent DSLs** across docs. Define **one canonical rule schema**.
10. **Architectural fix:** rules are pure functions `State → Plan`. Condition = pure gas-metered bool; action = returns a data-only `Plan` (list of `ToolCall` descriptors). The **orchestrator** executes plans. Shadow mode = diff planned `Plan` vs the LLM path's actually-executed actions (structural match on tool name + args). This definition is currently undocumented.
11. `matches?` with regex from LLM-generated rules → ReDoS. Restrict to glob/literal/keyword or bound pattern complexity + timeout.
12. Rule versioning + S-expression pretty-printer needed for the "human-readable diff of what was compiled" requirement.
13. State schema exposed to rules (intent label, entities, transcript keywords, time bucket, active app, recent tool outcomes) must be defined so legal symbols are bounded.

---

## 8. Promotion Gate (`promotion_gate.py`) — Bugs & Gaps

1. `List[Dict[str, Any]]` annotation on `self._historical_regression_cases` with `Any` **not imported** → `NameError` at instantiation (PEP 526 evaluates annotations on attribute targets). **Proves the module was never executed.**
2. `verify_regression_suite` returns `True` unconditionally → vacuous "100 % regression". Define regression case = `(state_snapshot, expected_plan)` pairs drawn from each promoted rule's ≥5 successes; replay on every rule change.
3. One shadow failure → `failure_count` > 0 forever → zombie candidate that can never promote but keeps accumulating. A mismatch may be the **LLM path's** fault, not the rule's.
4. **Lifecycle state machine** needed: `PROPOSED → QUARANTINE → ACTIVE → DEMOTED → (QUARANTINE with counters reset, `demotion_count`+1) → RETIRED after 2 demotions`. User-cancelled interactions don't count as failures.
5. `is_active` builds a dummy `CandidateRule(rule_id="")` — sloppy; handle missing explicitly.
6. **Distinctness definition ambiguous** (doc 01: "Δt ≥ 15 min OR cosine ≥ 0.25 AND state hash"; doc 03: three ORs). Proposed deterministic definition: `cluster_id = hash(session_id, 15-min time bucket, semantic_cluster)` where semantic clusters come from agglomerative clustering at distance threshold 0.25; two cases are distinct iff `cluster_id` differs. Alternative: new case is distinct iff for every existing case Δt ≥ 15 min AND (cosine dist ≥ 0.25 OR state hash differs). Pick one, write the test.
7. No persistence: `quarantine_rules.json` / `active_rules.lisp` referenced in docs, never implemented. Use SQLite tables (§6).
8. Rule conflict resolution undefined when two active rules match: propose most-specific → first-promoted → fall back to LLM.
9. **Risk policy for rule actions**: tool risk levels `READ / WRITE / LAUNCH`; rules may auto-execute READ; WRITE/LAUNCH always require user confirmation (voice confirm UX is undesigned — TTS prompt + PTT yes/no via ASR).

---

## 9. Router, Classifier, Conformal Guard

- `ConformalPredictionGuard` hard-codes `quantile_threshold=0.82`, no `calibrate()`; stored `alpha` unused → **not conformal prediction**, static thresholding. With 0.82, any class with p ≥ 0.18 enters the set → 3-class problem almost always yields ≥ 2 classes → SAFE_FALLBACK nearly always; contradicts "avg set size ≤ 1.15". Implement `fit(cal_scores, cal_labels)` computing q̂ at `⌈(n+1)(1−α)⌉/n`.
- Exchangeability violated by temporal drift → sliding-window recalibration.
- **Data volume**: 100–300 decisions with 60/20/20 split → 20 cal points → q̂ = max → sets = everything. α = 0.05 needs ≥ 19 cal points to be defined, ~100 to be stable. Propose Phase 6 gate: **≥ 600 labelled decisions (400/100/100), ≥ 30 per class**, else blocked.
- ECE ≤ 0.045 with 10 bins on 60–100 test points → ±0.1 noise → unverifiable. Use fewer bins, bootstrap CI, or scale N.
- "+2 % accuracy over heuristic" on 100 samples = 2 samples = noise. Use McNemar's test or bootstrap CI; metric should be **macro-F1 / balanced accuracy** (majority baseline ~75 %).
- **Labeling protocol entirely unspecified.** Proposal: negative if user interrupts within 1.5 s of playback start, next-turn explicit negation ("no", "that's wrong"), or nonzero tool exit; otherwise positive after next turn or 60 s idle. Counterfactual: log cheap shadow evaluation of the other branches (would any LISP rule have matched?).
- Heuristic router uses substring matching (`"run"` hits "running"/"brunch"; `"start "` hits "start with"). Use word-boundary regex + intent lexicon + adversarial tests.
- Design question: since checking active-rule conditions is <1 ms, **always check LISP first**; router's real job is LLM vs direct-tool vs clarify. Router→LISP interface is otherwise undefined ("intent strings" have no producer in a LISP-first ordering). Resolve: rules match on regex/keyword + deterministic state predicates; embedding matching deferred.
- `log_path` defined but never used → decisions vanish on exit; breaks Phase 4 persistence requirement.
- `DecisionRecord` needs: tool used, outcome, user corrections, session id, LLM tool-calls, `user_interrupted`, timing trace.
- SetFit / Rasa DIET are better small-N options than frozen BERT + XGBoost; ModernBERT (RoPE, flash-attn) on NPU is uncertain — DistilBERT/MiniLM with fixed seq len is realistic. Tree models stay on CPU (invariant).

---

## 10. Sandbox / Docker

1. **Memory infeasible as specified**: vLLM 2.5 GB + sandbox 1.5 GB + Docker/kernel 0.5 GB = 4.5 GB = the entire clamp, before Playwright/Chromium. Will thrash. Fix: drop Chromium as default → `httpx` + `trafilatura`/readability (~50 MB), spawn Chromium on demand only for JS-heavy pages and kill after; cap sandbox at 768 MB. Or move inference out of WSL2 (Path B).
2. **Docker Desktop vs Docker CE**: Desktop runs its own `docker-desktop` distro; `.wslconfig` limit is global across distros; Desktop resets iptables and DOCKER-USER rules in Ubuntu don't apply. **Decide: Docker CE installed inside Ubuntu WSL2.** Also avoids Desktop RAM overhead + licensing.
3. **iptables ordering bug (doc 03)**: rules added with `-I` end up **reversed** → ACCEPT 80/443 and DNS 53 evaluated **before** private-range REJECTs → container can reach `192.168.1.1:443` and do DNS exfiltration to LAN resolver. Fix: use `-A` in order, or reverse; add final catch-all `DROP` (currently port 22 etc. to public internet is open). Restrict DNS to Docker's embedded resolver only.
4. `172.28.0.0/16` ⊂ `172.16.0.0/12` — REJECT overlaps the container's own subnet/gateway; embedded DNS at `127.0.0.11` may not traverse FORWARD the same way — test it.
5. IPv6 not covered → disable IPv6 on the docker network + sysctl. WSL2 mirrored networking mode can open IPv6 bypass paths.
6. Rules don't survive `wsl --shutdown` → startup script / `iptables-persistent`.
7. **Egress test is vacuous**: `curl --connect-timeout 2` to a non-existent host fails identically to a blocked host. Need a **positive control**: real listener on a LAN IP, reachable from WSL2 directly, blocked from container.
8. Simpler alternative (ADR-003): `--network internal` + egress proxy container with allowlist; sandbox has no direct network.
9. **Split-container proposal (ADR-004)**: file-sandbox (workspace mounted, **no network**) and web-sandbox (network, **no files**) — closes the fetch→exfiltrate-workspace channel structurally.
10. **Drop `--gpus` / GPU-PV** from sandbox: tools don't need GPU; passthrough exposes vLLM VRAM.
11. `--pids-limit=64` counts threads; Chromium spawns 100+ → crash. Need ≥ 256–512 (moot if Chromium dropped).
12. `--read-only` + `--cap-drop=ALL` + `no-new-privileges` + 64 MB noexec tmpfs conflicts with Chromium (needs writable `/dev/shm`, home, larger tmpfs, `--no-sandbox` or userns). Document as known limitation.
13. **Ephemeral workspace is a bind mount → persists across restarts**, contradicting the `hard_kill_and_recreate` test. Use tmpfs / anonymous volume with `docker rm -v` / explicit host wipe.
14. Workspace semantics contradiction: brief's "downloads summary" example implies reading real `~/Downloads` (Windows host), but tools see only `/workspace`. Decide: dedicated `LuccaWorkspace` dir as default mount; mounting Downloads is explicit, off-by-default config. drvfs mounts into Docker → root-owned files, write failures, slow.
15. **Host↔container RPC transport undefined**. Never expose Docker Engine API over TCP. Lightweight tool server in container accepting only port-forwarded local connections (or `docker exec` with JSON stdio). Container never initiates outbound to host.
16. `--cpus=2.0` on sandbox competes with vLLM's 4 processors → jitter.
17. "Read-only web fetch" must mean GET-only, no cookies persisted, no form submission.

---

## 11. SafeFileTool

- Doc 04 tests are Windows-oriented (reserved names `nul`/`com1`, `PermissionError`) but production runs in a **Linux container**. Test expects `PermissionError`; code raises `PathTraversalException` → test fails as written. Reconcile.
- Message strings don't match test substrings ("escapes workspace sandbox"/"Access denied").
- `..%2f..%2f` not decoded → resolves to literal in-workspace filename → `FileNotFoundError` not `PermissionError`. Decision: **reject** any path containing `%`, NUL, control chars outright.
- TOCTOU symlink swap between resolve and write — single writer today, but future archive-extraction tool could plant symlinks. Mitigate with `O_NOFOLLOW` / explicit symlink checks; document as accepted risk with control.
- Missing limits: `max_read_bytes`, `max_write_bytes`, `max_list_entries`; binary detection / `errors="replace"`; overlong paths; case-insensitivity if NTFS-backed.

## 12. App Launcher

- Host-side whitelist; zero-arg vs parametrised templates with strict per-app validators; no `shell=True` (`os.startfile` / explicit `cmd /c` for `.cmd`); confirmation prompt; rate limit; define "launch" when already running (focus vs new instance).

---

## 13. Audio, PTT, TTS, NPU Feasibility

- **Sample rates**: capture 16 kHz (Ultravox/Whisper), playback 24 kHz (Kokoro). Config has one field. "Zero-copy linear interpolation resampling" is nonsense (not zero-copy; aliasing). Run two streams, no resampling. Split config into `capture_sample_rate` / `playback_sample_rate`.
- **PTT key `caps_lock` via pynput** toggles OS caps state; hooks fail under elevated/UAC/game windows. Use `right_ctrl`, `F13`, `scroll_lock`, or mouse side button; consider `keyboard` lib or Win32 `RegisterHotKey`; decide hold vs toggle; timestamp from OS key-release event, not polling.
- WASAPI shared mode (~10 ms mixer) as default; exclusive needs explicit `WasapiSettings`.
- `AvSetMmThreadCharacteristicsW` via ctypes is redundant — PortAudio WASAPI already applies MMCSS "Pro Audio" to its callback thread.
- **GIL hazard**: audio callback thread contending with JSON parsing / DB / OpenVINO in the same process → underruns regardless of MMCSS. Docs never address this. → §15 process split.
- **Kokoro on NPU is the biggest unvalidated Phase 1 risk**: StyleTTS2 + ISTFTNet have dynamic input (phoneme length) and dynamic output (duration-predictor dependent); Intel NPU plugin needs static shapes. "35 ms/s" and "~85 MB NPU SRAM" figures are unsourced. Mitigation: static-shape bucketing spike. **Fallback ladder**: NPU (bucketed) → iGPU via OpenVINO GPU plugin (dynamic shapes OK) → CPU int8 ONNX (~RTF 0.15 on 24-core Arrow Lake → ~180 ms for 1.2 s clause; within budget). Rewrite criterion: "TTS device placement measured and reported; NPU preferred; CPU/iGPU permitted with documented RTF." Keep NPU as primary but structure as **Phase 1a time-boxed decision gate** with pre-defined exit condition (honest, not a silent weakening — brief says stop and report rather than weaken).
- Mechanical NPU verification: check OpenVINO compiled-model `EXECUTION_DEVICES` property, not Task Manager.
- `NPU_COMPILATION_MODE_PARAMS` is undocumented/version-specific; minimise use.
- **Barge-in entirely unspecified**: PTT during playback must abort vLLM stream, flush TTS queue, stop playback, reset chunker. Core voice UX; add spec + tests.
- Lip-sync: Kokoro exposes no phoneme timings publicly (duration predictor has them internally). Phase 1: **RMS-envelope 3-state mouth**; phoneme→viseme deferred.

## 14. Streaming Chunker (`streaming_chunker.py`)

- Sentence regex splits on decimals (`3.14` → "three." "fourteen"), abbreviations (`Dr.`, `e.g.`), ellipses, numbered lists, URLs, filenames (`config.yaml`), Windows paths, times, colons. Needs abbreviation list + one-token lookahead buffering (split only if followed by whitespace + uppercase/quote/EOS, not a digit).
- "≥5 tokens" threshold conflates SSE deltas with words; use chars/words.
- No forced max-length split → punctuation-free sentence stalls output. Add max chunk length.
- Markdown (`**`, lists, code fences), emoji, non-ASCII quotes, numbers/units need normalisation before TTS (misaki handles some numbers).
- `flush()` resets `_is_first_chunk` but abort path doesn't → add `reset()`; check thread-safety.
- **Tool-call demux**: Llama 3.1 tool-call JSON appears in the token stream; chunker would speak it. Need a demultiplexer detecting tool-call syntax and diverting from TTS.

## 15. Multi-Turn Context

- Chat API resends audio history each turn (growing payloads, prefix cache ineffective for multimodal). Strategy: **current turn raw audio only; all prior user turns as ASR transcript text** (reuses Whisper pass). Optional k≤2 raw turns if measured cheap. `max-model-len 8192`, fp8 KV, prefix caching on for the system prompt. Single audio input per request; 30 s cap.

## 16. Process Topology, Observability, Lifecycle (all unspecified)

- Proposed 4 processes: **audio** (capture/playback/PTT, minimal deps), **core** (router, memory, LISP, inference client, tool bridge; asyncio), **NPU inference server** (OpenVINO: Kokoro/Whisper/embeddings — isolates crashes), **UI/avatar** (owns GUI thread). IPC: ZeroMQ or localhost asyncio TCP, length-prefixed Pydantic JSON; shared-memory ring buffer for audio frames. Python 3.12 has no free-threading.
- **Latency trace schema** (per turn, `trace_id`): `t_key_release, t_request_sent, t_first_token, t_first_text_chunk, t_tts_start, t_tts_done, t_first_audio_callback`. Per-stage budgets: PTT→send ≤ 15 ms; send→first token ≤ 150 ms; first token→first chunk ≤ 80 ms; TTS first chunk ≤ 180 ms; queue→speaker ≤ 50 ms → ≈ 475 ms target; regression detection per stage. Measure first **non-silent** WASAPI buffer, not first frame generated. Also test 10-consecutive-turn requirement and VRAM **slope** across turns, not just max.
- Structured JSON logging, metrics naming, telemetry in SQLite.
- Startup/shutdown: model server up → NPU compile-cache warm → health checks → degraded-mode messaging ("brain offline") → graceful stop. Failure/recovery runbook.
- Config: `pydantic-settings`, `.env`, precedence order; `LuccaConfig` hard-codes an absolute project path (portability).

## 17. Reflection Loop

- Input: `DecisionRecord`s + tool traces → LLM emits structured output `{sexpr, rationale, exemplar_record_ids}` under **constrained grammar** (vLLM `guided_grammar` EBNF via xgrammar/outlines, or llama.cpp GBNF) → parse → static validation (whitelisted primitives, registered tools, arg schemas, complexity limits) → QUARANTINE. Output is a CandidateRule, never memory.
- Triggers from doc 01 fine; add rate limit (1 per 10 min), run only when idle ≥ 60 s, abort on PTT (shares the inference engine with live voice).
- Apply-rate thresholds (e.g. 0.08) are unsourced → mark **provisional**, re-baseline after 50–200 runs. Mechanical gate: candidates generated, parse-valid rate ≥ 0.5, ≥ 1 promoted per N attempts. Add candidate-generation metric separate from gate-rejection metric.
- Promotion shows human-readable pretty-printed diff vs parent version.

## 18. Phase Plan & Human-in-the-Loop Gates

- Phase 4 "≥100 real logged decisions", Phase 5 "one rule promoted from a real repeated pattern (≥5 distinct clusters)", Phase 6 real data — all require **wall-clock human usage** an implementer model cannot produce. Weaker model will fabricate or stall.
- Mark these as **HUMAN GATES**. Implementer deliverable = code + tests on synthetic fixtures + verified data-collection pipeline. Define "real" to include **scripted replay of recorded real sessions**. Provide dogfooding protocol (e.g. 25 varied tasks × 4 sessions checklist).
- Phase 1 acceptance implicitly needs multi-turn → pulls ASR into Phase 1 scope.
- Add **Phase 0** spikes: engine bake-off (§3), Kokoro NPU feasibility (§13), FP8-on-sm_120 check.
- Vision API fallback / OCR / screenshots in the brief are unscoped → explicitly defer to Phase 7+.

## 19. Security / Threat Model (missing)

- Lightweight STRIDE threat model with trust boundaries: LLM output untrusted; tool results untrusted data; web content → prompt injection → tool calls (write/launch). Mitigations: confirmation for WRITE/LAUNCH, cap web content length, block automatic fetch→write chains, split containers (§10.9).
- Default HMAC key fail-closed; no key in container; no Docker API over TCP.
- Data retention/privacy policy for recorded audio and transcripts.

## 20. UI / Avatar

- Framework unspecified (Pygame/PyQt6/Raylib). For transparent, click-through, always-on-top 2D sprite on Windows → **PyQt6** (ADR-005), ~80 MB RAM. Separate process (§16). RMS lip-flap Phase 1.

## 21. Repo / Dependency Hygiene

- `src/lucca/brain/`, `senses/`, `ui/` empty, **no `__init__.py`** → not packages. `lucca.main` missing.
- `pyproject.toml` missing: async HTTP client (`httpx`), `pydantic-settings`, TTS (`kokoro`/`kokoro-onnx`), `openvino-tokenizers`, `docker` SDK, `lightgbm`/`scikit-learn`, IPC lib, `pytest-timeout`, `hypothesis`, `import-linter`. No `uv.lock`. `pynput`/`chromadb` questionable.
- Test infra (`conftest.py`) references fixtures and modules that do not exist → suite is non-functional beyond conftest.
- `promotion_gate.py` `Any` import bug (§8.1) proves no module has been executed. **Assume nothing in `src/` has run.**

## 22. Testing Gaps & Proposed Tiered Strategy

**Tiers (all hardware-dependent tests marked + skippable):**
- T0 static: `ruff`, strict `mypy` (zero `Any` in public interfaces), `import-linter` boundary contracts, AST test on signer/payload-factory imports.
- T1 pure unit: MicroScheme, chunker, path sanitiser, provenance gate, promotion gate, conformal `fit`, labeling function, distinctness.
- T2 fake-backed integration: scripted vLLM/llama-server stand-in (SSE stream incl. tool-call JSON), fake TTS, fake sandbox client.
- T3 real hardware: NPU placement (`EXECUTION_DEVICES`), latency trace, VRAM slope, egress positive-control, WSL2 RAM ceiling.
- T4 soak: 200-turn RAM/VRAM endurance under 4.5 GB clamp, thermal throttling measurement (tok/s and RTF over 30 min).
- `hypothesis` property tests: parser round-trip / never raises non-`SchemeError`; path sanitiser never yields path outside workspace; chunker never splits inside a number/abbreviation and never emits empty chunk.

**Missing tests to add:** barge-in; chunker edge cases; LISP parser fuzz + depth bomb + memory bomb; Whisper WER on fixed clip set (target WER ≤ 8 % clean speech); VAD trimming; SQLite concurrency/WAL locking; rule static validation; import boundaries; conformal coverage on synthetic data; labeling-function unit tests; egress positive control + IPv6; ephemeral-workspace reset; hallucination-write end-to-end (§5.11); VRAM slope; 10-consecutive-turn latency; per-stage trace budget regression; NPU device assertion.

## 23. Research Doc (`docs/02`) Gaps — Prior Art to Add

`docs/02` lacks the explicitly requested GitHub survey; citations lack URLs; one link points to a local path; conflates Kokoro TTS-Arena Elo with MOS; "Reflection Drift" undefined; cascade latency estimate outdated. **All items below are recalled from training knowledge — URLs, stars, licences MUST be verified by the implementer; provide a table with blank verification columns.**

- **Desktop/VTuber companions (near-identical prior art):** Open-LLM-VTuber, AIRI, kimjammer/neuro, Amica.
- **Voice pipelines:** Pipecat, LiveKit Agents (sentence aggregation directly relevant to chunker), Vocode, RealtimeSTT/RealtimeTTS + `stream2sentence`, RealtimeVoiceChat.
- **Speech-LLMs:** Ultravox, Moshi, Qwen2-Audio, GLM-4-Voice.
- **TTS/ASR tooling:** kokoro-onnx, Kokoro-FastAPI, faster-whisper, whisper.cpp, distil-whisper, OpenVINO GenAI Whisper-on-NPU samples, Intel NPU acceleration library.
- **Memory:** MemGPT/Letta, mem0, Zep/Graphiti (temporal KG — supersession), HippoRAG, Generative Agents (memory stream + reflection ≈ Lucca's reflection loop), CoALA; retrieval: RRF, BM25/FTS5, ColBERT; storage: sqlite-vec, LanceDB.
- **Symbolic/rule learning:** Soar/ACT-R production compilation (classic prior art for compiled shortcuts), Voyager, Reflexion, Popper/ILASP (ILP), DreamCoder, LLM+PDDL / Fast Downward, pyhop/GTPyhop; Scheme impls: Norvig `lis.py`, hissp, hy, sexpdata.
- **Routing/calibration:** RouteLLM, FrugalGPT, HybridLLM, MAPIE, `CalibratedClassifierCV`, netcal, Venn-Abers, temperature scaling; small-N intent: Rasa DIET, SetFit.
- **Sandboxing:** gVisor, Firecracker, nsjail, bubblewrap, E2B.
- **Platform notes:** WSL2 `autoMemoryReclaim`, mirrored networking + Docker iptables, vLLM cu128 wheels for Blackwell (may no longer need source build), llama.cpp `mtmd` Ultravox support (verify).

## 24. Documentation Gaps (deliverables to create)

ADRs (001 engine, 002 storage, 003 egress proxy, 004 split containers, 005 UI framework, 006 provenance tiers, 007 rules-as-plans, 008 process topology); glossary; threat model; failure/recovery runbook; observability spec (log schema, trace schema, metrics); data retention/privacy; config precedence; error taxonomy; DB schema versioning/migrations; backup strategy; canonical rule DSL grammar; state schema for rules; labeling protocol; lifecycle state machine; dogfooding protocol; port interfaces (`SpeechLLMPort`, `STTPort`, `TTSPort`, `EmbeddingPort`, `VectorStorePort`, `SandboxPort`, `LauncherPort`); Phase 0 spike specs with exit criteria.

## 25. Open Decisions for the User (single clarifying round — ranked)

1. **Engine path** (§3): vLLM/WSL2 FP8 vs llama.cpp/Windows Q6_K vs cascade — or approve Phase 0 bake-off with cascade as hedge. *Default if no answer: bake-off, ports abstraction, cascade documented.*
2. **Docker CE in Ubuntu WSL2 vs Docker Desktop.** *Default: Docker CE.*
3. **Workspace semantics**: dedicated `LuccaWorkspace` vs mounting real user folders. *Default: dedicated dir; Downloads opt-in.*
4. **Kokoro NPU as hard Phase 1 criterion vs decision-gated fallback ladder.** *Default: Phase 1a gate with ladder.*
5. **MUX / GPU mode** of the laptop (hybrid vs discrete). *Default: assume hybrid; verify.*
6. **Human-gate handling** for Phases 4–6 (scripted replay acceptable?). *Default: yes, replay of recorded real sessions counts.*
7. **Storage**: approve SQLite+FTS5+sqlite-vec replacing Chroma. *Default: approve.*
8. **PTT key** default. *Default: right ctrl, hold-to-talk.*

## 26. Proposed Deliverable Structure

```
docs/06_critical_review_findings.md          # §2–§21 expanded with line refs into docs 00–05
docs/07_contradiction_register.md            # §2 table + canonical values
docs/08_adr/ADR-001..008.md
docs/09_developer_spec/
  01_process_topology_and_ipc.md
  02_ports_and_interfaces.md
  03_provenance_model.md                     # tiers, signers, quote grounding
  04_memory_storage_schema.md                # SQLite DDL, bitemporal, migrations
  05_rule_dsl_grammar_and_lifecycle.md       # canonical DSL, state schema, plans, state machine
  06_router_classifier_and_labeling.md       # labeling protocol, conformal fit, data-volume gates
  07_audio_pipeline_and_barge_in.md
  08_streaming_chunker_spec.md
  09_sandbox_hardening.md                    # fixed iptables, split containers, RPC
  10_latency_trace_and_budgets.md
  11_observability_config_and_lifecycle.md
  12_threat_model.md
docs/10_testing_matrix_v2.md                 # tiers, thresholds, regenerated from real API
docs/11_phase_plan_v2.md                     # Phase 0 spikes, human gates, deferred scope
docs/12_prior_art_survey.md                  # §23 with verification columns
docs/13_open_questions_and_defaults.md       # §25
```

## 27. Recommended Next Steps for the New Instance

1. Read this file fully. Skim `docs/00`–`05` only to capture exact line refs for the contradiction register.
2. Ask the single clarifying round (§25) via `ask_followup_question`, or proceed with defaults if the user declines.
3. Write `docs/07_contradiction_register.md` first (smallest, highest leverage), then ADR-001, then the developer spec files **one file per tool call**, committing to disk each time.
4. Regenerate the testing matrix from the *actual* code API and the fixed thresholds.
5. Fix `README.md` / `SKILL.md` dangling references.
6. Final handoff pass: verify every doc cross-reference resolves; produce a one-page implementer entry point.
7. Do **not** modify `src/` in Architect mode; list code fixes (§5, §7, §8, §9, §11, §14) as a tracked issue list in `docs/06` for a Code-mode pass.