# Project Lucca — Threat Model and Security Architecture

**Document Version:** 1.0.0  
**Status:** Living Canonical Specification  
**Associated Security Policy:** [`SECURITY.md`](../../SECURITY.md)  

---

## 1. System Boundary and Architectural Trust Philosophy

Project Lucca operates on a core defense-in-depth premise:

> **The Large Language Model is an untrusted cognitive component.**  
> Neural token predictions cannot be trusted with direct host execution, unrestricted memory write authority, or unverified claims of physical action.

Rather than relying on model RLHF "alignment" or conversational guardrails (which are susceptible to jailbreaking, persona hijacking, and indirect prompt injection), Lucca isolates neural generation within deterministic architectural wrappers:
1. **Sandboxed Action Execution:** State-changing commands and code run inside a persistent, isolated Docker container in Ubuntu WSL2.
2. **Cryptographic Memory Provenance:** Writes to long-term memory require domain-separated HMAC-SHA256 cryptographic envelopes. LLM self-narration cannot sign memory records.
3. **Receipt-Grounded Action Verification:** Declarative action assertions are monitored by a syntactic matcher comparing claims against authentic runtime tool receipts.
4. **Symbolic Rule Quarantine:** Dynamically induced MicroScheme LISP rules are quarantined by default and cannot execute on host state without explicit human approval.

---

## 2. Model Choice vs. Safety Architecture

### Why Uncensored Community Weights ("Heretic") Are Used
Project Lucca employs quantized community fine-tunes (`culturerevolt/gemma-4-*-heretic` / `Mistral-Nemo-Instruct-2407-abliterated`). 
- **Reasoning:** Commercial conversational models frequently refuse legitimate local administrative and systems automation requests due to over-broad conversational refusals. Uncensored weights provide consistent compliance with procedural commands.
- **Risks:** Uncensored weights will generate arbitrary text upon request, including instructions for dangerous tasks or hallucinated claims of system destruction.
- **Defense Posture:** Because the model itself has no inherent safety boundaries, **safety must be enforced structurally** by the sandboxing and provenance tiers.

### Realistic Assessment of Output Supervision
In a 23-utterance live evaluation battery (`PREREG_MATCHER_SENSITIVITY.md`), the `TruthInReceiptMatcher` detected only 1 of 23 ungrounded action claims (4.3% sensitivity broad / 1/8, 12.5% strict). 
> **Important:** Output supervision is an active research prototype and **is not yet a certified safety boundary**. Operators must not rely on output supervision alone to prevent malicious actions; safety currently rests on Docker sandbox isolation and human-in-the-loop confirmation for dangerous tools.

---

## 3. Threat Taxonomy

### 3.1 In-Scope Threats

| Threat Vector | Attack Scenario | Architectural Defense | Enforcing Test / Code Citation |
| :--- | :--- | :--- | :--- |
| **Prompt Injection via Web / OCR** | Malicious text in a scraped web page or on-screen window instructs the companion to delete files. | Untrusted web and visual content is tagged `TOOL_CONTENT_UNTRUSTED`. The `ProvenanceGate` strictly rejects memory writes from untrusted content. Tools operate under strict Pydantic schemas. | [`tests/test_turn_loop.py`](../../tests/test_turn_loop.py), [`src/lucca/memory/provenance.py`](../../src/lucca/memory/provenance.py) |
| **Host Breakout via Tool Execution** | The model attempts to execute shell scripts or system binaries directly on the Windows host. | Direct host execution fallback is disabled (`use_direct_fallback=False` per `D-AUD-13`). Code runs in Docker CE in WSL2. Shell binaries (`cmd.exe`, `powershell.exe`) are blacklisted. | [`tests/test_wo37_integration.py`](../../tests/test_wo37_integration.py), [`src/lucca/sandbox/launcher.py`](../../src/lucca/sandbox/launcher.py) |
| **Long-Term Memory Poisoning** | Adversary injects fabricated facts into SQLite memory to alter future model behavior. | Every memory commit requires an authentic domain-separated HMAC-SHA256 signature from a registered signer (`UserSpeechSigner`, `ToolResultSigner`). Unsigned commits are rejected or quarantined. | [`tests/test_memory_tab.py`](../../tests/test_memory_tab.py), [`src/lucca/memory/store.py`](../../src/lucca/memory/store.py) |
| **Rule Engine Hijacking** | Induced rules attempt to perform malicious host state mutations. | Induced MicroScheme rules are locked in `QUARANTINE` mode. Automatic promotion is structurally blocked (`D-REAS-06`). Gas metering caps execution at 1,000 steps. | [`tests/test_rule_induction.py`](../../tests/test_rule_induction.py), [`src/lucca/reasoning/rule_engine.py`](../../src/lucca/reasoning/rule_engine.py) |
| **Ungrounded Action Confabulation** | Model claims "I deleted your files" when no deletion occurred, inducing user panic. | `TruthInReceiptMatcher` inspects action verbs against authentic `ToolReceipt`s from the active turn and flags or aborts ungrounded claims. | [`tests/test_truth_in_receipt_battery.py`](../../tests/test_truth_in_receipt_battery.py) |

