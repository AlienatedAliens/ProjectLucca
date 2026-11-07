"""
Project Lucca — Deduplicated Walton Critical-Question Evaluators (WO-43 Phase 3.1)
Spec: plans/wo43_refactor_and_power/03_PHASE3_DOMAIN_GOD_OBJECTS_DEDUP_AND_DECOMPOSITION_SPEC.md §1
Consolidates the 5 Walton argumentation scheme evaluators (Authority, Sign, Analogy,
Consequence, Precedent) onto 3 shared, parameterized evidence-gathering helpers:
1. `extract_normalized_receipt_text`
2. `collect_independent_corroboration`
3. `collect_dispute_evidence`
plus `evaluate_q1_observation_and_memory`.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from types import ModuleType
from typing import TYPE_CHECKING, Final

import structlog

from lucca.core.schemas import InferenceStep, VerifierLabel
from lucca.memory.latent_probe import (
    BelnapLatentInvestigator,
    BelnapValue,
    has_structural_proposition_conflict,
)

if TYPE_CHECKING:
    from lucca.core.corroboration import CQAnswer, CriticalQuestionResult, Scheme
    from lucca.ports import SemanticVerifierPort
logger = structlog.get_logger(__name__)
_RE_RATIFICATION_POSITIVE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:ratif\w*|binding|grounding[\-\s]eligible|upheld|affirm\w*|establish\w*)\b",
    re.IGNORECASE,)
_RE_CONGRUENCE_POSITIVE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:congruen\w*|match\w*|parallel\w*|identical\w*)\b", re.IGNORECASE,)
_SQL_BASE_MEM: Final[str] = ("SELECT m.entry_id, m.content, e.signer_id FROM memories m "
    "JOIN provenance_envelopes e ON m.entry_id = e.entry_id "
    "WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL")


def _cb() -> ModuleType:
    import lucca.core.corroboration as cb  # noqa: PLC0415
    return cb


def extract_normalized_receipt_text(receipt: object) -> str:
    """Extracts and lowercases combined output/content/structured text from a receipt."""
    out = getattr(receipt, "output", "") or ""
    cnt = getattr(receipt, "content", "") or ""
    st = getattr(receipt, "structured", "") or ""
    return f"{out} {cnt} {st}".lower()


def _receipt_cid(receipt: object) -> str:
    return str(getattr(receipt, "call_id", "") or getattr(receipt, "entry_id", "") or "rcpt")


def _make_cq(question: str, answer: CQAnswer, ids: list[str], sources: list[str],
    detail: str, scheme: Scheme, count_override: int | None = None,) -> CriticalQuestionResult:
    cnt = count_override if count_override is not None else len(ids)
    return _cb().CriticalQuestionResult(  # type: ignore[no-any-return]
        question=question, answer=answer, count=cnt, evidence_entry_ids=ids,
        sources=sources, detail=detail, scheme=scheme.value,)


def _make_q1_cq(question: str, matches: list[str], failed: bool, receipts: Sequence[object],
    ok_detail: str, fail_detail: str, unobserved_detail: str, scheme: Scheme,
) -> CriticalQuestionResult:
    cb = _cb()
    ok = bool(matches and not failed)
    srcs = ([cb.extract_receipt_source(receipts[0])] if receipts else ["store"]) if ok else []
    detail = ok_detail if ok else (fail_detail if failed else unobserved_detail)
    ans = cb.CQAnswer.SATISFIED if ok else cb.CQAnswer.FAILED
    return _make_cq(question, ans, matches if ok else [], srcs, detail, scheme)


def _make_corrob_cq(question: str, ind_sources: list[str], corrob_ids: list[str],
    ok_prefix: str, unk_detail: str, scheme: Scheme,) -> CriticalQuestionResult:
    cb = _cb()
    detail = (f"{ok_prefix} {len(ind_sources)} independent sources: {', '.join(ind_sources)}"
        if ind_sources else unk_detail)
    ans = cb.CQAnswer.SATISFIED if ind_sources else cb.CQAnswer.UNKNOWN
    return _make_cq(question, ans, corrob_ids, ind_sources, detail, scheme, len(ind_sources))


def _make_dispute_cq(question: str, ids: list[str], sources: list[str], details: list[str],
    fallback_found: str, unk_detail: str, scheme: Scheme,) -> CriticalQuestionResult:
    cb = _cb()
    detail = (details[0] if details else fallback_found) if ids else unk_detail
    ans = cb.CQAnswer.SATISFIED if ids else cb.CQAnswer.UNKNOWN
    return _make_cq(question, ans, ids, sources, detail, scheme)


def evaluate_q1_observation_and_memory(
    claim: str, step: InferenceStep, store: object, receipts: Sequence[object],
    verifier: SemanticVerifierPort | None, term_a_lower: str, term_b_lower: str,
    fail_on_receipt_fn: Callable[[str], bool], match_receipt_fn: Callable[[str, bool, float], bool],
    initial_matches: Sequence[str] = (), initial_failed: bool = False,) -> tuple[list[str], bool]:
    """Shared CQ1 evaluator across Sign, Analogy, Consequence, and Precedent schemes."""
    cb = _cb()
    q1_matches, q1_failed = list(initial_matches), initial_failed
    for r in receipts:
        r_text = extract_normalized_receipt_text(r)
        if not getattr(r, "ok", True):
            q1_failed = True
            break
        is_aligned, align_score, has_conflict = cb.compute_proposition_alignment(
            claim, r_text, step=step, verifier=verifier)
        if fail_on_receipt_fn(r_text):
            q1_failed = True
            break
        if match_receipt_fn(r_text, is_aligned, align_score) and not has_conflict:
            q1_matches.append(_receipt_cid(r))
    db = getattr(store, "db", None) if (not q1_matches and not q1_failed and store) else None
    if db is not None and hasattr(db, "read_cursor"):
        try:
            with db.read_cursor() as cur:
                cur.execute(f"{_SQL_BASE_MEM} AND (m.content LIKE ? OR m.content LIKE ?)",
                    (f"%{term_a_lower}%", f"%{term_b_lower}%"),)
                q1_matches.extend(str(row[0]) for row in cur.fetchall())
        except Exception as exc:  # noqa: BLE001
            logger.debug("walton_q1_db_error", error=str(exc))
    return (q1_matches, q1_failed)


def collect_independent_corroboration(
    claim: str, sql_where: str, sql_params: Sequence[str], step: InferenceStep,
    store: object, receipts: Sequence[object], verifier: SemanticVerifierPort | None,
    initial_sources: Sequence[str] = (), initial_signers: Sequence[str] = (),
    require_db_alignment: bool = False, receipt_match_fn: Callable[[str, bool], bool] | None = None,
) -> tuple[list[str], list[str]]:
    """Shared independent-source corroboration collector across store and receipts."""
    cb = _cb()
    claim_lower = claim.lower()
    seen_sources, seen_signer_types = list(initial_sources), list(initial_signers)
    independent_sources, corrob_entry_ids = [], []
    db = getattr(store, "db", None) if store is not None else None
    if db is not None and hasattr(db, "read_cursor"):
        try:
            with db.read_cursor() as cur:
                query = (
                    "SELECT m.entry_id, m.content, e.signer_id, e.payload_json FROM memories m "  # noqa: S608
                    "JOIN provenance_envelopes e ON m.entry_id = e.entry_id "
                    f"WHERE e.grounding_eligible = 1 AND m.valid_to IS NULL AND ({sql_where})"
                )
                cur.execute(query, tuple(sql_params))
                for eid, content, signer, payload_json_str in cur.fetchall():
                    src, row_signer_type = signer or "store", str(signer or "")
                    if payload_json_str:
                        try:
                            pj = json.loads(payload_json_str)
                            st = pj.get("structured") if isinstance(pj, dict) else None
                            src = ((st.get("source") if isinstance(st, dict) else None)
                                or (pj.get("signer_id") if isinstance(pj, dict) else None) or src)
                            row_signer_type = str(
                                pj.get("provenance") or pj.get("signer_id") or row_signer_type)
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("payload_json_parse_error", error=str(exc))
                    src_str = str(src).strip()
                    if require_db_alignment:
                        is_aligned, _, has_conflict = cb.compute_proposition_alignment(
                            claim, str(content or ""), step=step, verifier=verifier)
                        content_lower = str(content or "").lower()
                        if not ((claim_lower in content_lower or is_aligned) and not has_conflict):
                            continue
                    if src_str and all(cb.verify_source_independence(src_str, s, row_signer_type,
                            seen_signer_types[i] if i < len(seen_signer_types) else "",)
                        for i, s in enumerate(seen_sources)):
                        seen_sources.append(src_str)
                        seen_signer_types.append(row_signer_type)
                        independent_sources.append(src_str)
                        corrob_entry_ids.append(str(eid))
        except Exception as exc:  # noqa: BLE001
            logger.debug("corroboration_db_lookup_failed", error=str(exc))
    match_fn = receipt_match_fn or (lambda r_txt, aligned: claim_lower in r_txt or aligned)
    for r in receipts:
        r_text = extract_normalized_receipt_text(r)
        r_source, r_signer = cb.extract_receipt_source(r).strip(), cb.extract_receipt_signer_type(r)
        if (not r_source or r_source.lower() in ("fetch_url", "web_search", "search_web", "tool")
            or not all(cb.verify_source_independence(r_source, s, r_signer,
                    seen_signer_types[i] if i < len(seen_signer_types) else "",)
                for i, s in enumerate(seen_sources))):
            continue
        is_aligned, _, has_conflict = cb.compute_proposition_alignment(
            claim, r_text, step=step, verifier=verifier)
        if match_fn(r_text, is_aligned) and not has_conflict:
            seen_sources.append(r_source)
            seen_signer_types.append(r_signer)
            independent_sources.append(r_source)
            corrob_entry_ids.append(_receipt_cid(r))
    return (independent_sources, corrob_entry_ids)


def collect_dispute_evidence(
    claim: str, step: InferenceStep, store: object, receipts: Sequence[object],
    verifier: SemanticVerifierPort | None, receipt_predicate: Callable[[str, float, bool], bool],
    receipt_detail_fn: Callable[[str], str],
    sql_like_clauses: Sequence[tuple[str, Sequence[str], bool]],
    check_subject_predicate_mismatch: bool = False,
    use_raw_receipt_source: bool = False, db_first: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    """Shared dispute/counter-evidence collector across receipts and grounding store."""
    cb = _cb()
    dispute_entry_ids, dispute_sources, dispute_details = [], [], []
    def _scan_db() -> None:
        db = getattr(store, "db", None) if store is not None else None
        if db is None or not hasattr(db, "read_cursor"):
            return
        try:
            with db.read_cursor() as cur:
                if check_subject_predicate_mismatch and step.s and step.p:
                    cur.execute(f"{_SQL_BASE_MEM} AND m.content LIKE ?", (f"{step.s} {step.p} %",))
                    for eid, content, signer in cur.fetchall():
                        parts = content.strip().split()
                        if len(parts) >= 3 and parts[2].lower() != step.o.lower():
                            dispute_entry_ids.append(str(eid))
                            dispute_sources.append(str(signer or "memory"))
                            dispute_details.append(f"{content} contradicts {claim}")
                for where_clause, params, require_adv in sql_like_clauses:
                    cur.execute(f"{_SQL_BASE_MEM} AND ({where_clause})", tuple(params))
                    for eid, content, signer in cur.fetchall():
                        if require_adv and not bool(
                            cb._RE_ADVERSATIVE_DEFEATER.search(str(content or ""))):
                            continue
                        if str(eid) not in dispute_entry_ids:
                            dispute_entry_ids.append(str(eid))
                            dispute_sources.append(str(signer or "memory"))
                            dispute_details.append(f"{content}")
        except Exception as exc:  # noqa: BLE001
            logger.debug("dispute_db_lookup_failed", error=str(exc))
    def _scan_receipts() -> None:
        for r in receipts:
            r_text = extract_normalized_receipt_text(r)
            _, align_score, has_conflict = cb.compute_proposition_alignment(
                claim, r_text, step=step, verifier=verifier)
            if receipt_predicate(r_text, align_score, has_conflict):
                src = (str(getattr(r, "source", "") or getattr(r, "tool", "") or "receipt")
                    if use_raw_receipt_source else cb.extract_receipt_source(r))
                dispute_entry_ids.append(_receipt_cid(r))
                dispute_sources.append(src)
                dispute_details.append(receipt_detail_fn(src))
    if db_first:
        _scan_db()
        _scan_receipts()
    else:
        _scan_receipts()
        _scan_db()
    return (dispute_entry_ids, dispute_sources, dispute_details)


def _extract_asserting_source(step: InferenceStep) -> tuple[str, str]:
    for prem in step.premises:
        m = re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE)
        if m:
            return (m.group(1).strip(), m.group(2).strip())
    return ("", f"{step.s} {step.p} {step.o}".strip())


def _non_unspec(src: str) -> list[str]:
    return [src] if (src and src != "unspecified") else []


def _evaluate_authority_questions(
    step: InferenceStep, store: object = None, receipts: Sequence[object] = (),
    verifier: SemanticVerifierPort | None = None,) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Position to Know / Authority critical questions."""
    cb = _cb()
    raw_src, claim = _extract_asserting_source(step)
    asserting_source = raw_src or "unspecified"
    claim_lower, source_lower = claim.lower(), asserting_source.lower()
    q1_matches, primary_signer_type = [], ""
    for r in receipts:
        if not getattr(r, "ok", True):
            continue
        text, r_source = extract_normalized_receipt_text(r), cb.extract_receipt_source(r).lower()
        is_aligned, _, has_conflict = cb.compute_proposition_alignment(
            claim, text, step=step, verifier=verifier)
        if (claim_lower in text or is_aligned) and not has_conflict and (
            source_lower in text or source_lower in r_source
            or cb.is_same_source(asserting_source, r_source) or asserting_source == "unspecified"):
            q1_matches.append(_receipt_cid(r))
            if not primary_signer_type:
                primary_signer_type = cb.extract_receipt_signer_type(r)
    q1_res = _make_cq(cb.Q_AUTH_SIGNED_RECEIPT,
        cb.CQAnswer.SATISFIED if q1_matches else cb.CQAnswer.FAILED,
        q1_matches, [asserting_source] if q1_matches else [],
        f"Signed receipt proved {asserting_source} asserted '{claim}'"
        if q1_matches else f"No signed receipt found proving {asserting_source} asserted '{claim}'",
        cb.Scheme.AUTHORITY,)
    ind_sources, corrob_ids = collect_independent_corroboration(
        claim, "m.content = ? OR m.content = ? OR m.content LIKE ?",
        (claim, claim_lower, f"%{claim_lower}%"), step, store, receipts, verifier,
        _non_unspec(asserting_source), [primary_signer_type] if primary_signer_type else [],
        require_db_alignment=True,)
    q2_res = _make_corrob_cq(cb.Q_AUTH_INDEPENDENT_CORROB, ind_sources, corrob_ids,
        "Corroborated by", "No independent corroboration found", cb.Scheme.AUTHORITY,)
    disp_ids, disp_sources, disp_details = collect_dispute_evidence(
        claim, step, store, receipts, verifier, lambda r_txt, score, conflict: conflict and (
            score >= 0.25 or claim_lower in r_txt or bool(step.s and step.s.lower() in r_txt)
            or bool(cb._RE_NEGATION_POLARITY.search(r_txt))),
        lambda src: f"{src} reports dispute for {claim}", [(
            "m.content LIKE ? OR m.content LIKE ? OR m.content LIKE ?",
            (f"%disputes {claim_lower}%", f"%not_{step.p}%", f"%does_not_{step.p}%"), False,)],
        check_subject_predicate_mismatch=True, use_raw_receipt_source=True, db_first=True,)
    q3_res = _make_dispute_cq(cb.Q_AUTH_DISPUTE, disp_ids, disp_sources, disp_details,
        f"Dispute found for '{claim}'", "No disputes found", cb.Scheme.AUTHORITY,)
    return [q1_res, q2_res, q3_res]


