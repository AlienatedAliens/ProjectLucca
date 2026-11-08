"""
Project Lucca — Skill Package Format & Lifecycle Management
Spec 1.1.2 §3 (Skill Package Format), §13 Ladder L1a, ADR-006

Manages skill package directories, static & Z3 formal verification,
golden trace evaluation, active library bounds (30-ACTIVE cap),
and package retirement (_retired/ relocation).
"""

from __future__ import annotations

import json
import math
import re
import shutil
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import structlog
from pydantic import JsonValue

from lucca.core.config import get_resource_path
from lucca.core.exceptions import SchemeInterruptSignal, SchemeYieldSignal
from lucca.core.schemas import (
    RuleOutcome,
    RuleState,
    SkillMeta,
    ToolCall,
    ToolSchema,
)
from lucca.reasoning.lifecycle import ManagedRule, RuleLifecycleManager
from lucca.reasoning.scheme.eval import SchemeEvaluator, evaluate_rule
from lucca.reasoning.scheme.parser import (
    ALLOWED_OPS,
    Keyword,
    RuleDefinition,
    SchemeNode,
    Symbol,
    parse_expr,
)
from lucca.reasoning.scheme.prims import PURE_PRIMITIVES
from lucca.reasoning.scheme.validator import validate_rule_static
from lucca.reasoning.smt_verifier import SMTVerifier

SExpr = SchemeNode

logger = structlog.get_logger(__name__)

ACTIVE_SKILL_LIMIT: Final[int] = 30

_STANDARD_SCHEME_BUILTINS: Final[frozenset[str]] = (
    ALLOWED_OPS
    | frozenset(PURE_PRIMITIVES.keys())
    | frozenset(
        {
            "+",
            "-",
            "*",
            "/",
            "modulo",
            "min",
            "max",
            "abs",
            "=",
            "!=",
            "<",
            ">",
            "<=",
            ">=",
            "eq?",
            "equal?",
            "and",
            "or",
            "not",
            "if",
            "cond",
            "else",
            "let",
            "let*",
            "lambda",
            "define",
            "define-rule",
            "define-skill",
            "begin",
            "quote",
            "list",
            "cons",
            "car",
            "cdr",
            "null?",
            "length",
            "append",
            "map",
            "filter",
            "foldl",
            "foldr",
            "string-append",
            "string-contains?",
            "string-downcase",
            "string-length",
            "substring",
            "number->string",
            "string->number",
            "true",
            "false",
            "#t",
            "#f",
            "nil",
        }
    )
)


