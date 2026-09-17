# Spec 05 — Rule DSL (MicroScheme v2), State Schema, Evaluation, Lifecycle, Reflection

Implements ADR-007. Replaces `src/lucca/reasoning/micro_scheme.py` and `promotion_gate.py` behaviour. AGENTS.md invariant #4 is preserved exactly: N ≥ 5 distinct-cluster successes, 0 failures, 100 % regression.

## 1. Canonical rule form

```scheme
(rule "open-calculator-v1"                     ; rule-id (string literal, kebab-case + -vN)
  :when (and (intent= "launch_app")
             (entity-has? "app" "calculator")
             (not (app-running? "calculator")))
  :plan (list (tool "launch_app" :app "calculator")
              (say "Opening the calculator."))
  :priority 10)                                 ; optional int, default 0
```

Exactly this shape. `:when` → boolean; `:plan` → list of `tool`/`say` forms; nothing else is permitted at top level.

## 2. Grammar (EBNF — also emitted as GBNF for llama-server `grammar`)

```
rule      := "(" "rule" STRING ":when" expr ":plan" plan [":priority" INT] ")"
plan      := "(" "list" action* ")"
action    := "(" "tool" STRING kwarg* ")" | "(" "say" STRING ")"
kwarg     := KEYWORD atom
expr      := atom | "(" op expr* ")"
op        := "and" | "or" | "not" | "if" | "=" | "<" | ">" | "<=" | ">=" | "+" | "-" | "*" | "/"
           | "intent=" | "entity-has?" | "entity" | "transcript-has?" | "transcript-matches-glob?"
           | "app-running?" | "hour-between?" | "weekday?" | "last-tool-ok?" | "last-tool="
           | "session-turns>=" | "str-contains?" | "str-lower" | "len" | "min" | "max"
atom      := STRING | INT | FLOAT | "#t" | "#f" | KEYWORD | SYMBOL
STRING    := '"' ( [^"\\] | '\\' ["\\nt] )* '"'
KEYWORD   := ":" [a-zA-Z][a-zA-Z0-9_-]*
SYMBOL    := [a-zA-Z_][a-zA-Z0-9_?=<>!-]*
INT       := "-"? [0-9]+ ; FLOAT := "-"? [0-9]+ "." [0-9]+
comment   := ";" [^\n]*      (lexer-level)
```

**Deliberately absent:** `lambda`, `define`, `let`, `set!`, recursion, `eval`, regex (`matches?`) — glob only (`fnmatch`, no ReDoS), string multiplication, list construction beyond `list` in `:plan`.

## 3. Lexer/parser requirements (fix list vs current code)

| Requirement | Test |
|---|---|
| Regex-based lexer handles quoted strings with spaces/escapes, keywords, comments | T-LISP-01 (doc 02 sample rule parses) |
| Max nesting depth 32; max tokens 2 000; max source 8 KiB → `SchemeSyntaxError` | T-LISP-02 |
| Parser O(n) (index-based, no `pop(0)`) | T-LISP-03 (10 k-token input < 50 ms) |
| Unbalanced parens / stray tokens → `SchemeSyntaxError{line, col}` | T-LISP-04 |
| `if` with 2 or 3 branches only; arity errors are `SchemeSyntaxError` at parse time | T-LISP-05 |
| Hypothesis: random token soup never raises anything but `SchemeSyntaxError` | T-LISP-06 |

## 4. Evaluator requirements

- Environment: **frozen** primitives table; each evaluation gets a fresh child env containing only the `RuleState` bindings. No user `define`. Attempt to shadow a primitive → `SchemeRuntimeError`.
- `and`/`or`/`if` are special forms (short-circuit). All others strict.
- Gas: 1 unit per `eval` step, limit **1 000**; exceed → `SchemeGasExhausted`. Wall-clock guard 20 ms (`time.perf_counter`) → `SchemeTimeout`.
- Numeric guards: ints |x| ≤ 2⁶³; floats must be finite; `/` by zero → `SchemeRuntimeError`; `*` only on numbers.
- String/list guards: results ≤ 4 096 chars / ≤ 256 elements.
- Every Python exception inside a primitive is caught and re-raised as `SchemeRuntimeError(rule_id, form, cause_type)`. Tests assert no raw `TypeError/ZeroDivisionError/IndexError/KeyError/RecursionError` escapes (T-LISP-07, Hypothesis).
- Type errors (`(< "a" 1)`) → `SchemeRuntimeError`, not Python `TypeError`.
- `:plan` evaluation produces `Plan(actions=[ToolCall|Say])`; `tool` name must be in the registered tool list and kwargs must validate against that tool's Pydantic arg model **at static-validation time** (§7), else the rule is rejected before quarantine.

