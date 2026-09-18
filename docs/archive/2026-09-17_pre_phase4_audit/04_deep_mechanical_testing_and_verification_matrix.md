# Project Lucca — Deep Mechanical Testing & Verification Matrix
**Document ID:** `TEST-VERIFY-004`  
**Revision:** 3.0  
**Classification:** Enterprise Quality Assurance & Verification Standard  

---

## 1. Testing Philosophy & Rigor Standard

Project Lucca mandates **deep mechanical testing** rather than superficial pass/fail checks. A module is not accepted merely because it executes without raising an unhandled exception. It must be subjected to:
1. **Mathematical Invariant Verification:** Concrete calibration, error bounds, and coverage proofs.
2. **Stress & Jitter Testing:** High concurrency, memory pressure, and long-horizon endurance.
3. **Adversarial Penetration Testing:** Deliberate injection of hallucinations, path traversal mutations, and infinite loops.
4. **Automated Regression Gates:** Zero-tolerance regression suites for symbolic rules and routing accuracy.

---

## 2. Quantitative Verification Metrics & Formulations

### 2.1 Expected Calibration Error (ECE) & Brier Score
For the Phase 6 router, probabilities must reflect true empirical accuracy.

#### Expected Calibration Error (ECE)
Divide predicted probabilities into $M = 10$ equally spaced bins $B_1, B_2, \dots, B_M \subset [0, 1]$:
$$\text{ECE} = \sum_{m=1}^M \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
where:
* $\text{acc}(B_m) = \frac{1}{|B_m|} \sum_{i \in B_m} \mathbf{1}(y_i = \hat{y}_i)$
* $\text{conf}(B_m) = \frac{1}{|B_m|} \sum_{i \in B_m} \hat{P}(y_i = \hat{y}_i \mid x_i)$
* **Acceptance Threshold:** $\mathbf{\text{ECE} \le 0.045}$ (under 4.5% calibration error across all bins).

#### Multi-Class Brier Score
$$\text{BS} = \frac{1}{N} \sum_{i=1}^N \sum_{k=1}^K (f_{ik} - y_{ik})^2$$
where $f_{ik}$ is the calibrated predicted probability for class $k$, and $y_{ik} \in \{0, 1\}$.
* **Acceptance Threshold:** $\mathbf{\text{BS} \le 0.12}$ on held-out test data.

---

### 2.2 Hybrid Retrieval Evaluation (Reciprocal Rank Fusion)
To verify that hybrid dense + sparse search outperforms pure cosine similarity:
$$\text{RRF}(d) = \frac{1}{60 + \text{rank}_{dense}(d)} + \frac{1}{60 + \text{rank}_{sparse}(d)}$$
* **Metric:** Mean Reciprocal Rank (MRR) and Hit@1 on 30 test queries containing literal identifiers (error codes, file paths, UUIDs, function names).
* **Acceptance Criteria:**
  $$\mathbf{\text{MRR}_{hybrid} \ge \text{MRR}_{cosine} + 0.20}$$
  $$\mathbf{\text{Hit@1}_{hybrid} = 1.00} \quad (\text{on literal identifier benchmark})$$

---

### 2.3 Inductive Conformal Prediction Coverage
For a chosen user risk level $\alpha = 0.05$ (target: 95% coverage):
$$\text{Empirical Coverage} = \frac{1}{N_{test}} \sum_{i=1}^{N_{test}} \mathbf{1}(y_i \in C(x_i))$$
* **Acceptance Threshold:**
  $$\mathbf{\text{Empirical Coverage} \ge 1 - \alpha - \frac{1}{\sqrt{N_{test}}}}$$
  $$\mathbf{\text{Average Set Size } \mathbb{E}[|C(X)|] \le 1.15}$$

---

### 2.4 Reflection Apply Rate Telemetry
$$\text{Effective Apply Rate} = \frac{\text{Promoted Validated Rules}}{\text{Triggered Reflection Runs}}$$
* **Thresholds:**
  * $\text{Apply Rate} \ge 0.08$ $\implies$ **HEALTHY**
  * $0.02 \le \text{Apply Rate} < 0.08$ $\implies$ **DEGRADED (Alert Logged)**
  * $\text{Apply Rate} < 0.02$ across 50 runs $\implies$ **CRITICAL FAILURE (System flags reflection prompt drift)**

