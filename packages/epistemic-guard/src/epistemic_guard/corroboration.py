"""Multi-source RAG corroboration, wire-syndication deduplication, and OpenVINO INT8
`(query, passage)` open-web evidence classification (`CORROBORATES`, `IRRELEVANT`, `DISPUTES`).
"""

from __future__ import annotations

import re
import threading
import time
import urllib.parse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import numpy as np
import openvino as ov  # type: ignore[import-untyped]
from tokenizers import Tokenizer  # type: ignore[import-untyped]

from epistemic_guard.hazard import OpenVINOHazardClassifier
from epistemic_guard.models import resolve_managed_model_dir
from epistemic_guard.schemas import (
    PROOF_STANDARDS,
    Hazard,
    PassageAssessment,
    ProofStandard,
    WebEvidentiaryBurden,
    standard_for_confidence,
)

WEB_EVIDENCE_SEQ_LEN: Final[int] = 192
WEB_EVIDENCE_CLASSES: Final[tuple[str, ...]] = ("CORROBORATES", "IRRELEVANT", "DISPUTES")

POLICY_TABLE_2D: Final[dict[tuple[str, Hazard], ProofStandard]] = {
    ("casual_mention", Hazard.LOW): ProofStandard.BALANCE_OF_PROBABILITIES,
    ("casual_mention", Hazard.MEDIUM): ProofStandard.CLEAR_AND_CONVINCING,
    ("casual_mention", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("memory_commit_inferred", Hazard.LOW): ProofStandard.CLEAR_AND_CONVINCING,
    ("memory_commit_inferred", Hazard.MEDIUM): ProofStandard.CLEAR_AND_CONVINCING,
    ("memory_commit_inferred", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("unhedged_assertion", Hazard.LOW): ProofStandard.CLEAR_AND_CONVINCING,
    ("unhedged_assertion", Hazard.MEDIUM): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("unhedged_assertion", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("irreversible_action", Hazard.LOW): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("irreversible_action", Hazard.MEDIUM): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("irreversible_action", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,
}

_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "by",
        "at",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "that",
        "this",
        "it",
        "its",
        "what",
        "when",
        "where",
        "which",
        "who",
        "how",
        "why",
    }
)

_STUB_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:temporarily\s+unavailable|just\s+a\s+moment\.{2,}|checking\s+your\s+browser|"
    r"enable\s+javascript\s+and\s+cookies|access\s+denied|403\s+forbidden|404\s+not\s+found|"
    r"please\s+verify\s+you\s+are\s+a\s+human)",
    re.IGNORECASE,
)

_CONTROVERSY_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:is\s+a\s+(?:persistent\s+|common\s+|popular\s+)?myth\b|myth\s+(?:comes\s+from|that\b)|"
    r"(?:popular|common|widespread|persistent)\s+misconception\w*|debunk\w+|hoax\w*|untrue|"
    r"false\s+claim\w*|disput\w+|refut\w+|contradict\w+|"
    r"(?:is|remains?)\s+(?:widely\s+|still\s+)?(?:controversial|debated|contested)|"
    r"scientific\s+(?:debate|controversy|disagreement)|"
    r"(?:scientists?|researchers?|experts?)\s+(?:still\s+|remain\s+)?(?:disagree|debate|divided)|"
    r"competing\s+(?:hypotheses|theories)|conflicting\s+(?:clinical\s+|scientific\s+)?(?:evidence|studies|trials))\b",
    re.IGNORECASE,
)

_PROHIBITIVE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:not|no|never|cannot|can't|can\u2019t|shouldn't|shouldn\u2019t|don't|don\u2019t|"
    r"contraindicat\w*|forbid\w*|avoid\w*|insecure|deprecat\w*)\b",
    re.IGNORECASE,
)

_DISPUTE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:disput\w*|refut\w*|contradict\w*|debunk\w*|false|untrue|hoax|myth|"
    r"invalid\w*|forbidden|contraindicated|insecure|"
    r"(?:is|was|are|were|does|did|do|must|should|can|will)\s+not|"
    r"never\s+(?:announced|requires|sufficient|supported|released))\b",
    re.IGNORECASE,
)