## 5. `RuleState` (what `:when` can see) — versioned, `state_schema_version = 1`

```python
class RuleState(BaseModel, frozen=True):
    schema_version: Literal[1]
    transcript: str                       # Whisper text, normalised
    transcript_lower: str
    intent: str                           # from heuristic/classifier: launch_app|file_read|file_write|web_fetch|memory_query|chit_chat|clarify|unknown
    intent_conf: float
    entities: dict[str, list[str]]        # {"app":["calculator"], "file":["notes.txt"], ...} from rule-based NER (spec 06)
    hour_local: int; weekday: int          # 0=Mon
    apps_running: frozenset[str]           # from launcher's process snapshot (whitelisted names only)
    last_tool: str | None; last_tool_ok: bool | None
    session_turns: int
    mode: Literal["audio","transcript"]
```

Primitive → field mapping is fixed (`(intent= "x")` ≡ `state.intent == "x"`, `(entity-has? k v)` ≡ `v in state.entities.get(k, [])`, `(transcript-matches-glob? "open * please")` ≡ `fnmatch(state.transcript_lower, pattern)`, etc.). Adding a field = bump `schema_version`, migrate regression cases or mark them stale.

## 6. Evaluation & shadow semantics (per turn, in `lucca-core`)

```
outcomes = engine.evaluate(state, mode)          # all rules, ACTIVE and QUARANTINE
active_fired    = [o for o in outcomes if o.rule.status == ACTIVE and o.fired]
shadow_fired    = [o for o in outcomes if o.rule.status == QUARANTINE and o.fired]
```
- If `active_fired` non-empty: choose by priority desc → conjunct count desc → promoted_at asc; if the top two tie on all → `RULE_CONFLICT`, fall to LLM. Chosen plan → orchestrator → risk policy → execute. Router decision recorded as `RULE`.
- Otherwise LLM path runs. **After** the turn's tool calls complete, for each `shadow_fired` outcome: `matched = canonical(plan.tool_calls) == canonical(executed_tool_calls)` where canonical sorts kwargs, lowercases tool names, ignores `say`. If user barged in within 1.5 s or cancelled a confirm → `indeterminate=True` (not counted). Record `record_shadow(rule_id, matched, cluster_id, indeterminate)`.
- Also record, for every turn, whether **any** quarantine rule fired (counterfactual signal for the router, spec 06).

## 7. Static validation (before quarantine)

1. Parse (§3). 2. Depth/size limits. 3. Every symbol ∈ grammar `op` list. 4. Every `tool` name registered; kwargs validate against tool arg model; tool risk recorded. 5. `:when` must reference at least one state predicate (no constant-true rules). 6. Evaluate `:when` and `:plan` against 20 random `RuleState` fixtures — must not raise. 7. Rule-id unique; version suffix increments if same base exists. 8. Pretty-print canonical form; store `source_canonical` + `source_hash`.

## 8. Distinctness (clusters) — deterministic

```
cluster_id = sha1(f"{session_id}|{floor(turn_ts / 900)}|{semantic_cluster}")  # 900 s = 15 min buckets
semantic_cluster: agglomerative clustering (average linkage, cosine distance threshold 0.25)
                  over intent-encoder vectors of transcripts within the rule's evaluation history;
                  recomputed on each record_shadow; cluster label = index of the cluster containing this turn.
```
Two successes are distinct iff their `cluster_id`s differ. Repeating "open calculator" 5× in one minute → 1 cluster → 1 distinct success. Same request on 5 different days → 5. Same day, 5 phrasings 20 min apart → 5. Test T-RULE-03 covers these three scenarios exactly.

## 9. Lifecycle state machine

```
PROPOSED ──static validation ok──► QUARANTINE
QUARANTINE: distinct_successes ≥ 5 ∧ failures == 0 ∧ regression_suite_ok ──► ACTIVE (record regression cases)
QUARANTINE: failures ≥ 1 ──► (stay; cannot promote) ; failures ≥ 3 or age > 30 days without promotion ──► RETIRED
ACTIVE: any non-indeterminate failure ──► DEMOTED (demotion_count += 1; successes, failures, clusters reset)
DEMOTED ──automatically──► QUARANTINE (needs 5 fresh distinct successes)
DEMOTED with demotion_count ≥ 2 ──► RETIRED
Any ──user says "stop doing X" (confirmed)──► RETIRED (user_retired=1)
```
Regression cases: at promotion, the 5+ `(RuleState, Plan)` success snapshots are stored in `rule_regression_cases`. `verify_regression_suite()` evaluates **every active rule** against **all** stored cases of all active rules; a case passes if the owning rule reproduces its plan and no *other* rule's `:when` newly fires on it (conflict introduction). Report lists `cases_run`, `cases_failed`, `duration_ms`; `cases_run == 0` for a rule being promoted ⇒ not eligible.

