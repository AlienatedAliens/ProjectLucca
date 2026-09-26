# R.2 Review — WO-20 Phase 4 (commit `5cb6661`) — **BOUNCE (1 blocker) + owner ratification needed**

**Reviewer:** Zoo. **Verdict: BOUNCE — one blocking defect; substance otherwise sound.**

## Review findings

### BLOCKER — F-P4-1: Migrations edited in place; existing databases cannot store INFERRED facts

`0001_init.sql` and `0006_autobiographical.sql` were **edited in place** to add `'INFERRED'` to the
`provenance_envelopes` CHECK constraint and the `mem_bi_eligible` trigger
([`0001_init.sql`](../src/lucca/memory/migrations/0001_init.sql)). This is correct for **new** databases only.

Every **existing** database (`C:\ProjectLucca\data\memory.sqlite`, any deployed install) already ran the old
migrations; its `provenance_envelopes` CHECK constraint and `mem_bi_eligible` trigger do **not** contain
`'INFERRED'`. Migrations are tracked in `schema_migrations`, so editing 0001/0006 will never re-run on them
(the tests pass because they build fresh DBs from the edited files — the test suite cannot see this failure).

**Consequence:** the first `finalize_chain()` against the live DB raises
`IntegrityError: provenance not memory-eligible` (or a CHECK violation on the envelope insert). The feature
is broken in production even though the suite is green.

**Exact fix (for implementing agent):**
1. Add `src/lucca/memory/migrations/0007_inferred_provenance.sql` that rebuilds `provenance_envelopes`
   with the widened CHECK (SQLite cannot ALTER a CHECK: create `provenance_envelopes_new` with the
   constraint, `INSERT ... SELECT` copy, drop, rename, recreate indexes/triggers referencing it), and
   recreates `mem_bi_eligible` with `'INFERRED'` added.
2. Revert the in-place edits to `0001_init.sql` and `0006_autobiographical.sql`? **No — keep them**, but
   note they must remain consistent with 0007 for fresh installs; alternatively revert them and let 0007 be
   the single source of the change for all DBs. Either is acceptable; pick one and document it in the
   migration docstring.
3. Add a migration test: create a DB with the **old** 0001 (git show the pre-edit blob), run
   `db.migrate()`, insert an INFERRED envelope, assert success.
4. Re-run full suite; re-submit R.1 with the new commit.

### Protocol breach — F-P4-2: STOP gate skipped (non-blocking, needs owner ratification now)

The plan's Phase 4 STOP gate required **presenting the INFERRED Belnap tier placement to the owner before
implementation**. The placement implemented — `USER_EXPLICIT (0) > USER_DERIVED (1) > INFERRED (2) >
LISP_ASSERTION (3)` — matches the plan's own text, so the substance is as-designed. **Owner: reply "ratified"
to this message to make the tier placement official** (no code change needed; this is the formal approval
the gate exists for). Logged here so the R.4 log can reference it.

### Verified as sound (prior reviewer, diff read)

- `ProvenanceGate` replay validation: every `INFERRED` premise resolves to an existing envelope; fabricated
  premise → `ProvenanceRejected` (test present). Matches ADR §"a trace with an unverified premise is rejected".
- `InferredFactSigner` via `SignerFactory.inferred_fact()` only — signer discipline holds.
- Supersession: direct `USER_EXPLICIT`/`USER_DERIVED` on the same predicate supersedes active `INFERRED`
  (bitemporal `valid_to`/`superseded_by` stamping) — matches Phase 4 manifest.
- Cascade/renderer framing `[deduced, confidence c]` — matches the DEDUCED→INFERRED doc convention
  (note: renderer says "deduced" while the tier is INFERRED — cosmetic inconsistency, note for WO-21).
- Scope: 12 files, all on-manifest. `731 passed` claimed; independent re-run required (below).

### Implementing agent's remaining steps

1. Implement F-P4-1's fix (migration 0007 + test with a pre-edit-schema DB).
2. Re-run: `uv run python -m pytest -q -m "not tier2 and not hw and not soak"` (expect 731+ passed).
3. Record in the R.4 log: `| 4 (INFERRED commit path) | 5cb6661 | implementing agent | reviewer (Zoo) | **BOUNCE→re-review after 0007** | 2026-09-26 |`.
4. **Do NOT start Phase 5 until the owner ratifies the tier placement (F-P4-2) and the BOUNCE fix lands.**
