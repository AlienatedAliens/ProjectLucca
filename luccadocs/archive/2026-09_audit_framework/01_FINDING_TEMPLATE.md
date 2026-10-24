# 01 — Finding Template

Every finding in `luccadocs/audit/findings/*.md` **must** use the block below verbatim: same field names, same order, no fields omitted. Fields that genuinely do not apply are filled with `None — <one-line reason>`, never left blank or deleted.

Rules that govern the template are in [`00_AUDIT_CHARTER.md`](00_AUDIT_CHARTER.md) §3–§7. Key constraints repeated here for the author:

- **ID** format: `F-<AREA>-<NNN>`; `AREA` ∈ `CORE`, `BRAIN`, `MEM`, `REAS`, `ROUT`, `SBX`, `SENS`, `UI`, `TEST`, `DRIFT`, `ARCH`; `NNN` is zero-padded and unique within the area file.
- **Severity** ∈ `S0`, `S1`, `S2`, `S3`, `S4` (Charter §4).
- **Category** — exactly one of `INVARIANT`, `CORRECTNESS`, `SECURITY`, `PERFORMANCE`, `RELIABILITY`, `TESTING`, `SPEC-DRIFT`, `ASSUMPTION`, `INCOMPLETE`, `MAINTAINABILITY`, `UX`, `DOCS` (Charter §6).
- **Location** — `path:line` or `path:start-end`; multiple ranges separated by `;`. Paths are repo-relative. If the evidence is an artefact rather than code, put the artefact path here too.
- **Evidence** — verbatim excerpt(s) in a fenced code block, or an artefact path under `luccadocs/audit/evidence/`. Paraphrase is not evidence. "Appears to" without evidence is disallowed (Charter §3.4).
- **Proposed remediation** — numbered, atomic steps a weaker model (target: GLM 5.3 Flash) can execute **without judgement calls**. Each step names the exact file, the exact function/class/constant, what the behaviour is *before* and what it must be *after*. If a step needs a decision, the decision is made here, in the finding — not deferred to the implementer.
- **Verification test** — mechanical: concrete input, concrete expected output, explicit threshold (if numeric), and tier `T0` / `T1` / `T2` / `T3`. A verification that requires a human to "look and see" is not acceptable below S4.
- **Status** — new findings are `DRAFT` until re-reviewed per Charter §3.5, then `OPEN`. Later programmes may move to `ACCEPTED`, `REJECTED`, `FIXED`, `VERIFIED`; the audit itself only produces `OPEN`.

---

## Template (copy from the next line to the closing rule)

```markdown
### F-<AREA>-<NNN> — <Title: one line, states the defect, not the fix>

| Field | Value |
|---|---|
| **ID** | F-<AREA>-<NNN> |
| **Title** | <same as heading> |
| **Severity** | S<0-4> — <Critical / High / Medium / Low / Info> |
| **Category** | <ONE of: INVARIANT / CORRECTNESS / SECURITY / PERFORMANCE / RELIABILITY / TESTING / SPEC-DRIFT / ASSUMPTION / INCOMPLETE / MAINTAINABILITY / UX / DOCS> |
| **Location** | `<repo-relative/path.py>:<start>-<end>`; `<second/path.py>:<line>` |
| **Status** | OPEN |

**Evidence**

`<repo-relative/path.py>:<start>-<end>`
```python
<verbatim excerpt — copied, not retyped; keep original indentation>
```
<and/or> Artefact: `luccadocs/audit/evidence/<artefact-file>` (registered in 02_EVIDENCE_INDEX.md, row <n>)

**What is wrong / assumed / missing**

<Plain statement of the defect, the unverified assumption, or the gap. One defect only. Describe observed behaviour, then expected behaviour.>

**Why it matters**

<Link to the thing this threatens: Charter §5 invariant number, archived spec section (path under luccadocs/archive/…), threat-model item, hardware-truth row, or user-facing consequence. State the concrete consequence, e.g. "untrusted page body can be committed as USER_DERIVED", "WSL2 exceeds 4.5 GB under X", "test passes without exercising Y".>

**Questions this raises**

1. <Explicit question the auditor could not answer from the code/evidence>
2. <…>
(Write `None — <reason>` if there are genuinely none.)

**Proposed remediation**

1. In `<path>`, function `<name>()`: <exact change>. Before: <behaviour>. After: <behaviour>.
2. In `<path>`, <exact change>. Before: <…>. After: <…>.
3. Add/modify test `<tests/path.py>::<test_name>` so that <exact assertion>.
(Each step is atomic and needs no interpretation. If a constant is introduced, give its name, value, and location. If a decision is needed, make it here and say why.)

**Verification test**

- **Tier:** T<0-3>
- **Input:** <exact input, fixture path, or command>
- **Expected output:** <exact output / assertion>
- **Threshold:** <numeric threshold with unit, or `n/a — boolean`>
- **Command:** `<exact command line, e.g. uv run pytest tests/test_x.py::test_y -q>`

**Cross-references:** <F-IDs of related findings, or `None`>

---
```

## Worked example (illustrative only — not a real finding)

```markdown
### F-MEM-000 — Example: gate accepts a tier that has no registered signer

| Field | Value |
|---|---|
| **ID** | F-MEM-000 |
| **Title** | Example: gate accepts a tier that has no registered signer |
| **Severity** | S0 — Critical |
| **Category** | INVARIANT |
| **Location** | `src/lucca/memory/gate.py:40-52` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/gate.py:40-52`
```python
<verbatim excerpt would go here>
```

**What is wrong / assumed / missing**

The gate checks `tier in ALLOWED_TIERS` but does not verify a signature exists for the tier; a caller can pass an `LLM_NARRATION` record with a forged tier label.

**Why it matters**

Charter §5 invariant 1 (no freeform LLM narration into memory). ADR-006 (archived) requires per-provenance signers with no signer for `LLM_NARRATION`.

**Questions this raises**

1. Is there any caller today that constructs a record with a tier label but without going through a signer?

**Proposed remediation**

1. In `src/lucca/memory/gate.py`, function `ProvenanceGate.admit()`: after the tier check, call `verify_signature(record)` and reject on failure. Before: tier label alone admits. After: tier label AND valid signature required.
2. Add `tests/test_provenance.py::test_gate_rejects_unsigned_record_with_valid_tier`: construct a record with tier `USER_EXPLICIT` and no signature; assert `admit()` raises `ProvenanceRejected`.

**Verification test**

- **Tier:** T1
- **Input:** record `{tier: USER_EXPLICIT, signature: None, text: "x"}`
- **Expected output:** `ProvenanceRejected` raised; no row inserted
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_provenance.py::test_gate_rejects_unsigned_record_with_valid_tier -q`

**Cross-references:** None

---
```
