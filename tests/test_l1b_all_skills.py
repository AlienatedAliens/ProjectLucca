"""
Phase 5 (L1b & T2 Complete): Acceptance Tests for all 16 Factory Skills
Spec 1.1.2 §3, §4.2 Expressibility Table, §13 Ladder L1, Handover #5.
"""

from pathlib import Path

import pytest

from lucca.brain.prompt_builder import format_category_manifest
from lucca.core.capabilities import dispatch_invoke_skill, get_default_native_tools
from lucca.core.exceptions import SchemeYieldSignal
from lucca.core.schemas import RuleState, ToolCall
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.skills import SkillManager, SkillPackage

FACTORY_SKILL_MANIFEST: dict[str, tuple[bool, list[str]]] = {
    # 12 tool-call skills
    "calc-eval-v1": (True, ["cognitive_core", "self"]),
    "unit-convert-v1": (True, ["cognitive_core"]),
    "quick-fact-v1": (True, ["information"]),
    "define-term-v1": (True, ["information"]),
    "memory-brief-v1": (True, ["cognitive_core", "self"]),
    "note-take-v1": (True, ["cognitive_core", "self"]),
    "self-health-v1": (True, ["self"]),
    "recent-context-v1": (True, ["cognitive_core", "self"]),
    "resource-report-v1": (True, ["self"]),
    "sys-specs-v1": (True, ["host_readonly"]),
    "proc-top-v1": (True, ["host_readonly"]),
    "session-recap-v1": (True, ["companion", "cognitive_core"]),
    # 1 pure-say skill
    "time-greeting-v1": (False, ["companion"]),
    # 1 barge-in skill
    "barge-in-sorry-v1": (False, ["companion"]),
    # 2 yield-shortcut skills
    "plan-decompose-v1": (False, ["cognitive_core"]),
    "correction-ack-v1": (False, ["cognitive_core"]),
}


@pytest.fixture
def skills_engine() -> RuleLifecycleManager:
    """RuleLifecycleManager initialized with repo config/skills/."""
    skills_dir = Path("config/skills")
    tools = get_default_native_tools()
    return RuleLifecycleManager(skills_dir=skills_dir, registered_tools=tools)


def test_all_16_skills_registered_active_and_validated(skills_engine: RuleLifecycleManager) -> None:
    """
    Assert all 16 factory skills:
    1. Exist in config/skills.
    2. Pass structural, formal Z3 SMT, and trace validation via SkillPackage.load_and_validate.
    3. Are loaded into RuleLifecycleManager with status ACTIVE and matching metadata.
    4. Are counted by SkillManager within the 30-cap (exactly 16 active).
    """
    tools = get_default_native_tools()
    skills_dir = Path("config/skills")

    assert len(FACTORY_SKILL_MANIFEST) == 16, "Must have exactly 16 factory skills"

    for skill_id, (expected_exposed, expected_cats) in FACTORY_SKILL_MANIFEST.items():
        pkg_dir = skills_dir / skill_id
        assert pkg_dir.exists() and pkg_dir.is_dir(), f"Missing package dir for {skill_id}"

        # 1. Structural, formal Z3, and golden trace validation
        pkg = SkillPackage.load_and_validate(pkg_dir, tools)
        assert pkg.meta.id == skill_id
        assert pkg.meta.status == "ACTIVE"
        assert pkg.meta.expose_as_tool == expected_exposed
        for cat in expected_cats:
            assert cat in pkg.meta.categories

        # 2. Engine status
        assert skill_id in skills_engine.rules, f"{skill_id} not registered in engine"
        managed = skills_engine.rules[skill_id]
        assert managed.status == "ACTIVE"
        assert managed.expose_as_tool == expected_exposed
        for cat in expected_cats:
            assert cat in managed.categories

    # 3. Active skill count <= 30 cap
    mgr = SkillManager(skills_dir=skills_dir, rule_engine=skills_engine)
    assert mgr.count_active_skills() == 16
    assert mgr.count_active_skills() <= mgr.active_limit