def _evaluate_sign_questions(
    step: InferenceStep, store: object = None, receipts: Sequence[object] = (),
    verifier: SemanticVerifierPort | None = None,) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Sign critical questions."""
    cb = _cb()
    sign, condition = step.s.strip(), step.o.strip()
    claim = f"{step.s} {step.p} {step.o}".strip()
    sign_lower, cond_lower = sign.lower(), condition.lower()
    q1_matches, q1_failed = evaluate_q1_observation_and_memory(
        claim, step, store, receipts, verifier, sign_lower, cond_lower,
        lambda r_txt: bool(cb._RE_NEGATION_POLARITY.search(r_txt))
        and not bool(cb._RE_ADVERSATIVE_DEFEATER.search(r_txt)), lambda r_txt, aligned, score: (
            aligned or score >= 0.35 or sign_lower in r_txt or cond_lower in r_txt
            or any(p.lower() in r_txt for p in step.premises)),)
    q1_res = _make_q1_cq(cb.Q_SIGN_CORRELATION, q1_matches, q1_failed, receipts,
        f"Observed sign '{sign}' reliably correlates with '{condition}'",
        f"Sign correlation for '{claim}' is unreliable or unobserved",
        f"No observation confirming sign '{sign}' correlates with '{condition}'", cb.Scheme.SIGN,)
    ind_sources, corrob_ids = collect_independent_corroboration(
        claim, "m.content LIKE ? OR m.content LIKE ?", (f"%{sign_lower}%", f"%{cond_lower}%"),
        step, store, receipts[1:] if len(receipts) > 1 else (), verifier,
        [cb.extract_receipt_source(receipts[0])] if receipts else [],
        [cb.extract_receipt_signer_type(receipts[0])] if receipts else [],
        receipt_match_fn=lambda r_txt, aligned: (
            sign_lower in r_txt or cond_lower in r_txt or aligned),)
    q2_res = _make_corrob_cq(cb.Q_SIGN_INDEPENDENT_CORROB, ind_sources, corrob_ids,
        "Sign corroborated by", "No independent corroboration found for the sign", cb.Scheme.SIGN,)
    disp_ids, disp_sources, disp_details = collect_dispute_evidence(
        claim, step, store, receipts, verifier, lambda r_txt, score, conflict: conflict and (
            score >= 0.20 or sign_lower in r_txt or cond_lower in r_txt
            or bool(cb._RE_ADVERSATIVE_DEFEATER.search(r_txt))),
        lambda src: f"{src} reports alternative explanation or dispute for sign '{sign}'", [(
            "m.content LIKE ? OR m.content LIKE ? OR m.content LIKE ?",
            (f"%alternative%{sign_lower}%", f"%disputes%{sign_lower}%", f"%not_{cond_lower}%"),
            False,)],)
    q3_res = _make_dispute_cq(cb.Q_SIGN_DISPUTE, disp_ids, disp_sources, disp_details,
        f"Dispute found for sign '{sign}'", "No alternative explanation or dispute found",
        cb.Scheme.SIGN,)
    return [q1_res, q2_res, q3_res]


def _evaluate_binary_relation_scheme(
    step: InferenceStep, store: object, receipts: Sequence[object],
    verifier: SemanticVerifierPort | None, scheme: Scheme, cue_regex: re.Pattern[str],
    q1_id: str, q1_ok: str, q1_fail: str, q1_unobs: str,
    q2_id: str, q2_rcpt_detail_fn: Callable[[str], str],
    q2_clauses: Sequence[tuple[str, Sequence[str], bool]], q2_fb: str, q2_unk: str,
    q3_id: str, q3_ok_prefix: str, q3_unk: str,
    init_matches: Sequence[str] = (), init_failed: bool = False,) -> list[CriticalQuestionResult]:
    cb = _cb()
    term_a_lower, term_b_lower = step.s.strip().lower(), step.o.strip().lower()
    claim = f"{step.s} {step.p} {step.o}".strip()
    asserting_source, _ = _extract_asserting_source(step)
    q1_matches, q1_failed = evaluate_q1_observation_and_memory(
        claim, step, store, receipts, verifier, term_a_lower, term_b_lower,
        lambda r_txt: bool(cb._RE_NEGATION_POLARITY.search(r_txt))
        and not bool(cb._RE_ADVERSATIVE_DEFEATER.search(r_txt)), lambda r_txt, aligned, score: (
            aligned or score >= 0.35 or bool(cue_regex.search(r_txt))
            or (term_a_lower in r_txt and term_b_lower in r_txt)
            or any(p.lower() in r_txt for p in step.premises)), init_matches, init_failed,)
    q1_res = _make_q1_cq(q1_id, q1_matches, q1_failed, receipts, q1_ok, q1_fail, q1_unobs, scheme)
    disp_ids, disp_sources, disp_details = collect_dispute_evidence(
        claim, step, store, receipts, verifier, lambda r_txt, score, conflict: conflict
        and (bool(cb._RE_ADVERSATIVE_DEFEATER.search(r_txt)) or score >= 0.20),
        q2_rcpt_detail_fn, q2_clauses,)
    q2_res = _make_dispute_cq(q2_id, disp_ids, disp_sources, disp_details, q2_fb, q2_unk, scheme)
    term_b_clean = term_b_lower.replace("_", " ")
    ind_sources, corrob_ids = collect_independent_corroboration(
        claim, "m.content LIKE ?", (f"%{term_b_lower}%",), step, store, receipts, verifier,
        _non_unspec(asserting_source), receipt_match_fn=lambda r_txt, aligned: (
            aligned or term_b_lower in r_txt or term_b_clean in r_txt
            or any(w in r_txt for w in re.split(r"[_\s]+", term_b_lower) if len(w) > 2)),)
    q3_res = _make_corrob_cq(q3_id, ind_sources, corrob_ids, q3_ok_prefix, q3_unk, scheme)
    return [q1_res, q2_res, q3_res]


def _evaluate_analogy_questions(
    step: InferenceStep, store: object = None, receipts: Sequence[object] = (),
    verifier: SemanticVerifierPort | None = None,) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Analogy critical questions."""
    cb = _cb()
    case_a, case_b = step.s.strip(), step.o.strip()
    init_matches, init_failed = [], False
    if verifier is not None and case_a and case_b:
        try:
            r_ab = verifier.check_consistency(premise=case_a, hypothesis=case_b)
            r_ba = verifier.check_consistency(premise=case_b, hypothesis=case_a)
            labels = (r_ab.label, r_ba.label)
            if not r_ab.degraded and not r_ba.degraded:
                if VerifierLabel.CONTRADICTION in labels:
                    init_failed = True
                elif VerifierLabel.ENTAILMENT in labels:
                    init_matches.append("semantic_entailment")
            if r_ab.degraded or r_ba.degraded or VerifierLabel.UNCERTAIN in labels:
                lex_conflict = has_structural_proposition_conflict(case_a, case_b)
                verdict = BelnapLatentInvestigator.evaluate_nli_verdict(
                    r_ab, has_lexical_conflict=lex_conflict)
                if verdict == BelnapValue.BOTH:
                    init_failed = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("analogy_verifier_eval_failed", error=str(exc))
    return _evaluate_binary_relation_scheme(
        step, store, receipts, verifier, cb.Scheme.ANALOGY, cb._RE_ANALOGY,
        cb.Q_ANALOGY_SIMILARITY,
        f"Relevant similarity established between '{case_a}' and '{case_b}'",
        f"Analogy defeated: cases '{case_a}' and '{case_b}' lack relevant similarity",
        f"No evidence establishing relevant similarity between '{case_a}' and '{case_b}'",
        cb.Q_ANALOGY_DIFFERENCES, lambda src: (
            f"{src} reports critical difference defeating analogy between '{case_a}' and '{case_b}'"
        ), [("m.content LIKE ? OR m.content LIKE ?",
            (f"%{case_a.lower()}%", f"%{case_b.lower()}%"), True,)],
        f"Critical difference defeats analogy between '{case_a}' and '{case_b}'",
        "No defeating differences found", cb.Q_ANALOGY_INDEPENDENT_CORROB,
        "Source case facts corroborated by", "No independent corroboration of source case facts",
        init_matches, init_failed,)


