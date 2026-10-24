# Library Extraction Plan: `agent-provenance-guard`

**Document Version:** 1.0.0  
**Date:** 2026-10-21  
**Target Extract:** `ProvenanceGate` + `SignerFactory` & `TruthInReceiptMatcher`  
**Proposed Package Name:** `agent-provenance-guard` (or `lucca-guard`)  
**Context:** Milestone 2 of 3-Month Grant Proposal ($6,000 budget)  
**Status:** PROPOSED ARCHITECTURAL SPECIFICATION (No repository files altered)

---

## 1. Executive Summary & Objective

A major deliverable for safety fund applications (Corrigibility Research Fund, Manifund, Mercor) is extracting Project Lucca's core runtime verification mechanisms into a lightweight, standalone, zero-bloat Python library. 

This library will enable any autonomous agent framework (e.g. LangChain, LlamaIndex, AutoGen, Claude Code, OpenHands) to enforce two non-negotiable safety properties:
1. **Provenance-Gated Memory (`ProvenanceGate`):** Enforces that LLM-generated narrations cannot confabulate memories without an authentic cryptographic HMAC-SHA256 envelope signed by an authorized domain signer (`ADR-006`).
2. **Deontic Receipt Supervision (`TruthInReceiptMatcher`):** Enforces that an agent's spoken or emitted narrations cannot claim tool actions (e.g. "I deleted your file") unless corroborated by authentic deterministic execution receipts (`ADR-010`).

---

## 2. Dependency Audit & Architectural Decoupling

Based on the repository dependency audit conducted in Part A (Question A8):

### Current In-Tree Dependencies:
- `src/lucca/sandbox/output_supervisor.py`:
  - **Internal Lucca Imports:** **Zero**. It is completely self-contained.
  - **External Dependencies:** `pydantic` (v2), `structlog`, stdlib (`re`, `typing`, `dataclasses`).
- `src/lucca/memory/gate.py` & `src/lucca/memory/signers.py`:
  - **Internal Lucca Imports:**
    - `from lucca.core.schemas import Provenance, SignedPayload, UnsignedPayload`
    - `from lucca.core.exceptions import ProvenanceError, SignatureTamperError`
  - **External Dependencies:** `cryptography` (for HKDF & HMAC-SHA256), `pydantic`, `structlog`.

### Decoupling Requirements (What Gets Cut):
- Cut all dependencies on SQLite WAL (`memory.sqlite`), `sqlite-vec`, and FTS5.
- Cut all dependencies on Docker CE / WSL2 sandbox transports.
- Cut all dependencies on MicroScheme, SymPy, and Z3 symbolic solvers.
- Cut all dependencies on ZeroMQ IPC, Faster-Whisper ASR, and Kokoro TTS.
- Bundle the standalone schemas (`SignedPayload`, `UnsignedPayload`, `Provenance`) directly into the extracted package.

### Third-Party Licenses:
All third-party dependencies carry fully permissive open-source licenses compatible with MIT/Apache-2.0 distribution:
- `cryptography`: Apache 2.0 / BSD 3-Clause
- `pydantic`: MIT
- `structlog`: MIT / Apache 2.0
- Python Standard Library: PSF License

---

## 3. Target Package Architecture & Layout

```text
agent-provenance-guard/
├── LICENSE                        # MIT License
├── README.md                      # Verification-first quickstart and API guide
├── pyproject.toml                 # uv / hatchling build specification (Python >=3.10)
├── src/
│   └── agent_guard/
│       ├── __init__.py            # Clean top-level exports
│       ├── py.typed               # PEP 561 typing marker
│       ├── exceptions.py          # ProvenanceError, VerificationFailure, TamperError
│       ├── schemas.py             # SignedPayload, UnsignedPayload, Provenance enum, ToolReceipt
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── gate.py            # ProvenanceGate (cryptographic memory barrier)
│       │   ├── signers.py         # SignerFactory, UserSpeechSigner, ToolResultSigner, etc.
│       │   └── keys.py            # HKDF master key derivation and persistence helpers
│       └── supervision/
│           ├── __init__.py
│           ├── supervisor.py      # TruthInReceiptMatcher (deontic action-claim supervisor)
│           └── verbs.py           # 21 verified action verb sets and epistemic hedge exemptions
└── tests/
    ├── conftest.py
    ├── test_gate.py               # Cryptographic tamper, envelope lifecycle, and replay tests
    ├── test_signers.py            # HKDF key separation and domain-specific signer tests
    ├── test_supervisor.py         # 73-sentence deontic action-receipt verification battery
    └── test_integration.py        # End-to-end agent interception pipeline
```

---

