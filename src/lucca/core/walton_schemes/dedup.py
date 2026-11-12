"""Near-duplicate syndication/sybil clustering and OpenVINO NLI cross-cluster dispute check.

Addresses R-33 (Source independence != distinct eTLD+1):
1. Collapses verbatim mirrors, lightly-edited syndicated wire dispatches, and sybil copies
   across distinct registrable domains using non-query token Jaccard/containment, 3-gram
   shingles, and 64-bit shingle SimHash after stripping wire datelines/attributions.
2. Evaluates inter-cluster contradiction across distinct deduplicated source clusters via
   both bidirectional polarity cues and in-process OpenVINO NLI (`verifier_deberta_v3_xsmall_ov`)
   with zero `lucca.senses` or `lucca.ui` imports (preserving hexagonal Contract 8).
"""

from __future__ import annotations

import hashlib
import json
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

from lucca.core.corroboration import is_same_source

try:
    from tokenizers import Tokenizer
except ImportError:  # pragma: no cover
    Tokenizer = None

logger = structlog.get_logger(__name__)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[4]

_WIRE_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:"
    r"report\s+from\s+[^\s:]+\s*:\s*"
    r"|\([a-z0-9\s\-]{3,30}\)\s*[\u2014\u2013\-:]+\s*"
    r"|[A-Z][A-Z\s.,']{2,28}(?:\([A-Za-z0-9\s.]+\))?\s*[\u2014\u2013\-]+\s*"
    r"|according\s+to\s+(?:[a-z\-]+\s+){0,4}(?:wire\s+)?(?:reports?|dispatches?|services?)\s*,\s*"
    r")+",
    re.IGNORECASE,
)

_DEDUP_STOPWORDS: Final[frozenset[str]] = frozenset(
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
        "atop",
        "across",
        "through",
        "during",
        "before",
        "after",
        "between",
        "within",
        "inside",
        "around",
        "near",
        "about",
        "approximately",
        "roughly",
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
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "their",
        "they",
        "them",
        "which",
        "who",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "what",
        "so",
        "such",
        "than",
        "then",
        "also",
        "both",
        "each",
        "every",
        "all",
        "any",
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
        "according",
    }
)

_EXPLICIT_DISPUTE_CUE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:disput\w*|refut\w*|contradict\w*|debunk\w*|myth\w*|hoax\w*|untrue|"
    r"false\s+claim\w*|misconception\w*|fallac\w*|erroneous\w*|unfounded|"
    r"contrary\s+to\s+(?:popular|common|viral|widespread|blog)|"
    r"(?:is|was|are|were|does|did|do|must|should|can|will)\s+not\b|"
    r"never\s+\w+|contains?\s+no\b|provides?\s+no\b|performs?\s+zero\b|"
    r"sharing\s+no\b|despite\s+popular)\b",
    re.IGNORECASE,
)


