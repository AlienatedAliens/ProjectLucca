# 06 — Critical Review Findings & Code-Fix Issue List

The full narrative of findings is in [`HANDOVER_2026-09-17_critical_review.md`](HANDOVER_2026-09-17_critical_review.md) (§2–§24). This document is the **actionable index**: every defect found in `src/`, `tests/`, `pyproject.toml`, `scripts/`, and docs, mapped to the spec that defines the fix. Severity: **S1** breaks correctness/security, **S2** breaks a stated requirement, **S3** quality/consistency.

## A. Existing code (`src/lucca/`) — nothing here has been executed; assume all of it is scaffold

| # | File | Defect | Sev | Fix spec |
|---|---|---|---|---|
| C-01 | `reasoning/promotion_gate.py:22` | `List[Dict[str, Any]]` with `Any` unimported → `NameError` at instantiation | S1 | spec 05 §9 (rewrite as `lifecycle.py`) |
| C-02 | `reasoning/promotion_gate.py:68` | `verify_regression_suite` returns `True` unconditionally | S1 | spec 05 §9 |
| C-03 | `reasoning/promotion_gate.py` | one shadow failure leaves a permanent zombie; no lifecycle states; no persistence; `is_active` builds dummy rule | S2 | spec 05 §9 |
| C-04 | `reasoning/micro_scheme.py` | whitespace tokenizer breaks quoted strings; no comments | S1 | spec 05 §3 |
| C-05 | `reasoning/micro_scheme.py` | `and`/`or` are functions (eager) | S2 | spec 05 §4 |
| C-06 | `reasoning/micro_scheme.py` | `define` mutates shared global env | S1 | spec 05 §4 |
| C-07 | `reasoning/micro_scheme.py` | `if` arity crash; raw Python exceptions leak; no depth cap; O(n²) parser; `*` on strings; no numeric caps | S1 | spec 05 §3–4 |
| C-08 | `reasoning/micro_scheme.py` | primitives referenced by docs absent; four DSLs | S2 | spec 05 §1–2 |
| C-09 | `router/conformal_guard.py:10` | hard-coded `quantile_threshold=0.82`, `alpha` unused, no `fit` | S1 | spec 06 §7 |
| C-10 | `router/heuristic_router.py` | substring keyword match (`run`∈`running`); `log_path` unused; `Dict[str, Any]` | S2 | spec 06 §2–3 |
| C-11 | `memory/provenance_gate.py` | single key signs+verifies; colon-joined signing string; unsigned `entry_id/entities/confidence`; no freshness/replay; default key | S1 | spec 03, ADR-006 |
| C-12 | `sandbox/safe_file_tool.py` | raises `PathTraversalException` where doc 04 expects `PermissionError`; `%2f` undecoded; no size caps; no symlink/`O_NOFOLLOW`; Windows-centric for a Linux container | S1 | spec 09 §4 |
| C-13 | `voice/streaming_chunker.py` | splits on decimals/abbreviations/filenames; token-count threshold; no max split; no `reset()`; no markdown normalisation; no tool-call demux | S2 | spec 08 |
| C-14 | `core/schemas.py:48,84,93` | `Dict[str, Any]` (zero-`Any` rule) | S3 | spec 02 (`JsonValue`) |
| C-15 | `core/config.py:25` | single `audio_sample_rate=24000`; hard-coded project path; default secret key; not `pydantic-settings` | S2 | spec 11 §1, register E2 |
| C-16 | `core/exceptions.py` | taxonomy incomplete | S3 | spec 11 §3 |
| C-17 | `brain/`, `senses/`, `ui/` | empty, no `__init__.py`; `lucca.main` missing | S2 | spec 01 §1 |
| C-18 | `tests/conftest.py` | fixtures reference modules that don't exist; `quantile_threshold=0.80` magic | S2 | matrix v2 §1 fakes |

## B. Build / repo

