# Findings — TEST (`tests/**`, `pyproject.toml`, `packaging/**`, `Lucca.spec`, `launch_lucca.bat`, `.env.example`, non-WSL `scripts/**`)

**Subtask:** S2i · **Method:** static line-by-line + S1 dynamic evidence (tier runs, coverage, static gates) · **Baseline:** HEAD `ed14f6b` + working tree per `03_BASELINE.md`, delta in [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) (`scripts/test_s1_startup.py` changed post-S0 — see F-TEST-009) · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; every finding cites `file:line` or an artefact under `docs/audit/evidence/`. Cross-area findings cross-referenced by ID.

**Severity totals: S0 = 0 · S1 = 2 · S2 = 6 · S3 = 7 · S4 = 0 · total = 15.**

---

## 1. Module map

| File | LOC | Responsibilities (as-built) | Live in product path? | Cov / result |
|---|---:|---|---|---|
| `pyproject.toml` | 98 | Deps, scripts, ruff/mypy/pytest config | yes (build + tooling) | S1_11a–d, S1_12–14 |
| `tests/conftest.py` | 17 | One `sample_state` fixture; **no `LUCCA_HOME` isolation** | test infra | — |
| `tests/*` (22 modules, 4,188 lines) | — | T1 unit + T3 hw; fakes: `fake_llm`, `fake_asr`, `fake_tts` | test infra | 131 passed / 2 failed (T3) / 61 % total cov (S1_12/14/30) |
| `packaging/build_exe.py` | 83 | PyInstaller onedir build; icon generation from sprite | build-time | never run in audit |
| `Lucca.spec` | 42 | Generated PyInstaller spec (`console=False`, absolute paths) | build-time | untracked artefact |
| `launch_lucca.bat` | 5 | `cd /d C:\projects\ProjectLucca && uv run lucca` | **yes** (user entry) | S1_24 |
| `.env.example` | 15 | Documents **retired architecture** (vLLM, caps_lock, HMAC secret) | docs | F-CORE-050 |
| `scripts/*` (non-WSL, 14 files) | ~1,030 | Benchmarks, spikes, env verify, startup probe | ops | S1_33–36 |

**Test-tier reality (S1_12/13/30):** T1 131 passed / 0 failed; T2 `-m tier2` **deselects everything** (marker unregistered, exit 5); T3 2 failed / 3 passed; coverage 61 % with ten modules at 0 %.

---

## 2. Findings

Ordered by severity, then by ID. Every finding re-reviewed per Charter §3.5 (log in §7); `Status: OPEN`.

### F-TEST-001 — The `tier2` marker is unregistered: the entire T2 integration tier silently selects nothing

| Field | Value |
|---|---|
| **ID** | F-TEST-001 |
| **Title** | The `tier2` marker is unregistered: the entire T2 integration tier silently selects nothing |
| **Severity** | S1 — High |
| **Category** | TESTING |
| **Location** | `pyproject.toml:101-104`; `docs/audit/evidence/S1_13_T2_tier2.txt` |
| **Status** | OPEN |

**Evidence**

`pyproject.toml:101-104`
```toml
markers = [
    "hw: Hardware-dependent tests (NPU/dGPU/Audio)",
    "soak: Long-running stability and soak tests",
]
```
Artefact: `S1_13_T2_tier2.txt` (row 24) — `uv run pytest -m tier2 -q` → **exit 5, "136 deselected in 1.29s"**, no tests collected, no warning text visible in `-q` output.

**What is wrong / assumed / missing**

The project's own testing convention (SKILL.md §2, core.md usage) defines four tiers — T0 static, T1 unit, **T2 fake-backed integration**, T3 hardware — but only `hw` and `soak` markers are registered. `-m tier2` deselects all 136 tests and exits 5; nothing in the repo references a registered way to run the integration tier, and no T2 test exists anywhere. The tier that is supposed to exercise the orchestrator loop with fakes (the F-CORE-035 gap) does not exist as an executable tier.

**Why it matters**

Every area audit found integration seams that only a T2 tier could cover (orchestrator wiring, memory commit path, sandbox service end-to-end); the tier is named in the convention, unregistered in config, and empty in fact — and the failure mode of running it is a quiet exit 5 that looks like "no tests matched" rather than "the tier is missing".

**Questions this raises**

1. None.

**Proposed remediation**

1. In `pyproject.toml:101-104`: register `"tier2: Fake-backed integration tests (no hardware)"` (and optionally `tier1`/`tier0`) and add `tier2` to the default deselect set (`addopts = "-m 'not hw and not soak and not tier2'"`) so T1 runs stay hermetic.
2. Seed the tier with the cross-area T2 tests already specified in other findings (F-REAS-003, F-UI-002, F-SBX-002, F-BRAIN-013).
3. Add `tests/test_static_gates.py::test_tier2_marker_registered` (T0): `pytest --markers` contains `tier2`; a `-m tier2` collection returns ≥ 0 tests without exit 5 once seeded.

**Verification test**

