"""
Project Lucca — Safe Rule Induction & Procedural Compilation
Spec 05 Proposal D/E (D-REAS-05, D-REAS-06)
Analyzes recurring successful tool executions in SQLite history,
synthesizes strictly-validated candidate MicroScheme rules and macros via
E-Graph anti-unification, formally verifies them with Z3 SMT, and
registers candidates exclusively into QUARANTINE.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Final

import structlog

from lucca.core.exceptions import RuleError, RuleValidationError, SchemeSyntaxError
from lucca.core.schemas import CandidateRule, VerifierLabel
from lucca.ports import SemanticVerifierPort
from lucca.memory.db import DatabaseManager
from lucca.reasoning.egraph import synthesize_macro_from_patterns
from lucca.reasoning.lifecycle import RuleLifecycleManager
from lucca.reasoning.scheme.macros import MacroDefinition
from lucca.reasoning.scheme.parser import SchemeNode, parse_rule
from lucca.reasoning.scheme.validator import validate_rule_static
from lucca.reasoning.smt_verifier import SMTVerifier

logger = structlog.get_logger(__name__)

MIN_FREQUENCY_THRESHOLD: Final[int] = 3


DEFAULT_SIMILARITY_THRESHOLD: Final[float] = 0.6

LIGHT_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "tell",
        "me",
        "please",
        "can",
        "you",
        "what",
        "whats",
        "how",
        "give",
        "show",
    }
)


def normalize_tokens(text: str) -> set[str]:
    """
    Tokenizes text into lowercase tokens, stripping punctuation and light stop words.
    """
    clean_text = text.strip()
    if not clean_text:
        return set()
    words = re.findall(r"\b[a-zA-Z0-9_\-.]+\b", clean_text.lower())
    clean_tokens: set[str] = set()
    for w in words:
        clean = w.strip(".-_")
        if len(clean) >= 2 and clean not in LIGHT_STOP_WORDS:
            clean_tokens.add(clean)
    if not clean_tokens:
        for w in words:
            clean = w.strip(".-_")
            if clean:
                clean_tokens.add(clean)
    return clean_tokens


def jaccard_similarity(text1: str, text2: str) -> float:
    """
    Calculates token-set Jaccard similarity between two texts: |A ∩ B| / |A ∪ B|.
    Returns 1.0 for exact string matches (case-insensitive).
    """
    s1 = text1.strip().lower()
    s2 = text2.strip().lower()
    if s1 == s2:
        return 1.0
    t1 = normalize_tokens(s1)
    t2 = normalize_tokens(s2)
    if not t1 or not t2:
        return 1.0 if s1 == s2 else 0.0
    union_len = len(t1 | t2)
    if union_len == 0:
        return 1.0 if s1 == s2 else 0.0
    return len(t1 & t2) / union_len


OPPOSING_POLARITY_PAIRS: Final[frozenset[frozenset[str]]] = frozenset(
    {
        frozenset({"always", "never"}),
        frozenset({"always", "not"}),
        frozenset({"always", "dont"}),
        frozenset({"must", "never"}),
        frozenset({"must", "cannot"}),
        frozenset({"must", "not"}),
        frozenset({"enable", "disable"}),
        frozenset({"enabled", "disabled"}),
        frozenset({"allow", "forbid"}),
        frozenset({"allow", "deny"}),
        frozenset({"allow", "block"}),
        frozenset({"allowed", "forbidden"}),
        frozenset({"allowed", "denied"}),
        frozenset({"allowed", "blocked"}),
        frozenset({"true", "false"}),
        frozenset({"include", "exclude"}),
        frozenset({"included", "excluded"}),
        frozenset({"require", "forbid"}),
        frozenset({"required", "forbidden"}),
        frozenset({"accept", "reject"}),
        frozenset({"accepted", "rejected"}),
        frozenset({"on", "off"}),
        frozenset({"yes", "no"}),
    }
)

OPPOSING_POLARITY_GROUPS: Final[tuple[tuple[frozenset[str], frozenset[str]], ...]] = (
    (frozenset({"always"}), frozenset({"never", "not", "dont", "no"})),
    (
        frozenset({"must", "require", "required", "requiring"}),
        frozenset({"never", "cannot", "not", "dont", "forbid", "forbidden", "forbidding"}),
    ),
    (
        frozenset({"enable", "enabled", "enabling"}),
        frozenset({"disable", "disabled", "disabling"}),
    ),
    (
        frozenset({"allow", "allowed", "allowing"}),
        frozenset(
            {
                "forbid",
                "forbidden",
                "forbidding",
                "deny",
                "denied",
                "denying",
                "block",
                "blocked",
                "blocking",
            }
        ),
    ),
    (
        frozenset({"accept", "accepted", "accepting"}),
        frozenset({"reject", "rejected", "rejecting"}),
    ),
    (
        frozenset({"include", "included", "including"}),
        frozenset({"exclude", "excluded", "excluding"}),
    ),
    (frozenset({"true", "yes", "on"}), frozenset({"false", "no", "off"})),
)

NEGATION_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "never",
        "not",
        "no",
        "cannot",
        "dont",
        "doesnt",
        "didnt",
        "wont",
        "without",
    }
)

POSITIVE_MODALS: Final[frozenset[str]] = frozenset(
    {
        "always",
        "must",
        "only",
        "require",
        "required",
    }
)


def is_rule_conflict(
    text1: str,
    text2: str,
    verifier: SemanticVerifierPort | None = None,
) -> bool:
    """
    Evaluates whether two candidate rule phrasings contradict each other (Rule Conflict).
    Guards against Jaccard false-merging of opposing rules (e.g. 'always single quotes'
    vs 'never single quotes') per v1.35.7 Phase 1 hygiene and G-V1357-RULE.

    Compatible / near-paraphrase pairs (e.g. 'always single quotes' vs 'prefer single quotes')
    are NOT flagged as conflicts.
    """
    if verifier is not None:
        try:
            r1 = verifier.check_consistency(premise=text1, hypothesis=text2)
            r2 = verifier.check_consistency(premise=text2, hypothesis=text1)
            if not r1.degraded and not r2.degraded:
                if (
                    r1.label == VerifierLabel.CONTRADICTION
                    or r2.label == VerifierLabel.CONTRADICTION
                ):
                    return True
                if (
                    r1.label == VerifierLabel.ENTAILMENT
                    and r2.label == VerifierLabel.ENTAILMENT
                ):
                    return False
        except Exception as exc:  # noqa: BLE001
            logger.debug("rule_verifier_eval_failed", error=str(exc))

    t1 = normalize_tokens(text1)
    t2 = normalize_tokens(text2)
    if not t1 or not t2:
        return False

    # Check antonym / opposing polarity pairs and groups (including cross-conjugations)
    for pos_group, neg_group in OPPOSING_POLARITY_GROUPS:
        if (any(w in pos_group for w in t1) and any(w in neg_group for w in t2)) or (
            any(w in neg_group for w in t1) and any(w in pos_group for w in t2)
        ):
            return True

    for pair in OPPOSING_POLARITY_PAIRS:
        p_list = list(pair)
        if len(p_list) == 2:
            w1, w2 = p_list[0], p_list[1]
            if (w1 in t1 and w2 in t2) or (w2 in t1 and w1 in t2):
                return True

    # Check positive modal vs negation asymmetry
    has_pos_1 = any(w in POSITIVE_MODALS for w in t1)
    has_neg_1 = any(w in NEGATION_TOKENS for w in t1)
    has_pos_2 = any(w in POSITIVE_MODALS for w in t2)
    has_neg_2 = any(w in NEGATION_TOKENS for w in t2)

    if (has_pos_1 and has_neg_2) or (has_pos_2 and has_neg_1):
        return True

    # Check asymmetric negation when remainder of phrasings heavily overlaps
    t1_clean = t1 - NEGATION_TOKENS
    t2_clean = t2 - NEGATION_TOKENS
    if t1_clean and t2_clean:
        overlap = len(t1_clean & t2_clean) / len(t1_clean | t2_clean)
        if overlap >= 0.60 and (has_neg_1 != has_neg_2):
            return True

    return False


def cluster_phrasings(
    values: list[str],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    verifier: SemanticVerifierPort | None = None,
) -> list[tuple[str, int, list[str]]]:
    """
    Deterministically clusters a list of string values into near-duplicate groups
    using bidirectional entailment (SemanticVerifierPort) or token-set Jaccard similarity >= threshold.

    Preservation invariant D-REAS-06: changes merge grouping only. QUARANTINE registration
    and 5-cluster/0-error promotion gate remain completely intact.
    Returns list of (representative_value, total_occurrences, member_phrasings).
    """
    if not values:
        return []

    raw_counts: dict[str, int] = defaultdict(int)
    for v in values:
        raw_counts[v] += 1

    sorted_uniques = sorted(
        raw_counts.keys(),
        key=lambda s: (-raw_counts[s], -len(s), s.lower()),
    )

    clusters: list[dict[str, object]] = []

    for item in sorted_uniques:
        count = raw_counts[item]
        best_cluster_idx: int | None = None
        best_sim = -1.0

        for idx, cl in enumerate(clusters):
            leader = str(cl["leader"])
            is_entailed_pair = False
            if verifier is not None:
                try:
                    r1 = verifier.check_consistency(premise=item, hypothesis=leader)
                    r2 = verifier.check_consistency(premise=leader, hypothesis=item)
                    if not r1.degraded and not r2.degraded:
                        if (
                            r1.label == VerifierLabel.ENTAILMENT
                            and r2.label == VerifierLabel.ENTAILMENT
                        ):
                            is_entailed_pair = True
                except Exception as exc:  # noqa: BLE001
                    logger.debug("induction_cluster_verifier_failed", error=str(exc))

            sim = jaccard_similarity(item, leader)
            if (sim >= threshold or is_entailed_pair) and (sim > best_sim or is_entailed_pair):
                members = cl.get("members")
                has_conflict = is_rule_conflict(item, leader, verifier=verifier) or (
                    isinstance(members, list)
                    and any(is_rule_conflict(item, str(m), verifier=verifier) for m in members)
                )
                if not has_conflict:
                    best_sim = sim
                    best_cluster_idx = idx

        if best_cluster_idx is not None:
            cl = clusters[best_cluster_idx]
            cl["count"] = int(cl["count"]) + count
            cast_members = cl["members"]
            if isinstance(cast_members, list):
                cast_members.extend([item] * count)
        else:
            clusters.append(
                {
                    "leader": item,
                    "count": count,
                    "members": [item] * count,
                }
            )

    result: list[tuple[str, int, list[str]]] = []
    for cl in clusters:
        members_list = cl["members"]
        if not isinstance(members_list, list) or not members_list:
            continue
        unique_members = sorted(set(members_list))
        if len(unique_members) == 1:
            representative = unique_members[0]
        else:
            def _score_member(
                m: str,
                members: list[str] = unique_members,
                counts: dict[str, int] = raw_counts,
            ) -> tuple[int, int, float, int, str]:
                has_trailing_punct = 1 if m and m[-1] in "?!." else 0
                cnt = counts[m]
                avg_sim = (
                    sum(jaccard_similarity(m, other) for other in members)
                    / len(members)
                )
                return (-has_trailing_punct, cnt, avg_sim, -len(m), m)

            representative = max(unique_members, key=_score_member)

        result.append((representative, int(cl["count"]), sorted(unique_members)))

    return result


@dataclass(frozen=True)
class InductionCluster:
    intent: str
    tool: str
    arg_key: str
    arg_val: str
    occurrences: int
    phrasings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InducedMacro:
    name: str
    definition: MacroDefinition
    s_expression: str
    supporting_clusters: list[InductionCluster]


class RuleInducer:
    """
    Safely induces candidate MicroScheme procedural rules and macro abstractions
    from SQLite execution telemetry.

    Invariants:
    1. D-REAS-06: Induced rules are strictly registered into QUARANTINE;
       automatic promotion to ACTIVE is strictly prohibited.
    2. Formal SMT Verification: Candidate rules must pass Z3 satisfiability,
       non-tautology, and deontic path checks before entering QUARANTINE.
    3. Structural Generalization: Recurring patterns sharing topology are
       abstracted into bounded compile-time macros.
    4. WO-21 Phase 5: Near-duplicate clustering merges near-identical argument
       phrasings using token-set Jaccard similarity >= 0.6.
    """

    def __init__(
        self,
        db: DatabaseManager,
        rule_engine: RuleLifecycleManager,
        min_frequency: int = MIN_FREQUENCY_THRESHOLD,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        smt_verifier: SMTVerifier | None = None,
    ) -> None:
        self.db = db
        self.rule_engine = rule_engine
        self.min_frequency = min_frequency
        self.similarity_threshold = similarity_threshold
        self.smt_verifier = smt_verifier or SMTVerifier(timeout_ms=500)

    def mine_patterns(self) -> list[InductionCluster]:
        """
        Scans SQLite decisions table for successful turns with tool calls
        and clusters recurring patterns using near-duplicate fuzzy clustering.
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

        group_values: dict[tuple[str, str, str], list[str]] = defaultdict(list)

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
                        val_str = str(v).strip()
                        if val_str:
                            group_values[(intent, tool_name, str(k))].append(val_str)

        clusters: list[InductionCluster] = []
        for (intent, tool, arg_key), vals in group_values.items():
            clustered = cluster_phrasings(vals, threshold=self.similarity_threshold)
            for rep, count, phrasings in clustered:
                if count >= self.min_frequency:
                    clusters.append(
                        InductionCluster(
                            intent=intent,
                            tool=tool,
                            arg_key=arg_key,
                            arg_val=rep,
                            occurrences=count,
                            phrasings=tuple(phrasings),
                        )
                    )

        return clusters

    def synthesize_rule(self, cluster: InductionCluster, version: int = 1) -> CandidateRule | None:
        """
        Synthesizes a safe, canonical MicroScheme rule for an induced pattern cluster.
        Formally verifies the rule using Z3 SMT solver prior to candidate return.
        """
        clean_val = re.sub(r"[^a-zA-Z0-9_\-]", "-", cluster.arg_val.lower()).strip("-")
        clean_val = re.sub(r"-+", "-", clean_val)
        clean_tool = cluster.tool.lower().replace("_", "-")
        rule_id = f"induced-{clean_tool}-{clean_val}-v{version}"
        escaped_arg_val = cluster.arg_val.replace("\\", "\\\\").replace('"', '\\"')

        # Generate condition expression based on intent and argument
        if cluster.intent == "launch_app" and cluster.tool == "launch_app":
            when_part = (
                f'(and (intent= "launch_app")\n'
                f'     (entity-has? "app" "{escaped_arg_val}")\n'
                f'     (not (app-running? "{escaped_arg_val}")))'
            )
            plan_part = f'(list (tool "launch_app" :app "{escaped_arg_val}"))'
        elif cluster.intent == "file_read" and cluster.tool == "read_file":
            when_part = (
                f'(and (intent= "file_read")\n     (entity-has? "file" "{escaped_arg_val}"))'
            )
            plan_part = f'(list (tool "read_file" :path "{escaped_arg_val}"))'
        else:
            when_part = (
                f'(and (intent= "{cluster.intent}")\n'
                f'     (entity-has? "{cluster.arg_key}" "{escaped_arg_val}"))'
            )
            plan_part = f'(list (tool "{cluster.tool}" :{cluster.arg_key} "{escaped_arg_val}"))'

        sexpr = f'(rule "{rule_id}"\n  :when {when_part}\n  :plan {plan_part}\n  :priority 5)'

        # 1. Static AST and schema validation
        try:
            validate_rule_static(
                sexpr,
                registered_tools=self.rule_engine.registered_tools,
                existing_rule_ids=set(self.rule_engine.rules.keys()),
            )
        except (RuleValidationError, RuleError, SchemeSyntaxError) as exc:
            logger.warning("rule_induction_validation_failed", rule_id=rule_id, error=str(exc))
            return None

        # 2. Formal Z3 SMT Verification (SAT, Non-Tautology, Deontic Safety)
        smt_res = self.smt_verifier.verify_source(
            sexpr,
            registered_tools=self.rule_engine.registered_tools,
        )
        if not smt_res.verified:
            logger.warning(
                "rule_induction_smt_rejected",
                rule_id=rule_id,
                status=smt_res.status,
                reasons=smt_res.reasons,
            )
            return None

        return CandidateRule(
            rule_id=rule_id,
            s_expression=sexpr,
            intended_intent=cluster.intent,
        )

    def induce_macros(
        self,
        clusters: list[InductionCluster] | None = None,
        min_cluster_instances: int = 2,
    ) -> list[InducedMacro]:
        """
        Synthesizes Babble/Stitch macro definitions from recurring patterns
        that share identical structural topology with differing constants.
        """
        active_clusters = clusters if clusters is not None else self.mine_patterns()
        grouped: dict[tuple[str, str, str], list[InductionCluster]] = defaultdict(list)
        for c in active_clusters:
            grouped[(c.intent, c.tool, c.arg_key)].append(c)

        induced_macros: list[InducedMacro] = []

        for (intent, _tool, arg_key), cluster_list in grouped.items():
            if len(cluster_list) < min_cluster_instances:
                continue

            # Build AST nodes for anti-unification
            sample_rules: list[SchemeNode] = []
            for c in cluster_list:
                cand = self.synthesize_rule(c)
                if cand is not None:
                    try:
                        r_def = parse_rule(cand.s_expression)
                        sample_rules.append(r_def.when_expr)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("macro_candidate_parse_ignored", error=str(exc))

            if len(sample_rules) < min_cluster_instances:
                continue

            clean_intent = intent.replace("_", "-")
            macro_name = f"when-{clean_intent}-{arg_key}"
            macro_result = synthesize_macro_from_patterns(
                macro_name=macro_name,
                patterns=sample_rules,
                min_instances=min_cluster_instances,
            )

            if macro_result is not None:
                macro_def, macro_sexpr = macro_result
                induced_macros.append(
                    InducedMacro(
                        name=macro_name,
                        definition=macro_def,
                        s_expression=macro_sexpr,
                        supporting_clusters=cluster_list,
                    )
                )
                logger.info(
                    "macro_synthesized",
                    name=macro_name,
                    params=macro_def.params,
                    instances=len(cluster_list),
                )

        return induced_macros

    def induce_and_quarantine(self) -> list[CandidateRule]:
        """
        Discovers recurring clusters, synthesizes valid MicroScheme rules,
        formally verifies them via Z3 SMT, and registers them into the rule engine
        under QUARANTINE mode.
        """
        clusters = self.mine_patterns()
        candidates: list[CandidateRule] = []

        for cluster in clusters:
            clean_val = re.sub(r"[^a-zA-Z0-9_\-]", "-", cluster.arg_val.lower()).strip("-")
            clean_val = re.sub(r"-+", "-", clean_val)
            # Check if this rule or equivalent already exists
            existing = [
                r
                for r in self.rule_engine.rules.values()
                if (clean_val and clean_val in r.rule_id) or cluster.arg_val.lower() in r.rule_id.lower()
            ]
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