Tables (migration 0003):

```sql
CREATE TABLE rules(rule_id TEXT PRIMARY KEY, base_id TEXT, version INTEGER, status TEXT CHECK(status IN ('PROPOSED','QUARANTINE','ACTIVE','DEMOTED','RETIRED')),
  source_canonical TEXT, source_hash TEXT UNIQUE, state_schema_version INTEGER, priority INTEGER,
  created_at REAL, promoted_at REAL, demoted_at REAL, retired_at REAL, demotion_count INTEGER DEFAULT 0, user_retired INTEGER DEFAULT 0,
  parent_rule_id TEXT, rationale TEXT);
CREATE TABLE rule_evaluations(eval_id INTEGER PRIMARY KEY, rule_id TEXT REFERENCES rules, trace_id TEXT, ts REAL, mode TEXT, fired INTEGER,
  matched INTEGER, indeterminate INTEGER, cluster_id TEXT, gas_used INTEGER, elapsed_us INTEGER, error TEXT);
CREATE TABLE rule_regression_cases(case_id INTEGER PRIMARY KEY, rule_id TEXT REFERENCES rules, state_json TEXT, expected_plan_json TEXT,
  state_schema_version INTEGER, captured_at REAL, stale INTEGER DEFAULT 0);
```

## 10. Reflection (rule synthesis)

- **Trigger:** all of — idle ≥ 60 s; ≥ 10 new decisions since last run; last run ≥ 10 min ago; not in DEGRADED. Abort immediately on `ptt.pressed` (LLM slot released).
- **Input:** last 200 `decisions` where `route ∈ {LLM}` and a tool call succeeded, grouped by `(intent, tool)`; groups with ≥ 3 members and ≥ 2 distinct sessions are candidates. For each group, the prompt contains: 3–5 example `RuleState` JSONs, the executed tool calls, the grammar, the predicate/primitive list, and the instruction to output **one** rule.
- **Decoding:** GBNF grammar from §2 via llama-server `grammar`; `max_tokens 400`; `temperature 0.2`.
- **Output handling:** parse → static validation → `PROPOSED → QUARANTINE`; store `rationale` (a second short free-text generation, stored but never executed).
- **Metrics (per run):** `groups_considered, candidates_generated, parse_ok, static_ok, quarantined`. Gate for Phase 5 mechanical criterion: over the first 20 reflection runs, `parse_ok / candidates_generated ≥ 0.5` and ≥ 1 rule promoted from real usage (HUMAN GATE, D-09). Apply-rate thresholds from docs 01/02 (0.08 etc.) are **provisional**, stored in config, and re-baselined after 200 runs.
- Promotion notice: speak "I've learned a shortcut: <rule.say or summary>. Say 'stop doing that' to remove it." and show the pretty-printed diff vs parent in the UI log.

## 11. Tests

| ID | Test | Pass |
|---|---|---|
| T-LISP-01…07 | see §3–§4 | as listed |
| T-LISP-08 | Memory bomb attempts (`(* 2 (* 2 …))` 64 deep, long strings) → typed error within 20 ms | — |
| T-LISP-09 | Primitive shadowing / `define` → `SchemeSyntaxError` | — |
| T-RULE-01 | Sample rule §1 → Plan with 1 ToolCall + 1 Say; canonical equality | — |
| T-RULE-02 | Shadow match/mismatch/indeterminate recorded correctly (fixture turns) | — |
| T-RULE-03 | Distinctness scenarios (3) | exact counts 1/5/5 |
| T-RULE-04 | Lifecycle: 5 distinct + 0 fail → ACTIVE; 1 active fail → DEMOTED → QUARANTINE with counters reset; 2nd → RETIRED | — |
| T-RULE-05 | `verify_regression_suite` with a mutated rule that changes a plan → fails; report non-empty | — |
| T-RULE-06 | Conflict: two active rules tie → RULE_CONFLICT, LLM path used, logged | — |
| T-RULE-07 | WRITE-risk plan from ACTIVE rule → confirm flow invoked (FakeUI), not executed on "no" | — |
| T-RULE-08 | Static validation rejects: unknown tool, bad kwargs, constant-true `:when`, regex primitive | — |
| T-REFL-01 | FakeLLM emits grammar-valid rule → quarantined; emits garbage → parse_ok=0, no crash | — |
| T-REFL-02 | Reflection aborts within 100 ms of `ptt.pressed` | — |
