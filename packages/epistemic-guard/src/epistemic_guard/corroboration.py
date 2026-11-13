"""Multi-source RAG & open-web corroboration, wire/reprint deduplication, and OpenVINO INT8
evidence + NLI contradiction verification (`web_evidence_int8` + `nli_int8`).
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import numpy as np
import openvino as ov
from tokenizers import Tokenizer

from epistemic_guard.hazard import OpenVINOHazardClassifier
from epistemic_guard.models import resolve_managed_model_dir
from epistemic_guard.nli import OpenVINONLIVerifier
from epistemic_guard.schemas import (
    PROOF_STANDARDS,
    Hazard,
    PassageAssessment,
    ProofStandard,
    WebEvidentiaryBurden,
    standard_for_confidence,
)
from epistemic_guard.web_filters import (
    EPISTEMIC_CONTROVERSY_RE,
    PROHIBITIVE_RE,
    QUERY_CONTROVERSY_INTENT_RE,
    RISK_DECREASE_OR_SAFE_RE,
    RISK_INCREASE_RE,
    SNIPPET_DISPUTE_CUE_RE,
    clean_scraped_passage,
    cluster_near_duplicate_sources,
    detect_conflicting_single_value_numbers,
    extract_anchor_tokens,
    extract_answer_signature,
    extract_registrable_domain,
    extract_specific_anchors,
    filter_relevant_open_web_sources,
    has_unanimous_decimal_measurement,
    select_best_query_sentences,
    shares_verbatim_long_span,
    stem_match,
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
    query_text: str = "",
) -> tuple[list[tuple[str, str]], int]:
    """Collapse same-domain entries and near-duplicate syndicated/mirror copies across domains."""
    raw_quads = [
        (extract_registrable_domain(dom, idx), dom, text, text)
        for idx, (dom, text) in enumerate(items, 1)
    ]
    clusters, collapsed = cluster_near_duplicate_sources(raw_quads, query_text)
    if collapsed > 0 or near_duplicate_threshold >= 0.55:
        unique: list[tuple[str, str]] = []
        extra_collapsed = 0
        for cl in clusters:
            is_dup = any(
                shingle_jaccard_similarity(cl.primary_body_text, prev_t, k=4)
                >= near_duplicate_threshold
                or shingle_jaccard_similarity(cl.primary_body_text, prev_t, k=3)
                >= (near_duplicate_threshold + 0.10)
                for _pd, prev_t in unique
            )
            if is_dup:
                extra_collapsed += 1
            else:
                unique.append((cl.primary_domain, cl.primary_combined_text))
        return unique, collapsed + extra_collapsed
    return [(cl.primary_domain, cl.primary_combined_text) for cl in clusters], collapsed


def _empty_burden(
    query_text: str,
    hazard: Hazard,
    hz_device: str,
    ev_device: str,
    nli_device: str,
    hz_ms: float,
    corrob_ms: float,
    *,
    raw_count: int = 0,
    collapsed: int = 0,
    filtered: int = 0,
    assessments: list[PassageAssessment] | None = None,
    guidance: str = "No usable web evidence available; abstain from stating unverified facts.",
) -> WebEvidentiaryBurden:
    req_casual = required_standard("casual_mention", hazard)
    req_commit = required_standard("memory_commit_inferred", hazard)
    req_unhedged = required_standard("unhedged_assertion", hazard)
    return WebEvidentiaryBurden(
        query=query_text,
        hazard=hazard,
        hazard_device=hz_device,
        evidence_device=ev_device,
        nli_device=nli_device,
        hazard_latency_ms=hz_ms,
        corroboration_latency_ms=corrob_ms,
        confidence=0.0,
        achieved_standard=ProofStandard.SPECULATION,
        required_casual_standard=req_casual,
        required_commit_standard=req_commit,
        required_unhedged_standard=req_unhedged,
        meets_casual_burden=False,
        meets_commit_burden=False,
        meets_unhedged_burden=False,
        raw_sources_count=raw_count,
        deduplicated_duplicates_collapsed=collapsed,
        irrelevant_sources_filtered=filtered,
        passage_assessments=assessments or [],
        summary_tag=f"0 relevant sources | hazard={hazard.value} (ABSTAIN)",
        guidance=guidance,
    )


def evaluate_web_evidence_burden(
    query_text: str,
    search_results: Sequence[Mapping[str, object]],
    *,
    classifier: OpenVINOHazardClassifier | None = None,
    evidence_classifier: OpenVINOWebEvidenceClassifier | None = None,
    nli_verifier: OpenVINONLIVerifier | None = None,
    device: str | None = None,
    near_duplicate_threshold: float = 0.55,
    warn_on_missing: bool = True,
) -> WebEvidentiaryBurden:
    """Evaluate multi-source RAG/web passages for hazard tier, wire duplicates, and disputes."""
    clf = classifier or OpenVINOHazardClassifier(device=device, warn_on_missing=warn_on_missing)
    ev_clf = evidence_classifier or OpenVINOWebEvidenceClassifier(
        device=device, warn_on_missing=warn_on_missing
    )
    nli = nli_verifier or OpenVINONLIVerifier(
        device="CPU" if device is None else device, warn_on_missing=warn_on_missing
    )
    hz_verdict = clf.evaluate(query_text)
    hazard = hz_verdict.hazard

    req_casual = required_standard("casual_mention", hazard)
    req_commit = required_standard("memory_commit_inferred", hazard)
    req_unhedged = required_standard("unhedged_assertion", hazard)

    t0 = time.perf_counter()
    raw_items_with_body: list[tuple[str, str, str, str]] = []
    has_scraped_html = False
    filtered_irrelevant = 0
    assessments: list[PassageAssessment] = []

    for idx, row in enumerate(search_results, 1):
        url = str(row.get("url", "") or row.get("source_url", "") or "").strip()
        raw_dom = str(row.get("domain", "") or row.get("source", "") or url)
        dom = extract_registrable_domain(raw_dom, idx)
        title = str(row.get("title", "") or "").strip()
        snippet = str(row.get("snippet", "") or "").strip()
        preview = str(row.get("content_preview", "") or row.get("content", "") or "").strip()
        body = (
            f"{snippet}. {preview}".strip(". ")
            if (snippet and preview and snippet not in preview)
            else (preview or snippet)
        )
        if preview or len(body) > 350:
            has_scraped_html = True
        combined = (
            f"{title}. {body}".strip(". ") if title and title not in body else (body or title)
        )
        if not combined:
            continue
        if not has_scraped_html:
            _clean_b, is_stub = clean_scraped_passage(combined, title=title)
            if is_stub:
                filtered_irrelevant += 1
                assessments.append(
                    PassageAssessment(domain=dom, stance="IRRELEVANT", confidence=0.95)
                )
                continue
        raw_items_with_body.append((dom, url or dom, combined, body or combined))

    if not raw_items_with_body:
        return _empty_burden(
            query_text,
            hazard,
            hz_verdict.device,
            ev_clf.active_device,
            nli.active_device,
            hz_verdict.latency_ms,
            round((time.perf_counter() - t0) * 1000.0, 3),
            filtered=filtered_irrelevant,
            assessments=assessments,
        )

    nli_con_fn = (lambda a, b: nli.bidirectional_summary(a, b)[0]) if nli.available else None

    if has_scraped_html:
        relevant_items, dropped = filter_relevant_open_web_sources(
            query_text,
            raw_items_with_body,
            neural_stance_fn=ev_clf.score_passage if ev_clf.available else None,
        )
        filtered_irrelevant += len(dropped)
        for d_dom, d_conf in dropped:
            assessments.append(
                PassageAssessment(
                    domain=d_dom,
                    stance="IRRELEVANT",
                    confidence=d_conf,
                    used_neural=ev_clf.available,
                )
            )
        if not relevant_items:
            return _empty_burden(
                query_text,
                hazard,
                hz_verdict.device,
                ev_clf.active_device,
                nli.active_device,
                hz_verdict.latency_ms,
                round((time.perf_counter() - t0) * 1000.0, 3),
                raw_count=len(raw_items_with_body) + len(dropped),
                filtered=filtered_irrelevant,
                assessments=assessments,
                guidance=(
                    "Retrieved web pages did not address the query topic; "
                    "abstain from stating unverified facts."
                ),
            )

        clusters, collapsed_count = cluster_near_duplicate_sources(
            relevant_items, query_text, contradiction_fn=nli_con_fn
        )
        anchors = extract_anchor_tokens(query_text)
        spec_anchors = set(extract_specific_anchors(anchors))
        query_anchors = set(anchors)
        primary = clusters[0]
        primary_dom = primary.primary_domain
        primary_sents = select_best_query_sentences(
            primary.primary_combined_text, query_text, top_k=2
        )
        primary_focus = " ".join(primary_sents)
        primary_focus_1 = primary_sents[0] if primary_sents else primary_focus[:280]
        primary_sig = extract_answer_signature(primary_focus, query_anchors)

        dispute_domains: list[str] = []
        unanimous_constant = has_unanimous_decimal_measurement(query_text, relevant_items)
        prohibitive_ctx = bool(
            PROHIBITIVE_RE.search(query_text)
            and PROHIBITIVE_RE.search(primary_focus)
            and not QUERY_CONTROVERSY_INTENT_RE.search(query_text)
        )

        # 1. Query-aligned controversy / myth-refutation / academic non-consensus
        if not unanimous_constant:
            q_asks_disp = bool(QUERY_CONTROVERSY_INTENT_RE.search(query_text))
            for dom, _url, comb, _body in relevant_items:
                clean_c, _ = clean_scraped_passage(comb)
                sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", clean_c) if s.strip()]
                for idx_s, sent in enumerate(sents):
                    if not EPISTEMIC_CONTROVERSY_RE.search(sent):
                        continue
                    window = " ".join(
                        sents[max(0, idx_s - 1) : min(len(sents), idx_s + 2)]
                    ).lower()
                    w_toks = set(re.findall(r"[a-z0-9]+", window))
                    w_stems = {t[:5] for t in w_toks if len(t) >= 5}
                    if q_asks_disp or any(stem_match(a, w_toks, w_stems) for a in spec_anchors):
                        if dom not in dispute_domains:
                            dispute_domains.append(dom)
                        break

        # 2. Directional clinical/empirical risk opposition
        inc_doms = [d for d, _u, comb, _b in relevant_items if RISK_INCREASE_RE.search(comb)]
        dec_doms = [
            d for d, _u, comb, _b in relevant_items if RISK_DECREASE_OR_SAFE_RE.search(comb)
        ]
        if inc_doms and dec_doms:
            for d in (*inc_doms, *dec_doms):
                if d not in dispute_domains:
                    dispute_domains.append(d)

        # 3. Conflicting single-value years or measurements
        for d in detect_conflicting_single_value_numbers(query_text, relevant_items):
            if d not in dispute_domains:
                dispute_domains.append(d)

        # 4. Pairwise single-sentence NLI contradiction + consensus corroboration
        corroborating_domains: list[str] = [primary_dom]
        accepted_bodies: list[str] = [primary.primary_body_text]
        assessments.append(
            PassageAssessment(
                domain=primary_dom,
                stance="DISPUTES" if primary_dom in dispute_domains else "CORROBORATES",
                confidence=0.90,
                used_neural=nli.available or ev_clf.available,
            )
        )

        for other in clusters[1:]:
            if any(
                shares_verbatim_long_span(other.primary_body_text, prev_b)
                for prev_b in accepted_bodies
            ):
                collapsed_count += 1
                continue

            other_sents = select_best_query_sentences(
                other.primary_combined_text, query_text, top_k=2
            )
            other_focus = " ".join(other_sents)
            other_focus_1 = other_sents[0] if other_sents else other_focus[:280]
            max_con, max_ent = (
                nli.bidirectional_summary(primary_focus_1, other_focus_1)
                if nli.available
                else (0.0, 0.0)
            )

            # High-precision NLI contradiction across query-aligned single sentences
            p_neg = bool(SNIPPET_DISPUTE_CUE_RE.search(primary_focus_1))
            o_neg = bool(SNIPPET_DISPUTE_CUE_RE.search(other_focus_1))
            if (
                not unanimous_constant
                and not prohibitive_ctx
                and max_con >= 0.94
                and p_neg != o_neg
                and other.primary_domain not in dispute_domains
            ):
                dispute_domains.append(other.primary_domain)

            if other.primary_domain in dispute_domains:
                assessments.append(
                    PassageAssessment(
                        domain=other.primary_domain,
                        stance="DISPUTES",
                        confidence=max(round(max_con, 4), 0.90),
                        used_neural=nli.available,
                    )
                )
                continue

            other_sig = extract_answer_signature(other_focus, query_anchors)
            shared_sig = primary_sig & other_sig
            if len(shared_sig) >= 1 or (max_ent >= 0.28 and max_con < 0.75):
                if other.primary_domain not in corroborating_domains:
                    corroborating_domains.append(other.primary_domain)
                    accepted_bodies.append(other.primary_body_text)
                assessments.append(
                    PassageAssessment(
                        domain=other.primary_domain,
                        stance="CORROBORATES",
                        confidence=max(round(max_ent, 4), 0.80),
                        used_neural=nli.available,
                    )
                )
    else:
        # Concise RAG / wire-snippet corroboration mode
        clusters, collapsed_count = cluster_near_duplicate_sources(
            raw_items_with_body, query_text, contradiction_fn=nli_con_fn
        )
        if near_duplicate_threshold < 0.55 and len(clusters) > 1:
            kept_cl = [clusters[0]]
            for cl in clusters[1:]:
                if any(
                    shingle_jaccard_similarity(cl.primary_body_text, p.primary_body_text, k=4)
                    >= near_duplicate_threshold
                    for p in kept_cl
                ):
                    collapsed_count += 1
                else:
                    kept_cl.append(cl)
            clusters = kept_cl

        primary = clusters[0]
        primary_dom = primary.primary_domain
        primary_text = primary.primary_combined_text
        q_content_tokens = {t for t in _word_tokens(query_text) if t not in _STOPWORDS}
        primary_tokens = {t for t in _word_tokens(primary_text) if t not in _STOPWORDS}
        prohibitive_ctx = bool(
            PROHIBITIVE_RE.search(query_text) and PROHIBITIVE_RE.search(primary_text)
        )

        corroborating_domains = []
        dispute_domains = []

        for idx, cl in enumerate(clusters):
            dom = cl.primary_domain
            text = cl.primary_combined_text
            toks = {t for t in _word_tokens(text) if t not in _STOPWORDS}
            q_overlap = len(q_content_tokens & toks)
            joint_overlap = len((q_content_tokens | primary_tokens) & toks)

            neural_stance, neural_conf = (
                ev_clf.score_passage(query_text, text)
                if ev_clf.available
                else ("CORROBORATES", 0.5)
            )

            if idx > 0 and joint_overlap == 0:
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
                and neural_conf >= 0.88
                and q_overlap <= 1
            ):
                filtered_irrelevant += 1
                assessments.append(
                    PassageAssessment(
                        domain=dom, stance="IRRELEVANT", confidence=neural_conf, used_neural=True
                    )
                )
                continue

            nli_con = (
                nli.bidirectional_summary(primary.primary_body_text, cl.primary_body_text)[0]
                if (idx > 0 and nli.available)
                else 0.0
            )
            explicit_controversy = bool(EPISTEMIC_CONTROVERSY_RE.search(text))
            explicit_refute = (
                idx > 0
                and not prohibitive_ctx
                and bool(SNIPPET_DISPUTE_CUE_RE.search(text))
                != bool(SNIPPET_DISPUTE_CUE_RE.search(primary_text))
            )
            is_disp = (
                explicit_controversy
                or explicit_refute
                or (idx > 0 and nli_con >= 0.95)
                or (
                    ev_clf.available
                    and neural_stance == "DISPUTES"
                    and neural_conf >= 0.90
                    and not prohibitive_ctx
                )
            )
            if is_disp:
                if dom not in dispute_domains:
                    dispute_domains.append(dom)
                if idx == 0 and dom not in corroborating_domains:
                    corroborating_domains.append(dom)
                assessments.append(
                    PassageAssessment(
                        domain=dom,
                        stance="DISPUTES",
                        confidence=max(round(nli_con, 4), neural_conf, 0.90),
                        used_neural=nli.available or ev_clf.available,
                    )
                )
            else:
                if dom not in corroborating_domains:
                    corroborating_domains.append(dom)
                assessments.append(
                    PassageAssessment(
                        domain=dom,
                        stance="CORROBORATES",
                        confidence=neural_conf if ev_clf.available else 0.80,
                        used_neural=ev_clf.available,
                    )
                )

    is_disputed = len(dispute_domains) > 0
    indep_count = len(corroborating_domains)

    if indep_count == 0 and not is_disputed:
        return _empty_burden(
            query_text,
            hazard,
            hz_verdict.device,
            ev_clf.active_device,
            nli.active_device,
            hz_verdict.latency_ms,
            round((time.perf_counter() - t0) * 1000.0, 3),
            raw_count=len(search_results),
            collapsed=collapsed_count,
            filtered=filtered_irrelevant,
            assessments=assessments,
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
        nli_device=nli.active_device,
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
        raw_sources_count=len(search_results),
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
