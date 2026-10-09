"""
Test Battery: WO-33 — Transactional Git Staging DAG (Module 8) & Belnap Latent Investigator (Module 10)
Enforces:
- Atomic workspace commits & zero dirty state on rollback
- DAG cycle detection & dependency validation
- Belnap-Dunn 4-valued lattice logic (TRUE, FALSE, NEITHER, BOTH)
- Non-destructive epistemic probing and contradiction handling
- Invariants: Zero-Any typing, sub-millisecond execution, ΔVRAM = 0 MB
"""

from __future__ import annotations

import os
from pathlib import Path
import time
import pytest

from lucca.memory.git_dag import (
    CycleDetectedError,
    GitStagingDAG,
    MissingDependencyError,
    OperationType,
    StagedOperation,
    StagingTransaction,
)
from lucca.memory.latent_probe import (
    BelnapLatentInvestigator,
    BelnapValue,
    LatentProbeRequest,
    ProbeActionRecommendation,
    ProbeTargetType,
    belnap_negation,
    information_join,
    information_meet,
    truth_join,
    truth_meet,
)


# ==============================================================================
# Module 8: Git Staging DAG Tests
# ==============================================================================


def test_git_dag_linear_topological_order() -> None:
    """Verifies that dependency order is respected in topological sort."""
    dag = GitStagingDAG()
    op1 = StagedOperation(
        op_id="op_1",
        op_type=OperationType.CREATE_DIR,
        path=Path("build"),
        dependencies=[],
    )
    op2 = StagedOperation(
        op_id="op_2",
        op_type=OperationType.WRITE_FILE,
        path=Path("build/module.py"),
        content="x = 1",
        dependencies=["op_1"],
    )
    op3 = StagedOperation(
        op_id="op_3",
        op_type=OperationType.WRITE_FILE,
        path=Path("build/test.py"),
        content="assert True",
        dependencies=["op_2"],
    )

    # Add in arbitrary order
    dag.add_operation(op3)
    dag.add_operation(op1)
    dag.add_operation(op2)

    assert dag.has_cycle() is False
    order = dag.topological_order()
    ordered_ids = [op.op_id for op in order]
    assert ordered_ids == ["op_1", "op_2", "op_3"]


def test_git_dag_cycle_detection() -> None:
    """Verifies that circular dependencies are caught and raise CycleDetectedError."""
    dag = GitStagingDAG()
    op1 = StagedOperation(
        op_id="op_1",
        op_type=OperationType.WRITE_FILE,
        path=Path("a.txt"),
        dependencies=["op_3"],
    )
    op2 = StagedOperation(
        op_id="op_2",
        op_type=OperationType.WRITE_FILE,
        path=Path("b.txt"),
        dependencies=["op_1"],
    )
    op3 = StagedOperation(
        op_id="op_3",
        op_type=OperationType.WRITE_FILE,
        path=Path("c.txt"),
        dependencies=["op_2"],
    )

    dag.add_operation(op1)
    dag.add_operation(op2)
    dag.add_operation(op3)

    assert dag.has_cycle() is True
    with pytest.raises(CycleDetectedError):
        dag.topological_order()


def test_git_dag_missing_dependency() -> None:
    """Verifies that referencing a non-existent op_id raises MissingDependencyError."""
    dag = GitStagingDAG()
    op = StagedOperation(
        op_id="op_1",
        op_type=OperationType.WRITE_FILE,
        path=Path("test.txt"),
        dependencies=["non_existent_op"],
    )
    dag.add_operation(op)

    with pytest.raises(MissingDependencyError):
        dag.validate_dependencies()


def test_staging_transaction_atomic_commit(tmp_path: Path) -> None:
    """Verifies successful multi-file atomic commit to disk."""
    tx = StagingTransaction(workspace_root=tmp_path)
    tx.begin()

    dir_path = tmp_path / "pkg"
    file1 = dir_path / "main.py"
    file2 = dir_path / "config.json"

    tx.stage_mkdir(dir_path)
    tx.stage_write(file1, "print('hello')", dependencies=["mkdir_0001"])
    tx.stage_write(file2, '{"active": true}', dependencies=["mkdir_0001"])

    res = tx.commit()
    assert res.success is True
    assert res.operations_executed == 3
    assert file1.exists()
    assert file1.read_text(encoding="utf-8") == "print('hello')"
    assert file2.exists()
    assert file2.read_text(encoding="utf-8") == '{"active": true}'


