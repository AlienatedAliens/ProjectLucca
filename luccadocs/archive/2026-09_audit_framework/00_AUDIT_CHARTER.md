# 00 — Audit Charter: Project Lucca Enterprise-Grade Audit

**Status:** ACTIVE
**Opened:** 2026-09-17 (UTC)
**Baseline:** git HEAD `ed14f6b44fc233c94f01c9f9f3c1f68619e026e7` on `master`, dirty working tree (see [`03_BASELINE.md`](03_BASELINE.md))
**Archived predecessor docs:** [`luccadocs/archive/2026-09-17_pre_phase4_audit/ARCHIVE_INDEX.md`](../archive/2026-09-17_pre_phase4_audit/ARCHIVE_INDEX.md)

---

## 1. Purpose

Project Lucca has been built through Phase 4. This audit is a full, enterprise-grade review of the codebase as it actually exists — not as the (now archived) documentation describes it. Its output is a body of findings that a subsequent remediation programme and a fresh, code-derived documentation set can be built from.

The audit exists to answer, with evidence, five questions about every subsystem:

1. Does the code uphold the hard invariants?
2. Does the code do what it claims to do on the main path and on edge paths?
3. Is every specified behaviour covered by a mechanical test?
4. Where has the implementation drifted from the archived specification, and which side is right?
5. What has been assumed, left unasked, or left incomplete?

## 2. Scope

### 2.1 In scope

Everything under:

- `src/lucca/` — all packages: `core`, `brain`, `memory`, `reasoning`, `router`, `sandbox`, `senses`, `ui`, plus `main.py`, `admin.py`, `ports.py`
- `tests/` — all test modules, fakes, fixtures
- `config/` — `intents.toml`, `persona.toml`, `tool_whitelist.toml`
- `docker/` — both sandbox Dockerfiles and `toolsrv/server.py`
- `scripts/` — including `scripts/wsl/lucca-egress.sh`
- `packaging/` — `build_exe.py`, and root `Lucca.spec`, `launch_lucca.bat`
- Root build/config files: `pyproject.toml`, `uv.lock`, `.env.example`, `.gitignore`
- The archived documentation set, **only** as a reference point for spec-drift findings

**All shipped "extra" features are first-class and in scope.** This explicitly includes: the affect layer (`core/affect.py`), the commorose (`ui/commorose.py`), the telemetry HUD (`ui/telemetry_hud.py`), system tools (`sandbox/system_tools.py`), the persona system (`config/persona.toml`, `brain/prompt_builder.py`), sprites (`ui/sprite.py`, `assets/sprites/`), and the egress script (`scripts/wsl/lucca-egress.sh`). None of these may be dismissed as "out of scope" or "experimental".

### 2.2 Out of scope

