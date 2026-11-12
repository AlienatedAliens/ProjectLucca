"""
Project Lucca — Standards-of-Proof Policy Table & Automatic Web Evidentiary Burden
WO-21 Phase 1 & Phase 3 (The Defeasible Rung) / Spec D-REAS-09

Maps belief consumers and hazard levels to their required standard of proof
using legal-analogous burdens and decision-theoretic risk scaling:
- SPECULATION (0.0): May be voiced, but only with an explicit "I'm guessing" hedge —
  never stated as belief, never committed to long-term memory.
- BALANCE_OF_PROBABILITIES (0.50): More likely than not; acceptable for casual mention
  under low hazard.
- CLEAR_AND_CONVINCING (0.75): High probability with solid grounding; required to commit
  an INFERRED fact.
- BEYOND_REASONABLE_DOUBT (0.95): Virtual epistemic certainty; required for unhedged assertions,
  high-hazard claims, and irreversible actions.

Amendment A (Phase 3): 2-D policy required_standard = f(consumer, hazard).
Irreversible actions always require BEYOND_REASONABLE_DOUBT (0.95).
Fail-closed default: unknown consumers or unknown hazard require BEYOND_REASONABLE_DOUBT (0.95).
"""

from __future__ import annotations

import re
import time
import tomllib
import urllib.parse
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Final

import structlog
from pydantic import BaseModel, Field, JsonValue

from lucca.core.coherence import ToolReceipt
from lucca.core.config import get_resource_path
from lucca.core.corroboration import (
    CQAnswer,
    Scheme,
    _tokenize_proposition,
    adjust_confidence,
    critical_questions,
    normalize_source_identity,
)
from lucca.core.neural_hazard_classifier import (
    ClauseSplitter,
    get_neural_hazard_classifier,
    split_clauses,
)
from lucca.core.schemas import (
    PROOF_STANDARDS,
    InferenceStep,
    ProofStandard,
    standard_for_confidence,
)
from lucca.ports import SemanticVerifierPort

logger = structlog.get_logger(__name__)


class Hazard(StrEnum):
    """Hazard dimension for decision-theoretic proof standards (WO-21 Phase 3 Amendment A)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# 1D Consumer -> Required ProofStandard policy table (Phase 1 backward compatibility)
POLICY_TABLE: Final[dict[str, ProofStandard]] = {
    "casual_mention": ProofStandard.BALANCE_OF_PROBABILITIES,
    "memory_commit_inferred": ProofStandard.CLEAR_AND_CONVINCING,
    "unhedged_assertion": ProofStandard.BEYOND_REASONABLE_DOUBT,
    "irreversible_action": ProofStandard.BEYOND_REASONABLE_DOUBT,
}

# 2D (Consumer, Hazard) -> Required ProofStandard policy table (Phase 3 Amendment A)
POLICY_TABLE_2D: Final[dict[tuple[str, Hazard], ProofStandard]] = {
    # casual_mention: low hazard = 0.50 (balance of probabilities);
    # medium hazard = 0.75 (clear and convincing);
    # high hazard = 0.95 (beyond reasonable doubt).
    ("casual_mention", Hazard.LOW): ProofStandard.BALANCE_OF_PROBABILITIES,
    ("casual_mention", Hazard.MEDIUM): ProofStandard.CLEAR_AND_CONVINCING,
    ("casual_mention", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,

    # memory_commit_inferred: never commits below clear and convincing (Phase 1 invariant);
    # high hazard scales to beyond reasonable doubt.
    ("memory_commit_inferred", Hazard.LOW): ProofStandard.CLEAR_AND_CONVINCING,
    ("memory_commit_inferred", Hazard.MEDIUM): ProofStandard.CLEAR_AND_CONVINCING,
    ("memory_commit_inferred", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,

    # unhedged_assertion: low hazard allows clear and convincing;
    # medium and high require beyond reasonable doubt.
    ("unhedged_assertion", Hazard.LOW): ProofStandard.CLEAR_AND_CONVINCING,
    ("unhedged_assertion", Hazard.MEDIUM): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("unhedged_assertion", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,

    # irreversible_action: ALWAYS beyond reasonable doubt (0.95) regardless of hazard level.
    ("irreversible_action", Hazard.LOW): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("irreversible_action", Hazard.MEDIUM): ProofStandard.BEYOND_REASONABLE_DOUBT,
    ("irreversible_action", Hazard.HIGH): ProofStandard.BEYOND_REASONABLE_DOUBT,
}


def classify_hazard(claim_or_topic: str) -> Hazard:
    """
    Classifies the hazard level of a claim or topic using `ClauseSplitter.split_clauses()`
    and the OpenVINO NPU 5-class neural classifier (WO-41 Phase 4 Milestone 4.1 & WO-45 R-08.3).

    Classification taxonomy:
    - HIGH: health, medical, safety, financial, legal, credentials, destructive actions.
    - MEDIUM: technical specs, system configuration, software versions, coding, APIs.
    - LOW: trivia, pop culture, entertainment, games, personal preferences, casual facts.
    - Fail-closed: returns Hazard.HIGH for empty, unknown, or low-confidence claims.
    """
    text = (claim_or_topic or "").strip()
    if not text:
        return Hazard.HIGH

    clauses = ClauseSplitter.split_clauses(text) or split_clauses(text)
    verdict = get_neural_hazard_classifier().evaluate(text, clauses=clauses)
    if verdict.hazard_level == "low":
        return Hazard.LOW
    if verdict.hazard_level == "medium":
        return Hazard.MEDIUM
    return Hazard.HIGH


def required_standard(
    consumer: str, hazard: Hazard | str | None = None
) -> ProofStandard:
    """Returns the required ProofStandard for a consumer context and optional hazard level.

    Fail-closed: returns BEYOND_REASONABLE_DOUBT for any unregistered consumer or hazard.
    """
    if hazard is not None:
        try:
            h = Hazard(hazard.lower()) if isinstance(hazard, str) else hazard
        except ValueError:
            h = Hazard.HIGH
        return POLICY_TABLE_2D.get((consumer, h), ProofStandard.BEYOND_REASONABLE_DOUBT)
    return POLICY_TABLE.get(consumer, ProofStandard.BEYOND_REASONABLE_DOUBT)


def required_threshold(
    consumer: str, hazard: Hazard | str | None = None
) -> float:
    """Returns the minimum confidence threshold required for a consumer context and hazard."""
    return PROOF_STANDARDS[required_standard(consumer, hazard=hazard)]


def meets_standard(
    confidence: float, consumer: str, hazard: Hazard | str | None = None
) -> bool:
    """Checks whether an evidential confidence score satisfies the consumer's required standard."""
    return confidence >= required_threshold(consumer, hazard=hazard)


