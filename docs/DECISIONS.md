# Project Lucca — Canonical Decisions Log (Post-Audit Baseline)

**Status:** Authoritative Post-Audit Record  
**Version:** 0.2.0  
**Updated:** September 2026  
**Charter Reference:** Ratified per D-AUD-19, consolidating all owner decisions from the audit period (`04_OWNER_DECISIONS.md`).

---

## 1. Architectural & Governance Decisions

### D-AUD-01 — Strict Typing Invariant
- **Decision:** Charter §5.5 ("zero `Any` in public interfaces") is a hard architectural invariant. Violations across `core`, `brain`, and `reasoning` are graded S0/INVARIANT and strictly forbidden by static gates.
- **Status:** Ratified & Enforced (`test_no_any_in_core_public_api`, `test_no_any_in_brain_public_api`, `test_no_any_in_reasoning_public_api`).

### D-AUD-02 — Phase 0 S5 RSS Metric Redefinition
- **Decision:** The legacy WorkingSet64 metric of a GPU-resident process is invalid for measuring host RAM. Resident host RSS must be measured using private working set bytes via `psutil.Process().memory_info().rss`.
- **Status:** Ratified & Enforced across telemetry, audit scripts, and tests.

---

## 2. Persona, UI & Voice Strategy

### D-AUD-03 — Voice Canonicalization & Persona Strip
- **Decision:** 
  1. `config/persona.toml -> voice` is the single canonical source of voice configuration. Default voice is **`genki_heroine`**.
  2. The third-party Chrono Trigger character identity ("Lucca Ashtear from 1000 AD", glasses/helmet/satchel lore) is completely stripped from the personality and prompt layers.
  3. The project name "Lucca" and the energetic "genki" voice archetype are retained for an original, product-owned companion identity.
- **Status:** Ratified & Enforced.

### D-AUD-04 — Persona File Precedence
- **Decision:** Runtime configuration resolves strictly from `<LUCCA_HOME>\config\persona.toml`. The repository copy serves as a first-run template.
- **Status:** Ratified & Enforced.

### D-AUD-14 / D-AUD-19 — Elimination of Fictional Capabilities
- **Decision:** The fictional capability layer (non-existent codebase inspection on port 5557-5559, simulated temporal logic gates, and fabricated latency badges) is completely eliminated from prompts, manifests, and UI surfaces.
- **Status:** Ratified & Enforced via `test_capability_claims_real` and `test_no_fabricated_metrics`.

### D-AUD-17 — Latency Badge Honesty
- **Decision:** The hardcoded `"382 ms"` latency badge in the UI is removed. The badge is hidden by default and only displayed when populated with measured `TurnTrace.total_e2e_ms`.
- **Status:** Ratified & Enforced.

### D-AUD-18 — UI Structure
- **Decision:** Retain the 10-tab settings window, refactored into a modular `ui/settings/` layout with clean separation between UI widgets and core orchestrator state.
- **Status:** Ratified & Enforced.

---

## 3. Inference, Model Supply & ASR Strategy

### D-AUD-05 — Model Supply & Verification (Option A)
- **Decision:** Deploy true Ultravox Q6_K backbone with Q8_0 mmproj; pin cryptographic checksums in `models/MANIFEST.json`; enforce validation in downloaders and before `llama-server` process launch.
- **Status:** Ratified & Enforced.

### D-AUD-06 — Evaluation of Alternative Text Brains (Spike)
- **Decision:** Evaluate alternative text models for Cascade / Transcript-First mode (Option D), including **gpt-oss-20b** and **Mistral NeMo 12B**, measuring TTFT, decode throughput, VRAM occupancy, and tool-call validity within the 9.5 GB dGPU budget.
- **Status:** Queued & In Progress.

### D-AUD-15 — ASR Device Ladder & Architecture
- **Decision:** Wire the configured `whisper-large-v3-turbo-ov` model with OpenVINO device ladder (NPU $\rightarrow$ GPU $\rightarrow$ CPU), replacing the temporary `distil-small.en` CPU shortcut.
- **Status:** Ratified — Implementation Queued (Active runtime remains `distil-small.en` on CPU int8 via `faster-whisper` in `src/lucca/senses/asr.py`).

### D-AUD-16 — Anime DSP Audio Processing
- **Decision:** Apply formant-shifting and high-frequency excitation DSP post-Kokoro synthesis to give the output an authentic anime heroine aesthetic.
- **Status:** Ratified — Standalone Module Implemented (`src/lucca/senses/dsp_chain.py`), TTS Output Pipeline Integration Queued.

---

## 4. Security, Sandbox & Memory Controls

### D-AUD-07 — `tool_contents` Untrusted Store
- **Decision:** Tool execution outputs returned from containers are stored with `TOOL_CONTENT_UNTRUSTED` provenance, subject to indirect prompt injection containment.
- **Status:** Ratified & Enforced.

### D-AUD-08 — Memory Backup Retention
- **Decision:** Database backups follow calendar-day UTC grouping (14 daily backups + 8 weekly Sunday backups).
- **Status:** Ratified & Enforced.

### D-AUD-09 — Cryptographic Provenance for Admin Edits
- **Decision:** Manual memory additions, updates, and deletions via the UI or admin CLI must pass through `ProvenanceGate` with HMAC/Ed25519 signatures. Arbitrary `signature="manual"` bypasses are prohibited.
- **Status:** Ratified & Enforced.

### D-AUD-10 — Application Launcher Whitelist
- **Decision:** Application launching is restricted to `config/tool_whitelist.toml`. Arbitrary shells (`cmd.exe`, `powershell.exe`) are strictly excluded from execution.
- **Status:** Ratified & Enforced.

### D-AUD-11 — Decision Telemetry & Auto-Labeling
- **Decision:** Decision records allow label updates, but the data volume gate ($\ge 600$ records) counts only the first label per decision to prevent synthetic label inflation.
- **Status:** Ratified & Enforced.

### D-AUD-12 — Rule Engine Quarantine Invariant
- **Decision:** Promoted MicroScheme rules operate under a strict zero-failure policy; a single runtime exception immediately retires the rule back to quarantine.
- **Status:** Ratified & Enforced.

### D-AUD-13 — Container-Mandatory Sandboxing
- **Decision:** Host execution fallback is disabled by default (`use_direct_fallback = False`). Tool execution requires containerized WSL2/Docker sandboxing, refusing execution with a spoken notice if unavailable.
- **Status:** Ratified & Enforced.
