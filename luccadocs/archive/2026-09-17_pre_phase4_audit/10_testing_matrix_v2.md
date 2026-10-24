# 10 — Deep Mechanical Testing Matrix v2

Supersedes `04_deep_mechanical_testing_and_verification_matrix.md` wherever they differ (doc 04 tests were written against an API that does not match the code and contain an inverted latency assertion, a vacuous egress test, and a vLLM-specific VRAM check). Test IDs referenced from the specs are collected here; the spec owning each ID holds the detailed pass condition.

## 1. Tiers and how to run them

| Tier | Marker | What | Needs | Command | Must pass before |
|---|---|---|---|---|---|
| T0 static | — | ruff, mypy --strict, import-linter, AST tests | nothing | `uv run lint` | every commit |
| T1 unit | (default) | pure logic: scheme, chunker, path validation, gate, lifecycle, conformal math, labeling | nothing | `uv run pytest -m "not tier2 and not hw and not soak"` | every commit |
| T2 fake-backed integration | `tier2` | orchestrator turn loop with `Fake*` adapters (scripted LLM SSE incl. tool calls, fake TTS/ASR, fake sandbox, in-memory SQLite) | nothing | `uv run pytest -m tier2` | every PR |
| T3 hardware | `hw` | real llama-server, NPU, audio loopback, WSL Docker | the MSI laptop | `uv run pytest -m hw` | phase sign-off |
| T4 soak | `soak` | 200-turn endurance, 30-min thermal, RAM/VRAM slopes | laptop, ~1 h | `uv run pytest -m soak` | Phase 1, 3, 5 sign-off |
| T5 human gate | — | dogfooding protocol / replay of recorded sessions | human | see phase plan | Phases 4–6 |

Every `hw` test writes a machine-readable report to `logs\test_reports\<test>-<ts>.json` **and** asserts. "Reported honestly" = the report file exists and the numbers in the sign-off doc are copied from it.

Fakes (`tests/fakes/`): `FakeLLM` (plays a JSONL script of `LLMEvent`s with configurable inter-token delay), `FakeSTT`, `FakeTTS` (writes a sine burst into the ring, records chunks), `FakeSandbox`, `FakeClock`, `FakeRandom`, `FakeUI`. Contract tests run the same module against fake and real.

## 2. Property-based tests (Hypothesis; `deadline=None`, `max_examples` as given)

| ID | Target | Property | N |
|---|---|---|---|
| P-01 | Scheme lexer/parser | any `str` → returns AST or raises `SchemeSyntaxError` only | 5 000 |
| P-02 | Scheme evaluator | any parseable AST over random `RuleState` → value or `SchemeError` subclass only; wall time < 50 ms | 2 000 |
| P-03 | `validate_rel_path` | any `str` → result under `/workspace` or `SandboxPathError`; never other exception | 5 000 |
| P-04 | Chunker | any list of Unicode deltas → never raises; concatenation invariant; no chunk > `force_split_at`; no split inside `\d\.\d` | 2 000 |
| P-05 | Canonical JSON | key-order independence; any field change ⇒ different `entry_id` | 1 000 |
| P-06 | FTS query builder | any `str` → valid FTS5 MATCH expression (executes without error on empty table) | 2 000 |
| P-07 | Ring buffer | random interleaved writes/reads never lose or duplicate samples (model-based `RuleBasedStateMachine`) | 500 steps × 50 |
| P-08 | Envelope codec | encode/decode round-trip for random payloads; oversized frame rejected | 1 000 |

## 3. Matrix by subsystem (IDs → owning spec)

