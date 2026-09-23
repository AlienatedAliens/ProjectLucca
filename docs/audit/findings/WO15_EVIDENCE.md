# Work Order 15 Evidence Log

**Date:** 2026-09-24  
**Plan:** `plans/2026-09-24_wo15_v1_release_remediation.md`  

---

## Phase 1 — Router correctness fixes

### 1.1 Baseline Mypy (Red)

Command:
```
cmd /c "uv run mypy src/lucca/router/heuristic.py 2>&1 | findstr /C:heuristic.py"
```

Verbatim Output:
```
src\lucca\router\heuristic.py:310: error: Incompatible types in assignment (expression has type "dict[str, float]", variable has type "list[float] | None")  [assignment]
src\lucca\router\heuristic.py:359: error: Argument "probabilities" to "RouteDecision" has incompatible type "list[float] | None"; expected "dict[str, float] | None"  [arg-type]
```

### 1.2 Baseline Gate Test (Red)

Command:
```
uv run python -m pytest tests/test_router.py::test_conformal_branch_respects_rule_conf_gate -v
```

Verbatim Output:
```
============================= test session starts =============================
platform win32 -- Python 3.12.14, pytest-9.1.1, pluggy-1.6.0 -- C:\Projects\ProjectLucca\.venv\Scripts\python.exe
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: C:\Projects\ProjectLucca
configfile: pyproject.toml
plugins: anyio-4.15.1, hypothesis-6.168.0, asyncio-1.4.0, cov-7.1.0, timeout-2.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_router.py::test_conformal_branch_respects_rule_conf_gate FAILED [100%]

================================== FAILURES ===================================
________________ test_conformal_branch_respects_rule_conf_gate ________________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x000001B8B41F9310>

    def test_conformal_branch_respects_rule_conf_gate(monkeypatch: pytest.MonkeyPatch) -> None:
        """Guarded router must NOT route RULE when intent conf < 0.80, even with a registered rule."""
        cal_probs = np.array(
            [
                [0.55, 0.45, 0.00],
                [0.85, 0.15, 0.00],
                [0.10, 0.85, 0.05],
                [0.05, 0.90, 0.05],
                [0.05, 0.15, 0.80],
                [0.10, 0.10, 0.80],
                [0.92, 0.08, 0.00],
                [0.08, 0.92, 0.00],
                [0.05, 0.05, 0.90],
                [0.60, 0.40, 0.00],
            ],
            dtype=np.float64,
        )
        cal_labels = np.array([0, 0, 1, 1, 2, 2, 0, 1, 2, 0], dtype=np.int64)
        guard = ConformalGuard(alpha=0.10)
        guard.fit(cal_probs, cal_labels)
    
        router = HeuristicRouter(conformal_guard=guard)
        monkeypatch.setattr(
            router,
            "classify_intent",
            lambda _t: ("launch_app", 0.61, {"app": ["calculator"], "file": [], "url": [], "quoted": []}),
        )
        decision = router.route("open calculator", has_registered_rule=True)
>       assert decision.action != RouteAction.RULE
E       AssertionError: assert <RouteAction.RULE: 'RULE'> != <RouteAction.RULE: 'RULE'>
E        +  where <RouteAction.RULE: 'RULE'> = RouteDecision(action=<RouteAction.RULE: 'RULE'>, tier=<ExecutionTier.ACT_THEN_NARRATE: 'ACT_THEN_NARRATE'>, probabilities={'RULE': 0.61, 'LLM': 0.39, 'CLARIFY': 0.0}, prediction_set=[<RouteAction.RULE: 'RULE'>], fallback_applied=False, calibrated=True, elapsed_us=13).action
E        +  and   <RouteAction.RULE: 'RULE'> = RouteAction.RULE

tests\test_router.py:585: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_router.py::test_conformal_branch_respects_rule_conf_gate - ...
============================== 1 failed in 2.63s ==============================
```

### 1.3 Milestone Checks (Green)

Command:
```
cmd /c "uv run mypy src/lucca/router/heuristic.py 2>&1 | findstr /C:heuristic.py"
```

Verbatim Output:
*(Empty output — exit code 1)*

Command:
```
git grep -n "type: ignore" -- src/lucca/router/heuristic.py
```

