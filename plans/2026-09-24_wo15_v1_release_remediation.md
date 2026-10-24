# Work Order 15 — v1.0 Release Remediation

**Status:** OPEN
**Supersedes:** the certification claims in `luccadocs/audit/findings/V1_RELEASE_AUDIT.md` made by commit `08e2aa6`
**Tag policy:** `v1.0.0` currently points at `08e2aa6`. It is NOT to be pushed. It will be deleted and re-created at the end of Phase 7 only if every gate below is green.
**Assignee:** Gemini (Antigravity)
**Reviewer:** Owner, using the Evidence file produced by this WO

---

## 0. Why this WO exists (read before touching anything)

The review of `08e2aa6` found that the release audit certified things the code does not do. Concretely:

| Claim in `V1_RELEASE_AUDIT.md` | Reality at `08e2aa6` |
|---|---|
| "wired the final C1 … Conformal Routing Abstention paths" | `ConformalGuard(` has zero call sites in `src/`. `orchestrator.py:320` builds `HeuristicRouter(db=..., log_path=...)` with no guard. Production router returns `calibrated=False` on every turn. |
| C1 acceptance PASS, Wilson LB 0.8308 | Measured on a test-local router with a guard fitted on **10 hand-typed probability vectors**. The 5 "live" turns went through the unguarded production router and only asserted a non-empty reply. `has_registered_rule` was derived from the probe's own ground-truth label. |
| "Non-parametric historical episode lookup" (Recall) | `ReplayEngine.recall_past_episodes` has zero callers. Its logic was duplicated inline into `cascade.py`. |
| "0 lint violations across all active docs" | The lint covers 4 files. `luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md` still says the brain is `Mistral-NeMo-12B` (lines 13, 151). The WO-14 plan's own Phase 1 gate required that file be rewritten; it was not touched. |
| — | Two new mypy errors at `heuristic.py:310` and `:359` (`list[float]` annotation vs `dict[str, float]` schema); a `# type: ignore[assignment]` added at `:320`. |
| — | With a guard present, `heuristic.py:300` silently drops the `conf >= 0.80` requirement for `RULE`. Latent because unwired; would fire `RULE` at `conf=0.61` if wired as-is. |

The pattern was: implement something adjacent to the requirement, write a test that exercises the adjacent thing, print PASS, mark DONE. **This WO is structured so that pattern cannot pass.** Every phase ends with structural checks (mostly `git grep`) whose output is pasted verbatim into the Evidence file. A phase is not DONE until its Evidence block is filled in and matches the expected pattern.

---

## 1. Rules of engagement (binding)

1. **Evidence file.** Create `luccadocs/audit/findings/WO15_EVIDENCE.md` at the start. For every phase, paste the exact command and its **verbatim** output under a heading `## Phase N — <name>`. No summaries, no paraphrase, no "output omitted". If output exceeds 200 lines, paste the first 40 and last 40 with a line count.
2. **No self-authored gates.** Do not add, weaken, or reinterpret any gate in this document. If a gate is impossible, stop and write `BLOCKED: <reason>` in the Evidence file under that phase. Do not proceed to a later phase.
3. **Red before green.** Where this WO says "must fail first", run the test, paste the failing output, then make the change, then paste the passing output. A phase with only the green output is incomplete.
4. **Forbidden constructs** in any file touched by this WO: `# type: ignore`, `# noqa: S110`, `except Exception: pass`, `pytest.skip` (except for the single llama-server health check in `hw`-marked tests), printing a verdict string before the corresponding `assert`.
5. **"Wired" has one meaning.** A symbol is wired only if `git grep` shows a call site inside `src/lucca/core/orchestrator.py` or `src/lucca/core/turn_pipeline.py` or a module they import at construction time. A test constructing the symbol is not wiring.
6. **Do not edit** `luccadocs/audit/findings/V1_RELEASE_AUDIT.md` until Phase 6. **Do not touch** the git tag until Phase 7.
7. **Shell.** The terminal in this workspace is `cmd.exe`. Use `&&` for chaining, `findstr` not `grep`/`Select-String`, `type` not `cat`, `dir /b` not `ls`. `git grep` works everywhere.
8. Commit after each phase with message `WO-15 Phase N: <name>`. Do not squash.

---

## 2. Phase map & milestones