def test_staging_transaction_rollback_preserves_clean_state(tmp_path: Path) -> None:
    """
    Verifies that a failed commit or rollback restores baseline:
    - Existing file retains original text
    - New file is deleted from disk
    """
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("original content", encoding="utf-8")
    new_file = tmp_path / "new.txt"

    # Validator that rejects "new.txt"
    def fail_on_new(op: StagedOperation) -> tuple[bool, str | None]:
        if "new.txt" in str(op.path):
            return False, "Forbidden file creation"
        return True, None

    tx = StagingTransaction(workspace_root=tmp_path, validators=[fail_on_new])
    tx.begin()
    tx.stage_write(existing_file, "overwritten content")
    tx.stage_write(new_file, "this should never persist")

    res = tx.commit()
    assert res.success is False
    assert "Forbidden file creation" in (res.error_message or "")

    # Check disk state
    assert existing_file.read_text(encoding="utf-8") == "original content"
    assert not new_file.exists()


def test_staging_transaction_diff_preview(tmp_path: Path) -> None:
    """Verifies that compute_diffs produces accurate unified diffs without touching disk."""
    target_file = tmp_path / "sample.py"
    target_file.write_text("def run():\n    return 1\n", encoding="utf-8")

    tx = StagingTransaction(workspace_root=tmp_path)
    tx.begin()
    tx.stage_write(target_file, "def run():\n    return 2\n")

    diffs = tx.dag.compute_diffs()
    assert target_file in diffs
    diff_text = diffs[target_file]
    assert "-    return 1" in diff_text
    assert "+    return 2" in diff_text
    # Disk unchanged
    assert target_file.read_text(encoding="utf-8") == "def run():\n    return 1\n"


# ==============================================================================
# Module 10: Belnap Latent Investigator Tests
# ==============================================================================


def test_belnap_lattice_algebra() -> None:
    """Tests the mathematical properties of the Belnap-Dunn 4-valued lattice."""
    T = BelnapValue.TRUE
    F = BelnapValue.FALSE
    BOT = BelnapValue.NEITHER
    TOP = BelnapValue.BOTH

    # Negation
    assert belnap_negation(T) == F
    assert belnap_negation(F) == T
    assert belnap_negation(BOT) == BOT
    assert belnap_negation(TOP) == TOP

    # Information join (combining evidence)
    assert information_join(T, F) == TOP  # Evidence for both truth and falsity = Contradiction
    assert information_join(BOT, T) == T
    assert information_join(BOT, F) == F
    assert information_join(TOP, T) == TOP

    # Information meet (shared evidence)
    assert information_meet(T, F) == BOT  # No shared evidence between disjoint polarities
    assert information_meet(TOP, T) == T
    assert information_meet(BOT, T) == BOT

    # Truth meet (AND)
    assert truth_meet(T, T) == T
    assert truth_meet(T, F) == F
    assert truth_meet(F, F) == F
    assert truth_meet(T, BOT) == BOT

    # Truth join (OR)
    assert truth_join(F, F) == F
    assert truth_join(T, F) == T
    assert truth_join(F, BOT) == BOT
    assert truth_join(T, BOT) == T


def test_belnap_investigator_filesystem_probe(tmp_path: Path) -> None:
    """Verifies non-destructive filesystem probe valuations."""
    investigator = BelnapLatentInvestigator()
    present_file = tmp_path / "exists.txt"
    present_file.write_text("data", encoding="utf-8")
    absent_file = tmp_path / "absent.txt"

    # Positive claim on present file -> TRUE
    res1 = investigator.investigate_filesystem(present_file, claim_exists=True)
    assert res1.belnap_value == BelnapValue.TRUE
    assert res1.recommendation == ProbeActionRecommendation.ACCEPT_AS_TRUE

    # Positive claim on absent file -> FALSE
    res2 = investigator.investigate_filesystem(absent_file, claim_exists=True)
    assert res2.belnap_value == BelnapValue.FALSE
    assert res2.recommendation == ProbeActionRecommendation.ACCEPT_AS_FALSE

    # Negative claim on absent file -> TRUE
    res3 = investigator.investigate_filesystem(absent_file, claim_exists=False)
    assert res3.belnap_value == BelnapValue.TRUE
    assert res3.recommendation == ProbeActionRecommendation.ACCEPT_AS_TRUE


