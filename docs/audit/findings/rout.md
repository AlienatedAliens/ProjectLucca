# Findings — ROUT (`src/lucca/router/**`)

**Subtask:** S2d · **Method:** static line-by-line · **Baseline:** HEAD `ed14f6b` + working tree per `03_BASELINE.md`, delta in [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) (router modules: **unchanged since S0**) · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; every finding cites `file:line` in the current tree. Core/MEM/brain findings cross-referenced by ID.

**Severity totals: S0 = 0 · S1 = 0 · S2 = 4 · S3 = 6 · S4 = 1 · total = 11.**

---

## 1. Module map

Coverage from `docs/audit/evidence/S1_14_coverage.txt` rows 50–52. LOC = non-blank lines (S0 metric, verified unchanged by `03b_BASELINE_DELTA.md`).

| File | LOC | Public symbols | Responsibilities (as-built) | Live callers in product path? | Outbound dependencies | Cov % | Tests exercising it |
|---|---:|---|---|---|---|---:|---|
| `router/heuristic.py` | 332 | `DEFAULT_KNOWN_APPS`, `DEFAULT_STOP_WORDS_AFTER_START`, `FILE_PATTERN`, `URL_PATTERN`, `QUOTED_PATTERN`, `HeuristicRouter` (`classify_intent`, `route`, `record_post_turn`) | Regex intent classification + entities; 3-branch action decision; JSONL + SQLite decision telemetry | **no** — no construction site in `src/` outside `router/` (F-CORE-003) | `structlog`, `memory.db`, `core.schemas` | 84 % | `tests/test_router.py` (T-RTR-01/03/04) |
| `router/labeler.py` | 174 | `NEGATION_REGEX`, `derive_label`, `persist_decision_label`, `check_data_volume_gate` | Ground-truth auto-labelling (8-priority ladder); label persistence; Phase-6 data-volume gate | **no** — pure functions with no caller in `src/` | `memory.db`, `core.schemas` | **100 %** | `tests/test_router.py` (T-RTR-05/11) |
| `router/conformal.py` | 51 | `ConformalGuard` (`fit`, `predict_set`, `decide`) | Split-conformal prediction sets; ambiguous-set → LLM fallback policy | **no** — no caller anywhere in `src/` | `numpy`, `core.exceptions` | 87 % | `tests/test_router.py` (T-RTR-06/07/08) |

**Wiring verdict:** the entire router area is **dead in the product path** — `HeuristicRouter`, `ConformalGuard`, `derive_label`, `persist_decision_label`, `check_data_volume_gate` have zero call sites outside `router/` and `tests/` (consistent with F-CORE-003). Consequence specific to this area: the `decisions`/`decision_labels`/`vec_decisions` tables (migration `0002_decisions.sql`) are never populated in production, so the Phase-6 data-volume gate (`labeler.py:188-195`) is permanently `blocked` and the ≥ 600-labelled-decision human gate (Charter §5.3) is unattainable without wiring — see F-ROUT-001.

## 2. As-built behaviour

### 2.1 Decision logic (`heuristic.py:180-269`)

`route()` computes `elapsed_us`, classifies intent (pure telemetry), then decides by exactly three inputs:

| Condition (first match wins) | Action | Probabilities written |
|---|---|---|
| `any_active_rule_fired` | RULE | `{"RULE": 0.90, "LLM": 0.05, "CLARIFY": 0.05}` (`:209`) |
| `vad_speech_ms < 400 or (conf < 0.35 and not any_active_rule_fired)` | CLARIFY | `{"CLARIFY": 0.90, ...}` (`:210-212`) |
| else | LLM | `{"LLM": 0.90, ...}` (`:213-215`) |

The classified intent **never selects an action** — a `launch_app` intent at confidence 0.95 routes to LLM exactly as `unknown`@0.20 does (only the conf<0.35 CLARIFY branch reads it). The classified entities (app/file/url/quoted) are stored in `RouteFeatures` for telemetry only. `prediction_set` is always the singleton `[action]`; `fallback_applied` always `False`; `calibrated` always `False` — the conformal path is never engaged.

### 2.2 Intent lexicon (`heuristic.py:100-178`)

| Intent | Trigger | Conf | Notes |
|---|---|---|---|
| `launch_app` | `\b(open\|launch\|start\|run)\b` + known-app substring in candidate, **or** unknown candidate of ≤ 2 words | 0.95 / 0.85 | substring match `app_name in candidate_app` (`:133`); stop-word guard for "start with…" (`:130`); lexicon from `intents.toml` `[intents.launch_app].apps` merged over `DEFAULT_KNOWN_APPS` (`:88-90`) |
| `file_read` / `file_write` | verb regex **and** a filename entity (`FILE_PATTERN`: txt/md/py/json/csv/pdf/docx only) | 0.90 | `:141-152` |
| `web_fetch` | verb regex **or** any URL entity | 0.90 | `:155-157` |
| `memory_query` | verb/phrase regex | 0.90 | `:160-164` |
| `chit_chat` | greeting regex | 0.95 | `:167-172` |
| `clarify` | single-word utterance | 0.40 | `:175-176` |
| `unknown` | fallback | 0.20 | `:178` |

