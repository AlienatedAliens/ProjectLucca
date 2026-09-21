"""
Unit and acceptance tests for Skill Package Format and Admin CLI.
Spec 1.1.2 §3, §13 Ladder L1a, Handover #4 Phase 3.

Acceptance Tests:
(a) register a valid package -> ACTIVE;
(b) missing recover.md -> refused;
(c) plan failing Z3 -> refused;
(d) failing golden trace -> refused;
(e) 31st ACTIVE skill -> refused with retirement prompt;
(f) retire -> package moved to _retired/, skill no longer fires, absent from manifest;
(g) >2 categories -> SkillMeta validation error.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lucca.admin import run_skills_cli
from lucca.brain.prompt_builder import format_category_manifest
from lucca.core.capabilities import get_default_native_tools
from lucca.core.schemas import RuleState, SkillMeta
from lucca.memory.db import DatabaseManager
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.skills import (
    SkillLimitExceededError,
    SkillManager,
    SkillNotFoundError,
    SkillValidationError,
)


def create_dummy_package(
    dest_dir: Path,
    skill_id: str = "test-skill-v1",
    intent: str = "calculate",
    categories: list[str] | None = None,
    expose_as_tool: bool = True,
    when_expr: str = '(intent= "calculate")',
    plan_action: str = '(tool "run_python" :code "1 + 1")',
    include_backup: bool = True,
    include_recover: bool = True,
    include_failure_dir: bool = True,
    traces: list[dict[str, object]] | None = None,
) -> Path:
    """Helper to create a skill package directory structure."""
    pkg_dir = dest_dir / skill_id
    pkg_dir.mkdir(parents=True, exist_ok=True)

    if categories is None:
        categories = ["cognitive_core"]

    meta = {
        "id": skill_id,
        "intent": intent,
        "description": f"Description for {skill_id}",
        "keywords": ["test", "calc"],
        "args": ["expr"],
        "status": "ACTIVE",
        "version": "1.0.0",
        "categories": categories,
        "expose_as_tool": expose_as_tool,
    }
    (pkg_dir / "meta_info.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    plan_scm = f"""(rule "{skill_id}"
  :when {when_expr}
  :plan (list {plan_action})
  :priority 10)
