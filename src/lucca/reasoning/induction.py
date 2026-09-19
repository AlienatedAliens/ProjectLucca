"""
Project Lucca — Safe Rule Induction & Procedural Compilation
Spec 05 Proposal E (D-REAS-06)
Analyzes recurring successful tool executions in SQLite history, synthesizes
strictly-validated candidate MicroScheme rules, and registers them into QUARANTINE.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Final

import structlog

from lucca.core.exceptions import RuleValidationError, SchemeSyntaxError
from lucca.core.schemas import CandidateRule
from lucca.memory.db import DatabaseManager
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.validator import validate_rule_static

logger = structlog.get_logger(__name__)

MIN_FREQUENCY_THRESHOLD: Final[int] = 3


@dataclass(frozen=True)
class InductionCluster:
    intent: str
    tool: str
    arg_key: str
    arg_val: str
    occurrences: int


class RuleInducer:
    """
    Safely induces candidate MicroScheme procedural rules from SQLite execution telemetry.
    Invariant (D-REAS-06): Induced rules are strictly registered into QUARANTINE;
    automatic promotion to ACTIVE is prohibited.
    """

    def __init__(
        self,
        db: DatabaseManager,
        rule_engine: RuleLifecycleManager,
        min_frequency: int = MIN_FREQUENCY_THRESHOLD,
    ) -> None:
        self.db = db
        self.rule_engine = rule_engine
        self.min_frequency = min_frequency

    def mine_patterns(self) -> list[InductionCluster]:
        """
        Scans SQLite decisions table for successful turns with tool calls
        and clusters recurring patterns.
        """
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT decision_id, features_json, tool_calls_json, tool_ok
                FROM decisions
                WHERE tool_ok = 1 AND tool_calls_json IS NOT NULL
                ORDER BY ts ASC
                """
            )
            rows = cur.fetchall()

        cluster_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)

        for _did, feat_raw, tool_calls_raw, _tok in rows:
            if not feat_raw or not tool_calls_raw:
                continue

            try:
                features = json.loads(feat_raw)
                tool_calls = json.loads(tool_calls_raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(features, dict) or not isinstance(tool_calls, list):
                continue

            intent = str(features.get("intent") or "unknown")
            entities = features.get("entities", {})
            if not isinstance(entities, dict):
                entities = {}

            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                tool_name = str(tc.get("tool") or "")
                args = tc.get("args")
                if not tool_name or not isinstance(args, dict):
                    continue

                # Inspect key argument pairs
                for k, v in args.items():
                    if isinstance(v, (str, int, float, bool)):
                        val_str = str(v).strip().lower()
                        if val_str:
                            cluster_counts[(intent, tool_name, str(k), val_str)] += 1

        clusters: list[InductionCluster] = []
        for (intent, tool, arg_key, arg_val), count in cluster_counts.items():
            if count >= self.min_frequency:
                clusters.append(
                    InductionCluster(
                        intent=intent,
                        tool=tool,
                        arg_key=arg_key,
                        arg_val=arg_val,
                        occurrences=count,
                    )
                )

        return clusters

    def synthesize_rule(self, cluster: InductionCluster, version: int = 1) -> CandidateRule | None:
        """
        Synthesizes a safe, canonical MicroScheme rule for an induced pattern cluster.
        """
        clean_val = cluster.arg_val.replace(" ", "-").replace(".", "-").replace("_", "-")
        clean_tool = cluster.tool.replace("_", "-")
        rule_id = f"induced-{clean_tool}-{clean_val}-v{version}"

        # Generate condition expression based on intent and argument
        if cluster.intent == "launch_app" and cluster.tool == "launch_app":
            when_part = (
                f'(and (intent= "launch_app")\n'
                f'     (entity-has? "app" "{cluster.arg_val}")\n'
                f'     (not (app-running? "{cluster.arg_val}")))'
            )
            plan_part = f'(list (tool "launch_app" :app "{cluster.arg_val}"))'
        elif cluster.intent == "file_read" and cluster.tool == "read_file":
            when_part = (
                f'(and (intent= "file_read")\n     (entity-has? "file" "{cluster.arg_val}"))'
            )
            plan_part = f'(list (tool "read_file" :path "{cluster.arg_val}"))'
        else:
            when_part = (
                f'(and (intent= "{cluster.intent}")\n'
                f'     (entity-has? "{cluster.arg_key}" "{cluster.arg_val}"))'
            )
            plan_part = f'(list (tool "{cluster.tool}" :{cluster.arg_key} "{cluster.arg_val}"))'

        sexpr = f'(rule "{rule_id}"\n  :when {when_part}\n  :plan {plan_part}\n  :priority 5)'

        try:
            # Validate statically before constructing candidate
            validate_rule_static(
                sexpr,
                registered_tools=self.rule_engine.registered_tools,
                existing_rule_ids=set(self.rule_engine.rules.keys()),
            )
        except (RuleValidationError, SchemeSyntaxError) as exc:
            logger.warning("rule_induction_validation_failed", rule_id=rule_id, error=str(exc))
            return None

        return CandidateRule(
            rule_id=rule_id,
            s_expression=sexpr,
            intended_intent=cluster.intent,
        )

    def induce_and_quarantine(self) -> list[CandidateRule]:
        """
        Discovers recurring clusters, synthesizes valid MicroScheme rules,
        and registers them into the rule engine under QUARANTINE mode.
        """
        clusters = self.mine_patterns()
        candidates: list[CandidateRule] = []

        for cluster in clusters:
            # Check if this rule or equivalent already exists
            existing = [r for r in self.rule_engine.rules.values() if cluster.arg_val in r.rule_id]
            if existing:
                continue

            candidate = self.synthesize_rule(cluster)
            if candidate is not None:
                try:
                    self.rule_engine.register_candidate(candidate)
                    candidates.append(candidate)
                    logger.info(
                        "induced_rule_quarantined",
                        rule_id=candidate.rule_id,
                        intent=candidate.intended_intent,
                        occurrences=cluster.occurrences,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "failed_to_register_candidate",
                        rule_id=candidate.rule_id,
                        error=str(exc),
                    )

        return candidates