| Phase | Deliverable | Milestone check (pasted in Evidence) |
|---|---|---|
| 1 | Router correctness fixes | mypy clean on `heuristic.py`; new gate test red→green |
| 2 | Real calibration + production wiring | `git grep "conformal_guard="` hits `orchestrator.py`; orchestrator test proves `calibrated=True` |
| 3 | Recall dedup | `recall_past_episodes` has exactly 1 def + 1 call site in `src/`, call site in `cascade.py` |
| 4 | C1 acceptance gate rebuilt | Gate uses `orch.router`; live-turn abstention asserted; offline variant runs in normal suite |
| 5 | Docs + lint coverage | Lint red on user guide → rewrite → lint green with 10 files covered |
| 6 | Audit amendment | Every row in §3 of the audit cites a test or grep that exists |
| 7 | Verification & re-tag | Full suite 0 failed, ruff/lint-imports clean, HW gate PASS, tag recreated |

---

## 3. PHASE 1 — Router correctness fixes

**Files:** `src/lucca/router/heuristic.py`, `tests/test_router.py`

### 3.1 Baseline (must fail first)

```
uv run mypy src/lucca/router/heuristic.py 2>&1 | findstr /C:"heuristic.py"
```
Expected before fix: two lines, `:310` and `:359`. Paste them.

### 3.2 Changes

1. Line ~292: change `probabilities: list[float] | None = None` to `probabilities: dict[str, float] | None = None`.
2. Remove `# type: ignore[assignment]` at ~320. Replace with an explicit mapping:
   ```python
   _ACTION_LIT: Final[dict[str, Literal["RULE", "LLM", "CLARIFY"]]] = {
       "RULE": "RULE", "LLM": "LLM", "CLARIFY": "CLARIFY",
   }
   ...
   action_lit = "LLM" if fallback_applied else _ACTION_LIT[conf_action]
   ```
   Put `_ACTION_LIT` at module level next to `INTENT_TO_RULE`.
3. Restore the RULE confidence gate inside the conformal branch. The RULE candidate condition in the guarded branch must be **identical** to the unguarded one:
   ```python
   rule_eligible = any_active_rule_fired or (
       intent in INTENT_TO_RULE and conf >= 0.80 and (has_registered_rule or any_active_rule_fired)
   )
   ```
   Use `rule_eligible` in both the guarded and unguarded branches. Extract it above the `if EMERGENCY_REFLEX_PATTERN` block so there is one definition.
4. **Always** compute the probability vector and populate `probabilities`, whether or not a guard is present. The guard only changes whether `decide()` is consulted. This is required so that `decisions.probabilities_json` accumulates real calibration data from the first turn (Phase 2 depends on it). Vector construction (order `[RULE, LLM, CLARIFY]`):
   - `rule_eligible` → `[conf, 1-conf, 0.0]`
   - `vad_speech_ms < 400 or intent == "clarify" or (intent in INTENT_TO_RULE and conf < 0.35 and not any_active_rule_fired)` → `[0.0, 1-conf, conf]`
   - otherwise → `[0.0, conf, 1-conf]`
   Assert the vector sums to 1.0 within 1e-9 (a `ValueError` if not — this is a programmer error, not a runtime condition).

### 3.3 Tests to add to `tests/test_router.py`

```python
def test_conformal_branch_respects_rule_conf_gate():
    """Guarded router must NOT route RULE when intent conf < 0.80, even with a registered rule."""
    # fit any valid guard (10 vectors is fine here — this is a unit test of the gate, not of calibration)
    # monkeypatch router.classify_intent to return ("launch_app", 0.61, {"app": ["calculator"]})
    # route("open calculator", has_registered_rule=True)
    # assert decision.action != RouteAction.RULE

def test_conformal_branch_routes_rule_at_high_conf():
    # same guard; classify_intent -> ("launch_app", 0.95, ...)
    # assert decision.action == RouteAction.RULE and decision.calibrated is True

def test_probabilities_always_populated_without_guard():
    # HeuristicRouter() with no guard; for transcripts hitting all three branches:
    # assert decision.probabilities is not None
    # assert abs(sum(decision.probabilities.values()) - 1.0) < 1e-9
    # assert decision.calibrated is False

def test_probabilities_is_dict_str_float():
    # assert isinstance(decision.probabilities, dict) and all(isinstance(v, float) for v in ...)
```

`test_conformal_branch_respects_rule_conf_gate` **must fail first** against the unmodified `heuristic.py` (it will route RULE at 0.61). Paste red, then green.

### 3.4 Evidence block