"""
    (pkg_dir / "plan.scm").write_text(plan_scm, encoding="utf-8")

    if include_backup:
        (pkg_dir / "backup.md").write_text(
            "# Alternative triggers\n- compute expr", encoding="utf-8"
        )

    if include_recover:
        (pkg_dir / "recover.md").write_text(
            "# Recovery policy\n- If execution fails, yield to core.", encoding="utf-8"
        )

    if include_failure_dir:
        f_dir = pkg_dir / "failure_examples"
        f_dir.mkdir(parents=True, exist_ok=True)
        (f_dir / ".gitkeep").write_text("", encoding="utf-8")

    if traces is None:
        traces = [
            {
                "id": f"{skill_id}-fire",
                "transcript": "calculate something",
                "intent": intent,
                "rule_fired": True,
                "expected_tool": "run_python",
            },
            {
                "id": f"{skill_id}-nofire",
                "transcript": "hello world",
                "intent": "greeting",
                "rule_fired": False,
            },
        ]

    lines = [json.dumps(t) for t in traces]
    (pkg_dir / "golden_traces.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return pkg_dir


@pytest.fixture
def isolated_env(tmp_path: Path):
    """Provides isolated DatabaseManager, RuleLifecycleManager, and SkillManager."""
    db_path = tmp_path / "memory.sqlite"
    db = DatabaseManager(db_path=db_path)
    db.migrate()

    skills_dir = tmp_path / "config" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    tools = get_default_native_tools()
    engine = RuleLifecycleManager(registered_tools=tools, db=db, skills_dir=skills_dir)
    manager = SkillManager(skills_dir=skills_dir, rule_engine=engine)

    return {
        "db": db,
        "db_path": db_path,
        "skills_dir": skills_dir,
        "engine": engine,
        "manager": manager,
        "tools": tools,
        "tmp_path": tmp_path,
    }


def test_a_register_valid_package_becomes_active(isolated_env) -> None:
    """(a) register a valid package -> ACTIVE."""
    env = isolated_env
    incoming_dir = env["tmp_path"] / "incoming"
    pkg_src = create_dummy_package(incoming_dir, "calc-eval-v1")

    pkg = env["manager"].register_package(pkg_src)
    assert pkg.meta.id == "calc-eval-v1"
    assert pkg.meta.status == "ACTIVE"

    # Verify on-disk presence in config/skills/calc-eval-v1
    installed_dir = env["skills_dir"] / "calc-eval-v1"
    assert installed_dir.exists()
    assert (installed_dir / "meta_info.json").exists()
    meta_on_disk = SkillMeta.model_validate_json(
        (installed_dir / "meta_info.json").read_text(encoding="utf-8")
    )
    assert meta_on_disk.status == "ACTIVE"

    # Verify presence in RuleLifecycleManager
    engine: RuleLifecycleManager = env["engine"]
    assert "calc-eval-v1" in engine.rules
    managed = engine.rules["calc-eval-v1"]
    assert managed.status == "ACTIVE"
    assert managed.expose_as_tool is True
    assert managed.categories == ["cognitive_core"]

    # Verify listing
    records = env["manager"].list_skills()
    assert any(r["id"] == "calc-eval-v1" and r["status"] == "ACTIVE" for r in records)


def test_b_missing_recover_md_refused(isolated_env) -> None:
    """(b) missing recover.md -> refused."""
    env = isolated_env
    incoming_dir = env["tmp_path"] / "incoming"
    pkg_src = create_dummy_package(
        incoming_dir,
        "missing-recover-v1",
        include_recover=False,
    )

    with pytest.raises(SkillValidationError, match="recover.md"):
        env["manager"].register_package(pkg_src)

    assert not (env["skills_dir"] / "missing-recover-v1").exists()
    assert "missing-recover-v1" not in env["engine"].rules


def test_c_plan_failing_z3_refused(isolated_env) -> None:
    """(c) plan failing Z3 -> refused."""
    env = isolated_env
    incoming_dir = env["tmp_path"] / "incoming"
    # Precondition contradiction: intent= "calc" AND intent= "notes" (UNSATISFIABLE)
    pkg_src = create_dummy_package(
        incoming_dir,
        "unsat-skill-v1",
        when_expr='(and (intent= "calculate") (intent= "notes"))',
    )

    with pytest.raises(SkillValidationError, match="UNSATISFIABLE|formal verification"):
        env["manager"].register_package(pkg_src)

    assert not (env["skills_dir"] / "unsat-skill-v1").exists()
    assert "unsat-skill-v1" not in env["engine"].rules


def test_d_failing_golden_trace_refused(isolated_env) -> None:
    """(d) failing golden trace -> refused."""
    env = isolated_env
    incoming_dir = env["tmp_path"] / "incoming"
    # Provide bad trace: rule_fired=True expected on greeting transcript where rule won't fire
    bad_traces: list[dict[str, object]] = [
        {
            "id": "bad-fire-trace",
            "transcript": "good morning",
            "intent": "greeting",
            "rule_fired": True,  # Will fail because when_expr requires intent= "calculate"
        },
        {
            "id": "good-nofire-trace",
            "transcript": "hello world",
            "intent": "greeting",
            "rule_fired": False,
        },
    ]
    pkg_src = create_dummy_package(
        incoming_dir,
        "bad-trace-v1",
        traces=bad_traces,
    )

    with pytest.raises(SkillValidationError, match="failed: expected rule_fired=True, got False"):
        env["manager"].register_package(pkg_src)

    assert not (env["skills_dir"] / "bad-trace-v1").exists()


def test_e_thirty_first_active_skill_refused_with_retirement_prompt(isolated_env) -> None:
    """(e) 31st ACTIVE skill -> refused with retirement prompt."""
    env = isolated_env
    incoming_dir = env["tmp_path"] / "incoming"

    # Register 30 active skills
    for i in range(1, 31):
        skill_id = f"skill-{i:02d}-v1"
        pkg_src = create_dummy_package(
            incoming_dir,
            skill_id,
            when_expr=f'(intent= "calc_{i}")',
            traces=[
                {"id": "fire", "intent": f"calc_{i}", "rule_fired": True},
                {"id": "nofire", "intent": "other", "rule_fired": False},
            ],
        )
        env["manager"].register_package(pkg_src)

    assert env["manager"].count_active_skills() == 30

    # Attempt to register the 31st skill
    pkg_31 = create_dummy_package(
        incoming_dir,
        "skill-31-v1",
        when_expr='(intent= "calc_31")',
        traces=[
            {"id": "fire", "intent": "calc_31", "rule_fired": True},
            {"id": "nofire", "intent": "other", "rule_fired": False},
        ],
    )

    with pytest.raises(SkillLimitExceededError) as exc_info:
        env["manager"].register_package(pkg_31)

    err_msg = str(exc_info.value)
    assert "Active skill limit reached (30/30)" in err_msg
    assert "Please retire an active skill before registering a new one" in err_msg
    assert "lucca-admin skills retire" in err_msg


def test_f_retire_moves_package_stops_firing_absent_from_manifest(isolated_env) -> None:
    """(f) retire -> package moved, skill no longer fires, absent from manifest."""
    env = isolated_env
    incoming_dir = env["tmp_path"] / "incoming"
    pkg_src = create_dummy_package(
        incoming_dir,
        "retire-target-v1",
        categories=["cognitive_core"],
        expose_as_tool=True,
    )

    env["manager"].register_package(pkg_src)
    engine: RuleLifecycleManager = env["engine"]

    # 1. Verify it fires when ACTIVE
    calc_state = RuleState(intent="calculate")
    active_outcomes = engine.evaluate(calc_state, mode="active")
    assert any(o.rule_id == "retire-target-v1" and o.fired for o in active_outcomes)

    # Verify present in manifest
    active_metas = engine.get_active_skill_metas()
    manifest_before = format_category_manifest("cognitive_core", active_metas)
    assert "retire-target-v1" in manifest_before

    # 2. Retire the skill
    dest_retired = env["manager"].retire_skill("retire-target-v1")
    assert dest_retired.exists()
    assert dest_retired == env["skills_dir"] / "_retired" / "retire-target-v1"
    assert not (env["skills_dir"] / "retire-target-v1").exists()

    # Verify status in meta_info.json is RETIRED
    retired_meta = SkillMeta.model_validate_json(
        (dest_retired / "meta_info.json").read_text(encoding="utf-8")
    )
    assert retired_meta.status == "RETIRED"

    # 3. Verify it no longer fires in active mode
    active_outcomes_after = engine.evaluate(calc_state, mode="active")
    assert not any(o.rule_id == "retire-target-v1" for o in active_outcomes_after)

    # 4. Verify it is absent from category manifest
    metas_after = engine.get_active_skill_metas()
    assert not any(m.id == "retire-target-v1" for m in metas_after)
    manifest_after = format_category_manifest("cognitive_core", metas_after)
    assert "retire-target-v1" not in manifest_after


def test_g_more_than_two_categories_rejected() -> None:
    """(g) >2 categories -> SkillMeta validation error."""
    with pytest.raises(ValidationError) as exc_info:
        SkillMeta(
            id="three-cat-skill-v1",
            intent="calculate",
            categories=["cognitive_core", "information", "self"],
        )

    err_str = str(exc_info.value)
    assert "Skill cannot declare more than 2 categories" in err_str


def test_cli_skills_commands_end_to_end(isolated_env, capsys) -> None:
    """Tests CLI commands (register, list, retire) end-to-end through run_skills_cli."""
    env = isolated_env
    incoming_dir = env["tmp_path"] / "incoming"
    pkg_src = create_dummy_package(incoming_dir, "cli-test-skill-v1")

    # 1. list when empty
    rc = run_skills_cli(
        action="list",
        db_path=env["db_path"],
        skills_dir=env["skills_dir"],
    )
    assert rc == 0

    # 2. register
    rc_reg = run_skills_cli(
        action="register",
        package_dir=str(pkg_src),
        db_path=env["db_path"],
        skills_dir=env["skills_dir"],
    )
    assert rc_reg == 0

    # 3. list shows active skill
    rc_list = run_skills_cli(
        action="list",
        db_path=env["db_path"],
        skills_dir=env["skills_dir"],
    )
    assert rc_list == 0

    # 4. retire
    rc_ret = run_skills_cli(
        action="retire",
        skill_id="cli-test-skill-v1",
        db_path=env["db_path"],
        skills_dir=env["skills_dir"],
    )
    assert rc_ret == 0

    # 5. retire nonexistent returns 1
    rc_ret_none = run_skills_cli(
        action="retire",
        skill_id="nonexistent-skill-v1",
        db_path=env["db_path"],
        skills_dir=env["skills_dir"],
    )
    assert rc_ret_none == 1
    with pytest.raises(SkillNotFoundError):
        env["manager"].retire_skill("nonexistent-skill-v1")
