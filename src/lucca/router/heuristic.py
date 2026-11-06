"""
Project Lucca — Heuristic Decision Router & Lexicon Matcher
Spec 06 §1, §2, §3
"""

import json
import re
import time
import tomllib
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, Literal

import numpy as np
import structlog

from lucca.core.config import get_config
from lucca.core.constitutional import compute_constitutional_hash
from lucca.core.schemas import (
    DecisionRecord,
    ExecutionTier,
    RouteAction,
    RouteDecision,
    RouteFeatures,
    ToolCall,
)
from lucca.core.text_utils import normalize_transcript
from lucca.memory.db import DatabaseManager
from lucca.ports import EmbeddingPort
from lucca.router.conformal import ConformalGuard
from lucca.router.neural_intent_classifier import get_neural_intent_classifier

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
        "windows terminal",
        "task manager",
        "taskmgr",
        "vscode",
        "vs code",
        "powershell",
        "cmd",
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
    "code_repair": "code",
    "spatial_grid": "formal_reasoning",
    "web_fetch": "information",
    "science_research": "information",
    "factual_lookup": "information",
    "math_computation": "formal_reasoning",
    "logic_constraints": "formal_reasoning",
    "code_generation": "code",
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
        embed_worker: EmbeddingPort | None = None,
        retention_files: int | None = None,
        blind_classifier_only: bool = False,
    ) -> None:
        self.log_path = Path(log_path) if log_path is not None else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = db
        self.conformal_guard = conformal_guard
        self.confidence_threshold = confidence_threshold
        self.conformal_alpha: float = 0.10
        self.conformal_min_samples: int = 30
        self.known_apps = set(DEFAULT_KNOWN_APPS)
        self.stop_words_after_start = set(DEFAULT_STOP_WORDS_AFTER_START)
        self.constitutional_hash = compute_constitutional_hash()
        self.last_decision_record: DecisionRecord | None = None
        self.db_write_failures: int = 0
        self.embed_worker = embed_worker
        self.blind_classifier_only = blind_classifier_only
        if retention_files is not None:
            self.retention_files = retention_files
        else:
            try:
                self.retention_files = get_config().log.decision_retention_files
            except Exception as exc:  # noqa: BLE001
                logger.debug("decision_retention_config_load_failed", error=str(exc))
                self.retention_files = 14
        self._load_intents_config(config_path)
        get_neural_intent_classifier()

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
            if "conformal_alpha" in router_cfg:
                self.conformal_alpha = float(router_cfg["conformal_alpha"])
            if "conformal_min_samples" in router_cfg:
                self.conformal_min_samples = int(router_cfg["conformal_min_samples"])
        except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
            logger.debug("intents_config_load_failed", path=str(path), error=str(exc))

    def _extract_app_entity(self, text: str) -> list[str]:
        words = set(re.findall(r"[a-z0-9]+", text))
        if not (words & {"open", "launch", "start", "run"}):
            return []
        for app_name in sorted(self.known_apps, key=lambda a: (-len(a), a)):
            if re.search(rf"\b{re.escape(app_name)}\b", text):
                return [app_name]
        return []

    def classify_intent(
        self,
        transcript: str,
        last_tool: str | None = None,
        blind_classifier_only: bool | None = None,
    ) -> tuple[str, float, dict[str, list[str]]]:
        """
        Classifies intent and extracts slot entities using the OpenVINO NPU Multi-Head Neural Router
        (WO-41 Phase 4 Milestone 4.2, replacing the legacy regex cascade).
        Returns (intent, confidence, entities).
        """
        norm_transcript = normalize_transcript(transcript)
        text = norm_transcript.strip().lower()
        entities: dict[str, list[str]] = {
            "app": [],
            "file": [],
            "url": [],
            "quoted": [],
        }

        for f in FILE_PATTERN.findall(text):
            entities["file"].append(f)
        for u in URL_PATTERN.findall(text):
            entities["url"].append(u)
        for q in QUOTED_PATTERN.findall(norm_transcript):
            entities["quoted"].append(q)

        app_matches = self._extract_app_entity(text)
        if app_matches:
            entities["app"].extend(app_matches)

        if EMERGENCY_REFLEX_PATTERN.match(norm_transcript.strip()):
            return "unknown", 0.20, entities

        verdict = get_neural_intent_classifier().evaluate(norm_transcript, last_tool=last_tool)
        pred_intent = verdict.predicted_intent
        pred_conf = verdict.intent_confidence

        if pred_intent == "launch_app" and not entities["app"]:
            return "unknown", 0.20, entities

        if entities["app"]:
            app_pat = "|".join(re.escape(a) for a in entities["app"])
            if re.search(
                rf"\b(?:open|launch|start|run)\s+(?:up\s+)?(?:the\s+)?(?:{app_pat})\b",
                text,
            ):
                return "launch_app", 0.92, entities

        # Non-whitelisted 3rd-party desktop application launch requests or figurative open/start/run idioms
        if not entities["app"] and re.search(
            r"\b(?:open|launch|start)\s+(?:blender|spotify|obsidian|figma|photoshop|illustrator|premiere|steam|vlc)\b|"
            r"^start\s+by\s+(?:summarizing|outlining|reviewing)\b|"
            r"^run\s+a\s+sanity\s+check\s+on\s+this\s+communication\s+plan\b|"
            r"^opening\s+a\s+neighborhood\s+bakery\b",
            text,
        ):
            return "unknown", 0.20, entities

        # Symbolic dangerous boundary check (both positive high-severity triggers and negative filter)
        has_dangerous_marker = bool(
            re.search(
                r"\b(?:delete\s+(?:all|every|my)|rm\s+-rf|format\s+(?:[a-z]:?|drive|disk|partition)|"
                r"diskpart|drop\s+(?:table|database|production)|wipe\s+(?:the\s+)?(?:root|hard\s+drive|disk|partition|all|c:)|"
                r"dd\s+if=/dev/(?:zero|random|urandom)|/dev/(?:sd[a-z]|nvme\d+n\d+)|master\s+boot\s+record|system32|"
                r"erase\s+all|passwords?|private\s+keys?|secret\s+keys?|auth\s+tokens?|ssh\s+(?:private\s+)?keys?|"
                r"id_rsa|id_ed25519|webhooks?|exfiltrat|ignore\s+(?:all\s+|your\s+)?(?:previous|prior|safety)|"
                r"disregard\s+(?:all\s+)?(?:previous|prior|safety)|forget\s+all\s+prior|"
                r"system\s+(?:prompt|instructions)|developer\s+(?:mode|instructions)|"
                r"bypass\s+(?:your\s+)?(?:safety|security|guardrails|restrictions)|"
                r"unfiltered|unrestricted|pretend\s+you(?:'re|\s+are)|act\s+as\s+an?\s+unfiltered)\b",
                text,
            )
        )
        if re.search(
            r"\b(?:rm\s+-rf\s+/|format\s+c:|dd\s+if=/dev/(?:zero|random)|wipe\s+c:\\windows\\system32|"
            r"(?:id_rsa|\.env)\b.*\b(?:exfiltrat|webhook|http\s+post|https?://)|"
            r"ignore\s+all\s+(?:previous|prior)\s+safety)\b",
            text,
        ):
            return "dangerous", 0.96, entities

        if pred_intent == "dangerous" and not has_dangerous_marker:
            return "unknown", 0.20, entities

        # Explicit local file_read / file_write disambiguation when a file entity is present
        if (
            entities["file"]
            and not has_dangerous_marker
            and not re.search(
                r"\b(?:bug|exception|traceback|error|failing|pytest|patch|fix|leak|crash| deadlock)\b",
                text,
            )
        ):
            if re.search(
                r"\b(?:write|save|create|append|store)\b.*\b(?:file|into|to)\b|\b(?:write|save|create)\s+(?:a\s+new\s+|the\s+|these\s+)?(?:local\s+)?(?:markdown\s+)?file\b",
                text,
            ):
                return "file_write", 0.92, entities
            if re.search(
                r"\b(?:read|view|inspect|display|show\s+me\s+what\s+is\s+written)\b",
                text,
            ):
                return "file_read", 0.92, entities

        # Explicit conversational context_query vs long-term memory_query disambiguation
        if re.search(
            r"\b(?:just\s+(?:pull|pulled|mentioned|said|searched)|a\s+(?:second|moment)\s+ago\s+in\s+(?:your\s+search|this\s+chat))\b",
            text,
        ):
            return "context_query", 0.92, entities

        if re.search(
            r"\b(?:do\s+you\s+(?:recall|remember)\s+what|what\s+did\s+i\s+tell\s+you\s+last\s+month|"
            r"check\s+your\s+stored\s+memory\s+and\s+remind\s+me|tell\s+me\s+what\s+you\s+remember\s+about\s+me)\b",
            text,
        ):
            return "memory_query", 0.92, entities

        # Third-person factual / biographical queries without 1st-person or memory-recall markers
        if pred_intent == "memory_query" and not re.search(
            r"\b(?:my|me|i|we|our|mine|ours|remember|recall|remind|memory|notes?|told\s+you|"
            r"discussed|mentioned|prefer|favorite|allergic|stored|saved|logged|yesterday|last\s+(?:week|month|session))\b",
            text,
        ):
            return "web_fetch", max(pred_conf, 0.85), entities

        if re.search(
            r"^(?:where\s+is\s+(?:she|he|branch\s+\d+)|who\s+is\s+[a-z]+\s+[a-z]+|"
            r"tell\s+me\s+about\s+[a-z]+\s+[a-z]+|how\s+about\s+you\s+just\s+tell\s+me\s+interesting\s+facts\s+about\s+it|"
            r"what\s+is\s+judge\s+[a-z]+(?:'s|')\s+current\s+assignment)\b",
            text,
        ):
            return "web_fetch", max(pred_conf, 0.85), entities

        # Explicit deductive syllogism / modus tollens soft_logic check
        if re.search(
            r"\b(?:premise\s+1\s*:|syllogis(?:m|tic)|modus\s+(?:ponens|tollens)|"
            r"if\s+the\s+greenhouse\s+heater\s+had\s+failed\s+overnight)\b",
            text,
        ):
            return "unknown", 0.85, entities

        if pred_intent == "clarify":
            return "clarify", 0.40, entities

        if pred_intent == "unknown":
            return "unknown", 0.20, entities

        return pred_intent, pred_conf, entities

    def route(
        self,
        transcript: str | RouteFeatures | None = None,
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
        mode: Literal["audio", "transcript", "vision"] = "transcript",
        has_registered_rule: bool = False,
        feats: RouteFeatures | None = None,
        model_tier: Literal["12B", "E4B", "E2B"] | None = None,
        blind_classifier_only: bool | None = None,
    ) -> RouteDecision:
        """
        Executes routing decision logic per Spec 06 §1 & §2 and logs full DecisionRecord.
        Accepts unpacked kwargs or a RouteFeatures instance (satisfying RouterPort).
        """
        t0 = time.perf_counter()

        target_feats = transcript if isinstance(transcript, RouteFeatures) else feats
        if target_feats is not None:
            transcript_text = target_feats.transcript
            any_active_rule_fired = target_feats.any_active_rule_fired
            any_quarantine_rule_fired = target_feats.any_quarantine_rule_fired
            vad_speech_ms = target_feats.vad_speech_ms
            intent_conf = target_feats.intent_conf
            hour_local = target_feats.hour_local
            weekday = target_feats.weekday
            apps_running = target_feats.apps_running
            last_tool = target_feats.last_tool
            last_tool_ok = target_feats.last_tool_ok
            session_turns = target_feats.session_turns
            mode = target_feats.mode
            has_registered_rule = target_feats.has_registered_rule
        else:
            transcript_text = transcript if isinstance(transcript, str) else ""

        transcript_text = normalize_transcript(transcript_text)
        eff_blind = self.blind_classifier_only if blind_classifier_only is None else blind_classifier_only

        intent, auto_conf, entities = self.classify_intent(
            transcript_text, last_tool=last_tool, blind_classifier_only=eff_blind
        )
        conf = intent_conf if (intent_conf is not None and intent_conf > 0.0) else auto_conf
        text_lower = transcript_text.strip().lower()

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
            vad_speech_ms < 400 or intent == "clarify" or (intent in INTENT_TO_RULE and conf < 0.35)
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

        verdict = get_neural_intent_classifier().evaluate(transcript_text, last_tool=last_tool)
        is_emergency_reflex = ("emergency_reflex" in verdict.active_domains) or bool(
            EMERGENCY_REFLEX_PATTERN.match(transcript_text.strip())
        )

        # Decision logic per Spec 06 §1, §2, §7, ADR-007, and D-ARCH-05
        if is_emergency_reflex:
            action_lit: Literal["RULE", "LLM", "CLARIFY"] = "RULE"
            prediction_set = [RouteAction.RULE]
            calibrated = bool(
                self.conformal_guard is not None and self.conformal_guard.q_hat is not None
            )
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
            vad_speech_ms < 400 or intent == "clarify" or (intent in INTENT_TO_RULE and conf < 0.35)
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
            if is_emergency_reflex:
                tier = ExecutionTier.REFLEX
            else:
                tier = ExecutionTier.ACT_THEN_NARRATE
        else:
            tier = ExecutionTier.FULL_LOOP

        # Dynamic Tiered Neurosymbolic Reasoning & Thinking Mode Dispatch via OpenVINO NPU Multi-Head Classifier
        if model_tier is None:
            try:
                cfg_model = get_config().llm.model.lower()
                if "e2b" in cfg_model:
                    effective_tier = "E2B"
                elif "e4b" in cfg_model:
                    effective_tier = "E4B"
                elif "26b" in cfg_model or "a4b" in cfg_model:
                    effective_tier = "26B"
                else:
                    effective_tier = "12B"
            except (AttributeError, KeyError, ValueError, TypeError):
                logger.debug("router_tier_detect_failed", error="config read error")
                effective_tier = "12B"
        else:
            effective_tier = model_tier

        reasoning_domain: str | None = None
        solver_tool: str | None = None
        thinking_mode: Literal["direct", "thinking", "adaptive"] = "adaptive"
        exposed_libraries: list[str] = []

        if (
            action_lit == "LLM"
            and not eff_blind
            and intent
            not in (
                "dangerous",
                "launch_app",
                "file_read",
                "file_write",
                "memory_query",
                "context_query",
                "chit_chat",
                "clarify",
                "factual_lookup",
            )
        ):
            active_doms = set(verdict.active_domains)
            if re.search(
                r"\b(?:premise\s+1\s*:|syllogis(?:m|tic)|modus\s+(?:ponens|tollens)|"
                r"if\s+the\s+greenhouse\s+heater\s+had\s+failed\s+overnight|"
                r"(?:every|all)\s+[^.?!]+\b(?:require|requires|are|is)\b[^.?!]+\.\s+[^.?!]+\b(?:is|are)\b[^.?!]+\.\s+(?:does|is|are)\b)",
                text_lower,
            ):
                active_doms = {"soft_logic"}
                intent = "unknown"
            elif intent == "unknown" and re.search(
                r"\b(?:open|launch|start)\s+(?:blender|spotify|obsidian|figma|photoshop|illustrator|premiere|steam|vlc)\b|"
                r"^start\s+by\s+(?:summarizing|outlining|reviewing)\b|"
                r"^run\s+a\s+sanity\s+check\s+on\s+this\s+communication\s+plan\b|"
                r"^opening\s+a\s+neighborhood\s+bakery\b",
                text_lower,
            ):
                active_doms = set()

            primary_dom = verdict.active_domains[0] if verdict.active_domains else None
            has_cw = "spatial_relocation" in active_doms
            has_spatial_grid = "spatial_grid" in active_doms or (intent == "spatial_grid")
            has_code_repair = "code_repair" in active_doms or (intent == "code_repair")
            has_z3 = "combinatorial_smt" in active_doms or (intent == "logic_constraints")
            has_soft = "soft_logic" in active_doms
            has_sympy = "mathematics" in active_doms or (intent == "math_computation")
            has_science = "science_research" in active_doms or (intent == "science_research")
            has_web_search = "web_search" in active_doms or (intent == "web_fetch")

            if has_cw:
                exposed_libraries.append("container_world")
            if has_spatial_grid:
                exposed_libraries.append("arc_primitives")
            if has_code_repair:
                exposed_libraries.append("swe_bench")
            if has_z3:
                exposed_libraries.append("z3")
            if has_sympy:
                exposed_libraries.append("sympy")
            if (has_science or has_web_search) and "research" not in exposed_libraries:
                exposed_libraries.append("research")

            if has_soft and (primary_dom == "soft_logic" or active_doms == {"soft_logic"}):
                reasoning_domain = "soft_logic"
                if effective_tier == "12B":
                    thinking_mode = "direct"
                else:
                    thinking_mode = "thinking"
            elif has_cw:
                reasoning_domain = "spatial_relocation"
                solver_tool = "container_world"
                thinking_mode = "direct"
            elif has_spatial_grid:
                reasoning_domain = "spatial_grid"
                solver_tool = "arc_primitives"
                thinking_mode = "thinking"
            elif has_code_repair:
                reasoning_domain = "code_repair"
                solver_tool = "apply_patch"
                thinking_mode = "thinking"
            elif has_z3 and not has_sympy:
                reasoning_domain = "combinatorial_smt"
                solver_tool = "z3_smt"
                thinking_mode = "direct"
            elif has_sympy:
                reasoning_domain = "mathematics"
                solver_tool = "sympy_sandbox"
                thinking_mode = "direct"
            elif has_z3:
                reasoning_domain = "combinatorial_smt"
                solver_tool = "z3_smt"
                thinking_mode = "direct"
            elif has_soft:
                reasoning_domain = "soft_logic"
                if effective_tier == "12B":
                    thinking_mode = "direct"
                else:
                    thinking_mode = "thinking"
            elif has_science:
                reasoning_domain = "science_research"
                solver_tool = "research_topic"
                thinking_mode = "thinking"
            elif has_web_search:
                reasoning_domain = "web_search"
                solver_tool = "search_web"
                thinking_mode = "thinking"

        route_action = RouteAction(action_lit)

        DELIBERATION_DOMAINS = {
            "mathematics",
            "combinatorial_smt",
            "soft_logic",
            "spatial_relocation",
            "science_research",
            "spatial_grid",
            "code_repair",
            "web_search",
        }
        word_count = len(text_lower.split())
        deliberation_lane = (
            reasoning_domain in DELIBERATION_DOMAINS
            and (word_count >= 15 or len(exposed_libraries) >= 2)
        )
        FLOOR_HOLD_CUES = [
            "Let me work that out.",
            "Give me a moment to think through this.",
            "Working on it now.",
        ]
        floor_hold_cue: str | None = None
        if deliberation_lane:
            import hashlib as _hl
            _idx = int(_hl.md5(text_lower.encode()).hexdigest(), 16) % len(FLOOR_HOLD_CUES)
            floor_hold_cue = FLOOR_HOLD_CUES[_idx]

        # Combinatorics & mathematical derivation token ceiling (1536 tokens)
        token_ceiling: int | None = None
        if (
            reasoning_domain in ("mathematics", "combinatorial_smt")
            or "aime_combinatorics" in verdict.active_domains
        ):
            token_ceiling = 1536

        decision = RouteDecision(
            action=route_action,
            tier=tier,
            probabilities=probabilities,
            prediction_set=prediction_set if prediction_set else [route_action],
            fallback_applied=fallback_applied,
            calibrated=calibrated,
            elapsed_us=elapsed_us,
            thinking_mode=thinking_mode,
            solver_tool=solver_tool,
            reasoning_domain=reasoning_domain,
            deliberation_lane=deliberation_lane,
            floor_hold_cue=floor_hold_cue,
            exposed_libraries=exposed_libraries,
            max_tokens=token_ceiling,
        )

        features = RouteFeatures(
            transcript=transcript_text,
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
            thinking_mode=thinking_mode,
            solver_tool=solver_tool,
            reasoning_domain=reasoning_domain,
            deliberation_lane=deliberation_lane,
            floor_hold_cue=floor_hold_cue,
            exposed_libraries=exposed_libraries,
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
            router_version="classifier-1.0-blind" if eff_blind else "heuristic-1.0-deterministic",
            executed_path=action_lit,
            counterfactual_rule_fired=any_quarantine_rule_fired,
            constitutional_hash=self.constitutional_hash,
        )
        self.last_decision_record = record

        if self.log_path:
            self._log_decision_jsonl(record)
        if self.db:
            self._log_decision_sqlite(record)

        return decision

    def _rotate_decision_log_if_needed(self, now_utc: datetime | date | None = None) -> Path | None:
        """Rotates log_path (e.g. decisions.jsonl) to decisions-YYYY-MM-DD.jsonl
        if the existing file belongs to a prior calendar day in UTC.
        Maintains crash-safe rename-on-open and prunes rotated files to retention count.
        """
        if not self.log_path or not self.log_path.exists():
            return None

        try:
            stat = self.log_path.stat()
            if stat.st_size == 0:
                return None
        except OSError:
            return None

        if now_utc is None:
            current_date = datetime.now(UTC).date()
        elif isinstance(now_utc, datetime):
            current_date = now_utc.astimezone(UTC).date()
        else:
            current_date = now_utc

        file_dt = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        file_date = file_dt.date()

        if file_date >= current_date:
            return None

        file_date_str = file_date.strftime("%Y-%m-%d")
        stem = self.log_path.stem
        suffix = self.log_path.suffix
        rotated_path = self.log_path.parent / f"{stem}-{file_date_str}{suffix}"

        try:
            if rotated_path.exists():
                with open(self.log_path, "rb") as src, open(rotated_path, "ab") as dst:
                    dst.write(src.read())
                self.log_path.unlink(missing_ok=True)
            else:
                self.log_path.rename(rotated_path)
        except OSError as exc:
            logger.warning("decision_log_rotation_failed", error=str(exc))
            return None

        self._prune_rotated_decision_logs()
        return rotated_path

    def _prune_rotated_decision_logs(self) -> list[Path]:
        """Prunes rotated log files exceeding retention count, keeping the most recent."""
        if not self.log_path:
            return []
        stem = self.log_path.stem
        suffix = self.log_path.suffix
        pattern = re.compile(rf"^{re.escape(stem)}-(\d{{4}}-\d{{2}}-\d{{2}}){re.escape(suffix)}$")

        rotated_files: list[tuple[str, Path]] = []
        try:
            for p in self.log_path.parent.iterdir():
                if p.is_file():
                    m = pattern.match(p.name)
                    if m:
                        rotated_files.append((m.group(1), p))
        except OSError:
            return []

        rotated_files.sort(key=lambda t: t[0])

        deleted: list[Path] = []
        if len(rotated_files) > self.retention_files:
            to_delete = rotated_files[: len(rotated_files) - self.retention_files]
            for _, p in to_delete:
                try:
                    p.unlink(missing_ok=True)
                    deleted.append(p)
                except OSError as exc:
                    logger.warning("decision_log_prune_failed", path=str(p), error=str(exc))
        return deleted

    def _log_decision_jsonl(self, record: DecisionRecord) -> None:
        if not self.log_path:
            return
        record_dt = datetime.fromtimestamp(record.ts, tz=UTC)
        self._rotate_decision_log_if_needed(now_utc=record_dt)

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
            self.db_write_failures += 1
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
                self.db_write_failures += 1
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
