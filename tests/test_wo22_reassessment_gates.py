"""Static gates for the 2026-09-27 deferred-item reassessment (WO-22 scope).

The reassessment of every deferred/can't-do item against WO-15..WO-21 shipments
pulled exactly two items forward into WO-22:

- ITEM-017 (multi-action narration aggregation)  -> WO-22 Phase 1 (planner)
- ITEM-021 (decision-record/turn-trace retrieval) -> WO-22 Phase 2 (diagnosis)

Everything else stays deferred. These gates make the pull-forward decisions
permanent and idiot-proof: if anyone reverts the plan amendment, un-amends the
backlog trigger, or renames the WO-21 stubs away, the suite goes red with a
message that names the file, the missing marker, and the fix.

All checks are documentation/source-text gates — no network, no production DB,
no hardware. Safe to run on fresh machines and CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

WO22_PLAN = REPO_ROOT / "plans" / "2026-09-27_wo22_practical_reasoning.md"
V2_BACKLOG = REPO_ROOT / "docs" / "V2_BACKLOG.md"
V2_ACTION_LOG = REPO_ROOT / "docs" / "V2_ACTION_LOG.md"

USER_MODEL_STUB = REPO_ROOT / "src" / "lucca" / "core" / "user_model.py"
EPISODE_RECALL_STUB = REPO_ROOT / "src" / "lucca" / "core" / "episode_recall.py"


def _read_text(path: Path) -> str:
    """Read a gate file, failing with the absolute path if it is missing.

    Idiot-proofing: a moved/renamed gate file must never silently pass —
    the failure names the exact path that disappeared.
    """
    if not path.exists():
        pytest.fail(
            f"Reassessment gate file is missing: {path.resolve()}\n"
            f"Fix: restore the file or update the path constant in "
            f"tests/test_wo22_reassessment_gates.py — never delete the gate "
            f"to make it pass."
        )
    return path.read_text(encoding="utf-8")


def _plan_phase_section(plan_text: str, phase_number: int) -> str:
    """Extract the body of `## Phase <N> ...` from the WO-22 plan.

    Idiot-proofing: if the heading is missing (renamed, renumbered, or the plan
    was truncated), the failure lists every heading actually found so the
    implementer can see immediately what happened.
    """
    sections = re.split(r"^## ", plan_text, flags=re.MULTILINE)
    headings = [s.splitlines()[0] if s.splitlines() else "<empty>" for s in sections]
    for section in sections:
        first_line = section.splitlines()[0] if section.splitlines() else ""
        match = re.match(rf"Phase {phase_number}\b", first_line)
        if match:
            return section
    pytest.fail(
        f"WO-22 plan {WO22_PLAN} has no '## Phase {phase_number}' heading.\n"
        f"Headings found: {headings}\n"
        f"Fix: restore the Phase {phase_number} heading or update the gate — "
        f"do not delete the gate."
    )


# ---------------------------------------------------------------------------
# ITEM-017 -> WO-22 Phase 1 (multi-action narration aggregation)
# ---------------------------------------------------------------------------


def test_item017_is_in_wo22_plan_phase1() -> None:
    """ITEM-017 must be pulled into Phase 1: a multi-step plan that narrates
    only the last step is dishonest narration — it is a planner dependency,
    not polish."""
    plan_text = _read_text(WO22_PLAN)
    phase1 = _plan_phase_section(plan_text, 1)

    assert "ITEM-017" in phase1, (
        f"{WO22_PLAN} Phase 1 no longer references ITEM-017 (multi-action "
        f"narration aggregation). The 2026-09-27 reassessment pulled it into "
        f"Phase 1 because GoalPlan multi-step execution is broken on arrival "
        f"without it. Fix: restore the ITEM-017 pull-forward row in the "
        f"Phase 1 manifest."
    )
    assert "turn_pipeline.py" in phase1, (
        f"{WO22_PLAN} Phase 1 manifest must name src/lucca/core/turn_pipeline.py "
        f"as the ITEM-017 code location (per V2_ACTION_LOG ITEM-017). "
        f"Fix: restore the manifest row."
    )
    assert "narration" in phase1.lower(), (
        f"{WO22_PLAN} Phase 1 must describe narration aggregation over "
        f"per-step receipts. Fix: restore the ITEM-017 manifest row text."
    )


def test_item017_not_leaked_into_phase2() -> None:
    """ITEM-017 belongs to Phase 1 only — a paste into Phase 2 means the
    manifest rows were shuffled and the diagnosis scope is polluted."""
    plan_text = _read_text(WO22_PLAN)
    phase2 = _plan_phase_section(plan_text, 2)
    assert "ITEM-017" not in phase2, (
        f"{WO22_PLAN} Phase 2 references ITEM-017, but ITEM-017 (narration "
        f"aggregation) belongs to Phase 1 only. Phase 2's pulled item is "
        f"ITEM-021. Fix: move the ITEM-017 row back to the Phase 1 manifest."
    )


def test_planning_test_manifest_covers_item017() -> None:
    """The Phase 1 test manifest (tests/test_planning.py row) must include the
    ITEM-017 narration cases, or the planner ships with untested narration."""
    plan_text = _read_text(WO22_PLAN)
    phase1 = _plan_phase_section(plan_text, 1)

    assert "test_planning.py" in phase1, (
        f"{WO22_PLAN} Phase 1 must declare tests/test_planning.py in its "
        f"manifest. Fix: restore the test manifest row."
    )
    test_row = [ln for ln in phase1.splitlines() if "test_planning.py" in ln]
    joined = "\n".join(test_row)
    assert "ITEM-017" in joined, (
        f"{WO22_PLAN} Phase 1 test_planning.py manifest row must include the "
        f"ITEM-017 narration-aggregation test cases (3-step plan narrates "
        f"every executed step; partial failure names the failed step).\n"
        f"Row found:\n{joined}\nFix: restore the ITEM-017 cases in the row."
    )


# ---------------------------------------------------------------------------
# ITEM-021 -> WO-22 Phase 2 (decision-record retrieval for DiagnosisEngine)
# ---------------------------------------------------------------------------


def test_item021_is_in_wo22_plan_phase2() -> None:
    """ITEM-021 must be pulled into Phase 2: the DiagnosisEngine reasons over
    her own stack, and decision records / turn traces are where the rich
    diagnostic signal lives — not just env_check outputs."""
    plan_text = _read_text(WO22_PLAN)
    phase2 = _plan_phase_section(plan_text, 2)

    assert "ITEM-021" in phase2, (
        f"{WO22_PLAN} Phase 2 no longer references ITEM-021 (in-session "
        f"decision-record retrieval). The 2026-09-27 reassessment pulled it "
        f"into Phase 2 because DiagnosisEngine is better when it can query "
        f"its own decision history. Fix: restore the ITEM-021 pull-forward "
        f"row in the Phase 2 manifest."
    )
    assert "retrieval.py" in phase2, (
        f"{WO22_PLAN} Phase 2 manifest must name src/lucca/memory/retrieval.py "
        f"as the ITEM-021 code location (per V2_ACTION_LOG ITEM-021). "
        f"Fix: restore the manifest row."
    )
    assert "DecisionRecord" in phase2 or "decision record" in phase2.lower(), (
        f"{WO22_PLAN} Phase 2 must describe indexing DecisionRecord/TurnTrace "
        f"into the in-session retrieval cascade. Fix: restore the ITEM-021 "
        f"manifest row text."
    )


def test_item021_not_leaked_into_phase1() -> None:
    """ITEM-021 belongs to Phase 2 only — see the mirrored Phase 1 gate."""
    plan_text = _read_text(WO22_PLAN)
    phase1 = _plan_phase_section(plan_text, 1)
    assert "ITEM-021" not in phase1, (
        f"{WO22_PLAN} Phase 1 references ITEM-021, but ITEM-021 (decision-"
        f"record retrieval) belongs to Phase 2 only. Phase 1's pulled item is "
        f"ITEM-017. Fix: move the ITEM-021 row back to the Phase 2 manifest."
    )


def test_self_diagnosis_test_manifest_covers_item021() -> None:
    """The Phase 2 test manifest (tests/test_self_diagnosis.py row) must
    include the ITEM-021 retrieval cases."""
    plan_text = _read_text(WO22_PLAN)
    phase2 = _plan_phase_section(plan_text, 2)

    assert "test_self_diagnosis.py" in phase2, (
        f"{WO22_PLAN} Phase 2 must declare tests/test_self_diagnosis.py in its "
        f"manifest. Fix: restore the test manifest row."
    )
    test_row = [ln for ln in phase2.splitlines() if "test_self_diagnosis.py" in ln]
    joined = "\n".join(test_row)
    assert "ITEM-021" in joined, (
        f"{WO22_PLAN} Phase 2 test_self_diagnosis.py manifest row must include "
        f"the ITEM-021 cases (seeded decision record retrievable in-session "
        f"and citable as evidence; no records -> no fabrication).\n"
        f"Row found:\n{joined}\nFix: restore the ITEM-021 cases in the row."
    )


# ---------------------------------------------------------------------------
# Backlog trigger hygiene (§1.11, §1.12, §1.13)
# ---------------------------------------------------------------------------


def _backlog_section(backlog_text: str, section_id: str) -> str:
    """Extract a `### <section_id> ...` section from V2_BACKLOG.md."""
    sections = re.split(r"^### ", backlog_text, flags=re.MULTILINE)
    for section in sections:
        first_line = section.splitlines()[0] if section.splitlines() else ""
        if first_line.startswith(section_id):
            return section
    pytest.fail(
        f"{V2_BACKLOG} has no '### {section_id}' section.\n"
        f"Fix: restore the section or update the gate — do not delete the gate."
    )


def test_backlog_113_trigger_is_owner_override_not_three_months() -> None:
    """§1.13's stale '>= 3 months of incident history' trigger was overridden
    by the owner on 2026-09-27 (5 real incidents documented); the section must
    record the override and point at WO-22 Phase 2."""
    backlog_text = _read_text(V2_BACKLOG)
    section = _backlog_section(backlog_text, "1.13")

    assert "Owner override 2026-09-27" in section, (
        f"{V2_BACKLOG} §1.13 must record the owner override dated 2026-09-27 "
        f"(5 documented incidents satisfy the trigger). Fix: restore the "
        f"override note in §1.13's Trigger to Revisit."
    )
    assert "WO-22 Phase 2" in section, (
        f"{V2_BACKLOG} §1.13 must point at WO-22 Phase 2 where fault model v1 "
        f"is being built. Fix: restore the WO-22 Phase 2 reference."
    )
    assert "superseded" in section, (
        f"{V2_BACKLOG} §1.13 must mark the original 3-month trigger as "
        f"superseded so no future agent re-reads it as active. Fix: restore "
        f"the superseded note."
    )
    # The stale trigger must never appear as an ACTIVE (unstruck) trigger.
    active_stale = re.search(r"(?<!~)\b3 months of operational incident history\b(?!~)", section)
    assert active_stale is None, (
        f"{V2_BACKLOG} §1.13 states '3 months of operational incident "
        f"history' as an unstruck (active) trigger — it was overridden on "
        f"2026-09-27. Fix: strike it through (~~...~~) and record the owner "
        f"override."
    )


def test_backlog_111_notes_wo21_user_model_stub_live() -> None:
    """§1.11's first gate (WO-21 stub) is OPEN — the backlog must say so, or
    the next reassessment re-derives it from scratch."""
    backlog_text = _read_text(V2_BACKLOG)
    section = _backlog_section(backlog_text, "1.11")
    assert "user_model.py" in section, (
        f"{V2_BACKLOG} §1.11 must note the WO-21 Phase 4 UserModel stub is "
        f"live (src/lucca/core/user_model.py) with the full model still gated "
        f"on SELF_HISTORY volume. Fix: restore the 2026-09-27 stubs-live note."
    )


def test_backlog_112_notes_wo21_episode_recall_stub_live() -> None:
    """§1.12's first gate (WO-21 stub) is OPEN — the backlog must say so."""
    backlog_text = _read_text(V2_BACKLOG)
    section = _backlog_section(backlog_text, "1.12")
    assert "episode_recall.py" in section, (
        f"{V2_BACKLOG} §1.12 must note the WO-21 Phase 4 EpisodeRecall stub "
        f"is live (src/lucca/core/episode_recall.py) with the full cycle "
        f"still gated on episode volume. Fix: restore the 2026-09-27 "
        f"stubs-live note."
    )