Verbatim Output:
*(Empty output — exit code 1)*

Command:
```
git grep -n "rule_eligible" -- src/lucca/router/heuristic.py
```

Verbatim Output:
```
src/lucca/router/heuristic.py:302:        rule_eligible = any_active_rule_fired or (
src/lucca/router/heuristic.py:308:        if rule_eligible:
src/lucca/router/heuristic.py:342:        elif rule_eligible:
```

Command:
```
uv run python -m pytest tests/test_router.py -q
```

Verbatim Output:
```
.................                                                        [100%]
17 passed, 1 deselected in 1.13s
```

---

## Phase 2 — Real calibration and production wiring

### 2.1 Milestone Checks (Verbatim)

Command:
```
git grep -n "conformal_guard=" -- src/
```

Verbatim Output:
```
src/lucca/core/orchestrator.py:327:                conformal_guard=guard,
```

Command:
```
git grep -n "fit_guard_from_db" -- src/
```

Verbatim Output:
```
src/lucca/core/orchestrator.py:102:from lucca.router.calibration import fit_guard_from_db
src/lucca/core/orchestrator.py:322:            guard = fit_guard_from_db(self.db) if self.db is not None else None
src/lucca/router/calibration.py:106:def fit_guard_from_db(
```

Command:
```
git grep -n "_insert_decision" -- tests/
```

Verbatim Output:
```
tests/helpers/decisions.py:17:def _insert_decision(
tests/test_l3_lifecycle_proof.py:25:from tests.helpers.decisions import _insert_decision
tests/test_l3_lifecycle_proof.py:67:        _insert_decision(
tests/test_l3_lifecycle_proof.py:80:        _insert_decision(
tests/test_router_calibration.py:16:from tests.helpers.decisions import _insert_decision
tests/test_router_calibration.py:34:        _insert_decision(
tests/test_router_calibration.py:52:        _insert_decision(
tests/test_router_calibration.py:71:    _insert_decision(
tests/test_router_calibration.py:90:        _insert_decision(
tests/test_router_calibration.py:106:    _insert_decision(
tests/test_router_calibration.py:142:        _insert_decision(
tests/test_router_calibration.py:154:        _insert_decision(
tests/test_router_calibration.py:165:        _insert_decision(
```

Command:
```
cmd /c "uv run mypy src/lucca/router/calibration.py src/lucca/router/heuristic.py 2>&1 | findstr /C:router\""
```

Verbatim Output:
*(Empty output — exit code 1)*

Command:
```
uv run python -m pytest tests/test_router_calibration.py tests/test_router.py -q
```

Verbatim Output:
```
.........................                                                [100%]
25 passed, 1 deselected in 1.96s
```

---

## Phase 3 — Recall deduplication

### 3.1 Milestone Checks (Verbatim)

Command:
```
git grep -n "recall_past_episodes" -- src/
```

Verbatim Output:
```
src/lucca/core/cascade.py:27:from lucca.reasoning.recall import recall_past_episodes, tokenize_query
src/lucca/core/cascade.py:978:            episodes = recall_past_episodes(db, query_text, limit=10)
src/lucca/reasoning/recall.py:63:def recall_past_episodes(
```

Command:
```
git grep -n "def recall_past_episodes" -- src/lucca/reasoning/replay.py
```

Verbatim Output:
*(Empty output — exit code 1)*

Command:
```
git grep -n -c "FROM decisions" -- src/lucca/core/cascade.py
```

Verbatim Output:
*(Empty output — exit code 1)*

Command:
```
git grep -E -n "except Exception:.*pass|noqa: S110" -- src/lucca/core/cascade.py src/lucca/reasoning/recall.py
```

Verbatim Output:
*(Empty output — exit code 1)*

Command:
```
uv run lint-imports
```

Verbatim Output:
```
=============
Import Linter
=============


---------
Contracts
---------

Analyzed 100 files, 294 dependencies.
-------------------------------------

UI must not import Core Orchestrator KEPT
Memory must not import Brain KEPT
Reasoning must not import Brain KEPT
Sandbox must not import Brain or UI KEPT
Memory must not import UI KEPT
Reasoning must not import UI KEPT

Contracts: 6 kept, 0 broken.
```