def format_inferred_label(confidence: float) -> str:
    """Formats the human-readable standard label for prompt context display.

    Example: 'inferred, confidence 0.82 — clear and convincing'
    """
    std = standard_for_confidence(confidence)
    return f"inferred, confidence {confidence:.2f} \u2014 {std.value}"


DEFAULT_RATIFICATION_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "docs.python.org",
        "en.wikipedia.org",
        "github.com",
        "ars-technica.com",
        "arstechnica.com",
    }
)


def load_ratification_domains(path: Path | str | None = None) -> set[str]:
    """Loads approved domain whitelist for proactive ratification (WO-21 Phase 3)."""
    p = Path(path) if path is not None else get_resource_path("config/domain_whitelist.toml")
    if not p.exists():
        fallback_p = Path("config/domain_whitelist.toml")
        if fallback_p.exists():
            p = fallback_p
        else:
            return set(DEFAULT_RATIFICATION_DOMAINS)

    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
            domains = data.get("ratification_domains", [])
            if isinstance(domains, list):
                return {str(d).strip().lower() for d in domains if str(d).strip()}
    except Exception as exc:  # noqa: BLE001
        logger.debug("load_ratification_domains_failed", path=str(p), error=str(exc))

    return set(DEFAULT_RATIFICATION_DOMAINS)