- **Tier:** T0
- **Input:** `uv run pytest --markers | findstr tier2`
- **Expected output:** marker registered
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest --markers && uv run pytest -m tier2 --collect-only -q`

**Cross-references:** F-CORE-035, F-CORE-036, F-REAS-003, F-SBX-002

---

### F-TEST-002 — `import-linter` is a dev dependency with no configuration: the declared architecture boundaries are unenforced

| Field | Value |
|---|---|
| **ID** | F-TEST-002 |
| **Title** | `import-linter` is a dev dependency with no configuration: the declared architecture boundaries are unenforced |
| **Severity** | S1 — High |
| **Category** | TESTING |
| **Location** | `pyproject.toml:40`; `docs/audit/evidence/S1_11d_lint_imports.txt`; `docs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/12_threat_model.md:21` (TM-01 cites "import-linter") |
| **Status** | OPEN |

**Evidence**

Artefact: `S1_11d_lint_imports.txt` (row 20) — `uv run lint-imports` → **exit 1, "Could not read any configuration"**; no `importlinter` key in `pyproject.toml`, no `.importlinter`/`setup.cfg` in the repo (S1_SUMMARY §2.6).

**What is wrong / assumed / missing**

The provenance threat model (TM-01) lists import-linter as a *control* preventing memory-provenance bypasses; the tool is a dependency and the SKILL.md T0 gate expects it, but there is no contract file — so the "core must not import adapters", "memory must not import brain", "ui must not import core.orchestrator" boundaries are aspiration. The S1 T0 gate ran without it and reported green overall.

**Why it matters**

Charter §5.1's type-level defence (TM-01: "import-linter; AST allow-list") is half-implemented; the F-CORE-034 finding (core imports concrete adapters, ports unused) is the visible symptom of a boundary system that was never configured.

**Questions this raises**

1. None.

**Proposed remediation**

1. Add `.importlinter` with contracts: `layers` (core → brain/senses/memory/reasoning/router/sandbox/ui → nothing), `forbidden` (ui → core.orchestrator, anything → lucca.senses except via ports, core → lucca.senses/sandbox concrete classes), matching F-CORE-034's remediation.
2. Wire `lint-imports` into a `lint` script (pyproject `[tool.hatch]` or a `uv run lint` composite) so the SKILL.md T0 gate is runnable — closing the S1_11 "program not found" gap (F-CORE-036 sibling).
3. Add the contracts to CI order: ruff → mypy → lint-imports → pytest.
4. Verification: `uv run lint-imports` exit 0 with the current tree (contracts must be written against as-built imports first, then tightened).

**Verification test**

- **Tier:** T0
- **Input:** `uv run lint-imports`
- **Expected output:** exit 0; contracts documented in the file
- **Threshold:** n/a — boolean
- **Command:** `uv run lint-imports`

**Cross-references:** F-CORE-034, F-CORE-036, TM-01

---

### F-TEST-003 — `pyproject.toml` disables every static gate that would have caught the audit's S0 findings

| Field | Value |
|---|---|
| **ID** | F-TEST-003 |
| **Title** | `pyproject.toml` disables every static gate that would have caught the audit's S0 findings |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `pyproject.toml:62,64-71,73-77`; `docs/audit/findings/core.md` F-CORE-001/054; `docs/audit/findings/brain.md` F-BRAIN-001 |
| **Status** | OPEN |

**Evidence**

`pyproject.toml:62`
```toml
ignore = ["PLR0913", "PLR2004", "S105", "PLR0911", "PLR0912", "PLR0915", "PLR0917", "S311", "S324", "ANN401"]
```
(`ANN401` ignored → `Any` in public interfaces passes ruff; `[tool.mypy]` at `:73-77` does **not** set `strict = true` — `disallow_any_explicit`/`disallow_any_expr` absent, `warn_return_any` alone can't catch `-> Any` definitions; per-file ignores at `:64-71` blanket-disable `S`/`ANN`/`BLE` for entire `ui/`, `sandbox/`, `senses/`, `scripts/` trees — the four areas with the most audit findings.)

**What is wrong / assumed / missing**

The S0 `Any` findings (F-CORE-001, F-BRAIN-001, F-REAS-001) and dozens of swallowed-exception findings (BLE001 ignored per-tree) would have been caught by the gates the tooling already supports; the ignores are broad, undocumented, and map suspiciously well onto "the code as written" rather than considered policy.

**Why it matters**

The static gate is the cheapest defence and it is configured to look away from exactly the defect classes the audit found; tightening it is the highest-leverage remediation in the programme.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `pyproject.toml`: remove `ANN401` from the global ignore (allow per-file ignores where genuinely needed); add `disallow_any_explicit = true` to `[tool.mypy]`; shrink the per-file ignores to named exceptions with comments.
2. Land the gate tightening together with the F-CORE-001/F-BRAIN-001/F-REAS-001 retypings (otherwise T0 goes red immediately — the intent).
3. Verification: `uv run ruff check src --select ANN401` → 0; `uv run mypy --strict src` → 0 (after the retyping remediations).

**Verification test**

- **Tier:** T0
- **Input:** the commands above
- **Expected output:** clean with strict gates
- **Threshold:** n/a — boolean
- **Command:** `uv run ruff check src --select ANN401 && uv run mypy --strict src`

**Cross-references:** F-CORE-001, F-CORE-054, F-BRAIN-001, F-REAS-001

---

### F-TEST-004 — The PyInstaller build packages a GUI-only exe whose windowed mode breaks the console-dependent code paths

| Field | Value |
|---|---|
| **ID** | F-TEST-004 |
| **Title** | The PyInstaller build packages a GUI-only exe whose windowed mode breaks the console-dependent code paths |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `Lucca.spec:29`; `packaging/build_exe.py:52-79`; `src/lucca/main.py` (print-based boot banner); `src/lucca/core/orchestrator.py` (print/caption paths) |
| **Status** | OPEN |

**Evidence**

`Lucca.spec:29`
```python
    console=False,