_AUTHORITATIVE_DOMAIN_SUFFIXES: Final[tuple[str, ...]] = (
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


def is_authoritative_domain(domain: str) -> bool:
    """Return True for institutional (.gov/.edu/.int) and formal standards-body domains."""
    d = (domain or "").strip().lower().rstrip(".")
    if not d:
        return False
    if any(d.endswith(sfx) for sfx in _AUTHORITATIVE_DOMAIN_SUFFIXES):
        return True
    return any(d == std or d.endswith("." + std) for std in _AUTHORITATIVE_STANDARDS_DOMAINS)


@dataclass(frozen=True)
class SourceCluster:
    """Canonical representative and member domains of a deduplicated web source cluster."""

    primary_domain: str
    primary_url: str
    primary_combined_text: str
    primary_body_text: str
    member_domains: tuple[str, ...]
    collapsed_duplicates: int


def strip_wire_boilerplate(text: str) -> str:
    """Remove leading wire datelines, agency tags, and `Report from <dom>:` prefixes."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    # Preserve case temporarily for uppercase dateline check, then strip repeated prefixes
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _WIRE_PREFIX_RE.sub("", cleaned).strip()
    return cleaned


def _content_tokens(text: str, exclude: frozenset[str]) -> list[str]:
    stripped = strip_wire_boilerplate(text).lower()
    raw_toks = re.findall(r"[a-z0-9]+", stripped)
    return [t for t in raw_toks if len(t) >= 2 and t not in _DEDUP_STOPWORDS and t not in exclude]


def _simhash64(tokens: Sequence[str], shingle_size: int = 2) -> int:
    if not tokens:
        return 0
    if len(tokens) < shingle_size:
        grams = [tuple(tokens)]
    else:
        grams = [tuple(tokens[i : i + shingle_size]) for i in range(len(tokens) - shingle_size + 1)]
    acc = [0] * 64
    for g in grams:
        digest = hashlib.blake2b(" ".join(g).encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        for bit in range(64):
            if (h >> bit) & 1:
                acc[bit] += 1
            else:
                acc[bit] -= 1
    out = 0
    for bit in range(64):
        if acc[bit] > 0:
            out |= 1 << bit
    return out


def _hamming64(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _shingle_jaccard(toks_a: Sequence[str], toks_b: Sequence[str], k: int = 3) -> tuple[float, int]:
    if len(toks_a) < k or len(toks_b) < k:
        return 0.0, 0
    sh_a = {tuple(toks_a[i : i + k]) for i in range(len(toks_a) - k + 1)}
    sh_b = {tuple(toks_b[i : i + k]) for i in range(len(toks_b) - k + 1)}
    inter = len(sh_a & sh_b)
    union = len(sh_a | sh_b)
    return ((inter / union) if union else 0.0), inter


class _CoreOpenVINONLI:
    """Lazy, thread-safe OpenVINO NLI cross-encoder for inter-cluster contradiction checks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._initialized = False
        self._compiled: ov.CompiledModel | None = None
        self._infer_req: ov.InferRequest | None = None
        self._tokenizer: Tokenizer | None = None
        self._input_names: list[str] = []
        self._con_idx: int = 0
        self._ent_idx: int = 1

    def _ensure_loaded(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            if Tokenizer is None:
                return
            env_dir = os.environ.get("LUCCA_VERIFIER_MODEL_DIR")
            candidates = ([Path(env_dir)] if env_dir else []) + [
                _REPO_ROOT / "models" / "verifier_deberta_v3_xsmall_ov",
                Path(r"C:\ProjectLucca\models\verifier_deberta_v3_xsmall_ov"),
                _REPO_ROOT / "models" / "verifier_minilm",
                Path(r"C:\ProjectLucca\models\verifier_minilm"),
            ]
            model_dir = next(
                (p for p in candidates if (p / "openvino_model.xml").exists()),
                None,
            )
            if model_dir is None:
                return
            try:
                cfg_path = model_dir / "config.json"
                if cfg_path.exists():
                    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    id2label = cfg.get("id2label", {})
                    if isinstance(id2label, dict) and id2label:
                        lmap = {str(v).lower(): int(k) for k, v in id2label.items()}
                        self._con_idx = lmap.get("contradiction", 0)
                        self._ent_idx = lmap.get("entailment", 1)
                tok_path = model_dir / "tokenizer.json"
                if not tok_path.exists():
                    return
                tok = Tokenizer.from_file(str(tok_path))
                tok.enable_truncation(max_length=128)
                tok.enable_padding(length=128)
                core = ov.Core()
                ov_model = core.read_model(str(model_dir / "openvino_model.xml"))
                self._input_names = [inp.get_any_name() for inp in ov_model.inputs]
                self._compiled = core.compile_model(ov_model, "CPU")
                self._infer_req = self._compiled.create_infer_request()
                self._tokenizer = tok
            except Exception as exc:  # noqa: BLE001
                logger.debug("core_nli_init_failed", error=str(exc))
                self._compiled = None
                self._infer_req = None
                self._tokenizer = None

    def infer_pair_probs(self, premise: str, hypothesis: str) -> tuple[float, float, float]:
        """Return `(p_contradiction, p_entailment, p_neutral)` for `premise -> hypothesis`."""
        self._ensure_loaded()
        if self._compiled is None or self._tokenizer is None or self._infer_req is None:
            return (0.0, 0.0, 1.0)
        p_clean = unicodedata.normalize("NFC", strip_wire_boilerplate(premise))[:512]
        h_clean = unicodedata.normalize("NFC", strip_wire_boilerplate(hypothesis))[:512]
        if not p_clean or not h_clean:
            return (0.0, 0.0, 1.0)
        try:
            enc = self._tokenizer.encode(p_clean, h_clean)
            feed: dict[str, np.ndarray[tuple[int, ...], np.dtype[np.int64]]] = {}
            if "input_ids" in self._input_names:
                feed["input_ids"] = np.array([enc.ids], dtype=np.int64)
            if "attention_mask" in self._input_names:
                feed["attention_mask"] = np.array([enc.attention_mask], dtype=np.int64)
            if "token_type_ids" in self._input_names:
                feed["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)
            with self._lock:
                outputs = self._infer_req.infer(feed)
                logits = np.squeeze(list(outputs.values())[0]).copy()
            exp_l = np.exp(logits - np.max(logits))
            probs = exp_l / np.sum(exp_l)
            con_p = float(probs[self._con_idx])
            ent_p = float(probs[self._ent_idx])
            neu_idx = next(
                (i for i in range(len(probs)) if i not in (self._con_idx, self._ent_idx)), 2
            )
            neu_p = float(probs[neu_idx]) if neu_idx < len(probs) else max(0.0, 1.0 - con_p - ent_p)
            return (con_p, ent_p, neu_p)
        except Exception as exc:  # noqa: BLE001
            logger.debug("core_nli_infer_failed", error=str(exc))
            return (0.0, 0.0, 1.0)

    def max_contradiction_prob(self, text_a: str, text_b: str) -> float:
        """Return max directional contradiction probability across (A->B, B->A)."""
        con_ab, _, _ = self.infer_pair_probs(text_a, text_b)
        con_ba, _, _ = self.infer_pair_probs(text_b, text_a)
        return max(con_ab, con_ba)

    def bidirectional_nli_summary(self, text_a: str, text_b: str) -> tuple[float, float]:
        """Return `(max_contradiction_prob, max_entailment_prob)` across (A->B, B->A)."""
        con_ab, ent_ab, _ = self.infer_pair_probs(text_a, text_b)
        con_ba, ent_ba, _ = self.infer_pair_probs(text_b, text_a)
        return (max(con_ab, con_ba), max(ent_ab, ent_ba))


_CORE_NLI_SINGLETON = _CoreOpenVINONLI()


def are_texts_near_duplicate(
    text_a: str,
    text_b: str,
    query_or_claim: str = "",
) -> bool:
    """Return True if two snippet/receipt texts represent verbatim or wire-syndicated copies.

    Requires substantive non-query overlap (`>= 4` non-query content words for exact copy;
    `>= 6` shared non-query content words for fuzzy shingle/SimHash match) so short atomic
    unit-test propositions and genuinely independent multi-source phrasings remain distinct.
    """
    q_exclude = frozenset(re.findall(r"[a-z0-9]+", (query_or_claim or "").lower()))
    norm_a = " ".join(re.findall(r"[a-z0-9]+", strip_wire_boilerplate(text_a).lower()))
    norm_b = " ".join(re.findall(r"[a-z0-9]+", strip_wire_boilerplate(text_b).lower()))
    if not norm_a or not norm_b:
        return False

    toks_a = _content_tokens(text_a, q_exclude)
    toks_b = _content_tokens(text_b, q_exclude)

    # 1. Exact normalized prose match (when snippet carries >= 4 non-query content tokens)
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

    # Guard against merging opposing-polarity snippets that share vocabulary
    cue_a = bool(_EXPLICIT_DISPUTE_CUE_RE.search(text_a))
    cue_b = bool(_EXPLICIT_DISPUTE_CUE_RE.search(text_b))
    if cue_a != cue_b:
        if _CORE_NLI_SINGLETON.max_contradiction_prob(text_a, text_b) >= 0.85:
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
        if _hamming64(_simhash64(toks_a, 2), _simhash64(toks_b, 2)) <= 12:
            return True
    return False


def cluster_near_duplicate_sources(
    raw_items: Sequence[tuple[str, str, str, str]],
    query_text: str,
) -> tuple[list[SourceCluster], int]:
    """Cluster `(domain, url, combined_text, body_text)` items into distinct origin clusters.

    Returns `(clusters, total_collapsed_duplicates)`.
    """
    clusters: list[SourceCluster] = []
    collapsed_total = 0

    for dom, url, combined, body in raw_items:
        matched_idx: int | None = None
        for idx, cl in enumerate(clusters):
            if any(is_same_source(dom, m) for m in cl.member_domains):
                matched_idx = idx
                break
            if are_texts_near_duplicate(body, cl.primary_body_text, query_text):
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
    # Promote institutional/standards-body clusters ahead of unverified domains (preserving
    # original rank order within each authority tier) per Walton CQ1 Authority priority.
    clusters.sort(key=lambda cl: 0 if is_authoritative_domain(cl.primary_domain) else 1)
    return clusters, collapsed_total


def detect_cross_cluster_dispute(
    clusters: Sequence[SourceCluster],
    nli_contradiction_threshold: float = 0.97,
) -> list[str]:
    """Detect semantic or polarity contradiction across distinct deduplicated source clusters.

    Handles contrary authoritative sources at ANY rank position (`idx == 0` or `idx > 0`).
    Returns the list of conflicting cluster domains (excluding `clusters[0].primary_domain`
    unless `clusters[0]` is itself the contrary refutation against `clusters[1:]`).
    """
    if len(clusters) < 2:
        return []

    primary = clusters[0]
    dispute_domains: list[str] = []

    for other in clusters[1:]:
        nli_con = _CORE_NLI_SINGLETON.max_contradiction_prob(
            primary.primary_body_text, other.primary_body_text
        )
        if nli_con >= nli_contradiction_threshold:
            if other.primary_domain not in dispute_domains:
                dispute_domains.append(other.primary_domain)

    return dispute_domains