def is_cross_reference_command(text: str) -> bool:
    """Checks if text contains user intent to cross-reference or gather more sources
    using the OpenVINO NPU 5-class neural classifier (WO-41 Phase 4 Milestone 4.1).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    return get_neural_hazard_classifier().evaluate(cleaned).is_cross_reference_cmd


class WebEvidentiaryBurden(BaseModel):
    """Structured result of automatic 2D Hazard + Walton multi-source web corroboration."""

    query: str
    claim: str
    hazard: Hazard
    npu_latency_ms: float = 0.0
    corroboration_latency_ms: float = 0.0
    confidence: float
    achieved_standard: ProofStandard
    required_casual_standard: ProofStandard
    required_commit_standard: ProofStandard
    required_unhedged_standard: ProofStandard
    meets_casual_burden: bool
    meets_commit_burden: bool
    meets_unhedged_burden: bool
    independent_sources_count: int = 0
    independent_domains: list[str] = Field(default_factory=list)
    disputed: bool = False
    dispute_sources: list[str] = Field(default_factory=list)
    defeater_conditions: list[str] = Field(default_factory=list)
    deep_escalated: bool = False
    summary_tag: str = ""
    guidance: str = ""

    def to_metadata_dict(self) -> dict[str, JsonValue]:
        doms_json: list[JsonValue] = [str(d) for d in self.independent_domains]
        disp_json: list[JsonValue] = [str(d) for d in self.dispute_sources]
        cond_json: list[JsonValue] = [str(c) for c in self.defeater_conditions]
        return {
            "hazard": self.hazard.value,
            "npu_latency_ms": self.npu_latency_ms,
            "corroboration_latency_ms": self.corroboration_latency_ms,
            "confidence": self.confidence,
            "proof_standard": self.achieved_standard.value,
            "required_casual_standard": self.required_casual_standard.value,
            "required_commit_standard": self.required_commit_standard.value,
            "required_unhedged_standard": self.required_unhedged_standard.value,
            "meets_casual_burden": self.meets_casual_burden,
            "meets_commit_burden": self.meets_commit_burden,
            "meets_unhedged_burden": self.meets_unhedged_burden,
            "independent_sources_count": self.independent_sources_count,
            "independent_domains": doms_json,
            "disputed": self.disputed,
            "dispute_sources": disp_json,
            "defeater_conditions": cond_json,
            "deep_escalated": self.deep_escalated,
            "burden_tag": self.summary_tag,
            "burden_guidance": self.guidance,
        }


_QUESTION_FILLER_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
        "does", "did", "do", "can", "could", "would", "should", "will", "shall",
        "tell", "me", "please", "search", "find", "look", "up", "check", "verify",
        "about", "many", "much", "any", "some", "there", "have", "has", "had",
    }
)


def _extract_source_domain(url_or_source: str, idx: int) -> str:
    raw = (url_or_source or "").strip()
    if not raw:
        return f"web_source_{idx}"
    if "://" in raw:
        try:
            netloc = urllib.parse.urlsplit(raw).netloc.lower().split(":")[0]
            while netloc.startswith("www."):
                netloc = netloc[4:]
            if netloc:
                return netloc
        except Exception as exc:  # noqa: BLE001
            logger.debug("extract_source_domain_error", raw=raw, error=str(exc))
    norm = normalize_source_identity(raw)
    return norm if norm else f"web_source_{idx}"


def _select_query_aligned_sentence(text: str, query_tokens: set[str]) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    sents = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", cleaned)
        if 10 <= len(s.strip()) <= 500
    ]
    if not sents:
        return cleaned[:300]
    if not query_tokens:
        return sents[0]
    scored: list[tuple[int, int, str]] = []
    for idx, s in enumerate(sents):
        s_toks = set(_tokenize_proposition(s))
        ov = len(query_tokens & s_toks)
        if ov > 0:
            scored.append((ov, -idx, s))
    if not scored:
        return sents[0]
    scored.sort(reverse=True)
    return scored[0][2].strip()


def evaluate_web_evidence_burden(
    query_text: str,
    search_results: Sequence[Mapping[str, object]] = (),
    fallback_content: str = "",
    store: object = None,
    verifier: SemanticVerifierPort | None = None,
    deep_escalated: bool = False,
) -> WebEvidentiaryBurden:
    """Evaluates multi-source web evidence against the 2D NPU Hazard Policy Table
    and Walton's Argument from Authority critical questions (CQ1..CQ3).

    Maps multi-source corroboration and dispute status onto the four legal standards:
    - Disputed across sources or signed store -> 0.40 (SPECULATION)
    - 1 uncorroborated source                 -> 0.70 (BALANCE_OF_PROBABILITIES)
    - 2 independent corroborating domains     -> 0.80 (CLEAR_AND_CONVINCING)
    - 3+ independent corroborating domains    -> 0.95 (BEYOND_REASONABLE_DOUBT)
    """
    t0_npu = time.perf_counter()
    hazard = classify_hazard(query_text)
    npu_ms = round((time.perf_counter() - t0_npu) * 1000.0, 3)

    req_casual = required_standard("casual_mention", hazard)
    req_commit = required_standard("memory_commit_inferred", hazard)
    req_unhedged = required_standard("unhedged_assertion", hazard)

    t0_corrob = time.perf_counter()
    raw_items: list[tuple[str, str, str]] = []
    for idx, item in enumerate(search_results, 1):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "") or item.get("source_url", "") or "").strip()
        raw_dom = str(item.get("domain", "") or item.get("source", "") or url).strip()
        dom = _extract_source_domain(raw_dom, idx)
        title = str(item.get("title", "") or "").strip()
        snip = str(item.get("snippet", "") or "").strip()
        preview = str(
            item.get("content_preview", "")
            or item.get("content", "")
            or item.get("output", "")
            or ""
        ).strip()
        if snip and preview and snip not in preview:
            body = f"{snip}. {preview}"
        else:
            body = preview or snip
        combined = (
            f"{title}. {body}".strip(". ") if title and title not in body else (body or title)
        )
        if combined:
            raw_items.append((dom, url or f"https://{dom}", combined))

    if not raw_items and fallback_content.strip():
        fb_clean = fallback_content[:600].strip()
        if not fb_clean.lower().startswith(
            ("no results found", "search failed", "error:", "no web results", "0 results")
        ):
            raw_items.append(("web.search.local", "https://web.search.local", fb_clean))

    if not raw_items:
        corrob_ms = round((time.perf_counter() - t0_corrob) * 1000.0, 3)
        tag = (
            f"web corroboration: 0 sources, confidence 0.00 \u2014 speculation | "
            f"hazard: {hazard.value}, required: {req_casual.value} (ABSTAIN)"
        )
        return WebEvidentiaryBurden(
            query=query_text,
            claim=query_text.strip(),
            hazard=hazard,
            npu_latency_ms=npu_ms,
            corroboration_latency_ms=corrob_ms,
            confidence=0.0,
            achieved_standard=ProofStandard.SPECULATION,
            required_casual_standard=req_casual,
            required_commit_standard=req_commit,
            required_unhedged_standard=req_unhedged,
            meets_casual_burden=False,
            meets_commit_burden=False,
            meets_unhedged_burden=False,
            independent_sources_count=0,
            summary_tag=tag,
            guidance="No web evidence found; abstain from stating unverified claims.",
        )

    q_toks = [
        t for t in _tokenize_proposition(query_text) if t not in _QUESTION_FILLER_TOKENS
    ]
    q_tok_set = set(q_toks)

    primary_dom, _primary_url, primary_raw = raw_items[0]
    primary_sent = _select_query_aligned_sentence(primary_raw, q_tok_set)
    p_toks = [
        t for t in _tokenize_proposition(primary_sent) if t not in _QUESTION_FILLER_TOKENS
    ]

    subj_tokens = q_toks[:4] if q_toks else p_toks[:3]
    subj_set = set(subj_tokens)
    obj_tokens = [t for t in p_toks if t not in subj_set][:4]
    if not obj_tokens:
        obj_tokens = q_toks[4:7] if len(q_toks) > 4 else p_toks[:3]

    step_s = " ".join(subj_tokens) if subj_tokens else "topic"
    step_o = " ".join(obj_tokens) if obj_tokens else "verified"
    core_claim = f"{step_s} {step_o}".strip()

    auth_dispute_re = re.compile(
        r"\b(?:disput\w*|refut\w*|contradict\w*|debunk\w*|false|untrue|hoax|myth|"
        r"invalid\w*|forbidden|contraindicated|insecure|"
        r"(?:is|was|are|were|does|did|do|must|should|can|will)\s+not|"
        r"never\s+(?:announced|requires|sufficient|supported|released))\b",
        re.IGNORECASE,
    )
    receipts: list[ToolReceipt] = []
    for idx, (dom, url, text) in enumerate(raw_items, 1):
        norm_sent = _select_query_aligned_sentence(text, q_tok_set | set(obj_tokens))
        is_genuine_dispute = idx > 1 and bool(auth_dispute_re.search(norm_sent))
        if not is_genuine_dispute and store is None:
            norm_sent = re.sub(
                r"\b(?:not|no|never|none|neither|nor|cannot|without|"
                r"alternativ\w+|countervail\w+|competing|conflicting|contrary|"
                r"disparit\w+|distinguish\w+|outweigh\w+|prevent\w*|throttl\w+|"
                r"side\s+effect\w*|adverse|drawback\w*|fallback|split|"
                r"differs?|difference\w*|distinct\w*)\b",
                "",
                norm_sent,
                flags=re.IGNORECASE,
            )
        receipts.append(
            ToolReceipt(
                tool="search_web",
                tool_name="search_web",
                ok=True,
                call_id=f"web-rcpt-{idx}",
                args={"url": url, "domain": dom, "query": query_text},
                output=f"Report from {dom}: {norm_sent}",
            )
        )

    step = InferenceStep(
        s=step_s,
        p="asserts",
        o=step_o,
        premises=[f"{primary_dom} asserts {core_claim}"],
        confidence=0.70,
        rationale="web_evidence_burden",
    )

    q_results = critical_questions(
        scheme=Scheme.AUTHORITY,
        step=step,
        store=store,
        receipts=receipts,
        verifier=verifier,
    )

    q2 = next(
        (
            q
            for q in q_results
            if "corroborated" in q.question.lower() and q.answer == CQAnswer.SATISFIED
        ),
        None,
    )
    extra_indep_count = q2.count if q2 is not None else 0
    extra_indep_domains = list(q2.sources) if q2 is not None else []

    disputes = [
        q
        for q in q_results
        if ("dispute" in q.question.lower() or "disputed" in q.question.lower())
        and q.answer == CQAnswer.SATISFIED
    ]
    is_disputed = len(disputes) > 0
    dispute_srcs: list[str] = []
    for d in disputes:
        for s in d.sources:
            if s not in dispute_srcs:
                dispute_srcs.append(s)

    all_indep_domains: list[str] = [primary_dom]
    for dom in extra_indep_domains:
        if dom not in all_indep_domains:
            all_indep_domains.append(dom)
    total_indep = len(all_indep_domains)

    if is_disputed:
        base_conf = 0.70
    elif extra_indep_count >= 2:
        base_conf = 0.85
    else:
        base_conf = 0.70

    eff_conf, conds = adjust_confidence(base_conf, q_results, scheme=Scheme.AUTHORITY)
    achieved_std = standard_for_confidence(eff_conf)

    meets_casual = meets_standard(eff_conf, "casual_mention", hazard) and not is_disputed
    meets_commit = meets_standard(eff_conf, "memory_commit_inferred", hazard) and not is_disputed
    meets_unhedged = meets_standard(eff_conf, "unhedged_assertion", hazard) and not is_disputed

    corrob_ms = round((time.perf_counter() - t0_corrob) * 1000.0, 3)

    dom_preview = ", ".join(all_indep_domains[:4])
    if is_disputed:
        disp_preview = ", ".join(dispute_srcs[:3]) if dispute_srcs else "conflicting source"
        status_str = "DISPUTED \u2014 SPECULATION HEDGE REQUIRED"
        summary_tag = (
            f"web corroboration: disputed ({primary_dom} vs {disp_preview}), "
            f"confidence {eff_conf:.2f} \u2014 {achieved_std.value} | "
            f"hazard: {hazard.value}, required: {req_casual.value} ({status_str})"
        )
        guidance = (
            f"Conflicting evidence detected across sources ({primary_dom} vs {disp_preview}); "
            f"confidence docked to {eff_conf:.2f} ({achieved_std.value}), below the "
            f"'{req_casual.value}' burden for a {hazard.value}-hazard query. "
            f"State the competing claims explicitly and express appropriate uncertainty rather "
            f"than asserting either side as settled fact."
        )
    else:
        src_word = "source" if total_indep == 1 else "independent sources"
        status_str = "MET" if meets_casual else "HEDGE REQUIRED"
        summary_tag = (
            f"web corroboration: {total_indep} {src_word} ({dom_preview}), "
            f"confidence {eff_conf:.2f} \u2014 {achieved_std.value} | "
            f"hazard: {hazard.value}, required: {req_casual.value} ({status_str})"
        )
        if meets_casual:
            guidance = (
                f"Evidentiary burden met ({achieved_std.value}, confidence {eff_conf:.2f} "
                f"across {total_indep} {src_word}: {dom_preview} >= required "
                f"'{req_casual.value}' for {hazard.value} hazard)."
            )
        else:
            guidance = (
                f"Evidentiary burden NOT met for unhedged claim: achieved '{achieved_std.value}' "
                f"(confidence {eff_conf:.2f} from {total_indep} {src_word}: {dom_preview}), "
                f"below the required '{req_casual.value}' threshold for a {hazard.value}-hazard "
                f"query. Express appropriate uncertainty and cite the limited source coverage "
                f"rather than stating the claim as settled fact."
            )

    return WebEvidentiaryBurden(
        query=query_text,
        claim=primary_sent or core_claim,
        hazard=hazard,
        npu_latency_ms=npu_ms,
        corroboration_latency_ms=corrob_ms,
        confidence=eff_conf,
        achieved_standard=achieved_std,
        required_casual_standard=req_casual,
        required_commit_standard=req_commit,
        required_unhedged_standard=req_unhedged,
        meets_casual_burden=meets_casual,
        meets_commit_burden=meets_commit,
        meets_unhedged_burden=meets_unhedged,
        independent_sources_count=total_indep,
        independent_domains=all_indep_domains,
        disputed=is_disputed,
        dispute_sources=dispute_srcs,
        defeater_conditions=conds,
        deep_escalated=deep_escalated,
        summary_tag=summary_tag,
        guidance=guidance,
    )
