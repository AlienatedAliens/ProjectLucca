"""
Project Lucca — Heuristic Decision Router & Lexicon Matcher
Spec 06 §1, §2, §3
"""

import json
import re
import time
import tomllib
import uuid
from pathlib import Path
from typing import Final, Literal

import numpy as np
import structlog

from lucca.core.schemas import (
    DecisionRecord,
    ExecutionTier,
    RouteAction,
    RouteDecision,
    RouteFeatures,
    ToolCall,
)
from lucca.memory.db import DatabaseManager
from lucca.router.conformal import ConformalGuard

logger = structlog.get_logger(__name__)

EMERGENCY_REFLEX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:please|lucca|hey\s+lucca)\s+)?"
    r"(shut\s*down|turn\s*off|exit(?!\s+(?:code|status|number|value))|quit|pause|mute|stop(?:\s+(?:everything|all|listening|doing|it|right\s+now|right\s+here))?|halt)"
    r"(?:\s+(?:everything|all|now|please|immediately|lucca|right\s+now|right\s+here|doing\s+that|listening|audio|yourself|execution|the\s+system|it))?[.!]?$",
    re.IGNORECASE,
)

DEFAULT_KNOWN_APPS: Final[frozenset[str]] = frozenset(
    {
        "calculator",
        "calc",
        "notepad",
        "text editor",
        "browser",
        "edge",
        "chrome",
        "terminal",
        "cmd",
        "powershell",
        "code",
        "vscode",
    }
)

DEFAULT_STOP_WORDS_AFTER_START: Final[frozenset[str]] = frozenset(
    {"with", "at", "from", "on", "by", "for", "in", "to"}
)

FILE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b([a-zA-Z0-9_\-./\\]+\.(?:txt|md|py|json|csv|pdf|docx|toml|yaml|yml|sql|rs|cpp|h|c|log|env))\b",
    re.IGNORECASE,
)
URL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:https?://\S+|\b(?:[a-zA-Z0-9-]+\.)+(?:com|org|net|gov|edu|io|ai|co|ph)(?:/\S*)?)\b",
    re.IGNORECASE,
)
QUOTED_PATTERN: Final[re.Pattern[str]] = re.compile(r'"([^"]+)"')

INTENT_TO_RULE: Final[frozenset[str]] = frozenset(
    {"launch_app", "file_read", "file_write", "web_fetch"}
)

_ACTION_LIT: Final[dict[str, Literal["RULE", "LLM", "CLARIFY"]]] = {
    "RULE": "RULE",
    "LLM": "LLM",
    "CLARIFY": "CLARIFY",
}

INTENT_CATEGORY_MAP: Final[dict[str, str]] = {
    "file_read": "self",
    "file_write": "self",
    "web_fetch": "information",
    "memory_query": "cognitive_core",
    "chit_chat": "companion",
    "launch_app": "self",
}


def map_intent_to_category(
    intent: str,
    entities: dict[str, list[str]] | None = None,
) -> str | None:
    """
    Deterministic mapping from heuristic router intent/entities to a 7-category menu slot (T1.4).
    If no mapping fires, logs a category_miss telemetry event and returns None.
    """
    cat = INTENT_CATEGORY_MAP.get(intent)
    if cat is not None:
        return cat
    logger.info("category_miss", intent=intent, entities=entities)
    return None


