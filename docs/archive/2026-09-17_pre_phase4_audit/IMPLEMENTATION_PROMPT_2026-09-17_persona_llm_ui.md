# Implementation Prompt — Persona Tab Enrichment & LLM Tab Honesty Pass

**Date:** 2026-09-17
**Target:** Antigravity AI implementation agent
**Scope:** `src/lucca/ui/settings_dialog.py`, `src/lucca/brain/prompt_builder.py`, `src/lucca/brain/llm_client.py`, `src/lucca/core/config.py`, `src/lucca/main.py`, `config/persona.toml`, plus one new shared module and new tests.
**Out of scope:** Memory subsystem, provenance gate, IPC topology, sandbox, audio pipeline, LISP reasoning. Do not touch them.

---

## 0. Mission

Make the Persona and LLM Tuning tabs of the Chrono Trigger Configuration Suite tell the truth about machinery that already exists, enrich persona authoring using prose-compilation (never pseudo-code), and turn the LLM tab into a real model registry with honest server control. Every claim the UI makes must be verifiably real — a button that says "restarted" must have restarted something.

## 1. Non-Negotiable Constraints (from AGENTS.md — read it first)

1. **No CCv2 / roleplay-frontend structures.** No `character_book`, no lorebooks, no `alternate_greetings`, no `mes_example` dialogue blocks, no character-card JSON import. These are un-gated knowledge injection and scripted consistency that compete with the provenance-gated memory/affect layers. Rejected by design.
2. **Prose compilation rule.** Any UI control that influences personality (sliders, dropdowns, checkboxes) must compile into natural-language prose sentences in the system prompt. Never emit `trait=value`, `Warmth("high")`, bracket syntax, or key-value trait lists into prompt text. Pseudo-code prompting degrades instruction-tuned LLM output (prose-style leakage).
3. **Provenance invariants unchanged.** persona.toml is user-authored static config (USER_EXPLICIT-equivalent). Nothing in this work touches the ProvenanceGate, memory signers, or memory eligibility.
4. **Hardware budget.** Host: RTX 5080 16GB VRAM, llama-server native Windows (ADR-001). LLM runs on dGPU only. Never suggest NPU for LLM or tree models.
5. **Code standards.** Python 3.12+, `uv`, Pydantic v2 for cross-boundary contracts, strict typing, zero `Any` in public interfaces, ruff + mypy clean.
6. **Never edit a threshold to make a test pass.** If a measured value violates a budget, record it in `docs/14_blockers.md` and stop.
7. Line numbers cited below are approximate (the file drifts). Locate by function name and verify before editing.

## 2. Defect Register (verified 2026-09-17 — fix all of these)

| # | Defect | Location |
|---|--------|----------|
| D1 | `_restart_llm_server()` is fake: sleeps 1.2s, then claims "✓ Server restarted successfully (Health 200 OK)" without touching any process | `settings_dialog.py` |
| D2 | Model combo is hardcoded (3 baked-in entries), mislabels "Llama-3.1-8B-Instruct-Q4_K_M.gguf" as "Active Default" (real default: `ultravox-v0_5-llama-3_1-8b-Q6_K.gguf`), and selection is unwired to anything | `settings_dialog.py` `_build_llm_tab` |
| D3 | Formality mismatch: persona tab combo offers `casual`/`formal`, but `FORMALITY_MODIFIERS` keys are `casual`/`neutral`/`precise`; "formal" silently falls back to casual | `settings_dialog.py` vs `prompt_builder.py` |
| D4 | `get_system_prompt()` returns `custom_prompt` *instead of* the compiled prompt, amputating `ARCHITECTURAL_SELF_AWARENESS`, tool-use notice, and voice-response constraints | `prompt_builder.py` |
| D5 | `save_persona_to_config()` silently drops list values (`refuse_topics`) and strips all comments; non-empty string lists would serialize as invalid TOML (Python repr single-quotes) | `prompt_builder.py` |
| D6 | Dead config: `uses_your_name`, `admits_uncertainty`, `boundaries.never_pretend_to_feel` exist in `config/persona.toml` but are never injected into the prompt; `[affect]` values are read by `core/affect.py` but never shown in UI | `prompt_builder.py`, `settings_dialog.py` |
| D7 | `llm_client.stream_turn()` hardcodes `temperature=0.2`, `max_tokens=512` and never reads `config.llm.temperature` (0.6) / `config.llm.max_tokens` | `llm_client.py` |
| D8 | Downloader is a raw URL box: no mmproj pairing, no GGUF validation, no compatibility check; can download a 5GB file that can never load | `settings_dialog.py` `_start_model_download` |
| D9 | `LLMSettings` already has `mode` (audio/transcript), `kv_type`, `text_model`, `temperature`, `max_tokens` — none exposed in UI | `core/config.py` |

## 3. Work Items (implement in order)

### WI-1 — `prompt_builder.py` repairs + prose compilation core

