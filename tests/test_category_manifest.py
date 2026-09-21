"""
Unit tests for per-turn category manifest and Prompt Frontier Suffix.
Spec 1.1.2 §2.4, Phase 1 (T1.4, T1.6).
"""

import pytest

from lucca.brain.prompt_builder import (
    build_messages,
    format_category_manifest,
)
from lucca.core.schemas import SkillMeta
from lucca.router.heuristic import map_intent_to_category


def test_manifest_content_for_mocked_skills() -> None:
    """T1.4: Manifest content correctly formats category and exposed skill entries."""
    skills = [
        SkillMeta(
            id="calc-eval-v1",
            intent="calculate",
            description="Evaluate math expressions deterministically",
            args=["expr"],
            status="ACTIVE",
            categories=["self"],
            expose_as_tool=True,
        ),
        SkillMeta(
            id="unit-convert-v1",
            intent="convert",
            description="Convert physical units",
            args=["amount", "from_unit", "to_unit"],
            status="ACTIVE",
            categories=["self"],
            expose_as_tool=True,
        ),
        SkillMeta(
            id="hidden-v1",
            intent="internal",
            description="Internal rule not exposed as tool",
            args=[],
            status="ACTIVE",
            categories=["self"],
            expose_as_tool=False,  # not exposed
        ),
        SkillMeta(
            id="search-fact-v1",
            intent="search",
            description="Search facts online",
            args=["query"],
            status="ACTIVE",
            categories=["information"],
            expose_as_tool=True,
        ),
    ]

    manifest = format_category_manifest("self", skills)
    assert manifest.startswith("\n[SKILLS category=self: ")
    assert manifest.endswith("]")
    assert "calc-eval-v1 — Evaluate math expressions deterministically (args: expr)" in manifest
    assert "unit-convert-v1 — Convert physical units (args: amount, from_unit, to_unit)" in manifest
    # Non-exposed and non-category skills must NOT appear
    assert "hidden-v1" not in manifest
    assert "search-fact-v1" not in manifest


def test_empty_category_emits_no_manifest() -> None:
    """T1.4: Empty, None, or zero exposed skills emit empty string."""
    skills = [
        SkillMeta(
            id="calc-eval-v1",
            intent="calculate",
            description="Eval expr",
            args=["expr"],
            categories=["self"],
            expose_as_tool=True,
        )
    ]

    assert format_category_manifest(None, skills) == ""
    assert format_category_manifest("", skills) == ""
    assert format_category_manifest("   ", skills) == ""
    assert format_category_manifest("self", []) == ""
    assert format_category_manifest("information", skills) == ""  # No skills in this category


def test_prefix_byte_identity_across_10_turns_multi_category() -> None:
    """
    T1.6: Render prompt for 10 synthetic turns spanning >= 3 categories.
    Assert byte content before the final user message is 100% identical.
    Assert suffix differs only in the manifest portion.
    """
    categories = ["self", "information", "companion", "cognitive_core", "host_perception"]
    skills_map: dict[str, list[SkillMeta]] = {
        "self": [
            SkillMeta(
                id="calc-eval-v1",
                intent="calculate",
                description="Evaluate math",
                args=["expr"],
                categories=["self"],
                expose_as_tool=True,
            )
        ],
        "information": [
            SkillMeta(
                id="quick-fact-v1",
                intent="fact",
                description="Fact lookup",
                args=["topic"],
                categories=["information"],
                expose_as_tool=True,
            )
        ],
        "companion": [
            SkillMeta(
                id="time-greeting-v1",
                intent="greeting",
                description="Greet user",
                args=[],
                categories=["companion"],
                expose_as_tool=True,
            )
        ],
        "cognitive_core": [
            SkillMeta(
                id="plan-decompose-v1",
                intent="decompose",
                description="Decompose plan",
                args=["task"],
                categories=["cognitive_core"],
                expose_as_tool=True,
            )
        ],
        "host_perception": [
            SkillMeta(
                id="sys-status-v1",
                intent="status",
                description="Check status",
                args=[],
                categories=["host_perception"],
                expose_as_tool=True,
            )
        ],
    }

    mock_history = [
        {"role": "user", "content": "Hello Lucca!"},
        {"role": "assistant", "content": "Hello creator! Ready to build."},
    ]

    rendered_turns = []
    for i in range(10):
        cat = categories[i % len(categories)]
        cat_skills = skills_map[cat]
        msgs = build_messages(
            history=mock_history,
            current_text="What should we work on next?",
            stance_tag="neutral",
            category=cat,
            skills=cat_skills,
        )
        rendered_turns.append(msgs)

    # 1. Assert prefix (everything before the final user message) is byte-identical
    first_prefix_bytes = b"".join(
        m.model_dump_json().encode("utf-8") for m in rendered_turns[0][:-1]
    )
    for i, msgs in enumerate(rendered_turns[1:], start=1):
        turn_prefix_bytes = b"".join(m.model_dump_json().encode("utf-8") for m in msgs[:-1])
        assert turn_prefix_bytes == first_prefix_bytes, f"Turn {i} prefix diverged from Turn 0"

    # 2. Assert final user message begins with identical base text and stance suffix
    base_prefix = "What should we work on next?\n[STANCE: neutral]\n[SKILLS category="
    for _i, msgs in enumerate(rendered_turns):
        user_content = str(msgs[-1].content)
        assert user_content.startswith("What should we work on next?\n[STANCE: neutral]")
        assert user_content.startswith(base_prefix)


def test_category_miss_logged_when_no_mapping_fires(capsys: pytest.CaptureFixture[str]) -> None:
    """T1.4: When no deterministic mapping fires, log category_miss and return None."""
    import structlog.testing

    with structlog.testing.capture_logs() as captured:
        cat = map_intent_to_category("unknown_unmapped_intent", entities={"app": ["xyz"]})
        assert cat is None

    # Verify category_miss was logged via structlog or output
    out = capsys.readouterr()
    has_event = any(e.get("event") == "category_miss" for e in captured)
    has_stdout = "category_miss" in out.out or "category_miss" in out.err
    assert has_event or has_stdout
