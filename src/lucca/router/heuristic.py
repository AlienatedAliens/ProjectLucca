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

logger = structlog.get_logger(__name__)

SEMANTIC_INTENT_ANCHORS: Final[dict[str, tuple[str, ...]]] = {
    "web_fetch": (
        "why don't you look for alternative sources",
        "can you look up more information on her for me",
        "search other records and news articles",
        "could you search online for this topic",
        "find more details and information on the web",
        "check other websites and sources for me",
        "look into different places or databases",
        "search the web for news articles about this",
        "look up details online",
        "try alternative sources",
        "dig deeper into the sources",
    ),
    "context_query": (
        "which websites have you searched",
        "what sites did you check",
        "what sources did you look at",
        "what tools did you just execute",
        "what did you say earlier",
        "what did we just talk about",
        "where did you look",
    ),
    "chit_chat": (
        "hello how are you doing today",
        "good morning lucca",
        "thanks so much for your help",
        "nice talking with you",
        "what's going on",
    ),
    "memory_query": (
        "do you remember what my favorite thing is",
        "what is my address or where do i live",
        "do you recall what i told you last week",
        "what did i tell you earlier",
    ),
    "science_research": (
        "what is the mechanism of action of",
        "explain the chemical reaction between",
        "how does photosynthesis work",
        "what causes this biological phenomenon",
        "describe the physics of",
        "how does benzene resist electrophilic addition",
        "what is the crystal structure and lattice parameters of",
        "explain the spectroscopic properties and absorption bands of",
    ),
    "math_computation": (
        "calculate the integral of",
        "find the roots of the polynomial",
        "what is the sum of this series",
        "prove that this equation has a solution",
        "how many ways can you arrange",
        "solve the system of linear equations",
        "calculate the eigenvalues and determinant of the matrix",
        "compute the prime factors and greatest common divisor",
        "evaluate the logarithmic or trigonometric expression",
        "find the numerical and algebraic solution to the formula",
    ),
    "logic_constraints": (
        "solve this logic puzzle",
        "given these constraints find the solution",
        "if a implies b and b implies c then",
        "which of these statements is consistent",
        "find the truth assignment satisfying these conditions",
    ),
    "code_generation": (
        "write a function that",
        "debug this python code",
        "implement an algorithm for",
        "what does this code do",
    ),
    "factual_lookup": (
        "who invented",
        "when did",
        "what year was",
        "where was the first",
    ),
    "code_repair": (
        "diagnose and fix the bug in this python file",
        "apply a patch to resolve the failing test",
        "grep the codebase for the error message",
        "inspect the traceback and fix the code",
        "run pytest on the test suite to verify",
        "view lines of this module to find the bug",
        "find the syntax or runtime error in the repository",
        "repair the failing unit test in the package",
        "investigate the issue in the codebase",
        "fix the regression in the repository",
    ),
    "spatial_grid": (
        "transform this arc grid",
        "rotate the 2D grid matrix 90 degrees",
        "flood fill the enclosed shape with color",
        "apply gravity drop to the falling objects",
        "solve this concept arc visual reasoning task",
        "align the shapes to the left bounding box",
        "find the connected components and sort by size",
        "detect repeating patterns in the 2d array",
        "predict the output grid from input demonstration grids",
    ),
}

EMERGENCY_REFLEX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:please|lucca|hey\s+lucca)\s+)?"
    r"(shut\s*down|turn\s*off|exit(?!\s+(?:code|status|number|value))|quit|pause|mute|stop(?:\s+(?:everything|all|listening|doing|it|right\s+now|right\s+here))?|halt)"
    r"(?:\s+(?:everything|all|now|please|immediately|lucca|right\s+now|right\s+here|doing\s+that|listening|audio|yourself|execution|the\s+system|it))?[.!]?$",
    re.IGNORECASE,
)

RECENT_CONTEXT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"what did (?:i|you) (?:just|last) (?:say|tell|ask|do|search|look\s*up|find)|"
    r"repeat (?:that|what)|what was that|"
    r"which (?:sites?|websites?|sources?|urls?|pages?|links?) "
    r"(?:did|have) you (?:search(?:ed)?|check(?:ed)?|look(?:ed)?\s+at|visit(?:ed)?|use[d]?)|"
    r"what (?:sites?|websites?|sources?|urls?|pages?|links?) "
    r"(?:did you|have you) (?:search(?:ed)?|check(?:ed)?|look(?:ed)?\s+at|visit(?:ed)?|use[d]?)|"
    r"where did you (?:search|look|check)"
    r")\b",
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