def test_all_16_skills_execution_and_entity_invariants(skills_engine: RuleLifecycleManager) -> None:
    """
    Assert every one of the 16 factory skills executes cleanly according to doctrine:
    - Tool-call skills respect the entity-absent invariant: absence yields, presence acts.
    - Parameterless tool-call skills dispatch tools cleanly.
    - Pure-say, barge-in, and yield-shortcut skills fire on valid states.
    """
    # 1. calc-eval-v1
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="calculate 3 * 7",
                transcript_lower="calculate 3 * 7",
                intent="chit_chat",
                entities={},
            ),
            mode="active",
        )
    assert exc_info.value.reason == "calc: no expression"
    calc_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="calculate",
                transcript_lower="calculate",
                intent="chit_chat",
                entities={"expr": ["3 * 7"]},
            ),
            mode="active",
        )
        if o.rule_id == "calc-eval-v1"
    )
    assert (
        calc_out.fired
        and isinstance(calc_out.plan.actions[0], ToolCall)
        and calc_out.plan.actions[0].tool == "run_python"
    )

    # 2. unit-convert-v1
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="convert 100 kg to lbs",
                transcript_lower="convert 100 kg to lbs",
                intent="chit_chat",
                entities={},
            ),
            mode="active",
        )
    assert exc_info.value.reason == "convert: no expression"
    conv_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="convert",
                transcript_lower="convert",
                intent="chit_chat",
                entities={"expr": ["100 * 2.20462"]},
            ),
            mode="active",
        )
        if o.rule_id == "unit-convert-v1"
    )
    assert (
        conv_out.fired
        and isinstance(conv_out.plan.actions[0], ToolCall)
        and conv_out.plan.actions[0].tool == "run_python"
    )

    # 3. quick-fact-v1
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="quick fact about mars",
                transcript_lower="quick fact about mars",
                intent="chit_chat",
                entities={},
            ),
            mode="active",
        )
    assert exc_info.value.reason == "fact: no topic"
    fact_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="quick fact about",
                transcript_lower="quick fact about",
                intent="chit_chat",
                entities={"topic": ["mars"]},
            ),
            mode="active",
        )
        if o.rule_id == "quick-fact-v1"
    )
    assert (
        fact_out.fired
        and isinstance(fact_out.plan.actions[0], ToolCall)
        and fact_out.plan.actions[0].tool == "search_web"
    )

    # 4. define-term-v1
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="what is quantum computing",
                transcript_lower="what is quantum computing",
                intent="chit_chat",
                entities={},
            ),
            mode="active",
        )
    assert exc_info.value.reason == "define: no term"
    def_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="what is",
                transcript_lower="what is",
                intent="chit_chat",
                entities={"term": ["quantum computing"]},
            ),
            mode="active",
        )
        if o.rule_id == "define-term-v1"
    )
    assert (
        def_out.fired
        and isinstance(def_out.plan.actions[0], ToolCall)
        and def_out.plan.actions[0].tool == "search_web"
    )

    # 5. memory-brief-v1
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="memory about project",
                transcript_lower="memory about project",
                intent="memory_query",
                entities={},
            ),
            mode="active",
        )
    assert exc_info.value.reason == "memory-brief: no query"
    mem_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="memory about",
                transcript_lower="memory about",
                intent="memory_query",
                entities={"query": ["project"]},
            ),
            mode="active",
        )
        if o.rule_id == "memory-brief-v1"
    )
    assert (
        mem_out.fired
        and isinstance(mem_out.plan.actions[0], ToolCall)
        and mem_out.plan.actions[0].tool == "memory_search"
    )

    # 6. note-take-v1
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="take note buy milk",
                transcript_lower="take note buy milk",
                intent="file_write",
                entities={},
            ),
            mode="active",
        )
    assert exc_info.value.reason == "note-take: no content"
    note_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="take note",
                transcript_lower="take note",
                intent="file_write",
                entities={"content": ["buy milk"]},
            ),
            mode="active",
        )
        if o.rule_id == "note-take-v1"
    )
    assert (
        note_out.fired
        and isinstance(note_out.plan.actions[0], ToolCall)
        and note_out.plan.actions[0].tool == "note_write"
    )
    assert note_out.plan.actions[0].args["content"] == "buy milk"

    # 7. self-health-v1
    health_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="check self health",
                transcript_lower="check self health",
                intent="chit_chat",
                entities={},
            ),
            mode="active",
        )
        if o.rule_id == "self-health-v1"
    )
    assert (
        health_out.fired
        and isinstance(health_out.plan.actions[0], ToolCall)
        and health_out.plan.actions[0].tool == "self_metrics"
    )

    # 8. recent-context-v1
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="recent context roadmap",
                transcript_lower="recent context roadmap",
                intent="memory_query",
                entities={},
            ),
            mode="active",
        )
    assert exc_info.value.reason == "recent-context: no topic"
    rec_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="recent context",
                transcript_lower="recent context",
                intent="memory_query",
                entities={"topic": ["roadmap"]},
            ),
            mode="active",
        )
        if o.rule_id == "recent-context-v1"
    )
    assert (
        rec_out.fired
        and isinstance(rec_out.plan.actions[0], ToolCall)
        and rec_out.plan.actions[0].tool == "memory_search"
    )

    # 9. resource-report-v1
    res_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="show resource report",
                transcript_lower="show resource report",
                intent="chit_chat",
                entities={},
            ),
            mode="active",
        )
        if o.rule_id == "resource-report-v1"
    )
    assert (
        res_out.fired
        and isinstance(res_out.plan.actions[0], ToolCall)
        and res_out.plan.actions[0].tool == "self_metrics"
    )

    # 10. sys-specs-v1
    specs_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="system specs",
                transcript_lower="system specs",
                intent="chit_chat",
                entities={},
            ),
            mode="active",
        )
        if o.rule_id == "sys-specs-v1"
    )
    assert (
        specs_out.fired
        and isinstance(specs_out.plan.actions[0], ToolCall)
        and specs_out.plan.actions[0].tool == "sys_info"
    )
    assert specs_out.plan.actions[0].args["limit"] == 10

    # 11. proc-top-v1
    proc_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="top processes",
                transcript_lower="top processes",
                intent="chit_chat",
                entities={},
            ),
            mode="active",
        )
        if o.rule_id == "proc-top-v1"
    )
    assert (
        proc_out.fired
        and isinstance(proc_out.plan.actions[0], ToolCall)
        and proc_out.plan.actions[0].tool == "sys_info"
    )
    assert proc_out.plan.actions[0].args["limit"] == 25

    # 12. session-recap-v1
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="session recap",
                transcript_lower="session recap",
                intent="memory_query",
                entities={},
            ),
            mode="active",
        )
    assert exc_info.value.reason == "session-recap: no query"
    sess_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="session recap",
                transcript_lower="session recap",
                intent="memory_query",
                entities={"query": ["today"]},
            ),
            mode="active",
        )
        if o.rule_id == "session-recap-v1"
    )
    assert (
        sess_out.fired
        and isinstance(sess_out.plan.actions[0], ToolCall)
        and sess_out.plan.actions[0].tool == "memory_search"
    )

    # 13. time-greeting-v1 (pure say)
    greet_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="hello",
                transcript_lower="hello",
                intent="chit_chat",
                hour_local=9,
                session_turns=0,
            ),
            mode="active",
        )
        if o.rule_id == "time-greeting-v1"
    )
    assert (
        greet_out.fired
        and greet_out.plan.actions[0].text == "Good morning! How can I help you today?"
    )

    # 14. barge-in-sorry-v1 (interrupted? predicate)
    barge_out = next(
        o
        for o in skills_engine.evaluate(
            RuleState(
                transcript="wait", transcript_lower="wait", intent="barge_in", interrupted=True
            ),
            mode="active",
        )
        if o.rule_id == "barge-in-sorry-v1"
    )
    assert barge_out.fired and barge_out.plan.actions[0].text == "Sorry — you were saying?"

    # 15. plan-decompose-v1 (yield)
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="step by step how to build a treehouse",
                transcript_lower="step by step how to build a treehouse",
                intent="chit_chat",
            ),
            mode="active",
        )
    assert exc_info.value.reason == "multi-step task"
    assert exc_info.value.context["mode"] == "plan"

    # 16. correction-ack-v1 (yield)
    with pytest.raises(SchemeYieldSignal) as exc_info:
        skills_engine.evaluate(
            RuleState(
                transcript="no actually that is wrong",
                transcript_lower="no actually that is wrong",
                intent="chit_chat",
            ),
            mode="active",
        )
    assert exc_info.value.reason == "operator correction"
    assert exc_info.value.context["salience"] == "high"


