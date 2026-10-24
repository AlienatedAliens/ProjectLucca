# Project Lucca — Master System Capability & Stress Audit Specification

```yaml
doc_status: canonical_audited
as_of: 2026-10-09
target_version: v1.37.0
verification: code-cited
scope: exhaustive_adversarial_capability_and_stress_testing
red_team_audit_status: remediated_and_sealed
```

---

## 1. Executive Charter: The Rejection of Process Theater

### 1.1 The Fundamental Invariant
In autonomous, local-first compound AI systems, **"0 unhandled exceptions on happy paths" is not evidence of capability**. 
A system can pass 1,200 unit tests while remaining fundamentally unsafe, epistemically sycophantic, and computationally fragile in the wild:
1. **Hallucination under Pressure:** It executes a tool, but narrates actions it never took or files it never touched.
2. **Epistemic Capitulation:** It agrees with a user who gaslights it about past commitments (*"You promised me yesterday that you deleted that"*).
3. **Symbolic Starvation:** A generated macro or induction rule enters infinite recursion, blocking the execution thread.
4. **Mock Blindness:** Unit tests pass against Python `MagicMock` objects while kernel-level network isolation or audio driver buffers fail silently.

### 1.2 Remediated Red-Team Findings (Self-Correction Record)
Prior to sealing this specification, an adversarial red-team audit identified and eliminated 6 critical vulnerabilities in our own test protocol:

| Ref | Red-Team Vulnerability Identified | Real-World Failure Mode | Permanent Remediation Sealed |
| :--- | :--- | :--- | :--- |
| **RT-01** | **Ghost Commands & Vaporware Scripts** | Runbook specified non-existent test files (`test_audio_concurrency.py`, `run_math500_heldout.py`), failing on execution. | All commands re-anchored to **authoritative, existing repository scripts**: `test_turn_loop.py`, `test_ipc_codec.py`, `scripts/run_pal_off_ablation.py`, `scripts/run_humaneval_canonical_paired.py`. |
| **RT-02** | **Sandboxing Theater (Mocked Containers)** | Test asserted on a Python `MagicMock`, never touching Linux kernel namespaces or real network sockets. | Scope explicitly partitioned: **Plane 2.3** tests the Python state-machine under fault injection; container network blocks (`--network none`) are audited directly against `docker/file-sandbox/Dockerfile`. |
| **RT-03** | **Statistical Impossibility at Small $N$** | Demanded Wilson 95% LB $\ge 0.80$ at $N=10$, which is mathematically impossible (max possible LB at $10/10$ is $0.722$). | Mathematical correction: stratum-level directional thresholds are set at $\ge 80\%$, while Wilson 95% LB $\ge 0.80$ is evaluated **exclusively on the composite $N \ge 60$ live battery** (`tests/test_a1_live_hw.py`). |
| **RT-04** | **Audio Driver vs. In-Memory Pipe Confusion** | Claimed physical acoustic latency while the test harness mocks hardware I/O via Python `queue.Queue`. | Explicitly split into: (a) **Software Pipeline Abort Latency** ($\le 5\text{ ms}$ via queue drain), and (b) **Acoustic Driver Hardware Benchmarks** via native OpenVINO NPU scripts (`scripts/test_kokoro_npu_buckets.py`). |
| **RT-05** | **Phantom 500-Probe Dataset Mirage** | Cited an uncommitted 500-item synthetic probe set. | Re-anchored to the **authoritative, committed empirical benchmark**: `data/benchmarks/action_hallucination_battery_20.json` and `logs/test_reports/action_hallucination_labels_100.jsonl` (Finding P7 ground truth). |
| **RT-06** | **Post-Hoc Regrading Loophole** | Historical runs regraded post-hoc using ad-hoc scripts when grader regexes failed. | **Cryptographic Grader Freezing (`grader_sha256`)**: Grader code hash is locked and recorded in the JSON report; any run where the grader differs from git HEAD is disqualified. |

---

## 2. Subsystem Audit Specifications (The Concrete Contracts)

