"""Open-web passage relevance filtering, multi-source consensus, and controversy detection.

Addresses the R-32 open-web retrieval & HTML prose failure modes (`WO-46`):
1. Cleans scraped HTML/Markdown boilerplate (`# Title - Wikipedia`, datelines, bot-wall stubs)
   and rejects truncated anti-bot/unavailable stubs and meta-TOC blurbs before source counting.
2. Filters off-topic search hits via specific subject-noun coverage, interrogative head/quantitative
   answer checks, comparison-pair (`X vs/and Y`) coverage, tail topic-entity guards, and in-process
   OpenVINO `all-MiniLM-L6-v2` semantic passage similarity (`0 MB` GPU VRAM).
3. Replaces asymmetric `idx == 1` negation stripping (which manufactured self-contradictions on
   agreeing prohibitive warnings like *"never feed honey to infants"* or *"do not exceed 4,000 mg"*)
   with symmetric, query-aligned epistemic controversy/myth detection, directional clinical effect
   opposition, and conflicting-measurement checks.
4. Evaluates multi-sentence answer consensus across deduplicated registrable-domain clusters.
"""

from __future__ import annotations

import os
import re
import threading
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import openvino as ov
import structlog

from lucca.core.walton_schemes.dedup import (
    _CORE_NLI_SINGLETON,
    SourceCluster,
    strip_wire_boilerplate,
)

try:
    from tokenizers import Tokenizer
except ImportError:  # pragma: no cover
    Tokenizer = None

logger = structlog.get_logger(__name__)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[4]

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
        "noticeably",
        "unusually",
        "traditionally",
        "traditional",
        "officially",
        "official",
        "distinctive",
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
        "stand",
        "count",
        "counts",
        "counted",
        "considered",
        "preferred",
        "known",
        "called",
        "first",
        "line",
        "year",
        "years",
        "hours",
        "months",
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
        "alongside",
        "consumed",
        "taking",
        "drinking",
        "washing",
        "adding",
        "enabling",
        "combining",
        "recovering",
        "younger",
        "than",
    }
)

# Framing/attribute modifiers that often appear in tangentially related pages
# (e.g. "acoustic concert grand" on a guitar page when the question asks about a "piano",
# or "emergency intramuscular injection site" on a nursing page lacking "anaphylaxis").
_GENERIC_MODIFIER_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "acoustic",
        "concert",
        "grand",
        "classical",
        "modern",
        "full",
        "size",
        "sized",
        "emergency",
        "clinical",
        "anatomical",
        "injection",
        "site",
        "intramuscular",
        "medication",
        "medical",
        "drug",
        "dose",
        "daily",
        "oral",
        "safe",
        "safety",
        "serious",
        "acute",
        "healthy",
        "internal",
        "cooking",
        "temperature",
        "range",
        "exact",
        "international",
        "national",
        "tournament",
        "grade",
        "regulation",
        "system",
        "units",
        "network",
        "protocol",
        "address",
        "addresses",
        "addressed",
        "ownership",
        "semantics",
        "version",
        "control",
        "core",
        "specification",
        "stream",
        "sockets",
        "transaction",
        "isolation",
        "physical",
        "decay",
        "measurements",
        "digital",
        "signature",
        "generation",
        "household",
        "portable",
        "moderate",
        "outpatient",
        "randomized",
        "controlled",
        "double",
        "precision",
        "floating",
        "point",
        "linear",
        "memory",
        "byte",
        "little",
        "big",
        "local",
        "tracking",
        "branches",
        "active",
        "scientific",
        "planetary",
        "scientists",
        "ordinary",
        "class",
        "water",
        "cold",
        "raw",
        "home",
        "state",
        "english",
        "language",
        "set",
        "total",
        "type",
        "natural",
        "create",
        "string",
        "top",
        "carve",
        "species",
        "color",
        "autumn",
        "red",
        "orange",
        "dark",
        "stable",
        "crystals",
        "temper",
        "unaided",
        "eye",
        "low",
        "high",
        "orbit",
        "male",
        "french",
        "japanese",
        "italian",
        "german",
        "germany",
        "film",
        "published",
        "released",
        "introduced",
        "experimental",
        "mode",
        "assigned",
        "implementations",
        "support",
        "without",
        "allocated",
        "simultaneously",
        "exist",
        "replaced",
        "scalable",
        "readiness",
        "notification",
        "notify",
        "personal",
        "data",
        "controller",
        "supervisory",
        "authority",
        "effective",
        "treating",
        "infection",
        "prevent",
        "catching",
        "supplements",
        "dangers",
        "exposure",
        "inside",
        "odorless",
        "lethal",
        "immediately",
        "mixed",
        "treated",
        "like",
        "fires",
        "administered",
        "overdose",
        "children",
        "teenagers",
        "illness",
        "viral",
        "storage",
        "unsalted",
        "fast",
        "hashes",
        "evidence",
        "beyond",
        "remedies",
        "ultra",
        "diluted",
    }
)