### 2.3 Telemetry

`route()` writes a `DecisionRecord` to `logs/…jsonl` (append, no rotation, `:282-283`) and/or the `decisions` table (`:285-323`, all exceptions swallowed to warnings). `record_post_turn()` (`:325-369`) updates tool outcomes/barge-in on the DB row and the in-memory `last_decision_record`. **Both loggers have no production caller** (the router is unwired), so today the tables are empty and the only rows ever written were in tests.

### 2.4 Labelling & gate (`labeler.py`)

`derive_label` is an 8-priority pure-function ladder (early-barge-in → confirm-declined → negation → tool-failed → rule-would-match → rule-wrong → clarify-useful → implicit-ok POS default). `persist_decision_label` upserts into `decision_labels`. `check_data_volume_gate` enforces the Phase-6 thresholds: ≥ 600 labelled, ≥ 20 sessions, ≥ 14-day span, ≥ 30 per class in the newest-100 split (`:188-195`) — matching Spec 06 §5 and Charter §5.3's human-gate floor.

### 2.5 Conformal guard (`conformal.py`)

Textbook split-conformal: `fit` requires `n ≥ ⌈1/α⌉−1` (`:28-32`), computes `q_hat` at the `⌈(n+1)(1−α)⌉/n` quantile with `method="higher"` (`:34-41`); `predict_set` returns classes with `1−p ≤ q_hat` (`:43-46`); `decide` acts on singleton sets and falls back to `"LLM"` otherwise (`:48-63`). Component is correct and tested (T-RTR-06/07/08) — and completely unwired: no classifier produces probabilities anywhere, no caller constructs the guard.

---

## 3. Findings

Ordered by severity, then by ID. Every finding re-reviewed per Charter §3.5 (log in §7); `Status: OPEN`.

### F-ROUT-001 — The Phase-4 router is entirely unwired: decision/label tables can never populate and the Phase-6 data gate is permanently blocked

| Field | Value |
|---|---|
| **ID** | F-ROUT-001 |
| **Title** | The Phase-4 router is entirely unwired: decision/label tables can never populate and the Phase-6 data gate is permanently blocked |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/router/heuristic.py:55`; `src/lucca/router/labeler.py:188-195`; `src/lucca/core/orchestrator.py` (no router import); `docs/archive/2026-09-17_pre_phase4_audit/13_decisions_log.md` (commit `b75ce27` claims "complete Phase 4 Executive Router") |
| **Status** | OPEN |

**Evidence**

A repo-wide search for `HeuristicRouter|ConformalGuard|derive_label|persist_decision_label|check_data_volume_gate` returns hits only inside `src/lucca/router/` and `tests/` — no construction or call site in `main.py`, `orchestrator.py`, or any process entry point. `03_BASELINE.md` §3 records commit `b75ce27`: "feat(router): complete Phase 4 Executive Router, Decision Logging & Auto-Labeling + Affect Layer".

**What is wrong / assumed / missing**

The router, labeller, and conformal guard exist as tested components and are referenced by nothing. Consequences specific to this area (the turn-loop absence itself is F-CORE-003, not restated here): (a) `decisions`/`decision_labels`/`vec_decisions` (migration `0002_decisions.sql`) accumulate zero production rows; (b) `check_data_volume_gate` can only ever return `blocked` (`labeler.py:197`) because there is nothing to count; (c) the Phase-6 human gate (≥ 600 labelled decisions, Charter §5.3) is unattainable until the router is wired and real usage accrues; (d) commit history claims the phase complete.

**Why it matters**

Phased-build discipline (Charter §5.3) rests on sign-off bundles describing reality; a "completed" Phase 4 whose deliverable is unreachable code means the ≥ 600-decision data floor and the ≥ 1 promoted rule gate (which needs labelled real usage) cannot be satisfied by any amount of time — only by the wiring work the phase was supposed to have delivered.

**Questions this raises**

1. None — the wiring plan belongs to the F-CORE-003 remediation; this finding pins the ROUT-side deliverable gap.

**Proposed remediation**

1. In `src/lucca/core/orchestrator.py` (CORE-area change, joint with F-CORE-003): construct `HeuristicRouter(db=DatabaseManager(), log_path=logs/decisions.jsonl)` and call `route()` per turn; call `record_post_turn()` after each turn with tool outcomes and barge-in data.
2. In the turn-loop post-turn stage: call `derive_label(...)` + `persist_decision_label(...)` for the previous decision once the next-turn transcript is available (the Spec 06 §4 data flow).
3. Add `tests/test_router.py::test_orchestrator_writes_decisions` (T2): run a scripted turn through the wired orchestrator; assert a `decisions` row and a `decision_labels` row exist.

**Verification test**

- **Tier:** T2
- **Input:** the test above
- **Expected output:** ≥ 1 decision + label row per turn; `check_data_volume_gate` counts them
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py::test_orchestrator_writes_decisions -q`

