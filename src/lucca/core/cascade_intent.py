"""
Project Lucca — Epistemic Cascade Intent Classifier and Floor-Holding Cues (WO-43 Phase 3.3)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §3
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from lucca.core.cascade import EpistemicSubstrate


def _sub() -> type[EpistemicSubstrate]:
    from lucca.core.cascade import EpistemicSubstrate  # noqa: PLC0415

    return EpistemicSubstrate


def select_floor_cue(query_text: str, target_substrate: EpistemicSubstrate | None = None) -> str:
    """
    Selects an acoustic floor-holding reflex cue within < 1ms to claim
    the conversational floor before multi-substrate search execution.
    """
    lower = query_text.lower()
    if target_substrate == _sub().SELF:
        return "Reflecting on my design..."
    if target_substrate == _sub().CAPABILITIES:
        return "Checking my capabilities..."
    if target_substrate == _sub().TELEMETRY or any(
        w in lower
        for w in ("gpu", "vram", "cpu", "ram", "hardware", "specs", "load", "utilization")
    ):
        return "Checking system telemetry..."
    if target_substrate == _sub().WORKSPACE or any(
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
    if target_substrate == _sub().MEMORY or any(
        w in lower for w in ("remember", "memory", "preference", "last time", "we talked", "who is")
    ):
        return "Checking my memory records..."
    if target_substrate == _sub().SELF_HISTORY or any(
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
    if target_substrate == _sub().WEB or any(
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
    "australia",
    "australian",
    "aussie",
    "uk",
    "british",
    "britain",
    "england",
    "scotland",
    "scottish",
    "ireland",
    "irish",
    "new zealand",
    "kiwi",
    "philippines",
    "filipino",
    "singapore",
    "singaporean",
    "malaysia",
    "malaysian",
    "new york",
    "nyc",
    "chicago",
    "texas",
    "southern",
    "canada",
    "canadian",
    "south africa",
    "japan",
    "japanese",
)

SLANG_OR_DIALECT_WORDS: tuple[str, ...] = (
    "slang",
    "colloquial",
    "colloquialism",
    "dialect",
    "idiom",
    "vernacular",
    "lingo",
    "jargon",
    "local term",
    "street term",
)

CULINARY_WORDS: tuple[str, ...] = (
    "food",
    "dish",
    "snack",
    "fish",
    "meat",
    "pastry",
    "cuisine",
    "grub",
    "cheese",
    "sandwich",
    "dessert",
    "bread",
    "roll",
    "pie",
    "stew",
    "beverage",
    "drink",
    "street food",
    "recipe",
    "barm",
)


def matches_slang_or_world_definition(lower: str) -> bool:
    """
    Conformal uncertainty gating: detect cultural, culinary, regional slang or unfamiliar entity
    inquiries.
    """
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
    # Detected structurally via formal problem framing, premise enumeration, or equations.
    closed_world_framing_pattern = re.compile(
        r"(?:^(?:consider\s+the\s+following|assume\s+a\s+counterfactual|suppose\s+that|"
        r"given\s+(?:the\s+)?(?:following\s+)?(?:clauses|premises|constraints|equations)|"
        r"scenario:|observations:|premises?:|clues?:|rule\s+\d+:)|"
        r"\b(?:step-by-step\s+deductive\s+proof|solve\s+(?:this\s+)?(?:logic\s+)?puzzle|"
        r"logic\s+puzzle|cryptarithmetic|satisfiable|truth-tellers?\s+and\s+liars?|"
        r"knights?\s+and\s+knaves?|solve\s+for\s+[a-z]\b))",
        re.IGNORECASE,
    )
    if closed_world_framing_pattern.search(lower):
        return False, [], None

    # Structural detection of self-contained math/constraint word problems:
    # Multiple numbered premises/rules or algebraic equations without personal/system inquiry.
    has_personal_or_system_ref = bool(
        re.search(
            r"\b(?:my|your|our|lucca|workspace|file|directory|gpu|cpu|ram|memory|session)\b",
            lower,
        )
    )
    if not has_personal_or_system_ref:
        has_numbered_premises = len(re.findall(r"(?:^|\n)\s*\d+\.\s+[A-Z]", clean)) >= 2
        has_algebraic_relations = bool(
            re.search(r"\b[a-z]\s*[+\-*/=<>]+\s*[a-z0-9]", lower)
            or re.search(
                r"\b(?:premise|clause|constraint|hypothesis|interval)\s+["
                r"a-z0-9]+\b",
                lower,
            )
        )
        if has_numbered_premises or has_algebraic_relations:
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

    # Substrate MEMORY: Episodic Memory & Personal/User Facts
    memory_words = (
        "what did i",
        "what did we",
        "do you remember",
        "in memory",
        "what is my",
        "what's my",
        "what was my",
        "what are my",
        "who is my",
        "where is my",
        "my favorite",
        "my preference",
        "prefer",
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
    # Structural detection of personal/private user or creator fact inquiries:
    # First-person possessive ("my <noun>", "creator's <noun>", "what did I <verb>")
    has_personal_fact_inquiry = bool(
        re.search(
            r"\b(?:what|who|where|when|which|tell\s+me|do\s+you\s+(?:know|remember|recall))\b"
            r".*\b(?:my|mine|i\s+(?:have|had|ate|own|live|prefer|like|use|told|said|set|chose)|"
            r"creator(?:'s)?|user(?:'s)?)\b",
            lower,
        )
        or re.search(
            r"\b(?:my|creator(?:'s)?|user(?:'s)?)\s+(?:[a-z]+\s+){0,2}"
            r"(?:name|pet|password|passkey|secret|key|code|pin|birthday|age|job|occupation|"
            r"family|friend|partner|sibling|allergy|diet|meal|car|phone|email|account)\b",
            lower,
        )
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
    # Inquiries about private user/creator facts must query MEMORY rather than axiomatic SELF
    is_private_memory = has_personal_fact_inquiry and not bool(
        re.search(
            r"\b(?:who\s+are\s+you|what\s+is\s+your\s+name|introduce\s+yourself|"
            r"tell\s+me\s+about\s+yourself|what\s+are\s+you)\b",
            lower,
        )
    )
    if re.search(self_pattern, lower) and not is_private_memory:
        substrates.append(_sub().SELF)
    if re.search(capability_pattern, lower):
        substrates.append(_sub().CAPABILITIES)
    is_personal_event_time = bool(
        re.search(
            r"\bwhat\s+time\s+(?:did|was|were|is\s+my|are\s+my|does\s+my|do\s+i)\b",
            lower,
        )
    )
    is_crypto_wallet = bool(
        re.search(r"\b(?:crypto|recovery\s+phrase|seed\s+phrase|wallet)\b", lower)
    )
    if _any_term_matches(lower, telemetry_words) and not is_crypto_wallet:
        substrates.append(_sub().TELEMETRY)
    if _any_term_matches(lower, temporal_words) and not is_personal_event_time:
        substrates.append(_sub().TELEMETRY)
        if _sub().SELF not in substrates:
            substrates.append(_sub().SELF)
    if is_personal_event_time or is_crypto_wallet:
        if _sub().MEMORY not in substrates:
            substrates.append(_sub().MEMORY)
    if _any_term_matches(lower, location_words):
        substrates.append(_sub().TELEMETRY)
        if _sub().SELF not in substrates:
            substrates.append(_sub().SELF)
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
    has_past_action_or_receipt_inquiry = bool(
        _any_term_matches(lower, self_history_words)
        or re.search(
            r"\b(?:did|have|had)\s+you\s+(?:ever\s+|actually\s+|successfully\s+|previously\s+|already\s+)?"
            r"(?:write|wrote|written|save|saved|create|created|edit|edited|modify|modified|"
            r"overwrite|overwritten|append|appended|read|inspect|inspected|open|opened|"
            r"delete|deleted|remove|removed|erase|erased|launch|launched|start|started|"
            r"run|ran|execute|executed|fetch|fetched|retrieve|retrieved|download|downloaded|"
            r"search|searched|query|queried|try|tried|attempt|attempted|tell|told|say|said|"
            r"mention|mentioned|state|stated|claim|claimed|use|used|call|called|perform|performed|"
            r"complete|completed|succeed|succeeded|fail|failed)\b",
            lower,
        )
        or re.search(
            r"\b(?:were\s+you\s+(?:able|allowed)\s+to|was\s+there\s+(?:any|a)\s+(?:record|receipt|attempt|call|execution)|"
            r"do\s+your\s+(?:execution\s+|tool\s+|verified\s+)?(?:receipts?|logs?|records?|history)\b|"
            r"check\s+your\s+(?:execution\s+|tool\s+|verified\s+)?(?:receipts?|logs?|records?|history)\b|"
            r"is\s+there\s+a\s+(?:verified\s+|tool\s+|execution\s+)?(?:receipt|record|log)\b|"
            r"according\s+to\s+your\s+(?:execution\s+|tool\s+|verified\s+)?(?:receipts?|logs?|records?|history)\b|"
            r"\b(?:execution|tool|verified)\s+receipts?\b|"
            r"\b(?:write_file|read_file|delete_file|launch_app|run_python|search_web|fetch_url)\b)",
            lower,
        )
        or re.search(
            r"\b(?:was|were)\s+(?:any\s+|the\s+|my\s+|your\s+)?[\w./:\-']+(?:\s+[\w./:\-']+){0,3}\s+"
            r"(?:ever\s+|actually\s+|successfully\s+)?(?:written|saved|created|edited|modified|"
            r"overwritten|read|inspected|deleted|removed|erased|launched|opened|started|"
            r"executed|run|fetched|retrieved|searched|queried|blocked|denied|prevented|completed)\b",
            lower,
        )
        or re.search(
            r"\b(?:what|which|how\s+many|when|why\s+did|can\s+you\s+(?:name|list|confirm|verify|recount|summarize)|"
            r"name\s+(?:the|all)|list\s+(?:the|all)|recount\s+(?:the|all))\b.*"
            r"\b(?:did\s+you|have\s+you|you\s+(?:wrote|written|saved|created|read|inspected|deleted|removed|"
            r"launched|opened|started|ran|executed|fetched|retrieved|searched|queried|tried|attempted|"
            r"used|called|performed|told|said|mentioned|stated)|"
            r"(?:files?|scripts?|documents?|urls?|websites?|queries|tools?|apps?|applications?|commands?|operations?|actions?)\s+"
            r"(?:were|was)\s+(?:written|saved|created|read|inspected|deleted|removed|launched|opened|"
            r"executed|run|fetched|retrieved|searched|blocked|denied|attempted|performed))\b",
            lower,
        )
        or re.search(
            r"\bdid\s+(?:the|your|any)\s+(?:[\w./:\-']+\s+){0,3}"
            r"(?:write|read|delete|deletion|launch|execution|script|fetch|search|call|attempt|"
            r"write_file|read_file|delete_file|launch_app|run_python|search_web|fetch_url)\b.*"
            r"\b(?:succeed|complete|fail|work|go\s+through|run|finish|start|load|get\s+blocked|get\s+denied)\b",
            lower,
        )
        or bool(
            re.search(
                r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|first|second|third|"
                r"fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+days?\s+ago\b|"
                r"\byesterday\b|\bearlier\s+this\s+week\b|\bthis\s+week\b|\blast\s+week\b|"
                r"\bpast\s+(?:\w+\s+)?days?\b|\bten-day\s+history\b",
                lower,
            )
            and re.search(
                r"\b(?:you|your|were|was|wrote|written|saved|read|inspected|deleted|launched|"
                r"opened|executed|ran|fetched|searched|blocked|denied|failed|succeeded|script|python|execution|completed)\b",
                lower,
            )
        )
    )
    has_belief_revision_inquiry = bool(
        (
            re.search(r"\b(?:you|your)\b", lower)
            and re.search(
                r"\b(?:view|views|opinion|opinions|belief|beliefs|stance|preference|preferences|"
                r"choice|choices|thought|thoughts|estimate|estimates|benchmark|benchmarks|"
                r"throughput|prefer|preferred|favour|favor|believe|think|reliable)\b",
                lower,
            )
        )
        or re.search(
            r"\b(?:how\s+(?:has|did)\s+your\s+(?:view|opinion|belief|stance|preference|choice|estimate)|"
            r"what\s+(?:was|is|were)\s+your\s+(?:original|initial|earlier|previous|current|revised|updated|final|first|preferred)\s+"
            r"(?:view|opinion|belief|stance|preference|choice|thought|estimate|throughput|model|format|provider|version)|"
            r"which\s+(?:[\w\-]+\s+){1,4}do\s+you\s+(?:now\s+|currently\s+)?(?:prefer|favour|favor|use|think|believe)|"
            r"which\s+(?:[\w\-]+\s+){1,4}did\s+you\s+(?:originally|initially|previously|first)\s+(?:prefer|favour|favor|think|believe)|"
            r"summarize\s+your\s+(?:current\s+)?(?:preferred|preferences|beliefs|views|choices)|"
            r"trace\s+the\s+full\s+progression\s+of\s+your\s+(?:benchmark|belief|preference|view)|"
            r"before\s+switching\s+to\s+[\w.\-]+,\s*which|before\s+revising\s+your\s+(?:belief|view|preference)|"
            r"when\s+you\s+updated\s+your\s+(?:preference|belief|view)|"
            r"why\s+did\s+you\s+switch\s+(?:away\s+)?from|"
            r"what\s+prompted\s+you\s+to\s+(?:revise|change|update|switch)\s+your)\b",
            lower,
        )
    )
    has_self_history_or_belief = has_past_action_or_receipt_inquiry or has_belief_revision_inquiry

    if (
        _any_term_matches(lower, workspace_words) or has_file_name
    ) and not has_self_history_or_belief:
        substrates.append(_sub().WORKSPACE)
    if has_self_history_or_belief:
        substrates.append(_sub().SELF_HISTORY)
    if (
        _any_term_matches(lower, memory_words)
        or is_private_memory
        or has_personal_fact_inquiry
        or has_self_history_or_belief
    ):
        if _sub().MEMORY not in substrates:
            substrates.append(_sub().MEMORY)
    has_slang_intent = (
        matches_slang_or_world_definition(lower)
        and not has_self_history_or_belief
        and not re.search(self_pattern, lower)
        and not re.search(capability_pattern, lower)
        and not _any_term_matches(lower, temporal_words)
    )
    if (_any_term_matches(lower, web_words) or has_slang_intent) and not has_self_history_or_belief:
        if _sub().WEB not in substrates:
            substrates.append(_sub().WEB)

    is_epistemic = len(substrates) > 0

    # Extract clean normalized topic string
    topic = extract_clean_topic(clean)

    return is_epistemic, substrates, topic