@dataclass
class Skill:
    """In-memory and induced skill representation with NARS Bayesian evidence tracking (WO-39)."""

    name: str
    s_expr: str = ""
    description: str = ""
    parameters: list[str] = field(default_factory=list)
    positive_evidence: int = 1
    negative_evidence: int = 0
    last_used_at: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    categories: list[str] = field(default_factory=list)
    status: str = "ACTIVE"

    @property
    def id(self) -> str:
        return self.name

    @property
    def code(self) -> str:
        return self.s_expr

    @property
    def nars_frequency(self) -> float:
        total = self.positive_evidence + self.negative_evidence
        return self.positive_evidence / max(1, total)

    @property
    def nars_confidence(self) -> float:
        total = self.positive_evidence + self.negative_evidence
        return total / (total + 1.0)


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
    except Exception as exc:  # noqa: BLE001
        logger.debug("resolve_skills_dir_failed", error=str(exc))
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
    positive_evidence: int = 1
    negative_evidence: int = 0
    last_used_at: float = field(default_factory=time.time)

    @property
    def nars_frequency(self) -> float:
        total = self.positive_evidence + self.negative_evidence
        return self.positive_evidence / max(1, total)

    @property
    def nars_confidence(self) -> float:
        total = self.positive_evidence + self.negative_evidence
        return total / (total + 1.0)

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
            entities: dict[str, JsonValue] = raw_entities if isinstance(raw_entities, dict) else {}
            raw_transcript = str(trace.get("transcript", ""))
            raw_apps = trace.get("apps_running")
            apps_list: list[str] = [str(a) for a in raw_apps] if isinstance(raw_apps, list) else []

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
                interrupted=bool(trace.get("interrupted", False)),
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
        self.skills: dict[str, Skill] = {}

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
                        meta = SkillMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                        if meta.status == "ACTIVE":
                            active_ids.add(meta.id)
                    except Exception as exc:  # noqa: BLE001, S110
                        logger.debug("count_active_skills_meta_pa"
                            "rse_failed", path=str(meta_file), error=str(exc))

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
            except Exception as exc:  # noqa: BLE001, S110
                logger.debug("dest_meta_parse_failed", path=str(dest_meta), error=str(exc))
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
                    except Exception as exc:  # noqa: BLE001, S110
                        logger.debug("list_skills_meta_parse_failed", path=str(meta_file),
                            error=str(exc))

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
                    except Exception as exc:  # noqa: BLE001, S110
                        logger.debug("list_retired_skills_meta_pa"
                            "rse_failed", path=str(meta_file), error=str(exc))

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

    def add_skill(
        self,
        skill: Skill | str,
        s_expr: str = "",
        description: str = "",
        parameters: list[str] | None = None,
        positive_evidence: int = 1,
        negative_evidence: int = 0,
    ) -> Skill:
        """Registers an in-memory Skill with NARS evidence tracking."""
        if isinstance(skill, Skill):
            obj = skill
        else:
            obj = Skill(
                name=str(skill),
                s_expr=s_expr,
                description=description,
                parameters=list(parameters or []),
                positive_evidence=max(0, int(positive_evidence)),
                negative_evidence=max(0, int(negative_evidence)),
            )
        self.skills[obj.name] = obj
        return obj

    def get_skill(self, name: str) -> Skill | None:
        """Retrieves an in-memory skill by name."""
        return self.skills.get(name)

    def record_outcome(self, name: str, success: bool) -> bool:
        """Updates NARS positive/negative evidence counts ($w^+, w^-$) for a skill."""
        now = time.time()
        updated = False
        if name in self.skills:
            sk = self.skills[name]
            if success:
                sk.positive_evidence += 1
            else:
                sk.negative_evidence += 1
            sk.last_used_at = now
            updated = True

        if self.rule_engine is not None and name in self.rule_engine.rules:
            rule = self.rule_engine.rules[name]
            if not success:
                rule.failure_count += 1
            updated = True

        return updated

    def retrieve_active_skills(
        self,
        context_query: str = "",
        top_k: int = 10,
        now: float | None = None,
    ) -> list[Skill]:
        """Retrieves top-K active skills ranked by ACT-R Spreading Activation & NARS confidence.

        Activation formula:
            A_i = ln(1 + w_i^+) - 0.5 * ln(1 + dt_i) + 2.0 * context_overlap + 3.0 * (f_i * c_i)
        """
        current_time = now if now is not None else time.time()
        pool: dict[str, Skill] = dict(self.skills)

        # Include disk/rule-engine active skills if not yet in self.skills
        if self.rule_engine is not None:
            for r_id, r in self.rule_engine.rules.items():
                if r.status == "ACTIVE" and r_id not in pool:
                    pos = max(1, len(r.success_clusters) + 1)
                    neg = max(0, r.failure_count)
                    pool[r_id] = Skill(
                        name=r_id,
                        s_expr="",
                        description=" ".join(r.categories),
                        positive_evidence=pos,
                        negative_evidence=neg,
                        categories=list(r.categories),
                        status=r.status,
                    )

        query_tokens = {
            t
            for t in re.sub(r"[^\w\s]", " ", context_query.lower().replace("-", " ").replace("_",
                " ")).split()
            if len(t) > 1
        }

        scored: list[tuple[float, Skill]] = []
        for sk in pool.values():
            if sk.status != "ACTIVE":
                continue
            dt = max(0.0, current_time - sk.last_used_at)
            base_activation = math.log(1.0 + max(0, sk.positive_evidence)) - 0.5 * math.log(
                1.0 + dt
            )
            if query_tokens:
                doc_text = f"{sk.name} {sk.description} {' '.join(sk.categories)} {sk.s_expr}"
                sk_tokens = {
                    t
                    for t in re.sub(
                        r"[^\w\s]", " ", doc_text.lower().replace("-", " ").replace("_", " ")
                    ).split()
                    if len(t) > 1
                }
                overlap = len(query_tokens & sk_tokens) / max(1, len(query_tokens))
            else:
                overlap = 0.0

            bayesian_weight = sk.nars_frequency * sk.nars_confidence
            total_score = base_activation + (2.0 * overlap) + (3.0 * bayesian_weight)
            scored.append((total_score, sk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [sk for _, sk in scored[: max(0, int(top_k))]]

    def _check_ast_symbol_grounding(
        self,
        expr: SExpr,
        bound_vars: set[str],
        grounded_primitives: set[str],
    ) -> tuple[bool, str]:
        """
        Recursively verifies that all operators and leaf tool symbols in an S-expression are
        grounded.
        """
        if isinstance(expr, (int, float, bool, Keyword)):
            return (True, "")
        if isinstance(expr, Symbol):
            name = expr.name
            if (
                name not in _STANDARD_SCHEME_BUILTINS
                and name not in bound_vars
                and name not in grounded_primitives
                and name not in self.skills
            ):
                return (False, f"Ungrounded symbol in skill AST: '{name}'")
            return (True, "")
        if isinstance(expr, str):
            return (True, "")
        if not isinstance(expr, list) or not expr:
            return (True, "")

        raw_head = expr[0]
        head: str | None = (
            raw_head.name
            if isinstance(raw_head, Symbol)
            else (raw_head if isinstance(raw_head, str) else None)
        )
        if head is not None:
            if head == "quote":
                return (True, "")
            if head == "lambda" and len(expr) >= 3:
                params_raw = expr[1]
                new_bound = set(bound_vars)
                if isinstance(params_raw, list):
                    for p in params_raw:
                        if isinstance(p, Symbol):
                            new_bound.add(p.name)
                        elif isinstance(p, str):
                            new_bound.add(p)
                elif isinstance(params_raw, Symbol):
                    new_bound.add(params_raw.name)
                elif isinstance(params_raw, str):
                    new_bound.add(params_raw)
                for sub in expr[2:]:
                    ok, msg = self._check_ast_symbol_grounding(sub, new_bound, grounded_primitives)
                    if not ok:
                        return (False, msg)
                return (True, "")

            if head in ("define", "define-skill") and len(expr) >= 3:
                target = expr[1]
                new_bound = set(bound_vars)
                if isinstance(target, list) and target:
                    for p in target:
                        if isinstance(p, Symbol):
                            new_bound.add(p.name)
                        elif isinstance(p, str):
                            new_bound.add(p)
                elif isinstance(target, Symbol):
                    new_bound.add(target.name)
                elif isinstance(target, str):
                    new_bound.add(target)
                for sub in expr[2:]:
                    ok, msg = self._check_ast_symbol_grounding(sub, new_bound, grounded_primitives)
                    if not ok:
                        return (False, msg)
                return (True, "")

            if head in ("let", "let*") and len(expr) >= 3 and isinstance(expr[1], list):
                new_bound = set(bound_vars)
                for binding in expr[1]:
                    if isinstance(binding, list) and len(binding) == 2:
                        b_name = (
                            binding[0].name
                            if isinstance(binding[0], Symbol)
                            else (binding[0] if isinstance(binding[0], str) else None)
                        )
                        if b_name is not None:
                            ok, msg = self._check_ast_symbol_grounding(
                                binding[1], new_bound, grounded_primitives
                            )
                            if not ok:
                                return (False, msg)
                            new_bound.add(b_name)
                for sub in expr[2:]:
                    ok, msg = self._check_ast_symbol_grounding(sub, new_bound, grounded_primitives)
                    if not ok:
                        return (False, msg)
                return (True, "")

            if (
                head not in _STANDARD_SCHEME_BUILTINS
                and head not in bound_vars
                and head not in grounded_primitives
                and head not in self.skills
            ):
                return (False, f"Ungrounded symbol in skill AST: '{head}'")

        elif isinstance(raw_head, list):
            ok, msg = self._check_ast_symbol_grounding(raw_head, bound_vars, grounded_primitives)
            if not ok:
                return (False, msg)

        for arg in expr[1:]:
            if isinstance(arg, list):
                ok, msg = self._check_ast_symbol_grounding(arg, bound_vars, grounded_primitives)
                if not ok:
                    return (False, msg)
            elif isinstance(arg, Symbol):
                ok, msg = self._check_ast_symbol_grounding(arg, bound_vars, grounded_primitives)
                if not ok:
                    return (False, msg)

        return (True, "")

    @staticmethod
    def _normalize_list_ast(node: SExpr, bound_vars: set[str]) -> SchemeNode:
        """
        Converts raw string symbols in list-based S-expressions into Symbol nodes for
        SchemeEvaluator.
        """
        if isinstance(node, list):
            if not node:
                return []
            head = node[0]
            norm_head: SchemeNode = (
                Symbol(head) if isinstance(head, str) else SkillManager._normalize_list_ast(head,
                    bound_vars)
            )
            rest = [SkillManager._normalize_list_ast(child, bound_vars) for child in node[1:]]
            return [norm_head, *rest]
        if isinstance(node, str) and node in bound_vars:
            return Symbol(node)
        return node

    def verify_in_shadow_sandbox(
        self,
        s_expr_or_skill: Skill | str | SExpr,
        episodes: Sequence[dict[str, object]],
        grounded_primitives: set[str] | None = None,
    ) -> tuple[bool, str]:
        """Verifies a candidate skill S-expression in an isolated gas-metered Shadow Sandbox.

        1. Symbol Grounding Check: every operator and identifier in the AST must be a
           built-in MicroScheme primitive, a bound parameter/episode variable, an
           existing verified skill, or in ``grounded_primitives``.
        2. Shadow Sandbox Replay: executes the candidate S-expression against all
           historical ``(inputs, expected_output)`` episodes and requires 100% match.
        """
        if not episodes:
            return (False, "No episodes provided for shadow sandbox verification")

        bound_params: set[str] = set()
        if isinstance(s_expr_or_skill, Skill):
            raw_source = s_expr_or_skill.s_expr
            bound_params.update(s_expr_or_skill.parameters)
        elif isinstance(s_expr_or_skill, str):
            raw_source = s_expr_or_skill
        else:
            raw_source = ""

        # Collect input variable names across episodes as valid bound environment symbols
        for ep in episodes:
            raw_in = ep.get("inputs", ep.get("input", ep.get("env", {})))
            if isinstance(raw_in, dict):
                for k in raw_in:
                    bound_params.add(str(k))
            else:
                bound_params.update({"x", "n", "input", "arg"})

        try:
            if isinstance(s_expr_or_skill, list):
                parsed: SExpr = self._normalize_list_ast(s_expr_or_skill, bound_params)
            else:
                if not raw_source or not raw_source.strip():
                    return (False, "Empty skill S-expression")
                parsed = parse_expr(raw_source)
        except Exception as exc:  # noqa: BLE001
            logger.debug("shadow_sandbox_parse_error", error=str(exc))
            return (False, f"Failed to parse skill S-expression: {exc}")

        allowed_prims: set[str] = set(grounded_primitives or set())
        if self.rule_engine is not None and self.rule_engine.registered_tools:
            allowed_prims.update(self.rule_engine.registered_tools.keys())

        grounded_ok, grounded_msg = self._check_ast_symbol_grounding(
            parsed, bound_params, allowed_prims
        )
        if not grounded_ok:
            return (False, grounded_msg)

        # Replay in isolated gas-metered SchemeEvaluator across all episodes
        for idx, ep in enumerate(episodes):
            raw_inputs = ep.get("inputs", ep.get("input", ep.get("env", {})))
            has_expected = False
            expected_val: object = None
            for exp_key in ("expected_output", "output", "expected"):
                if exp_key in ep:
                    expected_val = ep[exp_key]
                    has_expected = True
                    break
            if not has_expected:
                return (False, f"Episode {idx} missing expected_output")

            evaluator = SchemeEvaluator(gas_limit=1000, timeout_ms=50.0)
            env = dict(PURE_PRIMITIVES)

            # Bind episode inputs in env as zero-arg callables for Symbol lookup
            if isinstance(raw_inputs, dict):
                for k, v in raw_inputs.items():
                    env[str(k)] = lambda _args, _v=v: _v  # type: ignore[assignment]
            elif isinstance(raw_inputs, (list, tuple)):
                for i, v in enumerate(raw_inputs):
                    env[f"arg{i}"] = lambda _args, _v=v: _v  # type: ignore[assignment]
                if len(raw_inputs) == 1:
                    env["x"] = lambda _args, _v=raw_inputs[0]: _v  # type: ignore[assignment]
                    env["n"] = lambda _args, _v=raw_inputs[0]: _v  # type: ignore[assignment]
            else:
                env["x"] = lambda _args, _v=raw_inputs: _v  # type: ignore[assignment]
                env["n"] = lambda _args, _v=raw_inputs: _v  # type: ignore[assignment]
                env["input"] = lambda _args, _v=raw_inputs: _v  # type: ignore[assignment]

            try:
                eval_node = parsed
                if (
                    isinstance(parsed, list)
                    and len(parsed) >= 3
                    and isinstance(parsed[0], Symbol)
                    and parsed[0].name in ("define", "define-skill", "lambda")
                ):
                    eval_node = parsed[2]
                actual = evaluator.eval(eval_node, env)
            except Exception as exc:  # noqa: BLE001
                logger.debug("shadow_sandbox_eval_error", episode=idx, error=str(exc))
                return (False, f"Shadow sandbox execution error on episode {idx}: {exc}")

            if not _outputs_equal(actual, expected_val):
                return (
                    False,
                    f"Shadow sandbox mismatch on episode {idx}: "
                    f"expected {expected_val!r}, got {actual!r}",
                )

        return (True, "Shadow sandbox verification passed")

    def induce_and_register_skill(
        self,
        skill: Skill,
        episodes: Sequence[dict[str, object]],
        grounded_primitives: set[str] | None = None,
    ) -> tuple[bool, str]:
        """
        Verifies a newly induced skill in the Shadow Sandbox and registers it only if verified.
        """
        ok, msg = self.verify_in_shadow_sandbox(
            skill, episodes=episodes, grounded_primitives=grounded_primitives
        )
        if not ok:
            return (False, msg)
        self.add_skill(skill)
        return (True, msg)


def _outputs_equal(actual: object, expected: object) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return bool(actual) is bool(expected) and type(actual) is type(expected)
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=1e-6)
    return actual == expected


SkillLibrary = SkillManager