CONTAINER_WORLD_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"where\s+would\s+[a-z]+\s+look|"
    r"where\s+[a-z]+\s+would\s+look|"
    r"[a-z]+'?s\s+belief|"
    r"where\s+[a-z]+\s+(?:thinks?|believes?)|"
    r"where\s+(?:is|was|did\s+[a-z]+\s+(?:put|move|leave))|"
    r"who\s+(?:moved|took|has|placed)\s+the|"
    r"what\s+is\s+the\s+location\s+of|"
    r"while\s+[a-z]+\s+(?:is|was)\s+(?:away|out|asleep)|"
    r"without\s+[a-z]+\s+(?:seeing|knowing|noticing)|"
    r"[a-z]+\s+(?:thinks?|believes?)\s+(?:remain|are\s+in|is\s+in)|"
    r"container_world|containerworld|"
    r"find\s+the\s+[a-z]+\s+given"
    r")\b",
    re.IGNORECASE,
)

COMBINATORIAL_SMT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"zebra\s+puzzle|"
    r"einstein'?s\s+puzzle|"
    r"satisfy\s+(?:the\s+following\s+)?constraints|"
    r"truth[\s-]teller\s+and\s+liar|"
    r"knights?\s+and\s+knaves?|"
    r"five\s+houses|"
    r"which\s+house|"
    r"logic\s+grid|"
    r"z3|"
    r"smt\s+solver"
    r")\b",
    re.IGNORECASE,
)

SOFT_LOGIC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"which\s+(?:statement|conclusion|hypothesis)\s+is\s+(?:true|false|correct|most\s+likely)|"
    r"based\s+on\s+the\s+(?:story|context|passage)|"
    r"deduce\s+whether|"
    r"logically\s+follows|"
    r"murder\s+mystery|"
    r"who\s+committed\s+the\s+crime"
    r")\b",
    re.IGNORECASE,
)

MATHEMATICAL_SYMPY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"solve (?:the )?(?:system|equation|inequality|integral|derivative|polynomial)|"
    r"calculate|compute|find the sum|find the product|find the value of|"
    r"how many (?:ways|integers|solutions|combinations|permutations)|"
    r"find the number of (?:ways|integers|solutions|residents|items)|"
    r"roots? of|eigenvalues?|determinant|"
    r"prime factors?|gcd|lcm|modulo|"
    r"aime|competition math|olympiad math|"
    r"evaluate (?:the )?(?:expression|limit|series)|"
    r"sum of the squares|unique mode|median of the list|"
    r"sympy"
    r")\b|"
    r"(?:\\boxed|\\log_|\\sum_|\\int_|\\frac|\\binom|\b[0-9]+\s*[\+\-\*\/\^]\s*[0-9]+)",
    re.IGNORECASE,
)

SPATIAL_GRID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"arc(?:-agi)?|"
    r"concept\s*arc|"
    r"grid\s*transformation|"
    r"flood\s*fill|"
    r"gravity\s*drop|"
    r"rotate\s*(?:the\s*)?grid|"
    r"crop\s*grid|"
    r"bounding\s*box|"
    r"connected\s*components|"
    r"2d\s*(?:grid|array)|"
    r"demonstration\s*grids?|"
    r"input\s*grid|output\s*grid"
    r")\b",
    re.IGNORECASE,
)

CODE_REPAIR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"swe[-_]?bench|"
    r"pytest|"
    r"apply\s*patch|"
    r"run\s*pytest|"
    r"grep\s*tree|"
    r"view\s*slice|"
    r"failing\s*(?:unit\s*)?test|"
    r"diagnose\s*and\s*fix|"
    r"fix\s*(?:the\s*)?regression|"
    r"reproduce\s*(?:the\s*)?issue|"
    r"failing\s*test\s*suite"
    r")\b",
    re.IGNORECASE,
)

