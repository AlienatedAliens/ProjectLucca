"""2D Hazard-Scaled Standards of Proof, Walton Authority Corroboration, and Shingle Dedup."""

from __future__ import annotations

import re
import time
import urllib.parse
from collections.abc import Mapping, Sequence
from typing import Final

from lucca_epistemic.hazard import OpenVINOHazardClassifier
from lucca_epistemic.schemas import (
    PROOF_STANDARDS,
    Hazard,
    ProofStandard,
    WebEvidentiaryBurden,
    standard_for_confidence,
)

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
    """Compute word k-shingle Jaccard similarity to collapse verbatim & wire-syndicated copies."""
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
    device: str | None = None,
    near_duplicate_threshold: float = 0.55,
) -> WebEvidentiaryBurden:
    """Evaluate multi-source web snippets against 2D Hazard Policy + Walton Authority + Dedup."""
    clf = classifier or OpenVINOHazardClassifier(device=device)
    hz_verdict = clf.evaluate(query_text)
    hazard = hz_verdict.hazard

    req_casual = required_standard("casual_mention", hazard)
    req_commit = required_standard("memory_commit_inferred", hazard)
    req_unhedged = required_standard("unhedged_assertion", hazard)

    t0 = time.perf_counter()
    raw_pairs: list[tuple[str, str]] = []
    for idx, row in enumerate(search_results, 1):
        url = str(row.get("url", "") or row.get("source_url", "") or "")
        raw_dom = str(row.get("domain", "") or row.get("source", "") or url)
        dom = extract_registrable_domain(raw_dom, idx)
        title = str(row.get("title", "") or "").strip()
        snippet = str(row.get("snippet", "") or row.get("content", "") or "").strip()
        combined = (
            f"{title}. {snippet}".strip(". ")
            if title and title not in snippet
            else (snippet or title)
        )
        if combined:
            raw_pairs.append((dom, combined))

    if not raw_pairs:
        corrob_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return WebEvidentiaryBurden(
            query=query_text,
            hazard=hazard,
            hazard_device=hz_verdict.device,
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
            summary_tag=f"0 sources | hazard={hazard.value} (ABSTAIN)",
            guidance="No web evidence available; abstain from stating unverified facts.",
        )

    dedup_pairs, collapsed_count = deduplicate_syndicated_sources(
        raw_pairs, near_duplicate_threshold=near_duplicate_threshold
    )

    q_content_tokens = {t for t in _word_tokens(query_text) if t not in _STOPWORDS}
    primary_dom, primary_text = dedup_pairs[0]
    primary_tokens = {t for t in _word_tokens(primary_text) if t not in _STOPWORDS}

    corroborating_domains: list[str] = [primary_dom]
    dispute_domains: list[str] = []

    for dom, text in dedup_pairs[1:]:
        toks = {t for t in _word_tokens(text) if t not in _STOPWORDS}
        overlap = len((q_content_tokens | primary_tokens) & toks)
        if overlap == 0:
            continue
        if _DISPUTE_RE.search(text) and not _DISPUTE_RE.search(primary_text):
            dispute_domains.append(dom)
        elif not _SYBIL_DOMAIN_CUE_RE.search(dom):
            corroborating_domains.append(dom)

    # Also detect dispute when primary source is low-quality/sybil and a later source refutes it
    if not dispute_domains:
        for dom, text in raw_pairs[1:]:
            if (
                dom != primary_dom
                and _DISPUTE_RE.search(text)
                and not _DISPUTE_RE.search(primary_text)
            ):
                dispute_domains.append(dom)

    is_disputed = len(dispute_domains) > 0
    indep_count = len(corroborating_domains)

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
        independent_sources_count=indep_count,
        independent_domains=corroborating_domains,
        disputed=is_disputed,
        dispute_sources=dispute_domains,
        summary_tag=tag,
        guidance=guidance,
    )