# ---------------------------------------------------------------------------
# Anchors: the reassessment's source-of-truth records must not silently move
# ---------------------------------------------------------------------------


def test_action_log_still_defines_item017_and_item021() -> None:
    """The gates above key off ITEM-017/ITEM-021 identifiers from
    V2_ACTION_LOG.md. If those entries are renamed or removed, this anchor
    fails first so the gates get re-pointed deliberately, not accidentally."""
    action_log_text = _read_text(V2_ACTION_LOG)
    for item_id, location in (
        ("ITEM-017", "turn_pipeline.py"),
        ("ITEM-021", "retrieval.py"),
    ):
        assert f"[{item_id}]" in action_log_text, (
            f"{V2_ACTION_LOG} no longer defines [{item_id}]. The WO-22 "
            f"reassessment gates key off this identifier. Fix: re-point "
            f"tests/test_wo22_reassessment_gates.py to the new identifier — "
            f"deliberately, with the owner's sign-off."
        )
        assert location in action_log_text, (
            f"{V2_ACTION_LOG} [{item_id}] no longer names {location} as its "
            f"code location. If the code moved, update the action log AND the "
            f"WO-22 plan manifest together."
        )


def test_wo21_stubs_exist_in_source() -> None:
    """The reassessment's 'first gate OPEN' claims rest on the WO-21 stubs
    actually existing. If a stub is deleted or renamed, the backlog notes and
    the WO-23 re-evaluation plan are both stale."""
    user_model_text = _read_text(USER_MODEL_STUB)
    assert "class UserModel" in user_model_text, (
        f"{USER_MODEL_STUB} no longer defines class UserModel. The §1.11 "
        f"stubs-live note in {V2_BACKLOG} and the WO-22 plan's deferred "
        f"section reference it. Fix: update the stub path in the backlog, the "
        f"plan, and this gate together."
    )
    episode_recall_text = _read_text(EPISODE_RECALL_STUB)
    assert "class EpisodeRecall" in episode_recall_text, (
        f"{EPISODE_RECALL_STUB} no longer defines class EpisodeRecall. The "
        f"§1.12 stubs-live note in {V2_BACKLOG} and the WO-22 plan's deferred "
        f"section reference it. Fix: update the stub path in the backlog, the "
        f"plan, and this gate together."
    )


def test_wo22_plan_records_the_reassessment_decision() -> None:
    """The plan's deferred section must record that exactly two items were
    pulled forward and name the enforcing gate, so the decision is
    self-describing for the next implementing agent."""
    plan_text = _read_text(WO22_PLAN)
    assert "Deferred-item reassessment record" in plan_text, (
        f"{WO22_PLAN} must contain the 'Deferred-item reassessment record' "
        f"section documenting the 2026-09-27 pull-forward decision. "
        f"Fix: restore the section at the end of the plan."
    )
    assert "test_wo22_reassessment_gates.py" in plan_text, (
        f"{WO22_PLAN} must reference tests/test_wo22_reassessment_gates.py as "
        f"the enforcing gate for the reassessment decision. Fix: restore the "
        f"reference."
    )