1. **D3:** Align formality keys to `casual` / `neutral` / `precise` everywhere (UI combo, persona.toml comment, `FORMALITY_MODIFIERS`).
2. **D4:** Make `custom_prompt` additive. Compiled prompt = archetype prose + formality rule + voice-response constraints + `ARCHITECTURAL_SELF_AWARENESS` + (if set) a `\n\n[Creator Persona Directives]\n{custom_prompt}` section. Update `preview_system_prompt()` to match so the preview is truthful.
3. **D5:** Replace the hand-rolled TOML writer. Preserve comments and all unrelated keys; only rewrite keys the UI owns. Acceptable approach: targeted line-level rewrite of owned keys in the existing file text, creating the file only if absent. Round-trip must preserve `[boundaries]`, `[affect]`, `refuse_topics` (list), and all comments. Add a round-trip unit test: load → save → load produces identical data and the file still parses with `tomllib`.
4. **D6 (prompt side):** Extend the compiled prompt with prose directives derived from config:
   - `uses_your_name = true` → a prose sentence: address the user by name naturally when known.
   - `admits_uncertainty = true` → a prose sentence: say "I'm not sure" rather than guessing.
   - `boundaries.never_pretend_to_feel = true` → a prose sentence: describe affect as system state ("my engagement register is high"), never claim felt emotion.
   - `boundaries.refuse_topics` (non-empty) → one prose sentence naming declined topics.
5. **Prose archetype upgrade:** Rewrite the three `ARCHETYPES` entries in hybrid form: 3–4 bulleted core facts + one short paragraph written *in the voice the model should output* (the legitimate lesson from character-card practice, minus the CCv2 packaging). Keep each archetype ≤ ~120 tokens. Keep `ARCHITECTURAL_SELF_AWARENESS` unchanged.
6. **Trait-slider compilation helper:** Add `compile_trait_modulators(technical_depth: float, warmth: float, directness: float) -> str` (each 0.0–1.0). Map each scalar to one prose sentence selected from 3 bands (low/mid/high) per trait; return the joined sentences, or `""` when all are at neutral defaults (0.5) so the prompt stays clean. Example band mapping — Technical Depth high: "You relish mechanical detail and happily explain systems down to the substrate level." Warmth low: "You keep affection understated — dry humor over open enthusiasm." Directness high: "You lead with the answer first, then the reasoning." **Never** emit numbers or key=value pairs.

### WI-2 — Persona tab UI (`settings_dialog.py`)

1. **D3:** Fix the formality combo to Casual / Neutral / Precise.
2. Add a "Behavior & Boundaries" group box with checkboxes: "Address me by name", "Admit uncertainty aloud", "Never pretend to feel (affect = system state)" — loaded from and saved to persona.toml.
3. Add a `refuse_topics` editor (simple comma-separated QLineEdit or chip list) persisted as a TOML array of strings.
4. Add an "Affect Engine" group box: enabled checkbox, decay half-life slider (60–1800s), max TTS speed delta slider (0–0.25) — these read/write `[affect]` in persona.toml, which `core/affect.py` already consumes.
5. Add the three Granular Trait Modulator sliders (Technical Depth, Warmth / Playfulness, Directness, each 0–100, default 50) wired through `compile_trait_modulators()` into the live prompt preview. Persist the three scalars to persona.toml (e.g. `[traits]` table) and reload on open.
6. Custom archetype Add/Delete: persist user archetypes as prose blocks in a `[archetypes]` table in persona.toml; merge into the combo at load. Delete only removes user-defined entries, never the three built-ins.
7. Preview pane: show the *full* compiled prompt (post-WI-1) plus an approximate token count (chars ÷ 4).
8. **Save path:** `_handle_save()` must persist every new control through the WI-1 serializer and call `set_persona()` so changes apply without restart.

### WI-3 — Honest LLM server control (new shared module)

1. Create `src/lucca/brain/server_ctl.py` (or `src/lucca/core/server_ctl.py` — pick the better fit) by **extracting** the launch logic from `main.py:_ensure_llama_server` into reusable, strictly-typed functions:
   - `build_launch_command(cfg: LLMSettings, home_dir: Path) -> list[str]`
   - `is_healthy(host: str, port: int, timeout: float = 1.0) -> bool` (real GET /health)
   - `start_server(cfg, home_dir) -> subprocess.Popen` (raises on missing exe/model)
   - `stop_server(host, port) -> None` (terminate the tracked process; escalate to taskkill by PID only if terminate fails)
   - `restart_server(cfg, home_dir, timeout_s: float = 60.0) -> None` — stop, start, poll /health until 200 or timeout; raise on timeout.
2. Refactor `main.py` to consume this module (no behavior change at boot).
3. **D1:** Rewire the Restart button to call `restart_server()` on a QThread, with real status transitions: "Stopping…" → "Launching…" → "Waiting for /health…" → "✓ Healthy (port 8080, 12.3s)" or a real error. Button disabled during operation. No fabricated states.

### WI-4 — LLM tab: real model registry, compatibility, tuning