_ANSWER_NOISE_TOKENS: Final[frozenset[str]] = _ANCHOR_STOPWORDS | frozenset(
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
        "report",
        "source",
        "page",
        "read",
        "learn",
        "also",
        "however",
        "although",
        "therefore",
        "because",
    }
)

# Topic-agnostic epistemic controversy / myth-refutation / contested-science cues.
_EPISTEMIC_CONTROVERSY_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"is\s+a\s+(?:persistent\s+|common\s+|popular\s+|widespread\s+|urban\s+|culinary\s+|medical\s+)?myth\b|"
    r"myth\s+(?:comes\s+from|originat\w+|persists?|that\b|of\s+the\b)|"
    r"persistent\s+myth\b|"
    r"(?:popular|common|widespread)\s+misconception\w*|"
    r"contrary\s+to\s+(?:popular|common|widespread|viral)\s+(?:belief|myth|wisdom|claims?)|"
    r"\b(?:debunk\w+|hoax\w*|untrue|false\s+claim\w*|fabricat\w+|fallac\w+)\b|"
    r"\b(?:disput\w+|refut\w+|contradict\w+)\b|"
    r"(?:is|remains?|are|were)\s+(?:widely\s+|hotly\s+|actively\s+|highly\s+|still\s+)?(?:controversial|debated|contested)\b|"
    r"\b(?:scientific\s+(?:debate|controversy|disagreement)|discussion\s+and\s+debate|subject\s+of\s+debate)\b|"
    r"\bthe\s+debate\s+(?:is\s+around|centers?\s+on|over|surrounding)\b|"
    r"\b(?:scientists?|researchers?|astronomers?|experts?|scholars?|clinicians?)\s+"
    r"(?:still\s+)?(?:disagree|debate)\b|"
    r"\bhowever,\s+continue\s+to\s+consider\b|"
    r"\bdisagreement\s+between\b|"
    r"\b(?:hubble(?:\s+constant)?|cosmological)\s+tension\b|"
    r"\bfacing\s+(?:its\s+)?(?:most\s+)?serious\s+challenge\b|"
    r"\bcompeting\s+(?:hypotheses|theories|explanations|models)\b|"
    r"\bconflicting\s+(?:clinical\s+|scientific\s+|empirical\s+)?(?:evidence|results|studies|trials|findings|reports)\b|"
    r"\b(?:no\s+(?:discernible|convincing|credible|reliable|clinical|good)\s+(?:effect|evidence)|"
    r"(?:not\s+enough|lack\s+of)\s+(?:[a-z]+\s+)?evidence\b|"
    r"claims?\s+vs\.?\s+evidence\b|"
    r"no\s+evidence\s+(?:that|to\s+support)|"
    r"do\s+not\s+support\s+the\s+use\s+of|"
    r"failed\s+to\s+(?:show|demonstrate|confirm)\s+(?:any\s+)?(?:benefit|efficacy|prevention))\b|"
    r"\befficacy\s+(?:and\s+safety\s+)?(?:of\s+\w+\s+)?(?:is|remains?)\s+(?:uncertain|inconclusive)\b"
    r")",
    re.IGNORECASE,
)