```
uv run mypy src/lucca/router/heuristic.py 2>&1 | findstr /C:"heuristic.py"
   -> expected: no output
git grep -n "type: ignore" -- src/lucca/router/heuristic.py
   -> expected: no output
git grep -n "rule_eligible" -- src/lucca/router/heuristic.py
   -> expected: exactly 1 assignment + ≥2 uses
uv run python -m pytest tests/test_router.py -q
   -> expected: all pass, count ≥ previous + 4
```

---

## 4. PHASE 2 — Real calibration and production wiring

**Files:** new `src/lucca/router/calibration.py`, `src/lucca/core/orchestrator.py`, `config/intents.toml`, new `tests/test_router_calibration.py`

### 4.1 `src/lucca/router/calibration.py`

```python
CLASS_ORDER: Final[tuple[str, str, str]] = ("RULE", "LLM", "CLARIFY")

def load_labelled_decisions(db: DatabaseManager, limit: int = 500) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """
    Pull calibration pairs from the `decisions` table. Deterministic, no LLM.
    Row is usable iff: probabilities_json is non-null and parses to all three CLASS_ORDER keys,
                       fallback_applied == 0  (abstentions carry no ground truth about the right class).
    Label rule:
      action == "RULE" and tool_ok == 1            -> 0 (RULE was right)
      action == "RULE" and tool_ok == 0            -> 1 (RULE was wrong; LLM should have handled it)
      action == "LLM"  and user_interrupted == 0   -> 1
      action == "CLARIFY"                          -> 2
      anything else                                -> skip
    Returns (probs[n,3], labels[n]). n may be 0.
    """

def fit_guard_from_db(db: DatabaseManager, alpha: float = 0.10, min_samples: int = 30) -> ConformalGuard | None:
    """
    Returns a fitted ConformalGuard, or None if fewer than min_samples usable rows
    or ConformalGuard.fit raises InsufficientCalibration. Never raises.
    Logs structlog event "conformal_guard_fit" with fitted: bool, n: int, q_hat: float | None.
    """
```

No `Any`. Parse JSON into `dict[str, JsonValue]` and coerce with explicit `float()`.

### 4.2 `config/intents.toml`

Append:
```toml
[router]
confidence_threshold = 0.60
conformal_alpha = 0.10
conformal_min_samples = 30
```
`HeuristicRouter._load_intents_config` already reads `router.confidence_threshold`. Extend it to also read the two new keys into `self.conformal_alpha` and `self.conformal_min_samples` (defaults 0.10 / 30).

### 4.3 `orchestrator.py` — the actual wiring

Replace line 320:
```python
log_path = self.config.home_dir / "logs" / "decisions.jsonl"
intents_cfg = self.config.resolve_path("config/intents.toml")
guard = fit_guard_from_db(self.db) if self.db is not None else None
self.router = HeuristicRouter(
    db=self.db,
    log_path=log_path,
    config_path=intents_cfg if intents_cfg.exists() else None,
    conformal_guard=guard,
)
logger.info(
    "router_constructed",
    conformal_fitted=guard is not None and guard.q_hat is not None,
    q_hat=None if guard is None else guard.q_hat,
)
```
Read `alpha`/`min_samples` from the same TOML (load it once here with `tomllib`, or add a small helper in `calibration.py` — either is fine; do not duplicate the parsing logic in two places).

### 4.4 Tests — `tests/test_router_calibration.py`

Use `DatabaseManager(tmp_path / "x.sqlite"); db.migrate()` and the `_insert_decision` helper pattern from `tests/test_l3_lifecycle_proof.py:27` (copy it into a shared `tests/helpers/decisions.py` and import from both — do not leave two copies).

```python
def test_fit_guard_returns_none_on_empty_db()
def test_fit_guard_returns_none_below_min_samples()        # 29 rows -> None
def test_fit_guard_fits_at_min_samples()                    # 30 rows -> q_hat is float in [0,1]
def test_label_rule_rule_failure_maps_to_llm()              # action=RULE, tool_ok=0 -> label 1
def test_fallback_rows_excluded()                           # fallback_applied=1 rows never counted
def test_rows_without_probabilities_skipped()
def test_orchestrator_router_uncalibrated_on_empty_db()
    # build orchestrator with fakes (see tests/test_a1_runtime_wiring.py / test_orchestrator_parity.py
    # for the existing construction pattern); assert orch.router.conformal_guard is None
    # route one turn; assert decision.calibrated is False and decision.probabilities is not None
def test_orchestrator_router_calibrated_with_seeded_history()
    # seed 40 labelled decisions into the orchestrator's db BEFORE constructing the orchestrator
    # assert orch.router.conformal_guard is not None and .q_hat is not None
    # route "open calculator" with has_registered_rule=True; assert decision.calibrated is True
```