### 3.2 Out-of-Scope Threats

The following threats are outside the security perimeter of Project Lucca:
1. **Physical Silicon & Hardware Access:** Workstation tampering, physical cold-boot attacks on RAM, or DMA attacks via PCIe.
2. **Host OS Kernel Compromise:** Pre-existing malware running with Windows Administrator privileges or root access to WSL2.
3. **Compromised Hypervisor / Docker Daemon:** Exploits in the WSL2 Linux kernel or Docker CE daemon itself that facilitate VM breakout.
4. **Upstream Model Backdoors:** Deep Trojan weights embedded in the base Gemma 4 or ModernBERT checkpoints prior to publication.

---

## 4. Security Invariants and Verification

Every core security invariant in Project Lucca is validated by automated test suites in CI:

1. **No Host Execution Fallback (`D-AUD-13`):**
   - Direct execution on the host machine is disabled by default. If Docker CE is unavailable, sandboxed tools fail closed rather than falling back to host execution.
   - *Test:* [`tests/test_wo37_integration.py`](../../tests/test_wo37_integration.py)
2. **Strict Shell Blacklist (`D-AUD-10`):**
   - `LaunchAppArgs` explicitly rejects `cmd.exe`, `powershell.exe`, and batch scripts from being invoked via application launch tools.
   - *Test:* [`tests/test_packaging.py`](../../tests/test_packaging.py)
3. **Cryptographic Memory Envelope Verification (`D-MEM-05`):**
   - Memory facts are verified at read-time via HMAC-SHA256. Tampered records trigger alerts and are isolated into the persistent SQLite `memory_quarantine` table.
   - *Test:* [`tests/test_persistent_rpc.py`](../../tests/test_persistent_rpc.py), [`tests/test_memory_tab.py`](../../tests/test_memory_tab.py)
4. **Static Gate Zero-`Any` Invariant (`D-AUD-01`):**
   - All core, brain, reasoning, sandbox, and UI module interfaces are strictly typed with zero `Any` occurrences.
   - *Test:* [`tests/test_static_gates.py`](../../tests/test_static_gates.py)

---

## 5. Cryptographic Key Lifecycle

- **Key Generation:** A 256-bit master secret is generated via `secrets.token_bytes(32)` on initial setup.
- **Storage:** Persisted locally at `data/keys/master.key` with restricted Windows ACLs (`0600` equivalent).
- **Key Loss Behavior:** If `master.key` is deleted or rotated, existing memory rows fail HMAC-SHA256 signature verification upon read and are safely relocated to `memory_quarantine` without deleting underlying data.

---

## 6. Privacy & Sensor Data Governance

- **Microphone Audio:** Audio ring buffers are resident in host RAM. No audio frames are sent over the network. Transcription is computed entirely on local silicon (RTX 5080 via CUDA float16).
- **Screenshots & Vision:** Screen capture is on-demand via the Windows Desktop Duplication API / GDI. Text extraction uses native Windows 11 WinRT `Windows.Media.Ocr.OcrEngine` on local CPU. No images or text are transmitted externally.
- **Zero External Telemetry:** Project Lucca contains zero analytics beacons, error tracking pings, or cloud telemetry.