| # | Item | Defect | Fix |
|---|---|---|---|
| B-01 | `pyproject.toml` | `chromadb`, `rank-bm25`, `pynput` present; `httpx`, `pydantic-settings`, `pyzmq`, `openvino*`, `kokoro-onnx`, `sqlite-vec`, `rapidfuzz`, `structlog`, `psutil`, `PyQt6`, `lightgbm`, `scikit-learn`, `hypothesis`, `pytest-timeout`, `import-linter`, `jiwer` missing; no `uv.lock` | spec 11 §5 |
| B-02 | `scripts/setup_wslconfig.ps1` | writes `pageReporting=false`, `swap=2048MB` | register C2/C3 |
| B-03 | `scripts/verify_environment.py` | must add: MSHybrid VRAM baseline, NPU visibility, `sqlite-vec` load, Docker CE in Ubuntu (`docker info` via `wsl`), `LUCCA_HOME` layout, llama-server binary + model sha256 | spec 11 §7 `env-check` |
| B-04 | `README.md` | claims doc 01 contains k≤2 audio compaction; describes `.vscode` files; says vLLM/Chroma; latency "sub-400" | rewrite per register G3/I1/A2 + point to this doc set |
| B-05 | `.agents/skills/lucca-pipeline/SKILL.md` | references `python -m lucca.main`, vLLM health check, Chroma | update to llama-server `/health`, `lucca-admin env-check`, new test tiers |
| B-06 | `GEMINI.md` / `AGENTS.md` | AGENTS.md invariants remain valid; add pointer: "decisions log + register override docs 00–05" | one-line edit |

## C. Documentation defects (docs 00–05) — resolved by the new set, kept for traceability

| # | Doc | Defect | Resolved in |
|---|---|---|---|
| D-01 | 00/01/03/05 | vLLM + Q6 GGUF impossible | ADR-001 |
| D-02 | 01 L60–68 | latency "proof" uses unsourced 35 ms encoder / 45 ms TTFT / 43 ms-per-s Kokoro | spec 10 (measured budgets) |
| D-03 | 03 L202–210, 01 L124–130 | iptables ordering bug ×2, no default drop, DNS to LAN, IPv6 | ADR-003 |
| D-04 | 03 | `pageReporting=false`, swap 2 GB, vLLM in clamp | register §C |
| D-05 | 03 L151 | "zero-copy linear interpolation" | register E1 |
| D-06 | 03 | single sandbox with Playwright + read-only + pids 64 | ADR-004 |
| D-07 | 04 L112–113 | inverted latency assertion; vLLM VRAM check | matrix v2 §5 |
| D-08 | 04 | vacuous egress test; API-mismatched rule tests; trivial hallucination test; `PermissionError` | matrix v2 |
| D-09 | 04 §2.3 | ECE/accuracy/set-size thresholds unmeasurable at N | spec 06 §5–7 |
| D-10 | 02 | cascade latency, licence, backbone, Elo≠MOS, missing survey | doc 12 |
| D-11 | 05 | "mathematically prevents"; "sub-400 ms"; `Dict[str, Any]`; hexagonal claimed but unspecified | ADR-006, register A2/G4, spec 02 |
| D-12 | 00 | Whisper as "logging pass" only; Downloads folder example; GPU-PV to sandbox; Kokoro-on-NPU hard criterion; Phase 4–6 human dependence unstated | D-02, D-08, F7, D-07, phase plan |
| D-13 | 01 | distinctness precedence ambiguous; rules described as pure yet call tools; reflection thresholds unsourced | spec 05 §8, ADR-007, spec 05 §10 |
| D-14 | all | no process model, no IPC, no trace schema, no threat model, no config precedence, no error taxonomy, no retention, no backups, no migrations | ADR-008, specs 01, 10, 12, 11, 04 |

## D. Implementation order for the code fixes

1. Skeleton: packages + `__init__.py`, `ports.py`, `ipc_schemas.py`, `exceptions.py`, `config.py` (pydantic-settings), `main.py` supervisor with fakes (C-14..17, B-01).
2. Static gates green on the skeleton (ruff/mypy/import-linter) **before** porting any old logic.
3. Rewrite, do not patch: `scheme/` (C-04..08), `memory/signers.py + gate.py` (C-11), `sandbox/file_tool.py` (C-12), `brain/chunker.py + toolcall_demux.py` (C-13), `router/conformal.py + heuristic.py` (C-09, C-10), `reasoning/lifecycle.py` (C-01..03).
4. Delete `promotion_gate.py`, `micro_scheme.py`, `provenance_gate.py`, `safe_file_tool.py`, `streaming_chunker.py`, `conformal_guard.py`, `heuristic_router.py` once their replacements' Tier-1 tests pass (git history keeps them).
5. Only then begin Phase 0 spikes.
