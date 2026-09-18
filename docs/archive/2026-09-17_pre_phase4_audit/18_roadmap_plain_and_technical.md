# 18 — The Lucca Roadmap, Explained Twice

Every stage below is described **for a layperson** (what you'll notice, what it means) and then **for a developer** (what gets built, what proves it's done, where it's specified). Read one column or both.

Version labels: **v1.0** = Phases 0–3 + Phase 4 pipeline · **v1.1** = Phase 5 · **v1.2** = Phase 6 · **v2.x** = Phase 7 growth steps.
Time is in *effort*, not calendar; Phases 4–6 additionally need weeks of your real use (marked ⏳ human gate).

---

## The whole thing in one picture

```
 Phase 0        Phase 1        Phase 2        Phase 3        Phase 4        Phase 5        Phase 6        Phase 7+
 "Does the      "Ears and      "Hands"        "Memory"       "Notice        "Learn         "Learn         "Grow"
  hardware       voice"                                        patterns"      habits"        judgement"
  work?"
   │              │              │              │              │              │              │              │
 measure        talk ↔ hear    read/write     remember       log every      compile        train router   richer rules,
 everything     ~0.5 s         files, fetch   only what's    decision +     repeated       + conformal    2nd brain,
                interruptible  web, open apps provable       auto-label     behaviour      safety net     vision, avatar
                                                                              into rules
 ──────────────── v1.0 ──────────────────────────────────────►  ── v1.1 ──►  ── v1.2 ──►  ── v2.x ──►
                                                              ⏳ needs        ⏳ needs        ⏳ needs
                                                              your use        your use        ~600 turns
```

---

## Phase 0 — "Does the hardware actually do what we assumed?" (≤ 3 days)

**Layperson.** Before building anything, we test the five risky assumptions on your actual laptop: that the speech model loads and answers fast on the GPU, that the "hearing" model runs on the Intel NPU, that the voice runs on the NPU (or, if not, how fast it runs elsewhere), that the embedding model fits, and that the Windows/WSL/Docker setup is correct. Every number we've been *estimating* gets replaced with a *measurement*. Nothing you can use comes out of Phase 0 — but everything after it stands on real numbers instead of hopes.

**Developer.** Five spikes with exit conditions and pre-declared fallbacks ([`11_phase_plan_v2.md`](11_phase_plan_v2.md) §Phase 0): 0.1 environment (`lucca-admin env-check` green: MSHybrid VRAM baseline, CUDA 12.8, `.wslconfig` canonical, Docker CE in Ubuntu, sqlite-vec loads, NPU visible); 0.2 `llama-server` + Ultravox Q6_K + mmproj — ADR-001 S1–S10 (TTFT ≤ 200 ms median, ≥ 60 tok/s, ≤ 9.5 GB VRAM, tool-call + grammar + audio in one request, abort ≤ 50 ms, cascade works on the same file); 0.3 Whisper-large-v3-turbo on NPU (WER ≤ 8 %, 3 s clip ≤ 300 ms p95) else GPU/CPU ladder; 0.4 Kokoro device ladder (first chunk ≤ 180 ms on whichever device passes); 0.5 MiniLM on NPU (≤ 15 ms). Output: `docs/14_phase0_results.md` replacing every *estimate* in the specs. If a threshold fails: record in `docs/14_blockers.md`, do not relax it.

---

## Phase 1 — Ears and voice (v1.0 part 1)

**Layperson.** This is when Lucca first exists. You hold right-Ctrl, talk, let go; about half a second later a small sprite on your desktop moves its mouth and answers in a natural voice. Press the key again while it's talking and it stops instantly and listens. It hears you via one model (Whisper) and understands you via another (Ultravox) at the same time — the hearing model is what lets it write down exactly what you said. If the fast "listen directly to audio" mode doesn't hit the speed target on your machine, it falls back to "transcribe first, then answer" — slightly slower, and it tells you which mode it's in. What it can't do yet: touch files, remember anything past the current conversation, or do anything on its own.

**Developer.** Four processes + supervisor ([ADR-008](08_adr/ADR-008_process_topology.md), [spec 01](09_developer_spec/01_process_topology_and_ipc.md)): `lucca-audio` (WASAPI 16 k in / 24 k out, Win32 PTT hook with QPC timestamps, Silero VAD, shared-memory rings, jitter buffer), `lucca-npu` (OpenVINO Whisper/Kokoro/MiniLM with device ladders), `lucca-core` (turn state machine, LLM client with tool-call demux, chunker, trace), `lucca-ui` (PyQt6 overlay, RMS lip-flap). Speculative dispatch: audio → LLM and audio → ASR in parallel. Barge-in sequence ≤ 30 ms to silence, ≤ 100 ms to LLM slot idle ([spec 07 §7](09_developer_spec/07_audio_pipeline_and_barge_in.md)). Chunker with one-token lookahead, abbreviation/decimal protection, markdown stripping ([spec 08](09_developer_spec/08_streaming_chunker_spec.md)). **Done when** ([matrix §4](10_testing_matrix_v2.md)): latency e2e from trace — median ≤ 600 / p95 ≤ 800 ms audio mode (≤ 800 / 1 000 transcript mode), both reported; VRAM ≤ 9.5 GB, slope ≤ 20 MB/turn; 10 consecutive turns without desync; T-AUD/ASR/TTS/BRG/CHK green; 200-turn soak. TTS device is *reported* (NPU preferred), not required.

---

## Phase 2 — Hands (v1.0 part 2)

**Layperson.** Lucca gets a locked workshop. You drop files into `C:\ProjectLucca\inbox`; Lucca can read, search, and write copies of them inside its own workspace — a folder it can see and nothing else. It can fetch a public web page and summarise it. It can open apps from a list you approve (calculator, notepad, browser…). **Every time it wants to write a file or open an app, it asks you aloud, naming the actual file or app, and waits for "yes."** The file room has no internet; the internet room has no files — so nothing it reads can be smuggled out, and nothing it fetches can quietly change your files. Web pages it reads are treated as untrusted text: it can tell you about them, but they can't become part of its memory or make it do things.

**Developer.** Docker CE inside Ubuntu WSL2 ([ADR-003](08_adr/ADR-003_sandbox_egress_policy.md)); two container specs ([ADR-004](08_adr/ADR-004_split_sandbox_containers.md), [spec 09 §2](09_developer_spec/09_sandbox_hardening.md)): `file-sandbox` (`--network none`, bind of `C:\ProjectLucca\workspace` only, read-only root, cap-drop ALL, uid 1000, 768 MB) and ephemeral `web-sandbox` (egress chain: established → RFC1918/link-local/CGNAT REJECT → 80/443 ACCEPT → DROP; DNS pinned in `daemon.json`; IPv6 off). RPC = `docker exec` JSON over stdio, no ports, no socket exposure. `validate_rel_path` (reject `%`, NUL, `..`, symlinks; realpath + `O_NOFOLLOW`), size caps, `run_python` under rlimits. Launcher whitelist with templated args, `shell=False`, rate limit. Risk policy: READ/NETWORK auto; WRITE/LAUNCH confirm; ≤ 4 tool calls/turn; forbidden sequences (`read_file→fetch_url`, `fetch_url→write_file`) ([spec 12 §3](09_developer_spec/12_threat_model.md)). Host wipes workspace at task close. **Done when** T-SBX-01…19 green, incl. the **positive-controlled** egress table (a LAN listener reachable from Ubuntu, unreachable from the container), path fuzzing (5 000 Hypothesis cases), container-spec snapshot, forbidden-sequence refusal, and "summarise the files in my inbox" end-to-end.

---

## Phase 3 — Memory (v1.0 part 3) — *in progress*

**Layperson.** Lucca starts to remember — but under a strict rule: **it may only remember what it can prove.** Three kinds of things qualify: your exact words (from the hearing model), facts pulled out of your words *only if every name and value appears in what you actually said*, and hard facts about things it did (a file existed, a command succeeded). Things it merely *said* can never become memory — there is literally no mechanism for it. Say "I moved to Berlin" and it stops believing Seattle but remembers you used to live there. Say "forget that" and it reads back what it'll delete, then deletes it (recoverable for 30 days). Everything it knows about you can be exported as a plain text file with one command. It backs itself up daily.

**Developer.** One SQLite file, WAL + FTS5 + sqlite-vec, single writer in `lucca-core` ([ADR-002](08_adr/ADR-002_memory_storage.md), [spec 04](09_developer_spec/04_memory_storage_schema.md) DDL incl. bi-temporal `kg_edges`, `memory_sources` lineage, audit log, migrations, eligibility trigger). Provenance ([ADR-006](08_adr/ADR-006_provenance_tiers_and_signers.md), [spec 03](09_developer_spec/03_provenance_model.md)): closed enum; per-provenance HKDF-derived capability signers constructed only in allow-listed modules (AST test + import-linter); canonical-JSON HMAC over all fields; nonce + freshness; `USER_DERIVED` requires quote-grounding (substring or `partial_ratio ≥ 90`) against a `USER_EXPLICIT` source; `TOOL_CONTENT_UNTRUSTED` never memory-eligible. Hybrid retrieval = RRF(dense top-30, FTS top-30 with sub-token index) + 1-hop graph, k = 8, ≤ 600 tokens. Functional predicates supersede (latest-wins, history kept). **Done when** T-PROV-01…12 (incl. end-to-end hallucination-write: FakeLLM asserts a false "fact" and calls a tool → 0 memory rows, 1 audit reject; static signer allow-list; fail-closed on dev key), T-MEM-01…14 with frozen benchmarks (Hit@1 ≥ 0.93 identifiers, MRR delta ≥ 0.20, Recall@3 ≥ 0.90, P@1 ≥ 0.85, p95 ≤ 25 ms @ 50 k rows), supersession, forget, crash-mid-commit, and the *positive-controlled* working-memory discard test.

**v1.0 ships here** — Lucca talks, acts, remembers — once the Phase 4 logging pipeline (below) is also running.

---

## Phase 4 — Noticing patterns (v1.0 pipeline; ⏳ human gate for v1.1)

**Layperson.** Nothing visible changes. Behind the scenes Lucca starts keeping a careful diary: for every request, what it decided to do, what actually happened, and — worked out automatically from your reaction — whether that was the right call. Interrupting it within a second and a half, or saying "no, that's wrong" as your next sentence, counts as "wrong." Silence and moving on counts as "fine." This diary is the raw material for everything it learns later. The one thing you have to do: **use it.** The next phase cannot begin until there are at least 100 real logged interactions, and no one is allowed to fake them.

**Developer.** Heuristic router with word-boundary intent lexicon and adversarial fixtures (macro-F1 ≥ 0.85, 0 false `launch_app`); `DecisionRecord` persisted to SQLite + JSONL every turn; **labeling protocol** ([spec 06 §4](09_developer_spec/06_router_classifier_and_labeling.md)): early barge-in / explicit negation / tool failure → NEG; declined confirm → INDETERMINATE; counterfactual `rule_would_match`; else POS — all derivable by replay and unit-tested on fixtures. Speculative dispatch + `abort()` on RULE. Rule engine evaluates every turn (active and quarantine) so `any_*_rule_fired` is logged. **Mechanically done when** T-RTR-01…05 green and every turn yields a decision row + label. **H-4 (human gate):** ≥ 100 labelled decisions from live use or deterministic replay of recorded sessions (`lucca-admin replay`), never synthetic. Dogfooding protocol: 4 sessions, 25+ varied utterances each, every intent ≥ 5×, ≥ 5 corrections, ≥ 3 barge-ins.

---

## Phase 5 — Learning habits (v1.1; ⏳ human gate)

**Layperson.** This is the heart of the project. Lucca looks through its diary for things you ask for repeatedly and that it handled the same way each time. When it spots one, it writes a tiny rule for itself — a few lines, in a small, readable programming language (a dialect of LISP) — that says *when* the situation looks like this, *plan* to do that. The rule is then put on probation: it runs silently alongside the normal path and is checked against what actually happened. Only after it has been right on **five genuinely separate occasions and never wrong** does Lucca announce: "I've learned a shortcut: opening the calculator when you ask. Say 'stop doing that' to remove it." From then on that request is handled instantly, without the language model — and still with a spoken confirmation if it writes or launches anything. One mistake in production sends the rule back to probation; two demotions retire it; "stop doing that" is permanent. Expect the first shortcut after two or three weeks of daily use.

**Developer.** MicroScheme v2 ([spec 05](09_developer_spec/05_rule_dsl_grammar_and_lifecycle.md), [ADR-007](08_adr/ADR-007_rules_as_pure_plans.md)): regex lexer; O(n) parser with depth/size caps; special-form `and/or/if`; frozen primitives; fresh env per eval; gas 1 000, wall 20 ms, numeric/string/list caps; all Python exceptions wrapped. Canonical form `(rule id :when <pure-bool> :plan (list (tool …) (say …)) :priority n)` over a versioned `RuleState`. Static validation (registered tools, arg schemas, no constant-true `when`). Shadow = structural diff of planned vs executed tool calls; `INDETERMINATE` on barge-in/cancel. Distinctness = `sha1(session | 15-min bucket | agglomerative cluster @0.25)`. Lifecycle `PROPOSED → QUARANTINE → ACTIVE ⇄ DEMOTED → RETIRED`; regression cases captured at promotion; `verify_regression_suite` never vacuous. Reflection: idle ≥ 60 s, ≥ 10 new decisions, ≤ 1/10 min, aborts on PTT; GBNF-constrained generation; metrics `parse_ok/static_ok/quarantined`. **Mechanically done when** T-LISP/T-RULE/T-REFL green and a seeded synthetic session set yields ≥ 1 promotion through the real pipeline with fakes. **H-5:** ≥ 1 rule promoted from real or replayed-real usage; user hears the notice and can retire by voice.

---

## Phase 6 — Learning judgement (v1.2; ⏳ data-floor gate)

**Layperson.** Until now, deciding *how* to handle a request (use a learned shortcut, ask the language model, or ask you to clarify) has used simple hand-written rules. Once there's enough diary — around 600 interactions over a couple of weeks — Lucca trains a small statistical model on your actual corrections to make that call better. It comes with a safety net: when the model isn't confident, it falls back to the slow-but-safe path, and that "when to be unsure" threshold is calibrated with a real statistical guarantee rather than a guess. If there isn't enough data, this phase simply waits; it is never done with less.

**Developer.** Data floor: ≥ 600 labelled decisions, ≥ 30 per class in a **chronological** test split, ≥ 20 sessions, ≥ 14 days — enforced by `lucca-admin router report` ([spec 06 §5](09_developer_spec/06_router_classifier_and_labeling.md)). Features: MiniLM (NPU) embedding + 24 hand features. Model: LightGBM (CPU; tree models never on NPU) or logistic regression if per-class N < 60. Temperature scaling, then **split-conformal** guard with `fit()` computing `q̂` at `⌈(n+1)(1−α)⌉/n`, α = 0.10, `InsufficientCalibration` if n too small, weekly sliding-window refit. **Done when** macro-F1 gain ≥ 0.05 over heuristic with McNemar p < 0.05 (or bootstrap CI excluding 0); ECE (5 bins) ≤ 0.08 with CI upper ≤ 0.12; coverage ≥ 1 − α − 1/√n; avg set size ≤ 1.30; report with CIs and confusion matrix in `models\router\report-<sha>.md`. Raw accuracy is reported, never gated.

---

## Phase 7+ — Growth (v2.x, each step its own ADR)

**Layperson.** Once the core is trustworthy, the interesting expansions become safe to add: rules that can branch and chain ("if it's a PDF, extract the text first, then summarise, then file the date") rather than single shortcuts; a second, much larger "thinking" model that wakes only when you're idle to propose better habits — your new 64 GB of RAM is what makes that possible; an honest little mood system driven by real events, never claimed feelings; seeing your screen; a nicer animated avatar; other languages. Each one is gated the same way everything else is: measured, tested, and reversible.

**Developer.** Rule-language growth path G1–G6 ([ADR-007 §Growth](08_adr/ADR-007_rules_as_pure_plans.md)): conditionals in plans → sequenced steps with typed intermediate results → rule composition (depth ≤ 3, acyclic) → `let` + pure helpers → HTN methods with a pyhop-class planner → grounded `assert` with `LISP_ASSERTION`. Reflective brain ([ADR-010 §4](08_adr/ADR-010_larger_models_after_64GB_upgrade.md)): second `llama-server` (or an expert-paging runtime, after the §7 checklist) resident in RAM, started at idle, stopped on PTT. Affect state ([guide 16 §4](16_user_guide_onboarding.md), ADR-009 proposed): valence/arousal from measured signals, decays τ = 600 s, never in `RuleState`/memory. Operator seeding (`lucca-admin memory seed` with per-line voice confirmation). Vision/OCR tools, Live2D/VRM, coreference, non-English, egress-proxy allow-list, gVisor if WSL2 permits, SQLCipher at rest. Every step: new ADR, spike with exit criteria, matrix additions, no gate loosened.

---

## What never changes, at any phase

| Rule | Why it exists |
|---|---|
| Nothing leaves the laptop; no telemetry | The product is trust |
| Model narration can never become memory | The central research claim |
| WRITE/LAUNCH always confirmed aloud, naming the target | Agency without surprises |
| Rules promote only after ≥ 5 distinct successes, 0 failures, regression suite | Habits must be earned |
| Every performance number comes from the trace/report files | Honesty over marketing |
| Thresholds are never relaxed to pass; blockers are recorded | Same |
| Human gates are never satisfied by synthetic data | Same |

## Where to look next

- Decisions and why: [`13_decisions_log.md`](13_decisions_log.md)
- Every number in one place: [`07_contradiction_register.md`](07_contradiction_register.md) §Canonical numbers
- What "done" means per phase: [`10_testing_matrix_v2.md`](10_testing_matrix_v2.md) §4
- Living with it day to day: [`16_user_guide_onboarding.md`](16_user_guide_onboarding.md)
- What it is and how it compares: [`17_project_summary_and_positioning.md`](17_project_summary_and_positioning.md)