**Cross-references:** F-CORE-003, F-CORE-035, F-MEM-007 (same unwiring family)

---

### F-ROUT-002 — Classified intent never influences the routing action; the "deterministic router" routes nothing deterministically

| Field | Value |
|---|---|
| **ID** | F-ROUT-002 |
| **Title** | Classified intent never influences the routing action; the "deterministic router" routes nothing deterministically |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/router/heuristic.py:202-215` |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:207-215`
```python
        if any_active_rule_fired:
            action_lit: Literal["RULE", "LLM", "CLARIFY"] = "RULE"
            probs = {"RULE": 0.90, "LLM": 0.05, "CLARIFY": 0.05}
        elif vad_speech_ms < 400 or (conf < 0.35 and not any_active_rule_fired):
            action_lit = "CLARIFY"
            probs = {"CLARIFY": 0.90, "LLM": 0.05, "RULE": 0.05}
        else:
            action_lit = "LLM"
            probs = {"LLM": 0.90, "RULE": 0.05, "CLARIFY": 0.05}
```
(`intent` from `classify_intent` at `:202` is used only as `conf` input and telemetry; there is no `intent == "launch_app" → RULE`-style mapping anywhere.)

**What is wrong / assumed / missing**

The component's documented purpose (Spec 06 §1: deterministic State→Plan routing ahead of neural inference; the system prompt even advertises "MicroScheme … execute in sub-10ms before neural inference") requires intents like `launch_app`/`file_read`/`file_write` to route to the rule path. As-built, the only path to `RULE` is `any_active_rule_fired` — a flag fed by the (unwired) rule engine — so even a perfect `launch_app`@0.95 classification routes to LLM. Which side is right: the spec — the whole Phase-4 premise is deterministic routing of deterministic intents.

**Why it matters**

Combined with F-ROUT-001 this means the shipped "Executive Router" cannot execute a single deterministic route; the latency benefit the architecture promises (rule path before LLM) is structurally unreachable, and the decision telemetry being collected would train a classifier to imitate a router that never used its own classifications.

**Questions this raises**

1. Should intent→RULE mapping live in the heuristic (lexical intents → candidate rule lookup) or wait for the rule engine's own matcher? (→ §5 Q-R-01.)

**Proposed remediation**

1. In `src/lucca/router/heuristic.py`, `route()`: add an intent→action branch before the LLM default — `if intent in INTENT_TO_RULE and conf >= 0.80 and any rule exists for the intent: action = "RULE"` with probabilities derived from a calibration table, not constants (see F-ROUT-005). Before: intent ignored. After: deterministic intents route to RULE per Spec 06 §1.
2. Add `tests/test_router.py::test_launch_intent_routes_to_rule`: `route("open the calculator", intent_conf=0.95)` with a registered calculator rule → action `RULE`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** `RouteAction.RULE`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py::test_launch_intent_routes_to_rule -q`

**Cross-references:** F-ROUT-001, F-ROUT-005, F-CORE-003

---

### F-ROUT-003 — The launch lexicon advertises apps the tool whitelist forbids (`cmd`, `powershell`, `code`, `vscode`)

| Field | Value |
|---|---|
| **ID** | F-ROUT-003 |
| **Title** | The launch lexicon advertises apps the tool whitelist forbids (`cmd`, `powershell`, `code`, `vscode`) |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/router/heuristic.py:27-42`; `config/intents.toml:7`; `config/tool_whitelist.toml:4-32`; `docs/audit/evidence/S1_12_T1_unit.txt` (T1 log: `launch_not_whitelisted app=cmd`, `app=powershell`) |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:27-42`
```python
DEFAULT_KNOWN_APPS: Final[frozenset[str]] = frozenset(
    {
        "calculator",
        "calc",
        "notepad",
        "text editor",
        "browser",
        "edge",
        "chrome",
        "terminal",
        "cmd",
        "powershell",
        "code",
        "vscode",
    }
)
```
(`config/tool_whitelist.toml` contains exactly: calculator, notepad, browser, terminal, task_manager — no `cmd`, `powershell`, `code`, `vscode`, and no `task_manager` alias in the router lexicon; S1's T1 run logged `launch_not_whitelisted app=cmd` and `app=powershell`, row 22 of the evidence index.)

**What is wrong / assumed / missing**

Three lexicons define "launchable" differently: the router's built-in set, `intents.toml` (which adds nothing but matches the built-ins), and `tool_whitelist.toml` (the enforcement truth, which also contains `task_manager` the router does not know). The router will confidently classify "open cmd" as `launch_app`@0.95 with `entities.app=["cmd"]`, and the launcher will then refuse it — measured in the T1 sandbox logs. Conversely "open task manager" does not hit the router's known-app list (only the ≤ 2-word unknown-candidate fallback at 0.85).

**Why it matters**

A router that classifies un-launchable apps as high-confidence launch intents guarantees user-facing refusal loops ("opening cmd… I can't do that") once wired; and the missing `task_manager` alias means the one whitelisted app in S6's own test set is the one the lexicon does not know.

**Questions this raises**

1. None — `tool_whitelist.toml` is the enforcement truth (SBX area); the lexicons must derive from it.

**Proposed remediation**

1. In `src/lucca/router/heuristic.py`: replace `DEFAULT_KNOWN_APPS` with a load from `config/tool_whitelist.toml` aliases (the same file `sandbox/launcher.py:54` enforces), falling back to the current set only when the file is absent; delete `cmd`/`powershell`/`code`/`vscode` from the fallback or add them to the whitelist (owner decision; the whitelist is the security boundary — do not widen it to match the lexicon).
2. In `config/intents.toml:7`: align `[intents.launch_app].apps` to the whitelist aliases.
3. Add `tests/test_router.py::test_lexicon_matches_whitelist`: assert every router-known app resolves in the launcher whitelist and vice versa (excluding intentional aliases).

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** router lexicon ⊆ whitelist aliases ∪ declared aliases
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py::test_lexicon_matches_whitelist -q`

