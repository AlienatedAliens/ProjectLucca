# Findings — UI (`src/lucca/ui/**`, `assets/**`)

**Subtask:** S2h · **Method:** static line-by-line (targeted for the 2,466-line `settings_dialog.py`) + S1 dynamic evidence · **Baseline:** HEAD `ed14f6b` + working tree per `03_BASELINE.md`, delta in [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) (UI modules: **unchanged since S0**) · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; every finding cites `file:line` in the current tree or an artefact under `docs/audit/evidence/`. Cross-area findings cross-referenced by ID.

**Severity totals: S0 = 0 · S1 = 1 · S2 = 5 · S3 = 8 · S4 = 1 · total = 15.**

---

## 1. Module map

Coverage from `docs/audit/evidence/S1_14_coverage.txt` rows 74–82. LOC = non-blank lines (S0 metric, verified unchanged by `03b_BASELINE_DELTA.md`).

| File | LOC | Public symbols | Responsibilities (as-built) | Live callers in product path? | Outbound dependencies | Cov % | Tests |
|---|---:|---|---|---|---|---:|---|
| `ui/app.py` | 420 | `UIBridge`, `UIApplication` (`run`, `quit`), `main` | `lucca-ui` process: QApplication, sprite/bubble/chat-bar/commorose/HUD wiring, ZMQ bus listener + ingest publisher, tray, context menu | **yes** — `main.py:18,90` | `zmq`, `PyQt6`, all UI widgets, `brain.prompt_builder` | **0 %** | none |
| `ui/settings_dialog.py` | 2,100 | `SettingsDialog`, `ServerRestartWorker`, `ModelDownloadWorker`, + ~40 tab builders | 10-tab configuration suite: persona, voice, LLM registry/restart, whitelist, rules editor, diagnostics, help | **yes** — `app.py:36,244` | `brain.prompt_builder`, `brain.server_ctl`, `memory.manager`, `sandbox.system_tools`, `senses.dsp_chain/tts`, `reasoning.scheme.parser` | 68 % | `tests/test_ui_widgets.py` (partial) |
| `ui/speech_bubble.py` | 321 | `SpeechBubble` (`show_caption`, `show_confirmation`, `anchor_to`) | Typewriter subtitles, confirmation buttons, CT-styled header with **hard-coded "382 ms" latency badge** (F-UI-001) | **yes** — `app.py:37,88` | `PyQt6` | 72 % | `tests/test_ui_widgets.py` (partial) |
| `ui/sprite.py` | 260 | `CompanionSprite` | Sprite-sheet animation, drag, click/dbl-click/context callbacks, always-on-top, mouth aperture | **yes** — `app.py:38,87` | `PyQt6`, `states` | 38 % | `tests/test_ui_widgets.py` (partial) |
| `ui/commorose.py` | 254 | `CommoroseAction`, `CommoroseRadialMenu` | Radial quick-action menu (8 actions) | **yes** — `app.py:34,132` | `PyQt6` | **0 %** | none |
| `ui/input_bar.py` | 219 | `QuickChatBar` | Text input, mic hold-button (mouse PTT), send | **yes** — `app.py:35,89` | `PyQt6` | 52 % | `tests/test_ui_widgets.py` (partial) |
| `ui/telemetry_hud.py` | 352 | `TelemetryWorker`, `TelemetryHUD` | Floating hardware HUD polling `get_system_metrics` on a QThread | **yes** — `app.py:39,95` | `sandbox.system_tools`, `theme` | 58 % | none |
| `ui/states.py` | 62 | `AvatarTheme`, `THEMES` | 7 avatar colour themes (incl. `degraded` — never emitted, cf. core.md §3.1) | **yes** — `sprite.py` | — | 100 % | indirect |
| `ui/theme.py` | 226 | `CHRONO_TRIGGER_STYLE_SHEET`, `CT_*` palette | Global stylesheet | **yes** — `app.py:40,63` | — | 100 % | indirect |

**Wiring verdict:** all UI modules are live in the `lucca-ui` process. The UI is the only process with a working end-to-end IPC loop (bus listener → Qt signals → widgets; ingest publisher for user text/confirm/config). `app.py`/`commorose.py` at 0 % coverage means the entire interaction layer is untested.

## 2. As-built behaviour notes

- **IPC:** UI subscribes to the bus (`app.py:421-460`) for `ui.state`/`ui.caption`/`ui.confirm`/`audio.rms`; publishes `ui.user_text`, `ui.confirm_result`, `ui.config_update`, `ui.talk_press/release` on ingest. Cross-thread delivery via `UIBridge` Qt signals — correct Qt pattern.
- **Config update:** `_send_config_update` (`:370-390`) relays voice/speed/ptt_key + persona fields + `llm_model` (the dead field, F-CORE-057).
- **Settings dialog:** honest server restart via `ServerRestartWorker` (real stop/start/health-poll, `settings_dialog.py:82-120` — implements the implementation prompt's WI-3.3, though it bypasses the dead `restart_server`, F-BRAIN-035); model registry from disk (`scan_model_registry`); VRAM fit guard disabling restart (`:1223-1232`); persona save via `save_persona_to_config` (F-BRAIN-013's cross-process divergence).
- **Hard-coded paths:** `C:/ProjectLucca/...` appears throughout the dialog (TTS models `:901-902,1738-1739`, logs `:2117,2129,2187`, help text `:2254,2323`), plus `C:\projects\ProjectLucca` in the commorose CODEBASE action (`app.py:128`) and help text (`:2258,2331`).

