# Findings

One file per audit area. Each file is created by the subtask that audits that area and contains only findings written with [`../01_FINDING_TEMPLATE.md`](../01_FINDING_TEMPLATE.md) verbatim. Rules are in [`../00_AUDIT_CHARTER.md`](../00_AUDIT_CHARTER.md).

| File | AREA prefix | Covers |
|---|---|---|
| `core.md` | `F-CORE-NNN` | `src/lucca/core/**` (config, events, exceptions, ipc_schemas, orchestrator, schemas, trace, affect, env_check), `src/lucca/main.py`, `src/lucca/ports.py`, `src/lucca/admin.py` |
| `brain.md` | `F-BRAIN-NNN` | `src/lucca/brain/**` (chunker, llm_client, prompt_builder, server_ctl, toolcall_demux) |
| `memory.md` | `F-MEM-NNN` | `src/lucca/memory/**` including `migrations/*.sql` (db, entities, extraction, gate, manager, retrieval, signers, store, tokens, working) |
| `reasoning.md` | `F-REAS-NNN` | `src/lucca/reasoning/**` (lifecycle, scheme lexer/parser/eval/prims/validator) |
| `router.md` | `F-ROUT-NNN` | `src/lucca/router/**` (conformal, heuristic, labeler) and `config/intents.toml` |
| `sandbox.md` | `F-SBX-NNN` | `src/lucca/sandbox/**` (container_spec, egress, file_tool, launcher, policy, rpc, service, system_tools, web_tool, workspace), `docker/**`, `scripts/wsl/lucca-egress.sh`, `config/tool_whitelist.toml` |
| `senses.md` | `F-SENS-NNN` | `src/lucca/senses/**` (asr, audio_proc, dsp_chain, embed, npu_proc, ptt, ring_buffer, tts, vad) |
| `ui.md` | `F-UI-NNN` | `src/lucca/ui/**` (app, commorose, input_bar, settings_dialog, speech_bubble, sprite, states, telemetry_hud, theme), `assets/**`, `config/persona.toml` as consumed by the UI |
| `tests_and_build.md` | `F-TEST-NNN` | `tests/**` (modules, fakes, fixtures), `pyproject.toml` (pytest/ruff/mypy config, scripts, dependencies), `uv.lock`, `packaging/**`, `Lucca.spec`, `launch_lucca.bat`, `scripts/**` other than `scripts/wsl/` |
| `doc_drift.md` | `F-DRIFT-NNN` | Divergences between the implementation and the archived spec set under `luccadocs/archive/2026-09-17_pre_phase4_audit/`, plus stale in-repo references (`README.md`, `AGENTS.md`, `GEMINI.md`, `.agents/skills/lucca-pipeline/SKILL.md`) |
| `architecture.md` | `F-ARCH-NNN` | Cross-cutting structural findings raised via the recursive-review step (Charter §3.5, question 5): module boundaries, dependency direction, process topology, IPC contracts, shared state, lifecycle |

## Conventions

- Files are created only when their area is audited; do not pre-create empty files.
- Within a file, findings are ordered by ID ascending. IDs are never reused, even if a finding is later withdrawn (mark it `Status: WITHDRAWN` with a reason instead).
- Each file begins with a two-line header: the area name and the subtask ID / UTC timestamp that produced it, followed by a summary table (`ID | Severity | Category | Title`) that is regenerated whenever the file changes.
- Cross-area defects are filed once, in the area that owns the code where the fix would land, and cross-referenced from the other area(s).
- When a file boundary is ambiguous (e.g. `config/persona.toml` is read by `brain/prompt_builder.py` and displayed by `ui/settings_dialog.py`), file under the area that *parses* the data and cross-reference from the consumer.
