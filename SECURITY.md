# Security Policy

## 1. Reporting a Vulnerability

Project Lucca is an autonomous, sandboxed desktop companion that treats neural models as untrusted components. We welcome vulnerability disclosures regarding sandbox breakouts, unauthorized host execution, memory poisoning, or supervisory bypasses.

Please report security vulnerabilities directly to the project author:
- **Contact:** Sean Maxwell
- **Email:** `seatr@users.noreply.github.com` (or open a private security advisory on GitHub if available)
- **Response Target:** We aim to acknowledge reports within 48 hours and provide a patch or mitigation within 14 days.

Please **do not** report security vulnerabilities through public GitHub issues.

---

## 2. Threat Model and Scope

For a comprehensive definition of security boundaries, in-scope threat vectors, out-of-scope scenarios, and test-verified defenses, see:

👉 **[`luccadocs/security/THREAT_MODEL.md`](./luccadocs/security/THREAT_MODEL.md)**

### In-Scope Security Vectors
- **Sandbox Escape:** Bypassing Docker container isolation to execute arbitrary code or commands on the host operating system.
- **Shell Blacklist Bypass:** Circumventing the blacklist (`cmd.exe`, `powershell.exe`) in application launch dispatches.
- **Memory Poisoning:** Injecting forged facts or malicious rules into long-term SQLite memory without authorized HMAC cryptographic envelope signatures.
- **Rule Quarantine Bypass:** Forcing induced MicroScheme LISP rules from `QUARANTINE` mode into `ACTIVE` without operator approval.
- **Prompt Injection:** Indirect prompt injection through screen OCR (`extract_ocr_from_image`) or web content (`fetch_url`) triggering stateful or ungrounded actions.

### Out-of-Scope Security Vectors
- Root/Administrator compromise of the host Windows operating system or WSL2 kernel.
- Physical theft or physical hardware tampering with workstation silicon or RAM.
- Flaws in upstream NVIDIA GPU drivers, Intel NPU drivers, or Windows DWM.