```
(`build_exe.py:58` also passes `--windowed`. The product's boot path prints the banner/progress to stdout (`main.py:102-105,114-148`), the PTT/audio process prints per-press lines, and F-CORE-004 documents the `UnicodeEncodeError` from emoji `print()` when stdout is a redirected/absent stream — under `--windowed`, `sys.stdout` is **None** in PyInstaller, so every bare `print(...)` on the boot path raises `AttributeError`.)

**What is wrong / assumed / missing**

The packaged exe (the distribution target, per the build script and spec) cannot execute the code paths the source ships: `print` with `sys.stdout is None` raises, the emoji prints (F-CORE-004) compound it, and `launch_lucca.bat` runs `uv run lucca` instead of the exe — so the two distribution mechanisms disagree and neither is exercised by any test (0 % on `main.py`, build never run in the audit).

**Why it matters**

The packaging story is untested end-to-end: no test builds the exe, none runs it, and static evidence says the boot path would crash before the first audio frame.

**Questions this raises**

1. Is the PyInstaller exe the intended distribution (vs `launch_lucca.bat` + uv)? (→ §5 Q-T-01.)

**Proposed remediation**

1. In `src/lucca/main.py` (CORE-area): replace bare `print(...)` with a `safe_print()` helper that no-ops when `sys.stdout is None`; same for the emoji prints (F-CORE-004's remediation covers the mechanism).
2. In `packaging/build_exe.py`: add `--collect-all structlog` and a post-build smoke check that launches the exe with a `--selfcheck` flag (new CORE-area arg) which runs env-check and exits.
3. Add `tests/test_packaging.py::test_spec_targets_main_and_migrations` (T0): assert `Lucca.spec`/`build_exe.py` reference `main.py` and bundle `memory/migrations` (the runtime migration loader needs them, `db.py:20`).
4. Add a T3 build-and-launch smoke (marked `hw`, optional): build → start exe → assert the tray appears → terminate.

**Verification test**

- **Tier:** T0 + T3
- **Input:** the tests above
- **Expected output:** spec contents pinned; exe boots
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_packaging.py -q`

**Cross-references:** F-CORE-004, F-CORE-036, F-CORE-051

---

### F-TEST-005 — `launch_lucca.bat` and `Lucca.spec` hard-code the repo path and the two launch mechanisms disagree

| Field | Value |
|---|---|
| **ID** | F-TEST-005 |
| **Title** | `launch_lucca.bat` and `Lucca.spec` hard-code the repo path and the two launch mechanisms disagree |
| **Severity** | S2 — Medium |
| **Category** | MAINTAINABILITY |
| **Location** | `launch_lucca.bat:3`; `Lucca.spec:5-8,35`; `docs/audit/evidence/S1_SUMMARY.md` observation 28 |
| **Status** | OPEN |

**Evidence**

`launch_lucca.bat:3`
```bat
cd /d C:\projects\ProjectLucca
```
(`Lucca.spec:5-8,35` embed `C:/Projects/ProjectLucca` absolute paths generated at build time; the bat launches via `uv run lucca` from the repo, the spec builds a standalone exe — two distributions with different behaviours: bat → console uv process, exe → windowed build with the F-TEST-004 problems. The bat also runs `uv run lucca` without `--frozen`, silently honouring a drifted `uv.lock`.)

**What is wrong / assumed / missing**

The user-facing launcher depends on the repo existing at one exact path and on the uv environment being current; the packaged alternative is untested (F-TEST-004). Neither mechanism pins a version or verifies the environment before launch.

**Why it matters**