_SYBIL_DOMAIN_CUE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:mirror|copied|repost|syndicat|aggregator|content[-]?farm|seo[-]?news|\d{3,})",
    re.IGNORECASE,
)


class OpenVINOWebEvidenceClassifier:
    """OpenVINO INT8 3-class `(query, passage)` cross-encoder for web evidence stance."""

    def __init__(
        self,
        model_dir: Path | str | None = None,
        *,
        device: str | None = None,
        verify_hashes: bool = False,
        require_neural: bool = False,
        warn_on_missing: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self.available = False
        self.active_device = "DETERMINISTIC_CPU"
        self._tokenizer: Tokenizer | None = None
        self._infer_req: ov.InferRequest | None = None
        self._has_token_type_ids = False

        resolved = resolve_managed_model_dir(
            "web_evidence",
            model_dir,
            verify_hashes=verify_hashes,
            require_neural=require_neural,
            warn_on_missing=warn_on_missing,
        )
        self.model_dir = resolved
        if resolved is None:
            return

        xml_path = resolved / "openvino_model.xml"
        tok_path = resolved / "tokenizer.json"
        try:
            core = ov.Core()
            model = core.read_model(str(xml_path))
            seq_len = WEB_EVIDENCE_SEQ_LEN
            if model.inputs and model.inputs[0].partial_shape.is_static:
                seq_len = int(model.inputs[0].shape[1])
            input_names = {name for inp in model.inputs for name in inp.get_names()}
            self._has_token_type_ids = "token_type_ids" in input_names

            tok = Tokenizer.from_file(str(tok_path))
            tok.enable_truncation(max_length=seq_len)
            pad_id = 0 if self._has_token_type_ids else 1
            pad_tok = "[PAD]" if self._has_token_type_ids else "<pad>"
            tok.enable_padding(length=seq_len, pad_id=pad_id, **{"pad_token": pad_tok})
            self._tokenizer = tok

            avail = set(core.available_devices)
            candidates = (device,) if device is not None else ("NPU", "GPU.0", "GPU", "CPU")
            for dev in candidates:
                if dev == "CPU" or dev in avail:
                    try:
                        compiled = core.compile_model(model, dev)
                        self._infer_req = compiled.create_infer_request()
                        self.active_device = dev
                        self.available = True
                        break
                    except RuntimeError:
                        pass
            if not self.available:
                compiled = core.compile_model(model, "CPU")
                self._infer_req = compiled.create_infer_request()
                self.active_device = "CPU"
                self.available = True
        except Exception:
            if require_neural:
                raise
            self.available = False
            self.active_device = "DETERMINISTIC_CPU"

    def score_passage(self, query: str, passage: str) -> tuple[str, float]:
        """Return `(stance, confidence)` in `{'CORROBORATES', 'IRRELEVANT', 'DISPUTES'}`."""
        if not self.available or self._tokenizer is None or self._infer_req is None:
            return ("CORROBORATES", 0.5)
        enc = self._tokenizer.encode(query.strip(), passage.strip())
        feed: dict[str, np.ndarray[Any, Any]] = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }
        if self._has_token_type_ids:
            feed["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)
        with self._lock:
            res = self._infer_req.infer(feed)
            logits = np.asarray(list(res.values())[0], dtype=np.float64)[0]
        exp_l = np.exp(logits - np.max(logits))
        probs = exp_l / np.sum(exp_l)
        idx = int(np.argmax(probs))
        return (WEB_EVIDENCE_CLASSES[idx], round(float(probs[idx]), 4))


def required_standard(consumer: str, hazard: Hazard) -> ProofStandard:
    return POLICY_TABLE_2D.get((consumer, hazard), ProofStandard.BEYOND_REASONABLE_DOUBT)


def meets_standard(confidence: float, consumer: str, hazard: Hazard) -> bool:
    return confidence >= PROOF_STANDARDS[required_standard(consumer, hazard)]


def extract_registrable_domain(url_or_domain: str, idx: int) -> str:
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


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def shingle_jaccard_similarity(text_a: str, text_b: str, k: int = 4) -> float:
    """Compute word `k`-shingle Jaccard similarity to collapse verbatim and wire-syndicated text."""
    toks_a = _word_tokens(text_a)
    toks_b = _word_tokens(text_b)
    if not toks_a or not toks_b:
        return 0.0
    set_a: set[tuple[str, ...]]
    set_b: set[tuple[str, ...]]
    if len(toks_a) < k or len(toks_b) < k:
        set_a = {(t,) for t in toks_a}
        set_b = {(t,) for t in toks_b}
    else:
        set_a = {tuple(toks_a[i : i + k]) for i in range(len(toks_a) - k + 1)}
        set_b = {tuple(toks_b[i : i + k]) for i in range(len(toks_b) - k + 1)}
    union = len(set_a | set_b)
    return (len(set_a & set_b) / union) if union > 0 else 0.0


def deduplicate_syndicated_sources(
    items: Sequence[tuple[str, str]],
    *,
    near_duplicate_threshold: float = 0.55,
) -> tuple[list[tuple[str, str]], int]:
    """Collapse same-domain entries and near-duplicate syndicated/mirror copies across domains."""
    unique: list[tuple[str, str]] = []
    seen_domains: set[str] = set()
    collapsed = 0

    for dom, text in items:
        if dom in seen_domains:
            collapsed += 1
            continue
        is_near_dup = False
        for _prev_dom, prev_text in unique:
            sim_4 = shingle_jaccard_similarity(text, prev_text, k=4)
            sim_3 = shingle_jaccard_similarity(text, prev_text, k=3)
            if sim_4 >= near_duplicate_threshold or sim_3 >= (near_duplicate_threshold + 0.10):
                is_near_dup = True
                break
        if is_near_dup:
            collapsed += 1
            continue
        seen_domains.add(dom)
        unique.append((dom, text))

    return unique, collapsed


def evaluate_web_evidence_burden(
    query_text: str,
    search_results: Sequence[Mapping[str, object]],
    *,
    classifier: OpenVINOHazardClassifier | None = None,
    evidence_classifier: OpenVINOWebEvidenceClassifier | None = None,
    device: str | None = None,
    near_duplicate_threshold: float = 0.55,
    warn_on_missing: bool = True,
) -> WebEvidentiaryBurden:
    """Evaluate multi-source RAG/web passages for hazard tier, wire duplicates, and disputes."""
    clf = classifier or OpenVINOHazardClassifier(device=device, warn_on_missing=warn_on_missing)
    ev_clf = evidence_classifier or OpenVINOWebEvidenceClassifier(
        device=device, warn_on_missing=warn_on_missing
    )
    hz_verdict = clf.evaluate(query_text)
    hazard = hz_verdict.hazard

    req_casual = required_standard("casual_mention", hazard)
    req_commit = required_standard("memory_commit_inferred", hazard)
    req_unhedged = required_standard("unhedged_assertion", hazard)

    t0 = time.perf_counter()
    raw_pairs: list[tuple[str, str]] = []
    has_scraped = False
    filtered_irrelevant = 0
    for idx, row in enumerate(search_results, 1):
        url = str(row.get("url", "") or row.get("source_url", "") or "")
        raw_dom = str(row.get("domain", "") or row.get("source", "") or url)
        dom = extract_registrable_domain(raw_dom, idx)
        title = str(row.get("title", "") or "").strip()
        snippet = str(row.get("snippet", "") or "").strip()
        preview = str(row.get("content_preview", "") or row.get("content", "") or "").strip()
        if preview:
            has_scraped = True
        body = (
            f"{snippet}. {preview}".strip(". ")
            if (snippet and preview and snippet not in preview)
            else (preview or snippet)
        )
        if _STUB_MARKER_RE.search(body) and len(body) < 180:
            filtered_irrelevant += 1
            continue
        combined = (
            f"{title}. {body}".strip(". ") if title and title not in body else (body or title)
        )
        if combined:
            raw_pairs.append((dom, combined))

    if not raw_pairs:
        corrob_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return WebEvidentiaryBurden(
            query=query_text,
            hazard=hazard,
            hazard_device=hz_verdict.device,
            evidence_device=ev_clf.active_device,
            hazard_latency_ms=hz_verdict.latency_ms,
            corroboration_latency_ms=corrob_ms,
            confidence=0.0,
            achieved_standard=ProofStandard.SPECULATION,
            required_casual_standard=req_casual,
            required_commit_standard=req_commit,
            required_unhedged_standard=req_unhedged,
            meets_casual_burden=False,
            meets_commit_burden=False,
            meets_unhedged_burden=False,
            raw_sources_count=0,
            irrelevant_sources_filtered=filtered_irrelevant,
            summary_tag=f"0 sources | hazard={hazard.value} (ABSTAIN)",
            guidance="No usable web evidence available; abstain from stating unverified facts.",
        )

    dedup_pairs, collapsed_count = deduplicate_syndicated_sources(
        raw_pairs, near_duplicate_threshold=near_duplicate_threshold
    )

    q_content_tokens = {t for t in _word_tokens(query_text) if t not in _STOPWORDS}
    corroborating_domains: list[str] = []
    dispute_domains: list[str] = []
    assessments: list[PassageAssessment] = []

    primary_dom, primary_text = dedup_pairs[0]
    primary_tokens = {t for t in _word_tokens(primary_text) if t not in _STOPWORDS}
    prohibitive_ctx = bool(
        _PROHIBITIVE_RE.search(query_text) or _PROHIBITIVE_RE.search(primary_text)
    )

    for idx, (dom, text) in enumerate(dedup_pairs):
        toks = {t for t in _word_tokens(text) if t not in _STOPWORDS}
        q_overlap = len(q_content_tokens & toks)
        joint_overlap = len((q_content_tokens | primary_tokens) & toks)

        neural_stance = "CORROBORATES"
        neural_conf = 0.5
        if ev_clf.available:
            neural_stance, neural_conf = ev_clf.score_passage(query_text, text)

        # Deterministic controversy/myth override (high-precision explicit markers)
        explicit_controversy = bool(_CONTROVERSY_RE.search(text))
        explicit_refute = (
            idx > 0
            and not prohibitive_ctx
            and bool(_DISPUTE_RE.search(text))
            and not bool(_DISPUTE_RE.search(primary_text))
        )

        # Off-topic check: zero query-token overlap OR confident neural IRRELEVANT on weak overlap
        if (idx > 0 and joint_overlap == 0) or (has_scraped and q_overlap == 0 and idx > 0):
            filtered_irrelevant += 1
            assessments.append(
                PassageAssessment(
                    domain=dom,
                    stance="IRRELEVANT",
                    confidence=max(neural_conf, 0.85),
                    used_neural=ev_clf.available,
                )
            )
            continue
        if (
            ev_clf.available
            and neural_stance == "IRRELEVANT"
            and neural_conf >= 0.85
            and q_overlap <= 1
        ):
            filtered_irrelevant += 1
            assessments.append(
                PassageAssessment(
                    domain=dom,
                    stance="IRRELEVANT",
                    confidence=neural_conf,
                    used_neural=True,
                )
            )
            continue

        is_disp = (
            explicit_controversy
            or explicit_refute
            or (
                ev_clf.available
                and neural_stance == "DISPUTES"
                and neural_conf >= 0.88
                and not prohibitive_ctx
            )
        )
        if is_disp:
            if dom not in dispute_domains:
                dispute_domains.append(dom)
            if (
                idx == 0
                and dom not in corroborating_domains
                and not _SYBIL_DOMAIN_CUE_RE.search(dom)
            ):
                corroborating_domains.append(dom)
            assessments.append(
                PassageAssessment(
                    domain=dom,
                    stance="DISPUTES",
                    confidence=neural_conf if ev_clf.available else 0.90,
                    used_neural=ev_clf.available,
                )
            )
        elif not _SYBIL_DOMAIN_CUE_RE.search(dom):
            corroborating_domains.append(dom)
            assessments.append(
                PassageAssessment(
                    domain=dom,
                    stance="CORROBORATES",
                    confidence=neural_conf if ev_clf.available else 0.80,
                    used_neural=ev_clf.available,
                )
            )

    if not dispute_domains and not prohibitive_ctx:
        for dom, text in raw_pairs[1:]:
            if (
                dom != primary_dom
                and _DISPUTE_RE.search(text)
                and not _DISPUTE_RE.search(primary_text)
            ):
                dispute_domains.append(dom)

    is_disputed = len(dispute_domains) > 0
    indep_count = len(corroborating_domains)

    if indep_count == 0 and not is_disputed:
        corrob_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return WebEvidentiaryBurden(
            query=query_text,
            hazard=hazard,
            hazard_device=hz_verdict.device,
            evidence_device=ev_clf.active_device,
            hazard_latency_ms=hz_verdict.latency_ms,
            corroboration_latency_ms=corrob_ms,
            confidence=0.0,
            achieved_standard=ProofStandard.SPECULATION,
            required_casual_standard=req_casual,
            required_commit_standard=req_commit,
            required_unhedged_standard=req_unhedged,
            meets_casual_burden=False,
            meets_commit_burden=False,
            meets_unhedged_burden=False,
            raw_sources_count=len(raw_pairs),
            deduplicated_duplicates_collapsed=collapsed_count,
            irrelevant_sources_filtered=filtered_irrelevant,
            passage_assessments=assessments,
            summary_tag=f"0 relevant sources | hazard={hazard.value} (ABSTAIN)",
            guidance=(
                "Retrieved passages were off-topic or unavailable; abstain from unverified facts."
            ),
        )

    if is_disputed:
        eff_conf = 0.40
    elif indep_count >= 3:
        eff_conf = 0.95
    elif indep_count == 2:
        eff_conf = 0.80
    else:
        eff_conf = 0.70

    achieved = standard_for_confidence(eff_conf)
    meets_casual = meets_standard(eff_conf, "casual_mention", hazard) and not is_disputed
    meets_commit = meets_standard(eff_conf, "memory_commit_inferred", hazard) and not is_disputed
    meets_unhedged = meets_standard(eff_conf, "unhedged_assertion", hazard) and not is_disputed
    corrob_ms = round((time.perf_counter() - t0) * 1000.0, 3)

    dom_preview = ", ".join(corroborating_domains[:4])
    if is_disputed:
        disp_preview = ", ".join(dispute_domains[:3])
        guidance = (
            f"Sources disagree ({primary_dom} vs {disp_preview}); describe both sides "
            f"and do not present the disputed point as settled fact."
        )
        tag = (
            f"disputed ({primary_dom} vs {disp_preview}) | "
            f"conf={eff_conf:.2f} | hazard={hazard.value}"
        )
    elif meets_casual:
        guidance = (
            f"Supported by {indep_count} independent source(s) ({dom_preview}) "
            f"for {hazard.value}-hazard query."
        )
        tag = (
            f"{indep_count} independent source(s) | "
            f"conf={eff_conf:.2f} | hazard={hazard.value} (MET)"
        )
    else:
        guidance = (
            f"Only {indep_count} independent source(s) ({dom_preview}) found for a "
            f"{hazard.value}-hazard query; state the source limitation clearly."
        )
        tag = f"{indep_count} source(s) | conf={eff_conf:.2f} | hazard={hazard.value} (QUALIFY)"

    return WebEvidentiaryBurden(
        query=query_text,
        hazard=hazard,
        hazard_device=hz_verdict.device,
        evidence_device=ev_clf.active_device,
        hazard_latency_ms=hz_verdict.latency_ms,
        corroboration_latency_ms=corrob_ms,
        confidence=eff_conf,
        achieved_standard=achieved,
        required_casual_standard=req_casual,
        required_commit_standard=req_commit,
        required_unhedged_standard=req_unhedged,
        meets_casual_burden=meets_casual,
        meets_commit_burden=meets_commit,
        meets_unhedged_burden=meets_unhedged,
        raw_sources_count=len(raw_pairs),
        deduplicated_duplicates_collapsed=collapsed_count,
        irrelevant_sources_filtered=filtered_irrelevant,
        independent_sources_count=indep_count,
        independent_domains=corroborating_domains,
        disputed=is_disputed,
        dispute_sources=dispute_domains,
        passage_assessments=assessments,
        summary_tag=tag,
        guidance=guidance,
    )


# Plain-English convenience alias
corroborate_sources = evaluate_web_evidence_burden