The last two tests are the wiring proof. They must construct the orchestrator through its real `__init__`, not by assigning `orch.router = ...` afterwards.

### 4.5 Evidence block

```
git grep -n "conformal_guard=" -- src/
   -> expected: exactly one hit, in src/lucca/core/orchestrator.py
git grep -n "fit_guard_from_db" -- src/
   -> expected: def in calibration.py + 1 call in orchestrator.py
git grep -n "_insert_decision" -- tests/
   -> expected: 1 def (tests/helpers/decisions.py) + imports only; no second def
uv run mypy src/lucca/router/calibration.py src/lucca/router/heuristic.py 2>&1 | findstr /C:"router\\"
   -> expected: no output
uv run python -m pytest tests/test_router_calibration.py tests/test_router.py -q
   -> expected: all pass
```

---

## 5. PHASE 3 — Recall deduplication

**Files:** new `src/lucca/reasoning/recall.py`, `src/lucca/reasoning/replay.py`, `src/lucca/core/cascade.py`, `tests/test_conformal_recall.py`, new test in `tests/test_epistemic_cascade.py`

### 5.1 `src/lucca/reasoning/recall.py`

Move `ReplayEngine.recall_past_episodes` (replay.py:103–232) here as a module-level function. Imports allowed: `json`, `re`, `structlog`, `lucca.memory.db.DatabaseManager`, `lucca.core.schemas.JsonValue`. **Do not** import `lucca.reasoning.scheme.*` — this module must stay cheap for the cascade to import.

```python
RECALL_STOP_WORDS: Final[frozenset[str]] = frozenset({...})   # union of the two stop-word lists currently in replay.py and cascade.py
def tokenize_query(query_text: str) -> list[str]
def recall_past_episodes(db: DatabaseManager, query_text: str, limit: int = 5) -> list[RecallEpisode]
```

Define `RecallEpisode` as a Pydantic model in `src/lucca/core/schemas.py` (not a bare dict):
```python
class RecallEpisode(BaseModel):
    source: Literal["decisions", "execution_triples"]
    record_id: str
    ts: float
    match_score: int          # tokens matched
    tokens_total: int         # tokens in query after stop-word removal
    summary: str              # one-line human-readable, e.g. "Historical turn 'open calculator': routed RULE via ACT_THEN_NARRATE (succeeded)"
    payload: dict[str, JsonValue]
```

### 5.2 `replay.py`

Delete `recall_past_episodes` from `ReplayEngine`. Delete the `import re` if now unused. Do **not** leave a delegating stub.

### 5.3 `cascade.py`

In `query_substrate_self_history` (line 962), replace **both** inline blocks (execution_triples at 1002–1031 and decisions at 1033–1080) with:
```python
episodes = recall_past_episodes(db, query_text, limit=10)
for ep in episodes:
    items.append(EvidenceItem(
        substrate=EpistemicSubstrate.SELF_HISTORY,
        trust_tier=TrustTier.TIER_1_HARDWARE,
        source=f"history:{ep.source}:{ep.record_id}",
        content=ep.summary,
        polarity=BelnapValue.TRUE,
        confidence=min(1.0, ep.match_score / max(1, ep.tokens_total)),
        metadata={"match_score": ep.match_score, "tokens_total": ep.tokens_total, **ep.payload},
    ))
```
Keep the existing "2. Query memories for autobiographical classes" block untouched. Remove the inline tokenizer (975–999) — use `tokenize_query`. Any `except Exception: pass` in this function becomes `logger.debug("self_history_recall_error", error=str(exc))`.

### 5.4 Tests

- `tests/test_conformal_recall.py`: change imports to `from lucca.reasoning.recall import recall_past_episodes`; assert return items are `RecallEpisode`.
- Add to `tests/test_epistemic_cascade.py`:
  ```python
  def test_self_history_substrate_delegates_to_recall(monkeypatch):
      # monkeypatch lucca.core.cascade.recall_past_episodes with a spy returning one RecallEpisode(match_score=1, tokens_total=2, ...)
      # call cascade.query_substrate_self_history("open calculator")
      # assert spy called once; assert items[0].confidence == 0.5; assert "match_score" in items[0].metadata
  def test_self_history_confidence_scales_with_match():
      # real tmp db, seed 2 decisions: one matching 1/3 tokens, one matching 3/3; assert confidences 1/3 and 1.0 (±1e-9)
  ```