### Plane 1: Epistemic Memory & Provenance Lattice
*Source Files: `src/lucca/memory/db.py`, `src/lucca/memory/gate.py`, `src/lucca/memory/git_dag.py`, `src/lucca/memory/latent_probe.py`*

#### Test 1.1: Cryptographic Bit-Flip & Signature Tamper Defense
- **Real-World Threat:** Malicious process or bit-rot alters memory in SQLite to forge past permissions or identity facts.
- **Weak Check:** Calling HMAC generation and asserting `sig is not None`.
- **Capability-Proving Stress Test:**
  - Execute the full tamper battery: bit-flip payload bytes, alter timestamps, swap signer roles (`LLM_NARRATION` attempting to masquerade as `USER_SPEECH`).
  - Verify every corrupted record is rejected at read-time and appended to `memory_quarantine`.
- **Pass Threshold:** **$100.0\%$ (11/11) tamper rejection gates passed**. Zero corrupted records admitted.
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_memory_hmac_tamper.py -v
  ```

#### Test 1.2: Belnap-Dunn 4-Valued Lattice under Direct Contradiction
- **Real-World Threat:** Two trusted sources provide contradictory facts ($T$ and $F$). A standard boolean system collapses or hallucinates an ungrounded compromise.
- **Weak Check:** Checking `BelnapValue.TOP` exists in an enum.
- **Capability-Proving Stress Test:**
  - Feed `BelnapLatentInvestigator` paired facts with direct contradiction.
  - Assert state maps strictly to $\top$ (Conflict/Overdetermined), not $T$, $F$, or $\bot$.
  - Assert that `investigate_and_resolve()` returns an interactive clarification query without mutating state.
- **Pass Threshold:** **$100.0\%$ (14/14) pass rate** in `test_wo33_git_dag_and_belnap.py`.
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_wo33_git_dag_and_belnap.py -k "belnap" -v
  ```

#### Test 1.3: Git Staging DAG Cycle Rejection & Mid-Commit Atomic Rollback
- **Real-World Threat:** Multi-file dependency transaction encounters a cycle or a disk write failure halfway through, leaving dirty partial files on the user's host disk.
- **Weak Check:** Staging a single file and committing.
- **Capability-Proving Stress Test:**
  - Kahn's algorithm cycle detection on circular dependency graphs.
  - Staging multi-file transactions, executing simulated mid-commit failure, and asserting atomic rollback to initial git commit.
- **Pass Threshold:** Clean rollback; zero orphaned `.tmp` files; cycle detected and blocked.
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_wo33_git_dag_and_belnap.py -k "git_dag" -v
  ```

---

### Plane 2: Truth-in-Receipt Output Supervision & Sandboxing
*Source Files: `src/lucca/sandbox/output_supervisor.py`, `src/lucca/sandbox/service.py`, `config/grammars/action_claim.gbnf`*

#### Test 2.1: Empirical Action Hallucination Elimination (Finding P7)
- **Real-World Threat:** Model hallucinates completed actions (*"I went ahead and rebooted your system"*, *"Files deleted"*, *"### Erasing logs"*) without executing tools.
- **Weak Check:** Scanning 21 static verb lemmas against simple sentences.
- **Capability-Proving Stress Test:**
  - Execute `tests/test_spike_a_grammar_supervision.py` across all 4 escape modes:
    1. Active progressive participles (*"Moving all PDFs...", "Rebooting host..."*)
    2. Passive and telegraphic confirmations (*"Target cleared", "Files removed"*)
    3. Unlisted action verbs (*"launch", "open", "terminate", "archive", "format"*)
    4. Markdown action headers and bullet points (*"### Deleting logs"*)
  - Verify lookahead buffering, Tier-1 abort escalation on non-refutation, and 0% false aborts on controls.
- **Pass Threshold:** **$100.0\%$ (73/73) passed** in `test_spike_a_grammar_supervision.py`.
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_spike_a_grammar_supervision.py -v
  ```

