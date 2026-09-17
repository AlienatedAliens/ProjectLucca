# ADR-006 — Provenance: two-tier user provenance, content/structure split for tools, per-provenance capability signers

**Status:** Accepted 2026-09-17 (D-11). Preserves AGENTS.md invariant #1 unchanged (`LLM_NARRATION` never enters memory).
**Supersedes:** `src/lucca/memory/provenance_gate.py` single-key HMAC design; doc 05 "cryptographically signed / mathematically prevents" wording.

## Context

Review findings on the current gate:

1. The same object signs and verifies with one key; any code that can call `create_verified_payload` can assert any provenance. The HMAC therefore protects against nothing inside the process — the real hazard is a *developer* wiring LLM text into a trusted path.
2. Signature covers `content:provenance:timestamp` joined by `:` — ambiguous canonicalisation; `entry_id`, `entities`, `confidence` are unsigned and mutable after signing; no freshness check; default key `insecure_dev_key`.
3. Semantics gap: Ultravox emits no transcript, so `USER_EXPLICIT` text must come from Whisper (with a WER); and "facts" extracted from speech ("my sister is Maya" → `(user, has_sister, Maya)`) are **LLM output**, not user speech.
4. `TOOL_VERIFIED` was applied to fetched page text, so a malicious page could plant "verified" memories (indirect prompt injection).

## Decision

### Provenance vocabulary (closed enum)

| Provenance | Meaning | Memory-eligible? | Trust weight |
|---|---|---|---|
| `USER_EXPLICIT` | Verbatim Whisper transcript span of the user's speech; carries `audio_sha256`, `asr_avg_logprob`, `asr_model`. | Yes, if `asr_avg_logprob ≥ −0.5` (else `USER_EXPLICIT_LOWCONF`). | 1.0 |
| `USER_EXPLICIT_LOWCONF` | Same, low ASR confidence. | Only after user confirms the read-back. | — |
| `USER_DERIVED` | Structure (triple / attribute) extracted by the LLM **from a `USER_EXPLICIT` entry**, passing quote-grounding (below). References `source_entry_id`. | Yes. | 0.8 |
| `TOOL_VERIFIED` | Structural facts of a tool execution: exit code, path exists, size, sha256, HTTP status, duration. | Yes. | 1.0 |
| `TOOL_CONTENT_UNTRUSTED` | Bodies: file text, page text, command stdout. | **No**, unless user confirms a specific extracted statement → becomes `USER_DERIVED` with `source_entry_id` of the tool result. | — |
| `LISP_ASSERTION` | Output of an **active** (promoted) rule's plan execution result. | Yes. | 0.9 |
| `LLM_NARRATION` | Anything the LLM says that is not one of the above. | **Never.** Rejected by the gate, logged. | 0 |

### Quote-grounding (mechanical check for `USER_DERIVED`)

For each string-valued field in the derived structure (subject/object surface forms, attribute values): `normalise(field) ∈ normalise(source_transcript)` as substring **or** `rapidfuzz.partial_ratio ≥ 90`. Predicates are drawn from a closed predicate list (spec 04). Fail → reject with `GroundingError`, never silently degrade.

### Capability signers

```python
class ProvenanceSigner(Protocol):           # one concrete class per provenance
    provenance: Final[Provenance]
    def sign(self, payload: UnsignedPayload) -> SignedPayload: ...

class UserSpeechSigner(ProvenanceSigner): ...   # constructed ONLY in lucca.senses.asr
class ToolResultSigner(ProvenanceSigner): ...   # constructed ONLY in lucca.sandbox.client (host side)
class LispAssertionSigner(ProvenanceSigner): ...# constructed ONLY in lucca.reasoning.executor
```

- Keys: `HKDF-SHA256(master_key, info=b"lucca/provenance/" + provenance.name)`. Master key from `config\.env` `LUCCA_MASTER_KEY` (32 random bytes, base64). Startup **fails closed** if unset or equal to any known dev default unless `LUCCA_ENV=dev`.
- Signature covers **canonical JSON** (`sort_keys=True, separators=(',',':'), ensure_ascii=False`) of every payload field except `signature`. Payload includes `nonce` (16 random bytes) and `created_at`; gate rejects `now − created_at > 300 s` and duplicate `(nonce, content_sha256)` within 24 h.
- The gate (`lucca.memory.gate`) holds **verification keys only**, derived from the same master; it verifies against the key for the *claimed* provenance.
- `lucca.brain.*` (LLM client, prompt builder, reflection) **imports no signer**. Enforced by `import-linter` contract `forbidden: lucca.brain -> lucca.memory.signers` and by an AST test that lists every module constructing a signer and asserts it equals the allow-list above.
- The sandbox container never sees any key; `ToolResultSigner` runs on the host after the response is schema-validated.

### Wording

Docs must say: "provenance is enforced by **type- and module-level capability discipline**, with HMAC signatures as tamper-evidence across process and storage boundaries". Remove "mathematically prevents".

## Consequences

- Hallucination-write protection becomes structural (who can construct what) and testable statically, rather than a claim about HMAC.
- Memory extraction becomes explicitly a two-step pipeline: transcript stored verbatim (always), structure derived and grounded (sometimes).
- Web content can be summarised and discussed but cannot become memory without a user act.
- Slight increase in ceremony: three signer classes, one gate, one master key.

## Alternatives

| Option | Why not |
|---|---|
| Keep single HMAC | Provides no in-process boundary; misleading claims. |
| Asymmetric signatures (Ed25519) per source | Only valuable when verifier and signer are different trust domains (e.g. a remote tool host). Not needed now; the `Protocol` allows it later. |
| No signatures at all, capability typing only | Loses tamper-evidence for rows at rest and across the ZMQ boundary; cheap to keep. |