### 5.5 Evidence block

```
git grep -n "recall_past_episodes" -- src/
   -> expected: exactly 2 lines: the def in reasoning/recall.py and the call in core/cascade.py
git grep -n "def recall_past_episodes" -- src/lucca/reasoning/replay.py
   -> expected: no output
git grep -n -c "FROM decisions" -- src/lucca/core/cascade.py
   -> expected: no output (the query now lives in recall.py only)
git grep -n "except Exception:.*pass\|noqa: S110" -- src/lucca/core/cascade.py src/lucca/reasoning/recall.py
   -> expected: no output
uv run lint-imports
   -> expected: "Contracts: 6 kept, 0 broken"
uv run python -m pytest tests/test_conformal_recall.py tests/test_epistemic_cascade.py tests/test_l2_replay_and_contrastive.py -q
   -> expected: all pass
```

---

## 6. PHASE 4 — C1 acceptance gate rebuilt

**Files:** `tests/test_c1_abstention_acceptance.py`, new `tests/fixtures/router/calibration_seed.jsonl`, new `scripts/export_calibration_seed.py`

### 6.1 Calibration seed with stated provenance

Write `scripts/export_calibration_seed.py`:
- If `C:\ProjectLucca\data\memory.sqlite` exists and `load_labelled_decisions` yields ≥ 60 rows → export those rows (probabilities, action, tool_ok, user_interrupted, transcript) to `tests/fixtures/router/calibration_seed.jsonl` with header line `{"_provenance": "exported from live data/memory.sqlite on <ISO date>, n=<N>"}`.
- Otherwise → generate the seed by routing every transcript in `tests/fixtures/router/router_fixtures.jsonl` through an **unguarded** `HeuristicRouter`, recording its `probabilities`, and labelling with the fixture's expected action; header `{"_provenance": "synthetic: router_fixtures.jsonl routed through unguarded HeuristicRouter on <ISO date>, n=<N>"}`.
- Either way n ≥ 60. Run the script; commit the fixture. **Paste the header line in Evidence.** Hand-typing probability vectors is prohibited.

### 6.2 Rebuild the test

```python
@pytest.mark.hw
def test_c1_conformal_abstention_acceptance(tmp_path):
    # 1. llama-server health check (the ONLY permitted pytest.skip)
    # 2. orch, db, _ = _make_hw_orchestrator(tmp_path)  -- BEFORE constructing, seed db from calibration_seed.jsonl
    #    (adjust _make_hw_orchestrator or add a `pre_seed` callback so seeding happens before Orchestrator.__init__)
    # 3. assert orch.router.conformal_guard is not None and orch.router.conformal_guard.q_hat is not None,
    #    "production router is not calibrated — wiring failure, not a skip condition"
    # 4. For each of the 100 PROBES:
    #       has_rule = _has_registered_rule_for(orch, text)   # see 6.3 — NEVER from probe["category"]
    #       decision = orch.router.route(text, has_registered_rule=has_rule)
    #       assert decision.calibrated is True
    #       record abstained = decision.fallback_applied
    # 5. Live path (≥ 6 turns, not 5, through _invoke_text_turn):
    #       for text, expect_abstain in [("bake a chocolate cake", True), ("tell me something random", True),
    #                                    ("fold the laundry on the bed", True), ("read the file notes.txt", False),
    #                                    ("what is my name", False), ("hello Lucca", False)]:
    #           reply = _invoke_text_turn(orch, text, trace_id)
    #           assert reply
    #           rec = orch.router.last_decision_record
    #           assert rec is not None and rec.fallback_applied == expect_abstain, f"live path: {text}"
    # 6. metrics: precision Wilson LB, accuracy Wilson LB, false_abstention_rate
    # 7. asserts FIRST:
    #       assert len(results) >= 100
    #       assert prec_lb >= 0.80
    #       assert acc_lb >= 0.80
    #       assert false_abstentions / 50 <= 0.10
    # 8. THEN write JSON report and print banner with verdict computed as "PASS" (only reachable if asserts passed)
```

### 6.3 No label leakage

