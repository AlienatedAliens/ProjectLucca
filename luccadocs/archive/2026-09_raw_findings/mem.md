# Findings — MEM (`src/lucca/memory/**` including migrations)

**Subtask:** S2c · **Method:** static line-by-line + S1 dynamic evidence · **Baseline:** HEAD `ed14f6b` + working tree per `03_BASELINE.md`, delta-characterised in [`../03b_BASELINE_DELTA.md`](../03b_BASELINE_DELTA.md) (memory modules: **unchanged since S0**) · **Written:** 2026-09-18 (UTC)
**Rules honoured:** findings-only; every finding cites `file:line` in the current tree or an artefact under `luccadocs/audit/evidence/`. Core/brain findings cross-referenced by ID.

**Severity totals: S0 = 0 · S1 = 1 · S2 = 8 · S3 = 8 · S4 = 2 · total = 19.**

---

## 1. Module map

Coverage from `luccadocs/audit/evidence/S1_14_coverage.txt` (rows 32–41; T1). LOC = non-blank lines, S0 metric (verified unchanged by `03b_BASELINE_DELTA.md`).

| File | LOC | Public symbols | Responsibilities (as-built) | Live callers in product path? | Outbound dependencies | Cov % | Tests exercising it |
|---|---:|---|---|---|---|---:|---|
| `memory/db.py` | 113 | `DEFAULT_DB_PATH`, `configure_connection`, `DatabaseManager` (`get_connection`, `get_writer`, `migrate`, `read_cursor`, `check_integrity`, `close`) | SQLite WAL + pragmas + sqlite-vec loader; single-writer connection; forward migrations | **yes** — `router/heuristic.py:23` (decision logging), `router/labeler.py:18`; **no** for the rest of memory (see below) | `sqlite3`, `sqlite_vec`, `structlog` | 94 % | `test_memory_db.py::test_t_mem_11_migrations`, `test_t_mem_09_concurrency` |
| `memory/gate.py` | 115 | `PREDICATES`, `ProvenanceGate` (`admit`) | HMAC verification, entry_id/content_sha256 recomputation, freshness, replay, USER_DERIVED grounding structure | **no** — constructed only inside `MemoryStore` (`store.py:62`), which nothing in `src/` constructs (F-CORE-003) | `signers`, `core.schemas`, `core.exceptions` | 91 % | `test_provenance.py` (7) |
| `memory/signers.py` | 121 | `KNOWN_DEV_KEYS`, `hkdf_extract/expand`, `derive_provenance_key`, `canonicalize_payload_dict`, `canonicalize_unsigned_payload`, `ProvenanceSigner`, `BaseProvenanceSigner`, 4 signer classes | Per-provenance HKDF keys; HMAC signing; canonical JSON | **no** — docstring construction sites (`senses.asr_proxy`, `sandbox.client`, `reasoning.executor`) **do not exist in `src/`**; only `extraction.py` constructs one | `hmac`, `core.schemas` | 97 % | `test_provenance.py` |
| `memory/extraction.py` | 154 | `FUNCTIONAL_PREDICATES`, `ExtractedFact`, `check_fact_grounding`, `FactExtractor` | Quote-grounding (NFC + substring + rapidfuzz ≥ 90), ≤ 5 facts/turn, signs `USER_DERIVED` | **no** — no caller outside `memory/` | `rapidfuzz`, `signers`, `gate` | 68 % | `test_grounding.py` (indirect) |
| `memory/entities.py` | 90 | `FIRST_PERSON_TERMS`, `canonicalise`, `resolve_entity` | Entity resolution: canonicalise → exact → alias → fuzz ≥ 94 → create | **no** — called from `store.commit` only | `rapidfuzz`, `sqlite3` | 85 % | indirect via `test_memory_db.py` |
| `memory/store.py` | 481 | `MemoryStore` (`commit`, `search`, `supersede`, `forget`, `graph_neighbors`, `backup`, `check_integrity`, `export_jsonl`) | Atomic single-transaction commits; KG supersession; bi-temporal filters; backups (VACUUM INTO, 14+8 pruning); JSONL export | **no** — no construction site in `src/` (F-CORE-003) | `asyncio`, `sqlite_vec`, `gate`, `retrieval`, `entities`, `ports` | 67 % | `test_memory_db.py` (11 tests) |
| `memory/retrieval.py` | 223 | `calculate_age_str`, `format_memory_context`, `HybridRetriever` | sqlite-vec KNN + FTS5 BM25 → RRF (k=60) → bi-temporal filters → 1-hop KG expansion; prompt-context renderer | **no** — `format_memory_context` has **zero callers** (the cap control brain needs, unwired — F-BRAIN-011); `HybridRetriever` only via `MemoryStore` | `sqlite_vec`, `tokens`, `ports` | 75 % | `test_memory_db.py` (T-MEM-01/02/03/04/12) |
| `memory/manager.py` | 217 | `MemoryManager` (`list_memories`, `add_memory`, `update_memory`, `delete_memory`, `get_stats`) | Admin CRUD over the same tables — **bypasses the provenance gate** (F-MEM-001) | **yes** — `ui/settings_dialog.py:68,255` (UI process) | `db` | **41 %** | none (0 dedicated tests; lines 92–220 untested) |
| `memory/tokens.py` | 182 | `subtokens`, `STOP_WORDS`, `clean_term`, `escape_fts_token`, `build_fts_query` | Sub-token expansion; injection-safe FTS5 MATCH construction | **yes** (via retrieval) + `store.commit` index side | `re` | 97 % | property-tested via FTS injection test (T-MEM-08) |
| `memory/working.py` | 50 | `WorkingMemory` (`open_task`, `set`, `get`, `get_state`, `close_task`) | Ephemeral task journal (DB lifecycle rows + in-memory state) | **no** — no caller in `src/` | `db` | 86 % | `test_memory_db.py::test_t_mem_14` |
| `migrations/0001_init.sql` | 135 | — | Schema: `provenance_envelopes` (provenance CHECK, unique `(nonce, content_sha256)`), `memories` + **`mem_bi_eligible` trigger** (DB-level eligibility backstop), FTS5 external-content + sync triggers, `kg_*`, `tool_contents`, `pending_confirmations`, `gate_nonces`, `memory_audit`, `task_journal` | applied by `db.migrate` | — | n/a | `test_t_mem_11` |
| `migrations/0002_decisions.sql` | 36 | — | Router telemetry: `decisions`, `vec_decisions`, `decision_labels` | applied; written by router, read by `labeler.py` | — | n/a | router tests |

**Wiring verdict:** the entire provenance pipeline (`gate`, `signers`, `extraction`, `store`, `retrieval`, `working`, `entities`) is **dead in the product path** — no construction site exists outside `lucca.memory` itself and `tests/` (consistent with F-CORE-003). The only memory code live in the product is `DatabaseManager` (router decision logging) and `MemoryManager` (UI settings dialog) — and the latter is the one module that bypasses the gate.

## 2. Provenance pipeline as-built (Charter §5.1 verification)

### 2.1 Gate (`gate.py:54-135`)

`admit()` performs, in order: (1) `LLMNarration` type-check → unconditional reject (`:81-82`); (2) type + eligibility vs `MEMORY_ELIGIBLE` (`schemas.py:181-188` = {USER_EXPLICIT, USER_DERIVED, TOOL_VERIFIED, LISP_ASSERTION} — exactly matches the DB trigger `mem_bi_eligible`, `0001_init.sql:47-51`); (3) recompute `entry_id` (sha256 of canonical bytes [:32]) and `content_sha256`, reject on mismatch (`:92-104`); (4) per-provenance HMAC-SHA256 (HKDF keys, `signers.py:43-47`) with `hmac.compare_digest` (`:107-112`); (5) freshness `abs(now − created_at) ≤ 300 s` (`:114-117`); (6) replay check against an **in-memory** dict, 24 h retention (`:119-124`); (7) `USER_DERIVED` structural checks: non-empty `source_entry_ids`, closed `PREDICATES` for `structured["p"]` (`:127-133`).

