# 04 — Owner Decisions Taken During the Audit (2026-09-18)

**Status:** RATIFIED by the project owner in the S2b review session (2026-09-18T05:48Z).
**Scope rule honoured:** this file records decisions only. No source, test, config, script, or model file was modified. Execution of every decision below is queued for the post-audit remediation programme unless explicitly marked otherwise.
**Context:** audit paused at owner request after S2b; questions Q-01 (core), Q-B-02, Q-B-13, Q-B-14 and the F-BRAIN-002/003 model-supply decision were presented with recommendations; the owner ratified as follows.

---

## D-AUD-01 — `Any` severity: Charter §5.5 governs (S0) for public/cross-boundary interfaces

- **Decision:** Charter §5.5 ("zero `Any` in public interfaces") is a hard invariant; violations on public or cross-boundary surfaces grade **S0/INVARIANT**. The §4 S3 mention is read as covering private/internal helpers only.
- **Owner input:** "whatever is best long term" (ratified the auditor's recommendation).
- **Effect:** F-CORE-001 and F-BRAIN-001 gradings stand. No charter amendment needed; the post-audit docs set should make the §4/§5.5 wording consistent.

## D-AUD-02 — Phase 1 was entered with a known-failing Phase-0 S5 gate; disposition recorded

- **Finding of fact:** the pre-audit `phase0_llm.json` (2026-09-17T15:21Z) records `S5: FAIL, rss_mb=1809.42 > 800`; Phase-1 commits followed with no waiver in `13_decisions_log.md`. The S5 metric itself is invalid (WorkingSet64 of a GPU-resident process; the same process reads 11.6 MB WS vs 8.8 GB private bytes — `S1_SUMMARY` §2.4/§2.10).
- **Decision:** the Phase-0 bundle is **provisional** until F-BRAIN-007's remediation re-runs it with private-bytes RSS, real cold-start, asserted abort status, and rejection-based S9. The disposition ("Phase 1 entered with S5 FAIL unresolved; metric redefined") is to be written into the decisions log when it becomes writable.
- **Owner input:** "whatever is best long term" (ratified).

## D-AUD-03 — Voice: persona.toml `voice` is canonical; default `genki_heroine`; strip the Chrono Trigger personality

- **Decision (ownership):** `config/persona.toml → voice` is the single canonical voice source. The competing defaults (`TTSChunk.voice = "af_heart"` in `core/schemas.py:151` and `core/ipc_schemas.py:83`) are to be aligned or removed. Shipped default: **`genki_heroine`**.
- **Decision (persona content):** **strip the Chrono Trigger identity from the personality layer.** The "Lucca Ashtear, prodigy inventor from Chrono Trigger (Truce, Kingdom of Guardia, 1000 AD)" identity, the signature-props descriptions (glasses/helmet/satchel), and the CT-lore backstory in `ARCHETYPES["inventor"]` and `ARCHITECTURAL_SELF_AWARENESS` (`src/lucca/brain/prompt_builder.py:16-24, 47-91`) are to be replaced with an original, product-owned companion identity. The **name "Lucca" and the `genki` voice/archetype are retained** (assumption recorded: the owner said "strip the personality stuff", not rename the project; override if wrong).
- **Owner input:** "genki, strip out the chronotrigger personality stuff. whatever works best longterm".
- **Effect on findings:** F-BRAIN-004's remediation (truthful self-awareness block) is amended — the rewrite must also remove the CT identity, not just the false capability claims. The UI subtask (S2x, UI area) must inventory CT dependencies in `ui/` and `assets/sprites/` (SNES "royal blue dialogue frame", Lucca sprite sheet, `portrait_classic.png`) so the strip is complete; persona.toml's current `archetype = "kuudere"` stays valid as a non-CT archetype.
- **Rationale (long-term):** an original identity removes third-party IP from the shipped persona, removes the fiction-within-fiction problem (a character claiming a fabricated architecture), and keeps the differentiating voice (genki) that the owner explicitly wants.

## D-AUD-04 — Persona file: deployed copy canonical; repo copy becomes a first-run template

- **Decision:** `C:\ProjectLucca\config\persona.toml` (LUCCA_HOME-anchored) is the only runtime source. The repo `config/persona.toml` becomes a template copied to LUCCA_HOME on first run/install; the loader resolves only via `home_dir` (F-BRAIN-046 remediation step 1 ratified as the design).
- **Owner input:** "whatever works best longterm" (ratified the auditor's recommendation).

## D-AUD-05 — Model supply: Option A (true Ultravox backbone + Q8_0 mmproj + MANIFEST.json), executed as remediation task #1

- **Decision:** replace the renamed bartowski backbone with `ggml-org/ultravox-v0_5-llama-3_1-8b-GGUF` `ultravox-v0_5-llama-3_1-8b-Q6_K.gguf`; download the true Q8_0 mmproj (≈ 743 MB, recovering ~0.6 GiB VRAM vs the f16 file currently misnamed Q8_0); create `C:\ProjectLucca\models\MANIFEST.json` with sha256 pins; wire verification into `scripts/download_llm_models.py` and `server_ctl.start_server` (F-BRAIN-002/003 remediations as written). Re-run the 20-clip audio fixture suite and ADR-001 S10 against the true backbone; if it measures *worse* than the current backbone on tool-call validity, fall back to keeping the stock backbone **under its true name** with a recorded decision (Option B).
- **Timing:** execute as remediation task #1 after the audit completes (avoids a second mid-audit tree mutation; F-BRAIN-008). If the owner later wants it sooner, declare a formal fix-forward event with re-baseline (F-BRAIN-008 step 3).
- **Owner input:** "a" (Option A).

## D-AUD-06 — Evaluate gpt-oss-20B as an alternative/additional brain (spike queued)

- **Owner input:** "but also look into gpt 20b oss or whatever".
- **Decision:** run a Phase-0-style spike of **gpt-oss-20b** as a candidate text-mode/cascade brain, wired through the existing empty `LLMSettings.text_model` slot (`src/lucca/core/config.py:39`), before committing the long-term primary-model choice.

### Evaluation summary (specs marked ⚠ are from training knowledge, not re-verified — no web access during the audit; verify in the spike)

| Axis | Ultravox v0.5 Llama-3.1-8B (current, Option A) | gpt-oss-20b (candidate) |
|---|---|---|
| Audio input | **Native** (`input_audio` via mmproj; ADR-001 Option B) | **None** — text-only; forces transcript/cascade mode (Whisper first, +100–200 ms, ADR-001 Option D) |
| Params / active | 8B dense | ⚠ ~21B total / ~3.6B active (MoE, 32 experts) |
| VRAM (weights) | 6.3 GiB (Q6_K) + 0.7–1.3 GiB mmproj | ⚠ ~11–13 GiB native MXFP4; community GGUF quants vary — tight but plausible on 16 GB with q8_0 KV at ctx 8192 |
| Reasoning / tool use | 8B-instruct class; measured hallucinated calls on tones (S1_36) | ⚠ Substantially stronger (reasoning model, native tool calling, harmony format); reasoning effort configurable (low/med/high) |
| Latency fit (Spec 10: TTFT ≤ 180/300 ms, total ≈ 475 ms) | Measured: TTFT warm 19–44 ms, decode 73–80 tok/s (S1_18b) | ⚠ Decode should be fast (3.6B active); TTFT depends on reasoning effort — must be measured at `low`; reasoning traces could blow the voice budget |
| llama.cpp support | Shipping today (build 11026) | ⚠ Supported since Aug 2025 builds; build 11026 is far newer — verify `--jinja` harmony rendering + tool calls |
| Licence | Llama 3.1 community licence | ⚠ Apache 2.0 |
| Long-term role | Audio-native primary | Stronger **transcript-mode** brain; candidate primary if audio-native keeps underperforming |

### Spike plan (queued for the remediation programme)

1. Download `gpt-oss-20b` GGUF (pin sha256 in MANIFEST.json per D-AUD-05) into `models\llm\`; set `LLMSettings.text_model` to it.
2. Measure on the deployed binary: cold/warm start, TTFT ×20 at reasoning effort `low`, decode tok/s, VRAM (must stay ≤ 9.5 GB with KV q8_0 @ 8192), and the 20 text tool-call fixtures (threshold ≥ 18/20, same as ADR-001 S10).
3. Decision gate: if TTFT p95 ≤ 300 ms and tool-call validity ≥ 18/20, adopt gpt-oss-20b as `text_model` (transcript mode) and re-run the full turn-loop latency gate in transcript mode (Spec 10: median ≤ 800 ms, p95 ≤ 1 000 ms). Keep Ultravox as the audio-mode primary regardless; revisit "one model for both modes" only if the audio path fails its own gates after D-AUD-05.
4. Record the outcome in the decisions log; if adopted, ADR-001 gets an addendum (text_model ≠ backbone).

---

## Open follow-ups owned by this file

- Write D-AUD-01…06 into `luccadocs/13_decisions_log.md` when the post-audit docs set is writable (the current log is archived read-only).
- UI subtask: inventory Chrono Trigger dependencies in `ui/` + `assets/` (per D-AUD-03) before the UI area audit closes.
- Remediation programme: task #1 = D-AUD-05; task #2 = D-AUD-06 spike; both before any persona rewrite (D-AUD-03) so the persona is compiled against the final model choice.

---

## Batch ratification (2026-09-18T11:34Z) — D-AUD-07…19

**Owner input:** "Do whatever is best for the codebase" — all remaining owner-owned questions from the area question registers are ratified at their recorded defaults, chosen on the long-term codebase criterion. The audit freeze is **lifted**; the remediation programme (arch.md §2 sequencing) may begin, executing one commit per finding ID per F-ARCH-008.

### D-AUD-07 (Q-M-01) — `tool_contents`: wire as the `TOOL_CONTENT_UNTRUSTED` store
Implemented when F-CORE-019's remediation feeds tool results back; `pending_confirmations` dropped via migration `0003` unless a consumer appears.

### D-AUD-08 (Q-M-02) — Backup retention: calendar-day grouping
14 most-recent-per-day + 8 Sundays, per the docstring intent; UTC naming.

### D-AUD-09 (Q-M-03) — UI "add memory": keep, gate-verified
Admin writes go through a signed `UnsignedPayload` + `ProvenanceGate.admit` (F-MEM-001 remediation as written); `signature="manual"` eliminated.

### D-AUD-10 (Q-R-02) — Launch lexicon: remove `cmd`/`powershell`/`code`/`vscode`; whitelist NOT widened
`tool_whitelist.toml` is the security boundary; the router lexicon derives from it (F-ROUT-003).

### D-AUD-11 (Q-R-03) — `decision_labels`: upsert allowed; the data-volume gate counts only the FIRST label per decision
Relabelling after gate evaluation cannot inflate the ≥ 600 floor.

### D-AUD-12 (Q-E-01) — Quarantine tolerance: retire on FIRST failure
Strictest reading of "0 failures" (F-REAS-010 recorded default).

### D-AUD-13 (Q-S-01 / Q-A-02) — `run_python`: retained, container-mandatory
`use_direct_fallback` defaults `False`; host refusal with a spoken notice when Docker is unreachable (F-SBX-001).

### D-AUD-14 (Q-S-02 / Q-U-01) — `read_codebase_file` / CODEBASE action: deleted until specified
The system prompt claim, the commorose action (relabeled "OPEN PROJECT FOLDER"), and the help text all stop advertising Lucca-side code inspection (F-BRAIN-004/F-UI-004 coordinated strip).

### D-AUD-15 (Q-N-01) — ASR: wire the configured `whisper-large-v3-turbo-ov` model + device ladder
`distil-small.en` was a Phase-1 expedient; `language` auto-detected (F-SENS-001).

### D-AUD-16 (Q-N-02) — Anime DSP chain: wired into the production TTS path
Applied post-`engine.create`, pre-int16, behind a config flag defaulting on (F-SENS-015).

### D-AUD-17 (Q-U-02) — Latency badge: wired to real `TurnTrace.total_e2e_ms`; hidden until measured
The "382 ms" constant is deleted (F-UI-001).

### D-AUD-18 (Q-U-03 / Q-A-01) — UI: keep the 10-tab structure; strip CT identity per D-AUD-03
Tab split into a `ui/settings/` package (F-UI-008) during the honesty pass.

### D-AUD-19 (Q-T-01 / Q-T-02 / Q-D-01 / Q-D-03) — Distribution, CI, docs, fiction
- Distribution: `launch_lucca.bat` + `uv` primary; exe secondary until F-TEST-004's boot-path fix and a T3 smoke pass.
- Gating: the `lint` script is mandatory per commit; CI optional and deferred.
- Docs: post-audit set rewritten **from code truth** (charter plan confirmed).
- Fictional capability layer: **deleted entirely**, replaced by a true capability manifest derived from registered tools (F-DRIFT-006).

### Execution order (replaces the "Open follow-ups" item 3)

arch.md §2 sequencing stands, with D-AUD-13's fallback-off landing in Phase 0 alongside the governance layer (it is a one-line default change + refusal path), and D-AUD-05's model supply as Phase 1.