def test_invoke_skill_dispatch_all_exposed_skills(skills_engine: RuleLifecycleManager) -> None:
    """
    Assert invoke_skill dispatches all 12 exposed skills when their category is in the manifest,
    and all 4 unexposed skills refuse with skill_not_exposed.
    """
    exposed_test_args = {
        "calc-eval-v1": {"expr": "20 + 4"},
        "unit-convert-v1": {"expr": "5 * 1.60934"},
        "quick-fact-v1": {"topic": "astronomy"},
        "define-term-v1": {"term": "compiler"},
        "memory-brief-v1": {"query": "lucca architecture"},
        "note-take-v1": {"content": "remember to run soak tests"},
        "self-health-v1": {},
        "recent-context-v1": {"topic": "memory"},
        "resource-report-v1": {},
        "sys-specs-v1": {},
        "proc-top-v1": {},
        "session-recap-v1": {"query": "recent tasks"},
    }

    # All 12 exposed skills dispatch successfully
    for skill_id, test_args in exposed_test_args.items():
        ok, msg, payload = dispatch_invoke_skill(
            skill_id=skill_id,
            args=test_args,
            rule_engine=skills_engine,
            manifest_skill_ids={skill_id},
        )
        assert ok is True, f"{skill_id} failed dispatch: {msg}"
        assert payload is not None and payload["skill_id"] == skill_id

    # 4 unexposed skills refuse
    unexposed_skills = [
        "time-greeting-v1",
        "barge-in-sorry-v1",
        "plan-decompose-v1",
        "correction-ack-v1",
    ]
    for unexposed_id in unexposed_skills:
        ok, reason, _ = dispatch_invoke_skill(
            skill_id=unexposed_id,
            args={},
            rule_engine=skills_engine,
            manifest_skill_ids={unexposed_id},
        )
        assert ok is False, f"Expected {unexposed_id} to refuse"
        assert reason == "skill_not_exposed"


def test_category_manifest_filtering_and_formatting(skills_engine: RuleLifecycleManager) -> None:
    """
    Test format_category_manifest correctly selects skills by category:
    - cognitive_core returns cognitive_core skills
    - host_readonly returns host_readonly skills
    - companion returns companion skills
    """
    # 1. Cognitive Core manifest
    metas = skills_engine.get_active_skill_metas()
    manifest_cog = format_category_manifest("cognitive_core", metas)
    assert "calc-eval-v1" in manifest_cog
    assert "memory-brief-v1" in manifest_cog
    assert "note-take-v1" in manifest_cog
    assert "sys-specs-v1" not in manifest_cog  # sys-specs is host_readonly only

    # 2. Host Readonly manifest
    manifest_host = format_category_manifest("host_readonly", metas)
    assert "sys-specs-v1" in manifest_host
    assert "proc-top-v1" in manifest_host
    assert "calc-eval-v1" not in manifest_host