```python
def _has_registered_rule_for(orch, transcript: str) -> bool:
    intent, _, _ = orch.router.classify_intent(transcript)
    tool = INTENT_TO_RULE.get(intent)
    if tool is None:
        return False
    return any(r.status == "ACTIVE" and tool in r.tools_referenced for r in orch.rule_engine.rules.values())
```
If `ManagedRule` has no `tools_referenced` (check `lifecycle.py`), use whatever attribute records the rule's target tool; if none exists, add `tools_referenced: frozenset[str]` populated at registration. The probe's `category` field is used **only** for reporting, never as router input. Add an assertion in the test body: `assert "category" not in inspect.signature(orch.router.route).parameters` is silly — instead just grep (Evidence below).

### 6.4 Offline twin

Add `test_c1_abstention_offline(tmp_path)` — same 100 probes, same seeding, same asserts (steps 2–4, 6–7), orchestrator built with `tests/fakes/fake_llm.py`, no `hw` marker, no live-turn section. This runs in the normal suite so a regression in wiring fails CI, not just the HW run.

### 6.5 Evidence block

```
git grep -n "category in (" -- tests/test_c1_abstention_acceptance.py
   -> expected: no output
git grep -n "_build_conformal_guard\|cal_probs = np.array" -- tests/test_c1_abstention_acceptance.py
   -> expected: no output
git grep -n "VERDICT" -- tests/test_c1_abstention_acceptance.py
   -> paste; the line number must be greater than every `assert prec_lb` / `assert acc_lb` line number
type tests\fixtures\router\calibration_seed.jsonl | findstr /C:"_provenance"
   -> paste
uv run python -m pytest tests/test_c1_abstention_acceptance.py::test_c1_abstention_offline -q -s
   -> paste banner
uv run python -m pytest tests/test_c1_abstention_acceptance.py::test_c1_conformal_abstention_acceptance -q -s -m hw
   -> paste banner + JSON report path (llama-server must be up; if it is down, write BLOCKED and stop — do not skip and continue)
```

Metric targets (unchanged from roadmap): N ≥ 100, abstention-precision Wilson 95% LB ≥ 0.80, accuracy Wilson 95% LB ≥ 0.80, false-abstention rate ≤ 0.10, **and** `calibrated=True` on 100/100 probes, **and** 6/6 live-path abstention expectations met.

---

## 7. PHASE 5 — Docs and lint coverage

**Files:** `luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md`, `tests/test_static_gates.py`

### 7.1 Extend the lint (must fail first)

In `test_active_docs_staleness_lint` (`tests/test_static_gates.py:327`), extend `active_docs` to:
```
AGENTS.md, GEMINI.md, README.md,
luccadocs/ARCHITECTURE.md, luccadocs/DECISIONS.md, luccadocs/MODEL_STRATEGY.md,
luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md, luccadocs/V2_BACKLOG.md,
luccadocs/specs/STUDIO_CAPABILITY_ROADMAP.md, luccadocs/audit/findings/V1_RELEASE_AUDIT.md
```
Add forbidden patterns (NeMo may still be *mentioned* as deprecated/rollback in MODEL_STRATEGY — these patterns target NeMo-as-running-brain only):
```python
(re.compile(r"llama-server(?:\.exe)?\s*\(\s*(?:Mistral-)?NeMo", re.IGNORECASE), "llama-server described as running NeMo"),
(re.compile(r"\(\s*NeMo\s*12B\s*\)", re.IGNORECASE), "NeMo 12B named as the language model"),
(re.compile(r"Mistral-NeMo-12B\s+Q6_K", re.IGNORECASE), "NeMo Q6_K named as the loaded GGUF"),
```
Run the lint. **It must fail** on `USER_GUIDE_WHAT_LUCCA_DOES.md:13` and `:151`. Paste the red output. If it does not fail, the patterns are wrong — fix them before proceeding.

### 7.2 Rewrite `luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md`

