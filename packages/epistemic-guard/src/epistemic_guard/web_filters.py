"""Domain-agnostic open-web passage hygiene, query-anchor relevance filtering,
syndication/reprint deduplication, and multi-source consensus/dispute primitives.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

_STUB_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:temporarily\s+unavailable|just\s+a\s+moment\.{2,}|checking\s+your\s+browser|"
    r"enable\s+javascript\s+and\s+cookies|access\s+denied|403\s+forbidden|"
    r"404\s+not\s+found|please\s+verify\s+you\s+are\s+a\s+human|ddos\s+protection\s+by)",
    re.IGNORECASE,
)

_TOC_BLURB_ONLY_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}\s*[\u00b7\-:]\s*)?"
    r"(?:this\s+(?:guide|article|post|tutorial|page)\s+(?:covers|explains|walks\s+through|introduces|breaks\s+down)|"
    r"understand(?:ing)?\s+(?:the\s+difference\s+between\s+)?[a-z0-9\s\-]{2,55}\s+(?:through\s+|is\s+important\s+for\b)|"
    r"master\s+the\s+[a-z0-9\s\-]{3,50}\.\s+learn\s+|"
    r"[a-z0-9\s,\-]{5,70}\s+explained\s+for\s+(?:backend\s+|frontend\s+|software\s+)?(?:developers|engineers|beginners))",
    re.IGNORECASE,
)

_LEADING_DATELINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+"
    r"\d{1,2},\s+\d{4}|\d+\s+(?:hours?|days?|minutes?|weeks?|months?)\s+ago)\s*[\u00b7\-\u2013\u2014:]\s*",
    re.IGNORECASE,
)

_MARKDOWN_TAIL_NAV_RE: Final[re.Pattern[str]] = re.compile(
    r"\s+#\s+[^\n#]{2,120}(?:\s+[-\u2013\u2014|]\s+[^\n#]{2,80})?(?:\s+-\s+[^\x00-\x7F\w]+.*)?$"
)

_WIRE_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:"
    r"report\s+from\s+[^\s:]+\s*:\s*"
    r"|\([a-z0-9\s\-]{3,30}\)\s*[\u2014\u2013\-:]+\s*"
    r"|[A-Z][A-Z\s.,']{2,28}(?:\([A-Za-z0-9\s.]+\))?\s*[\u2014\u2013\-]+\s*"
    r"|according\s+to\s+(?:[a-z\-]+\s+){0,4}(?:wire\s+)?(?:reports?|dispatches?|services?)\s*,\s*"
    r")+",
    re.IGNORECASE,
)

_ANCHOR_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "into",
        "onto",
        "upon",
        "over",
        "under",
        "within",
        "between",
        "across",
        "through",
        "during",
        "before",
        "after",
        "around",
        "about",
        "instead",
        "compared",
        "according",
        "versus",
        "vs",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "can",
        "could",
        "would",
        "should",
        "must",
        "may",
        "might",
        "will",
        "shall",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "their",
        "they",
        "them",
        "many",
        "much",
        "any",
        "some",
        "same",
        "other",
        "such",
        "more",
        "most",
        "less",
        "least",
        "very",
        "actually",
        "briefly",
        "traditionally",
        "traditional",
        "officially",
        "official",
        "standard",
        "common",
        "commonly",
        "typical",
        "typically",
        "general",
        "average",
        "maximum",
        "minimum",
        "recommended",
        "require",
        "required",
        "requires",
        "give",
        "gives",
        "given",
        "cause",
        "causes",
        "caused",
        "make",
        "makes",
        "making",
        "use",
        "used",
        "using",
        "considered",
        "preferred",
        "known",
        "called",
        "first",
        "year",
        "years",
        "hours",
        "months",
        "days",
        "age",
        "adult",
        "adults",
        "human",
        "people",
        "value",
        "values",
        "conditions",
        "difference",
        "occurs",
        "occur",
        "studies",
        "trials",
        "guidance",
        "guidelines",
        "rules",
        "article",
        "never",
        "not",
        "than",
    }
)

_GENERIC_MODIFIER_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "modern",
        "classical",
        "full",
        "size",
        "sized",
        "emergency",
        "clinical",
        "medical",
        "daily",
        "oral",
        "safe",
        "safety",
        "serious",
        "acute",
        "healthy",
        "internal",
        "exact",
        "international",
        "national",
        "regulation",
        "system",
        "units",
        "version",
        "core",
        "specification",
        "physical",
        "measurements",
        "household",
        "portable",
        "moderate",
        "active",
        "scientific",
        "scientists",
        "ordinary",
        "state",
        "language",
        "total",
        "type",
        "natural",
        "create",
        "low",
        "high",
        "published",
        "released",
        "introduced",
        "assigned",
        "support",
        "without",
        "effective",
        "treating",
        "prevent",
        "dangers",
        "exposure",
        "inside",
        "immediately",
        "mixed",
        "treated",
        "like",
        "administered",
        "children",
        "evidence",
        "beyond",
    }
)

_DEDUP_STOPWORDS: Final[frozenset[str]] = _ANCHOR_STOPWORDS | frozenset(
    {
        "so",
        "then",
        "also",
        "both",
        "each",
        "every",
        "all",
        "one",
        "single",
        "report",
        "reports",
        "reported",
        "note",
        "notes",
        "say",
        "says",
        "said",
        "explain",
        "explains",
        "show",
        "shows",
        "indicate",
        "indicates",
        "find",
        "finds",
        "found",
        "wire",
        "approximately",
        "roughly",
        "near",
    }
)

_ANSWER_NOISE_TOKENS: Final[frozenset[str]] = _DEDUP_STOPWORDS | frozenset(
    {
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "january",
        "february",
        "march",
        "april",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "wikipedia",
        "org",
        "com",
        "gov",
        "edu",
        "http",
        "https",
        "www",
        "source",
        "page",
        "read",
        "learn",
        "however",
        "although",
        "therefore",
        "because",
    }
)

# General academic non-consensus, contested-science, and folk-belief refutation syntax
EPISTEMIC_CONTROVERSY_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"is\s+a\s+(?:persistent\s+|common\s+|popular\s+|widespread\s+|urban\s+|culinary\s+|medical\s+)?myth\b|"
    r"myth\s+(?:comes\s+from|originat\w+|persists?|that\b|of\s+the\b)|"
    r"persistent\s+myth\b|"
    r"(?:popular|common|widespread|persistent)\s+misconception\w*|"
    r"contrary\s+to\s+(?:popular|common|widespread|viral|conventional|traditional)\s+"
    r"(?:belief|myth|wisdom|claims?|assumptions?|views?)|"
    r"(?:do|does)\s+not\s+actually\s+[a-z]{3,14}\b|"
    r"(?:debunk\w+|hoax\w*|untrue|false\s+claim\w*|fabricat\w+|fallac\w+)\b|"
    r"(?:disput\w+|refut\w+|contradict\w+)\b|"
    r"(?:is|remains?|are|were)\s+(?:widely\s+|hotly\s+|actively\s+|highly\s+|still\s+)?"
    r"(?:controversial|debated|contested|unresolved|unsettled|inconclusive)\b|"
    r"(?:remains?|is\s+still)\s+an?\s+(?:open\s+question|matter\s+of\s+debate|subject\s+of\s+debate|"
    r"active\s+area\s+of\s+debate|unresolved\s+question)\b|"
    r"(?:no|lack\s+of)\s+(?:scientific\s+|clinical\s+|medical\s+|academic\s+|clear\s+|broad\s+|"
    r"universal\s+|general\s+)?consensus\b|"
    r"(?:ongoing|continuing|long-standing|unresolved|active|scientific|academic)\s+"
    r"(?:debate|controversy|disagreement|arguments?)\b|"
    r"the\s+debate\s+(?:is\s+around|centers?\s+on|over|surrounding)\b|"
    r"(?:scientists?|researchers?|astronomers?|experts?|scholars?|clinicians?|historians?|physicists?)\s+"
    r"(?:still\s+|remain\s+|continue\s+to\s+)?(?:disagree|debate|divided)\b|"
    r"disagreement\s+between\b|"
    r"(?:cosmological|hubble(?:\s+constant)?)\s+tension\b|"
    r"(?:competing|rival|opposing)\s+(?:hypotheses|theories|explanations|models|interpretations|"
    r"schools\s+of\s+thought)\b|"
    r"conflicting\s+(?:clinical\s+|scientific\s+|empirical\s+)?(?:evidence|results|studies|trials|"
    r"findings|reports)\b|"
    r"no\s+(?:discernible|convincing|credible|reliable|clinical|good)\s+(?:effect|evidence)\b|"
    r"(?:not\s+enough|lack\s+of|insufficient)\s+(?:[a-z]+\s+)?evidence\b|"
    r"claims?\s+vs\.?\s+evidence\b|"
    r"no\s+evidence\s+(?:that|to\s+support)\b|"
    r"do\s+not\s+support\s+the\s+use\s+of\b|"
    r"failed\s+to\s+(?:show|demonstrate|confirm)\s+(?:any\s+)?(?:benefit|efficacy|prevention)\b|"
    r"efficacy\s+(?:and\s+safety\s+)?(?:of\s+\w+\s+)?(?:is|remains?)\s+(?:uncertain|inconclusive)"
    r")\b",
    re.IGNORECASE,
)

QUERY_CONTROVERSY_INTENT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:scientific\s+debate|disagree\w*|controvers\w*|contested|debated|\btension\b|"
    r"beyond\s+placebo|myth\b|consensus\b)\b",
    re.IGNORECASE,
)

SNIPPET_DISPUTE_CUE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:disput\w*|refut\w*|contradict\w*|debunk\w*|myth\w*|hoax\w*|untrue|"
    r"false\s+claim\w*|misconception\w*|fallac\w*|erroneous\w*|unfounded|"
    r"contrary\s+to\s+(?:popular|common|viral|widespread|blog)|"
    r"(?:is|was|are|were|does|did|do|must|should|can|will)\s+not\b|"
    r"never\s+\w+|contains?\s+no\b|provides?\s+no\b|performs?\s+zero\b|"
    r"sharing\s+no\b|despite\s+popular)\b",
    re.IGNORECASE,
)

PROHIBITIVE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:not|no|never|cannot|can't|can\u2019t|shouldn't|shouldn\u2019t|don't|don\u2019t|"
    r"contraindicat\w*|forbid\w*|avoid\w*|insecure|deprecat\w*|lethal|fatal|toxic)\b",
    re.IGNORECASE,
)

RISK_INCREASE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:increas(?:ed|es|ing)\s+(?:[a-z\-]+\s+){0,3}(?:risk|arrhythmia\w*|mortality|incidence)|"
    r"associated\s+with\s+(?:an?\s+)?(?:increased\s+|higher\s+)?(?:cardiac\s+)?(?:arrhythmia\w*|risk))\b",
    re.IGNORECASE,
)

RISK_DECREASE_OR_SAFE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:(?:less|lower|decreased|reduced)\s+(?:risk\s+of\s+)?(?:cardiac\s+)?arrhythmia\w*|"
    r"safely\s+consume|no\s+need\s+to\s+restrict|does\s+not\s+increase\s+(?:[a-z\-]+\s+){0,2}risk|"
    r"protective\s+against)\b",
    re.IGNORECASE,
)

_COMPOUND_QUERY_SPLIT_RE: Final[re.Pattern[str]] = re.compile(
    r"\band\s+(?=(?:which|what|when|where|who|how|why|in\s+what|under\s+what)\b)",
    re.IGNORECASE,
)

_QUANTITATIVE_QUERY_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:\bhow\s+many\b|\bwithin\s+how\s+many\b|"
    r"\b(?:what|which)\s+(?:is\s+the\s+)?(?:[a-z0-9\-]+\s+){0,6}"
    r"(?:year|temperature|distance|elevation|speed|half[- ]life|payload\s+size|size|port|"
    r"status\s+code|dose|dosage|milligrams|kelvin|fahrenheit|celsius|kilometers|bits|hours)\b|"
    r"\bin\s+what\s+year\b|\bwhen\s+was\b)",
    re.IGNORECASE,
)

_NUMBER_ANSWER_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:\d+(?:[.,]\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"sixteen|twenty|thirty|fifty|hundred|thousand|single|sole|zero|none)\b",
    re.IGNORECASE,
)

_HOW_MANY_HEAD_RE: Final[re.Pattern[str]] = re.compile(
    r"\bhow\s+many\s+(?:total\s+)?([a-z0-9_\-]+(?:\s+(?:and|or)\s+[a-z0-9_\-]+)?(?:\s+[a-z0-9_\-]+){0,2}?)"
    r"(?=\s+(?:are|is|were|was|come|comes|can|could|do|does|did|must|should|exist|exists|have|has|in|on|at|to|for|of)\b|[?,.;]|$)",
    re.IGNORECASE,
)

_DIFF_BETWEEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\bdifference\s+between\s+(.+?)\s+and\s+(.+?)(?:\s+(?:on|in|for|under|within|during|across)\b|[?,.;]|$)",
    re.IGNORECASE,
)

_TAIL_PREPOSITION_ENTITY_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:for|of|on|in|alongside|with|to(?!\s+(?:avoid|prevent|create|make|treat|confirm|verify|support|establish|reduce|increase|ensure)\b))"
    r"\s+(?:a\s+|an\s+|the\s+)?([A-Za-z0-9_\-]+(?:\s+(?:or|and)\s+[A-Za-z0-9_\-]+|\s+[A-Za-z0-9_\-]+){0,4})\s*\??$"
)

_AUTHORITATIVE_SUFFIXES: Final[tuple[str, ...]] = (
    ".gov",
    ".edu",
    ".mil",
    ".gov.uk",
    ".ac.uk",
    ".edu.au",
    ".gov.au",
    ".gc.ca",
    ".int",
)

_AUTHORITATIVE_STANDARDS_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "ietf.org",
        "rfc-editor.org",
        "w3.org",
        "ieee.org",
        "iso.org",
        "unicode.org",
        "whatwg.org",
        "ecmainternational.org",
        "cochrane.org",
    }
)


@dataclass(frozen=True)
class SourceCluster:
    """Canonical representative and member domains of a deduplicated web source cluster."""

    primary_domain: str
    primary_url: str
    primary_combined_text: str
    primary_body_text: str
    member_domains: tuple[str, ...]
    collapsed_duplicates: int


def extract_registrable_domain(url_or_domain: str, idx: int) -> str:
    """Normalize a URL or host string to its registrable eTLD+1 domain."""
    raw = (url_or_domain or "").strip().lower()
    if not raw:
        return f"web_source_{idx}"
    if "://" in raw:
        netloc = urllib.parse.urlsplit(raw).netloc.split(":")[0]
    else:
        netloc = raw.split("/")[0].split(":")[0]
    while netloc.startswith("www."):
        netloc = netloc[4:]
    parts = [p for p in netloc.split(".") if p]
    if len(parts) >= 3 and parts[-2] in {"co", "org", "gov", "ac", "edu"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return netloc or f"web_source_{idx}"


def is_same_registrable_source(dom_a: str, dom_b: str) -> bool:
    """Return True if two host/domain strings resolve to the same registrable publisher."""
    return extract_registrable_domain(dom_a, 0) == extract_registrable_domain(dom_b, 1)


def is_authoritative_domain(domain: str) -> bool:
    """Return True for institutional (`.gov`/`.edu`/`.int`) and formal standards-body domains."""
    d = (domain or "").strip().lower().rstrip(".")
    if not d:
        return False
    if any(d.endswith(sfx) for sfx in _AUTHORITATIVE_SUFFIXES):
        return True
    return any(d == std or d.endswith("." + std) for std in _AUTHORITATIVE_STANDARDS_DOMAINS)


def strip_wire_boilerplate(text: str) -> str:
    """Remove leading wire datelines, agency tags, and `Report from <dom>:` prefixes."""
    cleaned = (text or "").strip()
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _WIRE_PREFIX_RE.sub("", cleaned).strip()
    return cleaned


def clean_scraped_passage(raw_text: str, title: str = "") -> tuple[str, bool]:
    """Clean scraped web prose and detect truncated anti-bot / unavailable / TOC-only stubs."""
    raw = (raw_text or "").strip()
    if not raw:
        return ("", True)

    has_stub = bool(_STUB_MARKER_RE.search(raw))
    cleaned = _STUB_MARKER_RE.sub(" ", raw)
    cleaned = _MARKDOWN_TAIL_NAV_RE.sub("", cleaned)
    cleaned = re.sub(r"#+\s+[^\n.!?]{2,90}(?=\s+#|\s*$)", " ", cleaned)
    cleaned = _LEADING_DATELINE_RE.sub("", cleaned.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return ("", True)

    residual = cleaned
    if title:
        t_clean = re.sub(r"\s+", " ", title).strip()
        if t_clean and residual.lower().startswith(t_clean.lower()):
            residual = residual[len(t_clean) :].strip(" .:-|\u2013\u2014")
            residual = _LEADING_DATELINE_RE.sub("", residual).strip()

    if has_stub and (len(residual) < 90 or residual.endswith("...")):
        return (cleaned, True)

    if _TOC_BLURB_ONLY_RE.search(residual) and len(residual) < 260:
        return (cleaned, True)

    return (cleaned, False)


def extract_anchor_tokens(text: str) -> list[str]:
    norm = text.lower().replace("_", " ").replace("-", " ")
    toks = re.findall(r"[a-z0-9]+", norm)
    out: list[str] = []
    for t in toks:
        if len(t) >= 2 and t not in _ANCHOR_STOPWORDS and t not in out:
            out.append(t)
    return out


def extract_specific_anchors(anchors: Sequence[str]) -> list[str]:
    spec = [a for a in anchors if a not in _GENERIC_MODIFIER_TOKENS]
    return spec if spec else list(anchors)


def stem_match(anchor: str, doc_tokens: set[str], doc_stems: set[str]) -> bool:
    if anchor in doc_tokens or f"{anchor}s" in doc_tokens or f"{anchor}es" in doc_tokens:
        return True
    if anchor.endswith("s") and len(anchor) >= 4 and anchor[:-1] in doc_tokens:
        return True
    return len(anchor) >= 5 and anchor[:5] in doc_stems


def passage_has_answer_number(text: str, query_text: str) -> bool:
    stripped = _LEADING_DATELINE_RE.sub("", text)
    q_nums = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", query_text))
    for m in _NUMBER_ANSWER_TOKEN_RE.finditer(stripped):
        tok = m.group(0).lower()
        if tok in q_nums:
            continue
        if re.fullmatch(r"20(?:19|2[0-9])", tok) and not re.search(
            r"\b(?:when\s+was|what\s+year|which\s+year)\b", query_text, re.IGNORECASE
        ):
            continue
        return True
    return False


def select_best_query_sentences(passage: str, query_text: str, top_k: int = 2) -> list[str]:
    """Select up to `top_k` clean sentences from `passage` best aligned with `query_text`."""
    cleaned, _ = clean_scraped_passage(passage)
    if not cleaned:
        return []
    anchors = extract_anchor_tokens(query_text)
    spec_anchors = set(extract_specific_anchors(anchors))
    anchor_set = set(anchors)
    raw_sents = [
        _LEADING_DATELINE_RE.sub("", s.strip()).strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", cleaned)
        if 12 <= len(s.strip()) <= 480 and not s.strip().startswith("#")
    ]
    if not raw_sents:
        return [cleaned[:360]]

    scored: list[tuple[float, int, str]] = []
    for idx, sent in enumerate(raw_sents):
        s_toks = set(re.findall(r"[a-z0-9]+", sent.lower()))
        s_stems = {t[:5] for t in s_toks if len(t) >= 5}
        spec_hits = sum(1 for a in spec_anchors if stem_match(a, s_toks, s_stems))
        gen_hits = sum(1 for a in (anchor_set - spec_anchors) if stem_match(a, s_toks, s_stems))
        has_controversy = (
            0.75 if (spec_hits >= 1 and EPISTEMIC_CONTROVERSY_RE.search(sent)) else 0.0
        )
        has_digit = 0.45 if passage_has_answer_number(sent, query_text) else 0.0
        score = (1.6 * float(spec_hits)) + (0.6 * float(gen_hits)) + has_controversy + has_digit
        scored.append((score, -idx, sent))

    scored.sort(reverse=True)
    chosen = [item[2] for item in scored[:top_k] if item[0] > 0]
    return chosen if chosen else [raw_sents[0]]


def _content_tokens(text: str, exclude: frozenset[str]) -> list[str]:
    stripped = strip_wire_boilerplate(text).lower()
    raw_toks = re.findall(r"[a-z0-9]+", stripped)
    return [t for t in raw_toks if len(t) >= 2 and t not in _DEDUP_STOPWORDS and t not in exclude]


def _simhash64(tokens: Sequence[str], shingle_size: int = 2) -> int:
    if not tokens:
        return 0
    grams = (
        [tuple(tokens)]
        if len(tokens) < shingle_size
        else [tuple(tokens[i : i + shingle_size]) for i in range(len(tokens) - shingle_size + 1)]
    )
    acc = [0] * 64
    for g in grams:
        digest = hashlib.blake2b(" ".join(g).encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        for bit in range(64):
            acc[bit] += 1 if ((h >> bit) & 1) else -1
    out = 0
    for bit in range(64):
        if acc[bit] > 0:
            out |= 1 << bit
    return out


def _shingle_jaccard(
    toks_a: Sequence[str], toks_b: Sequence[str], k: int = 3
) -> tuple[float, int]:
    if len(toks_a) < k or len(toks_b) < k:
        return 0.0, 0
    sh_a = {tuple(toks_a[i : i + k]) for i in range(len(toks_a) - k + 1)}
    sh_b = {tuple(toks_b[i : i + k]) for i in range(len(toks_b) - k + 1)}
    inter = len(sh_a & sh_b)
    union = len(sh_a | sh_b)
    return ((inter / union) if union else 0.0), inter


def are_texts_near_duplicate(
    text_a: str,
    text_b: str,
    query_or_claim: str = "",
    *,
    contradiction_fn: Callable[[str, str], float] | None = None,
) -> bool:
    """Return True if two passages represent verbatim or lightly edited syndicated copies."""
    q_exclude = frozenset(re.findall(r"[a-z0-9]+", (query_or_claim or "").lower()))
    norm_a = " ".join(re.findall(r"[a-z0-9]+", strip_wire_boilerplate(text_a).lower()))
    norm_b = " ".join(re.findall(r"[a-z0-9]+", strip_wire_boilerplate(text_b).lower()))
    if not norm_a or not norm_b:
        return False

    toks_a = _content_tokens(text_a, q_exclude)
    toks_b = _content_tokens(text_b, q_exclude)
    if norm_a == norm_b and len(toks_a) >= 4:
        return True

    set_a = set(toks_a)
    set_b = set(toks_b)
    stems_a = {t[:5] for t in toks_a}
    stems_b = {t[:5] for t in toks_b}
    shared = len(set_a & set_b)
    shared_stems = len(stems_a & stems_b)
    if len(stems_a) < 6 or len(stems_b) < 6 or shared_stems < 6:
        return False

    cue_a = bool(SNIPPET_DISPUTE_CUE_RE.search(text_a))
    cue_b = bool(SNIPPET_DISPUTE_CUE_RE.search(text_b))
    if cue_a != cue_b:
        if contradiction_fn is not None and contradiction_fn(text_a, text_b) >= 0.85:
            return False
        if contradiction_fn is None:
            return False

    union = len(set_a | set_b)
    token_jaccard = shared / union if union else 0.0
    stem_union = len(stems_a | stems_b)
    stem_jaccard = shared_stems / stem_union if stem_union else 0.0
    containment = shared_stems / min(len(stems_a), len(stems_b))
    sh3_jacc, sh3_shared = _shingle_jaccard(toks_a, toks_b, k=3)

    if token_jaccard >= 0.45 or stem_jaccard >= 0.44 or containment >= 0.64:
        return True
    if sh3_jacc >= 0.25 and sh3_shared >= 3:
        return True
    if len(toks_a) >= 8 and len(toks_b) >= 8 and shared >= 6:
        if (_simhash64(toks_a, 2) ^ _simhash64(toks_b, 2)).bit_count() <= 12:
            return True
    return False


def shares_verbatim_long_span(text_a: str, text_b: str, span_words: int = 11) -> bool:
    """Return True if two scraped pages share an exact `span_words`-token verbatim reprint."""
    toks_a = re.findall(r"[a-z0-9]+", strip_wire_boilerplate(text_a).lower())
    toks_b = re.findall(r"[a-z0-9]+", strip_wire_boilerplate(text_b).lower())
    if len(toks_a) < span_words or len(toks_b) < span_words:
        return False
    grams_a = {tuple(toks_a[i : i + span_words]) for i in range(len(toks_a) - span_words + 1)}
    return any(
        tuple(toks_b[j : j + span_words]) in grams_a for j in range(len(toks_b) - span_words + 1)
    )


def cluster_near_duplicate_sources(
    raw_items: Sequence[tuple[str, str, str, str]],
    query_text: str,
    *,
    contradiction_fn: Callable[[str, str], float] | None = None,
) -> tuple[list[SourceCluster], int]:
    """Cluster `(domain, url, combined_text, body_text)` items into distinct publisher clusters."""
    clusters: list[SourceCluster] = []
    collapsed_total = 0

    for dom, url, combined, body in raw_items:
        matched_idx: int | None = None
        for idx, cl in enumerate(clusters):
            if any(is_same_registrable_source(dom, m) for m in cl.member_domains):
                matched_idx = idx
                break
            if are_texts_near_duplicate(
                body, cl.primary_body_text, query_text, contradiction_fn=contradiction_fn
            ):
                matched_idx = idx
                break
        if matched_idx is not None:
            old = clusters[matched_idx]
            new_members = (
                old.member_domains if dom in old.member_domains else (*old.member_domains, dom)
            )
            clusters[matched_idx] = SourceCluster(
                primary_domain=old.primary_domain,
                primary_url=old.primary_url,
                primary_combined_text=old.primary_combined_text,
                primary_body_text=old.primary_body_text,
                member_domains=new_members,
                collapsed_duplicates=old.collapsed_duplicates + 1,
            )
            collapsed_total += 1
        else:
            clusters.append(
                SourceCluster(
                    primary_domain=dom,
                    primary_url=url,
                    primary_combined_text=combined,
                    primary_body_text=body,
                    member_domains=(dom,),
                    collapsed_duplicates=0,
                )
            )

    clusters.sort(key=lambda cl: 0 if is_authoritative_domain(cl.primary_domain) else 1)
    return clusters, collapsed_total


def filter_relevant_open_web_sources(
    query_text: str,
    raw_items_with_body: Sequence[tuple[str, str, str, str]],
    *,
    neural_stance_fn: Callable[[str, str], tuple[str, float]] | None = None,
) -> tuple[list[tuple[str, str, str, str]], list[tuple[str, float]]]:
    """Filter stubs, TOC blurbs, and off-topic hits; return `(kept_items, dropped_domains)`."""
    if not raw_items_with_body:
        return ([], [])

    anchors = extract_anchor_tokens(query_text)
    spec_anchors = extract_specific_anchors(anchors)
    sub_clauses = [c.strip() for c in _COMPOUND_QUERY_SPLIT_RE.split(query_text) if c.strip()]
    clause_anchor_sets: list[list[str]] = (
        [extract_specific_anchors(extract_anchor_tokens(c)) for c in sub_clauses]
        if len(sub_clauses) >= 2
        else []
    )

    is_quant_query = bool(_QUANTITATIVE_QUERY_RE.search(query_text))
    hm_match = _HOW_MANY_HEAD_RE.search(query_text)
    how_many_heads: list[str] = (
        extract_specific_anchors(extract_anchor_tokens(hm_match.group(1))) if hm_match else []
    )

    has_tech_identifier = any(
        any(c.isupper() for c in rw[1:]) or "_" in rw or any(c.isdigit() for c in rw)
        for rw in query_text.split()
    )
    q_words_raw = re.findall(r"[A-Za-z][A-Za-z0-9\-]*", query_text)
    proper_nouns: list[str] = []
    if not has_tech_identifier:
        for wi, w in enumerate(q_words_raw):
            wl = w.lower()
            if (
                wi > 0
                and w[0].isupper()
                and w[1:].islower()
                and len(wl) >= 4
                and wl not in _ANCHOR_STOPWORDS
                and wl not in _GENERIC_MODIFIER_TOKENS
                and wl not in proper_nouns
            ):
                proper_nouns.append(wl)

    diff_match = _DIFF_BETWEEN_RE.search(query_text)
    diff_pair: tuple[list[str], list[str]] | None = None
    if diff_match:
        lhs = extract_specific_anchors(extract_anchor_tokens(diff_match.group(1)))
        rhs = extract_specific_anchors(extract_anchor_tokens(diff_match.group(2)))
        rhs_only = [t for t in rhs if t not in lhs] or rhs
        lhs_only = [t for t in lhs if t not in rhs] or lhs
        if lhs_only and rhs_only:
            diff_pair = (lhs_only, rhs_only)

    query_no_purpose = re.sub(
        r"\s+to\s+(?:avoid|prevent|create|make|treat|confirm|verify|support|establish|reduce|increase|ensure)\b.*$",
        "",
        query_text.strip(),
        flags=re.IGNORECASE,
    )
    tail_match = _TAIL_PREPOSITION_ENTITY_RE.search(query_no_purpose)
    tail_spec_tokens: list[str] = []
    tail_has_or = False
    if tail_match:
        raw_tail = tail_match.group(1)
        tail_has_or = " or " in raw_tail.lower()
        pre_tail = set(extract_anchor_tokens(query_no_purpose[: tail_match.start()]))
        raw_tail_spec = [
            t for t in extract_anchor_tokens(raw_tail) if t not in _GENERIC_MODIFIER_TOKENS
        ]
        tail_spec_tokens = [t for t in raw_tail_spec if t not in pre_tail]

    kept: list[tuple[str, str, str, str]] = []
    dropped: list[tuple[str, float]] = []

    for dom, url, combined, body in raw_items_with_body:
        title_guess = combined.split(". ", 1)[0] if ". " in combined else ""
        clean_comb, is_stub_comb = clean_scraped_passage(combined, title=title_guess)
        clean_body, is_stub_body = clean_scraped_passage(body, title=title_guess)
        if is_stub_body or is_stub_comb:
            dropped.append((dom, 0.95))
            continue
        eff_text = clean_comb or clean_body
        if not eff_text:
            dropped.append((dom, 0.95))
            continue

        doc_toks = set(re.findall(r"[a-z0-9]+", eff_text.lower()))
        doc_stems = {t[:5] for t in doc_toks if len(t) >= 5}
        body_text_eff = clean_body or eff_text
        body_toks = set(re.findall(r"[a-z0-9]+", body_text_eff.lower()))
        body_stems = {t[:5] for t in body_toks if len(t) >= 5}

        non_q_toks = [
            t
            for t in body_toks
            if (len(t) >= 3 or t.isdigit()) and t not in _ANSWER_NOISE_TOKENS and t not in anchors
        ]
        if len(non_q_toks) < 3:
            dropped.append((dom, 0.90))
            continue

        if proper_nouns and len(proper_nouns) <= 3 and " or " not in query_text.lower():
            if sum(1 for pn in proper_nouns if stem_match(pn, doc_toks, doc_stems)) == 0:
                dropped.append((dom, 0.90))
                continue

        if len(clause_anchor_sets) >= 2:
            c1_anchors, c2_anchors = clause_anchor_sets[0], clause_anchor_sets[1]
            c2_specific = [a for a in c2_anchors if a not in c1_anchors]
            if c1_anchors and c2_specific:
                c1_ok = any(stem_match(a, body_toks, body_stems) for a in c1_anchors)
                c2_ok = any(stem_match(a, body_toks, body_stems) for a in c2_specific)
                if not (c1_ok and c2_ok):
                    dropped.append((dom, 0.88))
                    continue

        if diff_pair is not None:
            lhs_toks, rhs_toks = diff_pair
            if not (
                any(stem_match(a, body_toks, body_stems) for a in lhs_toks)
                and any(stem_match(b, body_toks, body_stems) for b in rhs_toks)
            ):
                dropped.append((dom, 0.90))
                continue

        if tail_spec_tokens:
            if tail_has_or or len(tail_spec_tokens) >= 3:
                if not any(stem_match(t, body_toks, body_stems) for t in tail_spec_tokens):
                    dropped.append((dom, 0.88))
                    continue
            elif not all(stem_match(t, body_toks, body_stems) for t in tail_spec_tokens):
                dropped.append((dom, 0.88))
                continue

        if how_many_heads:
            req_hm = [how_many_heads[-1]]
            if not all(stem_match(h, body_toks, body_stems) for h in req_hm):
                dropped.append((dom, 0.88))
                continue
            body_sents = [
                s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", body_text_eff) if s.strip()
            ]
            has_counted = any(
                all(
                    stem_match(
                        h,
                        set(re.findall(r"[a-z0-9]+", bs.lower())),
                        {t[:5] for t in re.findall(r"[a-z0-9]+", bs.lower()) if len(t) >= 5},
                    )
                    for h in req_hm
                )
                and bool(_NUMBER_ANSWER_TOKEN_RE.search(_LEADING_DATELINE_RE.sub("", bs)))
                for bs in body_sents
            )
            if not has_counted:
                dropped.append((dom, 0.88))
                continue

        if is_quant_query and not passage_has_answer_number(body_text_eff, query_text):
            dropped.append((dom, 0.88))
            continue

        if spec_anchors:
            spec_hits = sum(1 for a in spec_anchors if stem_match(a, doc_toks, doc_stems))
            spec_recall = spec_hits / len(spec_anchors)
        else:
            spec_hits = 1
            spec_recall = 1.0

        if len(spec_anchors) == 2 and " or " not in query_text.lower() and spec_hits < 2:
            dropped.append((dom, 0.85))
            continue
        if spec_recall < 0.34:
            dropped.append((dom, 0.85))
            continue

        if neural_stance_fn is not None:
            best_sents = select_best_query_sentences(eff_text, query_text, top_k=2)
            probe = " ".join(best_sents) if best_sents else eff_text[:360]
            stance, conf = neural_stance_fn(query_text, probe)
            if stance == "IRRELEVANT" and conf >= 0.88 and spec_recall < 0.67:
                dropped.append((dom, conf))
                continue
            if spec_recall < 0.50 and stance == "IRRELEVANT" and conf >= 0.55:
                dropped.append((dom, conf))
                continue
        elif spec_recall < 0.50 and spec_hits < 2:
            dropped.append((dom, 0.80))
            continue

        kept.append((dom, url, eff_text, clean_body or eff_text))

    return kept, dropped


def extract_answer_signature(sent: str, query_anchors: set[str]) -> set[str]:
    toks = re.findall(r"[a-z0-9]+", strip_wire_boilerplate(sent).lower())
    sig: set[str] = set()
    for t in toks:
        if t in _ANSWER_NOISE_TOKENS or t in query_anchors:
            continue
        if re.fullmatch(r"20(?:19|2[0-9])", t):
            continue
        if len(t) >= 4 or t.isdigit():
            sig.add(t[:6] if len(t) >= 6 and t.isalpha() else t)
    return sig


def detect_conflicting_single_value_numbers(
    query_text: str,
    all_relevant_items: Sequence[tuple[str, str, str, str]],
) -> list[str]:
    """Detect conflicting years or measurements on single-value factual queries."""
    if len(all_relevant_items) < 2:
        return []
    q_lower = query_text.lower()
    asks_year = bool(re.search(r"\b(?:what\s+year|which\s+year|in\s+what\s+year)\b", q_lower))
    asks_elev = bool(re.search(r"\b(?:orthometric\s+)?elevation\s+of\b", q_lower))
    if not (asks_year or asks_elev):
        return []

    q_nums = set(re.findall(r"\b\d{4}\b", query_text))
    per_item_vals: list[tuple[str, str, set[str]]] = []
    for dom, url, comb, _body in all_relevant_items:
        focus = " ".join(select_best_query_sentences(comb, query_text, top_k=2))
        if asks_year:
            years = {
                y for y in re.findall(r"\b(1[5-9]\d{2}|20[01]\d)\b", focus) if y not in q_nums
            }
            if years:
                per_item_vals.append((dom, url, years))
        elif asks_elev:
            elevs = {
                m.replace(",", "")
                for m in re.findall(r"\b(\d{1,2},\d{3})\s*(?:ft|feet)\b", comb, re.IGNORECASE)
            }
            if elevs:
                per_item_vals.append((dom, url, elevs))

    if len(per_item_vals) < 2:
        return []
    _base_dom, base_url, base_vals = per_item_vals[0]
    conflicting: list[str] = []
    for dom, url, vals in per_item_vals[1:]:
        if url != base_url and vals and base_vals and vals.isdisjoint(base_vals):
            if dom not in conflicting:
                conflicting.append(dom)
    return conflicting


def has_unanimous_decimal_measurement(
    query_text: str,
    all_relevant_items: Sequence[tuple[str, str, str, str]],
) -> bool:
    if not re.search(
        r"\b(?:official|exact)\s+[a-z\-\s]{0,30}\b(?:distance|speed|temperature)\b",
        query_text,
        re.IGNORECASE,
    ):
        return False
    dec_per_src = [
        set(re.findall(r"\b\d+\.\d+\b", comb))
        for _d, _u, comb, _b in all_relevant_items
        if re.findall(r"\b\d+\.\d+\b", comb)
    ]
    return len(dec_per_src) >= 2 and bool(set.intersection(*dec_per_src))