### Boot / IPC / lifecycle (spec 01)
| ID | Test | Pass |
|---|---|---|
| T-BOOT-01 | Full boot with fakes for hw pieces: all `boot.step` ok; ≤ 25 s warm on laptop (`hw`) | — |
| T-BOOT-02 | Second instance → exit code 4 "already running" | — |
| T-BOOT-03 | llama-server configured on `0.0.0.0` → boot refuses | — |
| T-BOOT-04 | Missing model file → `models verify` fails, spoken/UI message, exit 5 | — |
| T-IPC-01 | Envelope schema: unknown type NACKed, oversized frame dropped, malformed JSON logged | — |
| T-IPC-02 | Heartbeat: kill `lucca-ui` → detected ≤ 6 s → restarted; voice loop continues (tier2 with real subprocesses) | — |
| T-IPC-03 | Ordered shutdown flushes 50 queued memory writes; 0 lost | — |
| T-IPC-04 | Kill `lucca-npu` mid-TTS → `play.abort`, restart, next turn ok | tier2 |
| T-IPC-05 | UI crash isolation | tier2 |
| T-IPC-06 | Message without session token → dropped + logged | — |
| T-IPC-07 | 5 crashes in 10 min → DEGRADED, spoken notice once, no restart storm | — |

### Audio / ASR / TTS / barge-in (spec 07)
| ID | Test |
|---|---|
| T-AUD-01 | Callback duration p99 < 2 ms over 10 000 callbacks (`hw`) |
| T-AUD-02 | Two streams at 16 k/24 k open simultaneously; no resampler in call graph (AST: no `resample` import) |
| T-AUD-03 | PTT held 35 s → auto-release at 29.5 s; ring never overflows |
| T-AUD-04 | Debounce and empty-press (<250 ms speech) behaviour |
| T-AUD-05 | Pre-roll: clip starting 100 ms before key-down is fully captured (inject test tone) |
| T-AUD-06 | Jitter buffer adapts after 3 underruns; decays after clean turns |
| T-AUD-07 | Device hot-unplug/replug → stream reopened ≤ 2 s, event logged (`hw`, manual) |
| T-ASR-01..04 | WER ≤ 8 % (NPU/GPU) / ≤ 10 % (CPU) on frozen 40-clip set; latency; silent clip; 29.5 s clip |
| T-ASR-05 | Device ladder: force NPU compile failure (env flag) → GPU/CPU selected; `asr_device` reported |
| T-TTS-01..03 | First-chunk ≤ 180 ms; RTF ≤ 0.35; 200-chunk RSS growth ≤ 30 MB |
| T-TTS-04 | Ladder: NPU bucket compile → measured; forced failure → GPU → CPU; `EXECUTION_DEVICES` asserted equals reported device |
| T-TTS-05 | Chunk from an aborted `trace_id` never reaches the ring |
| T-BRG-01..04 | Silence ≤ 30 ms; no stale frames; slot idle ≤ 100 ms; next-turn latency unaffected |
| T-BRG-05 | Barge-in during CONFIRM_WAIT cancels the pending action (nothing executed) |

### LLM client & chunker (specs 02, 08, ADR-001)
| ID | Test |
|---|---|
| T-LLM-01 | SSE parsing: token deltas, structured tool calls, `Done` usage; malformed line → `LLMProtocolError` |
| T-LLM-02 | Prompt builder section order = spec 10 §4; token counts within budgets on 50 fixture contexts |
| T-LLM-03 | `abort()` idempotent; second call no error |
| T-LLM-04 | Mode switch audio↔transcript by config only; both produce a valid request body |
| T-LLM-05..09 | `hw` Phase 0 spike S1–S10 (ADR-001) as tests writing `phase0_llm.json` |
| T-CHK-01..14 | per spec 08 |

### Memory / provenance (specs 03, 04)
| T-PROV-01..12 | per spec 03 |
| T-MEM-01..11 | per spec 04 |
| T-MEM-12 | Retrieval never returns `forgotten_at IS NOT NULL` or superseded rows unless asked |
| T-MEM-13 | Backup created at idle; restore round-trip; integrity failure → read-only mode |
| T-MEM-14 | Working memory: 8-step task keeps typed state; on close nothing persisted **and** a positive control (a `USER_EXPLICIT` commit in the same task) *is* persisted — proves the discard test is not vacuous |

### Rules / reflection (spec 05)
| T-LISP-01..09, T-RULE-01..08, T-REFL-01..02 | per spec 05 |
| T-RULE-09 | 50 active rules evaluate in ≤ 5 ms total |
| T-RULE-10 | Regression suite with a `RuleState` schema bump marks cases stale and blocks promotion until re-captured |