---

## 3. Findings

Ordered by severity, then by ID. Every finding re-reviewed per Charter §3.5 (log in §7); `Status: OPEN`.

### F-UI-001 — The speech bubble displays a hard-coded fake latency badge ("382 ms") that never updates

| Field | Value |
|---|---|
| **ID** | F-UI-001 |
| **Title** | The speech bubble displays a hard-coded fake latency badge ("382 ms") that never updates |
| **Severity** | S1 — High |
| **Category** | UX |
| **Location** | `src/lucca/ui/speech_bubble.py:99-110` |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/speech_bubble.py:99`
```python
        self.latency_label = QLabel("382 ms", self)
```
(a repo-wide search finds no `latency_label.setText` anywhere — the value is set once at construction and never changed; no trace or bus event feeds it.)

**What is wrong / assumed / missing**

Every speech bubble shows a green "382 ms" latency badge — a fabricated constant presented as a live measurement, on the widget the user stares at all day. The real per-turn latency exists in `TurnTrace` (`total_e2e_ms`, computed in `core/trace.py:44-60`) and is logged to `traces.jsonl`, but nothing pipes it to the UI. Which side is right: the Spec 16 §3 design (a live latency indicator) — the implementation must either measure or remove the badge.

**Why it matters**

Fabricated telemetry displayed to the user — the most visible member of the honesty-of-recorded-metrics family (F-CORE-009, F-SBX-011, F-SENS-005/013, F-ROUT-005). It also makes every real latency complaint unverifiable ("it says 382 ms but it took 5 seconds").

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/speech_bubble.py`: hide the badge by default (`self.latency_label.hide()`); add `set_latency_ms(ms: float | None)` that shows it with the measured value or hides it on `None`.
2. In `src/lucca/core/orchestrator.py` (CORE-area change): include `total_e2e_ms` in the final `ui.caption` payload (or a new `ui.latency` bus event) so the UI can call `set_latency_ms` per turn.
3. Add `tests/test_ui_widgets.py::test_latency_badge_hidden_until_measured`: fresh bubble → badge hidden; `set_latency_ms(412.0)` → visible with "412 ms".

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** no fabricated value ever displayed
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_latency_badge_hidden_until_measured -q`

**Cross-references:** F-CORE-009, F-CORE-056, F-SBX-011, F-SENS-005

---

### F-UI-002 — The UI process exits without notifying core: the supervisor logs a dead-child warning every second for the rest of the session

| Field | Value |
|---|---|
| **ID** | F-UI-002 |
| **Title** | The UI process exits without notifying core: the supervisor logs a dead-child warning every second for the rest of the session |
| **Severity** | S1 — High |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/ui/app.py:471-478`; `src/lucca/main.py` (Supervisor loop); `docs/audit/evidence/S1_24_lucca_main.stderr.log`; `docs/audit/findings/core.md` F-CORE-005/006 |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/app.py:471-478`
```python
    def quit(self) -> None:
        self.running = False
        try:
            self.ingest_sock.close(linger=0)
            self.ctx.destroy(linger=0)
        except Exception:  # noqa: BLE001, S110
            pass
        self.app.quit()
```
(no `ui.state offline` publication, no farewell envelope — the process simply exits; observed consequence in `S1_24_lucca_main.stderr.log`: ≥ 807 identical `WARNING: Child process 'ui' exited with code 0.` lines, one per supervisor tick, and the supervisor took no action.)

**What is wrong / assumed / missing**

"Quit Lucca" (tray and context menu) tears down Qt and ZMQ locally and exits 0. Spec 01 §7's shutdown order begins with `ui.state offline` on the bus; nothing sends it. The supervisor (F-CORE-005/006) neither restarts the child nor shuts the app down — the user's "Quit" leaves a headless voice assistant running with a dead UI, spamming stderr. Which side is right: the spec — UI quit is the user's shutdown gesture and must propagate.

**Why it matters**

The only user-initiated shutdown path in the product leaves the system half-alive with a log flood; the S1 session ended only because the auditor force-killed the tree.

**Questions this raises**

1. None — the fix shape is already specified by Spec 01 §7; the supervisor-side half is F-CORE-005/006.

**Proposed remediation**

1. In `src/lucca/ui/app.py`, `quit()`: before teardown, publish `Envelope(type="ui.state", payload=UIStatePayload(state="offline", …))` on the bus (a PUB socket — the UI currently has no bus publisher; add one alongside the ingest PUSH). Before: silent exit. After: offline announcement.
2. In `src/lucca/main.py` (CORE-area change, joint with F-CORE-006): on `ui` child exit with code 0, initiate full shutdown instead of logging.
3. Add `tests/test_ui_widgets.py::test_quit_publishes_offline` (T2): run `UIApplication.quit()` with a captured bus; assert an `ui.state=offline` envelope was published.

**Verification test**

- **Tier:** T2
- **Input:** the test above
- **Expected output:** offline envelope on the bus before exit
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_quit_publishes_offline -q`