WEB_SEARCH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"search\s*(?:the\s*)?web|"
    r"web\s*search|"
    r"look\s*(?:up\s+)?online|"
    r"google\s*search|"
    r"latest\s*news|"
    r"current\s*events|"
    r"searxng|"
    r"check\s+(?:other\s+)?(?:web)?sites|"
    r"check\s+online|"
    r"sources\s+online"
    r")\b",
    re.IGNORECASE,
)


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
        self.last_decision_record: DecisionRecord | None = None
        self.db_write_failures: int = 0
        self.embed_worker = embed_worker
        self._anchor_embeddings: dict[str, list[list[float]]] | None = None
        self._anchor_matrix: np.ndarray | None = None
        self._anchor_labels: list[str] | None = None
        if retention_files is not None:
            self.retention_files = retention_files
        else:
            try:
                self.retention_files = get_config().log.decision_retention_files
            except Exception as exc:  # noqa: BLE001
                logger.debug("decision_retention_config_load_failed", error=str(exc))
                self.retention_files = 14
        self._load_intents_config(config_path)

    def _get_anchor_embeddings(self) -> dict[str, list[list[float]]]:
        if self._anchor_embeddings is not None and self._anchor_matrix is not None:
            return self._anchor_embeddings
        if self.embed_worker is None:
            return {}
        if hasattr(self.embed_worker, "compiled") and self.embed_worker.compiled is None:
            return {}
        res: dict[str, list[list[float]]] = {}
        all_vecs: list[list[float]] = []
        all_labels: list[str] = []
        for intent, phrases in SEMANTIC_INTENT_ANCHORS.items():
            vecs, _, _ = self.embed_worker.embed_text(list(phrases))
            res[intent] = vecs
            for v in vecs:
                all_vecs.append(v)
                all_labels.append(intent)
        self._anchor_embeddings = res
        if all_vecs:
            self._anchor_matrix = np.array(all_vecs, dtype=np.float32)
            self._anchor_labels = all_labels
        return res

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

    def classify_intent(
        self,
        transcript: str,
        last_tool: str | None = None,
    ) -> tuple[str, float, dict[str, list[str]]]:
        """
        Classifies intent and extracts entities using word-boundary regexes per Spec 06 §2.
        Returns (intent, confidence, entities).
        ``last_tool`` is the most-recently-executed tool name for the current session;
        it is used to promote short corrections issued mid-search to ``web_fetch`` intent.
        """
        norm_transcript = normalize_transcript(transcript)
        text = norm_transcript.strip().lower()
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
        for q in QUOTED_PATTERN.findall(norm_transcript):
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

        # 3b. Conversational Context Query (WO-17 Phase 6)
        if RECENT_CONTEXT_PATTERN.search(text):
            return "context_query", 0.95, entities

        # 4. Memory Query
        mem_pattern = (
            r"\b(remember|recall|what\s+is\s+my|who\s+is\s+my|where\s+do\s+i|do\s+you\s+remember)\b"
        )
        if re.search(mem_pattern, text):
            return "memory_query", 0.90, entities

        # 5. Chit Chat & Persona / Companion Inquiries
        chit_pattern = (
            r"\b(hello|hi|hey|how\s+are\s+you|what's\s+up|thank\s+you|thanks|"
            r"good\s+morning|good\s+afternoon|good\s+night|"
            r"who\s+are\s+you|what\s+are\s+you|tell\s+me\s+about\s+yourself|"
            r"(?:what|can\s+you\s+tell\s+me\s+anything)\s+about\s+yourself|"
            r"what\s+can\s+you\s+tell\s+me\s+about\s+yourself|"
            r"what\s+can\s+you\s+do|your\s+name|introduce\s+yourself|"
            r"test(?:ing)?\s+you|how\s+about\s+we\s+try\s+testing\s+you)\b"
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
            r"when\s+(?:was|is)|how\s+about\s+(?:the|a|an)\b|"
            # Meta-search directives — user redirecting an ongoing web-search turn
            r"try\s+(?:alternative|other|different|more|another)\s+"
            r"(?:source|sources|website|websites|site|sites|approach|approaches)|"
            r"look\s+(?:elsewhere|further|deeper|more|harder)|"
            r"dig\s+(?:deeper|further|more)|"
            r"search\s+(?:again|more|harder|further)|"
            r"find\s+(?:more|other|different)\s+(?:sources?|results?|information|info)|"
            r"check\s+(?:other|more|different)\s+(?:sources?|sites?|websites?|places?)|"
            r"look\s+for\s+(?:more|other|alternative|different)\s+(?:sources?|info|information)"
            r")\b"
        )
        if re.search(web_pattern, text) or entities["url"]:
            return "web_fetch", 0.90, entities

        # 7. Clarify: very short utterance — but promote to web_fetch if mid-search-session.
        # A bare name correction or a single follow-up word while last_tool was a web tool
        # is almost certainly a search refinement, not an ambiguous mumble.
        _WEB_TOOLS: frozenset[str] = frozenset({"search_web", "fetch_url", "web_fetch"})
        if last_tool in _WEB_TOOLS and len(text.split()) <= 6 and text:
            return "web_fetch", 0.75, entities
        if len(text.split()) <= 1 and text:
            return "clarify", 0.40, entities

        # 8. Semantic Embedding Classification (Vectorized Anchor Dot-Product)
        # Evaluates cosine similarity against intent anchors when regex yields unknown
        anchors = self._get_anchor_embeddings()
        if (
            anchors
            and self._anchor_matrix is not None
            and self._anchor_labels
            and self.embed_worker is not None
        ):
            try:
                q_vecs, _, _ = self.embed_worker.embed_text([text])
                if q_vecs and any(abs(v) > 1e-6 for v in q_vecs[0]):
                    qv = np.array(q_vecs[0], dtype=np.float32)
                    sims = np.dot(self._anchor_matrix, qv)
                    best_idx = int(np.argmax(sims))
                    best_sim = float(sims[best_idx])
                    best_intent = self._anchor_labels[best_idx]
                    if best_intent and best_sim >= 0.28:
                        return best_intent, float(min(best_sim, 0.95)), entities
            except Exception as exc:  # noqa: BLE001
                logger.debug("semantic_intent_classification_failed", error=str(exc))

        return "unknown", 0.20, entities

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

        intent, auto_conf, entities = self.classify_intent(transcript_text, last_tool=last_tool)
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
            if EMERGENCY_REFLEX_PATTERN.search(text_lower):
                tier = ExecutionTier.REFLEX
            else:
                tier = ExecutionTier.ACT_THEN_NARRATE
        else:
            tier = ExecutionTier.FULL_LOOP

        # Dynamic Tiered Neurosymbolic Reasoning & Thinking Mode Dispatch
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

        if action_lit == "LLM":
            regex_cw = bool(CONTAINER_WORLD_PATTERN.search(text_lower))
            regex_spatial = bool(SPATIAL_GRID_PATTERN.search(text_lower))
            regex_code = bool(CODE_REPAIR_PATTERN.search(text_lower))
            regex_z3 = bool(COMBINATORIAL_SMT_PATTERN.search(text_lower))
            regex_sympy = bool(MATHEMATICAL_SYMPY_PATTERN.search(text_lower))
            regex_soft = bool(SOFT_LOGIC_PATTERN.search(text_lower))
            regex_web = bool(WEB_SEARCH_PATTERN.search(text_lower))

            has_cw = regex_cw
            has_spatial_grid = regex_spatial or (intent == "spatial_grid")
            has_code_repair = regex_code or (intent == "code_repair")
            has_z3 = regex_z3 or (intent == "logic_constraints")
            has_soft = regex_soft
            has_sympy = regex_sympy or (intent == "math_computation")
            has_science = (intent == "science_research") or any(
                k in text_lower
                for k in (
                    "mechanism",
                    "chemical reaction",
                    "photosynthesis",
                    "spectroscopy",
                    "lattice",
                    "biochemical",
                    "electrophilic",
                    "orbital",
                    "quantum state",
                    "half-life",
                )
            )
            has_web_search = regex_web or (intent in ("web_fetch", "factual_lookup"))

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

            if has_cw:
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
            elif regex_z3 and not regex_sympy:
                reasoning_domain = "combinatorial_smt"
                solver_tool = "z3_smt"
                thinking_mode = "direct"
            elif regex_sympy and not regex_z3:
                reasoning_domain = "mathematics"
                solver_tool = "sympy_sandbox"
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
                    thinking_mode = "direct"  # Avoid 36.7% overthinking collapse on 12B
                else:
                    thinking_mode = "thinking"  # Capture 23% -> 63% thinking lift on edge tiers
            elif has_science:
                reasoning_domain = "science_research"
                solver_tool = "research_topic"
                thinking_mode = "thinking"
            elif has_web_search:
                reasoning_domain = "web_search"
                solver_tool = "search_web"
                thinking_mode = "thinking"

        route_action = RouteAction(action_lit)

        # D-DUAL-01: Deliberation lane detection.
        # A turn is routed to the deliberation lane (multi-second budget, floor-hold TTS cue)
        # when it is a hard reasoning problem: math/SMT/spatial/soft_logic/science + (>= 15 words or multi-lobe).
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
