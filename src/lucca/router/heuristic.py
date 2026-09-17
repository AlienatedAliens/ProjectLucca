"""
Project Lucca — Heuristic Decision Router & Lexicon Matcher
Spec 06 §1, §2, §3
"""

import json
import re
import time
import uuid
from pathlib import Path
from typing import Literal

from lucca.core.schemas import RouteAction, RouteDecision

KNOWN_APPS = frozenset(
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

STOP_WORDS_AFTER_START = frozenset({"with", "at", "from", "on", "by", "for", "in", "to"})

FILE_PATTERN = re.compile(r"\b([\w\-.]+\.(?:txt|md|py|json|csv|pdf|docx))\b", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+")
QUOTED_PATTERN = re.compile(r'"([^"]+)"')


class HeuristicRouter:
    """
    Phase 4 deterministic decision router with word-boundary regex intent matching
    and decision logging.
    """

    def __init__(self, log_path: Path | str | None = None) -> None:
        self.log_path = Path(log_path) if log_path is not None else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def classify_intent(self, transcript: str) -> tuple[str, float, dict[str, list[str]]]:
        """
        Classifies intent and extracts entities using word-boundary regexes.
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

        # 1. Launch App: check word boundary
        launch_match = re.search(
            r"\b(open|launch|start|run)\b\s+(?:the\s+)?(?P<app>[a-z0-9 .-]+)",
            text,
        )
        if launch_match:
            candidate_app = launch_match.group("app").strip()
            first_word = candidate_app.split()[0] if candidate_app else ""
            # Guard against adversarial: "start with the second file"
            if first_word not in STOP_WORDS_AFTER_START:
                # Check if candidate or any alias is a known app
                for app_name in KNOWN_APPS:
                    if app_name in candidate_app:
                        entities["app"].append(app_name)
                        return "launch_app", 0.95, entities
                if not entities["file"] and len(candidate_app.split()) <= 2:
                    entities["app"].append(candidate_app)
                    return "launch_app", 0.85, entities

        # 2. File Read
        if (
            re.search(r"\b(read|view|show|cat)\b\s+(?:the\s+)?(?:file\s+)?", text)
            and entities["file"]
        ):
            return "file_read", 0.90, entities

        # 3. File Write
        if re.search(r"\b(write|create|save|append)\b\s+(?:to\s+)?", text) and entities["file"]:
            return "file_write", 0.90, entities

        # 4. Web Fetch
        if re.search(r"\b(fetch|browse|download|web|scrape|curl)\b", text) or entities["url"]:
            return "web_fetch", 0.90, entities

        # 5. Memory Query
        if re.search(r"\b(remember|recall|what\s+is\s+my|who\s+is\s+my|where\s+do\s+i)\b", text):
            return "memory_query", 0.90, entities

        # 6. Chit Chat
        if re.search(r"\b(hello|hi|hey|how\s+are\s+you|what's\s+up|thank\s+you|thanks)\b", text):
            return "chit_chat", 0.95, entities

        # 7. Clarify: very short utterance
        if len(text.split()) <= 1 and text:
            return "clarify", 0.40, entities

        return "unknown", 0.20, entities

    def route(
        self,
        transcript: str,
        any_active_rule_fired: bool = False,
        vad_speech_ms: int = 1000,
        intent_conf: float | None = None,
    ) -> RouteDecision:
        t0 = time.perf_counter()

        intent, auto_conf, entities = self.classify_intent(transcript)
        conf = intent_conf if intent_conf is not None else auto_conf

        # Decision logic per Spec 06 §1 & §2
        if any_active_rule_fired:
            action: Literal["RULE", "LLM", "CLARIFY"] = "RULE"
            probs = {"RULE": 0.90, "LLM": 0.05, "CLARIFY": 0.05}
        elif vad_speech_ms < 400 or (conf < 0.35 and not any_active_rule_fired):
            action = "CLARIFY"
            probs = {"CLARIFY": 0.90, "LLM": 0.05, "RULE": 0.05}
        else:
            action = "LLM"
            probs = {"LLM": 0.90, "RULE": 0.05, "CLARIFY": 0.05}

        elapsed_us = int((time.perf_counter() - t0) * 1_000_000)

        route_action = RouteAction(action)
        decision = RouteDecision(
            action=route_action,
            probabilities=probs,
            prediction_set=[route_action],
            calibrated=False,
            elapsed_us=elapsed_us,
        )

        if self.log_path:
            self._log_decision(transcript, decision, intent, conf)

        return decision

    def _log_decision(
        self,
        transcript: str,
        decision: RouteDecision,
        intent: str,
        intent_conf: float,
    ) -> None:
        if not self.log_path:
            return
        record = {
            "decision_id": f"dec-{uuid.uuid4().hex[:12]}",
            "ts": time.time(),
            "transcript": transcript,
            "intent": intent,
            "intent_conf": intent_conf,
            "action": decision.action,
            "probabilities": decision.probabilities,
            "elapsed_us": decision.elapsed_us,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
