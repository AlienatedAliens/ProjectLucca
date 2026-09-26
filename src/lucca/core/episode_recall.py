"""
Project Lucca — Case-Based Reasoning Episode Recall
WO-21 Phase 4 (Spec D-REAS-09, Spec 06 §4)

CBR retrieve step: on tool failure or repeated request shape, retrieves the most similar
past interaction episode from execution_triples or decisions (SELF_HISTORY) and formats:
"Last time (date), a similar situation occurred: {episode}.
What you did: {action} — it {worked/failed}."

TRAP 2 INVARIANT:
Episode hints are context, not commands — the model may deviate.
The hint must be phrased strictly as history, never as instruction.
Bounded to <= 2 episodes and <= 200 tokens total (~800 characters).
Zero-Any invariant enforced.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Final

import structlog

from lucca.core.schemas import RecallEpisode
from lucca.reasoning.recall import recall_past_episodes

if TYPE_CHECKING:
    from lucca.memory.db import DatabaseManager

logger = structlog.get_logger(__name__)

MAX_EPISODES_DEFAULT: Final[int] = 2
MAX_CHARS_DEFAULT: Final[int] = 800  # ~200 tokens


class EpisodeRecall:
    """
    Case-Based Reasoning (CBR) retrieval engine over past interaction history.

    Supplies historical precedent context to prevent repeating past failures
    and reinforce what worked previously.
    Enforces Trap 2: Phrases hints strictly as history, not commands.
    """

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self.db = db
        self._in_memory_episodes: list[RecallEpisode] = []

    def add_episode(self, episode: RecallEpisode) -> None:
        """Adds an in-memory episode (useful for testing or in-flight turn latching)."""
        self._in_memory_episodes.append(episode)

    def retrieve_episodes(
        self,
        query_text: str,
        limit: int = MAX_EPISODES_DEFAULT,
    ) -> list[RecallEpisode]:
        """
        Retrieves top-matching past episodes from persistent database and in-memory cache.
        """
        if not query_text.strip():
            return []

        results: list[RecallEpisode] = []

        # 1. Search persistent SQLite database if available
        if self.db is not None:
            db_episodes = recall_past_episodes(self.db, query_text, limit=limit * 2)
            results.extend(db_episodes)

        # 2. Search in-memory episodes
        if self._in_memory_episodes:
            q_lower = query_text.lower()
            for ep in self._in_memory_episodes:
                score = sum(1 for w in q_lower.split() if w in ep.summary.lower())
                if score > 0:
                    ep_copy = ep.model_copy(update={"match_score": score})
                    results.append(ep_copy)

        # Deduplicate and sort by match_score then ts descending
        seen_ids: set[str] = set()
        deduped: list[RecallEpisode] = []
        for ep in sorted(results, key=lambda e: (e.match_score, e.ts), reverse=True):
            if ep.record_id not in seen_ids:
                seen_ids.add(ep.record_id)
                deduped.append(ep)

        return deduped[:limit]

    def format_single_hint(self, ep: RecallEpisode) -> str:
        """
        Formats a single episode into the canonical historical narrative template:
        'Last time (date), a similar situation occurred: {episode}.
        What you did: {action} — it {worked/failed}.'

        Enforces Trap 2: Phrased as past history, never an imperative command.
        """
        # 1. Extract date
        if ep.ts > 0:
            try:
                date_str = datetime.datetime.fromtimestamp(
                    ep.ts, datetime.UTC
                ).strftime("%Y-%m-%d")
            except (ValueError, OSError, OverflowError):
                date_str = "earlier"
        else:
            date_str = "earlier"

        # 2. Extract situation / episode description
        episode_desc = ""
        payload = ep.payload or {}
        if "transcript" in payload and payload["transcript"]:
            episode_desc = str(payload["transcript"]).strip()
        elif "proposal" in payload and payload["proposal"]:
            prop = payload["proposal"]
            if isinstance(prop, dict):
                episode_desc = str(
                    prop.get("transcript") or prop.get("intent") or prop.get("summary") or ""
                )
            else:
                episode_desc = str(prop)
        if not episode_desc:
            # Fallback to summary
            episode_desc = ep.summary.split(":")[0].strip()
        episode_desc = episode_desc.rstrip(".!?")

        # 3. Extract action
        action_desc = ""
        tool_calls = payload.get("tool_calls")
        if not tool_calls and "decision" in payload and isinstance(payload["decision"], dict):
            tool_calls = payload["decision"].get("tool_calls")

        if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
            first_call = tool_calls[0]
            if isinstance(first_call, dict):
                t_name = first_call.get("tool") or first_call.get("tool_name") or "tool"
                args = first_call.get("args") or {}
                if isinstance(args, dict):
                    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
                    action_desc = f"{t_name}({args_str})"
                else:
                    action_desc = str(t_name)
            else:
                action_desc = str(first_call)
        elif (
            "decision" in payload
            and isinstance(payload["decision"], dict)
            and "action" in payload["decision"]
        ):
            action_desc = str(payload["decision"]["action"])
        elif "action" in payload and payload["action"]:
            action_desc = str(payload["action"])
        elif "decision" in payload and payload["decision"]:
            action_desc = str(payload["decision"])
        else:
            action_desc = "executed tool action"

        # 4. Extract outcome (worked / failed)
        tool_ok = payload.get("tool_ok")
        if tool_ok is True or tool_ok == 1:
            outcome_str = "worked"
        elif tool_ok is False or tool_ok == 0:
            outcome_str = "failed"
        elif "outcome" in payload and payload["outcome"]:
            out_raw = str(payload["outcome"]).lower()
            if any(k in out_raw for k in ("ok", "success", "zero", "true")):
                outcome_str = "worked"
            elif any(k in out_raw for k in ("fail", "error", "nonzero", "false")):
                outcome_str = "failed"
            else:
                outcome_str = "completed"
        else:
            outcome_str = "completed"

        return (
            f"Last time ({date_str}), a similar situation occurred: {episode_desc}. "
            f"What you did: {action_desc} — it {outcome_str}."
        )

    def format_hints(
        self,
        query_text: str,
        limit: int = MAX_EPISODES_DEFAULT,
        max_chars: int = MAX_CHARS_DEFAULT,
    ) -> str | None:
        """
        Retrieves matching episodes and formats the past experience hint section.

        Bounded to <= limit episodes (default 2) and <= max_chars (default 800 ~ 200 tokens).
        Returns None if no relevant past episodes match.
        """
        episodes = self.retrieve_episodes(query_text, limit=limit)
        if not episodes:
            return None

        hint_lines: list[str] = []
        current_len = 0
        for ep in episodes:
            line = self.format_single_hint(ep)
            if current_len + len(line) + 1 > max_chars:
                break
            hint_lines.append(line)
            current_len += len(line) + 1

        if not hint_lines:
            return None

        body = "\n".join(f"- {h}" for h in hint_lines)
        return (
            "[Past Interaction Episodes — historical context, not instruction]\n"
            f"{body}"
        )