def _evaluate_consequence_questions(
    step: InferenceStep, store: object = None, receipts: Sequence[object] = (),
    verifier: SemanticVerifierPort | None = None,) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Consequences critical questions."""
    cb = _cb()
    action, consequence = step.s.strip(), step.o.strip()
    return _evaluate_binary_relation_scheme(
        step, store, receipts, verifier, cb.Scheme.CONSEQUENCE, cb._RE_CONSEQUENCE,
        cb.Q_CONSEQ_PLAUSIBLE,
        f"Plausible consequence established: '{action}' leads to '{consequence}'",
        f"Causal link implausible: '{action}' does not lead to '{consequence}'",
        f"No evidence establishing that '{action}' leads to '{consequence}'",
        cb.Q_CONSEQ_COUNTERVAILING,
        lambda src: f"{src} reports countervailing consequence for '{action}'",
        [("m.content LIKE ?", (f"%{action.lower()}%",), True)],
        f"Countervailing consequence identified for '{action}'",
        "No countervailing consequences found", cb.Q_CONSEQ_INDEPENDENT_CORROB,
        "Consequence confirmed by", "No independent empirical confirmation of consequence",)


def _evaluate_precedent_questions(
    step: InferenceStep, store: object = None, receipts: Sequence[object] = (),
    verifier: SemanticVerifierPort | None = None,) -> list[CriticalQuestionResult]:
    """Evaluates Walton Argument from Precedent critical questions."""
    cb = _cb()
    current_case, ruling = step.s.strip(), step.o.strip()
    claim = f"{step.s} {step.p} {step.o}".strip()
    case_lower, ruling_lower = current_case.lower(), ruling.lower()
    q1_matches, q1_failed = evaluate_q1_observation_and_memory(
        claim, step, store, receipts, verifier, case_lower, ruling_lower,
        lambda r_txt: bool(re.search(r"\b(?:incongruen\w*|distinguish\w*)\b", r_txt)),
        lambda r_txt, aligned, score: (
            aligned or score >= 0.35 or bool(_RE_CONGRUENCE_POSITIVE.search(r_txt))
            or (case_lower in r_txt and ruling_lower in r_txt)
            or any(p.lower() in r_txt for p in step.premises)),)
    q1_res = _make_q1_cq(cb.Q_PREC_FACT_CONGRUENCE, q1_matches, q1_failed, receipts,
        f"Precedent facts congruent with current case '{current_case}'",
        f"Precedent facts incongruent or distinguishable for '{ruling}'",
        f"No evidence establishing factual congruence for precedent '{ruling}'",
        cb.Scheme.PRECEDENT,)
    is_superseded, is_ratified, q2_detail, q2_eids, q2_sources = False, False, "", [], []
    for r in receipts:
        r_text = extract_normalized_receipt_text(r)
        src, cid = cb.extract_receipt_source(r), _receipt_cid(r)
        if bool(cb._RE_NEGATION_POLARITY.search(r_text)) and not bool(
            cb._RE_ADVERSATIVE_DEFEATER.search(r_text)):
            is_superseded = True
            q2_detail = f"{src} reports precedent for '{ruling}' was overturned or superseded"
            q2_eids.append(cid)
            q2_sources.append(src)
            break
        if bool(_RE_RATIFICATION_POSITIVE.search(r_text)):
            is_ratified = True
            q2_detail = f"Prior decision '{ruling}' was ratified and remains binding"
            q2_eids.append(cid)
            q2_sources.append(src)
    db = getattr(store, "db", None) if (not is_superseded and store is not None) else None
    if db is not None and hasattr(db, "read_cursor"):
        try:
            with db.read_cursor() as cur:
                cur.execute(f"{_SQL_BASE_MEM} AND (m.content LIKE ? OR m.content LIKE ?)",
                    (f"%{case_lower}%", f"%{ruling_lower}%"),)
                for row in cur.fetchall():
                    if bool(cb._RE_NEGATION_POLARITY.search(str(row[1] or "").lower())):
                        is_superseded = True
                        q2_detail = (
                            f"Prior decision '{ruling}' was overturned or superseded: {row[1]}")
                        q2_eids.append(str(row[0]))
                        q2_sources.append(str(row[2] or "store"))
                        break
                    is_ratified = True
                    q2_eids.append(str(row[0]))
                    q2_sources.append(str(row[2] or "store"))
                if is_ratified and not is_superseded:
                    q2_detail = f"Prior decision '{ruling}' found ratified in grounding store"
        except Exception as exc:  # noqa: BLE001
            logger.debug("precedent_q2_db_error", error=str(exc))
    q2_active = is_superseded or is_ratified
    q2_ans = (cb.CQAnswer.FAILED if is_superseded
        else (cb.CQAnswer.SATISFIED if is_ratified else cb.CQAnswer.UNKNOWN))
    if is_superseded:
        q2_det = q2_detail or f"Precedent for '{ruling}' was overturned or superseded"
    elif is_ratified:
        q2_det = q2_detail or f"Prior decision '{ruling}' was ratified and remains binding"
    else:
        q2_det = "Precedent ratification status unconfirmed"
    q2_res = _make_cq(cb.Q_PREC_RATIFIED, q2_ans, q2_eids if q2_active else [],
        q2_sources if q2_active else [], q2_det, cb.Scheme.PRECEDENT,)
    comp_ids, comp_sources, comp_details = collect_dispute_evidence(
        claim, step, store, receipts, verifier,
        lambda r_txt, _score, _conflict: bool(cb._RE_ADVERSATIVE_DEFEATER.search(r_txt)),
        lambda src: f"{src} reports competing precedent for '{ruling}'",
        [("m.content LIKE ? OR m.content LIKE ?", (f"%{case_lower}%", f"%{ruling_lower}%"), True)],
    )
    q3_res = _make_dispute_cq(cb.Q_PREC_COMPETING, comp_ids, comp_sources, comp_details,
        f"Competing precedent on record for '{ruling}'", "No competing precedents found",
        cb.Scheme.PRECEDENT,)
    return [q1_res, q2_res, q3_res]