Mechanically tested: canonicalisation order-independence (T-PROV-01), signer×provenance authorisation matrix (T-PROV-02), tamper detection on 4 fields (T-PROV-03), replay (T-PROV-04), freshness boundary 299/301 s (T-PROV-05), LLM_NARRATION rejection, 100-case property test (P-05). **The gate itself is sound as a component; the defects are around it** (unwired — F-CORE-003; admin bypass — F-MEM-001; in-memory replay — F-MEM-010; `abs()` freshness — F-MEM-012).

### 2.2 Signers (`signers.py`)

Four signers with disjoint `allowed_provenances`: `UserSpeechSigner` {USER_EXPLICIT, USER_EXPLICIT_LOWCONF}, `DerivedFactSigner` {USER_DERIVED}, `ToolResultSigner` {TOOL_VERIFIED, TOOL_CONTENT_UNTRUSTED}, `LispAssertionSigner` {LISP_ASSERTION}. Authorisation is enforced at sign time and tested (T-PROV-02). Gaps: `KNOWN_DEV_KEYS` (`:16-23`) is **dead** — the TM-13 "known-dev-key list" control is unimplemented (F-MEM-005, cross-ref F-CORE-013); the docstrings' construction sites (`lucca.senses.asr_proxy`, `lucca.sandbox.client`, `lucca.reasoning.executor`) **do not exist** — no runtime component signs anything; and `USER_EXPLICIT_LOWCONF` is signable but not memory-eligible and has no consumer or upgrade path anywhere (F-MEM-004).

### 2.3 Commit path (`store.py:70-298`)

`commit()` → gate (skipped if the caller passes a pre-built `Admitted`, `:84-88` — see F-MEM-011) → embedding via `EmbeddingPort` (silently skipped unless exactly 384 dims, `:95-101`; failures append to `vec_backfill`, which **nothing ever consumes**, `:66,196` — F-MEM-008) → single `BEGIN IMMEDIATE` transaction under `asyncio.Lock`: envelope → memory row → sources → vec → KG upsert with functional-predicate supersession + audit rows → `gate_nonces` → `memory_audit` → COMMIT; `ROLLBACK` + `MemoryCommitFailed` on error, re-raising `ProvenanceRejected`/`MemoryStoreReadOnly` untouched (`:294-298`). Crash-atomicity is tested (T-MEM-10 fault hook, `:287-289`).

### 2.4 Retrieval (`retrieval.py:78-260`)

Dense KNN (top 30) + FTS5 BM25 (top 30, injection-safe query builder per P-06) → RRF k=60 → filters (forgotten, superseded, kind, since) → 1-hop KG expansion for fact hits, emitted as `kind="graph"` hits with **hard-coded `provenance=USER_DERIVED` and `created_at=now`** (`:222-231` — F-MEM-006) → dedupe by content → top-k → **write-back** of `access_count`/`last_access` via the writer connection outside any explicit transaction (`:246-258` — F-MEM-009).

### 2.5 The bypass (`manager.py:84-150`)

`MemoryManager.add_memory` — reachable from the UI process (`settings_dialog.py:255,68`) — inserts a `provenance_envelopes` row with `signer_id="ui-admin"`, **`signature="manual"`**, an **unchecked free-text `provenance` string** (default `"USER_EXPLICIT"`), no HMAC, no gate call, no freshness, no nonce discipline beyond a random uuid, then inserts the memory row. The DB trigger `mem_bi_eligible` passes it whenever the string names an eligible provenance. Result: rows in the same envelope table the gate defends, carrying a signature value that no verifier would accept, invisible to gate replay tracking. **F-MEM-001.** `update_memory`/`delete_memory` further break the audit chain (F-MEM-002/003).

**Invariant verdict (Charter §5.1):** the invariant is satisfied **vacuously** in the running product — no turn ever reaches memory because nothing wires the store (F-CORE-003) — and **undermined by construction** where the pipeline is reachable: the admin path (F-MEM-001) writes memory commits that never passed the gate, and the dead-signer gap means that if the pipeline is wired as-is, only `FactExtractor` has a live construction site; ASR/tool/LISP signers would have to be created first. No `LLM_NARRATION` path to memory exists (type-checked at the gate, no signer, and nothing feeds LLM text to memory — core.md §6).

---

## 3. Findings

Ordered by severity, then by ID. Every finding re-reviewed per Charter §3.5 (log in §7); `Status: OPEN`.

### F-MEM-001 — `MemoryManager.add_memory` writes provenance envelopes with `signature="manual"` and an unchecked provenance string, bypassing the ProvenanceGate