**Cross-references:** F-BRAIN-027, F-MEM-027 n/a; SBX launcher (T-SBX-14)

---

### F-ROUT-004 — App matching uses substring containment and accepts unknown 2-word candidates as launch intents

| Field | Value |
|---|---|
| **ID** | F-ROUT-004 |
| **Title** | App matching uses substring containment and accepts unknown 2-word candidates as launch intents |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/router/heuristic.py:126-138` |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:132-138`
```python
                for app_name in self.known_apps:
                    if app_name in candidate_app:
                        entities["app"].append(app_name)
                        return "launch_app", 0.95, entities
                if not entities["file"] and len(candidate_app.split()) <= 2:
                    entities["app"].append(candidate_app)
                    return "launch_app", 0.85, entities
```

**What is wrong / assumed / missing**

Two false-positive paths: (a) substring containment — known app `"code"` matches any candidate containing it (`"open barcode generator"` → launch `code`@0.95; `"open terminal encoder"` → `terminal`); (b) the ≤ 2-word fallback brands **any** unknown two-word object of "open/start/run" as a launch intent at 0.85 (`"open pod bay"` → `launch_app`, app `"pod bay"`). Word-boundary protection exists for the *verb* (`\b(open|…)\b`) but not for the *app* match. Expected: token-boundary or alias-exact matching, and unknown candidates should route to CLARIFY, not a fabricated launch.

**Why it matters**