def test_belnap_investigator_env_var_probe() -> None:
    """Verifies environment variable probing."""
    investigator = BelnapLatentInvestigator()
    var_name = "LUCCA_TEST_BELNAP_ENV"
    os.environ[var_name] = "active_mode"

    try:
        # Match expected
        res_match = investigator.investigate_env_var(var_name, expected_val="active_mode")
        assert res_match.belnap_value == BelnapValue.TRUE

        # Mismatch expected -> Contradiction (BOTH)
        res_mismatch = investigator.investigate_env_var(var_name, expected_val="disabled_mode")
        assert res_mismatch.belnap_value == BelnapValue.BOTH
        assert res_mismatch.recommendation == ProbeActionRecommendation.SOLICIT_USER_CLARIFICATION

        # Unset var -> NEITHER
        res_unset = investigator.investigate_env_var("NON_EXISTENT_VAR_12345")
        assert res_unset.belnap_value == BelnapValue.NEITHER
    finally:
        del os.environ[var_name]


def test_belnap_investigator_memory_conflict_and_clarification() -> None:
    """Verifies detection of conflicting beliefs and generation of clarification prompt."""
    investigator = BelnapLatentInvestigator()

    premise = "User works remotely on Mondays"
    hypothesis = "User does not work remotely on Mondays"

    res = investigator.investigate_memory_conflict(premise, hypothesis)
    assert res.belnap_value == BelnapValue.BOTH
    assert res.recommendation == ProbeActionRecommendation.SOLICIT_USER_CLARIFICATION
    assert res.clarification_prompt is not None
    assert "User works remotely on Mondays" in res.clarification_prompt
    assert "User does not work remotely on Mondays" in res.clarification_prompt


def test_belnap_investigator_combine_evidence() -> None:
    """Verifies information join evidence accumulation across multiple probes."""
    investigator = BelnapLatentInvestigator()

    # Probe 1: File exists (TRUE)
    p1 = investigator.investigate_filesystem("dummy_path", claim_exists=True)
    p1.belnap_value = BelnapValue.TRUE

    # Probe 2: Memory contradicts (FALSE)
    p2 = investigator.investigate_filesystem("dummy_path", claim_exists=False)
    p2.belnap_value = BelnapValue.FALSE

    # Combining TRUE + FALSE produces BOTH (⊤)
    combined = investigator.combine_evidence([p1, p2])
    assert combined.belnap_value == BelnapValue.BOTH
    assert combined.recommendation == ProbeActionRecommendation.SOLICIT_USER_CLARIFICATION


def test_wo33_sub_millisecond_latency() -> None:
    """Enforces sub-millisecond execution budget on DAG operations and Belnap logic."""
    dag = GitStagingDAG()
    for i in range(20):
        dag.add_operation(
            StagedOperation(
                op_id=f"op_{i}",
                op_type=OperationType.WRITE_FILE,
                path=Path(f"file_{i}.txt"),
                content="x",
                dependencies=[f"op_{i-1}"] if i > 0 else [],
            )
        )

    t0 = time.perf_counter()
    order = dag.topological_order()
    t_dag = (time.perf_counter() - t0) * 1000.0
    assert len(order) == 20
    assert t_dag < 1.0, f"DAG sort took {t_dag:.3f}ms (must be < 1.0ms)"

    investigator = BelnapLatentInvestigator()
    t0 = time.perf_counter()
    _ = investigator.investigate_memory_conflict("Fact A", "Not Fact A")
    t_belnap = (time.perf_counter() - t0) * 1000.0
    assert t_belnap < 1.0, f"Belnap probe took {t_belnap:.3f}ms (must be < 1.0ms)"


def test_staged_operation_content_hash_and_stage_delete(tmp_path: Path) -> None:
    """Verifies content hash computation and stage_delete lifecycle."""
    op = StagedOperation(
        op_id="op_hash",
        op_type=OperationType.WRITE_FILE,
        path=tmp_path / "hash.txt",
        content="hello world",
    )
    h = op.compute_content_hash()
    assert h is not None
    assert len(h) == 64

    # Test stage_delete
    del_file = tmp_path / "to_delete.txt"
    del_file.write_text("delete me", encoding="utf-8")
    assert del_file.exists()

    tx = StagingTransaction(workspace_root=tmp_path)
    tx.begin()
    tx.stage_delete(del_file)
    res = tx.commit()
    assert res.success is True
    assert not del_file.exists()


def test_latent_probe_request_schema() -> None:
    """Verifies LatentProbeRequest specification creation and attributes."""
    req = LatentProbeRequest(
        probe_id="probe_001",
        target_type=ProbeTargetType.MEMORY_ASSERTION,
        target_identifier="user_pref_coffee",
        claim_assertion="User drinks coffee",
        expected_truth_polarity=True,
    )
    assert req.probe_id == "probe_001"
    assert req.target_type == ProbeTargetType.MEMORY_ASSERTION
    assert req.expected_truth_polarity is True

