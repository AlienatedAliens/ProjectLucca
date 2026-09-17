# START HERE — Implementer Entry Point (Project Lucca)

You are implementing Project Lucca from a reviewed, decided plan. This page tells you what to read, in what order, what you may not change, and what to do when reality disagrees with a document.

## 1. Read order (≈ 90 minutes)

1. [`13_decisions_log.md`](13_decisions_log.md) — every decision, its evidence, what it supersedes.
2. [`07_contradiction_register.md`](07_contradiction_register.md) — canonical numbers; wins over docs 00–05.
3. [`08_adr/`](08_adr/) ADR-001 → 008.
4. [`09_developer_spec/`](09_developer_spec/) 01 → 12 (01, 02, 11 first — they define the skeleton you build first).
5. [`10_testing_matrix_v2.md`](10_testing_matrix_v2.md) and [`11_phase_plan_v2.md`](11_phase_plan_v2.md).
6. [`06_critical_review_findings.md`](06_critical_review_findings.md) §A and §D — what to delete/rewrite in `src/`.
7. Skim [`12_prior_art_survey.md`](12_prior_art_survey.md); consult docs 00–05 only for background.

## 2. Ten facts you must not re-derive

1. LLM = `llama-server` **natively on Windows**, Ultravox Q6_K GGUF + `mmproj`. vLLM is retired. (ADR-001)
2. Ultravox emits **no transcript** → Whisper runs on the Intel NPU **every turn**, in parallel with the LLM. (D-02)
3. Cascade/transcript mode is the **same binary and same model file** without `--mmproj`. (ADR-001 §fallback)
4. WSL2 hosts **only** the sandbox: Docker **CE** inside Ubuntu, `nat` networking, `.wslconfig` per register §C. (D-03/D-04)
5. Storage = one SQLite file: WAL + FTS5 + `sqlite-vec`. Chroma/rank-bm25/pickle are gone. (ADR-002)
6. Runtime root `C:\ProjectLucca`; only `workspace\` is ever mounted into a container; the host wipes it at task close. (D-08)
7. Provenance: no signer exists for `LLM_NARRATION`; `USER_DERIVED` needs quote-grounding; tool bodies are `TOOL_CONTENT_UNTRUSTED`. (ADR-006)
8. Rules are pure `State → Plan`; the orchestrator executes plans under the risk policy; WRITE/LAUNCH always confirm. (ADR-007)
9. Four processes + external llama-server; ZMQ control plane; shared-memory audio rings; audio callback < 2 ms. (ADR-008)
10. Latency gate: median ≤ 600 ms, p95 ≤ 800 ms, PTT-release → first non-silent sample, from the trace, both modes reported. (spec 10)

## 3. Build order

```
Phase 0 spikes (≤ 3 days)  →  skeleton + static gates  →  rewrite the 7 scaffold modules  →  Phase 1 … Phase 6
```
- Skeleton first (spec 01 §1 layout, ports in spec 02, config in spec 11). `ruff`, `mypy --strict`, `import-linter` must be green **before** any old logic is ported.
- Then rewrite (not patch) the modules listed in `06 §A`; delete originals once Tier-1 tests pass.
- Every adapter ships a `Fake*` and a contract test (spec 02 §Adapter acceptance).
- Phase gates are in matrix §4. Phases 4–6 stop at **human gates**; build Phase 5 mechanics while H-4 data accumulates.

## 4. When a document is wrong

- **A threshold cannot be met on the real hardware:** do **not** change it. Write the measured value, the test ID, and the environment to `docs/14_blockers.md` and stop that phase. Someone will decide.
- **A number is marked *estimate*:** measure it in Phase 0, write the measurement into `docs/14_phase0_results.md`, and update the spec line with the value and date.
- **Two of the new documents disagree:** the decisions log wins, then the register, then the ADR, then the spec. Record the conflict in `docs/14_second_pass_review.md` as a new row.
- **A prior-art claim marked `B`/`R`:** verify (URL, licence, date) before relying on it; log in `docs/12a_prior_art_verification.md`.

## 5. Things a weaker model tends to do here — don't

- Don't "temporarily" run Whisper, Kokoro, or embeddings inside WSL2/Docker to make something work. The NPU is host-only.
- Don't write a test that passes when the thing under test is absent (vacuous egress test, `return True` regression suite, discard test with no positive control). Every negative test needs a positive control.
- Don't put `Dict[str, Any]` in a public model; use `JsonValue` or a typed sub-model.
- Don't fabricate "real usage" decisions to unblock Phases 4–6.
- Don't insert iptables rules with `-I` in a loop.
- Don't measure latency from anything but the trace points in spec 10.
- Don't add a dependency that isn't in spec 11 §5 without an ADR.

## 6. Definition of done for this plan's handoff

- [x] Decisions recorded and user-approved (`13`).
- [x] Contradictions reconciled with canonical values (`07`).
- [x] ADRs 001–008 written with alternatives.
- [x] Developer specs 01–12 with normative numbers and test IDs.
- [x] Testing matrix v2 with tiers, property tests, sign-off bundles.
- [x] Phase plan v2 with Phase 0 spikes and explicit human gates.
- [x] Prior-art survey with verification status.
- [x] Defect index for existing code and docs.
- [x] Second-pass review performed and its fixes applied (`14_second_pass_review.md`).
- [x] README / AGENTS / GEMINI / SKILL point to the new set.
- [ ] Phase 0 measurements (implementer).
- [ ] `docs/14_blockers.md` (created only if a threshold fails).