**Cross-references:** F-CORE-005, F-CORE-006, F-CORE-029, F-CORE-038

---

### F-UI-003 — Hard-coded absolute paths throughout the UI (`C:\ProjectLucca`, `C:\projects\ProjectLucca`) break portability and dev/prod separation

| Field | Value |
|---|---|
| **ID** | F-UI-003 |
| **Title** | Hard-coded absolute paths throughout the UI (`C:\ProjectLucca`, `C:\projects\ProjectLucca`) break portability and dev/prod separation |
| **Severity** | S2 — Medium |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/ui/app.py:113,128`; `src/lucca/ui/settings_dialog.py:901-902,1738-1739,2117,2129,2187`; `src/lucca/ui/app.py:128` |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/app.py:113`
```python
                lambda: _open_dir(r"C:\ProjectLucca"),
```
(`settings_dialog.py:901-902`: TTS model existence checks; `:2117,2129,2187`: log dirs; `app.py:128`: CODEBASE commorose action opening the repo in Explorer. `config.resolve_path` exists and is used correctly by `WorkspaceManager` — the UI simply doesn't use it. The F-CORE-030 family now spans core, mem, sbx, sens, and ui.)

**What is wrong / assumed / missing**

Every hard-coded path breaks on a non-default install and in dev checkouts (the repo lives at `C:\Projects\ProjectLucca` — case differs from the hard-coded `C:\projects\` in three places, working only via Windows case-insensitivity). The TTS model checks at `:901-902`/`:1738-1739` duplicate F-SENS-008's paths and will disagree with the TTS worker's own resolution once that is config-anchored.

**Why it matters**

Same portability defect family, now with a user-facing surface (FOLDERS/CODEBASE commorose actions open wrong or non-existent directories on any other machine).

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/app.py:113,128` and `settings_dialog.py` (all 6 sites): resolve via `get_config().resolve_path(...)` / `get_config().home_dir`; for the CODEBASE action, resolve the repo root from the package location or a config field, and hide the action when absent.
2. Add `tests/test_ui_widgets.py::test_no_hardcoded_project_paths`: grep `src/lucca/ui` for `C:\projects`/`C:/ProjectLucca`/`C:\ProjectLucca` literals → zero.

**Verification test**

- **Tier:** T0
- **Input:** the grep gate above
- **Expected output:** zero hard-coded roots in `src/lucca/ui`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_no_hardcoded_project_paths -q`

**Cross-references:** F-CORE-030, F-MEM-013, F-SBX-012, F-SENS-008

---

### F-UI-004 — The commorose CODEBASE action and help text advertise "read-only codebase inspection" that no tool provides

| Field | Value |
|---|---|
| **ID** | F-UI-004 |
| **Title** | The commorose CODEBASE action and help text advertise "read-only codebase inspection" that no tool provides |
| **Severity** | S2 — Medium |
| **Category** | UX |
| **Location** | `src/lucca/ui/app.py:125-130`; `src/lucca/ui/settings_dialog.py:2258,2331`; `docs/audit/findings/brain.md` F-BRAIN-004 |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/app.py:126-129`
```python
            CommoroseAction(
                "CODEBASE",
                "💻",
                lambda: _open_dir(r"C:\projects\ProjectLucca"),
                "Read-only codebase inspection",
            ),
```
(`settings_dialog.py:2331`: "Codebase Self-Inspection: Safe, read-only access to `C:\projects\ProjectLucca` allowing Lucca to discuss her own code" — the capability the system prompt also advertises (F-BRAIN-004) and no tool implements: `read_codebase_file` exists but is unregistered (F-SBX-012), and the commorose action merely opens Explorer for the *human*.)

**What is wrong / assumed / missing**

Three surfaces (system prompt, commorose, help tab) promise the companion can inspect its own code; the only real behaviour is Explorer opening a folder — which is the *user's* action, not Lucca's capability. The advertised Lucca-side capability does not exist.

**Why it matters**

The implementation prompt's mission ("every claim the UI makes must be verifiably real") is violated on three coordinated surfaces; the user asks "show me your code" and the companion has no tool to do it.

**Questions this raises**

1. None — Q-S-02 (SBX) already asks whether the capability should exist; this finding pins the UI-side claims.

**Proposed remediation**

1. In `src/lucca/ui/app.py:125-130`: relabel the action "OPEN PROJECT FOLDER" with description "Open the project directory in Explorer" (honest about what it does), or implement the capability per Q-S-02's outcome.
2. In `src/lucca/ui/settings_dialog.py:2258,2331`: align the help text to the same decision.
3. Joint with F-BRAIN-004 step 1 (system prompt) so all three surfaces agree.
4. Add `tests/test_ui_widgets.py::test_codebase_claims_honest`: assert the commorose description and help text no longer claim Lucca-side inspection (or that the tool exists, per Q-S-02).

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** claims match capability
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_codebase_claims_honest -q`

**Cross-references:** F-BRAIN-004, F-SBX-012, Q-S-02

---

### F-UI-005 — The settings dialog's rule editor and diagnostics tabs present fictional machinery as live

| Field | Value |
|---|---|
| **ID** | F-UI-005 |
| **Title** | The settings dialog's rule editor and diagnostics tabs present fictional machinery as live |
| **Severity** | S2 — Medium |
| **Category** | UX |
| **Location** | `src/lucca/ui/settings_dialog.py:272-273,2300-2302`; `docs/audit/findings/reas.md` F-REAS-003 |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/settings_dialog.py:272-273`
```python
                "state": "ACTIVE",
                "code": '(rule "npu-whisper-pin-v1"\n  :when (and (intent= "voice_input") (not (npu-active?)))\n  :plan (list (tool "restart_npu_subsystem") (say "Re-aligning voice stream to the AI Boost NPU!"))\n  :priority 95)',
```
(the rules tab ships a sample rule referencing `npu-active?` and `restart_npu_subsystem` — neither exists in `ALLOWED_OPS`/`STATE_PREDICATES` (`parser.py:31-83`) nor in any tool registry; the tab's help text (`:2300-2302`) describes "active MicroScheme LISP reasoning pathways" and "isolated gas budgets" — the editor only runs `parse_rule` (F-REAS wiring verdict), and the diagnostics tab renders `get_system_metrics`' fabricated NPU/iGPU rows (F-SBX-011).)

**What is wrong / assumed / missing**

The UI presents: a sample rule that fails the product's own static validation (unknown operator/predicate), a rule editor described as executing rules when it only parses, and hardware telemetry with fabricated statuses. A user pasting the shipped sample into the shipped editor gets a validation error for a non-existent primitive.

**Why it matters**

The UI is the trust surface between the user and the system's claims; three coordinated fabrications (sample rule, editor description, telemetry) teach the user to distrust every green check.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/settings_dialog.py:272-273`: replace the sample rule with one that validates — e.g. `(rule "open-calculator-v1" :when (intent= "launch_app") :plan (list (tool "launch_app" :app_name "calculator")) :priority 90)`.
2. In `:2300-2302`: reword the help text to "syntax validation via the MicroScheme parser; execution pending the rule engine wiring" (or wire the engine per F-REAS-003).
3. In the diagnostics tab: render F-SBX-011's honest unknowns instead of the fabricated rows.
4. Add `tests/test_ui_widgets.py::test_sample_rule_validates`: the shipped sample passes `parse_rule` + `validate_rule_static`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** sample rule validates
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_sample_rule_validates -q`

**Cross-references:** F-BRAIN-004, F-REAS-003, F-SBX-011, F-CORE-033

---

### F-UI-006 — The UI process never confirms the bus is alive: captions/state updates silently no-op if core binds late

| Field | Value |
|---|---|
| **ID** | F-UI-006 |
| **Title** | The UI process never verifies its ZMQ connections; a late-binding core silently deafens the UI |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/ui/app.py:81-83,421-425` |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/app.py:82-83`
```python
        self.ingest_sock = self.ctx.socket(zmq.PUSH)
        self.ingest_sock.connect(f"tcp://127.0.0.1:{self.config.ipc.ingest_port}")
```
(ZMQ `connect` is asynchronous and always "succeeds"; the bus listener polls with 100 ms timeouts and silently drops everything until core binds. There is no handshake, no retry-with-backoff logging, and no UI indication that captions/state updates are not flowing. The supervisor spawns the UI child before the orchestrator binds (F-CORE-028), so an early-quit or slow core leaves a live-looking UI that receives nothing.)

**What is wrong / assumed / missing**

No connectivity feedback: the user sees a sprite that never changes state and never shows captions, with no error anywhere (bus receive failures are swallowed at `:456-457`). Expected: a connection-status indicator (sprite theme `offline` exists for exactly this, `states.py:53-59`) driven by a real handshake (`sys.ping` on the ctl socket, which the audio/npu processes already answer).

**Why it matters**

The "UI is alive but deaf" state is indistinguishable from a hung core for the user; the S1 screenshot session showed the UI working, but nothing in the code guarantees it.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/app.py`: on startup and every 5 s, send `sys.ping` on a DEALER socket; on no pong within 2 s, set the sprite to `offline` theme and show a one-line caption "Waiting for Lucca core…"; on first pong, restore.
2. Add `tests/test_ui_widgets.py::test_ui_shows_offline_without_core` (T1, sockets stubbed): no pong → sprite state `offline`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** offline indication without a live core
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_ui_shows_offline_without_core -q`

**Cross-references:** F-CORE-005, F-SENS-013

---

### F-UI-007 — `ui.config_update` sends `llm_model` that core ignores (dead field relayed by the UI)

| Field | Value |
|---|---|
| **ID** | F-UI-007 |
| **Title** | The settings dialog's model switch persists config but the running core never reloads it |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/ui/app.py:387`; `src/lucca/core/orchestrator.py:198-222`; `docs/audit/findings/core.md` F-CORE-057 |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/app.py:387`
```python
                llm_model=new_config.get("llm_model"),
```
(core.md F-CORE-057 documents that `UIConfigUpdatePayload.llm_model` is accepted and relayed but never applied; the UI's own model-combo flow requires the Restart button to take effect — which the dialog does say — but the config-update channel still carries the field as if it were live.)

**What is wrong / assumed / missing**

Cross-referenced, not restated: the UI-side contribution is that `_send_config_update` includes the field unconditionally, so every persona/voice save also transmits a model change the core drops. The UI should either omit the field when unchanged or the payload field should be removed (F-CORE-057's remediation).

**Why it matters**

Dead-field traffic on the control channel; misleads future maintainers into believing model switching is hot.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/app.py:387`: send `llm_model` only when it differs from the last-sent value, or drop the key pending F-CORE-057's removal decision.
2. Covered by F-CORE-057's verification test.

**Verification test**

- **Tier:** T1
- **Input:** unchanged-model config update
- **Expected output:** `llm_model` omitted/None
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py -q -k config_update`

**Cross-references:** F-CORE-057, F-BRAIN-013

---

### F-UI-008 — `settings_dialog.py` is 2,466 lines / 120 KB with 10 tabs in one class

| Field | Value |
|---|---|
| **ID** | F-UI-008 |
| **Title** | `settings_dialog.py` is 2,466 lines / 120 KB — ~14 % of all `src/` lines in one module |
| **Severity** | S3 — Low |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/ui/settings_dialog.py:1-2466`; `docs/audit/03_BASELINE.md:194` |
| **Status** | OPEN |

**Evidence**

`03_BASELINE.md` §5.1 observation: "`src/lucca/ui/settings_dialog.py` is 2,100 lines / 120 KB, ~14 % of all `src/` lines in a single module" (now 2,466 total lines). The class builds 10 tabs, 2 QThread workers, and the model registry in one file.

**What is wrong / assumed / missing**

Monolithic UI module: every tab is a private method of one class, cross-referencing each other's widgets; the file already mixes concerns (persona prose, server control, model registry, whitelist editing, rule editing, log viewing). Any tab change risks the whole dialog; the 68 % coverage number hides that entire tabs are untested.

**Why it matters**

Maintainability: the remediation programme will touch this file for F-BRAIN-004/013, F-SBX-011/012, D-AUD-03 — each change compounds in the single class.

**Questions this raises**

1. None.

**Proposed remediation**

1. Split into `ui/settings/` package: `dialog.py` (shell), `persona_tab.py`, `voice_tab.py`, `llm_tab.py`, `whitelist_tab.py`, `rules_tab.py`, `diagnostics_tab.py`, `help_tab.py`, `workers.py` (the two QThreads). Mechanical extraction, no behaviour change.
2. Add an import-boundary test asserting no tab module imports another tab module.

**Verification test**

- **Tier:** T0
- **Input:** `uv run ruff check src/lucca/ui && uv run mypy --strict src/lucca/ui`
- **Expected output:** clean after the split
- **Threshold:** n/a — boolean
- **Command:** `uv run ruff check src/lucca/ui && uv run mypy --strict src/lucca/ui`

**Cross-references:** None

---

### F-UI-009 — The commorose FOLDERS/CODEBASE actions and several settings paths open Explorer via `subprocess.Popen` with no error handling

| Field | Value |
|---|---|
| **ID** | F-UI-009 |
| **Title** | The commorose FOLDERS/CODEBASE actions and HUD log-open use bare `explorer.exe` Popen with no error handling |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/ui/app.py:97-98`; `src/lucca/ui/telemetry_hud.py:367-368` |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/app.py:97-98`
```python
        def _open_dir(path: str) -> None:
            subprocess.Popen(["explorer.exe", path])
```
(no try/except; a missing path or a non-Windows host raises inside the Qt slot, surfacing as a silent callback failure or a traceback on the console.)

**What is wrong / assumed / missing**

Un-guarded subprocess in UI callbacks; on a path that doesn't exist Explorer shows an error dialog, on failure the exception vanishes into Qt's slot exception handling (which prints to stderr in PyQt6 and can be configured to abort).

**Why it matters**

Minor robustness; consistent with the UI's 0 % coverage — no test would catch a slot exception.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/app.py:97-98` and `telemetry_hud.py:367-368`: wrap in try/except with a `logger.warning("explorer_open_failed", path=…)`; verify the path exists first and show a Qt message box on failure.
2. Add `tests/test_ui_widgets.py::test_open_dir_missing_path_no_crash`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** no exception escapes the slot
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_open_dir_missing_path_no_crash -q`

**Cross-references:** None

---

### F-UI-010 — The telemetry HUD's close event can block the GUI thread for up to 500 ms waiting on the sampler

| Field | Value |
|---|---|
| **ID** | F-UI-010 |
| **Title** | The telemetry HUD's close event blocks the GUI thread up to 500 ms on the sampler thread |
| **Severity** | S3 — Low |
| **Category** | PERFORMANCE |
| **Location** | `src/lucca/ui/telemetry_hud.py:349-352` |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/telemetry_hud.py:349-351`
```python
        self.poll_timer.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(500)
```
(`TelemetryWorker.run` calls `get_system_metrics()`, which shells out to `nvidia-smi` with a 2 s timeout (`system_tools.py:39`) — a slow WMI/nvidia-smi call holds `closeEvent` for up to 500 ms of GUI freeze.)

**What is wrong / assumed / missing**

Blocking `wait()` on the UI thread contradicts the worker's stated purpose ("preventing GUI hitching", `:48`). Expected: detach (daemon-style) and let the finished signal be dropped, or cache the last metrics and never block.

**Why it matters**

GUI hitch on HUD close; small but on the interaction path.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/telemetry_hud.py:349-351`: remove the `wait(500)`; connect `TelemetryWorker.finished` to a safe cleanup and let the thread finish detached (QThread parented to the widget already prevents premature destruction).
2. Add `tests/test_ui_widgets.py::test_hud_close_does_not_block` (timing assertion ≤ 50 ms with a stubbed slow sampler).

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** close returns ≤ 50 ms with a slow sampler
- **Threshold:** ≤ 50 ms
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_hud_close_does_not_block -q`

**Cross-references:** F-CORE-017

---

### F-UI-011 — The sprite's `degraded` theme is unreachable: no code emits the state

| Field | Value |
|---|---|
| **ID** | F-UI-011 |
| **Title** | The sprite's `degraded` theme is unreachable: no component ever emits the state |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/ui/states.py:60-67`; `docs/audit/findings/core.md` §3.1 (`degraded` never assigned) |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/states.py:60-67` defines a full `degraded` theme; core.md §3.1 documents that the orchestrator's `degraded` state is declared but never assigned — so `sprite.set_state("degraded")` can never be reached through the bus.

**What is wrong / assumed / missing**

The visual language for "system unhealthy" exists and is dead, while the conditions that should trigger it (llama-server down, sandbox unavailable, integrity failure) are all real states the product can enter silently.

**Why it matters**

The UI has no way to look unhealthy — the user cannot distinguish "thinking" from "broken".

**Questions this raises**

1. None.

**Proposed remediation**

1. In the F-CORE-005 remediation (supervisor degradation), publish `ui.state=degraded` when a child dies or the LLM is unreachable; the sprite side already works.
2. Add `tests/test_ui_widgets.py::test_degraded_theme_reachable`: emit `ui.state=degraded` → sprite theme switches.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** degraded theme applied
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_degraded_theme_reachable -q`

**Cross-references:** F-CORE-005, F-CORE-033, F-UI-006

---

### F-UI-012 — The commorose PERSONA/VOICE/TOOLS actions open hard-coded tab indices that silently break on tab reordering

| Field | Value |
|---|---|
| **ID** | F-UI-012 |
| **Title** | The commorose PERSONA/VOICE/TOOLS actions open hard-coded tab indices that silently break on tab reordering |
| **Severity** | S3 — Low |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/ui/app.py:116-124,321-325` |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/app.py:117`
```python
                "PERSONA", "🧠", lambda: self._open_settings_tab(0), "Switch persona profile"
```
(`_open_settings_tab` at `:321-325` does `tabs.setCurrentIndex(index)` with magic numbers 0/1/3; the tab order is defined in `settings_dialog.py`'s builder with no shared constants.)

**What is wrong / assumed / missing**

Index-based tab navigation couples two files by invisible contract; inserting a tab reorders every commorose shortcut to the wrong pane with no error.

**Why it matters**

Fragile coupling across a 2,466-line dialog (F-UI-008's structure problem made user-visible).

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/settings_dialog.py`: expose `TAB_INDEX = {"persona": 0, "voice": 1, "tools": 3, …}` (or `tab_widget_index(name)`); in `app.py`, use the named constants.
2. Add `tests/test_ui_widgets.py::test_commorose_tab_targets_resolve`: assert each named tab index maps to a tab whose title contains the expected keyword.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** named navigation survives reordering
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_commorose_tab_navigation -q`

**Cross-references:** F-UI-008

---

### F-UI-013 — The sprite's mouth aperture maps raw dBFS linearly with no noise gate: idle-room noise flaps the mouth

| Field | Value |
|---|---|
| **ID** | F-UI-013 |
| **Title** | The sprite's mouth aperture maps raw dBFS linearly with no noise gate or smoothing |
| **Severity** | S4 — Info |
| **Category** | UX |
| **Location** | `src/lucca/ui/sprite.py:99-111`; `src/lucca/senses/audio_proc.py:194-203` |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/sprite.py:99-100`
```python
    def set_mouth_aperture(self, dbfs: float) -> None:
        """Scales dBFS (-60 to -10) to mouth aperture (0.0 to 1.0)."""
```
(the audio process publishes `audio.rms` for every playing callback with no gate below the −50 dBFS first-sample threshold — ambient noise during playback modulates the mouth; no smoothing/attack-release is applied.)

**What is wrong / assumed / missing**

Lip-flap driven by raw RMS: background noise and sibilants produce jitter; there is no attack/release envelope. Informational: cosmetic fidelity of the avatar.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/sprite.py`, `set_mouth_aperture`: apply a one-pole smoothing (attack 30 ms / release 120 ms) and a −45 dBFS gate.
2. Add `tests/test_ui_widgets.py::test_mouth_aperture_smoothed`: alternating loud/quiet frames → monotone-ish aperture, no full-swing flicker.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** smoothed aperture
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_mouth_aperture_smoothed -q`

**Cross-references:** None

---

### F-UI-014 — The settings dialog constructs `MemoryManager()` against the production database on open

| Field | Value |
|---|---|
| **ID** | F-UI-014 |
| **Title** | The settings dialog constructs `MemoryManager()` against the production database on open, with failures silently swallowed |
| **Severity** | S2 — Medium |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/ui/settings_dialog.py:254-257`; `docs/audit/findings/mem.md` F-MEM-001/F-MEM-013 |
| **Status** | OPEN |

**Evidence**

`src/lucca/ui/settings_dialog.py:254-257`
```python
        try:
            self.memory_manager: MemoryManager | None = MemoryManager()
        except Exception:
```
(`MemoryManager()` with no args opens `C:\ProjectLucca\data\memory.sqlite` — the production DB — from the UI process; the except swallows the exception type entirely, leaving `memory_manager = None` with no user-visible degraded state; combined with F-MEM-001's gate bypass, this is the write path.)

**What is wrong / assumed / missing**

The UI opens the production memory DB eagerly on dialog open (even if the user never visits the memory tab), with a silent failure mode. Expected: lazy construction on first memory-tab use, config-anchored path, and a visible "memory unavailable" state on failure.

**Why it matters**

Cross-process SQLite access to the production DB from a UI dialog, plus a silent None that turns every memory-tab action into a no-op.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ui/settings_dialog.py:254-257`: construct lazily on first memory-tab activation; log the exception with type; show "Memory subsystem unavailable" in the tab when None.
2. Add `tests/test_ui_widgets.py::test_memory_manager_lazy_and_visible_failure`: broken DB path → tab shows unavailable, no crash.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** lazy construction; visible degraded state
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_memory_manager_lazy -q`

**Cross-references:** F-MEM-001, F-MEM-013

---

### F-UI-015 — The commorose and tray duplicate five actions with divergent labels and no shared definition

| Field | Value |
|---|---|
| **ID** | F-UI-015 |
| **Title** | The commorose and tray/context menus duplicate actions with divergent labels and no shared definition |
| **Severity** | S4 — Info |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/ui/app.py:100-131,154-186,188-239` |
| **Status** | OPEN |

**Evidence**

Three menus define overlapping actions independently: tray ("💬 Quick Chat Bar", "⚙️ Settings & Diagnostics", "Show / Hide Avatar", "🔁 Reset Avatar Position", "Quit Lucca" — `:158-180`), context menu ("💬 Quick Chat Bar (Double-Click)", "📌 Always on Top", "✕ Quit Lucca", `:213-237`), commorose (8 actions, `:100-131`). Labels, emoji, and behaviour sets differ across the three; adding an action requires touching all three sites.

**What is wrong / assumed / missing**

No single action registry; drift is already visible (tray lacks Always-on-Top; context menu labels differ from tray). Informational maintainability.

**Questions this raises**

1. None.

**Proposed remediation**

1. Define a single `UI_ACTIONS` registry (id, label, icon, handler) in `ui/app.py` and render tray/context/commorose from it.
2. Add `tests/test_ui_widgets.py::test_action_registry_single_source`: every menu action id appears in the registry.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** one source of truth
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_ui_widgets.py::test_action_registry -q`

**Cross-references:** F-UI-008

---

## 4. Assumptions register

| # | Location | Assumption embedded in code | Why unverified | Risk if false |
|---|---|---|---|---|
| A-U-01 | `app.py:67-69` | `assets/icon.png` is reachable via cwd or `home_dir/assets` | cwd-dependent first branch (F-CORE-030 pattern) | Missing taskbar/tray icon on non-default installs |
| A-U-02 | `app.py:78` | Always-on-top default is wanted | No persisted preference; resets every launch | User preference not remembered |
| A-U-03 | `app.py:421-460` | The bus delivers every caption reliably (SUB with no SNDHWM concerns) | PUB/SUB drop semantics under slow subscriber; Qt signal queue absorbs | Missed captions under burst (F-CORE-046's quadratic traffic) |
| A-U-04 | `settings_dialog.py:90` | 25 s is enough for a model reload + health | Measured cold start 13.93 s warm; cold-from-nothing ~42 s (fabricated constant, F-BRAIN-007) | Restart reports failure on a healthy slow start |
| A-U-05 | `speech_bubble.py:60` | 22 ms typewriter tick is comfortable | No user testing recorded | Cosmetic |
| A-U-06 | `telemetry_hud.py:94` | 1 s polling of nvidia-smi/psutil is cheap | `nvidia-smi` subprocess per second while HUD visible (measured 2.65 s cold in S1_01; warm ~50 ms) | CPU cost while HUD open |
| A-U-07 | `sprite.py` | The sprite sheet atlas indices match `assets/sprites/lucca/manifest.json` | Not verified in this subtask (asset-level) | Wrong frames displayed |
| A-U-08 | `app.py:55` | AppUserModelID "…0.2" is stable | Version drift (F-CORE-051) | Taskbar grouping quirks |

## 5. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-U-01 | Should the CODEBASE commorose action exist at all (it opens Explorer, not a Lucca capability)? | F-UI-004 / Q-S-02 alignment | owner |
| Q-U-02 | Should the latency badge be wired to real traces (F-UI-001 step 2) or removed? | Honesty vs feature | owner |
| Q-U-03 | Is the 10-tab settings suite the intended final shape (D-AUD-03 strips CT identity from persona; tabs reference CT styling)? | Post-D-AUD-03 UI scope | owner |

## 6. Coverage gaps

### 6.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| Bus→widget caption/state/confirm delivery | Spec 01 §4 | none (`app.py` 0 %) |
| Commorose radial menu interactions | Charter §2.1 shipped feature | none (0 %) |
| Honest latency display | impl. prompt mission | none (fabricated — F-UI-001) |
| UI-quit shutdown announcement | Spec 01 §7 | none (F-UI-002) |
| Server restart worker end-to-end | impl. prompt WI-3.3 | worker logic untested (lines 97-120 uncovered); depends on dead `stop_server` scoping (F-BRAIN-024) |
| Model download worker validation | impl. prompt WI-4.4 | none (lines 123+ uncovered) |
| VRAM fit guard | impl. prompt WI-4.6 | none (lines 1223-1232 uncovered) |
| Confirmation buttons → `ui.confirm_result` | Spec 01 §6 | none on the UI side (`speech_bubble.py:322-374` uncovered) |
| Hard-coded path elimination | F-CORE-030 family | none (F-UI-003) |

### 6.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| `tests/test_ui_widgets.py` | UI widget behaviour | Widget construction/geometry only; no IPC, no settings-dialog flows, no commorose (0 %), no app wiring |
| `settings_dialog.py` persona preview (68 % cov) | Truthful compiled prompt preview | Preview correctness tested; the save→core propagation gap (F-BRAIN-013) is not |

## 7. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** Reviewing F-UI-001 (fake latency badge) enumerated its sibling fabricated displays and placed the whole family in one cross-reference set. Reviewing F-UI-002 (quit without announcement) cross-checked the S1 stderr artefact (≥ 807 lines) and pinned the UI-side half of the shutdown defect. Reviewing F-UI-008 (monolith) surfaced the hard-coded-path cluster F-UI-003 and the tab-index fragility F-UI-012.
2. **Unasked questions.** 2 registered (§5) plus the carried Q-S-02; decisions recorded in findings (F-UI-001: hide-until-measured; F-UI-010: detach-not-wait; F-UI-011: supervisor publishes degraded).
3. **Unwarranted assumptions.** The first draft claimed the restart worker was "fake" per the implementation prompt's D1 — corrected after reading `settings_dialog.py:82-120`: the worker is real (the D1 defect was fixed); the remaining gap is that it bypasses the dead `restart_server` and uses a 25 s timeout against a 42 s fabricated cold start (A-U-04). F-UI-013 was graded S4 (cosmetic).
4. **Incomplete planning.** Every remediation names file, function, before/after, and a runnable command; the owner-owned calls (CODEBASE capability, latency badge fate, CT styling post-D-AUD-03) are parked as Q-U-01…03.
5. **Architectural flaws → F-ARCH candidates.** (a) F-UI-001/004/005: the UI is the third surface (with the system prompt and `query_capabilities`) advertising capabilities that do not exist — folded into the F-BRAIN-004 honesty F-ARCH; (b) F-UI-002 completes the shutdown-order finding family (F-CORE-005/006/029) — the UI side was the missing publisher.

Severity re-grades during the pass: F-UI-001 kept S1 (permanent fabricated measurement on the primary widget); F-UI-002 kept S1 (only user-initiated shutdown path is broken); F-UI-006 S2→S3 (mitigated by ZMQ connect semantics and the supervisor's co-spawn timing); F-UI-013 set S4.