---

## 3. Automated Test Suites & Stress Harnesses

### TEST SUITE 1: End-to-End Voice Latency & Audio Stability (Phase 1)
```python
import time
import numpy as np
import pytest


class TestVoiceLatencyHarness:
    """Rigorous 20-utterance latency & stability harness."""

    def test_end_to_end_latency_distribution(self, audio_pipeline):
        latencies = []
        vram_readings = []

        for i in range(20):
            # 1. Inject real recorded utterance PCM
            pcm_buffer = load_test_audio_sample(f"sample_{i % 5}.wav")

            # Start timer at the exact microsecond of hotkey release
            t_release = time.perf_counter()

            # Stream into pipeline and record arrival of first audio buffer
            first_audio_frame = audio_pipeline.process_utterance(pcm_buffer)
            t_playback_start = time.perf_counter()

            latency_ms = (t_playback_start - t_release) * 1000.0
            latencies.append(latency_ms)

            # Record VRAM usage via NVML
            vram_mb = get_gpu_vram_usage_mb()
            vram_readings.append(vram_mb)

            # Verify no audio glitches (DC offset or clipping)
            assert not np.isnan(first_audio_frame).any()
            assert np.max(np.abs(first_audio_frame)) <= 1.0

            time.sleep(0.5)

        median_latency = np.median(latencies)
        p95_latency = np.percentile(latencies, 95)
        max_vram = np.max(vram_readings)

        print(
            f"\n[LATENCY REPORT] Median: {median_latency:.1f}ms, P95: {p95_latency:.1f}ms, Max VRAM: {max_vram}MB"
        )

        # Hard Acceptance Thresholds
        assert 300.0 <= median_latency <= 600.0, (
            f"Median latency {median_latency}ms failed 300-600ms range!"
        )
        assert max_vram <= 9800, f"VRAM {max_vram}MB exceeded 9.8GB safety ceiling!"
```

---

### TEST SUITE 2: Sandbox Security & Penetration Testing (Phase 2)

#### 1. Path-Traversal Mutation Fuzzing
```python
@pytest.mark.parametrize(
    "malicious_path",
    [
        "../../etc/passwd",
        "..%2f..%2fetc%2fshadow",
        "/etc/shadow",
        "workspace/../../../Windows/System32/cmd.exe",
        "symlink_to_root/etc/hosts",
        "foo/bar/../../../../../../../../../../windows/win.ini",
        "nul",
        "com1",
        "\\\\?\\C:\\Windows",
    ],
)
def test_path_traversal_rejection(sandbox_file_tool, malicious_path):
    """Verifies that all path mutations are strictly rejected."""
    with pytest.raises(PermissionError) as exc_info:
        sandbox_file_tool.read_file(malicious_path)
    assert "escapes workspace sandbox" in str(exc_info.value) or "Access denied" in str(
        exc_info.value
    )
```

#### 2. Network Isolation Egress Probe
```python
def test_local_subnet_egress_blocked(docker_sandbox):
    """Executes network probes inside container against forbidden subnets."""
    forbidden_targets = [
        "192.168.1.1",  # Typical router gateway
        "192.168.0.1",
        "10.0.0.1",
        "172.17.0.1",  # Docker default gateway
        "169.254.169.254",  # Cloud metadata endpoint
    ]
    for target in forbidden_targets:
        cmd = f"curl --connect-timeout 2 http://{target}/"
        exit_code, output = docker_sandbox.exec_run(cmd)
        assert exit_code != 0, (
            f"CRITICAL SECURITY FAILURE: Container reached internal host IP {target}!"
        )
```

#### 3. Ephemeral Workspace vs. Persistent Volume Invariant
```python
def test_volume_persistence_and_ephemeral_reset(docker_sandbox_manager):
    # 1. Write file to ephemeral workspace and persistent volume
    docker_sandbox_manager.exec("echo 'ephemeral_data' > /workspace/temp.txt")
    docker_sandbox_manager.exec("echo 'persistent_data' > /data/persist/state.txt")
    
    # 2. Hard kill and recreate the container
    docker_sandbox_manager.hard_kill_and_recreate()
    
    # 3. Assert ephemeral file is gone, persistent file is intact
    assert not docker_sandbox_manager.file_exists("/workspace/temp.txt")
    assert docker_sandbox_manager.read_file("/data/persist/state.txt").strip() == "persistent_data"
```