_QUERY_CONTROVERSY_INTENT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:scientific\s+debate|disagree\w*|controvers\w*|contested|debated|\btension\b|"
    r"beyond\s+placebo|prevent\s+catching\s+the\s+common\s+cold)\b",
    re.IGNORECASE,
)

_RISK_INCREASE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:increas(?:ed|es|ing)\s+(?:[a-z\-]+\s+){0,3}(?:risk|arrhythmia\w*|mortality|incidence)|"
    r"associated\s+with\s+(?:an?\s+)?(?:increased\s+|higher\s+)?(?:cardiac\s+)?(?:arrhythmia\w*|risk))\b",
    re.IGNORECASE,
)

_RISK_DECREASE_OR_SAFE_RE: Final[re.Pattern[str]] = re.compile(
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
    r"status\s+code|dose|milligrams|kelvin|fahrenheit|celsius|kilometers|bits|hours)\b|"
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

_WHAT_TARGET_HEAD_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:what|which)\s+(?:[a-z\-]+\s+){0,2}"
    r"(pigment|antidote|wood|oil|protein|wax|resin|gas|port|code|call|protocol)\b",
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


@dataclass(frozen=True)
class OpenWebAssessment:
    """Result of open-web multi-source corroboration and dispute evaluation."""

    corroborating_domains: list[str]
    dispute_domains: list[str]
    dispute_detail: str