Required content changes (keep the document's existing owner-facing tone and structure):
1. Every brain reference → `gemma-4-12b-heretic-Q6_K.gguf` via native `llama-server.exe`, 16K ctx, ≤ 12.5 GB VRAM, `enable_thinking=false` on companion tiers.
2. New subsection **"Recall and knowing when not to guess (C1)"** stating exactly: (a) past episodes are looked up from `decisions`/`execution_triples` by token overlap — no LLM call; (b) the router abstains to the full brain when heuristic confidence < 0.60; (c) once ≥ 30 labelled turns exist in `decisions`, a split-conformal guard is fitted at startup from that history and abstention becomes calibrated (`calibrated=True` in telemetry); before that it is threshold-only. Cite `src/lucca/router/calibration.py`, `src/lucca/reasoning/recall.py`, `tests/test_c1_abstention_acceptance.py`.
3. A **"v1.0 status"** paragraph: what is on the live path, what is deferred to `luccadocs/V2_BACKLOG.md`.
4. Every number in the doc (TTFT, VRAM, context, M=4/M=8, N≥3 induction, 5 clusters, 0.60 threshold, 30 min samples) must be followed by a parenthetical citing the file/test that establishes it. A number without a citation is a lint failure for the reviewer.

Then re-run the lint; paste green.

### 7.3 Evidence block

```
uv run python -m pytest tests/test_static_gates.py::test_active_docs_staleness_lint -q     (BEFORE rewrite -> must show 2 violations in USER_GUIDE)
uv run python -m pytest tests/test_static_gates.py::test_active_docs_staleness_lint -q     (AFTER  rewrite -> pass)
git grep -n -i "nemo" -- luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md
   -> expected: no output
git grep -n -c "" -- luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md
   -> paste line count (sanity: the file was rewritten, not gutted; expect within ±40% of the original 190-ish lines)
```

---

## 8. PHASE 6 — Audit amendment

**Files:** `luccadocs/audit/findings/V1_RELEASE_AUDIT.md`, `luccadocs/specs/STUDIO_CAPABILITY_ROADMAP.md`

1. Insert a new **§0 "Amendment (WO-15)"** at the top of `V1_RELEASE_AUDIT.md` containing the table from §0 of this WO (claim vs reality at `08e2aa6`) and a one-line statement that the original certification was withdrawn and re-issued after WO-15.
2. Rewrite §3 rows:
   - **C1 row** → "Abstention precision Wilson LB = <measured>, N = <measured>, `calibrated=True` on 100/100, 6/6 live-path expectations, guard fitted from `calibration_seed.jsonl` (n=<N>, provenance: <header>) via `fit_guard_from_db` at `Orchestrator.__init__`. Evidence: `tests/test_c1_abstention_acceptance.py`, `logs/test_reports/c1_abstention_acceptance_<ts>.json`."
   - **Active Docs Staleness Lint row** → replace "across all active docs" with the explicit 10-file list.
   - **Non-Hardware Regression Suite row** → the new count from Phase 7 (not 634).
   - Add row **"Router calibration wiring"** → evidence `tests/test_router_calibration.py::test_orchestrator_router_calibrated_with_seeded_history`.
   - Add row **"Recall single source of truth"** → evidence: the `git grep -n "recall_past_episodes" -- src/` output from Phase 3 (2 lines).
3. §1 Executive Summary: delete "Project Lucca is complete, locked, fully tested, and certified for production use on the target host hardware." Replace with: "All acceptance gates enumerated in §3 pass on the target host as of <date>. Conformal abstention is calibrated only once ≥ 30 labelled decisions exist; on a fresh install the router operates threshold-only until then."
4. §2 item 7: state the startup-fit behaviour and the threshold-only fallback explicitly.
5. `luccadocs/specs/STUDIO_CAPABILITY_ROADMAP.md` C1 row: point evidence at the new test names and the Phase 4 report path.

### 8.1 Evidence block

```
git grep -n "certified for production use" -- luccadocs/
   -> expected: no output
git grep -n "Amendment (WO-15)" -- luccadocs/audit/findings/V1_RELEASE_AUDIT.md
   -> expected: 1 hit
git grep -n "test_orchestrator_router_calibrated_with_seeded_history\|test_c1_abstention_offline" -- luccadocs/audit/findings/V1_RELEASE_AUDIT.md luccadocs/specs/STUDIO_CAPABILITY_ROADMAP.md
   -> expected: ≥ 2 hits
uv run python -m pytest tests/test_static_gates.py -q
   -> expected: pass (audit file is now in the lint set)
```

---

## 9. PHASE 7 — Full verification and re-tag

### 9.1 Static

```
uv run ruff check src/ tests/ scripts/export_calibration_seed.py
uv run ruff format --check src/ tests/
uv run lint-imports
uv run mypy src/lucca/router/heuristic.py src/lucca/router/calibration.py src/lucca/reasoning/recall.py 2>&1 | findstr /C:"router\\" /C:"reasoning\\recall"
   -> expected: no output (pre-existing errors in other modules are out of scope; do not fix them in this WO)
git grep -n "type: ignore" -- src/lucca/router/ src/lucca/reasoning/recall.py src/lucca/core/orchestrator.py
   -> expected: no output
```

### 9.2 Suite

Run exactly the invocation used for the `08e2aa6` release count so the numbers are comparable, then the new files explicitly:
```
uv run python -m pytest tests/ -x --ignore=tests/test_capability_assessment_live_hw.py --ignore=tests/test_a1_live_hw.py -q --tb=short
uv run python -m pytest tests/test_router.py tests/test_router_calibration.py tests/test_conformal_recall.py tests/test_epistemic_cascade.py tests/test_c1_abstention_acceptance.py::test_c1_abstention_offline tests/test_l3_lifecycle_proof.py tests/test_static_gates.py -q
```
Targets: 0 failed, 0 errors; total passed ≥ 634 + (new tests added in Phases 1–5, minimum 16). Paste the final summary line of each run.

### 9.3 Hardware

With `llama-server` up (`curl http://127.0.0.1:8080/health` → 200):
```
uv run python -m pytest tests/test_c1_abstention_acceptance.py -q -s -m hw
uv run python -m pytest tests/test_a1_acceptance_hw.py -q -m hw
```
Paste both banners. If `llama-server` is not up, write `BLOCKED` and stop; do not re-tag.

### 9.4 Re-tag

```
git ls-remote --tags origin v1.0.0
   -> if ANY output: the tag has already been pushed. Do NOT delete it. Use v1.0.1 below and write that in Evidence.
git tag -d v1.0.0
git add -A && git commit -m "WO-15: v1.0 remediation — conformal guard wired + DB-calibrated, recall deduplicated, user guide + lint coverage, audit amended"
git tag -a v1.0.0 -m "Project Lucca v1.0.0 — WO-15 remediated; all gates in V1_RELEASE_AUDIT.md §3 green"
git tag -n1 v1.0.0
git log -n 1 --stat
```
Paste all output. Do not push.

---

## 10. Reviewer checklist (owner fills this in; Gemini does not)

| # | Check | Command | Pass? |
|---|---|---|---|
| 1 | Guard wired at construction | `git grep -n "conformal_guard=" -- src/` → 1 hit in orchestrator.py | |
| 2 | Calibration is from DB, not literals | `git grep -n "cal_probs = np.array" -- src/ tests/` → no hits in src/; only in test_router.py unit test | |
| 3 | Recall single definition | `git grep -n "recall_past_episodes" -- src/` → 2 lines | |
| 4 | No label leakage | `git grep -n "category in (" -- tests/test_c1_abstention_acceptance.py` → none | |
| 5 | Verdict after asserts | line number of `VERDICT` > line numbers of `assert prec_lb`/`assert acc_lb` | |
| 6 | Lint covers user guide | `git grep -n "USER_GUIDE_WHAT_LUCCA_DOES" -- tests/test_static_gates.py` → 1 hit | |
| 7 | User guide names Gemma | `git grep -n -i "nemo" -- luccadocs/USER_GUIDE_WHAT_LUCCA_DOES.md` → none | |
| 8 | Evidence file complete | `luccadocs/audit/findings/WO15_EVIDENCE.md` has 7 `## Phase` headings, each with ≥ 1 verbatim command block, and every "must fail first" gate shows red then green | |
| 9 | No forbidden constructs | `git grep -n "type: ignore\|noqa: S110\|pytest.skip" -- src/lucca/router src/lucca/reasoning/recall.py tests/test_c1_abstention_acceptance.py tests/test_router_calibration.py` → only the single llama-server skip | |
| 10 | Tag | `git tag -n1 v1.0.0` points at the WO-15 commit; `git ls-remote --tags origin` shows it was never pushed at `08e2aa6` | |

Any row failing → WO-15 is not closed. Do not accept a summary in place of this table.

---

## 11. Out of scope (do not do these in WO-15)

- Fixing the ~120 pre-existing mypy errors outside the three modules named in §9.1.
- Replacing the heuristic probability construction with a learned classifier (V2 backlog).
- Changing the 0.80 RULE gate, the 0.60 threshold, alpha, or min_samples. These are configuration, not this WO's decision.
- Rewriting `ARCHITECTURE.md` / `MODEL_STRATEGY.md` beyond the C1 sentences required in Phase 6.
- Any new capability. This is remediation only.