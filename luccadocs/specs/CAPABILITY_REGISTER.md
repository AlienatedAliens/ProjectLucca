# Project Lucca — Capability Register & Maturity Specification

**Spec ID:** `SPEC-CAP-REG-v1.0`
**Created:** 2026-11-01 (WO-39 planning set)
**Status:** PROPOSED — first draft for owner review. Maturity ratings below are *assessments from code and documentation reading*, not measurements, unless a cited artifact says otherwise.
**Machine-readable mirror:** [`data/capabilities.yaml`](../../data/capabilities.yaml) (schema in §6; enforced by `test_capability_register_yaml_and_gates` in [`tests/test_static_gates.py`](../../tests/test_static_gates.py))
**Governing rules:** `AGENTS.md` Rule 8 (no unverified labels; "Author-measured"/"Self-measured"/"Unit-tested" only), Rule 05 (live-sourced comparisons only — see the sibling document [`../research/COMPETITIVE_MATRIX.md`](../research/COMPETITIVE_MATRIX.md)).

---

## 0. Why this document exists

The repo documents **mechanisms** (cascade, Belnap fusion, CEGIS, signers) and **benchmark scores**, but has never defined **what Lucca does for the owner, how well, and how anyone checks it**. That gap produced concrete damage:

1. `schedule_event` was previously an L1 stub that validated a date and returned a random ULID without storing or firing anything (**Resolved 2026-11-02:** [`src/lucca/sandbox/schedule_tool.py`](../../src/lucca/sandbox/schedule_tool.py) now persists reminders into SQLite `scheduled_events` and [`Orchestrator.maybe_fire_due_events()`](../../src/lucca/core/orchestrator.py) claims and speaks due events on the idle heartbeat).
2. The guide's headline "783.6 ms turn latency" sums routing + container + retrieval + TTS synthesis and contains **no LLM prefill or generation** ([`USER_GUIDE_WHAT_LUCCA_DOES.md:18`](./USER_GUIDE_WHAT_LUCCA_DOES.md)). It is not a turn-latency metric.
3. Tier-0 serving parameters disagree across three living documents: `AGENTS.md` says `ctx=131072`, the guide says `ctx=32768 / ngl=28`, and the guide's own §0 paragraph vs [`src/lucca/core/config.py`](../../src/lucca/core/config.py) disagree on `ngl`. A capability register with cited evidence forces one truth per row.
4. There is no answer to "is Lucca done?" because nothing enumerates *done with respect to what*. §7 defines the target profile that answers it.

**This spec is the user-facing spine.** Every work order after this one should state which capability IDs it moves, and by how many maturity rungs, with which acceptance evidence.

---

## 1. Maturity ladder (defines what "capable" means)

| Rung | Name | Definition | Evidence required to claim it |
|---|---|---|---|
| **L0** | Not built | No implementation, or interface only in docs. | Absence noted honestly in the register and backlog. |
| **L1** | Stub | Interface exists and passes shape checks, but performs no real user-visible work. | **Must be marked `stub: true` in YAML; must NOT be advertised to the LLM tool list or the user guide.** |
| **L2** | Built + unit-tested | Implemented; exercised by automated tests against fakes/mocks. | Named test file(s) green in CI. Label: *Unit-tested*. |
| **L3** | Live on hardware | Runs end-to-end on the owner's machine under realistic conditions, measured by the owner. | Script + artifact + timestamp. Label: *Author-measured*. |
| **L4** | Proven in daily use | Sustained evidence across real daily sessions (counts, error rates, owner log). | Dogfood ledger entries over ≥ 30 days. Label: *Self-measured, daily-use*. |

Rules:
- No capability may be described in living docs at a rung higher than its YAML row's rung.
- Third-party-reproducible claims require an external reproducer; until then, per Rule 8, only *Author-measured / Self-measured / Unit-tested* labels are permitted.
- Promotion across rungs is a documentation PR that links the artifact and the gate/test it satisfies (Rule 8 evidence-citation rule).

---

## 2. Capability register (user jobs)