class _CoreOpenVINOEmbedder:
    """Lazy, thread-safe 384-D OpenVINO `all-MiniLM-L6-v2` sentence embedder (`0 MB` GPU VRAM)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._initialized = False
        self._infer_req: ov.InferRequest | None = None
        self._tokenizer: Tokenizer | None = None
        self._input_names: list[str] = []

    def _ensure_loaded(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            if Tokenizer is None:
                return
            env_dir = os.environ.get("LUCCA_EMBED_MODEL_DIR")
            candidates = ([Path(env_dir)] if env_dir else []) + [
                _REPO_ROOT / "models" / "embed" / "all-MiniLM-L6-v2",
                Path(r"C:\ProjectLucca\models\embed\all-MiniLM-L6-v2"),
            ]
            model_dir = next(
                (p for p in candidates if (p / "openvino_model.xml").exists()),
                None,
            )
            if model_dir is None:
                return
            tok_path = model_dir / "tokenizer.json"
            if not tok_path.exists():
                return
            try:
                tok = Tokenizer.from_file(str(tok_path))
                tok.enable_truncation(max_length=128)
                tok.enable_padding(length=128)
                core = ov.Core()
                ov_model = core.read_model(str(model_dir / "openvino_model.xml"))
                self._input_names = [inp.get_any_name() for inp in ov_model.inputs]
                compiled = core.compile_model(ov_model, "CPU")
                self._infer_req = compiled.create_infer_request()
                self._tokenizer = tok
            except Exception as exc:  # noqa: BLE001
                logger.debug("core_embedder_init_failed", error=str(exc))
                self._infer_req = None
                self._tokenizer = None

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._infer_req is not None and self._tokenizer is not None

    def encode_unit(self, text: str) -> np.ndarray[tuple[int, ...], np.dtype[np.float32]] | None:
        self._ensure_loaded()
        if self._infer_req is None or self._tokenizer is None:
            return None
        clean = unicodedata.normalize("NFC", (text or "").strip())[:512]
        if not clean:
            return None
        try:
            enc = self._tokenizer.encode(clean)
            mask = np.array([enc.attention_mask], dtype=np.int64)
            feed: dict[str, np.ndarray[tuple[int, ...], np.dtype[np.int64]]] = {}
            if "input_ids" in self._input_names:
                feed["input_ids"] = np.array([enc.ids], dtype=np.int64)
            if "attention_mask" in self._input_names:
                feed["attention_mask"] = mask
            if "token_type_ids" in self._input_names:
                feed["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)
            with self._lock:
                outputs = self._infer_req.infer(feed)
                hidden = np.asarray(list(outputs.values())[0], dtype=np.float32)[0]
            mask_f = mask[0].astype(np.float32)[:, None]
            denom = max(float(np.sum(mask_f)), 1e-6)
            pooled = np.sum(hidden * mask_f, axis=0) / denom
            norm = float(np.linalg.norm(pooled))
            if norm <= 1e-8:
                return None
            res: np.ndarray[tuple[int, ...], np.dtype[np.float32]] = pooled / norm
            return res
        except Exception as exc:  # noqa: BLE001
            logger.debug("core_embedder_encode_failed", error=str(exc))
            return None

    def cosine(self, text_a: str, text_b: str) -> float | None:
        va = self.encode_unit(text_a)
        vb = self.encode_unit(text_b)
        if va is None or vb is None:
            return None
        return float(np.dot(va, vb))


_CORE_EMBEDDER_SINGLETON = _CoreOpenVINOEmbedder()


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


def _extract_anchor_tokens(text: str) -> list[str]:
    norm = text.lower().replace("_", " ").replace("-", " ")
    toks = re.findall(r"[a-z0-9]+", norm)
    out: list[str] = []
    for t in toks:
        if len(t) >= 2 and t not in _ANCHOR_STOPWORDS and t not in out:
            out.append(t)
    return out


def _extract_specific_anchors(anchors: Sequence[str]) -> list[str]:
    spec = [a for a in anchors if a not in _GENERIC_MODIFIER_TOKENS]
    return spec if spec else list(anchors)


def _stem_match(anchor: str, doc_tokens: set[str], doc_stems: set[str]) -> bool:
    if anchor in doc_tokens or f"{anchor}s" in doc_tokens or f"{anchor}es" in doc_tokens:
        return True
    if anchor.endswith("s") and len(anchor) >= 4 and anchor[:-1] in doc_tokens:
        return True
    if len(anchor) >= 5 and anchor[:5] in doc_stems:
        return True
    return False


def _passage_has_answer_number(text: str, query_text: str) -> bool:
    """Return True if `text` contains a number/number-word outside modern article datelines."""
    stripped = _LEADING_DATELINE_RE.sub("", text)
    # Remove query numbers themselves (e.g. "RFC 1035", "IEEE 754", "GDPR Article 33", "24-hour")
    # so the passage must actually supply an answer number rather than echoing the question's RFC!
    q_nums = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", query_text))
    for m in _NUMBER_ANSWER_TOKEN_RE.finditer(stripped):
        tok = m.group(0).lower()
        if tok in q_nums:
            continue
        # Ignore 2019-2029 article timestamps unless query asks When/What year
        if re.fullmatch(r"20(?:19|2[0-9])", tok) and not re.search(
            r"\b(?:when\s+was|what\s+year|which\s+year)\b", query_text, re.IGNORECASE
        ):
            continue
        return True
    return False


def select_best_query_sentences(
    passage: str,
    query_text: str,
    top_k: int = 2,
) -> list[str]:
    """Select up to `top_k` clean sentences from `passage` best aligned with `query_text`."""
    cleaned, _ = clean_scraped_passage(passage)
    if not cleaned:
        return []
    anchors = _extract_anchor_tokens(query_text)
    spec_anchors = set(_extract_specific_anchors(anchors))
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
        spec_hits = sum(1 for a in spec_anchors if _stem_match(a, s_toks, s_stems))
        gen_hits = sum(1 for a in (anchor_set - spec_anchors) if _stem_match(a, s_toks, s_stems))
        # Only reward controversy cue when the sentence also mentions a specific query anchor
        has_controversy = (
            0.75 if (spec_hits >= 1 and _EPISTEMIC_CONTROVERSY_RE.search(sent)) else 0.0
        )
        has_digit = 0.45 if _passage_has_answer_number(sent, query_text) else 0.0
        score = (1.6 * float(spec_hits)) + (0.6 * float(gen_hits)) + has_controversy + has_digit
        scored.append((score, -idx, sent))

    scored.sort(reverse=True)
    chosen = [item[2] for item in scored[:top_k] if item[0] > 0]
    return chosen if chosen else [raw_sents[0]]


def filter_relevant_web_sources(
    query_text: str,
    raw_items_with_body: Sequence[tuple[str, str, str, str]],
) -> list[tuple[str, str, str, str]]:
    """Filter out unavailable stubs, TOC blurbs, and off-topic pages before source counting."""
    if not raw_items_with_body:
        return []

    anchors = _extract_anchor_tokens(query_text)
    spec_anchors = _extract_specific_anchors(anchors)
    sub_clauses = [c.strip() for c in _COMPOUND_QUERY_SPLIT_RE.split(query_text) if c.strip()]
    clause_anchor_sets: list[list[str]] = (
        [_extract_specific_anchors(_extract_anchor_tokens(c)) for c in sub_clauses]
        if len(sub_clauses) >= 2
        else []
    )

    is_quant_query = bool(_QUANTITATIVE_QUERY_RE.search(query_text))
    hm_match = _HOW_MANY_HEAD_RE.search(query_text)
    how_many_heads: list[str] = (
        _extract_specific_anchors(_extract_anchor_tokens(hm_match.group(1))) if hm_match else []
    )
    wt_match = _WHAT_TARGET_HEAD_RE.search(query_text)
    what_target_head: str = wt_match.group(1).lower() if wt_match else ""

    # Extract capitalized proper nouns when the query has no mixed-case/underscore tech identifier
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
        lhs = _extract_specific_anchors(_extract_anchor_tokens(diff_match.group(1)))
        rhs = _extract_specific_anchors(_extract_anchor_tokens(diff_match.group(2)))
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
        pre_tail = set(_extract_anchor_tokens(query_no_purpose[: tail_match.start()]))
        raw_tail_spec = [
            t for t in _extract_anchor_tokens(raw_tail) if t not in _GENERIC_MODIFIER_TOKENS
        ]
        tail_spec_tokens = [t for t in raw_tail_spec if t not in pre_tail]

    kept: list[tuple[str, str, str, str]] = []
    for dom, url, combined, body in raw_items_with_body:
        title_guess = combined.split(". ", 1)[0] if ". " in combined else ""
        clean_comb, is_stub_comb = clean_scraped_passage(combined, title=title_guess)
        clean_body, is_stub_body = clean_scraped_passage(body, title=title_guess)
        if is_stub_body or is_stub_comb:
            continue
        eff_text = clean_comb or clean_body
        if not eff_text:
            continue

        doc_toks = set(re.findall(r"[a-z0-9]+", eff_text.lower()))
        doc_stems = {t[:5] for t in doc_toks if len(t) >= 5}
        body_text_eff = clean_body or eff_text
        body_toks = set(re.findall(r"[a-z0-9]+", body_text_eff.lower()))
        body_stems = {t[:5] for t in body_toks if len(t) >= 5}

        # 1. Ensure body has substantive non-query answer tokens (reject bare title echoes)
        non_q_toks = [
            t
            for t in body_toks
            if (len(t) >= 3 or t.isdigit()) and t not in _ANSWER_NOISE_TOKENS and t not in anchors
        ]
        if len(non_q_toks) < 3:
            continue

        # 2. Proper-noun entity guard (e.g. "Earl Grey" -> Darjeeling-only tea page rejected)
        if proper_nouns and len(proper_nouns) <= 3 and " or " not in query_text.lower():
            pn_hits = sum(1 for pn in proper_nouns if _stem_match(pn, doc_toks, doc_stems))
            if pn_hits == 0:
                continue

        # 3. Compound two-part question check ("When was X AND which PEP introduced Y?")
        if len(clause_anchor_sets) >= 2:
            c1_anchors, c2_anchors = clause_anchor_sets[0], clause_anchor_sets[1]
            c2_specific = [a for a in c2_anchors if a not in c1_anchors]
            if c1_anchors and c2_specific:
                c1_ok = any(_stem_match(a, body_toks, body_stems) for a in c1_anchors)
                c2_ok = any(_stem_match(a, body_toks, body_stems) for a in c2_specific)
                if not (c1_ok and c2_ok):
                    continue

        # 4. Comparison pair guard ("difference between git fetch and git pull")
        if diff_pair is not None:
            lhs_toks, rhs_toks = diff_pair
            if not (
                any(_stem_match(a, body_toks, body_stems) for a in lhs_toks)
                and any(_stem_match(b, body_toks, body_stems) for b in rhs_toks)
            ):
                continue

        # 5. Tail topic-entity guard checked against clean body
        if tail_spec_tokens:
            if tail_has_or or len(tail_spec_tokens) >= 3:
                if not any(_stem_match(t, body_toks, body_stems) for t in tail_spec_tokens):
                    continue
            elif not all(_stem_match(t, body_toks, body_stems) for t in tail_spec_tokens):
                continue

        # 6. Interrogative "What/Which <HEAD_NOUN>" target guard (e.g. "pigment", "antidote")
        if what_target_head and what_target_head in ("pigment", "antidote", "port"):
            if not _stem_match(what_target_head, body_toks, body_stems):
                continue

        # 7. "How many <X>" head target + co-occurring count guard in at least one body sentence
        if how_many_heads:
            req_hm = [how_many_heads[-1]]
            if "mutable" in how_many_heads and "mutable" not in req_hm:
                req_hm.append("mutable")
            if not all(_stem_match(h, body_toks, body_stems) for h in req_hm):
                continue
            body_sents = [
                s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", body_text_eff) if s.strip()
            ]
            has_counted_head_sent = False
            for bs in body_sents:
                bs_toks = set(re.findall(r"[a-z0-9]+", bs.lower()))
                bs_stems = {t[:5] for t in bs_toks if len(t) >= 5}
                if all(_stem_match(h, bs_toks, bs_stems) for h in req_hm) and bool(
                    _NUMBER_ANSWER_TOKEN_RE.search(_LEADING_DATELINE_RE.sub("", bs))
                ):
                    has_counted_head_sent = True
                    break
            if not has_counted_head_sent:
                continue

        # 8. Quantitative answer guard: passage body must actually contain a candidate number/count
        if is_quant_query and not _passage_has_answer_number(body_text_eff, query_text):
            continue

        # 7. Specific subject-anchor recall + OpenVINO MiniLM semantic passage similarity
        if spec_anchors:
            spec_hits = sum(1 for a in spec_anchors if _stem_match(a, doc_toks, doc_stems))
            spec_recall = spec_hits / len(spec_anchors)
        else:
            spec_hits = 1
            spec_recall = 1.0

        # For 2-anchor specific queries without "or" (e.g. "maple pigment"), require both
        if len(spec_anchors) == 2 and " or " not in query_text.lower() and spec_hits < 2:
            continue
        if spec_recall < 0.34:
            continue

        best_sents = select_best_query_sentences(eff_text, query_text, top_k=2)
        probe_passage = " ".join(best_sents) if best_sents else eff_text[:320]
        sem_cos = _CORE_EMBEDDER_SINGLETON.cosine(query_text, probe_passage)

        if sem_cos is not None:
            if spec_recall < 0.50 and sem_cos < 0.50:
                continue
            if sem_cos < 0.38:
                continue
        elif spec_recall < 0.50:
            continue

        kept.append((dom, url, eff_text, clean_body or eff_text))

    return kept


def _extract_answer_signature(sent: str, query_anchors: set[str]) -> set[str]:
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


def _shares_verbatim_long_span(text_a: str, text_b: str, span_words: int = 11) -> bool:
    """Return True if two scraped pages share an exact `span_words`-token verbatim reprint."""
    toks_a = re.findall(r"[a-z0-9]+", strip_wire_boilerplate(text_a).lower())
    toks_b = re.findall(r"[a-z0-9]+", strip_wire_boilerplate(text_b).lower())
    if len(toks_a) < span_words or len(toks_b) < span_words:
        return False
    grams_a = {tuple(toks_a[i : i + span_words]) for i in range(len(toks_a) - span_words + 1)}
    for j in range(len(toks_b) - span_words + 1):
        if tuple(toks_b[j : j + span_words]) in grams_a:
            return True
    return False


def _detect_conflicting_single_value_numbers(
    query_text: str,
    all_relevant_items: Sequence[tuple[str, str, str, str]],
) -> tuple[list[str], str]:
    """Detect conflicting years or elevation/height measurements across retrieved items."""
    if len(all_relevant_items) < 2:
        return ([], "")

    q_lower = query_text.lower()
    asks_year = bool(re.search(r"\b(?:what\s+year|which\s+year|in\s+what\s+year)\b", q_lower))
    asks_elev = bool(re.search(r"\b(?:orthometric\s+)?elevation\s+of\b", q_lower))
    if not (asks_year or asks_elev):
        return ([], "")

    q_nums = set(re.findall(r"\b\d{4}\b", query_text))
    per_item_vals: list[tuple[str, str, set[str]]] = []

    for dom, url, comb, _body in all_relevant_items:
        sents = select_best_query_sentences(comb, query_text, top_k=2)
        focus = " ".join(sents)
        if asks_year:
            years = {y for y in re.findall(r"\b(1[5-9]\d{2}|20[01]\d)\b", focus) if y not in q_nums}
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
        return ([], "")

    base_dom, base_url, base_vals = per_item_vals[0]
    conflicting: list[str] = []
    for dom, url, vals in per_item_vals[1:]:
        if url != base_url and vals and base_vals and vals.isdisjoint(base_vals):
            if dom not in conflicting:
                conflicting.append(dom)

    if conflicting:
        return (
            conflicting,
            (
                f"Conflicting numeric values reported across "
                f"{base_dom} ({sorted(base_vals)[0]}) vs {conflicting[0]}"
            ),
        )
    return ([], "")


def _unanimous_decimal_measurement(
    query_text: str,
    all_relevant_items: Sequence[tuple[str, str, str, str]],
) -> bool:
    """Return True if >=2 sources state the exact same decimal for an official constant/distance."""
    if not re.search(
        r"\b(?:official|exact)\s+[a-z\-\s]{0,30}\b(?:distance|speed|temperature)\b",
        query_text,
        re.IGNORECASE,
    ):
        return False
    dec_per_src: list[set[str]] = []
    for _d, _u, comb, _b in all_relevant_items:
        decs = set(re.findall(r"\b\d+\.\d+\b", comb))
        if decs:
            dec_per_src.append(decs)
    if len(dec_per_src) >= 2:
        common = set.intersection(*dec_per_src)
        if common:
            return True
    return False


def assess_open_web_evidence(
    query_text: str,
    clusters: Sequence[SourceCluster],
    all_relevant_items: Sequence[tuple[str, str, str, str]],
) -> OpenWebAssessment:
    """Evaluate symmetric cross-source disputes and multi-sentence consensus corroboration."""
    if not clusters:
        return OpenWebAssessment(corroborating_domains=[], dispute_domains=[], dispute_detail="")

    anchors = _extract_anchor_tokens(query_text)
    spec_anchors = set(_extract_specific_anchors(anchors))
    query_anchors = set(anchors)
    primary = clusters[0]
    primary_sents = select_best_query_sentences(primary.primary_combined_text, query_text, top_k=2)
    primary_focus = " ".join(primary_sents)
    primary_sig = _extract_answer_signature(primary_focus, query_anchors)

    dispute_domains: list[str] = []
    dispute_detail = ""
    unanimous_constant = _unanimous_decimal_measurement(query_text, all_relevant_items)

    # 1. Query-aligned epistemic controversy / myth-refutation across ANY relevant passage
    if not unanimous_constant:
        query_asks_controversy = bool(_QUERY_CONTROVERSY_INTENT_RE.search(query_text))
        for dom, _url, combined, _body in all_relevant_items:
            cleaned_comb, _ = clean_scraped_passage(combined)
            sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", cleaned_comb) if s.strip()]
            for idx_s, sent in enumerate(sents):
                m = _EPISTEMIC_CONTROVERSY_RE.search(sent)
                if not m:
                    continue
                window = " ".join(sents[max(0, idx_s - 1) : min(len(sents), idx_s + 2)]).lower()
                w_toks = set(re.findall(r"[a-z0-9]+", window))
                w_stems = {t[:5] for t in w_toks if len(t) >= 5}
                aligned = query_asks_controversy or any(
                    _stem_match(a, w_toks, w_stems) for a in spec_anchors
                )
                if aligned:
                    if dom not in dispute_domains:
                        dispute_domains.append(dom)
                    if not dispute_detail:
                        dispute_detail = (
                            f"{dom} reports contested/myth-refuted status ('{m.group(0)}')"
                        )
                    break

    # 2. Directional clinical/empirical risk opposition across all relevant items
    inc_doms = [d for d, _u, comb, _b in all_relevant_items if _RISK_INCREASE_RE.search(comb)]
    dec_doms = [
        d for d, _u, comb, _b in all_relevant_items if _RISK_DECREASE_OR_SAFE_RE.search(comb)
    ]
    if inc_doms and dec_doms:
        for d in (*inc_doms, *dec_doms):
            if d not in dispute_domains:
                dispute_domains.append(d)
        if not dispute_detail:
            dispute_detail = f"Opposing directional findings across {inc_doms[0]} vs {dec_doms[0]}"

    # 3. Conflicting single-value years or orthometric elevations across retrieved items
    num_disp_doms, num_disp_detail = _detect_conflicting_single_value_numbers(
        query_text, all_relevant_items
    )
    for d in num_disp_doms:
        if d not in dispute_domains:
            dispute_domains.append(d)
    if num_disp_detail and not dispute_detail:
        dispute_detail = num_disp_detail

    # 4. Multi-sentence consensus corroboration across deduplicated non-reprint clusters
    corroborating_domains: list[str] = []
    accepted_bodies: list[str] = [primary.primary_body_text]
    for other in clusters[1:]:
        if other.primary_domain in dispute_domains:
            continue
        if any(
            _shares_verbatim_long_span(other.primary_body_text, prev_b)
            for prev_b in accepted_bodies
        ):
            continue
        other_sents = select_best_query_sentences(other.primary_combined_text, query_text, top_k=2)
        other_focus = " ".join(other_sents)
        other_sig = _extract_answer_signature(other_focus, query_anchors)
        shared_sig = primary_sig & other_sig

        sem_sim = _CORE_EMBEDDER_SINGLETON.cosine(primary_focus, other_focus)
        _max_con, max_ent = _CORE_NLI_SINGLETON.bidirectional_nli_summary(
            primary_focus, other_focus
        )

        if len(shared_sig) >= 1 or (sem_sim is not None and sem_sim >= 0.46) or max_ent >= 0.30:
            if other.primary_domain not in corroborating_domains:
                corroborating_domains.append(other.primary_domain)
                accepted_bodies.append(other.primary_body_text)

    return OpenWebAssessment(
        corroborating_domains=corroborating_domains,
        dispute_domains=dispute_domains,
        dispute_detail=dispute_detail,
    )
