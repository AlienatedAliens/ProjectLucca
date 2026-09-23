"""
Project Lucca — Dream-RSI Replay-Before-Shadow Engine
Spec 1.1.2 §6.2 (Rung L2), §9 (Ladder Acceptance Tests)

Evaluates candidate induced/proposed rules offline against recorded interaction
episodes (from SQLite decisions table) before allowing them to consume live
shadow evaluation budget.

Enforces:
1. Zero synthetic padding: N_real must be >= min_episodes (default 50) to pass.
2. Zero tolerance: Any runtime exception, gas exhaustion, or misfire fails replay.
"""

from __future__ import annotations

import json
import re
from typing import Final

import structlog
from pydantic import BaseModel, Field

from lucca.core.schemas import RuleOutcome, RuleState
from lucca.memory.db import DatabaseManager
from lucca.reasoning.scheme.eval import evaluate_rule
from lucca.reasoning.scheme.parser import RuleDefinition

logger = structlog.get_logger(__name__)

DEFAULT_REPLAY_MIN_EPISODES: Final[int] = 50


class ReplayReport(BaseModel):
    """Structured report produced by Dream-RSI offline replay evaluation."""

    evaluated_rule_id: str
    passed: bool
    n_real: int
    min_required: int = DEFAULT_REPLAY_MIN_EPISODES
    fires: int = 0
    errors: int = 0
    misfires: int = 0
    reasons: list[str] = Field(default_factory=list)
    error_details: list[str] = Field(default_factory=list)


