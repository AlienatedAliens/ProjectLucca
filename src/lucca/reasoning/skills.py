"""
Project Lucca — Skill Package Format & Lifecycle Management
Spec 1.1.2 §3 (Skill Package Format), §13 Ladder L1a, ADR-006

Manages skill package directories, static & Z3 formal verification,
golden trace evaluation, active library bounds (30-ACTIVE cap),
and package retirement (_retired/ relocation).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import structlog
from pydantic import JsonValue

from lucca.core.config import get_resource_path
from lucca.core.exceptions import SchemeInterruptSignal, SchemeYieldSignal
from lucca.core.schemas import RuleOutcome, RuleState, SkillMeta, ToolCall, ToolSchema
from lucca.reasoning.lifecycle import ManagedRule, RuleLifecycleManager
from lucca.reasoning.scheme.eval import evaluate_rule
from lucca.reasoning.scheme.parser import RuleDefinition
from lucca.reasoning.scheme.validator import validate_rule_static
from lucca.reasoning.smt_verifier import SMTVerifier

logger = structlog.get_logger(__name__)

ACTIVE_SKILL_LIMIT: Final[int] = 30


class SkillError(Exception):
    """Base exception for skill package operations."""


class SkillValidationError(SkillError):
    """Raised when a skill package fails static, formal, or trace validation."""


class SkillLimitExceededError(SkillError):
    """Raised when registering an ACTIVE skill exceeds the library cap."""


class SkillNotFoundError(SkillError):
    """Raised when a requested skill package does not exist."""


def resolve_skills_dir(custom_path: Path | str | None = None) -> Path:
    """Resolves the root directory for skill packages."""
    if custom_path is not None:
        p = Path(custom_path).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    try:
        resolved = get_resource_path("config/skills").resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved
    except Exception:  # noqa: BLE001
        fallback = Path("config/skills").resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


@dataclass
class SkillPackage:
    """Encapsulates an authored or induced skill package on disk."""

    pkg_dir: Path
    meta: SkillMeta
    plan_source: str
    rule_def: RuleDefinition
    backup_text: str
    recover_text: str
    traces: list[dict[str, JsonValue]]

    @classmethod
    def load_and_validate(
        cls,
        pkg_dir: Path,
        registered_tools: dict[str, ToolSchema] | None = None,
    ) -> SkillPackage:
        """
        Loads and performs full structural, formal, and empirical validation
        on a skill package directory per Spec 1.1.2 §3:
        1. meta_info.json exists and validates against SkillMeta.
        2. backup.md, recover.md, and failure_examples/ exist.
        3. plan.scm exists, passes validate_rule_static, and passes Z3 SMTVerifier.
        4. golden_traces.jsonl contains >= 2 traces (fire + no-fire) and all pass.
        """
        if not pkg_dir.exists() or not pkg_dir.is_dir():
            raise SkillValidationError(f"Package directory does not exist: {pkg_dir}")

        # 1. Validate meta_info.json
        meta_file = pkg_dir / "meta_info.json"
        if not meta_file.exists():
            raise SkillValidationError(f"Missing required file: meta_info.json in {pkg_dir}")
        try:
            meta_json = json.loads(meta_file.read_text(encoding="utf-8"))
            meta = SkillMeta.model_validate(meta_json)
        except Exception as exc:
            raise SkillValidationError(f"Invalid meta_info.json: {exc}") from exc

        # 2. Check documentation & failure artifacts
        backup_file = pkg_dir / "backup.md"
        if not backup_file.exists() or not backup_file.is_file():
            raise SkillValidationError("Missing required file: backup.md")
        backup_text = backup_file.read_text(encoding="utf-8")

        recover_file = pkg_dir / "recover.md"
        if not recover_file.exists() or not recover_file.is_file():
            raise SkillValidationError("Missing required file: recover.md")
        recover_text = recover_file.read_text(encoding="utf-8")

        failure_dir = pkg_dir / "failure_examples"
        if not failure_dir.exists() or not failure_dir.is_dir():
            raise SkillValidationError("Missing required directory: failure_examples/")

        # 3. Validate plan.scm statically and via Z3 SMT
        plan_file = pkg_dir / "plan.scm"
        if not plan_file.exists() or not plan_file.is_file():
            raise SkillValidationError("Missing required file: plan.scm")
        plan_source = plan_file.read_text(encoding="utf-8")

        try:
            rule_def = validate_rule_static(
                plan_source,
                registered_tools=registered_tools,
            )
        except Exception as exc:
            raise SkillValidationError(f"Static validation failed for plan.scm: {exc}") from exc

        if meta.id != rule_def.rule_id:
            raise SkillValidationError(
                f"ID mismatch: meta_info.json id ('{meta.id}') does not match "
                f"plan.scm rule id ('{rule_def.rule_id}')"
            )

        smt = SMTVerifier()
        smt_res = smt.verify_rule(rule_def, registered_tools=registered_tools)
        if not smt_res.verified:
            reasons_str = "; ".join(smt_res.reasons) if smt_res.reasons else smt_res.status
            raise SkillValidationError(
                f"SMT formal verification failed ({smt_res.status}): {reasons_str}"
            )

        # 4. Golden traces evaluation (>=2 traces, fire + no-fire)
        traces_file = pkg_dir / "golden_traces.jsonl"
        if not traces_file.exists():
            traces_file = pkg_dir / "traces.jsonl"
        if not traces_file.exists():
            raise SkillValidationError(
                "Missing required traces file: golden_traces.jsonl (or traces.jsonl)"
            )

        traces: list[dict[str, JsonValue]] = []
        with open(traces_file, encoding="utf-8") as tf:
            for line_idx, line in enumerate(tf, 1):
                clean = line.strip()
                if not clean:
                    continue
                try:
                    data = json.loads(clean)
                    if isinstance(data, dict):
                        traces.append(data)
                except Exception as exc:
                    raise SkillValidationError(
                        f"Malformed JSON in traces file at line {line_idx}: {exc}"
                    ) from exc

        if len(traces) < 2:
            raise SkillValidationError(
                f"Golden traces must contain at least 2 traces, found {len(traces)}"
            )

        fire_count = 0
        no_fire_count = 0

        for t_idx, trace in enumerate(traces, 1):
            trace_id = str(trace.get("id", f"trace-{t_idx}"))
            raw_entities = trace.get("entities")
            entities: dict[str, JsonValue] = (
                raw_entities if isinstance(raw_entities, dict) else {}
            )
            raw_transcript = str(trace.get("transcript", ""))
            raw_apps = trace.get("apps_running")
            apps_list: list[str] = (
                [str(a) for a in raw_apps] if isinstance(raw_apps, list) else []
            )

            state = RuleState(
                transcript=raw_transcript,
                transcript_lower=raw_transcript.lower(),
                intent=str(trace.get("intent", "")),
                intent_conf=float(trace.get("intent_conf", 1.0)),
                entities=entities,
                hour_local=int(trace.get("hour_local", 12)),
                weekday=int(trace.get("weekday", 0)),
                apps_running=apps_list,
                last_tool=str(trace["last_tool"]) if trace.get("last_tool") is not None else None,
                last_tool_ok=bool(trace.get("last_tool_ok", True)),
                session_turns=int(trace.get("session_turns", 1)),
                mode="transcript" if trace.get("mode") == "transcript" else "audio",
            )

            try:
                outcome = evaluate_rule(rule_def, state)
            except (SchemeYieldSignal, SchemeInterruptSignal):
                outcome = RuleOutcome(
                    rule_id=rule_def.rule_id,
                    fired=True,
                    errored=False,
                    plan=None,
                    gas_used=0,
                    elapsed_us=0,
                )
            if outcome.errored:
                raise SkillValidationError(
                    f"Golden trace #{t_idx} ('{trace_id}') errored: {outcome.error}"
                )

            expected_fired = trace.get("rule_fired")
            if expected_fired is not None:
                exp_bool = bool(expected_fired)
                if outcome.fired != exp_bool:
                    raise SkillValidationError(
                        f"Golden trace #{t_idx} ('{trace_id}') failed: "
                        f"expected rule_fired={exp_bool}, got {outcome.fired}"
                    )

            if outcome.fired:
                fire_count += 1
                expected_tool = trace.get("expected_tool")
                if expected_tool is not None and str(expected_tool):
                    tool_names = (
                        [a.tool for a in outcome.plan.actions if isinstance(a, ToolCall)]
                        if outcome.plan
                        else []
                    )
                    if str(expected_tool) not in tool_names:
                        raise SkillValidationError(
                            f"Golden trace #{t_idx} ('{trace_id}') failed: expected tool "
                            f"'{expected_tool}' not called in plan (called: {tool_names})"
                        )
            else:
                no_fire_count += 1

        if fire_count == 0 or no_fire_count == 0:
            raise SkillValidationError(
                "Golden traces must include at least one fire (rule_fired=true) "
                f"and at least one no-fire (rule_fired=false) trace "
                f"(got {fire_count} fire, {no_fire_count} no-fire)"
            )

        return cls(
            pkg_dir=pkg_dir,
            meta=meta,
            plan_source=plan_source,
            rule_def=rule_def,
            backup_text=backup_text,
            recover_text=recover_text,
            traces=traces,
        )


class SkillManager:
    """
    Manages package lifecycles, active limits, and storage under config/skills/.
    """

    def __init__(
        self,
        skills_dir: Path | str | None = None,
        rule_engine: RuleLifecycleManager | None = None,
        active_limit: int = ACTIVE_SKILL_LIMIT,
    ) -> None:
        self.skills_dir = resolve_skills_dir(skills_dir)
        self.retired_dir = self.skills_dir / "_retired"
        self.retired_dir.mkdir(parents=True, exist_ok=True)
        self.rule_engine = rule_engine
        self.active_limit = active_limit

    def count_active_skills(self) -> int:
        """Counts distinct ACTIVE skills on disk and in the rule engine."""
        active_ids: set[str] = set()
        if self.skills_dir.exists() and self.skills_dir.is_dir():
            for child in self.skills_dir.iterdir():
                if not child.is_dir() or child.name.startswith("_") or child.name.startswith("."):
                    continue
                meta_file = child / "meta_info.json"
                if meta_file.exists() and meta_file.is_file():
                    try:
                        meta = SkillMeta.model_validate_json(
                            meta_file.read_text(encoding="utf-8")
                        )
                        if meta.status == "ACTIVE":
                            active_ids.add(meta.id)
                    except Exception:  # noqa: BLE001, S110
                        pass

        if self.rule_engine is not None:
            for r in self.rule_engine.rules.values():
                if r.status == "ACTIVE":
                    active_ids.add(r.rule_id)

        return len(active_ids)

    def register_package(
        self,
        pkg_path: Path | str,
        registered_tools: dict[str, ToolSchema] | None = None,
    ) -> SkillPackage:
        """
        Validates, installs, and registers a skill package into ACTIVE status.
        Enforces the 30-ACTIVE limit.
        """
        source_dir = Path(pkg_path).resolve()
        tools = (
            registered_tools
            if registered_tools is not None
            else (self.rule_engine.registered_tools if self.rule_engine else None)
        )

        pkg = SkillPackage.load_and_validate(source_dir, registered_tools=tools)

        # 30-cap check
        active_count = self.count_active_skills()
        is_already_active = False
        dest_meta = self.skills_dir / pkg.meta.id / "meta_info.json"
        if dest_meta.exists():
            try:
                curr_meta = SkillMeta.model_validate_json(dest_meta.read_text(encoding="utf-8"))
                if curr_meta.status == "ACTIVE":
                    is_already_active = True
            except Exception:  # noqa: BLE001, S110
                pass
        if self.rule_engine and pkg.meta.id in self.rule_engine.rules:
            if self.rule_engine.rules[pkg.meta.id].status == "ACTIVE":
                is_already_active = True

        if not is_already_active and active_count >= self.active_limit:
            raise SkillLimitExceededError(
                f"Active skill limit reached ({self.active_limit}/{self.active_limit}). "
                "Please retire an active skill before registering a new one "
                "(use 'lucca-admin skills retire <skill_id>')."
            )

        # Copy to destination if not already in skills_dir/<id>
        dest_dir = self.skills_dir / pkg.meta.id
        if source_dir.resolve() != dest_dir.resolve():
            shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)

        # Ensure meta_info.json marks status ACTIVE
        meta_file = dest_dir / "meta_info.json"
        updated_meta = pkg.meta.model_copy(update={"status": "ACTIVE"})
        meta_file.write_text(updated_meta.model_dump_json(indent=2), encoding="utf-8")

        # Update in-memory package object
        pkg.meta = updated_meta
        pkg.pkg_dir = dest_dir

        # Register in rule engine if present
        if self.rule_engine is not None:
            existing = self.rule_engine.rules.get(pkg.meta.id)
            if existing is not None:
                existing.status = "ACTIVE"
                existing.definition = pkg.rule_def
                existing.expose_as_tool = pkg.meta.expose_as_tool
                existing.categories = list(pkg.meta.categories)
                existing.skill_meta = pkg.meta
                existing.retired_at = None
                existing.user_retired = False
            else:
                managed = ManagedRule(
                    rule_id=pkg.meta.id,
                    status="ACTIVE",
                    definition=pkg.rule_def,
                    expose_as_tool=pkg.meta.expose_as_tool,
                    categories=list(pkg.meta.categories),
                    skill_meta=pkg.meta,
                )
                self.rule_engine.rules[pkg.meta.id] = managed

            if self.rule_engine.db is not None:
                self.rule_engine.persist(pkg.meta.id)

        logger.info(
            "skill_package_registered_active",
            skill_id=pkg.meta.id,
            dir=str(dest_dir),
            active_count=self.count_active_skills(),
        )
        return pkg

    def retire_skill(self, skill_id: str) -> Path:
        """
        Retires an active or quarantined skill:
        - Relocates its package directory into config/skills/_retired/<skill_id>
        - Updates meta_info.json status to RETIRED
        - Marks rule RETIRED in RuleLifecycleManager
        - Excludes from future manifest and active evaluations
        """
        found = False
        pkg_dir = self.skills_dir / skill_id
        dest_dir = self.retired_dir / skill_id

        if pkg_dir.exists() and pkg_dir.is_dir():
            found = True
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.move(str(pkg_dir), str(dest_dir))
            meta_file = dest_dir / "meta_info.json"
            if meta_file.exists():
                try:
                    meta = SkillMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                    ret_meta = meta.model_copy(update={"status": "RETIRED"})
                    meta_file.write_text(ret_meta.model_dump_json(indent=2), encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("failed_to_update_retired_meta", error=str(exc))

        if self.rule_engine is not None and skill_id in self.rule_engine.rules:
            found = True
            self.rule_engine.user_retire(skill_id)
            rule = self.rule_engine.rules[skill_id]
            if rule.skill_meta is not None:
                rule.skill_meta = rule.skill_meta.model_copy(update={"status": "RETIRED"})

        if not found:
            raise SkillNotFoundError(f"Skill '{skill_id}' not found.")

        logger.info("skill_package_retired", skill_id=skill_id, retired_path=str(dest_dir))
        return dest_dir

    def list_skills(self) -> list[dict[str, JsonValue]]:
        """Scans active and retired directories, returning structured records."""
        skills: dict[str, dict[str, JsonValue]] = {}

        # 1. Active packages
        if self.skills_dir.exists() and self.skills_dir.is_dir():
            for child in sorted(self.skills_dir.iterdir()):
                if not child.is_dir() or child.name.startswith("_") or child.name.startswith("."):
                    continue
                meta_file = child / "meta_info.json"
                if meta_file.exists() and meta_file.is_file():
                    try:
                        meta = SkillMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                        skills[meta.id] = {
                            "id": meta.id,
                            "status": meta.status,
                            "categories": ", ".join(meta.categories) if meta.categories else "-",
                            "expose_as_tool": meta.expose_as_tool,
                            "clusters": "0 / 5",
                            "failures": 0,
                        }
                    except Exception:  # noqa: BLE001, S110
                        pass

        # 2. Retired packages
        if self.retired_dir.exists() and self.retired_dir.is_dir():
            for child in sorted(self.retired_dir.iterdir()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                meta_file = child / "meta_info.json"
                if meta_file.exists() and meta_file.is_file():
                    try:
                        meta = SkillMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                        skills[meta.id] = {
                            "id": meta.id,
                            "status": "RETIRED",
                            "categories": ", ".join(meta.categories) if meta.categories else "-",
                            "expose_as_tool": meta.expose_as_tool,
                            "clusters": "-",
                            "failures": 0,
                        }
                    except Exception:  # noqa: BLE001, S110
                        pass

        # 3. Merge telemetry from rule engine
        if self.rule_engine is not None:
            for r in self.rule_engine.rules.values():
                if r.rule_id in skills:
                    rec = skills[r.rule_id]
                    rec["status"] = r.status
                    rec["clusters"] = f"{len(r.success_clusters)} / 5"
                    rec["failures"] = r.failure_count
                else:
                    skills[r.rule_id] = {
                        "id": r.rule_id,
                        "status": r.status,
                        "categories": ", ".join(r.categories) if r.categories else "-",
                        "expose_as_tool": r.expose_as_tool,
                        "clusters": f"{len(r.success_clusters)} / 5",
                        "failures": r.failure_count,
                    }

        return sorted(list(skills.values()), key=lambda x: str(x.get("id", "")))