class HeuristicRouter:
    """
    Phase 4 deterministic decision router with word-boundary regex intent matching
    and decision telemetry logging to SQLite + JSONL.
    """

    def __init__(
        self,
        log_path: Path | str | None = None,
        db: DatabaseManager | None = None,
        config_path: Path | str | None = None,
        conformal_guard: ConformalGuard | None = None,
        confidence_threshold: float = 0.60,
    ) -> None:
        self.log_path = Path(log_path) if log_path is not None else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = db
        self.conformal_guard = conformal_guard
        self.confidence_threshold = confidence_threshold
        self.known_apps = set(DEFAULT_KNOWN_APPS)
        self.stop_words_after_start = set(DEFAULT_STOP_WORDS_AFTER_START)
        self.last_decision_record: DecisionRecord | None = None
        self._load_intents_config(config_path)

    def _load_intents_config(self, config_path: Path | str | None) -> None:
        path = (
            Path(config_path)
            if config_path is not None
            else Path(r"C:\ProjectLucca\config\intents.toml")
        )
        if not path.exists():
            return
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            intents = data.get("intents", {})
            launch_cfg = intents.get("launch_app", {})
            if "apps" in launch_cfg and isinstance(launch_cfg["apps"], list):
                self.known_apps.update(str(a).lower() for a in launch_cfg["apps"])
            if "stop_words_after_start" in launch_cfg and isinstance(
                launch_cfg["stop_words_after_start"], list
            ):
                self.stop_words_after_start.update(
                    str(w).lower() for w in launch_cfg["stop_words_after_start"]
                )
            router_cfg = data.get("router", {})
            if "confidence_threshold" in router_cfg:
                self.confidence_threshold = float(router_cfg["confidence_threshold"])
        except (OSError, tomllib.TOMLDecodeError, ValueError):
            pass

    def classify_intent(self, transcript: str) -> tuple[str, float, dict[str, list[str]]]:
        """
        Classifies intent and extracts entities using word-boundary regexes per Spec 06 §2.
        Returns (intent, confidence, entities).
        """
        text = transcript.strip().lower()
        entities: dict[str, list[str]] = {
            "app": [],
            "file": [],
            "url": [],
            "quoted": [],
        }

        # Extract entities
        for f in FILE_PATTERN.findall(text):
            entities["file"].append(f)
        for u in URL_PATTERN.findall(text):
            entities["url"].append(u)
        for q in QUOTED_PATTERN.findall(transcript):
            entities["quoted"].append(q)

        # 0. Dangerous / Boundary (Safety First): destructive, sensitive, or adversarial requests
        dangerous_pattern = (
            r"\b(delete\s+(?:all|every|my)|rm\s+-rf|format\s+(?:[a-z]:?|drive|disk)|drop\s+(?:table|database)|"
            r"wipe|destroy|erase\s+(?:all|every|my)|remove\s+all)\b"
        )
        sensitive_pattern = (
            r"\b(password|passwd|secret|credential|api.?key|token|ssn|"
            r"social\s+security|credit\s+card)\b"
        )
        hijack_pattern = (
            r"\b(pretend\s+you(?:'re|\s+are)|act\s+as\s+(?:if\s+you|a\s+different)|"
            r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions|"
            r"you\s+are\s+now|forget\s+(?:everything|your\s+(?:instructions|rules)))\b"
        )
        prompt_extract_pattern = (
            r"\b(system\s+prompt|system\s+message|initial\s+prompt|hidden\s+instructions|"
            r"tell\s+me\s+your\s+(?:prompt|instructions|rules|system))\b"
        )
        if re.search(dangerous_pattern, text):
            return "dangerous", 0.95, entities
        if re.search(sensitive_pattern, text):
            return "dangerous", 0.95, entities
        if re.search(hijack_pattern, text):
            return "dangerous", 0.90, entities
        if re.search(prompt_extract_pattern, text):
            return "dangerous", 0.85, entities

        # 1. Launch App: check word boundary
        launch_match = re.search(
            r"\b(open|launch|start|run)\b\s+(?:the\s+)?(?P<app>[a-z0-9 .-]+)",
            text,
        )
        if launch_match:
            candidate_app = launch_match.group("app").strip()
            first_word = candidate_app.split()[0] if candidate_app else ""
            # Guard against adversarial: "start with the second file"
            if first_word not in self.stop_words_after_start:
                # Check if candidate or any alias is a known app
                for app_name in sorted(self.known_apps, key=lambda a: (-len(a), a)):
                    if re.search(rf"\b{re.escape(app_name)}\b", candidate_app):
                        entities["app"].append(app_name)
                        return "launch_app", 0.95, entities
                if not entities["file"] and len(candidate_app.split()) <= 2:
                    entities["app"].append(candidate_app)
                    return "launch_app", 0.85, entities

        # 2. File Read
        if (
            re.search(r"\b(read|view|show|cat|inspect|examine)\b\s+(?:the\s+)?(?:file\s+)?", text)
            and entities["file"]
        ):
            return "file_read", 0.90, entities

        # 3. File Write
        if (
            re.search(r"\b(write|create|save|append|dump)\b\s+(?:to\s+)?", text)
            and entities["file"]
        ):
            return "file_write", 0.90, entities

        # 4. Memory Query
        mem_pattern = (
            r"\b(remember|recall|what\s+is\s+my|who\s+is\s+my|where\s+do\s+i|do\s+you\s+remember)\b"
        )
        if re.search(mem_pattern, text):
            return "memory_query", 0.90, entities

        # 5. Chit Chat
        chit_pattern = (
            r"\b(hello|hi|hey|how\s+are\s+you|what's\s+up|thank\s+you|thanks|"
            r"good\s+morning|good\s+afternoon|good\s+night)\b"
        )
        if re.search(chit_pattern, text):
            return "chit_chat", 0.95, entities

        # 6. Web Fetch / Search & Factual Inquiries
        web_pattern = (
            r"\b(fetch|browse|download|web|scrape|curl|lookup|look\s*up|"
            r"search(?:\s+(?:for|google|online|the\s+web|web|wikipedia))?|"
            r"google|check\s+(?:google|wikipedia|online|news)|"
            r"find\s+(?:out|information|online)|headlines|wikipedia|"
            r"tell\s+me\s+about|facts\s+about|who\s+(?:is|was)|"
            r"what\s+(?:is|are|can\s+you\s+tell)|where\s+(?:is|are|was|does)|"
            r"when\s+(?:was|is)|how\s+about)\b"
        )
        if re.search(web_pattern, text) or entities["url"]:
            return "web_fetch", 0.90, entities

        # 7. Clarify: very short utterance
        if len(text.split()) <= 1 and text:
            return "clarify", 0.40, entities

        return "unknown", 0.20, entities

    def route(
        self,
        transcript: str,
        any_active_rule_fired: bool = False,
        any_quarantine_rule_fired: bool = False,
        vad_speech_ms: int = 1000,
        intent_conf: float | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
        hour_local: int = 0,
        weekday: int = 0,
        apps_running: list[str] | None = None,
        last_tool: str | None = None,
        last_tool_ok: bool | None = None,
        session_turns: int = 0,
        mode: Literal["audio", "transcript"] = "transcript",
        has_registered_rule: bool = False,
    ) -> RouteDecision:
        """
        Executes routing decision logic per Spec 06 §1 & §2 and logs full DecisionRecord.
        """
        t0 = time.perf_counter()

        intent, auto_conf, entities = self.classify_intent(transcript)
        conf = intent_conf if intent_conf is not None else auto_conf
        text_lower = transcript.strip().lower()

        fallback_applied = False
        calibrated = False
        probabilities: dict[str, float] | None = None
        prediction_set: list[RouteAction] = []

        rule_eligible = any_active_rule_fired or (
            intent in INTENT_TO_RULE
            and conf >= 0.80
            and (has_registered_rule or any_active_rule_fired)
        )

        if rule_eligible:
            p_vec = np.array([conf, 1.0 - conf, 0.0], dtype=np.float64)
        elif (
            vad_speech_ms < 400
            or intent == "clarify"
            or (intent in INTENT_TO_RULE and conf < 0.35 and not any_active_rule_fired)
        ):
            p_vec = np.array([0.0, 1.0 - conf, conf], dtype=np.float64)
        else:
            p_vec = np.array([0.0, conf, 1.0 - conf], dtype=np.float64)

        if abs(float(np.sum(p_vec)) - 1.0) > 1e-9:
            raise ValueError(f"Probability vector does not sum to 1.0: {p_vec}")

        probabilities = {
            "RULE": float(p_vec[0]),
            "LLM": float(p_vec[1]),
            "CLARIFY": float(p_vec[2]),
        }

        # Decision logic per Spec 06 §1, §2, §7, ADR-007, and D-ARCH-05
        if EMERGENCY_REFLEX_PATTERN.search(text_lower):
            action_lit: Literal["RULE", "LLM", "CLARIFY"] = "RULE"
            prediction_set = [RouteAction.RULE]
        elif self.conformal_guard is not None and self.conformal_guard.q_hat is not None:
            conf_action, pred_classes, conf_fallback = self.conformal_guard.decide(
                p_vec, class_names=["RULE", "LLM", "CLARIFY"]
            )
            fallback_applied = conf_fallback or (
                conf < self.confidence_threshold and intent != "dangerous"
            )
            action_lit = "LLM" if fallback_applied else _ACTION_LIT[conf_action]
            prediction_set = [RouteAction(a) for a in pred_classes]
            calibrated = True
        elif rule_eligible:
            action_lit = "RULE"
            prediction_set = [RouteAction.RULE]
        elif (
            vad_speech_ms < 400
            or intent == "clarify"
            or (intent in INTENT_TO_RULE and conf < 0.35 and not any_active_rule_fired)
        ):
            action_lit = "CLARIFY"
            prediction_set = [RouteAction.CLARIFY]
        else:
            action_lit = "LLM"
            prediction_set = [RouteAction.LLM]
            if conf < self.confidence_threshold and intent != "dangerous":
                fallback_applied = True

        elapsed_us = int((time.perf_counter() - t0) * 1_000_000)

        # Determine ExecutionTier per D-ARCH-05 (Spec 06, Owner Section 6 Mandate)
        if action_lit == "RULE":
            if EMERGENCY_REFLEX_PATTERN.search(text_lower):
                tier = ExecutionTier.REFLEX
            else:
                tier = ExecutionTier.ACT_THEN_NARRATE
        else:
            tier = ExecutionTier.FULL_LOOP

        route_action = RouteAction(action_lit)
        decision = RouteDecision(
            action=route_action,
            tier=tier,
            probabilities=probabilities,
            prediction_set=prediction_set if prediction_set else [route_action],
            fallback_applied=fallback_applied,
            calibrated=calibrated,
            elapsed_us=elapsed_us,
        )

        features = RouteFeatures(
            transcript=transcript,
            transcript_lower=text_lower,
            intent=intent,
            intent_conf=conf,
            entities=entities,
            hour_local=hour_local,
            weekday=weekday,
            apps_running=apps_running or [],
            last_tool=last_tool,
            last_tool_ok=last_tool_ok,
            session_turns=session_turns,
            mode=mode,
            vad_speech_ms=vad_speech_ms,
            any_active_rule_fired=any_active_rule_fired,
            any_quarantine_rule_fired=any_quarantine_rule_fired,
            has_registered_rule=has_registered_rule,
            tier=tier,
        )

        tid = trace_id or f"trace-{uuid.uuid4().hex[:8]}"
        sid = session_id or f"session-{uuid.uuid4().hex[:8]}"
        did = f"dec-{uuid.uuid4().hex[:12]}"

        record = DecisionRecord(
            decision_id=did,
            trace_id=tid,
            session_id=sid,
            ts=time.time(),
            features=features,
            decision=decision,
            router_version="heuristic-1.0-deterministic",
            executed_path=action_lit,
            counterfactual_rule_fired=any_quarantine_rule_fired,
        )
        self.last_decision_record = record

        if self.log_path:
            self._log_decision_jsonl(record)
        if self.db:
            self._log_decision_sqlite(record)

        return decision

    def _log_decision_jsonl(self, record: DecisionRecord) -> None:
        if not self.log_path:
            return
        payload = record.model_dump()
        payload["transcript"] = record.features.transcript
        payload["intent"] = record.features.intent
        payload["intent_conf"] = record.features.intent_conf
        payload["action"] = record.decision.action.value
        payload["tier"] = record.decision.tier.value
        payload["probabilities"] = record.decision.probabilities
        payload["elapsed_us"] = record.decision.elapsed_us

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _log_decision_sqlite(self, record: DecisionRecord) -> None:
        if not self.db:
            return
        try:
            writer = self.db.get_writer()
            writer.execute(
                """
                INSERT INTO decisions(
                    decision_id, trace_id, session_id, ts, features_json, action,
                    probabilities_json, prediction_set_json, fallback_applied, elapsed_us,
                    router_version, executed_path, tool_calls_json, tool_ok, llm_first_token_ms,
                    user_interrupted, interrupted_after_ms, counterfactual_rule_fired
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.decision_id,
                    record.trace_id,
                    record.session_id,
                    record.ts,
                    json.dumps(record.features.model_dump(), ensure_ascii=False),
                    record.decision.action.value,
                    json.dumps(record.decision.probabilities),
                    json.dumps([a.value for a in record.decision.prediction_set]),
                    1 if record.decision.fallback_applied else 0,
                    record.decision.elapsed_us,
                    record.router_version,
                    record.executed_path,
                    json.dumps([tc.model_dump() for tc in record.tool_calls])
                    if record.tool_calls
                    else None,
                    None if record.tool_ok is None else (1 if record.tool_ok else 0),
                    record.llm_first_token_ms,
                    1 if record.user_interrupted else 0,
                    record.interrupted_after_ms,
                    1 if record.counterfactual_rule_fired else 0,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("decision_sqlite_log_failed", error=str(exc))

    def record_post_turn(
        self,
        decision_id: str,
        tool_calls: list[ToolCall] | None = None,
        tool_ok: bool | None = None,
        llm_first_token_ms: float | None = None,
        user_interrupted: bool = False,
        interrupted_after_ms: float | None = None,
    ) -> None:
        """Updates decision record with post-turn outcomes (tools, latencies, barge-in)."""
        if self.db:
            try:
                writer = self.db.get_writer()
                writer.execute(
                    """
                    UPDATE decisions SET
                        tool_calls_json = ?,
                        tool_ok = ?,
                        llm_first_token_ms = ?,
                        user_interrupted = ?,
                        interrupted_after_ms = ?
                    WHERE decision_id = ?
                    """,
                    (
                        json.dumps([tc.model_dump() for tc in tool_calls]) if tool_calls else None,
                        None if tool_ok is None else (1 if tool_ok else 0),
                        llm_first_token_ms,
                        1 if user_interrupted else 0,
                        interrupted_after_ms,
                        decision_id,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("post_turn_sqlite_update_failed", error=str(exc))

        if self.last_decision_record and self.last_decision_record.decision_id == decision_id:
            if tool_calls is not None:
                self.last_decision_record.tool_calls = tool_calls
            if tool_ok is not None:
                self.last_decision_record.tool_ok = tool_ok
            if llm_first_token_ms is not None:
                self.last_decision_record.llm_first_token_ms = llm_first_token_ms
            self.last_decision_record.user_interrupted = user_interrupted
            self.last_decision_record.interrupted_after_ms = interrupted_after_ms
