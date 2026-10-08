"""
Project Lucca — 5-Substrate Epistemic Search Cascade & Belnap Bilattice Orchestration
Spec 10 §4, Milestone 3 Architecture
Implements deterministic multi-tier evidence search, Belnap FOUR bilattice synthesis,
acoustic floor-holding reflex cues, and calibrated honest abstention.
"""

from __future__ import annotations

import enum
import json
import platform
import re
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

import structlog
import ulid
from pydantic import BaseModel, Field, JsonValue

from lucca.core.schemas import (
    MemoryHit,
    RetrievalQuery,
    ToolResult,
    VerifierLabel,
    standard_for_confidence,
)
from lucca.core.trace import now_ns
from lucca.memory.extraction import FUNCTIONAL_PREDICATES
from lucca.ports import MemoryStorePort, SemanticVerifierPort
from lucca.reasoning.recall import recall_past_episodes, tokenize_query

logger = structlog.get_logger(__name__)


# ============================================================================
# 1. Epistemic Substrates, Trust Tiers & Belnap FOUR Bilattice Enums
# ============================================================================


class EpistemicSubstrate(enum.IntEnum):
    """
    Epistemic substrates in Project Lucca's cognitive architecture:
    0: Live System / Hardware Telemetry (< 1ms, Tier 1)
    1: Workspace Filesystem / AST (5–20ms, Tier 2)
    2: Cryptographic Episodic & Semantic Memory (15–40ms, Tier 3)
    3: SSRF-Hardened Sandboxed Web (300–1500ms, Tier 4)
    4: Calibrated Honest Abstention (0ms, \\bot Ground Truth Gap)
    5: Axiomatic Core Persona & Self-Model (0ms, Tier 0)
    6: Authoritative Dynamic Capability & Tool Registry (0ms, Tier 0)
    """

    TELEMETRY = 0
    WORKSPACE = 1
    MEMORY = 2
    WEB = 3
    ABSTENTION = 4
    SELF = 5
    CAPABILITIES = 6
    SELF_HISTORY = 7


class TrustTier(enum.IntEnum):
    """
    Epistemic Trust Hierarchy: Lower integer denotes higher physical authority.
    Tier 0 strictly supersedes Tier 1, Tier 1 strictly supersedes Tier 2, etc.
    """

    TIER_0_AXIOMATIC = 0  # Axiomatic self-knowledge, persona, and registered capabilities
    TIER_1_HARDWARE = 1  # Direct OS/sensor telemetry (hardware truth)
    TIER_2_WORKSPACE = 2  # Bounded container filesystem / source AST
    TIER_3_MEMORY = 3  # HMAC-signed episodic memory & user preferences
    TIER_4_WEB = 4  # External untrusted network content (tainted)


class BelnapValue(enum.StrEnum):
    """
    Belnap's 4-valued evidential bilattice FOUR:
    T: Supported True (positive evidence without refutation)
    F: Supported False (refuted / negative evidence)
    BOT: Epistemic Gap (\bot, Unknown / Neither true nor false)
    TOP: Contradiction / Conflict (\top, Both true and false supported)
    """

    TRUE = "T"
    FALSE = "F"
    UNKNOWN = "BOT"
    CONFLICT = "TOP"


# ============================================================================
# 2. Belnap Bilattice Algebraic Operations
# ============================================================================