| Field | Value |
|---|---|
| **ID** | F-MEM-001 |
| **Title** | `MemoryManager.add_memory` writes provenance envelopes with `signature="manual"` and an unchecked provenance string, bypassing the ProvenanceGate |
| **Severity** | S1 — High |
| **Category** | SECURITY |
| **Location** | `src/lucca/memory/manager.py:84-150`; `src/lucca/ui/settings_dialog.py:68,255`; `src/lucca/memory/migrations/0001_init.sql:47-51` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/manager.py:101-123`
```python
            conn.execute(
                """
                INSERT INTO provenance_envelopes (
                    entry_id, provenance, kind, signer_id, signature,
                    content_sha256, nonce, created_at, trace_id, session_id,
                    confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    provenance,
                    kind,
                    "ui-admin",
                    "manual",
                    content_hash,
                    nonce,
                    now,
                    "ui-admin-trace",
                    "ui-admin-session",
                    1.0,
                    json.dumps({"content": content, "source": "ui-manual"}),
                ),
            )
```
(`provenance: str = "USER_EXPLICIT"` parameter at `:89` — a free string, never validated against the `Provenance` enum, the eligibility set, or the gate; `signature="manual"` can never verify under any key.)

**What is wrong / assumed / missing**

The one memory-write path actually wired into the running product (UI settings dialog constructs `MemoryManager` at `settings_dialog.py:255`) inserts provenance envelopes that never passed `ProvenanceGate.admit()`: no HMAC, no freshness, no replay tracking, no eligibility check beyond the DB trigger's string-membership test. The `provenance` parameter accepts any string — `"USER_EXPLICIT"` passes `mem_bi_eligible` and lands in memory; the `entry_id` format (`aud-{uuid}`, `:93`) is a third id scheme disjoint from the gate's sha256-based ids. Expected: the admin path goes through the gate (a dedicated admin provenance + signer), or writes to a visibly separate store that retrieval never treats as provenance-bearing.

**Why it matters**

Charter §5 invariant 1: memory commits originate only from gate-verified provenance. This path commits without the gate and pollutes `provenance_envelopes` — the table every downstream consumer (`store.export_jsonl`, retrieval joins, future audits) treats as cryptographically grounded — with rows whose signature is the literal string "manual". It also establishes the precedent that envelope-table writers need not be the gate: exactly the trust boundary TM-08 draws.

**Questions this raises**

1. Is the UI "add memory" feature a first-class user capability (needs a real admin provenance + signer) or a debugging tool (must not write `provenance_envelopes` at all)? (Decision recorded: if kept, add a dedicated admin provenance signed by a new admin signer; eligibility is the owner's call.)

**Proposed remediation**

1. In `src/lucca/memory/manager.py`, `add_memory()`: change the signature to accept a `BaseProvenanceSigner` (and give the manager a `master_key`); build an `UnsignedPayload` (`trace_id="ui-admin"`, `session_id="ui-admin"`, fresh random nonce), sign it, run it through `ProvenanceGate.admit`, and commit via the same transaction shape as `MemoryStore.commit`. Before: raw envelope insert with `signature="manual"`. After: gate-verified commit with a real HMAC.
2. In `src/lucca/ui/settings_dialog.py` (UI-area change): pass the master key from config to the `MemoryManager` constructor; refuse to construct when `master_key is None` (D-AUD-02 context: fail-closed posture).
3. Add `tests/test_memory_db.py::test_admin_add_memory_requires_valid_signature`: add a memory via the new path; assert the stored envelope verifies under `gate.admit` and that no row with `signature='manual'` can be produced.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** stored envelope passes `gate.admit`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_admin_add_memory_requires_valid_signature -q`

**Cross-references:** F-MEM-002, F-MEM-003, F-CORE-003, F-CORE-013

---

### F-MEM-002 — `update_memory` rewrites content without updating `content_sha256`/`signature` and writes no audit row

| Field | Value |
|---|---|
| **ID** | F-MEM-002 |
| **Title** | `update_memory` rewrites content without updating `content_sha256`/`signature` and writes no audit row |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/memory/manager.py:152-184` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/manager.py:159-168`
```python
            if importance is not None:
                conn.execute(
                    "UPDATE memories SET content = ?, importance = ? WHERE memory_id = ?",
                    (new_content, importance, memory_id),
                )
            else:
                conn.execute(
                    "UPDATE memories SET content = ? WHERE memory_id = ?",
                    (new_content, memory_id),
                )
```

**What is wrong / assumed / missing**

Editing a memory changes `memories.content` but leaves the joined `provenance_envelopes.content_sha256` (and `signature`, `entry_id`) pointing at the **old** text: every future verification of that memory against its envelope fails, and nothing records who changed what — no `memory_audit` row, unlike `store.forget`/`supersede` which both audit. Expected: content edits create a **new** gate-verified version that supersedes the old (the bi-temporal model exists for exactly this), or at minimum re-sign and audit in-transaction.

**Why it matters**

The audit trail (TM-11, Spec 04 §8) silently diverges from the data; `export_jsonl` (`store.py:493-533`) emits rows whose `payload.content_sha256` no longer matches their content — an integrity lie in the export.

**Questions this raises**

1. None — the bi-temporal supersession path already exists (`store.supersede`).

**Proposed remediation**

1. In `src/lucca/memory/manager.py`, `update_memory()`: replace the in-place content UPDATE with supersession — sign the new content via the F-MEM-001 step-1 path, insert the new memory, call `MemoryStore.supersede(old, new, reason="ui-edit")`. Before: in-place rewrite, stale envelope. After: bi-temporal edit chain with audit rows.
2. Add `tests/test_memory_db.py::test_update_memory_supersedes_and_audits`: edit a memory; assert the old row has `valid_to`/`superseded_by` set, a `memory_audit` row exists, and the new envelope verifies.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** supersession chain + audit row; old envelope untouched
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_update_memory_supersedes_and_audits -q`

**Cross-references:** F-MEM-001, F-MEM-003

---

### F-MEM-003 — `delete_memory(hard=True)` deletes the provenance envelope and writes no audit row

| Field | Value |
|---|---|
| **ID** | F-MEM-003 |
| **Title** | `delete_memory(hard=True)` deletes the provenance envelope and writes no audit row |
| **Severity** | S2 — Medium |
| **Category** | SECURITY |
| **Location** | `src/lucca/memory/manager.py:186-220` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/manager.py:207-209`
```python
                conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
                if entry_id:
                    conn.execute("DELETE FROM provenance_envelopes WHERE entry_id = ?", (entry_id,))
```
(no `memory_audit` row is written on this path, unlike `store.forget` at `store.py:389-393`.)

**What is wrong / assumed / missing**

Hard delete removes the memory **and** its provenance envelope, with no audit record. `memory_audit` rows referencing the deleted `entry_id` (e.g. the original `'commit'` row, `store.py:270-285`) dangle; `export_jsonl` (INNER JOIN on envelopes, `store.py:507`) silently drops the memory from exports. Expected per Spec 04 §8 / TM-11: deletion is soft (`forgotten_at`, as `store.forget` does, with audit) and envelopes are never destroyed — they are the evidence.

**Why it matters**

A user (or a compromised UI process) can erase a memory **and** its provenance in one call with no trace — the repudiation question TM-11 exists to answer becomes unanswerable for deleted rows.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/manager.py`, `delete_memory()`: remove the hard-delete branch (or route it through `store.forget` semantics): always soft-delete (`forgotten_at`), keep `provenance_envelopes`, write `INSERT INTO memory_audit(ts, kind, reason) VALUES (?, 'forget', ?)`. Before: envelope destroyed, no audit. After: soft delete + audit; envelopes immutable.
2. Add `tests/test_memory_db.py::test_delete_memory_preserves_envelope_and_audits`: delete a memory; assert the envelope row still exists and a `forget` audit row was written.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** envelope retained; audit row present; `memories.forgotten_at` set
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_delete_memory_preserves_envelope_and_audits -q`

**Cross-references:** F-MEM-001, F-MEM-002

---

### F-MEM-004 — `USER_EXPLICIT_LOWCONF` is signable but not memory-eligible and has no consumer or upgrade path

| Field | Value |
|---|---|
| **ID** | F-MEM-004 |
| **Title** | `USER_EXPLICIT_LOWCONF` is signable but not memory-eligible and has no consumer or upgrade path |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/memory/signers.py:111-116`; `src/lucca/core/schemas.py:171,181-188`; `src/lucca/memory/migrations/0001_init.sql:50` |
| **Status** | OPEN |

**Evidence**

`src/lucca/core/schemas.py:181-188`
```python
MEMORY_ELIGIBLE: frozenset[Provenance] = frozenset(
    {
        Provenance.USER_EXPLICIT,
        Provenance.USER_DERIVED,
        Provenance.TOOL_VERIFIED,
        Provenance.LISP_ASSERTION,
    }
)
```
(`UserSpeechSigner` signs `USER_EXPLICIT_LOWCONF` at `signers.py:113-114`; the DB trigger `mem_bi_eligible` (`0001_init.sql:47-51`) likewise excludes it; a repo-wide search finds no other reference to the tier.)

**What is wrong / assumed / missing**

The low-confidence tier can be **signed** but can never be committed (gate step 2 rejects it; the trigger aborts), and nothing reads, displays, or upgrades it — Spec 03's designed flow (low-confidence transcript → read-back confirmation → upgrade to `USER_EXPLICIT` or discard) is unimplemented. A signed LOWCONF payload today is a dead end.

**Why it matters**

The ASR confidence control (Spec 12 §4 residual risk: "Whisper mis-hearing becomes `USER_EXPLICIT` — confidence gating + read-back") has no implementation: either low-conf transcripts are silently dropped with no read-back (UX loss), or — once ASR wiring lands — implementers will route them straight to `USER_EXPLICIT` because the upgrade path does not exist, realising exactly the accepted-residual-risk scenario.

**Questions this raises**

1. None — the flow is specified (Spec 03) and simply absent.

**Proposed remediation**

1. In `src/lucca/memory/` (new `lowconf.py` or in `extraction.py`): implement `confirm_lowconf(payload, confirmed, signer) -> SignedPayload | None` — on confirmation re-sign the same content as `USER_EXPLICIT` with a fresh nonce and `source_entry_ids=[old.entry_id]`; on refusal return None and write `memory_audit('lowconf_discarded')`.
2. Add `tests/test_provenance.py::test_lowconf_confirm_upgrade`: sign LOWCONF → confirm → the new payload admits under the gate as `USER_EXPLICIT` with a source link to the original entry.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** upgraded payload admitted; original never committed
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_provenance.py::test_lowconf_confirm_upgrade -q`

**Cross-references:** F-CORE-003

---

### F-MEM-005 — `KNOWN_DEV_KEYS` is dead: the TM-13 known-dev-key control is unimplemented

| Field | Value |
|---|---|
| **ID** | F-MEM-005 |
| **Title** | `KNOWN_DEV_KEYS` is dead: the TM-13 known-dev-key control is unimplemented |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/memory/signers.py:16-23`; `luccadocs/archive/2026-09-17_pre_phase4_audit/09_developer_spec/12_threat_model.md:33` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/signers.py:16-23`
```python
KNOWN_DEV_KEYS: Final[frozenset[str]] = frozenset(
    {
        "insecure_dev_key",
        "changeme",
        "test_secret_key_lucca_12345",
        "default_master_key",
    }
)
```
(a repo-wide search finds no consumer; `core/config.py:155` defaults `master_key` to `None` and nothing rejects dev-known values.)

**What is wrong / assumed / missing**

TM-13 ("Spoofing: default/dev master key in prod — fail-closed boot; known-dev-key list") names this exact control; the constant exists and is never consulted. Combined with F-CORE-013 (no fail-closed on unset key) the prod key posture is: unset → boots anyway; set to a known-dev value → boots anyway.

**Why it matters**

A product that boots with `changeme` as its master key signs all provenance with a publicly-guessable HMAC key — provenance forgery becomes trivial (TM-08/TM-13), and the threat model's accepted-risk framing is void because its control does not exist.

**Questions this raises**

1. None.

**Proposed remediation**

1. Add `assert_prod_master_key(master_key: str | None, env_mode: str) -> None` (new `src/lucca/memory/keycheck.py`; MEM-owned, CORE-called per the boundary decision) raising `ProvenanceRejected` when `env_mode == "prod"` and (`master_key is None` or `master_key in KNOWN_DEV_KEYS` or `len(master_key.encode()) < 32`).
2. Call it from `main.py` boot (CORE-area change) before spawning children — this also implements F-CORE-013's missing check.
3. Add `tests/test_provenance.py::test_prod_rejects_dev_keys`: each value in `KNOWN_DEV_KEYS` plus `None` → rejected in prod; accepted in dev.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** rejection in prod for all dev keys and None
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_provenance.py::test_prod_rejects_dev_keys -q`

**Cross-references:** F-CORE-013, F-CORE-025, F-MEM-018

---

### F-MEM-006 — KG-expansion hits are emitted with hard-coded `provenance=USER_DERIVED` and `created_at=now`

| Field | Value |
|---|---|
| **ID** | F-MEM-006 |
| **Title** | KG-expansion hits are emitted with hard-coded `provenance=USER_DERIVED` and `created_at=now` |
| **Severity** | S2 — Medium |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/memory/retrieval.py:220-232` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/retrieval.py:223-229`
```python
                        graph_hit = MemoryHit(
                            memory_id=int(erow[0]),
                            content=graph_content,
                            provenance=Provenance.USER_DERIVED,
                            score=graph_score,
                            kind="graph",
                            created_at=current_time,
                            valid_from=float(erow[4]),
```

**What is wrong / assumed / missing**

Graph-expansion hits report the provenance of the edge's memory as `USER_DERIVED` regardless of its actual tier (the edge may descend from a `TOOL_VERIFIED` or `LISP_ASSERTION` fact — the edge's `memory_id` is in hand and joins to `provenance_envelopes`), and report `created_at = current_time` (the retrieval moment) instead of the edge's recorded time, so `calculate_age_str` renders every graph fact as "0s ago". Both fields flow into `format_memory_context`'s rendered prompt block (`[{kind}/{provenance} {age}]`) — the LLM would be told a provenance and a recency that may both be false.

**Why it matters**

Provenance labels in retrieval output are claims about evidence quality; fabricating them breaks the labelling contract even though no consumer is wired today. The fabricated recency also distorts any future recency-weighted ranking.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/retrieval.py`, the edge query (`:211-217`): add `p.provenance, ed.recorded_at` via `JOIN provenance_envelopes p` on the edge's memory entry; populate `provenance` and `created_at` from the row. Before: hard-coded. After: actual values.
2. Add `tests/test_memory_db.py::test_graph_hits_carry_real_provenance`: commit a `TOOL_VERIFIED` fact; search; assert the graph hit's provenance is `TOOL_VERIFIED` and `created_at` is the recorded time.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** graph hit provenance matches the edge's memory provenance
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_graph_hits_carry_real_provenance -q`

**Cross-references:** F-BRAIN-011, F-MEM-017

---

### F-MEM-007 — `tool_contents` and `pending_confirmations` tables have no writer or reader anywhere

| Field | Value |
|---|---|
| **ID** | F-MEM-007 |
| **Title** | `tool_contents` and `pending_confirmations` tables have no writer or reader anywhere |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/memory/migrations/0001_init.sql:110-127` |
| **Status** | OPEN |

**Evidence**

`0001_init.sql:110-119`
```sql
CREATE TABLE IF NOT EXISTS tool_contents(
  content_id      INTEGER PRIMARY KEY,
  entry_id        TEXT REFERENCES provenance_envelopes(entry_id),
  trace_id        TEXT NOT NULL,
  tool_name       TEXT NOT NULL,
  body            TEXT NOT NULL,
  sha256          TEXT NOT NULL,
  created_at      REAL NOT NULL,
  expires_at      REAL NOT NULL
);
```
(a repo-wide search for `tool_contents` and `pending_confirmations` finds only this migration — no INSERT, no SELECT, in `src/` or `tests/`.)

**What is wrong / assumed / missing**

Two spec'd storage surfaces exist in the schema and nowhere in code: `tool_contents` (the `TOOL_CONTENT_UNTRUSTED` body store with TTL — the mechanism that would let tool/page text be *referenced* without entering the prompt or memory) and `pending_confirmations` (durable pending-action state). With F-CORE-019 (tool results discarded), the product keeps **no** record of tool bodies at all; these tables were the designed home and are dead.

**Why it matters**

The `TOOL_CONTENT_UNTRUSTED` tier is signed by `ToolResultSigner` but has no storage: the tier's entire purpose (store untrusted bodies with TTL, reference them by id) is unimplemented. The schema suggests the feature was designed and dropped mid-implementation.

**Questions this raises**

1. Should `tool_contents` be wired when F-CORE-019 is remediated (results stored here instead of being dropped), or are the tables obsolete? (→ §5 Q-M-01.)

**Proposed remediation**

1. Decide the fate of the two tables (decision pending Q-M-01): if keeping, implement `ToolContentStore.put/get(expires_at)` in `memory/` and call it from the sandbox result path when F-CORE-019 is remediated; if dropping, add migration `0003_drop_dead_tables.sql` (`DROP TABLE IF EXISTS tool_contents; DROP TABLE IF EXISTS pending_confirmations;`).
2. Either way, add a T1 test pinning the decision (store round-trip, or a migration test asserting the tables are gone).

**Verification test**

- **Tier:** T1
- **Input:** the pinning test from step 2
- **Expected output:** matches the recorded decision
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py -q -k tool_contents`

**Cross-references:** F-CORE-019, F-MEM-004

---

### F-MEM-008 — The embedding backfill queue is appended to and never consumed

| Field | Value |
|---|---|
| **ID** | F-MEM-008 |
| **Title** | The embedding backfill queue is appended to and never consumed |
| **Severity** | S2 — Medium |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/memory/store.py:66,94-101,189-196` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/store.py:195-196`
```python
                else:
                    self.vec_backfill.append(memory_id)
```
(`vec_backfill: list[int]` declared at `:66`; a repo-wide search finds no reader, flush, or persistence — a process restart loses it. Embedding is also silently skipped when the vector is not exactly 384 dims, `:97-99`, with only a warning.)

**What is wrong / assumed / missing**

Memories committed without an embedding (embedder absent, wrong dim, or embed exception) are supposed to be backfilled later (Spec 04 §4); the queue exists, grows in memory, and is never drained — those memories are permanently invisible to dense retrieval (BM25 still finds them), with no log summary and no recovery.

**Why it matters**

Silent, unrecoverable degradation of half the hybrid retrieval contract; the failure mode (memory exists but dense search misses it) is invisible in operation.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/store.py`: add `async def backfill_embeddings(self) -> int` — re-embed and insert for each queued id, then clear; call it opportunistically after each successful embed **and** from a startup sweep that rebuilds the queue from `SELECT memory_id FROM memories WHERE memory_id NOT IN (SELECT memory_id FROM vec_memories) AND forgotten_at IS NULL` (making restart safe). Before: write-only queue. After: drained + restart-recoverable.
2. Add `tests/test_memory_db.py::test_embedding_backfill_recovers_missing_vectors`: commit with a failing embedder, then with a working one; assert the memory becomes dense-searchable.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** dense search finds the memory after backfill
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_embedding_backfill_recovers_missing_vectors -q`

**Cross-references:** F-MEM-009

---

### F-MEM-009 — Retrieval mutates the database on the read path (`access_count` via the writer, outside any transaction)

| Field | Value |
|---|---|
| **ID** | F-MEM-009 |
| **Title** | Retrieval mutates the database on the read path (`access_count` via the writer, outside any transaction) |
| **Severity** | S2 — Medium |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/memory/retrieval.py:246-258` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/retrieval.py:250-256`
```python
                writer = self.db.get_writer()
                ph = ",".join("?" for _ in matched_mids)
                writer.execute(
                    f"UPDATE memories SET access_count = access_count + 1, last_access = ? "  # noqa: S608
                    f"WHERE memory_id IN ({ph})",
                    [current_time, *matched_mids],
                )
```

**What is wrong / assumed / missing**

`search()` — nominally a read — takes the **single shared writer connection** and executes an UPDATE in autocommit mode with no coordination with `MemoryStore.commit`'s `BEGIN IMMEDIATE` (protected by the asyncio lock retrieval does not take). Interleaving with a commit's long transaction is serialised only by SQLite locking; the write happens even for read-only callers; and a `sqlite3.Error` is swallowed to a warning **after** the hits were already computed — partially applied side effects with no retry.

**Why it matters**

A read API with hidden, partially-failing writes is a concurrency and correctness hazard on the path that is supposed to be the safe one, and makes retrieval non-idempotent — complicating any future caching or replay.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/retrieval.py:246-258`: wrap the UPDATE in `BEGIN IMMEDIATE`/`COMMIT` (busy_timeout already 5 s), or move the access-count update behind an explicit `MemoryStore.record_access(ids)` that takes the same `asyncio.Lock` as commit. Before: unlocked autocommit write inside search. After: locked/transactional or explicit-API write.
2. Add `tests/test_memory_db.py::test_search_access_update_is_transactional`: run search concurrently with a commit loop (mirroring T-MEM-09's harness); assert no `database is locked` escapes and counts are exactly +1 per hit per search.

**Verification test**

- **Tier:** T1
- **Input:** the concurrency test above
- **Expected output:** no lock errors; exact +1 semantics
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_search_access_update_is_transactional -q`

**Cross-references:** F-MEM-008

---

### F-MEM-010 — Gate replay protection is per-instance in-memory state; the durable `gate_nonces` table is written but never read

| Field | Value |
|---|---|
| **ID** | F-MEM-010 |
| **Title** | Gate replay protection is per-instance in-memory state; the durable `gate_nonces` table is written but never read |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/memory/gate.py:68-75,119-124`; `src/lucca/memory/store.py:264-268`; `src/lucca/memory/migrations/0001_init.sql:28,129-134` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/gate.py:69`
```python
        self._seen_nonces: dict[tuple[str, str], float] = {}
```
(`store.commit` inserts into `gate_nonces` at `store.py:264-268`; no code path ever SELECTs from that table; the envelope table's `ux_env_nonce` unique index (`0001_init.sql:28`) only blocks re-inserting an *identical committed* envelope.)

**What is wrong / assumed / missing**

Replay detection lives in a process-local dict: a second `ProvenanceGate` instance (second process, or post-restart) accepts a payload the first already admitted, as long as it is still within the 300 s freshness window. The durable table exists for exactly this and is write-only. Mitigations keeping this S3: freshness bounds replay to ±300 s, and committing the same envelope twice fails on `ux_env_nonce`.

**Why it matters**

The gate's advertised guarantee ("replay-free", class docstring `:56-58`) holds only within one process instance; the ADR-008 topology has four processes, each holding an independent, diverging replay view.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/gate.py`, `admit()` step 6: before the in-memory check, `SELECT 1 FROM gate_nonces WHERE nonce = ? AND content_sha256 = ?` (the gate gains a `DatabaseManager` or nonce-lookup callable in its constructor; tests inject an in-memory db); after admission, INSERT the row. Before: memory-only. After: durable, cross-instance.
2. Add `tests/test_provenance.py::test_replay_detected_across_gate_instances`: admit with gate A (db-backed), construct gate B on the same db, re-admit → `ProvenanceRejected("Replay detected")`.

**Verification test**

- **Tier:** T1
- **Input:** the two-instance test above
- **Expected output:** second instance rejects the replay
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_provenance.py::test_replay_detected_across_gate_instances -q`

**Cross-references:** F-MEM-001

---

### F-MEM-011 — `MemoryStore.commit` skips the gate entirely when handed a pre-built `Admitted`

| Field | Value |
|---|---|
| **ID** | F-MEM-011 |
| **Title** | `MemoryStore.commit` skips the gate entirely when handed a pre-built `Admitted` |
| **Severity** | S3 — Low |
| **Category** | SECURITY |
| **Location** | `src/lucca/memory/store.py:84-91`; `src/lucca/core/schemas.py:233-234` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/store.py:84-88`
```python
        if isinstance(payload, Admitted):
            signed_payload = payload.payload
        elif isinstance(payload, SignedPayload):
            admitted = self.gate.admit(payload, now=current_time)
            signed_payload = admitted.payload
```

**What is wrong / assumed / missing**

`Admitted` is an ordinary frozen Pydantic model (`schemas.py:233-234`) that anyone can construct as `Admitted(payload=<forged SignedPayload>)`; `commit()` trusts the type and never re-verifies. Defense-in-depth: since `Admitted` is only ever produced by `gate.admit`, the shortcut is safe *by convention*, but the invariant-critical commit path should not depend on caller discipline.

**Why it matters**

One line of caller error (or one future caller passing `Admitted` to skip a slow gate) commits unverified payloads — the exact failure the gate exists to prevent.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/store.py:84-91`: always run `self.gate.admit(signed_payload, now=current_time)` regardless of the incoming type (gate admission is idempotent modulo the replay check — see F-MEM-010 — so re-verification is safe once replay state is durable). Before: type-based shortcut. After: unconditional verification.
2. Add `tests/test_memory_db.py::test_commit_reverifies_prebuilt_admitted`: forge an `Admitted` around a tampered payload; assert `commit` raises `ProvenanceRejected`.

**Verification test**

- **Tier:** T1
- **Input:** the forged-Admitted test above
- **Expected output:** `ProvenanceRejected`, nothing committed
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_commit_reverifies_prebuilt_admitted -q`

**Cross-references:** F-MEM-001, F-MEM-010

---

### F-MEM-012 — Gate freshness uses `abs(now − created_at)`: future-dated payloads are admitted

| Field | Value |
|---|---|
| **ID** | F-MEM-012 |
| **Title** | Gate freshness uses `abs(now − created_at)`: future-dated payloads are admitted |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/memory/gate.py:114-117` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/gate.py:115-117`
```python
        age = abs(current_time - payload.created_at)
        if age > 300.0:
            raise ProvenanceRejected(f"Payload timestamp expired ({age:.1f}s > 300.0s)")
```

**What is wrong / assumed / missing**

A payload stamped up to 300 s in the **future** passes freshness. Legitimate signers stamp `time.time()` at signing, so a future timestamp is either clock skew or manufacture; a skew-tolerant design would allow a small forward skew but the symmetric window means a payload created_at=now+299 is admitted and then sits at the top of every recency ordering. Expected: allow a small forward skew (e.g. 5 s) and reject beyond it.

**Why it matters**

Minor, but the freshness check is the gate's time-trust anchor; a symmetric window is a gratuitous widening of it. Tested behaviour (T-PROV-05) only exercises the past side.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/gate.py:114-117`: replace with `skew = current_time - payload.created_at; if skew > 300.0: raise ...; if skew < -5.0: raise ProvenanceRejected(f"Payload timestamp {abs(skew):.1f}s in the future")`. Before: symmetric ±300 s. After: −5 s/+300 s.
2. Extend `tests/test_provenance.py::test_t_prov_05_freshness_window` with a +299 s case → rejected.

**Verification test**

- **Tier:** T1
- **Input:** payload with `created_at = now + 299`
- **Expected output:** `ProvenanceRejected` (future)
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_provenance.py::test_t_prov_05_freshness_window -q`

**Cross-references:** F-MEM-010

---

### F-MEM-013 — Memory paths hard-code `C:\ProjectLucca` for the database and backup directory

| Field | Value |
|---|---|
| **ID** | F-MEM-013 |
| **Title** | Memory paths hard-code `C:\ProjectLucca` for the database and backup directory |
| **Severity** | S3 — Low |
| **Category** | MAINTAINABILITY |
| **Location** | `src/lucca/memory/db.py:19`; `src/lucca/memory/store.py:40` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/db.py:19`
```python
DEFAULT_DB_PATH: Final[Path] = Path(r"C:\ProjectLucca\data\memory.sqlite")
```
(`store.py:40`: `DEFAULT_BACKUP_DIR = Path(r"C:\ProjectLucca\data\backups")`; `core/config.py` has `paths.data`/`resolve_path` which these ignore — the F-CORE-030 pattern, memory-side instance.)

**What is wrong / assumed / missing**

The defaults bypass `LUCCA_HOME`/`LuccaConfig.paths`, so tests and any non-default deployment either pass explicit paths (fine) or silently touch the production database (not fine — `MemoryManager()` at `settings_dialog.py:255` uses the default and therefore the **production** DB from the UI process). Expected: defaults resolve via `get_config().resolve_path("data/memory.sqlite")`.

**Why it matters**

Same defect class as F-CORE-030 (test/prod conflation, dev-mode blindness); the UI's `MemoryManager()` is a live consumer that always opens the prod database.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/db.py:19`: `DEFAULT_DB_PATH = get_config().resolve_path("data/memory.sqlite")` (import inside the default factory to avoid import cycles), and `store.py:40` analogously for backups. Before: hard-coded roots. After: config-anchored.
2. Add `tests/test_memory_db.py::test_default_paths_follow_lucca_home`: with `LUCCA_HOME` pointed at tmp, assert the defaults land under tmp.

**Verification test**

- **Tier:** T1
- **Input:** the tmp-home test above
- **Expected output:** defaults resolve under the configured home
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_default_paths_follow_lucca_home -q`

**Cross-references:** F-CORE-030, F-MEM-001

---

### F-MEM-014 — `graph_neighbors` looks entities up with `lower().strip()` instead of `canonicalise()`

| Field | Value |
|---|---|
| **ID** | F-MEM-014 |
| **Title** | `graph_neighbors` looks entities up with `lower().strip()` instead of `canonicalise()` |
| **Severity** | S3 — Low |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/memory/store.py:399-417`; `src/lucca/memory/entities.py:19-28` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/store.py:404`
```python
            s_can = entity.lower().strip()
```
(entities are stored **canonicalised** — punctuation-stripped, whitespace-collapsed (`entities.py:19-28`) — so the canonical form of "Dr. Smith" is `dr smith`, while `graph_neighbors("Dr. Smith")` searches for `dr. smith` and finds nothing.)

**What is wrong / assumed / missing**

The one public KG query normalises differently from the one write path; any query containing punctuation (the entity-resolution rules exist precisely because surfaces contain punctuation) returns empty. Expected: `s_can = canonicalise(entity)`.

**Why it matters**

The KG query API is silently broken for punctuated entities — the common case for names, paths, and file references.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/store.py:404`: `s_can = canonicalise(entity)` (import from `entities`). Before: lower/strip. After: same canonicalisation as writes.
2. Add `tests/test_memory_db.py::test_graph_neighbors_punctuated_entity`: commit a fact whose subject is "Dr. Smith"; assert `graph_neighbors("Dr. Smith")` returns the edge.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** edge returned for the punctuated surface
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_graph_neighbors_punctuated_entity -q`

**Cross-references:** None

---

### F-MEM-015 — `RetrievalQuery.exact_identifiers` is never used by the retriever

| Field | Value |
|---|---|
| **ID** | F-MEM-015 |
| **Title** | `RetrievalQuery.exact_identifiers` is never used by the retriever |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/core/schemas.py:241`; `src/lucca/memory/retrieval.py:78-260` |
| **Status** | OPEN |

**Evidence**

`src/lucca/core/schemas.py:240-242`
```python
    k: int = 8
    exact_identifiers: list[str] = Field(default_factory=list)
    include_superseded: bool = False
```
(a repo-wide search finds `exact_identifiers` only in the schema and in `tests/fixtures/retrieval/identifiers.jsonl` — the retrieval pipeline never reads it.)

**What is wrong / assumed / missing**

Spec 04 §6's identifier-exact-match lane (id/code identifiers that fuzzy and vector retrieval miss) is declared in the query contract and unimplemented; the retrieval benchmark fixtures for it exist (`identifiers.jsonl`, exercised by T-MEM-01 via … the same hybrid path), so the benchmark passes without the feature it names.

**Why it matters**

A query-contract field that silently does nothing misleads callers into believing identifier lookups are exact; the identifier benchmark's green is not evidence of the feature.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/retrieval.py`, `search()`: after the RRF fusion, for each `exact_identifiers` value run `SELECT ... FROM memories WHERE content LIKE ?` (token-bounded) and prepend matches as rank-0 hits (deduped). Before: field ignored. After: identifier lane per spec.
2. Add `tests/test_memory_db.py::test_exact_identifiers_lane`: commit content containing `LUCCA-1234`; search with `exact_identifiers=["LUCCA-1234"]` and a paraphrase-only query; assert the hit ranks first.

**Verification test**

- **Tier:** T1
- **Input:** the test above
- **Expected output:** identifier hit present and top-ranked
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_exact_identifiers_lane -q`

**Cross-references:** None

---

### F-MEM-016 — `WorkingMemory._tasks` grows without bound; tasks are never pruned unless explicitly closed

| Field | Value |
|---|---|
| **ID** | F-MEM-016 |
| **Title** | `WorkingMemory._tasks` grows without bound; tasks are never pruned unless explicitly closed |
| **Severity** | S3 — Low |
| **Category** | RELIABILITY |
| **Location** | `src/lucca/memory/working.py:20-44` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/working.py:22,24-31`
```python
        self._tasks: dict[str, dict[str, Any]] = {}

    def open_task(self, task_id: str, now: float | None = None) -> None:
        current_time = now if now is not None else time.time()
        self._tasks[task_id] = {}
```
(no TTL, no cap, no sweep; `close_task` is the only removal path and `get`/`set` on a closed task raise or return defaults.)

**What is wrong / assumed / missing**

A crashed or abandoned task leaks its state dict for the process lifetime; `INSERT OR REPLACE INTO task_journal` also overwrites the previous journal row for a reused task_id, losing the prior lifecycle record.

**Why it matters**

Unbounded state in a long-lived process; minor until the (currently unwired) multi-step task feature is actually used.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/memory/working.py`: add a `max_open_tasks: int = 64` cap — `open_task` evicts the oldest open task (with `close_task(outcome="evicted")`) when at capacity. Before: unbounded. After: capped with audited eviction.
2. Add `tests/test_memory_db.py::test_working_memory_evicts_oldest`: open 65 tasks; assert the first was closed with `evicted` and `get` raises/default.

**Verification test**

- **Tier:** T1
- **Input:** the eviction test above
- **Expected output:** oldest task evicted; journal shows `evicted`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_working_memory_evicts_oldest -q`

**Cross-references:** F-MEM-007

---

### F-MEM-017 — `format_memory_context` implements the memory-prompt caps (160 chars, 600 tokens) that nothing calls

| Field | Value |
|---|---|
| **ID** | F-MEM-017 |
| **Title** | `format_memory_context` implements the memory-prompt caps (160 chars, 600 tokens) that nothing calls |
| **Severity** | S3 — Low |
| **Category** | INCOMPLETE |
| **Location** | `src/lucca/memory/retrieval.py:36-64` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/retrieval.py:41-43`
```python
    """
    Render memory hits into prompt context block per Spec 04 §6 / Spec 10:
    - [{kind}/{provenance} {age}] {content} truncated to 160 chars
    - graph hits as: - {content}
    Enforces <= max_tokens (approx 4 chars/token).
    """
```
(a repo-wide search finds zero callers in `src/`; `brain/prompt_builder.py:630-634` renders memory hits raw instead — F-BRAIN-011.)

**What is wrong / assumed / missing**

The Spec 04 §6/Spec 10 §4 compliant renderer exists — per-hit 160-char truncation, provenance/age labelling, 600-token budget — and is dead code, while the live prompt builder interpolates uncapped, unlabelled raw content. Two implementations of the same concern, the correct one unwired.

**Why it matters**

When memory retrieval is wired (F-CORE-003), whoever wires it must choose: the compliant renderer (correct caps) or the raw path (injection surface, F-BRAIN-011). The correct control existing-but-dead is precisely how the raw path survives review.

**Questions this raises**

1. None.

**Proposed remediation**

1. In `src/lucca/brain/prompt_builder.py` (BRAIN-area change, joint with F-BRAIN-011): replace the raw `- {m.content}` loop with a call to `format_memory_context(memories)` (move the function to a shared location or import from `memory.retrieval`), which supplies the caps and labelling this finding documents. Before: raw interpolation. After: the compliant renderer is the only path.
2. Add `tests/test_memory_db.py::test_format_memory_context_budget`: 20 hits × 400 chars → output ≤ 2 400 chars (600 × 4) and every non-graph line carries the `[kind/provenance age]` prefix.

**Verification test**

- **Tier:** T1
- **Input:** the budget test above
- **Expected output:** ≤ 2 400 chars; labelled lines
- **Threshold:** ≤ 2 400 chars
- **Command:** `uv run pytest tests/test_memory_db.py::test_format_memory_context_budget -q`

**Cross-references:** F-BRAIN-011, F-MEM-006, F-CORE-003

---

### F-MEM-018 — Answer to core Q-15/F-CORE-060: `master_key=None` reaches the gate as a `TypeError`, not a fail-closed rejection — but no product path constructs the gate today

| Field | Value |
|---|---|
| **ID** | F-MEM-018 |
| **Title** | Answer to core Q-15/F-CORE-060: `master_key=None` reaches the gate as a `TypeError`, not a fail-closed rejection — but no product path constructs the gate today |
| **Severity** | S4 — Info |
| **Category** | ASSUMPTION |
| **Location** | `src/lucca/memory/gate.py:60-63`; `src/lucca/memory/signers.py:74-77`; `src/lucca/core/config.py:155`; `src/lucca/main.py` (no construction site) |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/gate.py:60-63`
```python
    def __init__(self, master_key: bytes) -> None:
        if len(master_key) < 32:
            raise ProvenanceRejected(f"Master key must be at least 32 bytes, got {len(master_key)}")
```
(`config.master_key` is `str | None = None` (`config.py:155`); a repo-wide search finds no construction of `ProvenanceGate`, `MemoryStore`, or any signer outside `lucca.memory` itself and `tests/`.)

**What is wrong / assumed / missing**

This finding answers core Q-15 ("What does `signers.py` do with `master_key is None`?"): with `None`, `len(None)` raises `TypeError` **before** the guard — an untyped crash, not the typed fail-closed rejection the guard intends; the same applies to `BaseProvenanceSigner.__init__` (`signers.py:74-77`) and `MemoryStore`. **However**, no product path constructs any of these today (F-CORE-003), so the crash is unreachable in the shipped product: F-CORE-060 does **not** escalate F-CORE-013 to S0. The real exposure remains F-CORE-013 itself (boot proceeds with no key) plus F-MEM-005 (dev keys accepted).

**Why it matters**

Resolves the open severity question from the core audit with code truth; also documents that the *intended* fail-closed semantics are implemented as an accidental `TypeError`.

**Questions this raises**

1. None — resolved; F-CORE-060 can be closed with this citation.

**Proposed remediation**

1. In `src/lucca/memory/gate.py:60-63` and `signers.py:74-77`: change the guard to `if not isinstance(master_key, (bytes, bytearray)) or len(master_key) < 32: raise ProvenanceRejected(...)` — typed rejection instead of `TypeError`.
2. Implement the boot-time gate from F-MEM-005 (which makes the question moot for prod).
3. Extend `tests/test_provenance.py::test_prod_rejects_dev_keys` with a `master_key=None` construction case asserting `ProvenanceRejected`.

**Verification test**

- **Tier:** T1
- **Input:** `ProvenanceGate(master_key=None)`
- **Expected output:** `ProvenanceRejected`, not `TypeError`
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_provenance.py::test_prod_rejects_dev_keys -q`

**Cross-references:** F-CORE-060, F-CORE-013, F-MEM-005

---

### F-MEM-019 — Backup pruning keeps "14 most recent", not 14 daily + 8 weekly, and names files in local time

| Field | Value |
|---|---|
| **ID** | F-MEM-019 |
| **Title** | Backup pruning keeps "14 most recent", not 14 daily + 8 weekly, and names files in local time |
| **Severity** | S4 — Info |
| **Category** | CORRECTNESS |
| **Location** | `src/lucca/memory/store.py:424-476` |
| **Status** | OPEN |

**Evidence**

`src/lucca/memory/store.py:446-470`
```python
        for b in backups:
            try:
                date_part = b.name.replace("memory-", "").split("-")[0]
                dt = datetime.datetime.strptime(date_part, "%Y%m%d")
            except ValueError:
                continue

            is_sunday = dt.weekday() == 6
            keep = False
            if daily_kept < 14:
                daily_kept += 1
                keep = True
            elif is_sunday and weekly_kept < 8:
                weekly_kept += 1
                keep = True
```
(naming at `:428`: `now.strftime('%Y%m%d-%H%M')` with `datetime.datetime.now()` — local time, no UTC marker.)

**What is wrong / assumed / missing**

The loop keeps the **14 most recent backups regardless of date** (six backups made in one hour consume the whole "daily" quota), then retains up to 8 further Sundays. The docstring claims "14 daily backups and 8 weekly (Sunday) backups" — the implementation is "newest 14 + up to 8 older Sundays". Also the timestamp is local time, so the filename cannot be compared to the retention rule reliably across DST. Multiple backups on one day are possible (minute-resolution names) making "daily" ambiguous by construction.

**Why it matters**

Informational: retention is *more* conservative in count than claimed but not the documented policy; long-gap recovery windows differ from the spec's intent. S4 because data safety is unaffected (more retained than promised, never fewer) and the discrepancy needs an owner decision on intent.

**Questions this raises**

1. Is the intended policy "14 calendar days + 8 Sundays" (requires per-day grouping) or "newest 14 + 8 Sundays" (current behaviour, rename the docstring)? (→ §5 Q-M-02.)

**Proposed remediation**

1. Per Q-M-02's answer: either implement calendar-day grouping (`dict[date] → keep newest per day, then Sunday rule`) or fix the docstring/audit message to state the actual policy and switch naming to `datetime.now(timezone.utc)`.
2. Add `tests/test_memory_db.py::test_backup_retention_policy`: create 20 same-day backups + 10 Sunday-spaced ones; assert retention matches the ratified policy.

**Verification test**

- **Tier:** T1
- **Input:** the retention test above
- **Expected output:** retention matches the ratified policy exactly
- **Threshold:** n/a — boolean
- **Command:** `uv run pytest tests/test_memory_db.py::test_backup_retention_policy -q`

**Cross-references:** None

---

## 4. Assumptions register

| # | Location | Assumption embedded in code | Why unverified | Risk if false |
|---|---|---|---|---|
| A-M-01 | `gate.py:60-62`; `signers.py:74-76` | `master_key` is always a ≥ 32-byte `bytes` when the gate/signers are constructed | `config.master_key` is `str \| None` (`config.py:155`); `None` → `TypeError` not `ProvenanceRejected` (F-MEM-018) | Untyped crash instead of fail-closed, once wiring lands |
| A-M-02 | `store.py:97-99` | Embeddings are always exactly 384 floats | Only the MiniLM-L6-v2 model exists today; a different embedder silently disables dense search | Half the hybrid contract silently off |
| A-M-03 | `store.py:439-440` | `VACUUM INTO` with a quote-escaped path is injection-safe | Sufficient for SQLite string literals; path came from caller/backup naming | None identified; recorded for completeness |
| A-M-04 | `retrieval.py:203` | `hits[-1]` is the lowest-scored hit | Relies on `sorted_candidates` remaining RRF-ordered through filtering — true today; a future filter reordering breaks `graph_score` anchoring | Graph hits scored against the wrong anchor |
| A-M-05 | `extraction.py:161` | `min(0.8, max(0.1, confidence*0.9))` is a sound derived-confidence formula | No calibration data; the 0.8 ceiling is a magic number | Derived facts systematically over/under-ranked |
| A-M-06 | `tokens.py:30-156` | The English stop-word list fits the product's languages | Single-user host; user language unknown (no i18n config) | Non-English memories over-filtered at query time |
| A-M-07 | `manager.py:23` | Constructing `MemoryManager()` from the UI with the default DB path is intended | Opens the **production** database from the settings dialog (F-MEM-013) | UI operations mutate prod data with no isolation |
| A-M-08 | `entities.py:84` | fuzz ratio ≥ 94 with same `type` is safe aliasing | Threshold is a magic number; no false-merge audit beyond the `alias_added` row | Distinct entities merged (e.g. two similarly-named projects) |
| A-M-09 | `store.py:428` | Local-time backup names are comparable for retention | DST/UTC ambiguity (F-MEM-019) | Retention decisions made on ambiguous timestamps |
| A-M-10 | `db.py:57` | `isolation_level=None` + explicit BEGIN/COMMIT everywhere is safe with `check_same_thread=False` | Single-writer discipline relies on the asyncio lock in `store` only; `MemoryManager`/router paths skip it (F-MEM-009) | Intermittent `database is locked` under concurrency |

## 5. Questions register

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| Q-M-01 | Should `tool_contents` be wired as the `TOOL_CONTENT_UNTRUSTED` store when F-CORE-019 is remediated, or dropped? | F-MEM-007 remediation shape; determines whether untrusted bodies become referencable | owner / architect |
| Q-M-02 | Is backup retention "14 calendar days + 8 Sundays" or "newest 14 + 8 Sundays"? | F-MEM-019 remediation | owner |
| Q-M-03 | Should the UI admin memory feature exist at all as a user capability (with a dedicated admin provenance), or be removed/debug-gated? | F-MEM-001 remediation shape | owner |
| Q-M-04 | When the pipeline is wired, does `USER_EXPLICIT_LOWCONF` get the read-back confirmation flow (Spec 03) or is the tier removed? | F-MEM-004 | owner / architect |
| Q-M-05 | Should `mem_bi_eligible` (DB trigger) and `MEMORY_ELIGIBLE` (gate) be generated from one source of truth? | Today they agree; nothing enforces future agreement | architect |
| Q-M-06 | Is the single shared writer connection (`db.get_writer`) the intended concurrency model once four processes exist per ADR-008? | Cross-process writes to one SQLite file rely on busy_timeout alone | architect |

## 6. Coverage gaps

### 6.1 Spec'd behaviours with no mechanical test

| Spec'd behaviour | Source | Test status |
|---|---|---|
| Admin CRUD paths (`add_memory`/`update_memory`/`delete_memory`) | UI feature (`settings_dialog.py:255`) | **none** — `manager.py` at 41 % coverage; the one live write path is the least-tested module in the package |
| LOWCONF read-back/upgrade flow | Spec 03 | none (feature absent — F-MEM-004) |
| Known-dev-key rejection | TM-13 | none (feature absent — F-MEM-005) |
| Cross-instance replay protection | `gate_nonces` table | none (table write-only — F-MEM-010) |
| Identifier-exact retrieval lane | Spec 04 §6 (`exact_identifiers`) | none (field unused — F-MEM-015) |
| Embedding backfill | Spec 04 §4 | none (queue never drained — F-MEM-008) |
| `format_memory_context` caps/labelling | Spec 04 §6 / Spec 10 §4 | none for the function (untested lines 45–64); consumer missing (F-BRAIN-011) |
| `graph_neighbors` correctness | Spec 04 §6 | none (untested; F-MEM-014) |
| Grounding negative cases (T-GRND set beyond the 40-pair bench) | Spec 03 §5.2 | `test_grounding.py` covers positives + some negatives; quote-spanning-NFC edge cases untested |

### 6.2 Tests that pass without exercising the claimed mechanism

| Test | Claim | What it actually verifies |
|---|---|---|
| `test_memory_db.py::test_t_mem_01_and_02_identifier_benchmarks` | identifier retrieval benchmarks | hybrid path only; `exact_identifiers` lane absent (F-MEM-015) — the "identifier" fixtures pass through fuzzy retrieval |
| `test_provenance.py::test_t_prov_04_replay_rejection` | replay defence | same-instance dict only; no cross-instance/restart case (F-MEM-010) |
| `test_memory_db.py::test_t_mem_13_backups_and_integrity` | backup retention | exercises `backup()` once; never constructs enough backups to exercise the pruning branches (`store.py:446-476` untested) |
| `test_memory_db.py::test_t_mem_14_working_memory_discard` | task journal | open/set/close only; eviction/leak behaviour untested (F-MEM-016) |

## 7. Recursive review log

Second pass applied Charter §3.5's five questions to every DRAFT finding before setting `Status: OPEN`. Changes made:

1. **Oversights → new findings.** Reviewing F-MEM-001 (bypass) surfaced its siblings on the same admin paths: F-MEM-002 (edit invalidates envelope) and F-MEM-003 (delete destroys envelope). Reviewing F-MEM-006 (fabricated provenance) surfaced F-MEM-017 (the correct renderer exists unwired — the two findings are the same wiring gap seen from both sides). Reviewing F-MEM-008 (backfill) surfaced the read-path-write hazard F-MEM-009 (same writer-connection model). Reviewing F-MEM-005 (dead dev-key list) merged with the core Q-15 answer into F-MEM-018 rather than duplicating the master-key story.
2. **Unasked questions.** 6 questions registered (§5); anything answerable from code was answered in the finding (F-MEM-018 closes core Q-15/F-CORE-060 with the `TypeError`-before-guard fact and the no-construction-site fact).
3. **Unwarranted assumptions.** The first draft of F-MEM-001 asserted the admin path was "reachable from the UI" — verified at `settings_dialog.py:255` before grading; the first draft of F-MEM-010 called cross-restart replay "possible" — downgraded in the narrative to bounded-by-freshness (±300 s) and protected at commit by `ux_env_nonce`, keeping S3. F-MEM-019 was graded S4 after confirming retention never retains *fewer* than the documented policy.
4. **Incomplete planning.** Every remediation names file, function, before/after, and a runnable command; decisions that needed making were made in the finding (F-MEM-001: gate-verified admin commit; F-MEM-002: supersede-not-rewrite; F-MEM-003: soft-delete only; F-MEM-005: MEM-owned `assert_prod_master_key`; F-MEM-011: unconditional re-verification), with the two genuinely owner-owned calls parked in §5 (Q-M-01, Q-M-02).
5. **Architectural flaws → F-ARCH candidates.** (a) The provenance pipeline's total unwiring (F-CORE-003 + every "no caller in src/" row of §1) is programme-level — the audit's central invariant currently holds only because no data flows; (b) the dual-write-surface problem (gate-verified `MemoryStore.commit` vs gate-bypassing `MemoryManager`) is a structural trust-boundary defect that survives any wiring; (c) the durable-vs-in-memory split of gate state (`gate_nonces` write-only) reflects a design that never chose a process model — flagged for the ARCH roll-up alongside core.md §11's candidates.

Severity re-grades during the pass: F-MEM-001 kept S1 (not S0: the invariant is vacuously intact in the running product and the path is owner-facing UI, not an external attacker surface — flagged for owner revisit under Q-M-03); F-MEM-010 S2→S3 after quantifying the freshness/unique-index mitigations; F-MEM-018 S3→S4 (resolves a question; asserts no defect beyond the typed-guard nit).