The first-run experience on any machine other than the dev box is undefined; and the observed launch path (`S1_24`) is the bat — so the audited runtime depends on an unpinned environment.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `launch_lucca.bat`: derive the script directory (`cd /d "%~dp0"`) instead of the hard-coded path; add `uv sync --frozen` before `uv run lucca`.
2. In `packaging/build_exe.py`: generate `Lucca.spec` from relative paths (it is a generated artefact — regenerate, don't hand-maintain) and add it to `.gitignore`.
3. Verification: run the bat from a copied repo at a different path (T3, manual or CI) — app boots.

**Verification test**

- **Tier:** T3
- **Input:** repo copied to a different path; run `launch_lucca.bat`
- **Expected output:** app boots
- **Threshold:** n/a — boolean
- **Command:** manual smoke (or CI job)

**Cross-references:** F-CORE-030, F-TEST-004

---

### F-TEST-006 — `.env.example` documents the retired architecture (vLLM, caps_lock, HMAC secret) and none of the current keys

| Field | Value |
|---|---|
| **ID** | F-TEST-006 |
| **Title** | `.env.example` documents the retired architecture (vLLM, caps_lock, HMAC secret) and none of the current keys |
| **Severity** | S3 — Low |
| **Category** | DOCS |
| **Location** | `.env.example:1-20`; `docs/audit/findings/core.md` F-CORE-050 |
| **Status** | OPEN |

**Evidence**

`.env.example:3-5`
```
# vLLM Server (WSL2)
LUCCA_VLLM_URL=http://localhost:8000/v1
LUCCA_VLLM_MODEL=fixie-ai/ultravox-v0_5-llama-3_1-8b
```
(also `LUCCA_PTT_KEY=caps_lock` vs shipped `alt-gr`; `LUCCA_HMAC_SECRET_KEY` vs the actual `LUCCA_MASTER_KEY` alias; the real config's env contract is `LUCCA_ENV__MODE`, `LUCCA_LLM__*`, `LUCCA_ASR__*`, `LUCCA_TTS__*`, `LUCCA_PTT__*`, `LUCCA_MASTER_KEY` — none present.)

**What is wrong / assumed / missing**

Cross-references F-CORE-050 (core-side); the TEST-area obligation is that the example environment file is the first thing a new operator copies — and every key in it is dead, while every live key is absent. `pydantic-settings` reads `LUCCA_*` with `env_nested_delimiter="__"` (`config.py:135-137`); the example teaches the wrong contract.

**Why it matters**

Operator-facing configuration documentation that is 100 % stale; copying it configures nothing.

**Questions this raises**

1. None.

**Proposed remediation**

1. Rewrite `.env.example` from `LuccaConfig`'s fields (`core/config.py`): `LUCCA_ENV__MODE`, `LUCCA_MASTER_KEY`, `LUCCA_LLM__MODE/MODEL/MMPROJ/CTX/KV_TYPE/TEMPERATURE/MAX_TOKENS`, `LUCCA_ASR__MODEL/DEVICE_LADDER/LOWCONF_LOGPROB`, `LUCCA_TTS__VOICE/SPEED`, `LUCCA_PTT__KEY/MODE/MAX_SECONDS`, `LUCCA_UI__ENABLED` — each with the shipped default commented.
2. Add `tests/test_env_example.py::test_env_example_matches_config` (T0): parse `.env.example` keys; assert each maps to a real settings field (no dead keys, no undocumented required keys).

**Verification test**

- **Tier:** T0
- **Input:** the test above
- **Expected output:** zero dead keys
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_env_example.py -q`

**Cross-references:** F-CORE-050, F-CORE-020

---

### F-TEST-007 — `conftest.py` provides no `LUCCA_HOME` isolation: tests share and mutate the production tree

| Field | Value |
|---|---|
| **ID** | F-TEST-007 |
| **Title** | `conftest.py` provides no `LUCCA_HOME` isolation: tests share and mutate the production tree |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `tests/conftest.py:1-22`; `tests/test_turn_loop.py` (traces via real `LUCCA_HOME`); `docs/audit/findings/core.md` A-23 |
| **Status** | OPEN |

**Evidence**

`tests/conftest.py` (verbatim, 22 lines) defines a single `sample_state` fixture — no autouse fixture sets `LUCCA_HOME` to a tmp dir, no tmp-path DB redirect, no traces.jsonl redirect. `core.md` §1 documents that `test_turn_loop.py` writes real `traces.jsonl` under `LUCCA_HOME`, and `test_affect.py::test_affect_tracker_lifecycle` passes whether or not the prod persona file exists (A-20 in core.md).

**What is wrong / assumed / missing**

Any test touching config-defaulted paths (traces, memory DB via `MemoryManager()` defaults, persona import-load F-BRAIN-031) reads/writes the **production** `C:\ProjectLucca` tree. The audit's own T1 run appended to the production `traces.jsonl`. Expected: an autouse fixture setting `LUCCA_HOME` to a per-test tmp dir (env-var based, since `config.py:157-166` re-reads it).

**Why it matters**

Test runs mutate the production data directory (traces at minimum); test results depend on host state; and CI on a clean machine exercises different code paths than the dev box.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `tests/conftest.py`: add
```python
@pytest.fixture(autouse=True)
def _isolated_lucca_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    home = tmp_path / "lucca_home"
    monkeypatch.setenv("LUCCA_HOME", str(home))
    yield home
```
   and fix the per-test fallout (paths that hard-code `C:\ProjectLucca` — F-CORE-030/F-MEM-013/F-SBX-012/F-SENS-008 — get red first, which is the point).
2. Add `tests/test_conftest.py::test_tests_run_in_tmp_home`: assert `get_config().home_dir` is under tmp during any test.

**Verification test**

- **Tier:** T0
- **Input:** full T1 run
- **Expected output:** production `traces.jsonl` unmodified; all tests green in tmp home
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest -m "not hw and not soak" -q` (with a before/after hash of `C:\ProjectLucca\logs\traces.jsonl`)

**Cross-references:** F-BRAIN-031, F-CORE-030, F-CORE-023 (A-20)

---

### F-TEST-008 — No T0 gate runs in CI or pre-commit: `uv run lint` does not exist and the composite gate is undefined

| Field | Value |
|---|---|
| **ID** | F-TEST-008 |
| **Title** | No T0 gate is runnable as documented: `uv run lint` does not exist and no CI/pre-commit wiring exists |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `pyproject.toml:45-47` (scripts section has only lucca/lucca-admin); `docs/audit/evidence/S1_11_T0_lint.txt`; `.agents/skills/lucca-pipeline/SKILL.md` §2 |
| **Status** | OPEN |

**Evidence**

Artefact: `S1_11_T0_lint.txt` (row 19) — `uv run lint` → **exit 2, "Failed to spawn: lint — program not found"**. `pyproject.toml:45-47` defines only `lucca-admin` and `lucca` scripts. No `.github/workflows/`, no pre-commit config, no CI of any kind exists in the repo.

**What is wrong / assumed / missing**

The project's own operational skill documents `uv run lint` (ruff + mypy + import-linter + AST tests) as the T0 gate; the command does not exist, and nothing else (CI, pre-commit, Makefile) runs the gates automatically. Every gate result in this audit was produced by manual invocation.

**Why it matters**

Gates that require remembering to run them manually do not run; the audit found 3 S0s and dozens of S1/S2s that a mandatory T0 would have flagged at commit time.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `pyproject.toml`: add `[tool.hatch.envs.default.scripts]` or a `[project.scripts]` entry `lint = "lucca.tools.lint:main"` (new ~30-line module chaining ruff → mypy → lint-imports → pytest `-q --collect-only`) returning non-zero on any failure.
2. Add a minimal GitHub Actions workflow (or document the local-only policy in AGENTS.md if CI is deliberately absent — decision recorded: add the script at minimum).
3. Verification: `uv run lint` exits 0 on the current tree (post F-TEST-002/003 remediations) and non-zero on a seeded violation.

**Verification test**

- **Tier:** T0
- **Input:** `uv run lint` on a seeded violation (a temp `x: Any` in a public signature)
- **Expected output:** non-zero exit naming the file
- **Threshold:** n/a — boolean
- **Command:** `uv run lint`

**Cross-references:** F-CORE-036, F-TEST-002, F-TEST-003

---

### F-TEST-009 — `scripts/test_s1_startup.py` changed after the S0 baseline without a commit, record, or test

| Field | Value |
|---|---|
| **ID** | F-TEST-009 |
| **Title** | `scripts/test_s1_startup.py` changed after the S0 baseline without a commit, record, or test |
| **Severity** | S3 — Low |
| **Category** | TESTING |
| **Location** | `scripts/test_s1_startup.py`; `docs/audit/03b_BASELINE_DELTA.md` §3; `docs/audit/findings/brain.md` F-BRAIN-008 |
| **Status** | OPEN |

**Evidence**

`03b_BASELINE_DELTA.md` §3 (evidence `S2b_01/02`): the file is 51 → 49 non-blank lines vs S0 and newly appears as `M` in `git status` — one of only three changed files in the tree, with no commit and no note identifying the author or intent (the S2b re-inventory answered *what* changed; *who/why* remains open, brain F-BRAIN-008 Q1).

**What is wrong / assumed / missing**

The TEST-area dimension of the mid-audit mutation: an ops script modified in the freeze window. The current content still carries F-BRAIN-028's defects (false-pass against a pre-existing server, hard-coded command), so whatever the edit intended, the documented defects persist.

**Why it matters**

Uncommitted, unattributed changes to the frozen tree during an audit; recorded here so the TEST-area corpus is complete and the F-BRAIN-008 remediation (freeze-window rule) has a TEST-side instance.

**Questions this raises**

1. None beyond brain F-BRAIN-008 Q1 (who/why).

**Proposed remediation**

1. Covered by F-BRAIN-008's remediation (freeze-window rule + `03b` delta record); no separate action.
2. When F-BRAIN-028's rewrite lands, the script becomes single-source (`build_launch_command`), eliminating the drift class.

**Verification test**

- **Tier:** T0
- **Input:** `git status --porcelain scripts/test_s1_startup.py`
- **Expected output:** committed (clean) after the F-BRAIN-028 rewrite
- **Threshold:** n/a — boolean
- **Command:** `git status --porcelain scripts/test_s1_startup.py`

**Cross-references:** F-BRAIN-008, F-BRAIN-028

---

### F-TEST-010 — The hw test tier writes no machine-readable reports, breaking the sign-off bundle contract

| Field | Value |
|---|---|
| **ID** | F-TEST-010 |
| **Title** | The hw test tier writes no machine-readable reports, breaking the sign-off bundle contract |
| **Severity** | S2 — Medium |
| **Category** | TESTING |
| **Location** | `tests/test_phase1_live_hw.py`; `tests/test_phase2_live_hw.py`; `docs/archive/2026-09-17_pre_phase4_audit/10_testing_matrix_v2.md` §1/§4; `docs/audit/evidence/S1_31_reports_harvest.txt` |
| **Status** | OPEN |

**Evidence**

Artefact: `S1_31_reports_harvest.txt` (row 57) — `logs\test_reports\` **does not exist** in the repo or under `C:\ProjectLucca\logs`; the archived testing matrix §1 requires "Every `hw` test writes a machine-readable report" and §4 expects them in the Phase 1–4 sign-off bundles. The `hw` tests (`test_phase1_live_hw.py`, `test_phase2_live_hw.py`) contain no report-writing code (assertions only).

**What is wrong / assumed / missing**

The T3 tier produces pytest console output only — no per-test JSON with measured latencies, devices, and thresholds. Phase sign-off therefore has no machine-checkable artefacts for its hardware gates, and the S1 harvest had nothing to collect. `pyproject.toml` also registers no `pytest-timeout`/report plugins for it despite `pytest-timeout` being a dev dependency.

**Why it matters**

Charter §5.3's phased discipline requires green sign-off bundles; hardware gates without machine-readable reports cannot be verified after the fact — exactly the gap that let the spike suite's fabrications (F-BRAIN-007) go unnoticed.

**Questions this raises**

1. None.

**Proposed remediation**

1. Add a `tests/hw_report.py` helper: `write_hw_report(test_id: str, measured: dict, thresholds: dict, passed: bool) -> None` writing `logs\test_reports\<test_id>-<UTC>.json` with schema `{test_id, utc, measured, thresholds, passed, host}`.
2. Call it from every test in `test_phase1_live_hw.py`/`test_phase2_live_hw.py` (each already has its measured values in-scope).
3. Add `tests/test_hw_report.py::test_hw_report_written_and_schema_valid` (T1, tmp dir).
4. Register `logs/test_reports/` in the sign-off bundle checklist (future docs).

**Verification test**

- **Tier:** T1 + T3
- **Input:** any `hw` test run
- **Expected output:** one JSON per test under `logs\test_reports\`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest -m hw -q && dir logs\test_reports`

**Cross-references:** F-BRAIN-007, F-CORE-056, Charter §5.3

---

### F-TEST-011 — The fakes bypass the real SENS workers, so the voice pipeline has no test below the hardware tier

| Field | Value |
|---|---|
| **ID** | F-TEST-011 |
| **Title** | The fakes bypass the real SENS workers, so the voice pipeline has no test below the hardware tier |
| **Severity** | S3 — Low |
| **Category** | TESTING |
| **Location** | `tests/fakes/fake_llm.py`; `tests/fakes/fake_asr.py:1-20`; `tests/fakes/fake_tts.py`; `docs/audit/findings/sens.md` (tts 32 %, audio_proc/npu_proc/ptt/vad 0 %) |
| **Status** | OPEN |

**Evidence**

`tests/fakes/fake_asr.py` returns a fixed `"test input"` transcript regardless of audio; `fake_tts.py` writes a 200 ms sine into the play ring; `fake_llm.py` replays a script. The real `ASRWorker`/`TTSWorker` are constructed only in the 0 %-covered process entry points — turn-loop tests never touch them.

**What is wrong / assumed / missing**

The fakes are reasonable for orchestration tests, but there is no seam test that constructs the real workers with tiny local models (whisper-tiny, a 1-sentence Kokoro clip) — so `F-SENS-001` (wrong model), `F-SENS-004` (voice fallback), and the TTS path's blocking behaviour (F-CORE-017) were invisible until a hardware run. Expected: an optional-models T1 tier (skipped when models absent) that exercises the real workers.

**Why it matters**

The largest coverage holes in the audit (SENS 0 % files) are exactly where the fakes substitute; the T1 tier's 61 % is computed *with* those holes.

**Questions this raises**

1. None.

**Proposed remediation**

1. Add `tests/test_senses_real.py` (marker `realmodels`, skip when `models/` absent): real `ASRWorker.transcribe` on `tests/fixtures/audio_tool_calls/calc_01.wav` returns text containing "calculator"; real `TTSWorker.synthesize` returns `samples > 0`.
2. Register the `realmodels` marker in `pyproject.toml` alongside the tier fix (F-TEST-001).

**Verification test**

- **Tier:** T1 (model-gated)
- **Input:** the fixtures above
- **Expected output:** real workers pass on real audio
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest -m realmodels tests/test_senses_real.py -q`

**Cross-references:** F-SENS-001, F-SENS-004, F-CORE-035

---

### F-TEST-012 — `.env.example` keys and `pyproject` dependency pins disagree with the shipped architecture (numpy `<2.3` cap, unused `openvino-genai`/`networkx`/`torch`-era deps)

| Field | Value |
|---|---|
| **ID** | F-TEST-012 |
| **Title** | Dependency list contains unused packages and unexplained pins; the example env teaches none of it |
| **Severity** | S3 — Low |
| **Category** | MAINTAINABILITY |
| **Location** | `pyproject.toml:7-29`; `.env.example` |
| **Status** | OPEN |

**Evidence**

`pyproject.toml:16-18,28`
```toml
    "openvino-genai>=2025.0.0",
    "openvino-tokenizers>=2025.0.0",
    ...
    "networkx>=3.3.0",
```
(a repo-wide search finds no `openvino_genai`/`networkx` import in `src/`; `numpy<2.3.0` cap unexplained; `torch` in the mypy override list (`:91`) but not a dependency; `rich` imported nowhere in `src/`. F-CORE-050 documents the `.env.example` half.)

**What is wrong / assumed / missing**

Dead dependencies bloat the install (openvino-genai is hundreds of MB) and obscure which packages the security surface actually includes; the numpy cap has no recorded reason; `.env.example` (F-TEST-006) compounds the confusion.

**Why it matters**

Supply-chain surface and install time; every unused dependency is attack surface with zero benefit.

**Questions this raises**

1. None.

**Proposed remediation**

1. Run `uv run deptry src` (or equivalent) to confirm the unused set; remove `openvino-genai`, `networkx`, `rich` (or adopt them with a commit message explaining), and add a comment on the numpy pin citing the reason (kokoro-onnx/numpy 2.x incompat?).
2. Verification: `uv sync --frozen` green after removal; full T1 green.

**Verification test**

- **Tier:** T0
- **Input:** `uv run deptry src && uv run pytest -m "not hw and not soak" -q`
- **Expected output:** no unused deps flagged; tests green
- **Threshold:** n/a — boolean
- **Command:** `uv run deptry src`

**Cross-references:** F-CORE-050, F-TEST-006

---

### F-TEST-013 — `packaging/build_exe.py` regenerates icons with PyQt6 at build time but lists `PyQt6` only as a hidden import — build requires a GUI-capable environment silently

| Field | Value |
|---|---|
| **ID** | F-TEST-013 |
| **Title** | `packaging/build_exe.py` requires PyQt6 at build time for icon generation but never declares or checks it |
| **Severity** | S4 — Info |
| **Category** | INCOMPLETE |
| **Location** | `packaging/build_exe.py:24-46` |
| **Status** | OPEN |

**Evidence**

`packaging/build_exe.py:26-27`
```python
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QImage, QPainter
```
(icon generation runs only when `assets/icon.ico/png` are missing — currently present, so the branch is dormant; on a headless CI without PyQt6 the build crashes with an import error deep in the script.)

**What is wrong / assumed / missing**

Build-time icon generation from sprites is a nice-to-have with an unguarded import; the icons are committed, so the branch should either be deleted or the import moved to the top with a clear "PyQt6 required for icon generation" failure.

**Why it matters**

Informational build robustness.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `packaging/build_exe.py`: delete the icon-generation branch (icons are committed) or hoist the import with a clear error. Decision recorded: delete — generated artefacts should not be rebuilt from sprites at package time.
2. Verification: build with icons deleted → fails fast with a clear message, not an import traceback.

**Verification test**

- **Tier:** T0
- **Input:** build script review / optional T3 build
- **Expected output:** no dormant icon-generation branch
- **Threshold:** n/a — boolean
- **Command:** `uv run python packaging/build_exe.py --dry-run` (new flag)

**Cross-references:** F-TEST-004

---

### F-TEST-014 — `pyproject.toml` and `uv.lock` drift: `dev` dependency group duplicated between `[project.optional-dependencies]` and `[dependency-groups]`

| Field | Value |
|---|---|
| **ID** | F-TEST-014 |
| **Title** | `dev` dependencies are split between `[project.optional-dependencies]` and `[dependency-groups]` with different contents |
| **Severity** | S4 — Info |
| **Category** | MAINTAINABILITY |
| **Location** | `pyproject.toml:31-43,106-109` |
| **Status** | OPEN |

**Evidence**

`pyproject.toml:31-43` (`[project.optional-dependencies] dev = [pytest, pytest-asyncio, pytest-timeout, pytest-cov, hypothesis, mypy, ruff, import-linter, faster-whisper, jiwer]`) vs `:106-109` (`[dependency-groups] dev = [pyinstaller]`) — two "dev" groups with disjoint contents; `uv sync` installs the dependency-group, `pip install .[dev]` installs the optional-dependencies — different tools get different toolchains.

**What is wrong / assumed / missing**

The modern uv idiom is `[dependency-groups]` for all dev tooling; the split means `uv sync --frozen` (what `launch_lucca.bat` users get) does not include pytest/ruff/mypy — dev tooling arrives only via a second command nobody documents.

**Why it matters**

Informational: toolchain availability differs by install path; consolidation is mechanical.

**Questions this raises**

1. None.

**Proposed remediation**

1. Merge both into `[dependency-groups] dev = [...]` (uv-native), keep `[project.optional-dependencies]` empty or for extras only; regenerate `uv.lock`.
2. Verification: `uv sync --group dev` installs the full toolchain; `uv run pytest --collect-only` works after a bare `uv sync --group dev`.

**Verification test**

- **Tier:** T0
- **Input:** `uv sync --group dev && uv run pytest --collect-only -q`
- **Expected output:** collection succeeds
- **Threshold:** n/a — boolean
- **Command:** `uv sync --group dev`

**Cross-references:** F-TEST-005

---

### F-TEST-015 — The three T1 test failures' worth of hardware findings have no regression home: `hw` failures don't block or file anywhere

| Field | Value |
|---|---|
| **ID** | F-TEST-015 |
| **Title** | The two T3 hardware failures are recorded only as console output — no blocker, no report, no gate |
| **Severity** | S3 — Low |
| **Category** | TESTING |
| **Location** | `docs/audit/evidence/S1_30_T3_hw.txt`; `tests/test_phase1_live_hw.py`; `docs/audit/04_OWNER_DECISIONS.md` |
| **Status** | OPEN |

**Evidence**

Artefact: `S1_30_T3_hw.txt` (row 56) — `test_live_phase1_conversational_turn` (`tokens_out=0`) and `test_live_phase1_tool_call_turn` (`query_capabilities` ≠ `launch_app`) failed on real hardware at 00:58Z; the failures are cross-referenced by BRAIN (F-BRAIN-004) and CORE (F-CORE-007) findings, but no `14_blockers.md` entry, no hw report (F-TEST-010), and no automated gate consumed them.

**What is wrong / assumed / missing**

The audit's failure-handling convention ("never edit a threshold to pass; record the measured value in `docs/14_blockers.md` and stop" — AGENTS.md) has no target: `docs/14_blockers.md` is archived read-only, and the hw failures live only in this audit's evidence. Expected per the project's own rule: a blocker row per failed hardware gate.

**Why it matters**

Two real-hardware main-path failures currently survive only inside audit documents; the remediation programme must not lose them.

**Questions this raises**

1. None.

**Proposed remediation**

1. In the post-audit docs programme: create `docs/14_blockers.md` rows for both T3 failures citing `S1_30` and the owning findings (F-CORE-007, F-BRAIN-004).
2. Structural fix via F-TEST-010 (hw reports) so future failures are machine-recorded.
3. No code change in this audit.

**Verification test**

- **Tier:** n/a — documentation
- **Input:** the post-audit docs set
- **Expected output:** blocker rows exist citing both failures
- **Threshold:** n/a
- **Command:** n/a

**Cross-references:** F-BRAIN-007, F-CORE-007, F-BRAIN-004, F-TEST-010

---

## 4. Assumptions register

| # | Location | Assumption embedded in code/config | Why unverified | Risk if false |
|---|---|---|---|---|
| A-T-01 | `pyproject.toml:95-104` | `asyncio_mode = "auto"` is wanted for the async store tests | Works today; couples all tests to pytest-asyncio semantics | Sync tests accidentally async |
| A-T-02 | `pyproject.toml:12` | numpy `<2.3` cap is required | No recorded reason; deps not audited for 2.x compat (F-TEST-012) | Stale cap blocks security updates |
| A-T-03 | `build_exe.py:63` | Migrations dir bundling is the right layout for the frozen app | `db.py:20` uses `__file__`-relative path — resolves differently frozen | Migrations not found in the exe |
| A-T-04 | `Lucca.spec:28` | UPX packing is safe for the CUDA/OpenVINO DLLs | UPX notoriously breaks some signed/native DLLs | Exe crashes at import |
| A-T-05 | `conftest.py` | Tests may touch the host tree | No isolation fixture (F-TEST-007) | Prod data mutated by tests |
| A-T-06 | `S1_12` | T1 green means regression-safe | 61 % coverage with 0 %-holes in the exact interaction modules | Silent regressions |
| A-T-07 | `S1_13` | Exit 5 on `-m tier2` reads as "no tests" to operators | Ambiguous pytest exit semantics | Missing tier unnoticed (F-TEST-001) |

## 5. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-T-01 | Is the PyInstaller exe the intended distribution, or is `launch_lucca.bat` + uv the product? | F-TEST-004/005 remediation scope | owner |
| Q-T-02 | Should CI exist (GitHub Actions) or is local-only gating the policy? | F-TEST-008 shape | owner |
| Q-T-03 | Which T2 seeds from the area findings should land first? | F-TEST-001 seeding order | architect |

## 6. Coverage gaps

### 6.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| T2 integration tier existence and execution | SKILL.md §2 / testing convention | tier unregistered, empty (F-TEST-001) |
| Import-boundary enforcement | TM-01 | tool unconfigured (F-TEST-002) |
| Strict static gates | Charter §5.5 | gates disabled (F-TEST-003) |
| Packaged-exe boot | Spec 16 / packaging | none (F-TEST-004) |
| Launcher portability | — | none (F-TEST-005) |
| Env contract documentation | Spec 11 | example file stale (F-TEST-006) |
| Test/production isolation | — | none (F-TEST-007) |
| Mandatory T0 gate | SKILL.md §2 | command missing (F-TEST-008) |
| hw machine-readable reports | testing matrix §1/§4 | none (F-TEST-010) |
| Real-model seam tests | — | none (F-TEST-011) |
| hw failure blockers | AGENTS.md rule | none (F-TEST-015) |

### 6.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| T1 suite (131 passed) | Regression safety | 61 % coverage with 0 % on app.py/commorose/audio_proc/npu_proc/ptt/vad/admin/env_check/events — the interaction and process layers are untested |
| `-m tier2` | Integration tier | deselects everything, exit 5 (F-TEST-001) |
| `uv run lint` (SKILL.md T0) | Static gate | command does not exist (F-TEST-008) |
| `verify_environment.py` / `env-check` | Environment green | 7/7 and 6/6 PASS with MANIFEST absent, master key unset, WSL keys rejected (S1_09/10; cross-ref F-CORE-022/023/025) |

## 7. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** Reviewing F-TEST-001 (tier2) surfaced the T0-command gap F-TEST-008 (the SKILL.md gate that cannot run) and the marker-registration dependency for every other area's proposed tests. Reviewing F-TEST-004 (windowed exe) surfaced the launcher/spec disagreement F-TEST-005 and the migrations-bundling assumption A-T-03. Reviewing F-TEST-007 (no isolation) connected to the cross-area hard-coded-path findings that its fixture would flush out. Reviewing F-BRAIN-007's sign-off fabrication surfaced F-TEST-010 (hw reports) and F-TEST-015 (blocker home).
2. **Unasked questions.** 3 registered (§5); decisions recorded in findings (F-TEST-003: tighten with the retypings; F-TEST-008: add the script at minimum; F-TEST-013: delete the icon branch).
3. **Unwarranted assumptions.** The first draft asserted "no CI exists" as fact — verified by the repo listing (no `.github/`, no pre-commit) and kept, but F-TEST-008's remediation records the local-only policy alternative for the owner. The first draft of F-TEST-004 asserted the exe "would crash" — softened to the precise mechanism (`sys.stdout is None` → `print` raises) with F-CORE-004 as the mechanism citation; the exe was never run in the audit, so the claim is static-analysis-graded.
4. **Incomplete planning.** Every remediation names file, function, before/after, and a runnable command; the owner-owned calls (distribution target, CI policy, T2 seeding order) are parked as Q-T-01…03.
5. **Architectural flaws → F-ARCH candidates.** (a) F-TEST-001/002/003/008 together: the quality gate system is declaratively complete (tooling installed, tiers named, controls cited) and functionally absent — recommended for a single F-ARCH "governance layer not instantiated" finding alongside the architecture-not-instantiated family; (b) F-TEST-010/015: the sign-off artefact chain (Charter §5.3) has no machine-recorded substrate — programme-level.

Severity re-grades during the pass: F-TEST-001/002 kept S1 (the two gates whose absence explains the widest finding spread); F-TEST-004 S1→S2 (static-analysis-graded, unrun exe); F-TEST-007 S1→S2 (prod mutation limited to traces/logs in observed runs); F-TEST-013/014 set S4/S3 per impact.