## 4. Public API Specification

The library will expose a clean, idiomatic interface designed for seamless middleware integration:

```python
from agent_guard import (
    ProvenanceGate,
    SignerFactory,
    Provenance,
    TruthInReceiptMatcher,
    ToolReceipt,
    SupervisorVerdict,
)

# 1. Initialize Memory Cryptographic Barrier
keys = SignerFactory.from_master_key(master_key_bytes)
gate = ProvenanceGate(master_key=master_key_bytes)

# User speech signer creates authentic envelope
user_signer = keys.user_speech()
envelope = user_signer.sign(
    content="My name is Alice",
    trace_id="trace-01J...",
)

# Provenance Gate verifies authenticity and provenance classification
is_valid = gate.verify(envelope, expected_provenance=Provenance.USER_EXPLICIT)
# Raises SignatureTamperError if payload was modified; returns False if LLM narration

# 2. Deontic Receipt Supervision
matcher = TruthInReceiptMatcher()

receipts = [
    ToolReceipt(
        tool="write_file",
        args={"path": "notes.txt"},
        ok=True,
        output="wrote 24 bytes"
    )
]

# Check agent narration against deterministic execution receipts
verdict: SupervisorVerdict = matcher.verify_narration(
    narration="I have saved your notes to notes.txt, and deleted your backup.",
    receipts=receipts,
)

if not verdict.is_valid:
    print(f"Action Hallucination Blocked: {verdict.unsupported_claims}")
    # Output: ['deleted your backup']
```

---

## 5. Test Suite Migration

All extracted functionality is already backed by existing regression suites in Project Lucca. The test migration involves:

1. **Gate & Cryptographic Signers:**
   - Migrate `tests/test_provenance.py` and `tests/test_tamper_envelope.py`.
   - Tests verify: HKDF key separation across domains, HMAC-SHA256 integrity, tamper detection on payload mutations, nonce freshness, and strict rejection of unsigned or improperly signed envelopes (`LLM_NARRATION`, `TOOL_CONTENT_UNTRUSTED`).
2. **Receipt Supervisor:**
   - Migrate `tests/test_truth_in_receipt_battery.py` (73 tests).
   - Tests verify: 21 action verb families, past-context recollective exemptions, epistemic hedges ("I think I deleted"), and live control sentences (0 false positives).
3. **Execution Environment:**
   - The standalone test suite will require **no GPU, no local LLM server, and no Docker container**.
   - Entire suite executes in **<1.5 seconds** via `pytest`.

---

## 6. Implementation Steps & Hourly Work Breakdown

| Step | Task Description | Concrete Deliverables | Estimated Hours |
| :--- | :--- | :--- | :--- |
| **Phase 1: Scaffolding** | Create repository, `pyproject.toml`, CI/CD workflow (GitHub Actions with lint/type/test matrix). | Standalone repo, `uv.lock`, CI matrix (Python 3.10–3.13) | 4 hours |
| **Phase 2: Schemas & Cryptography** | Port `schemas.py`, `exceptions.py`, `signers.py`, and `gate.py`. Bundle HKDF key derivation utilities. | Pure cryptographic memory gate module | 6 hours |
| **Phase 3: Receipt Supervisor** | Port `output_supervisor.py` into `supervision/supervisor.py` and modularize `verbs.py`. | Self-contained regex & AST deontic receipt supervisor | 6 hours |
| **Phase 4: Test Suite Porting** | Port and adapt all 73 receipt tests and provenance unit tests. Add property-based testing (`hypothesis`). | 100% green test suite (~120 tests), 0 `Any` typing | 8 hours |
| **Phase 5: Framework Adapters** | Implement lightweight middleware hooks for LangChain and OpenAI/Anthropic client wrappers. | `agent_guard.adapters.langchain`, `agent_guard.adapters.openai` | 8 hours |
| **Phase 6: Documentation & Examples** | Author verification-focused documentation, threat model, API reference, and 3 runnable examples. | `README.md`, `luccadocs/THREAT_MODEL.md`, `examples/` | 6 hours |
| **Total Effort** | | | **38 hours (~1 week full-time)** |

---

## 7. Budget & Grant Milestones Alignment

In the context of the **$6,000 / 3-month grant request**:
- **Month 1:** Pre-registration and live re-measurement of receipt matcher sensitivity (Work Packages B3 & B4).
- **Month 2 (This Plan):** Extraction and public release of `agent-provenance-guard` on PyPI with full test suite, documentation, and adapter hooks. (38 hours).
- **Month 3:** Remediation of NLI verifier fail-open vulnerabilities (Work Package B5) and integration of INT8/NPU acceleration.