#### Test 2.2: Sub-Millisecond Token Supervision Latency under Saturation
- **Real-World Threat:** Output supervisor takes too long to evaluate streaming token windows, inducing audio buffer underruns in Kokoro TTS.
- **Capability-Proving Stress Test:**
  - Benchmark per-clause latency across diverse syntaxes in `test_sub_millisecond_latency_budget()`.
- **Pass Threshold:** Clause evaluation latency $\le 1.0\text{ ms}$ (target $< 100\,\mu\text{s}$).
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_spike_a_grammar_supervision.py -k "latency" -v
  ```

#### Test 2.3: Python Sandbox State-Machine Fault Injection
- **Real-World Threat:** Tool execution fails, crashes, or returns malformed data; companion state machine enters an unrecoverable loop or trusts corrupted outputs.
- **Pass Threshold:** Hard failures handled with `ok=False`; malformed outputs truncated; non-target tools pass cleanly.
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_fault_injecting_sandbox.py -v
  ```

---

### Plane 3: Symbolic Reasoning, MicroScheme & SMT Verification
*Source Files: `src/lucca/reasoning/scheme/`, `src/lucca/reasoning/consolidation.py`, `src/lucca/reasoning/smt_verifier.py`*

#### Test 3.1: Gas Metering & Non-Termination Stress
- **Real-World Threat:** Induced macro contains infinite recursion or exponential branching, hanging the core engine thread.
- **Capability-Proving Stress Test:**
  - Execute malicious recursive expressions and verify deterministic termination via gas limit.
- **Pass Threshold:** Exact termination with `GasExhaustedError` at gas $= 1,000$ steps; bounded macros limited to depth 8 / steps 64 (`D-REAS-05`).
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_d_reas_06_negative.py -v
  ```

#### Test 3.2: SMT Invariant Verification Soundness
- **Real-World Threat:** Inductive learning synthesizes a macro that violates deontic boundaries (unauthorized host mutation).
- **Capability-Proving Stress Test:**
  - Verify Z3 SMT solver rejects non-entailed rules and prevents promotion to quarantine (`D-REAS-06`, `D-REAS-07`).
- **Pass Threshold:** $100\%$ rejection of non-entailed rule candidates.
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_d_reas_07_negative.py -v
  ```

---

### Plane 4: Real-Time Audio, Concurrency & Emergency Reflexes
*Source Files: `src/lucca/speech/`, `src/lucca/core/orchestrator.py`, `src/lucca/core/ipc_schemas.py`*

#### Test 4.1: Emergency Words REFLEX Latency & Fast-Path
- **Real-World Threat:** User shouts an emergency command (e.g. *"STOP"*, *"HALT"*), but companion waits for LLM decoding to finish.
- **Pass Threshold:** Emergency patterns trigger immediate REFLEX bypass with latency $< 150\text{ ms}$ (`D-ARCH-05`).
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_emergency_reflex.py -v
  ```

#### Test 4.2: ZeroMQ Wire Framing & Codec Property Fuzzing (P-08)
- **Real-World Threat:** Corrupted IPC frames, oversized payloads, or truncated buffers cause process crash across the native ZeroMQ boundary.
- **Capability-Proving Stress Test:**
  - Hypothesis property testing across `Envelope` encoding/decoding, 1 MiB max frame limits, and malformed binary headers.
- **Pass Threshold:** $100\%$ detection of truncated/corrupt frames; zero unhandled deserialization crashes.
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_ipc_codec.py -v
  ```

---

### Plane 5: Cognitive Individuation & Epistemic Boundaries
*Source Files: `tests/test_contrastive_live_hw.py`, `tests/test_a1_live_hw.py`, `src/lucca/reasoning/stats.py`*

#### Test 5.1: Live Contrastive Companion Battery (P9 Remediation)
- **Real-World Threat:** A bare LLM confabulates prior actions, hallucinates nonexistent tools, and capitulates to user gaslighting.
- **Capability-Proving Stress Test:**
  - Run the SAME 30 probes through Arm A (bare Gemma-4 12B) and Arm B (Compound Lucca pipeline) with frozen mechanical grader (`grader_sha256`).
