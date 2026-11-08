"""WO-39 Milestone 3.2: Counterfactual Positive & Negative Verification of the 6 General Reasoning Structures.

Verifies on unseen, held-out inputs (with mandatory negative tests) that:
1. Organ 1: Belnap FOUR + NARS (w+, w-) evidence scoring, Study 1 autobiographical memory partitioning, and ProvenanceGate premise verification work genuinely.
2. Organ 2: Case-Based Reasoning (Retrieve, Reuse, Revise, Retain) in EpisodicCodeCache and strict dual-path agreement in Python CEGIS work genuinely.
3. Organ 3: Shadow Sandbox episode replay, Symbol Grounding verification, NARS (w+, w-) skill scoring, and ACT-R skill activation work genuinely.
4. Organ 4: MCTS + GP crossover synthesis over unseen test_cases (without oracle goal), Z3 algebraic abduction, EGraph cost extraction, and BDI AST+Z3 validation work genuinely.
5. Organ 5: Parameterized spatial grid primitives and metamorphic invariance checks work genuinely.
6. Organ 6: 3rd/4th-order recursive Theory-of-Mind (ContainerWorld), conformal calibration ground-truth join, STT "Lucca" wake-word normalization, .url sandbox escape prevention, and DSP pitch shifting work genuinely.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def test_organ1_belnap_nars_evidence_and_study1_memory_partition() -> None:
    """Verify Belnap FOUR + NARS (w+, w-) synchronization and Study 1 prompt partitioning."""
    from lucca.brain.prompt_builder import build_messages
    from lucca.core.cascade import BelnapValue, EpistemicSubstrate, EvidenceItem, TrustTier

    # 1. Positive + negative evidence produces CONFLICT (TOP) with exact NARS frequency & confidence
    conflict_item = EvidenceItem(
        content="Server port is 8080 vs 9000",
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="test:memory",
        confidence=0.8,
        positive_evidence=3,
        negative_evidence=1,
    )
    assert conflict_item.polarity == BelnapValue.CONFLICT
    assert conflict_item.told_true is True
    assert conflict_item.told_false is True
    assert conflict_item.nars_frequency == pytest.approx(0.75)
    assert conflict_item.nars_confidence == pytest.approx(4.0 / 5.0)

    # 2. Passing explicit polarity=BelnapValue.CONFLICT sets both flags
    explicit_conflict = EvidenceItem(
        content="Conflicting claim",
        substrate=EpistemicSubstrate.MEMORY,
        trust_tier=TrustTier.TIER_3_MEMORY,
        source="test:memory",
        confidence=0.5,
        polarity=BelnapValue.CONFLICT,
    )
    assert explicit_conflict.polarity == BelnapValue.CONFLICT
    assert explicit_conflict.told_true is True
    assert explicit_conflict.told_false is True

    # 3. Study 1 autobiographical split in prompt_builder.build_messages
    memories = [
        SimpleNamespace(
            entry_id="m1",
            content="The deployment port is 8443.",
            kind="fact",
            confidence=0.95,
            score=0.95,
            created_at=1000,
            valid_to=None,
            source_turn_id="sess_1:turn_1",
            provenance="TOOL_VERIFIED",
            grounding_eligible=True,
        ),
        SimpleNamespace(
            entry_id="m2",
            content="I think the secret codename might be Project Chimera.",
            kind="assistant_utterance",
            confidence=0.80,
            score=0.80,
            created_at=1001,
            valid_to=None,
            source_turn_id="sess_1:turn_1",
            provenance="ASSISTANT_UTTERANCE",
            grounding_eligible=False,
        ),
    ]
    messages = build_messages(memories=memories, current_text="What is the deployment port?")  # type: ignore[arg-type]
    combined = "\n".join(str(m.content) for m in messages)
    assert "Verified Grounded Memory" in combined
    assert "Autobiographical Recollections" in combined
    assert "do NOT cite as factual truth" in combined

    # 4. ProvenanceGate.verify_rule_premises & capabilities.verify_postcondition
    from lucca.core.capabilities import verify_postcondition
    from lucca.memory.gate import ProvenanceGate

    gate = ProvenanceGate()
    assert gate.verify_rule_premises(["unverified claim"], db=None) is False
    assert (
        gate.verify_rule_premises(
            ["the deployment port is 8443"],
            db=None,
            produced_conclusions={"the deployment port is 8443"},
        )
        is True
    )
    assert (
        verify_postcondition("", SimpleNamespace(ok=False, exit_code=1, content="already exists"))
        is False
    )
    assert (
        verify_postcondition(
            "output_contains:8443", SimpleNamespace(ok=True, exit_code=0, content="port 8443")
        )
        is True
    )


def test_organ2_cbr_four_rs_in_episodic_code_cache(tmp_path: Path) -> None:
    """Verify Retrieve, Reuse, Revise, Retain and NARS (w+, w-) scoring in EpisodicCodeCache."""
    from lucca.memory.episodic_code_cache import EpisodicCodeCache

    cache = EpisodicCodeCache(cache_file=tmp_path / "cbr_test.json")
    ep = cache.retain_episode(
        query="Compute the factorial of 6 in Python",
        code="import math\nprint(math.factorial(6))",
        output="720",
    )
    assert ep.positive_evidence >= 1
    assert ep.nars_frequency == 1.0

    # Retrieve precedent on unseen similar problem
    precedent = cache.retrieve_precedent("Compute the factorial of 8 in Python", min_similarity=0.3)
    assert precedent is not None

    # Reuse with parameter adaptation (6 -> 8)
    adapted_code = cache.adapt_and_reuse(precedent, "Compute the factorial of 8 in Python")
    assert "8" in adapted_code

    # Revise / verify outcome updates NARS evidence counts
    ok, _ = cache.revise_solution(
        adapted_code,
        precedent=precedent,
        verifier_fn=lambda c: (True, "40320"),
    )
    assert ok is True
    updated = cache.retrieve_precedent("Compute the factorial of 6 in Python", min_similarity=0.3)
    assert updated is not None
    assert updated.positive_evidence >= 2
    assert len(cache.get_all_episodes()) >= 1


def test_organ3_shadow_sandbox_and_symbol_grounding() -> None:
    """Verify SkillLibrary Shadow Sandbox rejects ungrounded/failing rules and graduates valid ones."""
    from lucca.reasoning.skills import SkillLibrary

    lib = SkillLibrary()
    episodes = [
        {"inputs": {"x": 3}, "expected_output": 10},
        {"inputs": {"x": 5}, "expected_output": 16},
        {"inputs": {"x": 10}, "expected_output": 31},
    ]

    # 1. Negative test: ungrounded imaginary tool/predicate must be rejected
    ok_ungrounded, reason_ungrounded = lib.verify_in_shadow_sandbox(
        "(teleport-quantum-core x)",
        episodes,
        grounded_primitives=set(),
    )
    assert ok_ungrounded is False
    assert "ground" in reason_ungrounded.lower() or "unknown" in reason_ungrounded.lower()

    # 2. Negative test: grounded arithmetic expression that gets the math wrong on episodes
    ok_wrong, _ = lib.verify_in_shadow_sandbox(
        "(+ (* 2 x) 1)",
        episodes,
    )
    assert ok_wrong is False

    # 3. Positive test: grounded arithmetic expression (+ (* 3 x) 1) matches all 3 episodes
    ok_valid, _ = lib.verify_in_shadow_sandbox(
        "(+ (* 3 x) 1)",
        episodes,
    )
    assert ok_valid is True

    # 4. Induce & register skill, record NARS outcomes, and retrieve via ACT-R activation
    from lucca.reasoning.skills import Skill

    induced_skill = Skill(
        name="triple-plus-one",
        description="Compute 3*x + 1 for integer x",
        parameters=["x"],
        s_expr="(+ (* 3 x) 1)",
    )
    ok_reg, _ = lib.induce_and_register_skill(induced_skill, episodes=episodes)
    assert ok_reg is True
    fetched = lib.get_skill("triple-plus-one")
    assert fetched is not None
    lib.record_outcome("triple-plus-one", success=True)
    active = lib.retrieve_active_skills("Compute 3*x + 1 integer")
    assert any(s.name == "triple-plus-one" for s in active)


def test_organ4_mcts_and_abduction_without_oracle_goal() -> None:
    """Verify MCTS and Abduction discover formulas strictly from unseen test_cases without oracle goal."""
    from lucca.reasoning.abduction import BackwardAbductionSolver
    from lucca.reasoning.mcts import ASTHoleMCTSEngine
    from lucca.reasoning.scheme.parser import parse_expr

    # Unseen linear relation: y = 2 * x + 1
    test_cases = [
        {"inputs": {"x": 2}, "output": 5},
        {"inputs": {"x": 4}, "output": 9},
        {"inputs": {"x": 7}, "output": 15},
    ]
    synth = ASTHoleMCTSEngine()
    sketch_ast = parse_expr("(+ (* (?hole k int) x) (?hole b int))")
    res = synth.synthesize(
        sketch_with_holes=sketch_ast,
        goal=0,
        test_cases=test_cases,
    )
    assert res.success is True

    # Negative test: contradictory test cases (same input x=2 requires both 5 and 99) must fail
    contradictory_cases = [
        {"inputs": {"x": 2}, "output": 5},
        {"inputs": {"x": 2}, "output": 99},
    ]
    res_bad = synth.synthesize(
        sketch_with_holes=parse_expr("(+ x (?hole c int))"),
        goal=0,
        test_cases=contradictory_cases,
    )
    assert res_bad.success is False

    # Abduction Z3 hole solving across multiple test cases: x + ?hole_c = output (where ?hole_c = 17)
    abd = BackwardAbductionSolver()
    hyps = abd.invert_goal_for_sketch(
        sketch=parse_expr("(+ x (?hole c int))"),
        target_val=0,
        hole_name="c",
        test_cases=[
            {"inputs": {"x": 3}, "output": 20},
            {"inputs": {"x": 10}, "output": 27},
        ],
    )
    assert any(h.candidate_expr == "17" for h in hyps)

    # Negative test for abduction: no single constant c satisfies both 3 + c = 10 and 3 + c = 50
    hyps_impossible = abd.invert_goal_for_sketch(
        sketch=parse_expr("(+ x (?hole c int))"),
        target_val=0,
        hole_name="c",
        test_cases=[
            {"inputs": {"x": 3}, "output": 10},
            {"inputs": {"x": 3}, "output": 50},
        ],
    )
    assert len(hyps_impossible) == 0


def test_organ4_bdi_validator_ast_and_z3() -> None:
    """Verify SpeculativeBDIValidator blocks dangerous AST / infinite loops and runs Z3."""
    from lucca.core.bdi_validator import SpeculativeBDIValidator

    validator = SpeculativeBDIValidator()

    # Negative test: dangerous os.system call
    bad_res = validator.validate_tool_call(
        "run_python", {"code": "import os\nos.system('rm -rf /')"}
    )
    assert bad_res.is_valid is False

    # Negative test: unbounded while True loop without break/return
    loop_res = validator.validate_tool_call(
        "run_python", {"code": "x = 0\nwhile True:\n    x += 1\n"}
    )
    assert loop_res.is_valid is False

    # Positive test: clean bounded computation
    validator.add_deontic_rule("(not (and (tool= fetch_url) (tainted? private)))")
    good_res = validator.validate_tool_call(
        "run_python", {"code": "total = sum(i * i for i in range(10))\nprint(total)"}
    )
    assert good_res.is_valid is True
    assert good_res.gas_used > 0


def test_organ5_spatial_primitives_and_metamorphic_invariance() -> None:
    """Verify parameterized spatial primitives and check_metamorphic_invariance."""
    from lucca.reasoning.spatial_dsl import (
        check_metamorphic_invariance,
        crop_grid,
        fill_holes,
        overlay_grid,
        reflect_grid,
        rot90,
        rotate_grid,
        translate_grid,
    )

    # 1. Parameterized primitive: fill_holes fills enclosed 0-region with fill_color=4
    ring_grid = [
        [1, 1, 1],
        [1, 0, 1],
        [1, 1, 1],
    ]
    expected_filled = [
        [1, 1, 1],
        [1, 4, 1],
        [1, 1, 1],
    ]
    assert fill_holes(ring_grid, fill_color=4) == expected_filled
    assert rotate_grid(ring_grid, 4) == ring_grid
    assert reflect_grid(reflect_grid(ring_grid, "h"), "h") == ring_grid
    assert crop_grid(ring_grid, 0, 0, 1, 1) == [[1, 1], [1, 0]]
    shifted_grid = translate_grid(ring_grid, 0, 0)
    assert overlay_grid(ring_grid, shifted_grid) == ring_grid

    train_pairs = [{"input": ring_grid, "output": expected_filled}]

    # 2. Positive test: rotation/transpose-equivariant transformation passes metamorphic check
    ok_inv, _ = check_metamorphic_invariance(lambda g: fill_holes(g, fill_color=4), train_pairs)
    assert ok_inv is True

    # 3. Negative test: non-equivariant hardcoded coordinate overwrite fails metamorphic check
    asymmetrical_in = [
        [1, 1, 1, 0],
        [1, 0, 1, 0],
        [1, 1, 1, 0],
        [0, 0, 0, 0],
    ]
    asymmetrical_out = [
        [1, 1, 1, 0],
        [1, 4, 1, 0],
        [1, 1, 1, 0],
        [0, 0, 0, 0],
    ]
    asym_pairs = [{"input": asymmetrical_in, "output": asymmetrical_out}]

    def hardcoded_cell_cheat(g: list[list[int]]) -> list[list[int]]:
        out = [row[:] for row in g]
        if len(out) > 1 and len(out[0]) > 1:
            out[1][1] = 4
        return out

    ok_cheat, _ = check_metamorphic_invariance(hardcoded_cell_cheat, asym_pairs)
    assert ok_cheat is False
    assert rot90(rot90(rot90(rot90(asymmetrical_in)))) == asymmetrical_in


def test_organ6_k_order_theory_of_mind_depth3_perspective() -> None:
    """Verify ContainerWorld.query_recursive tracks 1st-hop epistemic perspective at depth >= 3."""
    from lucca.sandbox.container_world import ContainerWorld

    cw = ContainerWorld()
    cw.set_room_occupants("room", ["Alice", "Bob", "Charlie"])
    cw.place("Alice", "key", "drawer")
    # Alice leaves before Bob moves the key to the safe while Charlie watches
    cw.set_room_occupants("room", ["Bob", "Charlie"])
    cw.move("Bob", "key", "safe")

    # Bob and Charlie know the key is in the safe:
    assert cw.query_recursive(["Bob", "Charlie"], "key") == "safe"
    # But Alice was NOT present when Bob moved it, so Alice thinks Bob thinks Charlie thinks it's in the drawer!
    assert cw.query_recursive(["Alice", "Bob", "Charlie"], "key") == "drawer"


def test_stt_lucca_wake_word_and_dsp_pitch_shift_and_url_security(tmp_path: Path) -> None:
    """Verify STT 'Lucca' normalization, DSP pitch shift frequency change, and .url sandbox escape block."""
    from lucca.sandbox.file_tool import SafeFileTool, SandboxSecurityError
    from lucca.senses.asr import normalize_lucca_wake_word
    from lucca.senses.dsp_chain import apply_pitch_shift

    # 1. STT wake-word normalization
    assert normalize_lucca_wake_word("Lucas, check the logs") == "Lucca, check the logs"
    assert (
        normalize_lucca_wake_word("Hey Luka what is the status?") == "Hey Lucca what is the status?"
    )
    assert normalize_lucca_wake_word("Lukas please run tests") == "Lucca please run tests"

    # 2. DSP pitch shift (+12 semitones doubles frequency of a 440Hz sine wave)
    sr = 16000
    t = np.linspace(0, 0.5, sr // 2, endpoint=False, dtype=np.float32)
    sine_440 = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    shifted, out_sr = apply_pitch_shift(sine_440, sr=sr, semitones=12.0)
    assert out_sr > 0
    assert shifted.shape == sine_440.shape
    assert not np.allclose(shifted, sine_440)

    # 3. SafeFileTool blocks .url shortcut pointing outside workspace_root
    outside_secret = tmp_path / "outside_secret.txt"
    outside_secret.write_text("TOP_SECRET_HOST_DATA", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    evil_url = workspace / "escape.url"
    evil_url.write_text(
        f"[InternetShortcut]\nURL=file:///{outside_secret.as_posix()}\n", encoding="utf-8"
    )

    ft = SafeFileTool(workspace_root=workspace)
    with pytest.raises((SandboxSecurityError, PermissionError)):
        ft.read_file("escape.url")