### Router (spec 06)
| T-RTR-01..10 | per spec 06 |
| T-RTR-11 | Data-volume gate evaluator on synthetic 300-decision DB → "blocked"; on 650 with ≥30/class → "eligible" |

### Sandbox / launcher (spec 09)
| T-SBX-01..16, 19 | per spec 09 (T-SBX-16: host recomputes sha256 of `read_file` content; mismatch ⇒ `ok=False`, audit; T-SBX-19: forbidden `read_file→fetch_url` sequence and over-long URL refused) |
| T-SBX-17 | Container spec snapshot test: rendered `docker run` args equal the spec text (catches accidental `--gpus`, missing `--cap-drop`) |
| T-SBX-18 | WSL restart → egress rules re-applied by boot command (`hw`, manual once) |

### UI (ADR-005)
| T-UI-01 | Click-through outside sprite; clickable on sprite (automated via `pyautogui` on laptop) |
| T-UI-02 | RMS → mouth state mapping with hysteresis (unit) |
| T-UI-03 | Confirm prompt shows templated text, buttons work, timeout 15 s |

### Observability / config (spec 11)
| T-OBS-01 | Every turn produces exactly one trace line with all points present (fakes) |
| T-OBS-02 | Log scan: no transcript text at INFO; no key material anywhere |
| T-OBS-03 | Config precedence: CLI > env > toml > .env > default (parametrised) |
| T-OBS-04 | Event names all in enum (AST) |
| T-OBS-05 | `lucca-admin env-check` exit codes per failure class |

### Soak (T4)
| T-SOAK-01 | 200 turns (fixture wavs, 3 s gap): VRAM slope ≤ 20 MB/turn; per-process RSS growth ≤ 100 MB; 0 crashes; latency drift of median ≤ 10 % first vs last 50 |
| T-SOAK-02 | 30 min continuous TTS+LLM: tok/s and RTF drop ≤ 20 % (thermal); report GPU/CPU temps via `nvidia-smi`/WMI |
| T-SOAK-03 | WSL2 memory ≤ 3 000 MB peak during 100 sandbox calls incl. 10 `render=true` |
| T-SOAK-04 | 24 h idle: RAM stable ±50 MB, no log growth > 5 MB, reflection ran ≤ 1/10 min |

## 4. Phase sign-off bundles

| Phase | Required green | Report artefacts |
|---|---|---|
| 0 | T-LLM-05..09, T-ASR-01/02/05, T-TTS-01/04, T-BOOT-01 | `phase0_llm.json`, `phase0_npu.json` |
| 1 | T0–T2 all; T-AUD-*, T-ASR-*, T-TTS-*, T-BRG-*, T-CHK-*, latency e2e (spec 10 §5) both modes; T-SOAK-01 | `latency_report_*.md` ×2, soak report |
| 2 | T-SBX-*, T-SOAK-03, container snapshot, egress table | `sandbox_verify_*.md` |
| 3 | T-PROV-*, T-MEM-*, benchmarks with numbers | `retrieval_bench_*.md` |
| 4 | T-RTR-01..05, T-OBS-01; ≥ 100 decisions captured (human gate) | `decisions.jsonl` stats |
| 5 | T-LISP-*, T-RULE-*, T-REFL-*; ≥ 1 rule promoted from real/replayed usage (human gate) | `rules list` output, regression report |
| 6 | T-RTR-06..11; data floor met; classifier report with CIs | `report-<sha>.md` |

## 5. Retired from doc 04 (do not implement)

- `assert 300.0 <= median_latency` (inverted).
- `assert max_vram <= 9800` measured against vLLM preallocation.
- `curl` egress test without positive control.
- `register_quarantine_rule(candidate_rule)` and `is_active_rule` signatures.
- `PermissionError` expectations for path tests; Windows reserved-name tests as Linux-container behaviour.
- Hallucination test that only checks an enum raises.
- ECE ≤ 0.045 @ 10 bins, "+2 % accuracy", avg set size ≤ 1.15.
