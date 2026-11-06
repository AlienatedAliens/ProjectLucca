# Project Lucca — Threat Model and Security Architecture

**Document Version:** 1.48.0 (`WO-42`)  
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
In the early regex-only prototype (`PREREG_MATCHER_SENSITIVITY.md`), `TruthInReceiptMatcher` alone detected 1 of 23 ungrounded action claims (4.3% broad sensitivity). In `WO-41`/`WO-42` (`2026-11-06`), Project Lucca added the clause-level OpenVINO FP16 `NeuralActionClaimVerifier` (`models/action_claim_verifier_ov` on Intel AI Boost NPU, `src/lucca/sandbox/neural_action_claim_verifier.py`) wired into `coherence.py`, achieving **99.26% accuracy (`2,007/2,022`), 98.73% recall (`465/471`), and 0.58% FPR (`9/1,551`)** across the `N=2,022` evaluation battery (`logs/test_reports/wo42_large_sample_2020_report.json`), **100.0% (`150/150`)** across `Blind-390` + `LOCKED_COH_050`, and **28/28 (`100.0%`)** live adversarial FAC interception across all 4 Gemma 4 tiers (`26B-A4B`, `12B`, `E4B`, `E2B` in `logs/test_reports/wo42_live_4model_100turn_report.json`). 
> **Important:** While `WO-42` raised action-claim detection recall from `4.3%` to `98.73%` (`N=2,022`), operators must still treat output supervision as one layer in a defense-in-depth stack; primary host safety rests on Docker sandbox isolation, `SequenceGuard` taint tracking, and human-in-the-loop HMAC confirmation tokens for state-mutating tools.

---

## 3. Threat Taxonomy

### 3.1 In-Scope Threats

| Threat Vector | Attack Scenario | Architectural Defense | Enforcing Test / Code Citation |
| :--- | :--- | :--- | :--- |
| **Prompt Injection via Web / OCR** | Malicious text in a scraped web page or on-screen window instructs the companion to delete files. | `sanitize_html_against_prompt_injection()` (`src/lucca/sandbox/web_tool.py`) strips CSS-hidden elements (`display:none`, `visibility:hidden`, `opacity:0`, `font-size:0`) and HTML comments before Scrapling DOM parsing. Untrusted web and visual content is tagged `TOOL_CONTENT_UNTRUSTED`. The `ProvenanceGate` strictly rejects memory writes from untrusted content, and `SequenceGuard` blocks state-mutating tools after untrusted fetches. | [`tests/test_turn_loop.py`](../../tests/test_turn_loop.py), [`src/lucca/sandbox/web_tool.py`](../../src/lucca/sandbox/web_tool.py), [`src/lucca/memory/provenance.py`](../../src/lucca/memory/provenance.py) |
| **Host Breakout via Tool Execution** | The model attempts to execute shell scripts or system binaries directly on the Windows host. | Direct host execution fallback is disabled (`use_direct_fallback=False` per `D-AUD-13`). Code runs in Docker CE in WSL2. Shell binaries (`cmd.exe`, `powershell.exe`) are blacklisted. | [`tests/test_wo37_integration.py`](../../tests/test_wo37_integration.py), [`src/lucca/sandbox/launcher.py`](../../src/lucca/sandbox/launcher.py) |
| **Long-Term Memory Poisoning** | Adversary injects fabricated facts into SQLite memory to alter future model behavior. | Every memory commit requires an authentic domain-separated HMAC-SHA256 signature from a registered signer (`UserSpeechSigner`, `ToolResultSigner`). Unsigned commits are rejected or quarantined. | [`tests/test_memory_tab.py`](../../tests/test_memory_tab.py), [`src/lucca/memory/store.py`](../../src/lucca/memory/store.py) |
| **Rule Engine Hijacking** | Induced rules attempt to perform malicious host state mutations. | Induced MicroScheme rules are locked in `QUARANTINE` mode. Automatic promotion is structurally blocked (`D-REAS-06`). Gas metering caps execution at 1,000 steps. `SkillLibrary` (`skills.py`) enforces `_check_ast_symbol_grounding` and `verify_in_shadow_sandbox`, and `DreamCoderMiner` expands macros before Z3 verification (`SMTVerifier` arithmetic/division safety). | [`tests/test_rule_induction.py`](../../tests/test_rule_induction.py), [`src/lucca/reasoning/skills.py`](../../src/lucca/reasoning/skills.py) |
| **Ungrounded Action Confabulation** | Model claims "I deleted your files" when no deletion occurred, inducing user panic. | `TruthInReceiptMatcher` + clause-level Intel NPU `NeuralActionClaimVerifier` (`src/lucca/sandbox/neural_action_claim_verifier.py`, `99.26%` accuracy on `N=2,022`, `28/28` live 4-model FAC) inspect action claims against authentic `ToolReceipt`s from the active turn and abort/self-correct ungrounded claims. `orchestrator.py` permanently removes `run_python_simulated` fake receipt minting (`WO-39`). | [`tests/test_truth_in_receipt_battery.py`](../../tests/test_truth_in_receipt_battery.py), [`src/lucca/sandbox/neural_action_claim_verifier.py`](../../src/lucca/sandbox/neural_action_claim_verifier.py) |
| **Workspace Shortcut / `.url` Escape & Unbounded Loops (`WO-39`)** | Crafted `.url` (`[InternetShortcut]`) file or `while True:` / `eval()` Python payload attempts workspace escape or resource exhaustion. | `file_tool.py` blocks `.url` / `[InternetShortcut]` files alongside `.lnk` and NTFS ADS; `ast_sanitizer.py` strips `eval`/`exec`/`compile`/`getattr` bypasses; `SpeculativeBDIValidator` (`bdi_validator.py`) enforces S-expression deontic rules, AST unbounded `while True:` loop detection, and a Z3 numeric resource bound solver. | [`src/lucca/sandbox/file_tool.py`](../../src/lucca/sandbox/file_tool.py), [`src/lucca/core/bdi_validator.py`](../../src/lucca/core/bdi_validator.py) |
| **Attributed-Speech & Null-Store Premise Laundering (`WO-39`)** | Adversary or hallucinated step formats `"<source> asserts <claim>"` to bypass premise corroboration or invokes `is_content_corroborated(None, ...)`. | `ProvenanceGate` (`gate.py`) fails closed (`is_content_corroborated(None, ...) -> False`), removes the `"<source> asserts <claim>"` regex bypass, and requires semantic/triple/NLI corroboration (`verify_rule_premises`), while `prompt_builder.py` (`_render_partitioned_memories`) isolates `grounding_eligible=0` speech under an explicit non-grounding header. | [`src/lucca/memory/gate.py`](../../src/lucca/memory/gate.py), [`src/lucca/brain/prompt_builder.py`](../../src/lucca/brain/prompt_builder.py) |

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