---

### TEST SUITE 3: Memory Provenance & Hallucination Rejection (Phase 3)

```python
def test_hallucination_write_rejection_gate(memory_subsystem):
    """Feed plausible but false LLM narration and assert zero memory leakage."""

    # 1. Simulate unverified LLM narrative text
    hallucinated_statement = "The user has 4 cats named Apollo, Zeus, Athena, and Thor."

    # Commit attempt without verified provenance envelope
    with pytest.raises(SecurityException) as exc_info:
        memory_subsystem.commit_entry(
            content=hallucinated_statement,
            provenance_tag=MemoryProvenance.LLM_NARRATION,  # FORBIDDEN
            confidence=0.99,
        )
    assert "Unverified LLM narration cannot be committed to long-term memory" in str(exc_info.value)

    # 2. Query memory to prove it was not committed
    search_results = memory_subsystem.hybrid_search("How many cats do I have?")
    for res in search_results:
        assert "Apollo" not in res.content
```

---

### TEST SUITE 4: LISP Rule Promotion Gate & Regression Suite (Phase 5)

```python
def test_five_strike_rule_promotion_and_demotion(lisp_engine, test_database):
    candidate_rule = """
    (rule (name "auto-cleanup")
          (pattern (intent "cleanup_temp"))
          (action (call-tool "fs_clean_temp" (dict "dir" "temp"))))
    """

    # 1. Register candidate rule in quarantine
    rule_id = lisp_engine.register_quarantine_rule(candidate_rule)
    assert not lisp_engine.is_active_rule(rule_id)

    # 2. Simulate 4 successful distinct evaluations (must NOT promote)
    for i in range(4):
        lisp_engine.record_rule_shadow_evaluation(rule_id, success=True, session_id=f"sess_{i}")
        assert not lisp_engine.is_active_rule(rule_id), f"Premature promotion at strike {i + 1}!"

    # 3. 5th success -> Must trigger promotion
    lisp_engine.record_rule_shadow_evaluation(rule_id, success=True, session_id="sess_4")
    assert lisp_engine.is_active_rule(rule_id), "Rule failed to promote after 5 distinct successes!"

    # 4. Inject 1 contradictory failure -> Immediate demotion
    lisp_engine.record_live_rule_outcome(rule_id, success=False, error="User cancelled action")
    assert not lisp_engine.is_active_rule(rule_id), "Rule was not demoted immediately upon failure!"
```

---

### TEST SUITE 5: Calibrated Classifier vs. Heuristic Benchmark (Phase 6)

```python
def test_classifier_benchmark_and_calibration(trained_router, heuristic_router, held_out_test_set):
    X_test, y_test = held_out_test_set

    # 1. Evaluate Heuristic Accuracy
    heuristic_preds = [heuristic_router.predict(x) for x in X_test]
    heuristic_acc = np.mean(np.array(heuristic_preds) == y_test)

    # 2. Evaluate Calibrated ML Router Accuracy
    ml_preds = [trained_router.predict(x) for x in X_test]
    ml_acc = np.mean(np.array(ml_preds) == y_test)

    # 3. Compute Calibration Metrics
    probabilities = np.array([trained_router.predict_proba(x) for x in X_test])
    ece = compute_expected_calibration_error(probabilities, y_test, num_bins=10)
    brier = compute_brier_score(probabilities, y_test)

    print(
        f"\n[BENCHMARK] Heuristic: {heuristic_acc * 100:.2f}%, ML: {ml_acc * 100:.2f}%, ECE: {ece:.4f}, Brier: {brier:.4f}"
    )

    # Acceptance Gates
    assert ml_acc >= heuristic_acc + 0.02, (
        f"ML Router ({ml_acc}) must beat Heuristic ({heuristic_acc}) by at least 2%!"
    )
    assert ece <= 0.045, f"ECE {ece:.4f} exceeded 0.045 threshold!"
    assert brier <= 0.12, f"Brier score {brier:.4f} exceeded 0.12 threshold!"
```