Maturity column = **proposed rating** (my assessment from this session's code/doc audit). `E` = evidence reference; `A` = acceptance check that must exist for the rung claimed.

### Presence & voice

| ID | User job | Example you say | What actually happens today | Maturity | Evidence / Acceptance |
|---|---|---|---|---|---|
| `CAP-VOICE` | Push-to-talk conversation in her voice | hold Right Alt, speak, release | PTT → VAD → Whisper ASR (`~74 ms`) → Gemma tier → Kokoro TTS (`~555–724 ms`), affect prosody, barge-in | L3 | E: [`scripts/bench_turn_latency.py`](../../scripts/bench_turn_latency.py), [`data/benchmarks/turn_latency/summary.json`](../../data/benchmarks/turn_latency/summary.json) (Author-measured warm p50/p95: **907.88 ms / 1,136.42 ms** on E4B; **1,360.57 ms / 1,821.13 ms** on 12B). |
| `CAP-REFLEX` | Emergency stop | "stop", "halt", "mute" | Deterministic reflex path, no LLM, <150 ms | L3 | E: `EMERGENCY_REFLEX_PATTERN`, `tests/test_router.py`. Keep regex/deterministic forever (auditable fast path). |
| `CAP-PRESENCE` | Be available ambiently | just talk to her like a person | Push-to-talk only; one Windows laptop; needs Docker/WSL + llama-server up | L2 | **Gap:** open-mic wake word deferred (backlog §voice). Acceptance for L3: `env_check` green + unattended 8 h session log. |

### Memory & self-knowledge

| ID | User job | Example you say | What actually happens today | Maturity | Evidence / Acceptance |
|---|---|---|---|---|---|
| `CAP-MEM-U` | Remember what you told her | "what did I tell you about X?" | Every user turn signed `USER_EXPLICIT`, FTS5+vec retrieval, inspectable/deletable via admin CLI & settings tab | L3 | E: guide §2.4, `tests/test_a1_autobiographical_memory.py`. Strongest asset. |
| `CAP-MEM-S` | Remember what she said/did | "did you actually search the web last week?" | `ASSISTANT_UTTERANCE` (continuity only, `grounding_eligible=0`) vs signed `ASSISTANT_ACTION` receipts; `SELF_HISTORY` substrate answers "did you do X" from records | L2→L3 | E: D-MEM-04, `tests/test_a1_acceptance_hw.py`. A: A1 battery ≥ threshold on live HW. |
| `CAP-ABSTAIN` | Refuse to invent the past or self | "what did I have for lunch Tuesday?" | Deterministic episode recall before LLM; confidence 0.60 fallback; split-conformal abstention once ≥30 labelled turns | L3 | E: `router/calibration.py:fit_guard_from_db`, `tests/test_c1_abstention_acceptance.py` (Wilson LB ≥ 0.80 on N=100 fixture). |
| `CAP-KNOWYOU` | Know you: preferences, goals, inferred facts | "you know I hate early meetings, right?" | Only verbatim user words persist; inference disabled (`USER_DERIVED` via `memory_commit` refuses model-authored content); `UserModel` v2 + `ActiveGoalManager` wired but goal-extraction needs live volume | **L1→L2** | **Gap:** inference path deliberately gated; zero accumulated live data. A(L3): 30-day dogfood log showing correctly recalled inferred preferences with user confirmation. |
| `CAP-LEARN` | Learn her own skills from repetition | you repeat a phrasing pattern ≥3 times | Rule induction produces `QUARANTINE` rules only; promotion requires 5 shadow clusters + operator via `lucca-admin`; **0 rules learned in production so far** | L2 | E: D-REAS-06, TR-04 (design note, no induction-quality eval). A(L3): first operator-promoted rule with shadow-replay error ledger. |

### Doing things

| ID | User job | Example you say | What actually happens today | Maturity | Evidence / Acceptance |
|---|---|---|---|---|---|
| `CAP-WORK` | File & notes work in one sandboxed folder | "write this to notes", "read config.toml" | `read_file`/`write_file`/`list_dir`/`search_text`/`note_*` inside `C:\ProjectLucca\workspace`; write ops confirmation-gated | L3 | E: guide §2.3, `sandbox/service.py` fail-closed dispatch, `tests/test_persistent_rpc.py`. |
| `CAP-CODE` | Run Python safely | "run this script" | `run_python` (+ async ULID tasks) inside persistent Docker worker; host fallback disabled (D-AUD-13); no Docker ⇒ structured `policy_violation`, never host exec | L3 | E: `rpc.py`, `AsyncTaskManager`, gate tests. |
| `CAP-MATH` | Hard math with verification | competition problems, conversions | `calc_math` AST; SymPy sandbox; PAL; thinking mode R1; CEGIS multi-turn repair | L3 | E: RESULTS.md rows (Author-measured): GSM8K PAL 95.75%, MATH-500 93.0% strict (12B), CEGIS 2× lift AIME subset. Scope note: benchmark quality ≠ unique capability (see competitive matrix). |
| `CAP-LOGIC` | Constraint solving | logic puzzles, scheduling constraints | Z3 SMT with `zebra_constraints.gbnf` deterministic compiler; ContainerWorld spatial state | L2→L3 | E: WO-28/36 records; needs a small live acceptance battery registered as a script. |
| `CAP-RESEARCH` | Web research with taint rules | "look up Judge Quintos" | `search_web`/`fetch_url` with Scrapling (`v0.4.6`) 3-tier anti-bot extraction (`curl_cffi` TLS impersonation + `sanitize_html_against_prompt_injection`), exfiltration sequence guard, `TOOL_CONTENT_UNTRUSTED` stamping, and concurrent `research_topic` synthesis | L3 | E: guide §2.1/§2.3, cascade `WEB` substrate, `src/lucca/sandbox/web_tool.py`, `src/lucca/sandbox/research_tool.py`. |
| `CAP-SEE` | See the screen / images | "what's on my screen right now?" | `screenshot_capture` + WinRT `OcrEngine` + native Gemma vision (mmproj); session image memory (WO-37) | L2→L3 | E: WO-37 records; A: live OCR-accuracy spot battery unregistered. |
| `CAP-HOST` | Act on the PC itself | "open Notepad", "what's in my clipboard" | `launch_app` (allowlist; `cmd.exe`/`powershell.exe` blacklisted per D-AUD-10), `clipboard_read`, `inbox_handoff`; all Class C confirmation-gated. **No GUI automation, no email/calendar/messaging — by design.** | L2 | E: policy.py allowlists, `tests/test_static_gates.py`. This is deliberately narrow (safety doctrine); competitive gap stated in matrix, not papered over. |
| `CAP-REMIND` | Reminders and scheduled events | "remind me at 6 pm" | `schedule_event` validates ISO 8601 datetime, persists to SQLite `scheduled_events`, and [`Orchestrator.maybe_fire_due_events()`](../../src/lucca/core/orchestrator.py) claims due reminders on the idle heartbeat, speaks them via TTS, and publishes `schedule.fired` on the UI bus | **L2** | E: [`schedule_tool.py`](../../src/lucca/sandbox/schedule_tool.py), `tests/test_new_tools.py`. A(L3): live session reminder fire verification. |

### Proactivity & interiority

| ID | User job | Example you say | What actually happens today | Maturity | Evidence / Acceptance |
|---|---|---|---|---|---|
| `CAP-PROACT` | She notices things and speaks first | (nothing — she initiates) | `IdlePulse` (60 s NLI coherence pass) and `DreamRetrospective` wired; user-visible proactive output today ≈ waking-continuity note after a session gap only | L1→L2 | E: WO-36 wiring, D-REAS-06 quarantine pipeline. A(L3): ledger of proactive events per day + owner-rated usefulness sample. |
| `CAP-AFFECT` | Mood-shaped voice, not robotic | ordinary chat | PAD ODE → prosody modulation + stance suffix at prompt frontier; `CognitiveOutcomeSink` (EUREKA/TASK_SUCCESS/TOOL_FAILURE events) | L2→L3 | E: WO-27 (frozen), affect tests. Subjective; acceptance = owner rating rubric in dogfood ledger. |

### Honesty & safety (the differentiator — weakest verified link)

| ID | User job | Example you say | What actually happens today | Maturity | Evidence / Acceptance |
|---|---|---|---|---|---|
| `CAP-HONEST` | Never claim an action that didn't happen | she says "I deleted the file" | Receipt verbs matched; [`ActionClaimGrammarSupervisor`](../../src/lucca/sandbox/output_supervisor.py) + [`TruthInReceiptMatcher`](../../src/lucca/sandbox/output_supervisor.py) + clause-level Intel NPU [`NeuralActionClaimVerifier`](../../src/lucca/sandbox/neural_action_claim_verifier.py) (`models/action_claim_verifier_ov`) in [`coherence.py`](../../src/lucca/core/coherence.py) achieve **99.26% accuracy (`2,007/2,022`), 98.73% recall (`465/471`), and 0.58% FPR (`9/1,551`)** on the `N=2,022` multi-sentence/adversarial battery (`logs/test_reports/wo42_large_sample_2020_report.json`), **100/100** across `Blind-390` + `LOCKED_COH_050`, and **28/28** live 4-model adversarial FAC interception (`logs/test_reports/wo42_live_4model_100turn_report.json`) | **L2** ⚠️ | E: `neural_action_claim_verifier.py`, `coherence.py`, `logs/test_reports/wo42_large_sample_2020_report.json`, `logs/test_reports/wo42_live_4model_100turn_report.json`. A(L3): 30-day daily-use dogfood ledger (`FP <= 2%` criterion already satisfied at `0.58%` on `N=2,022`). |
| `CAP-SELFINFO` | Accurate self-knowledge (tools, model, GPU) | "what tools do you have?" | `query_capabilities`/`self_metrics` from live registries; capabilities substrate *abstains* if registry unavailable | L3 | E: guide §2.1, cascade substrate 6. |
| `CAP-PRIVACY` | Nothing leaves the machine | (default posture) | Fully local: llama-server native, Docker WSL2 sandbox, SQLite memory, NPU/CPU senses; no cloud calls in product path | L3 | E: ARCHITECTURE.md; A: 30-day egress audit script (no external sockets from Lucca processes except opt-in web research) — **not yet written**. |
| `CAP-SAFE-ACT` | Destructive/injection attempts intercepted | "delete C:\Windows" | Policy gates, sequence guard, taint rules, confirmation tokens (single-use HMAC), injection suite | L3 | E: THREAT_MODEL.md, injection suite 20/20 (Author-measured, self-authored suite; external red-teaming absent — TR-05 caveat stands). |

---

## 3. Stubs-and-gaps ledger (the honest "what is NOT true" list)

This ledger is the anti-drift instrument; living docs must not contradict it.

| Item | Ledger entry |
|---|---|
| `schedule_event` | **Resolved (2026-11-02):** Upgraded from L1 stub to L2 (`scheduled_events` SQLite persistence in [`schedule_tool.py`](../../src/lucca/sandbox/schedule_tool.py) + idle-heartbeat firing via [`Orchestrator.maybe_fire_due_events()`](../../src/lucca/core/orchestrator.py)). |
| Turn latency "783.6 ms" | **Resolved (2026-11-02):** Replaced with full-turn PTT-release-to-first-audible-speech benchmark ([`scripts/bench_turn_latency.py`](../../scripts/bench_turn_latency.py), [`data/benchmarks/turn_latency/summary.json`](../../data/benchmarks/turn_latency/summary.json)): warm p50/p95 is **907.88 ms / 1,136.42 ms** on E4B (cold 1,744.77 ms) and **1,360.57 ms / 1,821.13 ms** on 12B (cold 2,964.73 ms). |
| Tier-0 serving params | **Resolved (2026-11-02):** `AGENTS.md`, `MODEL_STRATEGY.md`, `ARCHITECTURE.md`, `README.md`, and `USER_GUIDE` aligned to [`src/lucca/core/config.py:LLMSettings`](../../src/lucca/core/config.py) (`ctx=65536`, `ngl=99`, `--cpu-moe`, `--moe-cache-mib 7680`, `ubatch=2048`, `--mmproj mmproj-gemma-4-26B-A4B-it-BF16.gguf`). |
| Skills on live voice | Most tool-call skills yield hints to the model, not autonomous actions (guide §2.5 already says this honestly — keep it). |
| Learned rules | 0 production-learned; quarantine pipeline untested at scale. |
| User model inference | Disabled by doctrine; `UserModel` v2 needs live volume; no dogfood data yet. |
| Proactivity | Only waking-continuity today; "notice and speak first" effectively L1. |
| Honesty supervisor | **Updated (2026-11-06 / `WO-42`):** Clause-level Intel NPU `NeuralActionClaimVerifier` (`src/lucca/sandbox/neural_action_claim_verifier.py`) + `coherence.py` achieves **99.26% accuracy (`2,007/2,022`), 98.73% recall (`465/471`), and 0.58% FPR (`9/1,551`)** across the `N=2,022` evaluation battery (`logs/test_reports/wo42_large_sample_2020_report.json`), **100/100** across `Blind-390` + `LOCKED_COH_050`, and **28/28** live 4-model adversarial FAC interception (`logs/test_reports/wo42_live_4model_100turn_report.json`). L3 promotion awaits only the 30-day daily-use dogfood ledger. |
| Host action scope | No GUI automation/email/calendar — intentional, but must be stated in user-facing text so owners aren't misled. |
| External validation | No third-party reproduction of any benchmark; no external red-team. All scores Author-measured. |

---

## 4. Tool → capability map (all 24 advertised tools)

Registry: `get_default_native_tools()` ([`core/capabilities.py`](../../src/lucca/core/capabilities.py)), cap `MAX_REGISTRY_TOOLS = 24`.

| Tool | Capability ID | Class |
|---|---|---|
| `read_file` `write_file` `list_dir` `search_text` `note_write` `note_read` | `CAP-WORK` | self |
| `run_python` `run_python_async` | `CAP-CODE` | self |
| `calc_math` | `CAP-MATH` | self |
| `memory_search` `self_history_search` | `CAP-MEM-U` / `CAP-MEM-S` | self |
| `memory_commit` | `CAP-MEM-U` (grounded) | grounded commit |
| `invoke_skill` | `CAP-LEARN` / skills | self |
| `search_web` `fetch_url` | `CAP-RESEARCH` | self |
| `schedule_event` | `CAP-REMIND` | self (`scheduled_events` SQLite persistence + idle heartbeat fire) |
| `artifact_verify` | `CAP-HONEST` | self |
| `query_capabilities` `sys_info` `self_metrics` | `CAP-SELFINFO` | host_readonly |
| `launch_app` `clipboard_read` `inbox_handoff` | `CAP-HOST` | shared (confirmation) |
| `screenshot_capture` | `CAP-SEE` | shared |

Quarantined internal schemas (`delete_file`, `get_task_status`, `list_tasks`, `cancel_task`) stay in `EXTRA_TOOL_SCHEMAS` per WO-19a.

---

## 5. Measurement obligations (what must exist before L3/L4 claims)

| Metric | Definition to adopt | Artifact to create |
|---|---|---|
| **Turn latency (full)** | release-of-PTT → first audible speech, p50/p95, per tier (E4B/12B), cold and warm prefix cache | `scripts/bench_turn_latency.py` + `data/benchmarks/turn_latency/` |
| **ASR tail latency** | release → transcript final | same bench script, stage timings from turn trace |
| **Honesty FP/FN** | live-labelled claim audit: precision/recall + Wilson 95% CI, per tier | extends `scripts/eval_deontic_supervision.py` onto dogfood labels |
| **Recall correctness** | memory-search answer correctness on 30-day dogfood corpus, owner-labelled | `scripts/dogfood_recall_eval.py` |
| **Proactive usefulness** | events/day + owner useful/false-alarm ratio | dogfood ledger schema in `V2_BACKLOG` §dogfooding |
| **Privacy egress** | zero unexpected external sockets; allow-list: user-initiated `search_web`/`fetch_url` only | `scripts/egress_audit.py` |
| **Availability** | 24 h soak: process up, ring-buffer underrun = 0, Docker bridge green | extends `scripts/test_session_flow.py --auto` + env_check |

Until an artifact exists, the affected capability stays at its assessed rung — the register never runs ahead of evidence.

---

## 6. Machine-readable mirror & static gates

`data/capabilities.yaml` (schema v1):

```yaml
schema_version: 1
capabilities:
  - id: CAP-VOICE
    job: push-to-talk voice conversation
    maturity: L3
    maturity_basis: author-measured      # unit-tested | author-measured | self-measured | assessment
    stub: false
    risk_class: A
    acceptance:
      kind: script
      ref: scripts/bench_turn_latency.py   # pending — L3 not claimable until this exists
      criteria: p95 first-speech <= 1500 ms on E4B tier
    evidence:
      - luccadocs/research/papers/02_SUB_50MS_BARGE_IN_AND_ZERO_COPY_AUDIO.md
    failure_modes: [ASR mis-transcribe on crosstalk, TTS underrun]
    competitor_refs: []                   # only Rule-05-live-sourced entries
    target_maturity_v2: L3
  - id: CAP-REMIND
    job: reminders and scheduled events
    maturity: L1
    maturity_basis: assessment
    stub: true
    ...
```

Proposed static gates (extend `tests/test_static_gates.py`):
1. **Advertise gate:** every tool in `get_default_native_tools()` maps to ≥1 YAML capability; any capability with `stub: true` ⇒ its tool must be absent from the advertised registry and from `USER_GUIDE` §2.3 table. (Catches the `schedule_event` class of bug structurally.)
2. **Doc-consistency gate:** capability rungs referenced in living docs may not exceed YAML rungs (text lint on capability IDs).
3. **Evidence gate:** any YAML row at L3/L4 must cite ≥1 existing artifact path that exists on disk.
4. **Tool-count gate (existing):** 24 ≤ `MAX_REGISTRY_TOOLS` preserved; YAML tool map row count must equal registry length.

---

## 7. Target profile — "Lucca 2.0 complete"

| ID | Now | v2 target | What closing it requires |
|---|---|---|---|
| CAP-VOICE | L3 | L3 (honest metric) | §5 turn-latency artifact |
| CAP-REFLEX | L3 | L4 | daily-use log |
| CAP-PRESENCE | L2 | L3 | wake-word/open-mic decision (backlog) |
| CAP-MEM-U | L3 | L4 | 30-day dogfood ledger |
| CAP-MEM-S | L2→L3 | L4 | A1 battery on live HW + ledger |
| CAP-ABSTAIN | L3 | L4 | live-calibrated Wilson check |
| CAP-KNOWYOU | L1→L2 | L3 | live volume + inference gate decision (D-MEM doctrine preserved) |
| CAP-LEARN | L2 | L3 | first operator-promoted rule + induction-quality eval |
| CAP-WORK / CAP-CODE / CAP-MATH | L3 | L4 | daily-use ledger |
| CAP-LOGIC / CAP-SEE | L2→L3 | L3 | registered acceptance batteries |
| CAP-RESEARCH | L3 | L3 | (already adequate) |
| CAP-HOST | L2 | L2 | stays narrow **by design** — target is honesty of advertisement, not breadth |
| **CAP-REMIND** | **L2** | **L3** | live session fire verification + dogfood log |
| CAP-PROACT | L1→L2 | L3 | proactive event ledger + usefulness data |
| CAP-AFFECT | L2→L3 | L3 | rating rubric |
| **CAP-HONEST** | **L2** | **L3** | classifier supervisor out of shadow (WO-39 P1), FP ≤ 2% |
| CAP-SELFINFO | L3 | L4 | ledger |
| CAP-PRIVACY | L3 | L4 | egress audit over 30 days |
| CAP-SAFE-ACT | L3 | L3+ext | external red-team engagement (closes TR-05 caveat) |

Bold = the three rows that make "Lucca 2.0" mean something: reminders real, honesty proven, memory proven in daily use. Everything else is polish.

---

## 8. Review questions for the owner

1. Is the user-job list (§2) the right decomposition, or is something missing (e.g. multi-user, second device, avatar)?
2. Accept the maturity ladder + the three P0 actions (schedule_event, turn-latency metric, ctx/ngl truth)?
3. Is the v2 target profile too conservative on `CAP-HOST` (GUI automation stays out forever by doctrine — confirm)?
4. Approve the four static gates (§6) for implementation in a code-mode work order?
