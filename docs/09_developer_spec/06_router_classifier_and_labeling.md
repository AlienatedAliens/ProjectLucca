# Spec 06 — Executive Router, Decision Logging, Labeling Protocol, Classifier & Conformal Guard

Replaces `heuristic_router.py`, `conformal_guard.py` behaviour and doc 04 §2.3 thresholds. Phase 4 = heuristic + logging; Phase 6 = trained classifier + conformal guard. AGENTS.md invariant #2: tree models on CPU only; encoder on NPU.

## 1. What the router decides

Input `RouteFeatures` = every field of `RuleState` (spec 05 §5) **plus** `vad_speech_ms: int`, `asr_avg_logprob: float`, `any_active_rule_fired: bool`, `any_quarantine_rule_fired: bool`. (`vad_speech_ms`/`asr_avg_logprob` are deliberately *not* in `RuleState` so rules cannot condition on ASR confidence.) Output:

```python
class RouteDecision(BaseModel):
    action: Literal["RULE", "LLM", "CLARIFY"]
    probs: dict[str, float]            # sums to 1 (heuristic emits one-hot-ish 0.9/0.05/0.05)
    prediction_set: list[str]          # conformal set (Phase 6) or [action]
    fallback_applied: bool             # set size ≠ 1 → forced LLM
    elapsed_us: int
```

**Ordering (fixes the "LISP first needs intent" gap):** rule evaluation is always attempted first because it is deterministic and < 1 ms; `RULE` is only *possible* if `any_active_rule_fired`. The router then decides among `RULE` (trust the fired rule), `LLM`, `CLARIFY` (ask a question when transcript is too short/ambiguous: `vad_speech_ms < 400` or `intent_conf < 0.35` and no rule fired).

In `audio` mode the LLM request is dispatched speculatively at `ptt.released`; if router returns `RULE`, `SpeechLLMPort.abort()` is called (≤ 50 ms) and the plan executes. Net effect: routing never adds latency to the LLM path; it can only shortcut it.

## 2. Heuristic router (Phase 4) — normative

- Intent lexicon in `config\intents.toml`; matching is **word-boundary regex** on `transcript_lower` (`\b(open|launch|start|run)\b\s+(the\s+)?(?P<app>[a-z0-9 .-]+)`), never substring. Each intent has ≥ 5 positive and ≥ 5 adversarial negative fixtures (`"start with the second file"` must **not** be `launch_app`).
- Entity extraction (rule-based, Phase 4): app names from the launcher whitelist (aliases), filenames `\b[\w\-. ]+\.(txt|md|py|json|csv|pdf|docx)\b`, URLs, quoted strings.
- Decision: `any_active_rule_fired → RULE`; `CLARIFY` conditions above; else `LLM`. `probs` = 0.90 for chosen, rest split.
- Acceptance: on the frozen `router_fixtures.jsonl` (≥ 120 utterances, ≥ 20 per intent, incl. adversarial): intent macro-F1 ≥ 0.85; zero false `launch_app` on the adversarial set.

## 3. Decision record (single Pydantic model; migration 0002)

```python
class DecisionRecord(BaseModel):
    decision_id: str; trace_id: str; session_id: str; ts: float
    features: RouteFeatures                 # full snapshot (JSON)
    decision: RouteDecision
    router_version: str                     # "heuristic-1.0" | "clf-<sha>"
    executed_path: Literal["RULE","LLM","CLARIFY"]
    tool_calls: list[ToolCall]              # what actually ran
    tool_ok: bool | None
    llm_first_token_ms: float | None
    user_interrupted: bool                  # barge-in within this turn's playback
    interrupted_after_ms: float | None
    label: Literal["POS","NEG","INDETERMINATE"] | None   # filled later by labeling (§4)
    label_reason: str | None
    counterfactual_rule_fired: bool         # any quarantine rule fired (would RULE have been possible?)
```
`embedding` is **not** a field; `vec_decisions(decision_id, embedding float[384])` holds the intent-encoder vector for distinctness/clustering.

Persistence: appended to `decisions` in the same SQLite (write queue), **and** mirrored to `logs\decisions.jsonl` (append-only, for offline analysis). `log_path` must be used; unit test asserts a row exists after `route()` + `POSTTURN`.

## 4. Labeling protocol (ground truth for "was the route correct?")

Applied in POSTTURN of the **next** turn or after 60 s idle, whichever first:

| Priority | Signal | Label | Reason code |
|---|---|---|---|
| 1 | User barged in ≤ 1.5 s after playback started | NEG | `early_bargein` |
| 2 | Next transcript matches negation lexicon (`^(no|nope|wrong|not that|that's not|stop|undo|cancel)\b`) | NEG | `explicit_negation` |
| 3 | Any tool call `ok=False` (non-zero exit, timeout, schema error) | NEG | `tool_failed` |
| 4 | Confirm flow answered "no" | INDETERMINATE | `user_declined` |
| 5 | Route was `LLM` and the LLM made a tool call that an ACTIVE or QUARANTINE rule also planned identically | NEG for router (should have been RULE) but POS for the rule | `rule_would_match` |
| 6 | Route was `RULE` and user re-asked the same intent within 30 s | NEG | `rule_wrong` |
| 7 | Route was `CLARIFY` and user's next turn had `intent_conf ≥ 0.6` same intent | POS | `clarify_useful` |
| 8 | Otherwise | POS | `implicit_ok` |