Command:
```
uv run python -m pytest tests/test_conformal_recall.py tests/test_epistemic_cascade.py tests/test_l2_replay_and_contrastive.py -q
```

Verbatim Output:
```
............................                                             [100%]
28 passed in 3.46s
```

---

## Phase 4 — C1 Acceptance Gate Rebuilt

### 4.1 Live Acceptance Gate Execution

Command:
```
uv run python -m pytest tests/test_c1_abstention_acceptance.py -q -s -m hw
```

Verbatim Output:
```
================================================================================
  C1 ACCEPTANCE GATE: CONFORMAL ROUTING ABSTENTION PRECISION (HW)
--------------------------------------------------------------------------------
  Total Turns Graded (N)   : 100
  Total Abstentions        : 51
  True Abstentions         : 49
  False Abstentions        : 2
  Abstention Precision     : 96.08%
  Wilson 95% Interval      : [0.8541, 0.9932] (Threshold: LB >= 0.80)
  Overall Turn Accuracy    : 97.00% [0.9085, 0.9922]
  False Abstention Rate    : 4.00% (Threshold: <= 10.00%)
  Live HW Turns Tested     : 6
  Report Written To        : logs\test_reports\c1_abstention_acceptance_20260924T045336Z.json
  VERDICT                  : PASS (Wilson LB 0.8541 >= 0.80)
================================================================================
```

Report written to: `logs/test_reports/c1_abstention_acceptance_20260924T045336Z.json`

Offline twin execution:
```
uv run python -m pytest tests/test_c1_abstention_acceptance.py::test_c1_abstention_offline -q -s
```

Verbatim Output:
```
================================================================================
  C1 ACCEPTANCE GATE: CONFORMAL ROUTING ABSTENTION PRECISION (OFFLINE)
--------------------------------------------------------------------------------
  Total Turns Graded (N)   : 100
  Total Abstentions        : 51
  True Abstentions         : 49
  False Abstentions        : 2
  Abstention Precision     : 96.08%
  Wilson 95% Interval      : [0.8541, 0.9932] (Threshold: LB >= 0.80)
  Overall Turn Accuracy    : 97.00% [0.9085, 0.9922]
  False Abstention Rate    : 4.00% (Threshold: <= 10.00%)
  VERDICT                  : PASS (Wilson LB 0.8541 >= 0.80)
================================================================================
```

### 4.2 Structural Checks (Verbatim)

Command:
```
git grep -n "category in (" -- tests/test_c1_abstention_acceptance.py
```

Verbatim Output:
*(Empty output — exit code 1)*

Command:
```
git grep -n -E "_build_conformal_guard|cal_probs = np.array" -- tests/test_c1_abstention_acceptance.py
```

Verbatim Output:
*(Empty output — exit code 1)*

Command:
```
git grep -n "VERDICT" -- tests/test_c1_abstention_acceptance.py
git grep -n -E "assert prec_lb|assert acc_lb" -- tests/test_c1_abstention_acceptance.py
```

Verbatim Output:
```
tests/test_c1_abstention_acceptance.py:398:  VERDICT                  : PASS (Wilson LB {prec_lb:.4f} >= 0.80)
tests/test_c1_abstention_acceptance.py:543:  VERDICT                  : PASS (Wilson LB {prec_lb:.4f} >= 0.80)

tests/test_c1_abstention_acceptance.py:376:        assert prec_lb >= 0.80, (
tests/test_c1_abstention_acceptance.py:379:        assert acc_lb >= 0.80, (
tests/test_c1_abstention_acceptance.py:497:    assert prec_lb >= 0.80, f"Abstention precision Wilson LB {prec_lb:.4f} < 0.80 (target: >= 0.80)"
tests/test_c1_abstention_acceptance.py:498:    assert acc_lb >= 0.80, (
```
*(All assertions strictly precede VERDICT banner printing)*

Command:
```
cmd /c "type tests\fixtures\router\calibration_seed.jsonl | findstr /C:_provenance"
```

Verbatim Output:
```
{"_provenance": "synthetic: router_fixtures.jsonl routed through unguarded HeuristicRouter on 2026-09-23T20:48:23.557336+00:00, n=135"}
```

---

