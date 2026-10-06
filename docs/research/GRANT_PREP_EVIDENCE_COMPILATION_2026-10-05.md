# Grant-Prep Evidence Compilation — AST Safety & Tool Sandboxing (2026-10-05)

```yaml
doc_status: canonical
as_of: 2026-10-05
supersedes: []
superseded_by: []
verification: code-cited
```

**Purpose:** Compile the existing, verifiable evidence base for a Manifund
application in the **AST safety & tool sandboxing** space, record the
application sequencing decision, and register the two SPIKE proposals. Every
claim below cites its implementing file, test, or ratified ADR — per `D-DOC-01`,
nothing here is aspirational without a work order attached.

---

## 1. Evidence base (what already exists and is verified)

### 1.1 Execution containment

| Control | Mechanism | Receipt |
|---|---|---|
| All tool execution sandboxed | Docker CE inside Ubuntu WSL2; direct host execution fallback **disabled by default** | `D-AUD-13`; `src/lucca/sandbox/` |
| Network isolation for file ops | `--network none` on file-sandbox containers | `docker/file-sandbox/Dockerfile`; user guide §1.1 |
| Shell ban on app launching | `cmd.exe` / `powershell.exe` strictly blacklisted from application launching | `D-AUD-10` |
| Exfiltration prevention | SequenceGuard egress blocks are absolute — no human or internal confirmation can override | `D-SEC` confirmation family; `docs/ARCHITECTURE.md` §SequenceGuard |
| Confirmation provenance split | Internal `confirmed` cannot override sequence blocks; only explicit human grant (`human_confirmed`) can, and only for single-turn blocks | `docs/ARCHITECTURE.md` §Confirmation Provenance Split |
| Fault-injection testing | `FaultInjectingSandbox` with 3 distinct modes used in the test battery | `tests/test_fault_injecting_sandbox.py` |

### 1.2 Dispatch validation

| Control | Mechanism | Receipt |
|---|---|---|
| Typed argument schemas on every tool | Central Pydantic registry `TOOL_ARG_SCHEMAS`; static gate proves coverage | `D-SEC-04`; static gate `test_every_tool_has_arg_schema` |
| AST sanitization | Tolerant AST extractor with compiler preflight before execution | `tests/test_ast_sanitizer.py`; v1.3.0 structural compiler (WO-28) |
| Zero-`Any` invariant | Strict typing across `core`/`brain`/`reasoning`/`sandbox`/`ui` public APIs, statically gated | `D-AUD-01`; `tests/test_static_gates.py` |

### 1.3 Output-side supervision (the ACTION-CLAIM channel)

| Control | Mechanism | Receipt |
|---|---|---|
| Truth-in-Receipt matcher | Claims of stateful side effects must match verified ToolReceipts; 21 action verbs; hedge exemption policy | `D-SEC-05`; `src/lucca/sandbox/output_supervisor.py` |
| Formal battery | **70-sentence** scripted battery across 8 categories (broadened 2026-10-05: stale-receipt, failed-status, markdown, passive/multilingual characterization) | `tests/test_truth_in_receipt_battery.py` (70/70) |
| Live probe evidence | 100-probe action-hallucination battery; 0/50 control false aborts | `logs/test_reports/`; `docs/research/2026-10-05_action_hallucination_supervision_protocol_e2b_e4b.md` |
| Provenance gate | `LLM_NARRATION` unconditionally rejected; only authorized domain signers commit memory | ADR-006; `D-MEM-06` split (2026-10-05) |
| Coherence self-audit | Claim/receipt mismatch recorded as `COHERENCE_BREACH` first-class evidence | `src/lucca/core/coherence.py` |

### 1.4 Memory integrity

| Control | Mechanism | Receipt |
|---|---|---|
| Signed memory commits | HKDF HMAC-SHA256 two-stage read-time verification; persistent quarantine | `D-MEM-05`; `tests/test_memory_hmac_tamper.py` (11/11) |
| Provenance lattice | Deterministic vs LLM-inferred assertions distinguished (`D-MEM-06`, 2026-10-05) | `tests/test_provenance.py` |

**Scale of the verification discipline:** 1,240 passing tests / 67 hardware-
deselected, 24/24 static architectural gates (record `metrics-2026-10-05`,
`data/metrics/TEST_METRICS.yaml`).

---

## 2. Application sequencing decision (ratified order)

1. **Benchmark manifest first** — DONE 2026-10-05 (`data/benchmarks/MANIFEST.yaml`):
   numeric claims become citation-addressable before any application references them.
2. **Manifund application (this compilation → application draft)** — the
   evidence base above is the raw material; the application narrative frames it
   as: *a local-first companion where every tool dispatch, every memory commit,
   and every spoken action claim passes a mechanically verified gate, with the
   supervisor itself under active empirical improvement.*
3. **Clean held-out ablation run** (per
   [`docs/research/2026-10-04_pal_off_factorial_ablation_protocol.md`](2026-10-04_pal_off_factorial_ablation_protocol.md))
   — results feed the LTFF application and the standalone LessWrong/AF post;
   the raw confounded 58% figure is **not** publishable (paper 06 §5.1).
4. **LTFF application** — after the clean run produces quotable, enveloped results.

---

## 3. SPIKE proposals (registered, not scheduled)

### SPIKE-A — Grammar-constrained supervision on the ACTION-CLAIM channel (Manifund/CAIF fit)

Extend the in-flight 2026-10-05 action-hallucination supervision protocol with
**grammar-constrained decoding**: constrain generation on the ACTION-CLAIM
channel so that action verbs can only be emitted in frames the receipt matcher
can verify (past-tense + object), making ungrounded action claims
*unrepresentable* rather than merely detectable. This converts the supervisor
from a post-hoc DFA filter into a decode-time structural guarantee — a strong
fit for funder interests in decode-time safety mechanisms. **Extends, does not
re-plan:** the existing protocol doc remains the empirical backbone.

### SPIKE-B — Real intent classifier for routing (Emergent Ventures fit)

Replace the oracle benchmark-label routing (paper 06 §3.1 discloses the router
dispatches on dataset metadata labels) with a real in-the-wild intent
classifier (R0/P2/R1 dispatch). This closes the best-known gap between the
benchmark narrative and production behavior, and is a clean
measure-before/after story for a speed-focused funder.

---

## 4. Supervisor-improvement work already in flight (do not re-plan)

The action-hallucination supervision protocol
([`docs/research/2026-10-05_action_hallucination_supervision_protocol_e2b_e4b.md`](2026-10-05_action_hallucination_supervision_protocol_e2b_e4b.md))
is **already in flight** as of 2026-10-05: it measures whether E2B/E4B
actually hallucinate ungrounded side effects in unconstrained turns and whether
the supervisor catches them without false-aborting. Grant applications must
reference this in-flight work rather than proposing it anew; SPIKE-A above is
the *extension* of that protocol, not a replacement.

---

## 5. Honesty boundaries for the application

- The supervisor is a regex/DFA matcher with documented scope limits (passive
  voice and non-English utterances are known false-negative scope — battery
  category F). The application must state this; overselling "prevents
  ungrounded action claims" without the scope qualifier is what the external
  review flagged (P7).
- All benchmark numbers cited in any application must carry a manifest record
  ID from `data/benchmarks/MANIFEST.yaml` (sequencing decision §2.1).
- Personhood-adjacent claims must follow the re-score discipline
  ([`docs/research/PERSONHOOD_RESCORE_V1356_2026-10-05.md`](PERSONHOOD_RESCORE_V1356_2026-10-05.md)):
  measured-or-NOT-YET-MEASURED, never an estimated percentage.