Label + reason stored in `decision_labels(decision_id, label, reason, labeled_at)`. Every label is **derivable by replaying the trace** — no human annotation is required, so the labeling function itself is unit-tested on 30 fixture turn-pairs (T-RTR-05).

The *training target* for the classifier is `best_action`: `RULE` if `counterfactual_rule_fired ∧ label≠NEG(rule_wrong)`; `CLARIFY` if label reason `clarify_useful` or `intent_conf<0.35`; else `LLM`.

## 5. Data-volume gates (Phase 6 cannot start without these)

| Quantity | Minimum | Why |
|---|---|---|
| Labelled decisions | **600** | 400 train / 100 calibration / 100 test |
| Per class (`RULE`, `LLM`, `CLARIFY`) | **30** each in the test split | otherwise macro-F1 undefined/noisy |
| Distinct sessions | 20 | drift realism |
| Span | ≥ 14 days | exchangeability sanity |

Split is **chronological** (oldest → train, newest → test), not random — mirrors deployment and exposes drift.

## 6. Classifier (Phase 6)

- Features: intent-encoder embedding (MiniLM 384-d, NPU) of `transcript` + 24 hand features from `RouteFeatures` (`intent_conf`, `vad_speech_ms`, `len(transcript)`, `any_*_rule_fired`, `hour`, `weekday`, `session_turns`, `last_tool_ok`, one-hot intent).
- Model: **LightGBM** multiclass (CPU), `num_leaves ≤ 15`, `n_estimators ≤ 300`, early stopping on calibration split. Alternative if per-class N < 60: logistic regression on the same features (fewer params).
- Calibration: temperature scaling on the calibration split (fit one scalar), then conformal (§7). Report **ECE with 5 bins** plus a bootstrap 95 % CI (1 000 resamples) — the docs' "ECE ≤ 0.045 with 10 bins" is unmeasurable at N=100 and is replaced by: `ECE_5bin ≤ 0.08` **and** CI upper bound ≤ 0.12.
- Acceptance vs heuristic on the **same** 100 test decisions:
  - macro-F1(classifier) − macro-F1(heuristic) ≥ 0.05 **and** McNemar exact test p < 0.05 on per-decision correctness; **or** bootstrap 95 % CI of the macro-F1 difference excludes 0.
  - Raw accuracy is reported but is **not** a gate (majority-class baseline ≈ 0.75).
- Artefacts in `models\router\clf-<sha>.txt` + `calib-<sha>.json` + `report-<sha>.md` (all metrics, CIs, confusion matrix, data-volume table).

## 7. Conformal guard (correct implementation)

```python
class ConformalGuard:
    def __init__(self, alpha: float = 0.10) -> None: ...          # α=0.10 default; 0.05 needs ≥ 100 cal points to be meaningful
    def fit(self, cal_probs: NDArray[f32] (n,K), cal_labels: NDArray[i64] (n,)) -> None:
        scores = 1.0 - cal_probs[np.arange(n), cal_labels]        # non-conformity of the TRUE class
        q_level = math.ceil((n + 1) * (1 - self.alpha)) / n
        if q_level > 1.0: raise InsufficientCalibration(n, alpha)  # n too small for this α
        self.q_hat = float(np.quantile(scores, q_level, method="higher"))
    def predict_set(self, probs: NDArray[f32] (K,)) -> list[int]:
        return [k for k in range(K) if 1.0 - probs[k] <= self.q_hat]
```
- Minimum calibration size for α: `n ≥ ceil(1/α) − 1` → α=0.10 needs n ≥ 9 (use ≥ 100); α=0.05 needs ≥ 19 (use ≥ 200). Enforced by `InsufficientCalibration`.
- Sliding-window recalibration: refit `q_hat` weekly on the most recent 100 labelled decisions; log `q_hat` history.
- Policy: `len(set)==1 → act`; `len(set)>1 or 0 → fallback_applied=True, action=LLM`.
- Acceptance on test split: empirical coverage ≥ `1 − α − 1/√n_test` (α=0.10, n=100 → ≥ 0.80); average set size ≤ **1.30** (doc's 1.15 was unjustified for 3 classes at this N); fallback rate reported.

## 8. Tests

| ID | Test | Pass |
|---|---|---|
| T-RTR-01 | Word-boundary lexicon: adversarial fixtures | 0 false positives |
| T-RTR-02 | Heuristic intent macro-F1 on fixtures | ≥ 0.85 |
| T-RTR-03 | `route()` + POSTTURN persists a `decisions` row and a JSONL line | — |
| T-RTR-04 | Speculative dispatch: RULE decision → `abort()` called once, plan executed, LLM stream discarded | Tier 2 |
| T-RTR-05 | Labeling function on 30 fixture turn-pairs | exact labels |
| T-RTR-06 | `ConformalGuard.fit` with n=5, α=0.05 → `InsufficientCalibration` | — |
| T-RTR-07 | Synthetic 3-class data (n_cal=200): coverage within `[1−α−0.03, 1−α+0.05]` over 20 seeds | — |
| T-RTR-08 | Set-size policy: size 2 → LLM + `fallback_applied` | — |
| T-RTR-09 | Chronological split respected (no test ts < any train ts) | — |
| T-RTR-10 | Report generator emits all required fields; gate evaluator refuses when data-volume floor unmet | — |