1. **D2 — Model registry:** On dialog open, scan `C:\ProjectLucca\models\llm\*.gguf` (path from config `home_dir`). Populate the combo from disk reality: display name, on-disk size, and "(Active)" on the entry matching `config.llm.model`. No hardcoded entries.
2. **GGUF metadata:** Parse the GGUF header key-value section (magic `GGUF`, version, tensor count, KV count; read `general.name`, `general.architecture`, `general.quantization_version` if present, and derive quant from filename suffix as fallback) in a small strictly-typed helper. Show a description panel per selection: name, architecture, file size, quant.
3. **Audio-compatibility badge** — the core rule: compatibility with native audio input is a binary architectural property.
   - 🎙 **Audio-Native** — a sibling `mmproj*.gguf` exists in the same directory → runs `mode = "audio"` (raw `input_audio`).
   - 📄 **Text via Whisper** — no mmproj → runs `mode = "transcript"`; Whisper already runs every turn, so any text GGUF works with zero pipeline changes.
   - ⚠ **mmproj required** — filename/metadata indicates an audio model (e.g. `ultravox`) but no projector found; offer one-click mmproj fetch.
   Selecting a model sets `config.llm.model` (+ `mmproj`/`mode` per the badge) and requires the WI-3 restart to apply — say so in the UI.
4. **D8 — Curated catalog + raw URL:** Add a small vetted download table (name, HF repo, filename, approx size, audio-capable flag), e.g. Ultravox v0.5 Llama-3.1-8B Q6_K + its mmproj (audio-native), Qwen2.5-7B/14B-Instruct Q4_K_M (transcript mode), Llama-3.1-8B-Instruct Q6_K (transcript mode). Downloads use the existing `ModelDownloadWorker`; audio entries auto-fetch the paired mmproj. Keep the raw URL box as an advanced option, but after download validate the file starts with the `GGUF` magic before adding it to the registry; reject and delete otherwise.
5. **D9 — Expose existing config:** Add controls for: temperature (0.0–1.5, default from config), max_tokens (64–2048), KV-cache type selector (`f16` / `q8_0` / `q4_0` — the VRAM estimator already shows all three footprints; make the selector update which footprint is highlighted), mode toggle (Audio / Transcript), n-gpu-layers (0–99, default 99). Persist to the config layer used by `core/config.py` (follow however config is already persisted/loaded; if it is env/pydantic-settings only, persist to the project's config file and document the reload path).
6. **VRAM fit guard:** weights size (file size on disk as lower bound) + KV estimate at the current ctx slider + ~1GB overhead must not exceed 15GB; if it does, show a red warning and disable "Apply & Restart" until the user lowers ctx, picks a smaller kv_type, or picks a smaller model. Do not block display — block only the apply action.
7. Context slider, presets, and the KV estimator stay; fix the estimator label to state it's an Llama-8B-class approximation.

### WI-5 — `llm_client.py` config wiring (D7)

`stream_turn()` defaults must read `self.config.llm.temperature` and `self.config.llm.max_tokens` when the caller passes `None`. Change signature defaults to `None` and resolve inside. No behavior change for explicit callers.

### WI-6 — Tests (T0/T1 tier, no hardware required)

Add to `tests/`:
1. `test_prompt_builder.py` — formality keys valid; custom prompt is additive (assert `ARCHITECTURAL_SELF_AWARENESS` still present when custom prompt set); boundary/uncertainty/name flags each inject exactly one prose sentence; `compile_trait_modulators` returns prose with no `=`, no digits, no brackets, and `""` at all-neutral.
2. Persona TOML round-trip: save preserves comments, `[boundaries]`, `[affect]`, and `refuse_topics` list; file re-parses with `tomllib`.
3. `test_server_ctl.py` — `build_launch_command` includes `--mmproj` iff mode == audio and mmproj exists; `is_healthy` false on closed port (no server needed).
4. GGUF metadata parser: parse a tiny synthetic GGUF header fixture built in-test (bytes, not a real model).
5. Run: `uv run pytest tests/ -x -q`, `uv run ruff check src tests`, `uv run mypy src`. All green.

## 4. Definition of Done

- All D1–D9 fixed.
- Restart button performs a real stop/start/health-poll cycle and reports real outcomes only.
- Model combo reflects disk reality; every model shows an honest compatibility badge; switching models persists config and prompts a real restart.
- Every persona control compiles to prose; the preview shows the true compiled prompt with token estimate.
- persona.toml round-trips losslessly (comments, lists, tables).
- `llm_client` honors config temperature/max_tokens.
- New tests pass; ruff and mypy clean; no edits to memory, provenance, sandbox, IPC, or audio modules.
- No CCv2 artifacts anywhere: no character_book, lorebook, alternate_greetings, mes_example, or card import.

## 5. Explicitly Rejected (do not "improve" by adding)

- Character Card V2 import/export, lorebooks, scripted example dialogue, greeting scripts.
- Any pseudo-code trait syntax in prompts (W++, PList, AliChat, key=value trait dumps).
- Any new background process, ZMQ socket, or IPC channel.
- NPU execution for the LLM or any tree model.
- Changing any latency/VRAM threshold to make a check pass.