- Writing the new documentation set (a later programme; depends on this audit's findings)
- Any change to source, tests, configuration, containers, scripts, or packaging (see §3.1)
- Re-litigating user decisions already recorded in §5

## 3. Rules

### 3.1 Findings-only

**No file under `src/`, `tests/`, `docker/`, `scripts/`, `config/`, or `packaging/` may be modified, created, or deleted by any audit subtask.** Root files (`pyproject.toml`, `uv.lock`, `Lucca.spec`, `launch_lucca.bat`, `.env.example`, `.gitignore`, `README.md`, `AGENTS.md`, `GEMINI.md`) and `.agents/` are equally frozen. The only writable locations during the audit are `luccadocs/audit/**`.

Auditors may *run* code (tests, static gates, scripts) to produce evidence, provided execution does not mutate the frozen trees. Any artefact produced must land under `luccadocs/audit/evidence/` and be registered in [`02_EVIDENCE_INDEX.md`](02_EVIDENCE_INDEX.md).

### 3.2 No threshold edits

If a measured value fails a spec'd threshold, the auditor records the measured value and the threshold verbatim in the finding. The auditor never proposes "relax the threshold" as remediation unless the finding separately demonstrates, with evidence, that the threshold itself was wrong. This mirrors the project rule: *never edit a threshold to make a test pass*.

### 3.3 Hardware truth

All performance, memory, and VRAM reasoning in findings must use the **current** host, not any forward-looking configuration:

| Resource | Truth |
|---|---|
| System RAM | 16 GB |
| GPU | NVIDIA RTX 5080, 16 GB VRAM (Blackwell `sm_120`) |
| CPU | Intel Core Ultra 9 275HX (Arrow Lake) |
| NPU | Intel NPU — reachable **only** from native Windows 11, never from WSL2 or Docker |
| WSL2 | memory-clamped to **4.5 GB** via `.wslconfig` |
| Tree models | XGBoost / LightGBM run on **CPU**, never NPU |

The archived `ADR-010` (64 GB system-RAM upgrade) is **forward-looking only**. Any finding that relies on 64 GB is invalid. Any code path or config that silently assumes >16 GB RAM or >4.5 GB WSL2 is itself a finding.

### 3.4 Evidence rule

**Every finding must cite either a `file:line` (or `file:line-line`) location in the frozen tree, or an evidence artefact path under `luccadocs/audit/evidence/`.** Both are preferred.

- "Appears to", "seems to", "probably", "likely" **without an accompanying citation are disallowed.** If the auditor cannot confirm, the item is filed at severity S4 (Info) with category ASSUMPTION and an explicit question.
- Verbatim code excerpts in the `Evidence` field must be copied, not paraphrased.
- Line numbers refer to the file state at baseline HEAD `ed14f6b` **plus the uncommitted working-tree changes** listed in `03_BASELINE.md` §2 — i.e., the tree as it exists on disk at audit start. If a later subtask observes the tree has changed, it must stop and report.

### 3.5 Recursive review method

The audit is recursive: **every finding is itself re-reviewed** before it is accepted. The re-review asks, of the finding — not the code — five questions:

1. **Oversights** — Did the finding miss a sibling defect in the same function, an identical pattern elsewhere, or a consequence in a caller?
2. **Unasked questions** — What did the auditor need to know but did not ask? Every such question goes into `Questions this raises`.
3. **Unwarranted assumptions** — Did the finding assume a spec, a runtime condition, a hardware fact, or an intent that is not evidenced?
4. **Incomplete planning** — Is the `Proposed remediation` executable by a weaker model without judgement calls? Are there missing steps, missing file names, missing before/after behaviour?
5. **Architectural flaws** — Is this finding a local symptom of a structural problem? If so, a separate `F-ARCH-NNN` finding must be raised and cross-linked.

A finding that has not been re-reviewed carries `Status: DRAFT`. Only re-reviewed findings carry `Status: OPEN`.

### 3.6 One finding, one defect

A finding describes exactly one defect, assumption, or gap. Related defects are separate findings, cross-linked by ID. Aggregations ("various issues in module X") are disallowed.

### 3.7 Neutral tone

Findings state what the code does, what was expected, and why the gap matters. No praise, no blame, no speculation about motive.

## 4. Severity scale

| Severity | Name | Definition |
|---|---|---|
| **S0** | Critical | Violation of a hard invariant (§5), data loss, or a security defect (sandbox escape, egress bypass, provenance forgery, untrusted content reaching memory) |
| **S1** | High | Incorrect behaviour on the main (happy) path of a shipped feature |
| **S2** | Medium | Incorrect behaviour on an edge path, **or** a spec'd behaviour with no mechanical test covering it |
| **S3** | Low | Code quality, maintainability, dead code, naming, typing weaknesses (including `Any` in public interfaces), duplicated logic |
| **S4** | Info | A question to answer or an assumption to confirm; no defect asserted yet |

Severity is assigned by consequence, not by fix effort. A one-line fix to an S0 is still S0.

## 5. Hard invariants (any violation is S0 / INVARIANT)

1. **No freeform LLM narration into memory.** Memory commits originate only from `USER_EXPLICIT`, `USER_DERIVED` (quote-grounded from a `USER_EXPLICIT` source), `TOOL_VERIFIED`, or `LISP_ASSERTION`. `TOOL_CONTENT_UNTRUSTED` is never memory-eligible without a user act. `LLM_NARRATION` has no signer and is rejected by the `ProvenanceGate`.
2. **Hardware budget discipline** as per §3.3. No heavy background processes in WSL2. No OpenVINO NPU work inside WSL2/Docker. No tree models on NPU.
3. **Phased build discipline.** No phase proceeds until the prior phase's sign-off bundle is green and its reports exist. Human gates (Phases 4–6) are never satisfied by synthetic data. Thresholds are never edited to pass.
4. **Symbolic rule promotion gate.** No LISP rule compiled from a single interaction. Promotion requires N ≥ 5 distinct cluster successes with 0 failures and 100 % pass on historical regression cases.
5. **Code standards.** Python 3.12+, `uv`, Pydantic v2 for every cross-boundary contract, zero `Any` in public interfaces.

Settled facts auditors must not contradict without evidence: LLM = `llama-server` natively on Windows serving Ultravox Q6_K GGUF; Whisper runs on every turn; storage = SQLite + FTS5 + sqlite-vec; Docker CE inside Ubuntu WSL2; runtime root `C:\ProjectLucca`; four host processes + ZMQ.

## 6. Category taxonomy

Every finding carries exactly one primary category:

| Category | Use when |
|---|---|
| `INVARIANT` | A §5 invariant is violated or is unenforced by code |
| `CORRECTNESS` | Code produces a wrong result, wrong state, or wrong side-effect |
| `SECURITY` | Trust-boundary weakness: sandbox, egress, RPC, path handling, provenance, secrets, privilege |
| `PERFORMANCE` | Latency, throughput, memory, VRAM, or NPU/CPU budget concerns against hardware truth |
| `RELIABILITY` | Crash, hang, leak, unhandled exception, missing timeout, missing retry/backoff, unsafe shutdown |
| `TESTING` | Missing, weak, non-mechanical, flaky, or misleading tests; fixtures that do not exercise the claimed behaviour |
| `SPEC-DRIFT` | Implementation disagrees with the archived spec; finding must state which side is believed correct and why |
| `ASSUMPTION` | Code or design embeds an unverified premise about hardware, environment, model behaviour, or user intent |
| `INCOMPLETE` | Stub, TODO, partial implementation, unreachable feature flag, dead config key |
| `MAINTAINABILITY` | Structure, typing, duplication, naming, module boundaries, dependency direction |
| `UX` | Behaviour visible to the user that is confusing, misleading, or unsafe (including HUD/telemetry honesty) |
| `DOCS` | In-code docs, docstrings, `README`, `AGENTS.md`, help text that are wrong or stale relative to code |

## 7. Finding areas and IDs

Finding IDs follow `F-<AREA>-<NNN>` (zero-padded, three digits, unique per area). Areas:

| AREA | Covers |
|---|---|
| `CORE` | `src/lucca/core/**`, `main.py`, `ports.py`, `admin.py` |
| `BRAIN` | `src/lucca/brain/**` |
| `MEM` | `src/lucca/memory/**` including migrations |
| `REAS` | `src/lucca/reasoning/**` |
| `ROUT` | `src/lucca/router/**` |
| `SBX` | `src/lucca/sandbox/**`, `docker/**`, `scripts/wsl/**` |
| `SENS` | `src/lucca/senses/**` |
| `UI` | `src/lucca/ui/**`, `assets/**` |
| `TEST` | `tests/**`, `pyproject.toml` test/lint/type config, `packaging/**`, `Lucca.spec`, `scripts/**` (non-WSL) |
| `DRIFT` | Implementation vs. archived-spec divergences that span areas |
| `ARCH` | Cross-cutting structural findings raised via §3.5 step 5 |

One findings file per area lives under [`findings/`](findings/README.md). Every finding uses [`01_FINDING_TEMPLATE.md`](01_FINDING_TEMPLATE.md) verbatim.

## 8. Evidence and artefacts

- All produced artefacts (test logs, static-gate output, measurements, generated inventories) are stored under `luccadocs/audit/evidence/` and registered in `02_EVIDENCE_INDEX.md` with producer subtask, exact command, and UTC timestamp.
- Artefacts are append-only. Re-running a command produces a new artefact with a new timestamp; the old one is not overwritten.
- Test tiers referenced in findings follow the project convention: **T0** static (ruff/mypy/import-linter), **T1** unit (no hardware, fakes), **T2** integration (real IPC/DB/containers, no hardware models), **T3** hardware-in-the-loop (`hw` marker). Soak (T4) is out of audit scope unless a finding specifically requires it.

## 9. Decisions already made (do not re-ask)

1. All pre-audit `luccadocs/` content is archived read-only; a fresh docs set will be written later from code truth.
2. The audit is findings-only (§3.1).
3. Hardware truth is §3.3; `ADR-010` is forward-looking only.
4. All "extra" features are shipped, first-class, in scope (§2.1).

## 10. Known stale references at audit start

`AGENTS.md` and `.agents/skills/lucca-pipeline/SKILL.md` reference `luccadocs/…` paths that now resolve only under `luccadocs/archive/2026-09-17_pre_phase4_audit/`. These files are frozen for the audit; the stale paths are to be handled by a later subtask and should be recorded as a `DOCS` finding when the `TEST`/`DRIFT` area is audited.