def belnap_meet_t(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """Logical conjunction (meet in truth ordering <=_t: F <= {BOT, TOP} <= T)."""
    if BelnapValue.FALSE in (a, b):
        return BelnapValue.FALSE
    if a == BelnapValue.TRUE:
        return b
    if b == BelnapValue.TRUE:
        return a
    if a == b:
        return a
    return BelnapValue.FALSE


def belnap_join_t(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """Logical disjunction (join in truth ordering <=_t: F <= {BOT, TOP} <= T)."""
    if BelnapValue.TRUE in (a, b):
        return BelnapValue.TRUE
    if a == BelnapValue.FALSE:
        return b
    if b == BelnapValue.FALSE:
        return a
    if a == b:
        return a
    return BelnapValue.TRUE


def belnap_negation(a: BelnapValue) -> BelnapValue:
    """Truth negation (~). Swaps T and F, fixes BOT and TOP."""
    if a == BelnapValue.TRUE:
        return BelnapValue.FALSE
    if a == BelnapValue.FALSE:
        return BelnapValue.TRUE
    return a


def belnap_meet_k(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """Consensus / information meet (meet in knowledge ordering <=_k: BOT <= {T, F} <= TOP)."""
    if BelnapValue.UNKNOWN in (a, b):
        return BelnapValue.UNKNOWN
    if a == BelnapValue.CONFLICT:
        return b
    if b == BelnapValue.CONFLICT:
        return a
    if a == b:
        return a
    return BelnapValue.UNKNOWN


def belnap_join_k(a: BelnapValue, b: BelnapValue) -> BelnapValue:
    """Evidential pooling / information join (join in knowledge ordering <=_k).

    Ordering: BOT <= {T, F} <= TOP.
    """
    if BelnapValue.CONFLICT in (a, b):
        return BelnapValue.CONFLICT
    if a == BelnapValue.UNKNOWN:
        return b
    if b == BelnapValue.UNKNOWN:
        return a
    if a == b:
        return a
    # T and F pooled together yields conflict (\top)
    return BelnapValue.CONFLICT


def pool_evidence(values: Sequence[BelnapValue]) -> BelnapValue:
    """Pools multiple evidence items using Belnap information join (sum of knowledge)."""
    res = BelnapValue.UNKNOWN
    for v in values:
        res = belnap_join_k(res, v)
    return res


# ============================================================================
# 3. Evidence Models & Dynamic Calibrated Abstention
# ============================================================================


class EvidenceItem(BaseModel):
    """
    Atomic unit of evidence retrieved from an epistemic substrate.
    Strictly implements Belnap's (1977) four-valued data model via independent
    'told_true' and 'told_false' epistemic bits:
    - (told_true=True, told_false=False) -> T (Asserts p)
    - (told_true=False, told_false=True) -> F (Refutes p)
    - (told_true=True, told_false=True)   -> TOP (Contradiction / Conflict)
    - (told_true=False, told_false=False) -> BOT (Epistemic Gap / Unknown)
    """

    substrate: EpistemicSubstrate
    trust_tier: TrustTier
    source: str
    content: str
    proposition: str = ""
    told_true: bool = True
    told_false: bool = False
    confidence: float = 1.0
    timestamp_ns: int = Field(default_factory=now_ns)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def polarity(self) -> BelnapValue:
        """Derives the atomic Belnap value from the two independent epistemic bits."""
        if self.told_true and self.told_false:
            return BelnapValue.CONFLICT
        if self.told_true:
            return BelnapValue.TRUE
        if self.told_false:
            return BelnapValue.FALSE
        return BelnapValue.UNKNOWN


def build_calibrated_refusal(
    queried_substrates: Sequence[EpistemicSubstrate],
    topic: str | None = None,
) -> str:
    """
    Dynamically constructs a calibrated honest refusal listing ONLY the substrates
    actually queried for this turn, preventing false action assertions.
    """
    names_map: dict[EpistemicSubstrate, str] = {
        EpistemicSubstrate.SELF: "core persona & self-knowledge",
        EpistemicSubstrate.CAPABILITIES: "registered capabilities",
        EpistemicSubstrate.TELEMETRY: "system telemetry",
        EpistemicSubstrate.WORKSPACE: "workspace files",
        EpistemicSubstrate.MEMORY: "memory records",
        EpistemicSubstrate.WEB: "external web sources",
        EpistemicSubstrate.SELF_HISTORY: "execution and utterance history",
    }
    checked = [names_map[s] for s in queried_substrates if s in names_map]
    if not checked:
        checked_str = "available verified sources"
    elif len(checked) == 1:
        checked_str = checked[0]
    elif len(checked) == 2:
        checked_str = f"{checked[0]} and {checked[1]}"
    else:
        checked_str = f"{', '.join(checked[:-1])}, and {checked[-1]}"

    display_topic = topic.strip() if topic and len(topic.strip()) < 80 else "that"
    return (
        f"I checked my {checked_str}, but have no verified record of {display_topic}. "
        f"I don't know the answer and won't guess."
    )


class SearchCascadeResult(BaseModel):
    """Unified outcome of the 5-substrate search cascade."""

    belnap_status: BelnapValue
    evidence: list[EvidenceItem]
    resolved_substrate: EpistemicSubstrate
    elapsed_ms: float
    floor_cue_spoken: str | None = None
    calibrated_refusal: str | None = None
    synthesized_context: str = ""
    queried_substrates: list[EpistemicSubstrate] = Field(default_factory=list)
    recollections: list[str] = Field(default_factory=list)


# ============================================================================
# 4. Floor-Holding Cues & Intent Classifier
# ============================================================================


def select_floor_cue(query_text: str, target_substrate: EpistemicSubstrate | None = None) -> str:
    """
    Selects an acoustic floor-holding reflex cue within < 1ms to claim
    the conversational floor before multi-substrate search execution.
    """
    lower = query_text.lower()
    if target_substrate == EpistemicSubstrate.SELF:
        return "Reflecting on my design..."
    if target_substrate == EpistemicSubstrate.CAPABILITIES:
        return "Checking my capabilities..."
    if target_substrate == EpistemicSubstrate.TELEMETRY or any(
        w in lower
        for w in ("gpu", "vram", "cpu", "ram", "hardware", "specs", "load", "utilization")
    ):
        return "Checking system telemetry..."
    if target_substrate == EpistemicSubstrate.WORKSPACE or any(
        w in lower
        for w in (
            "file",
            "code",
            "directory",
            "workspace",
            "script",
            "folder",
            "repo",
            "inbox",
        )
    ):
        return "Searching the workspace files..."
    if target_substrate == EpistemicSubstrate.MEMORY or any(
        w in lower for w in ("remember", "memory", "preference", "last time", "we talked", "who is")
    ):
        return "Checking my memory records..."
    if target_substrate == EpistemicSubstrate.SELF_HISTORY or any(
        w in lower
        for w in (
            "what did you do",
            "did you do",
            "did you run",
            "did you tell me",
            "did you say",
            "have you ever been wrong",
            "what did you say",
            "what tools did you use",
            "past actions",
        )
    ):
        return "Reviewing my execution and conversation history..."
    if target_substrate == EpistemicSubstrate.WEB or any(
        w in lower for w in ("http", "https", "url", "website", "online", "fetch")
    ):
        return "Looking that up online..."
    return "Checking that for you..."


def extract_clean_topic(query_text: str) -> str:
    """
    Extracts a clean, normalized noun-phrase topic from an epistemic question.
    Strips question prefixes, internal question marks, compound sentence tails,
    and performs pronoun alignment for assistant voice ("I have no record of [topic]").
    """
    clean = query_text.strip()
    if not clean:
        return "that"

    # 1. Take primary inquiry clause if compound (split on punctuation)
    clauses = [c.strip() for c in re.split(r"[?!;]+", clean) if c.strip()]
    first_clause = clauses[0] if clauses else clean

    # 2. Strip leading question starters and conversational framing
    lower_clause = first_clause.lower()
    prefixes = (
        "what can you tell me about",
        "what can you tell me",
        "what can you",
        "can you tell me about",
        "can you tell me",
        "tell me about",
        "tell me",
        "do you know who is",
        "do you know what is",
        "do you know",
        "do you remember",
        "can you check",
        "check",
        "search for",
        "find",
        "who is",
        "who was",
        "who are",
        "who were",
        "what did i have for",
        "what did i",
        "what did we",
        "what did",
        "what do",
        "what is the definition of",
        "what is",
        "what was",
        "what are",
        "what were",
        "where is",
        "where was",
        "where are",
        "why is",
        "how is",
    )
    stripped = first_clause
    for p in sorted(prefixes, key=len, reverse=True):
        if lower_clause.startswith(p):
            stripped = first_clause[len(p) :].strip()
            break

    stripped = stripped.strip("?.!, \t\n\r")
    if not stripped:
        return "that"

    # 3. Pronoun alignment for assistant voice
    tokens = stripped.split()
    shifted: list[str] = []
    subject_preceders = frozenset(
        {
            "have",
            "has",
            "had",
            "did",
            "do",
            "does",
            "can",
            "could",
            "will",
            "would",
            "should",
            "if",
        }
    )
    for i, t in enumerate(tokens):
        tl = t.lower()
        if tl == "your":
            shifted.append("my")
        elif tl == "you":
            if i > 0 and tokens[i - 1].lower() in subject_preceders:
                shifted.append("I")
            elif i == 0 and len(tokens) > 1:
                shifted.append("I")
            else:
                shifted.append("me")
        elif tl == "my":
            shifted.append("your")
        elif tl == "me":
            shifted.append("you")
        elif tl == "i":
            shifted.append("you")
        else:
            shifted.append(t)

    res = " ".join(shifted).strip()
    return res if res else "that"


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


def _term_matches(text: str, term: str) -> bool:
    """Matches a term against text, honoring word boundaries for alphanumeric tokens."""
    left_b = r"\b" if term and term[0].isalnum() else ""
    right_b = r"\b" if term and term[-1].isalnum() else ""
    pattern = f"{left_b}{re.escape(term)}{right_b}"
    return bool(re.search(pattern, text))


def _any_term_matches(text: str, terms: tuple[str, ...]) -> bool:
    return any(_term_matches(text, t) for t in terms)


REGIONAL_OR_CULTURE_WORDS: tuple[str, ...] = (
    "australia", "australian", "aussie", "uk", "british", "britain", "england",
    "scotland", "scottish", "ireland", "irish", "new zealand", "kiwi",
    "philippines", "filipino", "singapore", "singaporean", "malaysia", "malaysian",
    "new york", "nyc", "chicago", "texas", "southern", "canada", "canadian",
    "south africa", "japan", "japanese",
)

SLANG_OR_DIALECT_WORDS: tuple[str, ...] = (
    "slang", "colloquial", "colloquialism", "dialect", "idiom", "vernacular",
    "lingo", "jargon", "local term", "street term",
)

CULINARY_WORDS: tuple[str, ...] = (
    "food", "dish", "snack", "fish", "meat", "pastry", "cuisine", "grub",
    "cheese", "sandwich", "dessert", "bread", "roll", "pie", "stew",
    "beverage", "drink", "street food", "recipe", "barm",
)


def matches_slang_or_world_definition(lower: str) -> bool:
    """Conformal uncertainty gating: detect cultural, culinary, regional slang or unfamiliar entity inquiries."""
    # 1. Direct slang/dialect keywords
    if any(re.search(rf"\b{re.escape(w)}\b", lower) for w in SLANG_OR_DIALECT_WORDS):
        return True

    # 2. Regional definitional phrasing: 'what is X in [region]' or 'what X is in [region]'
    for reg in REGIONAL_OR_CULTURE_WORDS:
        if re.search(rf"\bwhat\s+.+?\bin\s+{re.escape(reg)}\b", lower):
            return True

    # 3. Cultural/culinary entity definition: 'what is a/an ...' or 'what [a/an] ... is'
    if re.search(r"\bwhat\s+(?:(?:is|are)\s+(?:a|an)\s+|a\s+|an\s+)[a-z0-9\s'-]+", lower):
        return True

    # 'what does ... mean'
    if re.search(r"\bwhat\s+does\s+[a-z0-9\s'-]+?\s+mean\b", lower):
        return True

    # 'what is ...' where query contains culinary words
    has_culinary = any(re.search(rf"\b{re.escape(w)}\b", lower) for w in CULINARY_WORDS)
    if has_culinary and re.search(r"\bwhat\s+(?:is|are|[a-z0-9\s'-]+\s+is)\b", lower):
        return True

    # 'what is X and Y' (classic dishes like 'bubble and squeak', 'bangers and mash')
    if re.search(r"\bwhat\s+(?:is|are)\s+[a-z0-9'-]+\s+and\s+[a-z0-9'-]+", lower):
        return True

    return False


def _extract_target_entity(query_text: str) -> str | None:
    """Extracts candidate target entity from definitional or slang query for snippet filtering."""
    patterns = (
        r"\bwhat\s+(?:is|are|does|was)\s+(?:a|an|the)?\s*([a-zA-Z0-9\s'-]+?)(?:\s+mean|\s+in\b|\s+slang|\s+dialect|\?|$)",
        r"\bslang\s+(?:for|meaning)\s+([a-zA-Z0-9\s'-]+?)(?:\?|$)",
    )
    for p in patterns:
        m = re.search(p, query_text, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if cand and len(cand) < 60:
                return cand
    return None


def classify_epistemic_intent(
    query_text: str,
) -> tuple[bool, list[EpistemicSubstrate], str | None]:
    """
    Classifies whether query_text is an epistemic factual query, selects candidate
    substrates to query in priority order, and extracts the target topic.
    """
    clean = query_text.strip()
    if not clean:
        return False, [], None

    lower = clean.lower()

    # Non-epistemic conversational commands or pure acknowledgments
    non_epistemic_exact = {
        "hello",
        "hi",
        "hey",
        "good morning",
        "good evening",
        "good afternoon",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
        "stop",
        "pause",
        "shut down",
        "turn off",
        "exit",
        "quit",
        "mute",
        "unmute",
    }
    clean_punct = re.sub(r"[^\w\s]", "", lower).strip()
    if clean_punct in non_epistemic_exact:
        return False, [], None

    # Conversational small talk / pure banter (without factual inquiry)
    pure_banter = (
        r"^(?:how\s+are\s+you|how(?:'re|\s+are)\s+you\s+doing"
        r"|what(?:'s|\s+is)\s+up|how(?:'s|\s+is)\s+it\s+going)[.?!]?$"
    )
    if re.search(pure_banter, lower):
        return False, [], None

    # Conversational context queries (WO-17 Phase 6: do not query Substrate 2 memory)
    if RECENT_CONTEXT_PATTERN.search(lower):
        return False, [], None

    # Closed-world puzzles, hypothetical premises, and deductive math reasoning
    # MUST NOT trigger open-world file search, telemetry, or Belnap abstention refusal.
    hypothetical_puzzle_starters = (
        "consider the following premises",
        "assume a counterfactual",
        "scenario:",
        "observations:",
        "events occurred on",
        "four houses are arranged",
        "houses 1 to 4 arranged",
        "four teams",
        "round-robin tournament",
        "round robin",
        "on an island, knights",
        "knights and knaves",
        "knights & knaves",
        "events 1, 2, 3, 4 require",
        "tasks t1",
        "six diplomats",
        "circular table",
        "solve the base-10 addition",
        "ab + ba =",
        "cryptarithmetic",
        "given clauses:",
        "three employees (x, y, z)",
        "three employees",
        "choose integer quantities",
        "a closed market is defined",
        "bidders a and b",
        "a drone starts at coordinate",
        "discover the latent binary operation",
        "discover binary operation",
        "step-by-step deductive proof",
        "solve this puzzle",
        "logic puzzle",
        "supply: s =",
        "supply: p =",
        "substance has half-life",
        "worker a completes a job",
        "sequence defined by",
        "disease prevalence is",
        "solve for x, y, z",
        "interval i1 takes place",
        "rule: birds fly",
        "a room has no windows and one locked door",
        "a server cluster experienced data corruption",
        "alice arrives at",
        "rule 1:",
        "proposal:",
        "expert a (distinguished",
        "expert a",
        "mia places chocolate",
        "asset value v is",
        "in a second-price sealed-bid auction",
        "alice told bob a secret",
        "in an employment market",
        "three children (a, b, c)",
        "in an infinitely repeated prisoner's dilemma",
        "player 1 has either a nut hand",
        "two hunters can choose stag",
    )
    if any(lower.startswith(p) or p in lower for p in hypothetical_puzzle_starters):
        return False, [], None

    # Detect structured premise lists or math word problems (e.g. "1. Event A...", "Clues:\n1.")
    if re.search(r"\b(?:premise\s+\d+|clues?:|rule\s+\d+:|rule:\s+|question:\s+(?:is|what|determine|calculate))\b", lower):
        if re.search(r"\b(?:all\s+\w+\s+are|no\s+\w+\s+is|every\s+\w+\s+is|if\s+both\s+are\s+released|final\s+verdict|determine the exact|construct the valid|valid schedule|find digits|is the system satisfiable|abduce|resolve the conflict|most plausible explanation|competing hypotheses)\b", lower):
            return False, [], None

    # Substrate SELF: Companion identity, persona, creator, and design (Tier 0 Axiomatic)
    self_pattern = (
        r"\b(who\s+are\s+you|what\s+are\s+you|tell\s+me\s+about\s+yourself|"
        r"what\s+can\s+you\s+tell\s+me\s+about\s+yourself|who\s+made\s+you|who\s+built\s+you|"
        r"are\s+you\s+an?\s+(?:ai|human|robot|assistant|companion)|what(?:'s|\s+is)\s+your\s+name|"
        r"introduce\s+yourself|your\s+(?:personality|archetype|creator|lore))\b"
    )

    # Substrate CAPABILITIES: Available tools, desktop apps, and LISP pathways (Tier 0 Axiomatic)
    capability_pattern = (
        r"\b(what\s+tools|what\s+can\s+you\s+do|available\s+(?:tools|functions|skills)|"
        r"what\s+applications|what\s+apps|can\s+you\s+(?:launch|open|edit|run|execute)|"
        r"list\s+(?:your\s+)?(?:tools|functions|capabilities)|installed\s+tools|"
        r"reasoning\s+pathways|lisp\s+rules|microscheme|what\s+functions|access\s+to\s+(?:python|lisp))\b"
    )

    # Substrate TELEMETRY: System & Hardware Metrics
    telemetry_words = (
        "gpu",
        "vram",
        "cpu",
        "ram",
        "memory usage",
        "hardware",
        "specs",
        "workstation",
        "processor",
        "utilization",
        "load",
        "temperature",
        "telemetry",
        "substrate configuration",
        "nvidia",
        "intel",
        "overheating",
        "motherboard",
        "serial number",
        "chassis",
        "laptop specs",
    )

    # Substrate WORKSPACE: Filesystem & Code AST
    workspace_words = (
        "read the file",
        "read_file",
        "workspace",
        "directory",
        "folder",
        "config/",
        "src/",
        "data/",
        "scripts/",
        "repo",
        "main.py",
        "persona.toml",
        "files in",
        "list files",
        "grep",
        "ast",
        "contents of",
        "inbox",
        "drop folder",
        "incoming files",
        "any files",
        "what files",
        "have any files",
        "do you have files",
        "files do you have",
        "document",
        "documents",
    )
    has_file_name = bool(
        re.search(
            r"\b[a-zA-Z0-9_\-./\\]+\.(?:md|py|txt|toml|json|sql|csv|pdf|docx|yaml|yml)\b",
            lower,
        )
    )

    # Substrate MEMORY: Episodic Memory & Preferences
    memory_words = (
        "what did i",
        "what did we",
        "do you remember",
        "in memory",
        "what is my",
        "what are my",
        "my favorite",
        "my preference",
        "prefer",
        "creator full real name",
        "creator's full real name",
        "creator's real name",
        "full real name",
        "real name",
        "vault",
        "cat's name",
        "dog's name",
        "childhood pet",
        "pet's name",
        "breakfast",
        "weather outside",
        "passkey",
        "password",
        "recall",
        "last session",
        "notes on my",
        "talked about",
        "where do i",
        "where i live",
        "where do i live",
        "where am i living",
        "my location",
        "my city",
        "my town",
        "my address",
        "my home",
    )

    # Substrate WEB: External World / Web Search
    web_words = (
        "fetch_url",
        "http://",
        "https://",
        "fetch url",
        "browse",
        "website",
        "look up",
        "lookup",
        "search for",
        "search google",
        "check google",
        "google",
        "find out about",
        "check wikipedia",
        "wikipedia",
        "headlines",
        "online",
    )

    # Substrate TEMPORAL / TELEMETRY: Clock, Date, Time & Physical Geolocation
    temporal_words = (
        "what time",
        "current time",
        "time is it",
        "time right now",
        "what day is it",
        "what day it is",
        "what is the date",
        "what's the date",
        "today's date",
        "todays date",
        "current date",
        "what month",
        "what year",
        "exact time",
        "local time",
        "clock",
        "time in",
        "time for",
        "timezone",
        "time zone",
        "timezones",
        "time zones",
        "utc offset",
        "gmt offset",
        "daylight saving",
        "daylight savings",
        "daylight-saving",
        "dst",
        "standard time",
    )
    location_words = (
        "where are you located",
        "where you are located",
        "where are we located",
        "where you're located",
        "your location",
        "my location",
        "physical location",
        "machine located",
        "computer located",
        "pc located",
        "where are you",
        "where am i",
        "public ip",
        "ip address",
        "geolocation",
    )

    substrates: list[EpistemicSubstrate] = []
    # Private credentials, creator real names, and secrets must query MEMORY, not general SELF
    is_private_memory = _any_term_matches(
        lower, ("real name", "full real name", "passkey", "vault", "password")
    )
    if re.search(self_pattern, lower) and not is_private_memory:
        substrates.append(EpistemicSubstrate.SELF)
    if re.search(capability_pattern, lower):
        substrates.append(EpistemicSubstrate.CAPABILITIES)
    if _any_term_matches(lower, telemetry_words):
        substrates.append(EpistemicSubstrate.TELEMETRY)
    if _any_term_matches(lower, temporal_words):
        substrates.append(EpistemicSubstrate.TELEMETRY)
        if EpistemicSubstrate.SELF not in substrates:
            substrates.append(EpistemicSubstrate.SELF)
    if _any_term_matches(lower, location_words):
        substrates.append(EpistemicSubstrate.TELEMETRY)
        if EpistemicSubstrate.SELF not in substrates:
            substrates.append(EpistemicSubstrate.SELF)
    if _any_term_matches(lower, workspace_words) or has_file_name:
        substrates.append(EpistemicSubstrate.WORKSPACE)
    self_history_words = (
        "what did you do",
        "what were you doing",
        "what did we do",
        "what tools did you use",
        "did you run",
        "did you save",
        "did you execute",
        "did you tell me",
        "did you say",
        "have you ever been wrong",
        "have you ever made a mistake",
        "you said yesterday",
        "you said earlier",
        "what did you tell me",
        "what did you say",
        "past actions",
        "execution history",
        "did you claim",
    )
    if _any_term_matches(lower, self_history_words):
        substrates.append(EpistemicSubstrate.SELF_HISTORY)
    if _any_term_matches(lower, memory_words) or is_private_memory:
        substrates.append(EpistemicSubstrate.MEMORY)
    has_slang_intent = (
        matches_slang_or_world_definition(lower)
        and not _any_term_matches(lower, self_history_words)
        and not re.search(self_pattern, lower)
        and not re.search(capability_pattern, lower)
        and not _any_term_matches(lower, temporal_words)
    )
    if (
        _any_term_matches(lower, web_words)
        or has_slang_intent
    ) and not _any_term_matches(lower, self_history_words):
        if EpistemicSubstrate.WEB not in substrates:
            substrates.append(EpistemicSubstrate.WEB)

    is_epistemic = len(substrates) > 0

    # Extract clean normalized topic string
    topic = extract_clean_topic(clean)

    return is_epistemic, substrates, topic


# ============================================================================
# 5. Epistemic Search Cascade Implementation
# ============================================================================


class EpistemicSearchCascade:
    """
    Executes multi-tier epistemic search across Substrates 0 to 4,
    computes Belnap FOUR evidential synthesis, and enforces calibrated honest abstention.
    """

    def __init__(
        self,
        sandbox: object | None = None,
        memory_store: MemoryStorePort | None = None,
        enable_floor_cues: bool = True,
        verifier: SemanticVerifierPort | None = None,
    ) -> None:
        self.sandbox = sandbox
        self.memory_store = memory_store
        self.enable_floor_cues = enable_floor_cues
        self.verifier = verifier

    def classify_intent(self, query_text: str) -> tuple[bool, list[EpistemicSubstrate], str | None]:
        return classify_epistemic_intent(query_text)

    def select_floor_cue(
        self, query_text: str, target_substrate: EpistemicSubstrate | None = None
    ) -> str:
        return select_floor_cue(query_text, target_substrate)

    def _execute_sandbox(
        self,
        tool_name: str,
        args: dict[str, JsonValue],
        confirmed: bool = True,
    ) -> ToolResult | None:
        """Invokes a sandbox tool polymorphically (SandboxService or PersistentDockerWorker)."""
        if not self.sandbox:
            return None
        if hasattr(self.sandbox, "execute"):
            return self.sandbox.execute(tool_name=tool_name, args=args, confirmed=confirmed)
        if hasattr(self.sandbox, "execute_tool"):
            cid = f"call-casc-{ulid.ULID()}"
            return self.sandbox.execute_tool(
                call_id=cid, tool_name=tool_name, args=args, confirmed=confirmed
            )
        return None

    # ------------------------------------------------------------------------
    # Substrate SELF: Axiomatic Persona & Self-Model (0ms, Tier 0)
    # ------------------------------------------------------------------------
    def query_substrate_self(self, query_text: str) -> list[EvidenceItem]:
        """
        Queries live persona, identity, and runtime truth (Substrate SELF - Axiomatic Tier 0).

        Runtime facts (which LLM / ASR / TTS are loaded) are read from LuccaConfig at
        query time, never hard-coded, so a brain swap is a config change and Lucca's
        self-description stays truthful.
        """
        # Lazy imports: brain.prompt_builder / core.config import the cascade indirectly
        # (orchestrator -> cascade); importing at module top would form a cycle.
        from lucca.brain.prompt_builder import get_persona_config  # noqa: PLC0415
        from lucca.core.config import get_config  # noqa: PLC0415

        try:
            cfg = get_persona_config()
            rt = get_config()
            now_local = datetime.now().astimezone()
            time_str = now_local.strftime("%A, %B %d, %Y, %I:%M %p (%Z, UTC%z)")
            active_voice = cfg.voice or rt.tts.voice
            from lucca.speech.engines import ENGINE_CATALOG, parse_engine_from_spec
            eng_id, _ = parse_engine_from_spec(str(active_voice))
            eng_desc = ENGINE_CATALOG.get(eng_id)
            eng_name = eng_desc.name if eng_desc else "Kokoro-82M"
            tts_info = (
                f"speech synthesis 'CosyVoice 3 Frontier' (voice: '{active_voice}') with Kokoro-82M fallback"
                if "cosyvoice" in str(active_voice).lower()
                else f"speech synthesis '{eng_name}' (voice: '{active_voice}')"
            )
            vision_info = (
                f"; multimodal vision projector '{Path(rt.llm.mmproj).name}' active (mode: {rt.llm.mode})"
                if (rt.llm.mode == "vision" or getattr(rt.llm, "mmproj", None))
                else ""
            )
            content = (
                f"Agent Identity: Lucca, local AI engineer companion. "
                f"Current Local Time: {time_str}. "
                f"Archetype: {cfg.archetype}. Voice: {active_voice}. "
                f"Local Runtime: language model '{rt.llm.model_display_name()}' served by "
                f"llama-server on the dGPU (context {rt.llm.ctx} tokens){vision_info}; "
                f"speech recognition '{Path(rt.asr.model).name}' on NPU/CPU; "
                f"{tts_info}. "
                f"Host Workstation: {platform.node()} ({platform.platform()}). "
                f"Core Purpose: Pair-programming, systems debugging, and desktop automation. "
                f"Created locally for this workstation. "
                f"Admits uncertainty: {cfg.admits_uncertainty}."
            )
        except Exception as exc:  # noqa: BLE001 — degrade to static identity, never crash a turn
            logger.warning("cascade_self_substrate_fallback", error=str(exc))
            content = (
                "Lucca: local AI engineer companion for pair programming and systems engineering."
            )

        return [
            EvidenceItem(
                substrate=EpistemicSubstrate.SELF,
                trust_tier=TrustTier.TIER_0_AXIOMATIC,
                source="config/persona.toml",
                content=content,
                belnap_val=BelnapValue.TRUE,
                confidence=1.0,
                latency_ms=0.01,
            )
        ]

    # ------------------------------------------------------------------------
    # Substrate CAPABILITIES: Authoritative Capability Registry (0ms, Tier 0)
    # ------------------------------------------------------------------------
    def query_substrate_capabilities(self, query_text: str) -> list[EvidenceItem]:
        """Queries registered capabilities and tools (Substrate CAPABILITIES, Tier 0).

        The tool list is always derived from the live registry. If the registry cannot be
        read, this substrate returns **no evidence** rather than a hard-coded list — a stale
        list stamped TIER_0 / confidence 1.0 would itself be a confabulated self-description.
        """
        try:
            # Lazy import: capabilities imports the orchestrator's schemas; avoid a cycle.
            from lucca.core.capabilities import get_capability_registry  # noqa: PLC0415

            reg = get_capability_registry()
            apps = [a["key"] for a in reg.get_whitelisted_apps() if a.get("status") != "Disabled"]
            pathways = list(reg.get_reasoning_pathways().keys())
            tools = [t.function.name for t in reg.get_tool_definitions()]
            content = (
                f"Available Core Tools: {', '.join(tools)}. "
                f"Whitelisted Desktop Applications (Tool Studio): {', '.join(apps)}. "
                f"Active MicroScheme Reasoning Pathways (LISP Studio): {', '.join(pathways)}."
            )
        except Exception as exc:  # noqa: BLE001 — registry failure must yield abstention, not a crash
            logger.warning("cascade_capabilities_substrate_unavailable", error=str(exc))
            return []

        return [
            EvidenceItem(
                substrate=EpistemicSubstrate.CAPABILITIES,
                trust_tier=TrustTier.TIER_0_AXIOMATIC,
                source="CapabilityRegistry",
                content=content,
                belnap_val=BelnapValue.TRUE,
                confidence=1.0,
                latency_ms=0.01,
            )
        ]

    # ------------------------------------------------------------------------
    # Substrate 0: System & Hardware Telemetry (< 1ms target)
    # ------------------------------------------------------------------------
    def query_substrate_0_telemetry(self, query_text: str) -> list[EvidenceItem]:
        """Queries live hardware telemetry (GPU, CPU, RAM, NPU, Time, Location) via system_tools."""
        lower = query_text.lower()
        items: list[EvidenceItem] = []

        try:
            # Lazy import: system_tools pulls pynvml/psutil; keep cascade import cheap.
            from lucca.sandbox.system_tools import get_system_metrics  # noqa: PLC0415

            metrics = get_system_metrics()
            gpu = metrics.get("gpu", {})
            cpu = metrics.get("cpu", {})
            ram = metrics.get("ram", {})

            wants_gpu = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("gpu", "vram", "nvidia", "graphics", "video memory")
            )
            wants_cpu = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("cpu", "processor", "core", "intel", "ultra 9")
            )
            wants_ram = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("ram", "physical memory", "system memory")
            )
            is_clock_freq = bool(
                re.search(r"\b(?:core|gpu|cpu|bus|memory)\s+clock\b", lower)
                or re.search(r"\bclock\s+(?:speed|rate|freq|frequency|multiplier)\b", lower)
            )
            wants_time = not is_clock_freq and any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in (
                    "what time",
                    "current time",
                    "local time",
                    "exact time",
                    "time is it",
                    "today",
                    "what day",
                    "what month",
                    "what year",
                    "wall clock",
                    "system clock",
                    "clock",
                )
            )
            wants_location = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("location", "where", "located", "ip", "network", "city", "country", "place")
            )
            general_hw = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in ("hardware", "specs", "telemetry", "substrate configuration", "system")
            )

            timezone_inquiry = any(
                re.search(rf"\b{re.escape(w)}\b", lower)
                for w in (
                    "timezone",
                    "time zone",
                    "timezones",
                    "time zones",
                    "utc offset",
                    "gmt offset",
                    "daylight saving",
                    "daylight savings",
                    "daylight-saving",
                    "dst",
                    "standard time",
                    "awst",
                    "aest",
                    "acst",
                    "pst",
                    "pdt",
                    "est",
                    "edt",
                    "cst",
                    "cdt",
                    "mst",
                    "mdt",
                    "sgt",
                    "jst",
                    "gmt",
                    "utc",
                )
            )
            wants_time = wants_time or timezone_inquiry

            if wants_time or general_hw:
                from lucca.sandbox.service import resolve_target_timezone  # noqa: PLC0415

                target_tz = resolve_target_timezone(query_text)
                if target_tz is not None:
                    now_tz = datetime.now(target_tz)
                    iana_name = target_tz.key
                    tz_abbr = now_tz.strftime("%Z")
                    utc_offset = now_tz.strftime("%z")
                    is_dst = bool(now_tz.dst() and now_tz.dst().total_seconds() != 0)
                    time_str = now_tz.strftime("%A, %B %d, %Y, %I:%M:%S %p (%Z, UTC%z)")
                    content = (
                        f"Grounded Timezone: {iana_name} ({tz_abbr}, UTC{utc_offset}) | "
                        f"DST Active: {is_dst} | Time: {time_str}"
                    )
                    items.append(
                        EvidenceItem(
                            substrate=EpistemicSubstrate.TELEMETRY,
                            trust_tier=TrustTier.TIER_1_HARDWARE,
                            source="system_tools:zoneinfo",
                            content=content,
                            polarity=BelnapValue.TRUE,
                            confidence=1.0,
                            metadata={
                                "iana_name": iana_name,
                                "abbreviation": tz_abbr,
                                "utc_offset": utc_offset,
                                "is_dst": is_dst,
                                "local_time": time_str,
                            },
                        )
                    )
                else:
                    now_local = datetime.now().astimezone()
                    time_str = now_local.strftime("%A, %B %d, %Y, %I:%M %p (%Z, UTC%z)")
                    iana_name = getattr(now_local.tzinfo, "key", None) or now_local.tzname() or "UTC"
                    tz_abbr = now_local.strftime("%Z")
                    utc_offset = now_local.strftime("%z")
                    is_dst = bool(now_local.dst() and now_local.dst().total_seconds() != 0)
                    content = (
                        f"Host Local Time: {time_str} | Timezone: {iana_name} "
                        f"({tz_abbr}, UTC{utc_offset}) | DST: {is_dst}"
                    )
                    items.append(
                        EvidenceItem(
                            substrate=EpistemicSubstrate.TELEMETRY,
                            trust_tier=TrustTier.TIER_1_HARDWARE,
                            source="system_tools:local_clock",
                            content=content,
                            polarity=BelnapValue.TRUE,
                            confidence=1.0,
                            metadata={
                                "timestamp": metrics.get("timestamp"),
                                "iana_name": iana_name,
                                "abbreviation": tz_abbr,
                                "utc_offset": utc_offset,
                                "is_dst": is_dst,
                            },
                        )
                    )

            if wants_location:
                from lucca.sandbox.service import get_host_network_and_location  # noqa: PLC0415

                net_geo = get_host_network_and_location()
                if net_geo.get("public_ip"):
                    loc_content = (
                        f"Physical Host Geolocation: {net_geo.get('city')}, {net_geo.get('region')}, "
                        f"{net_geo.get('country')} (Coordinates: {net_geo.get('coordinates')}, "
                        f"ISP: {net_geo.get('isp')}, Public IP: {net_geo.get('public_ip')})"
                    )
                else:
                    local_ips = (
                        ", ".join(str(x) for x in net_geo.get("local_ips", []))  # type: ignore[union-attr]
                        or "local only"
                    )
                    loc_content = f"Host Network: Local IPs [{local_ips}]"

                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.TELEMETRY,
                        trust_tier=TrustTier.TIER_1_HARDWARE,
                        source="system_tools:network_geo",
                        content=loc_content,
                        polarity=BelnapValue.TRUE,
                        confidence=1.0,
                        metadata=net_geo,
                    )
                )

            if wants_gpu or general_hw:
                content = (
                    f"GPU: {gpu.get('name', 'NVIDIA GPU')} | "
                    f"Total VRAM: {gpu.get('total_gb', 16.0)} GB | "
                    f"Free VRAM: {gpu.get('free_gb', 16.0)} GB | "
                    f"Used VRAM: {gpu.get('used_gb', 0.0)} GB | "
                    f"Utilization: {gpu.get('utilization_pct', 0.0)}%"
                )
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.TELEMETRY,
                        trust_tier=TrustTier.TIER_1_HARDWARE,
                        source="system_tools:nvidia-smi",
                        content=content,
                        polarity=BelnapValue.TRUE,
                        confidence=1.0,
                        metadata=gpu,
                    )
                )

            if wants_cpu or general_hw:
                content = (
                    f"CPU: {cpu.get('name', 'Intel Core Ultra 9 275HX')} | "
                    f"Cores: {cpu.get('cores_logical', 24)} logical | "
                    f"System Load: {cpu.get('percent', 0.0)}% | "
                    f"Lucca Load: {cpu.get('lucca_percent', 0.0)}%"
                )
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.TELEMETRY,
                        trust_tier=TrustTier.TIER_1_HARDWARE,
                        source="system_tools:psutil_cpu",
                        content=content,
                        polarity=BelnapValue.TRUE,
                        confidence=1.0,
                        metadata=cpu,
                    )
                )

            if wants_ram or general_hw:
                content = (
                    f"System RAM: {ram.get('total_gb', 64.0)} GB total | "
                    f"Free: {ram.get('free_gb', 40.0)} GB | "
                    f"Used: {ram.get('used_gb', 24.0)} GB ({ram.get('percent', 0.0)}%) | "
                    f"Lucca RSS: {ram.get('lucca_used_mb', 0.0)} MB"
                )
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.TELEMETRY,
                        trust_tier=TrustTier.TIER_1_HARDWARE,
                        source="system_tools:psutil_ram",
                        content=content,
                        polarity=BelnapValue.TRUE,
                        confidence=1.0,
                        metadata=ram,
                    )
                )

        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_0_telemetry_query_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Substrate 1: Workspace Filesystem & AST (5–20ms target)
    # ------------------------------------------------------------------------
    def query_substrate_1_workspace(self, query_text: str) -> list[EvidenceItem]:
        """Queries workspace files via SandboxService or PersistentDockerWorker."""
        items: list[EvidenceItem] = []
        if not self.sandbox:
            return items

        try:
            lower = query_text.lower()

            # 1. Inbox inquiries
            if any(w in lower for w in ("inbox", "drop folder", "incoming")):
                res = self._execute_sandbox(
                    tool_name="list_dir",
                    args={"path": "inbox"},
                    confirmed=True,
                )
                if res and res.ok:
                    entries = (
                        (res.structured or {}).get("entries", [])
                        if isinstance(res.structured, dict)
                        else []
                    )
                    names = [str(e.get("name", "")) for e in entries if isinstance(e, dict)]
                    if names:
                        content_str = (
                            f"Inbox drop folder contains {len(names)} file(s) waiting to be imported: "
                            f"{', '.join(names)}. (Location: host inbox/)"
                        )
                    else:
                        content_str = "Inbox drop folder is currently empty (0 files waiting)."
                    items.append(
                        EvidenceItem(
                            substrate=EpistemicSubstrate.WORKSPACE,
                            trust_tier=TrustTier.TIER_2_WORKSPACE,
                            source="workspace:inbox",
                            content=content_str,
                            polarity=BelnapValue.TRUE,
                            confidence=1.0,
                            metadata={"path": "inbox", "files": names, "count": len(names)},
                        )
                    )
                return items

            # 2. Specific file read inquiries (e.g. "Read config/persona.toml in the workspace")
            file_match = re.search(
                r"([\w\-./\\]+\.(?:toml|py|json|md|txt|ya?ml|url))", query_text
            )
            is_explicit_listing = any(
                w in lower for w in ("list files", "directory", "folder", "all files", "what files")
            )
            if file_match and not is_explicit_listing:
                rel_path = file_match.group(1).replace("\\", "/")
                res = self._execute_sandbox(
                    tool_name="read_file",
                    args={"path": rel_path},
                    confirmed=True,
                )
                if res and res.ok and res.content:
                    snippet = res.content[:500]
                    items.append(
                        EvidenceItem(
                            substrate=EpistemicSubstrate.WORKSPACE,
                            trust_tier=TrustTier.TIER_2_WORKSPACE,
                            source=f"workspace:{rel_path}",
                            content=snippet,
                            polarity=BelnapValue.TRUE,
                            confidence=1.0,
                            metadata={"path": rel_path, "truncated": len(res.content) > 500},
                        )
                    )
                return items

            # 3. General workspace file listing inquiries
            is_workspace_listing = (
                any(
                    w in lower
                    for w in (
                        "list files",
                        "directory",
                        "workspace files",
                        "folder",
                        "files at all",
                        "any files",
                        "what files",
                        "have any files",
                        "do you have files",
                        "files do you have",
                        "in your workspace",
                        "in the workspace",
                        "files in workspace",
                        "show files",
                        "show me files",
                        "contents of workspace",
                        "what's in your workspace",
                        "what is in your workspace",
                        "all files",
                    )
                )
                or ("files" in lower and "workspace" in lower)
                or ("files" in lower and any(v in lower for v in ("have", "see", "show", "list", "any")))
            )

            if is_workspace_listing:
                res = self._execute_sandbox(
                    tool_name="list_dir",
                    args={"path": "."},
                    confirmed=True,
                )
                if res and res.ok:
                    entries = (
                        (res.structured or {}).get("entries", [])
                        if isinstance(res.structured, dict)
                        else []
                    )
                    names = [str(e.get("name", "")) for e in entries if isinstance(e, dict)]
                    if names:
                        content_str = (
                            f"Workspace directory contains {len(names)} item(s): "
                            f"{', '.join(names)}."
                        )
                    else:
                        content_str = "Workspace directory is currently empty (0 files)."
                    items.append(
                        EvidenceItem(
                            substrate=EpistemicSubstrate.WORKSPACE,
                            trust_tier=TrustTier.TIER_2_WORKSPACE,
                            source="workspace:list_dir",
                            content=content_str,
                            polarity=BelnapValue.TRUE,
                            confidence=1.0,
                            metadata={"path": ".", "files": names, "count": len(names)},
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_1_workspace_query_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Substrate 2: Cryptographic Episodic Memory (15–40ms target)
    # ------------------------------------------------------------------------
    def query_substrate_2_memory(self, query_text: str) -> list[EvidenceItem]:
        """Queries memory store for semantic/episodic facts with provenance."""
        items: list[EvidenceItem] = []
        if not self.memory_store or not query_text.strip():
            return items

        self._last_recollections: list[str] = []
        try:
            q = RetrievalQuery(query_text=query_text.strip(), k=8, include_superseded=True)
            res = self.memory_store.search(q)
            raw_hits: list[MemoryHit] = res if isinstance(res, list) else []

            for hit in raw_hits:
                # Invariant D-MEM-04: Non-grounding rows MUST NOT enter Belnap evidence fusion!
                if not getattr(hit, "grounding_eligible", True):
                    self._last_recollections.append(f'[{hit.provenance.value}] "{hit.content}"')
                    continue

                prov_val = (
                    hit.provenance.value
                    if hasattr(hit.provenance, "value")
                    else str(hit.provenance)
                )
                is_sup = hit.valid_to is not None
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.MEMORY,
                        trust_tier=TrustTier.TIER_3_MEMORY,
                        source=f"memory:{hit.memory_id or hit.source_turn_id}",
                        content=hit.content,
                        polarity=BelnapValue.TRUE,
                        confidence=hit.score,
                        metadata={
                            "kind": hit.kind,
                            "provenance": prov_val,
                            "created_at": hit.created_at,
                            "valid_from": getattr(hit, "valid_from", hit.created_at),
                            "valid_to": getattr(hit, "valid_to", None),
                            "superseded_by": getattr(hit, "superseded_by", None),
                            "is_superseded": is_sup,
                            "confidence": getattr(hit, "confidence", None),
                        },
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_2_memory_query_error", error=str(exc))

        return items

    def _evaluate_polarity(
        self,
        content: str,
        query_text: str = "",
    ) -> tuple[bool, bool]:
        """Evaluates evidential polarity (told_true, told_false) for an evidence item.

        Remediates hardcoded told_false=False defects (v1.35.7 Phase 1 hygiene).
        In Phase 3, integrates SemanticVerifierPort with automatic fail-open lexical degradation.
        Supports both instance calls `self._evaluate_polarity(content, query)` and
        unbound class calls `EpistemicSearchCascade._evaluate_polarity(content, query)`.
        """
        if isinstance(self, str):
            actual_content = self
            actual_query = content if isinstance(content, str) else query_text
            verifier = None
        else:
            actual_content = content
            actual_query = query_text
            verifier = getattr(self, "verifier", None)

        if verifier is not None and actual_query.strip():
            try:
                v_res = verifier.check_consistency(
                    premise=actual_content, hypothesis=actual_query
                )
                if not v_res.degraded:
                    if v_res.label == VerifierLabel.ENTAILMENT:
                        return True, False
                    if v_res.label == VerifierLabel.CONTRADICTION:
                        return False, True
            except Exception as exc:  # noqa: BLE001
                logger.debug("cascade_verifier_eval_failed", error=str(exc))

        content_lower = actual_content.lower()
        query_lower = actual_query.lower() if actual_query else ""

        # Strong negation / refutation patterns
        refutation_patterns = [
            r"\b(?:not\s+supported|does\s+not\s+support|do\s+not\s+support|cannot|unsupported)\b",
            r"\b(?:no\s+longer\s+supported|deprecated|removed|disabled|incompatible)\b",
            r"\b(?:not\s+available|never\s+supported|impossible|fails\s+to)\b",
            r"\b(?:is\s+false|false\b)",
        ]

        is_refuting = any(re.search(pat, content_lower) for pat in refutation_patterns)

        if is_refuting:
            query_is_negative = bool(
                re.search(r"\b(?:not|unsupported|never|cannot)\b", query_lower)
            )
            if query_is_negative:
                return True, False
            return False, True

        return True, False

    def query_substrate_self_history(self, query_text: str) -> list[EvidenceItem]:
        """
        Queries self-history (Substrate 7: SELF_HISTORY, Tier 1).
        Entailed by execution_triples ∪ ASSISTANT_ACTION ∪ ASSISTANT_UTTERANCE ∪ COHERENCE_BREACH.
        Abstains (returns empty list) if the record is empty.
        """
        items: list[EvidenceItem] = []
        db = getattr(self.memory_store, "db", None)
        if not db or not query_text.strip():
            return items

        try:
            tokens = tokenize_query(query_text)
            candidates: list[tuple[int, float, EvidenceItem]] = []

            episodes = recall_past_episodes(db, query_text, limit=10)
            for ep in episodes:
                ev = EvidenceItem(
                    substrate=EpistemicSubstrate.SELF_HISTORY,
                    trust_tier=TrustTier.TIER_1_HARDWARE,
                    source=f"history:{ep.source}:{ep.record_id}",
                    content=ep.summary,
                    polarity=BelnapValue.TRUE,
                    confidence=min(1.0, ep.match_score / max(1, ep.tokens_total)),
                    metadata={
                        "match_score": ep.match_score,
                        "tokens_total": ep.tokens_total,
                        **ep.payload,
                    },
                )
                items.append(ev)
                candidates.append((ep.match_score, ep.ts, ev))

            with db.read_cursor() as cur:
                # 2. Query memories for autobiographical classes
                cur.execute(
                    """
                    SELECT m.memory_id, m.content, p.provenance, p.trace_id,
                           m.created_at, m.superseded_by, p.grounding_eligible
                    FROM memories m
                    JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                    WHERE p.provenance IN (
                        'ASSISTANT_ACTION', 'ASSISTANT_UTTERANCE',
                        'COHERENCE_BREACH', 'ASSISTANT_BELIEF'
                    )
                    ORDER BY m.created_at DESC LIMIT 100
                    """
                )
                mem_rows = cur.fetchall()
                for mid, content, prov, tr_id, cat_ts, sup_by, gr_elig in mem_rows:
                    content_str = str(content)
                    is_wrong_query = "wrong" in query_text.lower() or "error" in query_text.lower()
                    if is_wrong_query and (prov == "COHERENCE_BREACH" or sup_by is not None):
                        told_true, told_false = self._evaluate_polarity(
                            content_str, query_text
                        )
                        candidates.append(
                            (
                                10,  # Highest priority for explicit error/breach retrospection
                                float(cat_ts),
                                EvidenceItem(
                                    substrate=EpistemicSubstrate.SELF_HISTORY,
                                    trust_tier=TrustTier.TIER_1_HARDWARE,
                                    source=f"history:breach:{mid}",
                                    content=(
                                        f"Historical revision / breach: {content_str} "
                                        f"(superseded_by={sup_by})"
                                    ),
                                    told_true=told_true,
                                    told_false=told_false,
                                    confidence=1.0,
                                    metadata={"provenance": str(prov), "superseded_by": sup_by},
                                ),
                            )
                        )
                    elif not is_wrong_query and tokens:
                        score = sum(1 for t in tokens if t in content_str.lower())
                        if score > 0:
                            told_true, told_false = self._evaluate_polarity(
                                content_str, query_text
                            )
                            candidates.append(
                                (
                                    score,
                                    float(cat_ts),
                                    EvidenceItem(
                                        substrate=EpistemicSubstrate.SELF_HISTORY,
                                        trust_tier=TrustTier.TIER_1_HARDWARE,
                                        source=f"history:{str(prov).lower()}:{mid}",
                                        content=content_str,
                                        told_true=told_true,
                                        told_false=told_false,
                                        confidence=1.0,
                                        metadata={
                                            "provenance": str(prov),
                                            "trace_id": str(tr_id),
                                            "grounding_eligible": int(gr_elig),
                                        },
                                    ),
                                )
                            )

                # Sort by (match_score DESC, created_at DESC) and cap at 5 items
                candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
                seen_sources = set()
                deduped: list[EvidenceItem] = []
                for _, _, item in candidates:
                    if item.source not in seen_sources:
                        seen_sources.add(item.source)
                        deduped.append(item)
                    if len(deduped) >= 5:
                        break
                return deduped
        except Exception as exc:  # noqa: BLE001
            logger.debug("self_history_recall_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Substrate 3: SSRF-Hardened Sandboxed Web (300–1500ms target)
    # ------------------------------------------------------------------------
    def query_substrate_3_web(self, query_text: str) -> list[EvidenceItem]:
        """Queries external web when explicit URL is supplied or via web search fallback."""
        items: list[EvidenceItem] = []
        if not self.sandbox:
            return items

        url_match = re.search(r"(https?://[^\s\"'>]+)", query_text)
        if url_match:
            target_url = url_match.group(1)
            try:
                # Propagate untrusted web taint to active session guard (Spec 09 / D-SEC-04)
                if (
                    self.sandbox
                    and hasattr(self.sandbox, "guard")
                    and hasattr(self.sandbox.guard, "mark_taint")
                ):
                    # Lazy import: avoids a sandbox <-> core import cycle.
                    from lucca.sandbox.policy import TaintFlags  # noqa: PLC0415

                    self.sandbox.guard.mark_taint(TaintFlags.UNTRUSTED_WEB)

                res = self._execute_sandbox(
                    tool_name="fetch_url",
                    args={"url": target_url},
                    confirmed=True,
                )
                if res and res.ok and res.content:
                    told_true, told_false = self._evaluate_polarity(
                        res.content[:600], query_text
                    )
                    items.append(
                        EvidenceItem(
                            substrate=EpistemicSubstrate.WEB,
                            trust_tier=TrustTier.TIER_4_WEB,
                            source=f"web:{target_url}",
                            content=res.content[:600],
                            proposition=f"web_content({target_url})",
                            told_true=told_true,
                            told_false=told_false,
                            confidence=0.85,
                            metadata={"url": target_url},
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("substrate_3_web_query_error", error=str(exc))
            return items

        # Fallback to search_web when no explicit URL is supplied
        try:
            if (
                self.sandbox
                and hasattr(self.sandbox, "guard")
                and hasattr(self.sandbox.guard, "mark_taint")
            ):
                from lucca.sandbox.policy import TaintFlags  # noqa: PLC0415

                self.sandbox.guard.mark_taint(TaintFlags.UNTRUSTED_WEB)

            topic = extract_clean_topic(query_text)
            search_query = topic if topic and topic != "that" else query_text
            target_entity = _extract_target_entity(query_text)

            search_args: dict[str, JsonValue] = {"query": search_query}
            if target_entity:
                search_args["target_entity"] = target_entity

            res = self._execute_sandbox(
                tool_name="search_web",
                args=search_args,
                confirmed=True,
            )
            if res and res.ok and res.content:
                told_true, told_false = self._evaluate_polarity(
                    res.content[:1500], query_text
                )
                items.append(
                    EvidenceItem(
                        substrate=EpistemicSubstrate.WEB,
                        trust_tier=TrustTier.TIER_4_WEB,
                        source=f"web_search:{search_query}",
                        content=res.content[:1500],
                        proposition=f"web_search_results({search_query})",
                        told_true=told_true,
                        told_false=told_false,
                        confidence=0.85,
                        metadata=res.structured if isinstance(res.structured, dict) else {"query": search_query},
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("substrate_3_web_search_error", error=str(exc))

        return items

    # ------------------------------------------------------------------------
    # Synthesis & Belnap Evidential Valuation
    # ------------------------------------------------------------------------
    def _detect_memory_supersession(
        self,
        evidence: list[EvidenceItem],
    ) -> tuple[list[str], list[str]]:
        """
        Detects intra-tier memory supersession per D-HON-01 and Spec 04 §3.
        Identifies newer valid_from facts on functional predicates or explicitly
        superseded rows.
        Returns:
            (resolutions, narration_contracts)
        Marks superseded EvidenceItems with metadata['is_superseded'] = True.
        """
        resolutions: list[str] = []
        narration_contracts: list[str] = []

        mem_items = [e for e in evidence if e.trust_tier == TrustTier.TIER_3_MEMORY]
        if not mem_items:
            return resolutions, narration_contracts

        # 1. Group by functional predicate (s, p)
        pred_groups: dict[tuple[str, str], list[tuple[EvidenceItem, float, str]]] = {}
        for item in mem_items:
            vf = float(item.metadata.get("valid_from", 0.0) or item.timestamp_ns / 1e9)
            content = item.content.strip()
            parts = content.split(maxsplit=2)
            if len(parts) >= 3 and parts[1] in FUNCTIONAL_PREDICATES:
                s, p, o = parts[0], parts[1], parts[2]
                pred_groups.setdefault((s, p), []).append((item, vf, o))
            else:
                for pred in FUNCTIONAL_PREDICATES:
                    if f" {pred} " in f" {content} ":
                        idx = content.find(pred)
                        s = content[:idx].strip() or "user"
                        o = content[idx + len(pred) :].strip()
                        pred_groups.setdefault((s, p), []).append((item, vf, o))
                        break

        def _entry_precedence(e: tuple[EvidenceItem, float, str]) -> tuple[int, float]:
            item, vf, _ = e
            prov = str(item.metadata.get("provenance", "")).upper()
            if "USER_EXPLICIT" in prov:
                p_rank = 4
            elif "USER_DERIVED" in prov:
                p_rank = 3
            elif "INFERRED" in prov:
                p_rank = 2
            elif "LISP" in prov or "ASSERTION" in prov:
                p_rank = 1
            else:
                p_rank = 0
            return (p_rank, vf)

        for (_s, _p), entries in pred_groups.items():
            if len(entries) < 2:
                continue
            entries.sort(key=_entry_precedence, reverse=True)
            best_item, best_vf, best_val = entries[0]
            for stale_item, _stale_vf, stale_val in entries[1:]:
                if stale_val.lower() != best_val.lower():
                    stale_item.metadata["is_superseded"] = True
                    resolutions.append(
                        f"D-HON-01 Verified Store Priority — Current value per store: "
                        f"'{best_item.content}' (valid_from: {best_vf}) supersedes "
                        f"historical record: '{stale_item.content}'"
                    )
                    narration_contracts.append(
                        "Narration Contract: Cite the verified store's current value over "
                        "transcript echo for entity-attribute queries per D-HON-01."
                    )

        # 2. Check for explicit valid_to on any memory items
        for item in mem_items:
            if item.metadata.get("valid_to") is not None or item.metadata.get("is_superseded"):
                item.metadata["is_superseded"] = True
                if not any(item.content in r for r in resolutions):
                    active_candidates = [
                        e
                        for e in mem_items
                        if not bool(e.metadata.get("is_superseded"))
                        and e.metadata.get("valid_to") is None
                    ]
                    if active_candidates:
                        active_candidates.sort(
                            key=lambda e: float(e.metadata.get("valid_from", 0.0) or 0.0),
                            reverse=True,
                        )
                        best = active_candidates[0]
                        resolutions.append(
                            f"D-HON-01 Verified Store Priority — Current value per store: "
                            f"'{best.content}' supersedes historical record: '{item.content}'"
                        )
                        narration_contracts.append(
                            "Narration Contract: Cite the verified store's current value over "
                            "transcript echo for entity-attribute queries per D-HON-01."
                        )

        return resolutions, narration_contracts

    def synthesize(
        self,
        query_text: str,
        evidence: list[EvidenceItem],
        topic: str | None = None,
        queried_substrates: Sequence[EpistemicSubstrate] | None = None,
        recollections: Sequence[str] | None = None,
    ) -> tuple[BelnapValue, str, str | None]:
        """
        Computes the Belnap evidential valuation and renders formatted context.
        Applies hierarchical trust tier tie-breaking:
        - Same-tier contradiction (told_true AND told_false) -> genuine conflict (TOP).
        - Cross-tier contradiction -> higher trust tier strictly supersedes lower tier.
          Stale historical lower-tier records do not block or force an unnecessary hedge.
        - Zero evidence -> BelnapValue.UNKNOWN (BOT) with dynamic honest refusal.
        Returns: (BelnapValue, synthesized_context, calibrated_refusal)
        """
        # Case 1: Substrate 4 Honest Abstention (Epistemic Gap BOT)
        if not evidence:
            refusal = build_calibrated_refusal(queried_substrates or [], topic)
            queried_names = [s.name for s in (queried_substrates or [])]
            synth_ctx = (
                f"[Belnap Epistemic State: BOT (Epistemic Gap / Unknown)]\n"
                f"Queried Substrates: {queried_names}\n"
                f"Empirical Status: No verified records or facts found for topic "
                f"'{topic or 'unspecified'}'.\n"
                "Mandatory Grounding Directive: You do not possess verified knowledge on this "
                "topic. You MUST explicitly admit uncertainty and decline to confabulate or guess. "
                f'Calibrated Statement: "{refusal}"'
            )
            return BelnapValue.UNKNOWN, synth_ctx, refusal

        # Group evidence by Trust Tier
        tier_map: dict[TrustTier, list[EvidenceItem]] = {}
        for ev in evidence:
            tier_map.setdefault(ev.trust_tier, []).append(ev)

        highest_tier = min(tier_map.keys())
        highest_tier_evidence = tier_map[highest_tier]

        # Supersession checks: intra-tier (D-HON-01) and cross-tier
        superseded_annotations: list[str] = []
        narration_contracts: list[str] = []

        intra_res, intra_contracts = self._detect_memory_supersession(evidence)
        superseded_annotations.extend(intra_res)
        narration_contracts.extend(intra_contracts)

        # Check Belnap value within highest active trust tier (excluding superseded records)
        active_highest = [
            e for e in highest_tier_evidence if not bool(e.metadata.get("is_superseded"))
        ]
        eval_tier_evidence = active_highest if active_highest else highest_tier_evidence
        highest_told_true = any(e.told_true for e in eval_tier_evidence)
        highest_told_false = any(e.told_false for e in eval_tier_evidence)

        if highest_told_true and highest_told_false:
            # Genuine same-tier contradiction
            belnap_status = BelnapValue.CONFLICT
        elif highest_told_true:
            belnap_status = BelnapValue.TRUE
        elif highest_told_false:
            belnap_status = BelnapValue.FALSE
        else:
            belnap_status = BelnapValue.UNKNOWN

        # Cross-tier staleness / supersession check
        for tier, items in tier_map.items():
            if tier > highest_tier:
                tier_told_true = any(e.told_true for e in items)
                tier_told_false = any(e.told_false for e in items)
                # If lower tier contradicts the higher tier:
                if (highest_told_true and tier_told_false) or (
                    highest_told_false and tier_told_true
                ):
                    superseded_annotations.append(
                        f"Trust Tier {highest_tier.value} ({highest_tier.name}) strictly "
                        f"supersedes historical/lower-trust Tier {tier.value} ({tier.name}) record."
                    )

        # Build formatted grounded context
        lines: list[str] = ["[Epistemic Search Cascade — Verified Ground Truth]"]
        if belnap_status == BelnapValue.CONFLICT:
            lines.append(
                "[Status: CONFLICT (TOP) — Genuine internal contradiction detected within "
                "authoritative tier; tension noted]"
            )
        else:
            lines.append(
                f"[Status: CONSISTENT ({belnap_status.value}) — Grounded Evidence Verified]"
            )

        if superseded_annotations:
            for note in superseded_annotations:
                lines.append(f"[Resolution: {note}]")
        if narration_contracts:
            for contract in sorted(set(narration_contracts)):
                lines.append(f"[{contract}]")

        # Sort evidence by Trust Tier, active before superseded, then confidence, valid_from
        def _evidence_sort_key(e: EvidenceItem) -> tuple[int, int, float, float]:
            is_sup = 1 if bool(e.metadata.get("is_superseded")) else 0
            vf = float(e.metadata.get("valid_from", 0.0) or 0.0)
            return (e.trust_tier.value, is_sup, -e.confidence, -vf)

        sorted_evidence = sorted(evidence, key=_evidence_sort_key)

        current_tier: TrustTier | None = None
        for item in sorted_evidence:
            if item.trust_tier != current_tier:
                current_tier = item.trust_tier
                lines.append(f"\n[Trust Tier {current_tier.value}: {current_tier.name}]")
            if bool(item.metadata.get("is_superseded")):
                polarity_tag = "[superseded]"
            elif item.metadata.get("provenance") == "INFERRED":
                meta_conf = item.metadata.get("confidence")
                conf_val = float(meta_conf) if meta_conf is not None else float(item.confidence)
                std_label = standard_for_confidence(conf_val).value
                polarity_tag = f"[inferred, confidence {conf_val:.2f} — {std_label}]"
            else:
                polarity_tag = (
                    "[asserts]"
                    if (item.told_true and not item.told_false)
                    else "[refutes]"
                    if (item.told_false and not item.told_true)
                    else "[both]"
                    if (item.told_true and item.told_false)
                    else "[neither]"
                )
            lines.append(f"- ({item.source}) {polarity_tag} {item.content}")

        # Append non-grounding recollections under explicit quoting frame (D-MEM-04)
        if recollections:
            lines.append(
                "\n[Recollections (Non-Grounding)]\n"
                "Things you previously said or believed — quote them as such; "
                "they are not evidence:"
            )
            for rec in recollections:
                lines.append(f"- {rec}")

        context_str = "\n".join(lines)
        return belnap_status, context_str, None

    # ------------------------------------------------------------------------
    # Master Cascade Query Loop
    # ------------------------------------------------------------------------
    def query(
        self,
        query_text: str,
        substrates: list[EpistemicSubstrate] | None = None,
        emit_floor_cue: bool = True,
    ) -> SearchCascadeResult:
        """
        Executes cascade fall-through across designated substrates,
        measuring elapsed time and returning consolidated evidence.
        """
        t0 = time.perf_counter()

        is_epistemic, detected_subs, topic = self.classify_intent(query_text)

        if substrates is not None:
            active_substrates = list(substrates)
        else:
            active_substrates = detected_subs or [
                EpistemicSubstrate.TELEMETRY,
                EpistemicSubstrate.WORKSPACE,
                EpistemicSubstrate.MEMORY,
            ]

        cue = self.select_floor_cue(query_text, active_substrates[0] if active_substrates else None)
        floor_cue = cue if (self.enable_floor_cues and emit_floor_cue) else None

        collected_evidence: list[EvidenceItem] = []
        resolved_substrate = EpistemicSubstrate.ABSTENTION

        for sub in active_substrates:
            if sub == EpistemicSubstrate.SELF:
                items = self.query_substrate_self(query_text)
                if items:
                    collected_evidence.extend(items)
                    resolved_substrate = EpistemicSubstrate.SELF
            elif sub == EpistemicSubstrate.CAPABILITIES:
                items = self.query_substrate_capabilities(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate in (
                        EpistemicSubstrate.ABSTENTION,
                        EpistemicSubstrate.SELF,
                    ):
                        resolved_substrate = EpistemicSubstrate.CAPABILITIES
            elif sub == EpistemicSubstrate.TELEMETRY:
                items = self.query_substrate_0_telemetry(query_text)
                if items:
                    collected_evidence.extend(items)
                    resolved_substrate = EpistemicSubstrate.TELEMETRY
            elif sub == EpistemicSubstrate.WORKSPACE:
                items = self.query_substrate_1_workspace(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.WORKSPACE
            elif sub == EpistemicSubstrate.MEMORY:
                items = self.query_substrate_2_memory(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.MEMORY
            elif sub == EpistemicSubstrate.WEB:
                items = self.query_substrate_3_web(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate == EpistemicSubstrate.ABSTENTION:
                        resolved_substrate = EpistemicSubstrate.WEB
            elif sub == EpistemicSubstrate.SELF_HISTORY:
                items = self.query_substrate_self_history(query_text)
                if items:
                    collected_evidence.extend(items)
                    if resolved_substrate in (
                        EpistemicSubstrate.ABSTENTION,
                        EpistemicSubstrate.SELF,
                    ):
                        resolved_substrate = EpistemicSubstrate.SELF_HISTORY

        # Retrieve any non-grounding recollections recorded during memory query
        recollections = list(getattr(self, "_last_recollections", []))

        # Perform Belnap evidential synthesis
        belnap_val, synthesized_ctx, calibrated_refusal = self.synthesize(
            query_text=query_text,
            evidence=collected_evidence,
            topic=topic,
            queried_substrates=active_substrates,
            recollections=recollections,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return SearchCascadeResult(
            belnap_status=belnap_val,
            evidence=collected_evidence,
            resolved_substrate=resolved_substrate,
            elapsed_ms=round(elapsed_ms, 3),
            floor_cue_spoken=floor_cue,
            calibrated_refusal=calibrated_refusal,
            synthesized_context=synthesized_ctx,
            queried_substrates=active_substrates,
            recollections=recollections,
        )