These classifications are recorded as decision telemetry (feeding future classifier labels per F-ROUT-005's probability fabrication) and, once the router is wired (F-ROUT-001/002), become confident RULE routes to a launcher that must refuse — a guaranteed bad interaction class invisible in tests because T-RTR-01 only tests the adversarial *verb* cases.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/router/heuristic.py:132`: match with a word-boundary regex built from escaped aliases (`r"\b" + re.escape(app_name) + r"\b"`) instead of `in`; delete the ≤ 2-word unknown fallback (`:136-138`) and let unknown candidates fall through to `clarify`/`unknown`.
2. Add `tests/test_router.py::test_t_rtr_02_app_boundary_adversarial`: `"open barcode generator"`, `"open pod bay"` → **not** `launch_app`; `"open the calculator app"` → `launch_app` calculator (positive retained).

**Verification test**

- **Tier:** T1
- **Input:** the adversarial set above
- **Expected output:** no false launch classification; positives retained
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py::test_t_rtr_02_app_boundary_adversarial -q`

**Cross-references:** F-ROUT-003

---

### F-ROUT-005 — Decision probabilities are hard-coded constants recorded as if they were model outputs

| Field | Value |
|---|---|
| **ID** | F-ROUT-005 |
| **Title** | Decision probabilities are hard-coded constants recorded as if they were model outputs |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/router/heuristic.py:209,212,215` |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:215`
```python
            probs = {"LLM": 0.90, "RULE": 0.05, "CLARIFY": 0.05}
```
(written verbatim into `decisions.probabilities_json` at `:306` and the JSONL log; every decision of an action class carries the identical fabricated distribution.)

**What is wrong / assumed / missing**

The heuristic emits a constant pseudo-distribution per action branch. Nothing today consumes it (the router is unwired), but the recorded purpose of the telemetry (Spec 06 §3/§4) is to train and calibrate the Phase-6 classifier — which would be fit against invented probabilities, and `ConformalGuard.fit` (whose whole contract is finite-sample guarantees on real scores) would be calibrated on constants, silently voiding its coverage guarantee.

**Why it matters**

Garbage-in at the telemetry layer poisons the exact Phase-6 pipeline the data gate is meant to protect; the fix is trivial now and painful after 600 labelled decisions accumulate.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/router/heuristic.py`: either (a) record `probabilities` as `null` with `router_version="heuristic-1.0-deterministic"` so downstream knows no distribution exists, or (b) emit the intent confidence in the action's slot and `1−conf` spread across the others — decision recorded: **(a)**, honest absence beats fabricated numbers. Before: constants. After: null + version marker.
2. Add `tests/test_router.py::test_t_rtr_03_no_fabricated_probabilities`: assert `decision.probabilities is None` for heuristic routes (update T-RTR-03's assertions accordingly).

**Verification test**

- **Tier:** T1
- **Input:** the updated T-RTR-03
- **Expected output:** `probabilities` null; version string carries `-deterministic`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py::test_t_rtr_03_no_fabricated_probabilities -q`

**Cross-references:** F-ROUT-002, F-CORE-041 (sibling fabricated-telemetry finding)

---

### F-ROUT-006 — `derive_label` checks confirm-declined before explicit negation, contradicting its documented priority order

| Field | Value |
|---|---|
| **ID** | F-ROUT-006 |
| **Title** | `derive_label` checks confirm-declined before explicit negation, contradicting its documented priority order |
| **Severity** | S3 — Low |
| **Category** | SPEC-DRIFT |
| **Location** | `src/lucca/router/labeler.py:41-77` |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/labeler.py:43-46` (docstring)
```python
    Priority 1: User barged in <= 1.5 s after playback started -> NEG (early_bargein)
    Priority 2: Next transcript matches negation lexicon -> NEG (explicit_negation)
    Priority 3: Any tool call ok=False (timeout, non-zero exit, schema error) -> NEG (tool_failed)
    Priority 4: Confirm flow answered 'no' -> INDETERMINATE (user_declined)
```
(code order at `:59-77`: Priority 1 → **confirm_declined** (`:68-69`) → **negation** (`:72-73`) → tool-failed.)

**What is wrong / assumed / missing**

The implementation evaluates `confirm_declined` (documented Priority 4) **before** `explicit_negation` (documented Priority 2). Where both signals fire (user declines a confirmation and then says "no, stop"), the code labels `INDETERMINATE/user_declined` where the documented order labels `NEG/explicit_negation`. Which side is right: defensible either way, but the docstring is the spec's restatement (Spec 06 §4) and the docstring and code must agree — decision recorded: **the code order is wrong** (a negation following a decline is stronger evidence of a bad route than the decline alone; INDETERMINATE should be the narrower case).

**Why it matters**

Label semantics feed the Phase-6 classifier and the human gate; a priority inversion that mislabels NEG as INDETERMINATE systematically shrinks the usable NEG set in exactly the confirmation-heavy turns the confirmation flow produces.

**Questions this raises**

1. None — order corrected to match the documented priority.

**Proposed remediation**

1. In `src/lucca/router/labeler.py`: move the `confirm_declined` block (`:67-69`) after the negation block (`:71-73`). Before: confirm → negation. After: negation → confirm (P1, P2, P3, P4 as documented).
2. Add `tests/test_router.py::test_t_rtr_05b_negation_outranks_decline`: both signals set → assert `NEG/explicit_negation`.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** `NEG` with `explicit_negation`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py::test_t_rtr_05b_negation_outranks_decline -q`

**Cross-references:** None

---

### F-ROUT-007 — `HeuristicRouter.route` violates the `RouterPort` signature

| Field | Value |
|---|---|
| **ID** | F-ROUT-007 |
| **Title** | `HeuristicRouter.route` violates the `RouterPort` signature |
| **Severity** | S3 — Low |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/ports.py:96-99`; `src/lucca/router/heuristic.py:180-196` |
| **Status** | OPEN |

**Evidence**

`src/lucca/ports.py:96-99`
```python
class RouterPort(Protocol):
    """..."""

    def route(self, feats: RouteFeatures) -> RouteDecision: ...
```
(`HeuristicRouter.route(self, transcript: str, any_active_rule_fired: bool = False, …13 parameters…) -> RouteDecision` — the port takes a `RouteFeatures` object the router builds internally at `:229-245` and never accepts.)

**What is wrong / assumed / missing**

Same defect class as F-CORE-040 (ports declared for a call model nothing implements): `RouterPort` cannot be satisfied by the only router that exists, and the port's `route(feats)` shape discards the telemetry inputs (trace_id, session_id, VAD, tool history) the implementation needs. The hexagonal boundary is decorative.

**Why it matters**

Any future wiring that goes "through the port" (import-linter discipline, F-CORE-034) cannot construct a conforming adapter without re-plumbing; the mismatch is the router-side half of the core typing-model finding.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/ports.py` (CORE-area change): redefine `RouterPort.route(self, transcript: str, *, features: RouteFeatures | None = None, **telemetry) -> RouteDecision` to match the implementation, or (preferred per F-CORE-040's resolution) move `RouteFeatures` construction into callers and keep `route(feats)`. Decision recorded: keep `route(feats)` and make `HeuristicRouter.route` accept `RouteFeatures` plus a `telemetry: DecisionTelemetry` object carrying the 13 fields.
2. Add a mypy-verified conformance test: `_: RouterPort = HeuristicRouter(db=None)` in `tests/test_router.py::test_router_satisfies_port`.

**Verification test**

- **Tier:** T0
- **Input:** `uv run mypy --strict src`
- **Expected output:** assignment type-checks
- **Threshold:** n/a — boolean
- **Command:** `uv run mypy --strict src/lucca/router src/lucca/ports.py`

**Cross-references:** F-CORE-040, F-CORE-034

---

### F-ROUT-008 — The decisions JSONL log is appended without rotation or size bound

| Field | Value |
|---|---|
| **ID** | F-ROUT-008 |
| **Title** | The decisions JSONL log is appended without rotation or size bound |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/router/heuristic.py:282-283` |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:282-283`
```python
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
```

**What is wrong / assumed / missing**

One decision per turn, appended forever to a single file with no rotation, retention, or size guard — the `traces.jsonl` defect (F-CORE-056) in a second file. Each record embeds the full transcript (`payload["transcript"]`), so the file also grows with unbounded user text.

**Why it matters**

Unbounded disk growth containing transcripts; same evidence-retention hygiene gap as the core trace file.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/router/heuristic.py`: rotate at 10 MB to `decisions-<UTC timestamp>.jsonl`, keep 5 (the F-CORE-056 remediation should define one shared rotation helper — reuse it here).
2. Add `tests/test_router.py::test_decision_log_rotates`: write past the threshold with a patched size; assert a rotated file appears and the active file is fresh.

**Verification test**

- **Tier:** T1
- **Input:** the rotation test above
- **Expected output:** rotated files capped at 5
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py::test_decision_log_rotates -q`

**Cross-references:** F-CORE-056

---

### F-ROUT-009 — Decision telemetry failures are swallowed to warnings at both write sites

| Field | Value |
|---|---|
| **ID** | F-ROUT-009 |
| **Title** | Decision telemetry failures are swallowed to warnings at both write sites |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/router/heuristic.py:322-323, 357-358` |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:322-323`
```python
        except Exception as exc:  # noqa: BLE001
            logger.warning("decision_sqlite_log_failed", error=str(exc))
```
(identical pattern in `record_post_turn` at `:357-358`; JSONL failures at `:282-283` are not caught at all — an unwritable log path raises out of `route()`.)

**What is wrong / assumed / missing**

Telemetry write failures degrade to a one-line warning with no counter, no backoff, and no surfacing — while the sibling JSONL path *crashes* `route()` on the same class of failure. Two different failure policies for the same concern, both wrong in opposite directions: the DB path silently loses the Phase-6 dataset; the JSONL path can kill the (future) turn thread on a disk-full.

**Why it matters**

The Phase-6 dataset is the audit-critical artefact (Charter §5.3 human gates); silent partial loss invalidates the data gate's counts. And a telemetry crash on the turn path would be a F-CORE-007-class silent turn failure.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/router/heuristic.py`: introduce a single `_log_failure(kind: str, exc: Exception)` that warns **and** increments a `self.telemetry_failures` counter; catch the JSONL write with the same handler. Before: divergent policies. After: uniform warn+count; `route()` never raises for telemetry.
2. Add `tests/test_router.py::test_telemetry_failure_never_raises_and_counts`: unwritable log path + broken db → `route()` returns a decision, counter == 2.

**Verification test**

- **Tier:** T1
- **Input:** the failure-injection test above
- **Expected output:** decision returned; failures counted
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py::test_telemetry_failure_never_raises_and_counts -q`

**Cross-references:** F-CORE-044, F-ROUT-008

---

### F-ROUT-010 — `ConformalGuard` is dead: the calibrated-classifier path (Spec 06 §7) is unimplemented end-to-end

| Field | Value |
|---|---|
| **ID** | F-ROUT-010 |
| **Title** | `ConformalGuard` is dead: the calibrated-classifier path (Spec 06 §7) is unimplemented end-to-end |
| **Severity** | S4 — Info |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/router/conformal.py:14-63`; `src/lucca/core/config.py` (`router.version`); `src/lucca/router/heuristic.py:225` (`calibrated=False` hard-coded) |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:224-225`
```python
            prediction_set=[route_action],
            fallback_applied=False,
            calibrated=False,
```
(a repo-wide search finds no construction of `ConformalGuard` outside `tests/`; no classifier training/inference code exists in `src/`; `config.router.version` is written but never branched on.)

**What is wrong / assumed / missing**

The conformal decision policy — singleton set acts, ambiguous set falls back to LLM, with finite-sample coverage — exists as a tested component and is referenced by nothing: no feature extractor, no trained model artifact, no fit/predict call site, and the heuristic hard-codes `calibrated=False`. The Spec 06 §7 architecture (heuristic now → classifier after the data gate) is half-built by design; this finding pins the missing half so the Phase-6 plan inherits an accurate inventory.

**Why it matters**

Informational: the component is correct and its tests (T-RTR-06/07/08) demonstrate the intended behaviour; the gap is the missing classifier + wiring, which is a scheduled phase deliverable, not a defect in shipped behaviour.

**Questions this raises**

1. None — the sequencing (data gate → train → calibrate → wire) is already specified; F-ROUT-005 flags the telemetry quality prerequisite.

**Proposed remediation**

1. Record in the Phase-6 plan: `ConformalGuard` wiring requires (a) F-ROUT-001's telemetry flowing, (b) F-ROUT-005's honest probabilities or real classifier outputs, (c) `check_data_volume_gate` passing, before `calibrated=True` can ever be written.
2. No code change in this audit.

**Verification test**

- **Tier:** n/a — documentation pin
- **Input:** n/a
- **Expected output:** Phase-6 plan references F-ROUT-010's prerequisites
- **Threshold:** n/a
- **Command:** n/a

**Cross-references:** F-ROUT-001, F-ROUT-005, F-CORE-003

---

### F-ROUT-011 — Dead condition: `conf < 0.35 and not any_active_rule_fired` in the CLARIFY branch

| Field | Value |
|---|---|
| **ID** | F-ROUT-011 |
| **Title** | Dead condition: `conf < 0.35 and not any_active_rule_fired` in the CLARIFY branch |
| **Severity** | S3 — Low |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/router/heuristic.py:210` |
| **Status** | OPEN |

**Evidence**

`src/lucca/router/heuristic.py:207-212`
```python
        if any_active_rule_fired:
            action_lit: Literal["RULE", "LLM", "CLARIFY"] = "RULE"
            probs = {"RULE": 0.90, "LLM": 0.05, "CLARIFY": 0.05}
        elif vad_speech_ms < 400 or (conf < 0.35 and not any_active_rule_fired):
```

**What is wrong / assumed / missing**

The `elif` is only reached when `any_active_rule_fired` is `False`, so the second conjunct `not any_active_rule_fired` is always `True` — dead code that suggests the author intended rule-fired turns to be immune to CLARIFY via a single compound condition, then restructured into the `if`/`elif` without cleaning up. Harmless today; misleading to the next maintainer and to any future refactor that reorders the branches.

**Why it matters**

Pure clarity defect; flagged because it sits in the decision core of the area's one live-behaviour function.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/router/heuristic.py:210`: simplify to `elif vad_speech_ms < 400 or conf < 0.35:`. Before: dead conjunct. After: equivalent, clear.
2. No behavioural change; existing T-RTR tests are the verification.

**Verification test**

- **Tier:** T1
- **Input:** existing `tests/test_router.py` suite
- **Expected output:** identical results pre/post change
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_router.py -q`

**Cross-references:** None

---

## 4. Assumptions register

| # | Location | Assumption embedded in code | Why unverified | Risk if false |
|---|---|---|---|---|
| A-R-01 | `heuristic.py:209-215` | The 0.90/0.05/0.05 distributions are meaningful telemetry | Constants (F-ROUT-005) | Classifier/calibration trained on fabricated scores |
| A-R-02 | `heuristic.py:44-46` | The conf<0.35 CLARIFY threshold separates ambiguous utterances | No threshold calibration data; T-RTR-01 tests lexicon only | Over/under-clarification on real speech |
| A-R-03 | `labeler.py:103` | Absence of negative signals implies success (POS `implicit_ok`) | Standard implicit-feedback assumption; no precision measurement exists | Label noise biased positive; classifier learns to please |
| A-R-04 | `labeler.py:63` | ≤ 1500 ms barge-in means the route was wrong | A barge-in may mean the *reply* was wrong, not the route | Route-quality signal diluted by TTS-content failures |
| A-R-05 | `labeler.py:89` | Re-asking the same intent ≤ 30 s means the rule was wrong | User may re-ask for variations | Good rules labelled NEG |
| A-R-06 | `conformal.py:56` | Default class order `["RULE", "LLM", "CLARIFY"]` matches training label indices | No training pipeline exists to pin the order | Silent class permutation when the classifier lands |
| A-R-07 | `heuristic.py:255` | Wall-clock `time.time()` is adequate for decision telemetry | Cross-process clock concerns (F-CORE-008/061) | Span/session maths distorted |

## 5. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-R-01 | Should deterministic intents route to RULE via the heuristic's lexicon, or via the rule engine's own matcher once wired? | F-ROUT-002 remediation shape; risks double-matching | architect |
| Q-R-02 | Should `cmd`/`powershell`/`code`/`vscode` be *added to the whitelist* (user wants them launchable?) or removed from the lexicon? | F-ROUT-003; widening the whitelist is a security decision | owner |
| Q-R-03 | Is `decision_labels` intended to be re-writable (upsert) after the data gate counts it? | Relabelling after gate evaluation could game the ≥ 600 floor | owner / architect |

## 6. Coverage gaps

### 6.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| Intent→RULE deterministic routing | Spec 06 §1 | none (feature absent — F-ROUT-002) |
| Lexicon/whitelist consistency | TM-14 / T-SBX-14 | none (mismatched — F-ROUT-003) |
| App-match word-boundary adversarials | Spec 06 §2 | verb cases only (T-RTR-01); app-substring cases absent (F-ROUT-004) |
| Real-probability telemetry | Spec 06 §3 | none (constants recorded — F-ROUT-005) |
| `derive_label` priority order as documented | Spec 06 §4 | tests never fire P2+P4 together (F-ROUT-006) |
| Router→port conformance | Spec 02 (`RouterPort`) | none (signature mismatch — F-ROUT-007) |
| Log rotation for decisions JSONL | Spec 11 retention | none (F-ROUT-008) |
| Conformal wiring (`calibrated=True` path) | Spec 06 §7 | component-tested only; end-to-end absent by design (F-ROUT-010) |

### 6.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| `test_router.py::test_t_rtr_05_auto_labeling_30_pairs` | auto-labelling engine | `derive_label` on synthetic pairs with hand-fed signals; no real decision stream exists (F-ROUT-001) — the labelling *engine* is tested, the labelling *pipeline* does not exist |
| `test_router.py::test_t_rtr_11_data_volume_gate` | Phase-6 eligibility gate | gate maths on seeded rows; production rows can never exist (F-ROUT-001) |
| `test_router.py::test_t_rtr_07_synthetic_conformal_coverage` | conformal coverage guarantee | correct on synthetic data; nothing produces real probabilities to guarantee coverage over (F-ROUT-010) |

## 7. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** Reviewing F-ROUT-001 (unwired) surfaced the ROUT-specific consequences that F-CORE-003 does not carry (empty telemetry tables, blocked Phase-6 gate, the `b75ce27` "complete" claim) — kept as a separate finding per the no-restatement rule, cross-linked. Reviewing F-ROUT-002 (intent ignored) surfaced the fabricated probabilities it feeds on → F-ROUT-005, and the dead conjunct → F-ROUT-011. Reviewing F-ROUT-003 (lexicon mismatch) surfaced the substring-matching sibling → F-ROUT-004.
2. **Unasked questions.** 3 registered (§5); answerable ones were resolved in the findings (F-ROUT-005 records the null-probabilities decision; F-ROUT-006 records the priority-order correction).
3. **Unwarranted assumptions.** The first draft of F-ROUT-004 claimed `"open the pod bay doors"` mis-classifies — verified against the ≤ 2-word fallback before citing (3-word candidates are excluded; the 2-word `"open pod bay"` case is the real one). F-ROUT-010 was graded S4 after confirming the missing classifier is a scheduled phase deliverable, not a defect in shipped behaviour. The conformal component itself was verified correct against the split-conformal construction before declaring it merely dead.
4. **Incomplete planning.** Every remediation names file, function, before/after, and a runnable command; the one owner-owned call (whitelist widening) is parked as Q-R-02 with a recorded default (do not widen the security boundary to match the lexicon).
5. **Architectural flaws → F-ARCH candidates.** (a) F-ROUT-001/002 together mean the architecture's central latency mechanism (deterministic routing before neural inference) is unreachable — the same programme-level unwiring family as F-CORE-003/F-MEM-007, recommended for a single F-ARCH "Phase 3–4 subsystems unwired" finding; (b) F-ROUT-005's fabricated telemetry is the sibling of F-CORE-009/041 (telemetry that records what the code wishes, not what happened) — recommended for an F-ARCH "honesty of recorded metrics" finding.

Severity re-grades during the pass: F-ROUT-002 kept S2 (unreachable behaviour of an unwired component — would be S1 the moment F-ROUT-001's wiring lands); F-ROUT-004 kept S2 (measured false-positive class, upstream of the launcher's refusal); F-ROUT-010 set S4 (scheduled deliverable, tested component).