class ReplayEngine:
    """
    Executes offline replay of candidate rules against historical interaction episodes.
    """

    def __init__(self, min_episodes: int = DEFAULT_REPLAY_MIN_EPISODES) -> None:
        self.min_episodes = min_episodes

    def load_past_episodes(self, db: DatabaseManager, limit: int = 50) -> list[RuleState]:
        """
        Reconstructs authentic RuleState objects from historical rows in the decisions table.
        Features are stored loss-free in decisions.features_json.
        """
        episodes: list[RuleState] = []
        try:
            with db.read_cursor() as cur:
                cur.execute(
                    """
                    SELECT decision_id, features_json, action, executed_path,
                           tool_calls_json, user_interrupted
                    FROM decisions
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

            for row in rows:
                features_raw = row[1]
                user_interrupted = bool(row[5]) if row[5] is not None else False
                try:
                    feats = json.loads(features_raw) if isinstance(features_raw, str) else {}
                    state = RuleState(
                        transcript=str(feats.get("transcript", "")),
                        transcript_lower=str(feats.get("transcript_lower", "")),
                        intent=str(feats.get("intent", "unknown")),
                        intent_conf=float(feats.get("intent_conf", 0.0)),
                        entities=dict(feats.get("entities", {})),
                        hour_local=int(feats.get("hour_local", 0)),
                        weekday=int(feats.get("weekday", 0)),
                        apps_running=frozenset(feats.get("apps_running", [])),
                        last_tool=feats.get("last_tool"),
                        last_tool_ok=feats.get("last_tool_ok"),
                        session_turns=int(feats.get("session_turns", 0)),
                        mode="transcript" if feats.get("mode") == "transcript" else "audio",
                        interrupted=user_interrupted,
                    )
                    episodes.append(state)
                except Exception as parse_err:  # noqa: BLE001
                    logger.warning("replay_episode_parse_failed", error=str(parse_err))
        except Exception as exc:  # noqa: BLE001
            logger.warning("replay_load_episodes_failed", error=str(exc))

        return episodes

    def recall_past_episodes(
        self,
        db: DatabaseManager,
        query_text: str,
        limit: int = 5,
    ) -> list[dict[str, object]]:
        """
        C1 Experience Bank Recall: deterministic retrieval of past interaction episodes
        from SQLite decisions and execution_triples tables without any LLM inference.
        """
        results: list[dict[str, object]] = []
        if not query_text.strip():
            return results

        tokens = [
            t.lower()
            for t in re.findall(r"\b[a-zA-Z0-9_\-.]+\b", query_text)
            if len(t) >= 3
            and t.lower()
            not in (
                "what",
                "happened",
                "before",
                "last",
                "time",
                "when",
                "with",
                "this",
                "that",
                "were",
                "doing",
                "tell",
                "about",
            )
        ]
        if not tokens:
            return results

        candidates: list[tuple[int, float, dict[str, object]]] = []

        try:
            with db.read_cursor() as cur:
                # 1. Query decisions table
                cur.execute(
                    """
                    SELECT decision_id, features_json, action, executed_path,
                           tool_calls_json, tool_ok, ts
                    FROM decisions
                    ORDER BY ts DESC
                    LIMIT 100
                    """
                )
                for did, feat_raw, act, exec_p, tc_raw, tok, ts in cur.fetchall():
                    score = 0
                    transcript = ""
                    intent = ""
                    if feat_raw:
                        try:
                            f_dict = json.loads(feat_raw) if isinstance(feat_raw, str) else {}
                            transcript = str(f_dict.get("transcript", ""))
                            intent = str(f_dict.get("intent", ""))
                        except Exception:  # noqa: BLE001, S110
                            pass

                    target_str = f"{transcript} {intent} {act} {tc_raw or ''}".lower()
                    for t in tokens:
                        if t in target_str:
                            score += 1

                    if score > 0:
                        candidates.append(
                            (
                                score,
                                float(ts or 0.0),
                                {
                                    "source": "decisions",
                                    "decision_id": did,
                                    "transcript": transcript,
                                    "intent": intent,
                                    "action": act,
                                    "executed_path": exec_p,
                                    "tool_calls": json.loads(tc_raw)
                                    if tc_raw and isinstance(tc_raw, str)
                                    else None,
                                    "tool_ok": bool(tok) if tok is not None else None,
                                    "ts": float(ts or 0.0),
                                },
                            )
                        )

                # 2. Query execution_triples table
                cur.execute(
                    """
                    SELECT triple_id, proposal_json, decision_json, outcome_json, created_at
                    FROM execution_triples
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                )
                for tr_id, prop_j, dec_j, out_j, cat_ts in cur.fetchall():
                    target_str = f"{prop_j} {dec_j} {out_j}".lower()
                    score = sum(1 for t in tokens if t in target_str)
                    if score > 0:
                        candidates.append(
                            (
                                score,
                                float(cat_ts or 0.0),
                                {
                                    "source": "execution_triples",
                                    "triple_id": tr_id,
                                    "proposal": json.loads(prop_j)
                                    if prop_j and isinstance(prop_j, str)
                                    else prop_j,
                                    "decision": json.loads(dec_j)
                                    if dec_j and isinstance(dec_j, str)
                                    else dec_j,
                                    "outcome": json.loads(out_j)
                                    if out_j and isinstance(out_j, str)
                                    else out_j,
                                    "ts": float(cat_ts or 0.0),
                                },
                            )
                        )

            candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            results = [cand[2] for cand in candidates[:limit]]
        except Exception as exc:  # noqa: BLE001
            logger.warning("recall_past_episodes_failed", error=str(exc))

        return results

    def replay_candidate_rule(
        self,
        rule_def: RuleDefinition,
        episodes: list[RuleState],
    ) -> ReplayReport:
        """
        Replays a candidate rule against past interaction episodes.

        Gate criteria:
        1. n_real >= min_episodes (Zero synthetic padding invariant).
        2. errors == 0.
        3. misfires == 0.
        """
        n_real = len(episodes)
        fires = 0
        errors = 0
        misfires = 0
        reasons: list[str] = []
        error_details: list[str] = []

        for idx, ep in enumerate(episodes):
            try:
                outcome: RuleOutcome = evaluate_rule(rule_def, ep)
                if outcome.errored:
                    errors += 1
                    err_msg = f"Episode #{idx} (intent='{ep.intent}'): {outcome.error}"
                    error_details.append(err_msg)
                elif outcome.fired:
                    fires += 1
                    # Check for dangerous or forbidden misfires
                    if ep.intent == "dangerous":
                        misfires += 1
                        error_details.append(
                            f"Episode #{idx}: rule fired on dangerous intent '{ep.intent}'"
                        )
            except Exception as exc:  # noqa: BLE001
                errors += 1
                error_details.append(f"Episode #{idx} unhandled exception: {exc}")

        # Gate decisions
        passed = True
        if n_real < self.min_episodes:
            passed = False
            reasons.append(
                f"INSUFFICIENT_HISTORY: N_real={n_real} < {self.min_episodes}. "
                f"Candidate rule '{rule_def.rule_id}' cannot clear Dream-RSI replay "
                f"until at least {self.min_episodes} real interaction turns are recorded."
            )

        if errors > 0:
            passed = False
            reasons.append(
                f"RUNTIME_ERRORS: Rule errored on {errors} episode(s) during replay evaluation."
            )

        if misfires > 0:
            passed = False
            reasons.append(
                f"MISFIRES: Rule fired inappropriately on {misfires} episode(s) (e.g. dangerous)."
            )

        if passed:
            reasons.append(
                f"REPLAY_PASSED: Evaluated across {n_real} real interaction episodes "
                f"with 0 errors and {fires} valid matches."
            )

        return ReplayReport(
            evaluated_rule_id=rule_def.rule_id,
            passed=passed,
            n_real=n_real,
            min_required=self.min_episodes,
            fires=fires,
            errors=errors,
            misfires=misfires,
            reasons=reasons,
            error_details=error_details,
        )