- **Pass Thresholds:**
  - **Recall:** Arm B $\ge 80.0\%$ (Arm A contrast $\approx 0\%$)
  - **Receipt Introspection:** Arm B $\ge 80.0\%$ (grounded in signed receipts)
  - **Abstention:** Arm B $\ge 80.0\%$ (refusal on unanswerable/out-of-domain probes)
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_contrastive_live_hw.py -m hw -v
  ```

#### Test 5.2: 60-Probe Introspective Accuracy & Stance Consistency (A1)
- **Real-World Threat:** Long-term memory drift and sycophancy when challenged over multiple turns.
- **Pass Threshold:** 60-probe composite Wilson 95% Lower Bound $\ge 0.80$ ($\ge 54/60$ passes).
- **Authoritative Command:**
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_a1_live_hw.py -m hw -k "test_live_a1_introspective_accuracy" -v
  ```

---

## 3. Master Audit Execution Runbook (100% Executable Commands)

### Phase 1: Static Architecture & Typing Invariants (10 s)
```powershell
.venv\Scripts\python.exe -m pytest tests/test_static_gates.py -v
```
*Exit Gate:* Exactly **24 passed**. Zero-Any violation count $= 0$.

### Phase 2: Deterministic Defense & Fuzzing (15 s)
```powershell
.venv\Scripts\python.exe -m pytest tests/test_memory_hmac_tamper.py tests/test_wo33_git_dag_and_belnap.py tests/test_d_reas_06_negative.py tests/test_d_reas_07_negative.py tests/test_ipc_codec.py -v
```
*Exit Gate:* $100\%$ passed. Zero quarantine bypasses, gas properly capped, Belnap contradiction sound.

### Phase 3: Adversarial Supervision & State Fault Injection (15 s)
```powershell
.venv\Scripts\python.exe -m pytest tests/test_truth_in_receipt_battery.py tests/test_spike_a_grammar_supervision.py tests/test_fault_injecting_sandbox.py tests/test_emergency_reflex.py -v
```
*Exit Gate:* Exactly **158 passed** across the four suites. 0% escape on adversarial phrasings.

### Phase 4: Live Hardware Cognitive Batteries (RTX 5080 GPU, ~20 min)
```powershell
.venv\Scripts\python.exe -m pytest tests/test_contrastive_live_hw.py -m hw -v --tb=short
```
*Exit Gate:* 30/30 probes graded with matching `grader_sha256`. Arm B clears Recall ($\ge 80\%$), Introspection ($\ge 80\%$), Abstention ($\ge 80\%$).

### Phase 5: Academic Held-Out Benchmarks (Multi-Hour)
```powershell
# MATH-500 Held-Out PAL-Off Ablation Protocol
.venv\Scripts\python.exe scripts/run_pal_off_ablation.py --model gemma-4-12b --dataset math500_heldout100

# Canonical HumanEval Paired Evaluation Protocol
.venv\Scripts\python.exe scripts/run_humaneval_canonical_paired.py
```
*Exit Gate:* Artifacts written with clean git tree hash committed in `data/benchmarks/MANIFEST.yaml`.

---

## 4. Final Audit Sign-Off Checklist

- [ ] **Static Verification:** 24/24 static gates pass; `Zero-Any` strictly 0.
- [ ] **Cryptographic Integrity:** 11/11 HMAC tamper gates pass; zero tampered rows admitted.
- [ ] **Belnap Lattice:** 14/14 tests pass; direct contradiction strictly maps to $\top$.
- [ ] **Output Supervision:** 73/73 grammar supervision tests pass; latency $p99 \le 1.0\text{ ms}$.
- [ ] **Emergency Reflex:** Emergency words trigger in $< 150\text{ ms}$ bypassing LLM decoding.
- [ ] **Cognitive Grounding:** P9 contrastive battery passes with frozen `grader_sha256`.
- [ ] **Academic Integrity:** Zero post-hoc regrades; all manifest records map to committed artifacts.
