"""
Project Lucca — Deduction, Walton Corroboration, Ratification & Planning Runner (WO-43 Phase 2, Sub-Step 2.5)
Spec D-REAS-09, WO-20, WO-21, WO-22, WO-23

Encapsulates rule chain evaluation, abductive deduction with the bounded Gather Ladder,
Walton critical-question corroboration, web-fact ratification & cross-reference,
and means-ends GoalPlan validation and execution.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import TYPE_CHECKING
import urllib.parse

from pydantic import JsonValue, ValidationError
import structlog
import ulid

from lucca.brain.prompt_builder import build_planning_messages
from lucca.core.coherence import ToolReceipt
from lucca.core.corroboration import (
    CQAnswer,
    CriticalQuestionResult,
    Scheme,
    adjust_confidence,
    critical_questions,
    detect_premise_scheme,
    extract_receipt_source,
)
from lucca.core.proof_policy import (
    meets_standard,
    required_standard,
    required_threshold,
)
from lucca.core.reasoning_context import ProofTraceStep, ReasoningContext, ReasoningEntry
from lucca.core.schemas import (
    AssertFact,
    GoalPlan,
    InferenceStep,
    PendingRatification,
    Provenance,
    RetrievalQuery,
    RuleOutcome,
    RuleState,
    SignedPayload,
    TokenDelta,
    UnsignedPayload,
    standard_for_confidence,
)
from lucca.core.trace import TurnTrace
from lucca.core.turn_pipeline import synthesize_plan_narration
from lucca.sandbox.schemas import EXTRA_TOOL_SCHEMAS, TOOL_ARG_SCHEMAS
from lucca.senses.ring_buffer import FLAG_EOS

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


class DeductionAndPlanningRunner:
    """Executes deductive rule chains, abductive gather-ladder reasoning, Walton corroboration, and GoalPlan steps."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orch = orchestrator

    def evaluate_rules_chain(
        self,
        state: RuleState,
        trace: TurnTrace | None = None,
        max_depth: int = 8,
        context: ReasoningContext | None = None,
    ) -> tuple[list[RuleOutcome], RuleState]:
        """Evaluates active rules with bounded re-evaluation loop (WO-20 Phase 1 & 2)."""
        orch = self._orch
        ctx = context if context is not None else ReasoningContext()
        orch.current_reasoning_context = ctx

        def _exec_assert(
            action: AssertFact, st: RuleState, rule_id: str | None = None
        ) -> RuleState:
            signed = orch._commit_lisp_assertion(action, trace)
            env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
            conf = signed.confidence if signed and signed.confidence is not None else 1.0

            ctx.add_intermediate(
                envelope_id=env_id,
                s=action.s,
                p=action.p,
                o=action.o,
                confidence=conf,
                step_kind="lisp_rule",
                rule_id=rule_id,
            )
            return st.model_copy(
                update={"asserted_facts": st.asserted_facts | {(action.s, action.p, action.o)}}
            )

        outcomes, final_state = orch.rule_engine.evaluate_chain(
            state, execute_assert=_exec_assert, max_depth=max_depth, context=ctx
        )
        if len(ctx) > 0:
            orch.finalize_chain(ctx, trace)
        return outcomes, final_state

    def finalize_chain(
        self,
        context: ReasoningContext | None = None,
        trace: TurnTrace | None = None,
    ) -> SignedPayload | None:
        """Commits the conclusion of a completed chain as INFERRED with its proof trace (WO-20 Phase 4)."""
        orch = self._orch
        ctx = context if context is not None else getattr(orch, "current_reasoning_context", None)
        if ctx is None or len(ctx) == 0:
            return None
        if not orch.memory_store:
            return None

        final_entry = ctx[-1]
        proof_trace_steps = ctx.proof_trace()
        proof_trace = [s.to_dict() for s in proof_trace_steps]
        confidence = min(s.confidence for s in proof_trace_steps) if proof_trace_steps else 1.0

        if not meets_standard(confidence, "memory_commit_inferred"):
            logger.info(
                "finalize_chain_refused_below_standard",
                confidence=confidence,
                required=required_threshold("memory_commit_inferred"),
                standard=required_standard("memory_commit_inferred").value,
                conclusion=f"{final_entry.s} {final_entry.p} {final_entry.o}",
            )
            return None

        all_conditions: list[str] = []
        for s in proof_trace_steps:
            for cond in s.conditions:
                if cond not in all_conditions:
                    all_conditions.append(cond)

        signer = orch.signer_factory.inferred_fact()
        now = orch.clock.now_utc() if hasattr(orch, "clock") and orch.clock else time.time()
        trace_id = trace.trace_id if trace else f"trace-{ulid.ULID()}"

        unsigned = UnsignedPayload(
            content=f"{final_entry.s} {final_entry.p} {final_entry.o}",
            provenance=Provenance.INFERRED,
            kind="fact",
            confidence=confidence,
            nonce=os.urandom(16).hex(),
            created_at=now,
            trace_id=trace_id,
            structured={
                "s": final_entry.s,
                "p": final_entry.p,
                "o": final_entry.o,
                "confidence": confidence,
                "proof_trace": proof_trace,
                "conditions": all_conditions,
                "proof_standard": standard_for_confidence(confidence).value,
            },
        )
        signed = signer.sign(unsigned)
        orch.memory_store.commit(signed, now=now)
        return signed

    def proof_trace(self) -> list[ProofTraceStep]:
        """Exposes the current turn's reasoning context proof trace (Spec D-REAS-09, WO-20 Phase 2/4)."""
        ctx = getattr(self._orch, "current_reasoning_context", None)
        if ctx is None:
            return []
        return ctx.proof_trace()

    def validate_premise(self, premise: str, context: ReasoningContext) -> tuple[bool, str | None]:
        """Validates a premise against signed tool receipts, reasoning context, or the signed store."""
        orch = self._orch
        clean = premise.strip()

        # 1. Attributed premise: "<source> asserts <claim>"
        attr_match = re.match(r"^(.+?)\s+asserts\s+(.+)$", clean, re.IGNORECASE)
        if attr_match:
            claim = attr_match.group(2).strip().lower()
            receipts = getattr(orch, "current_turn_receipts", []) or []
            executed = getattr(orch, "executed_tools", []) or []
            for r in list(receipts) + list(executed):
                ok = getattr(r, "ok", True)
                if not ok:
                    continue
                out = (
                    str(getattr(r, "output", "") or "")
                    or str(getattr(r, "content", "") or "")
                    or str(getattr(r, "structured", "") or "")
                ).lower()
                if claim in out or all(word in out for word in claim.split() if len(word) > 2):
                    return (True, None)
            return (False, "unverified_premise")

        # 2. Direct signed tool receipt check
        receipts = getattr(orch, "current_turn_receipts", []) or []
        executed = getattr(orch, "executed_tools", []) or []
        clean_lower = clean.lower()
        for r in list(receipts) + list(executed):
            ok = getattr(r, "ok", True)
            if not ok:
                continue
            out = (
                str(getattr(r, "output", "") or "")
                or str(getattr(r, "content", "") or "")
                or str(getattr(r, "structured", "") or "")
            ).lower()
            if clean_lower in out or all(
                word in out for word in clean_lower.split() if len(word) > 2
            ):
                return (True, None)

        # 3. Reasoning context check (intermediate facts in current chain)
        if context.resolve_premise(clean) is not None:
            return (True, None)
        for intermediate in context.intermediates:
            if (
                intermediate.conclusion.lower() == clean.lower()
                or intermediate.envelope_id == clean
            ):
                return (True, None)

        # 4. Signed memory store check
        if orch.db is not None:
            try:
                with orch.db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.content, e.entry_id, e.provenance
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1
                          AND (m.content = ? OR e.entry_id = ? OR m.content = ?)
                        """,
                        (clean, clean, clean.lower()),
                    )
                    if cur.fetchall():
                        return (True, None)

                    cur.execute(
                        """
                        SELECT m.content, e.payload_json
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1
                          AND m.valid_to IS NULL
                        ORDER BY m.created_at DESC
                        LIMIT 100
                        """
                    )
                    rows = cur.fetchall()
                    verifier_inst = getattr(orch, "verifier", None)
                    for row_content, row_payload_json in rows:
                        mem_text = str(row_content or "").strip()
                        if not mem_text:
                            continue
                        if row_payload_json:
                            try:
                                pj = json.loads(str(row_payload_json))
                                st = pj.get("structured") if isinstance(pj, dict) else None
                                if isinstance(st, dict) and {"s", "p", "o"} <= set(st.keys()):
                                    triple_str = f"{st['s']} {st['p']} {st['o']}".strip().lower()
                                    if triple_str == clean.lower():
                                        return (True, None)
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("premise_struct_json_parse_error", error=str(exc))
                        if verifier_inst is not None and hasattr(
                            verifier_inst, "check_consistency"
                        ):
                            try:
                                v_res = verifier_inst.check_consistency(
                                    premise=mem_text, hypothesis=clean
                                )
                                if (
                                    not getattr(v_res, "degraded", False)
                                    and str(getattr(v_res, "label", "")).upper().endswith("ENTAILMENT")
                                    and float(getattr(v_res, "score", 0.0)) >= 0.75
                                ):
                                    return (True, None)
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("premise_verifier_check_error", error=str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.debug("premise_validation_db_error", error=str(exc))

        return (False, "unverified_premise")

    def search_memory_for_premise(self, premise: str) -> list[str]:
        """Runs memory_search for unverified premise (Gather Ladder Step 2)."""
        orch = self._orch
        clean = premise.strip()
        hits: list[str] = []

        if re.match(r"^(.+?)\s+asserts\s+(.+)$", clean, re.IGNORECASE):
            return []

        if orch.memory_store is not None and hasattr(orch.memory_store, "search"):
            try:
                q = RetrievalQuery(query_text=clean, k=5)
                res = orch.memory_store.search(q)
                for h in res:
                    if getattr(h, "grounding_eligible", False):
                        words = [w.lower() for w in re.split(r"[\s_]+", clean) if len(w) > 2]
                        if clean.lower() in h.content.lower() or (
                            words and all(w in h.content.lower() for w in words)
                        ):
                            hits.append(h.content)
            except Exception as exc:  # noqa: BLE001
                logger.debug("gather_ladder_search_error", error=str(exc))

        if not hits and orch.db is not None:
            try:
                words = [w.lower() for w in re.split(r"[\s_]+", clean) if len(w) > 2]
                if words:
                    clauses = " AND ".join(["m.content LIKE ?" for _ in words])
                    params = [f"%{w}%" for w in words]
                    with orch.db.read_cursor() as cur:
                        cur.execute(
                            f"""
                            SELECT m.content
                            FROM memories m
                            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                            WHERE e.grounding_eligible = 1 AND {clauses}
                            """,
                            tuple(params),
                        )
                        for r in cur.fetchall():
                            hits.append(r[0])
            except Exception as exc:  # noqa: BLE001
                logger.debug("gather_ladder_db_search_error", error=str(exc))

        return hits

    def parse_inference_steps(self, text: str) -> list[InferenceStep]:
        """Extracts and validates InferenceStep models from LLM JSON response."""
        clean_text = text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
        if fence_match:
            clean_text = fence_match.group(1).strip()

        array_match = re.search(r"\[[\s\S]*\]", clean_text)
        obj_match = re.search(r"\{[\s\S]*\}", clean_text)

        raw_data: object = None
        if array_match:
            raw_data = json.loads(array_match.group(0))
        elif obj_match:
            raw_data = json.loads(obj_match.group(0))
        else:
            raw_data = json.loads(clean_text)

        steps: list[InferenceStep] = []
        if isinstance(raw_data, list):
            for item in raw_data:
                if isinstance(item, dict):
                    steps.append(InferenceStep.model_validate(item))
        elif isinstance(raw_data, dict):
            steps.append(InferenceStep.model_validate(raw_data))

        return steps

    def evaluate_step_corroboration(
        self, step: InferenceStep, context: ReasoningContext | None = None
    ) -> list[CriticalQuestionResult]:
        """Evaluates Walton critical questions for attributed or grounding premises (WO-21/23)."""
        orch = self._orch
        has_attributed = any(
            re.match(r"^(.+?)\s+asserts\s+(.+)$", p.strip(), re.IGNORECASE) for p in step.premises
        )
        receipts = list(getattr(orch, "current_turn_receipts", []) or []) + list(
            getattr(orch, "executed_tools", []) or []
        )
        scheme, ambig_note = detect_premise_scheme(step)

        if has_attributed or scheme != Scheme.AUTHORITY:
            if ambig_note and ambig_note not in step.conditions and len(step.conditions) < 8:
                step.conditions.append(ambig_note)
            try:
                q_results = critical_questions(
                    scheme, step, store=orch.memory_store, receipts=receipts
                )
                eff_conf, new_conditions = adjust_confidence(
                    step.confidence, q_results, scheme=scheme
                )
                step.confidence = eff_conf
                for cond in new_conditions:
                    if cond not in step.conditions and len(step.conditions) < 8:
                        step.conditions.append(cond)
                return q_results
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "critical_questions_failed", scheme=str(scheme), error=str(exc)
                )
                return []

        effective_ctx = context or getattr(orch, "current_reasoning_context", None)
        ctx_conclusions = {
            e.conclusion.lower() for e in (effective_ctx.intermediates if effective_ctx else [])
        }
        ctx_env_ids = {
            e.envelope_id for e in (effective_ctx.intermediates if effective_ctx else [])
        }
        if len(step.premises) >= 2 and orch.db is not None:
            try:
                premise_eids: list[str] = []
                with orch.db.read_cursor() as cur:
                    for prem in step.premises:
                        clean_prem = prem.strip()
                        if clean_prem.lower() in ctx_conclusions or clean_prem in ctx_env_ids:
                            continue
                        cur.execute(
                            """
                            SELECT m.entry_id
                            FROM memories m
                            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                            WHERE e.grounding_eligible = 1
                              AND m.valid_to IS NULL
                              AND (m.content = ? OR m.content = ? OR m.content LIKE ?)
                            """,
                            (clean_prem, clean_prem.lower(), f"%{clean_prem}%"),
                        )
                        for r in cur.fetchall():
                            if str(r[0]) not in premise_eids and str(r[0]) not in ctx_env_ids:
                                premise_eids.append(str(r[0]))
                                break

                if len(premise_eids) >= 2:
                    q_corrob = CriticalQuestionResult(
                        question=(
                            "Is the claim corroborated by an independent grounding-eligible fact?"
                        ),
                        answer=CQAnswer.SATISFIED,
                        count=len(premise_eids),
                        evidence_entry_ids=premise_eids,
                        sources=["store"],
                        detail=(
                            f"Corroborated by {len(premise_eids)} independent "
                            "grounding premises in store"
                        ),
                    )
                    dispute_eids: list[str] = []
                    dispute_details: list[str] = []
                    if step.s and step.p:
                        with orch.db.read_cursor() as cur:
                            cur.execute(
                                """
                                SELECT m.entry_id, m.content, e.signer_id
                                FROM memories m
                                JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                                WHERE e.grounding_eligible = 1
                                  AND m.valid_to IS NULL
                                  AND m.content LIKE ?
                                """,
                                (f"{step.s} {step.p} %",),
                            )
                            for row in cur.fetchall():
                                eid, content, _signer = row
                                parts = content.strip().split()
                                if len(parts) >= 3 and parts[2].lower() != step.o.lower():
                                    dispute_eids.append(str(eid))
                                    dispute_details.append(
                                        f"{content} contradicts {step.s} {step.p} {step.o}"
                                    )

                    if dispute_eids:
                        q_dispute = CriticalQuestionResult(
                            question="Is the claim disputed by any grounding-eligible fact?",
                            answer=CQAnswer.SATISFIED,
                            count=len(dispute_eids),
                            evidence_entry_ids=dispute_eids,
                            sources=["store"],
                            detail=dispute_details[0],
                        )
                    else:
                        q_dispute = CriticalQuestionResult(
                            question="Is the claim disputed by any grounding-eligible fact?",
                            answer=CQAnswer.UNKNOWN,
                            count=0,
                            evidence_entry_ids=[],
                            sources=[],
                            detail="No disputes found",
                        )

                    q_results = [q_corrob, q_dispute]
                    eff_conf, new_conditions = adjust_confidence(step.confidence, q_results)
                    step.confidence = eff_conf
                    for cond in new_conditions:
                        if cond not in step.conditions and len(step.conditions) < 8:
                            step.conditions.append(cond)
                    return q_results
            except Exception as exc:  # noqa: BLE001
                logger.warning("premise_corroboration_failed", error=str(exc))

        return []

    def run_deduction_step(
        self,
        goal: str,
        trace: TurnTrace | None = None,
        context: ReasoningContext | None = None,
        llm: object | None = None,
    ) -> tuple[list[InferenceStep], str | None]:
        """Runs the abductive deduction loop with bounded gather ladder (Spec D-REAS-09, WO-20 Phase 3)."""
        orch = self._orch
        effective_llm = llm if llm is not None else getattr(orch, "llm", None)
        if effective_llm is None:
            logger.warning("no_llm_available_for_deduction")
            return ([], "No language model available for deduction.")

        ctx = (
            context
            if context is not None
            else (getattr(orch, "current_reasoning_context", None) or ReasoningContext())
        )
        orch.current_reasoning_context = ctx
        trace_id = trace.trace_id if trace else f"trace-{ulid.ULID()}"

        verified_facts: list[str] = [entry.conclusion for entry in ctx.intermediates]
        if orch.db is not None:
            try:
                with orch.db.read_cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.content
                        FROM memories m
                        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
                        WHERE e.grounding_eligible = 1
                        ORDER BY m.created_at DESC
                        LIMIT 20
                        """
                    )
                    for row in cur.fetchall():
                        if row[0] not in verified_facts:
                            verified_facts.append(row[0])
            except Exception as exc:  # noqa: BLE001
                logger.debug("deduction_context_gather_error", error=str(exc))

        attributed_receipts: list[str] = []
        for r in getattr(orch, "current_turn_receipts", []) or []:
            out = str(getattr(r, "output", "") or getattr(r, "content", "") or "")
            if out:
                attributed_receipts.append(f"{getattr(r, 'tool', 'tool')}: {out}")

        full_text = ""
        for event in effective_llm.stream_turn(
            current_text=goal,
            memories=[],
            history=getattr(orch, "history", []),
            trace_id=trace_id,
        ):
            if isinstance(event, TokenDelta):
                full_text += event.delta

        proposed_steps: list[InferenceStep] = []
        try:
            proposed_steps = orch._parse_inference_steps(full_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("deduction_llm_parse_error", error=str(exc), raw=full_text)
            return ([], f"Failed to parse deduction steps: {exc}")

        accepted_steps: list[InferenceStep] = []

        for step in proposed_steps:
            for prem in step.premises:
                if re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE):
                    if prem not in step.conditions and len(step.conditions) < 8:
                        step.conditions.append(prem)

            unverified: list[str] = []
            for prem in step.premises:
                ok, _ = orch._validate_premise(prem, ctx)
                if not ok:
                    unverified.append(prem)

            if not unverified:
                q_results = orch._evaluate_step_corroboration(step)
                action = AssertFact(s=step.s, p=step.p, o=step.o)
                signed = orch._commit_lisp_assertion(action, trace, llm_inferred=True)
                env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
                ctx.add_intermediate(
                    envelope_id=env_id,
                    s=step.s,
                    p=step.p,
                    o=step.o,
                    confidence=step.confidence,
                    step_kind="llm_abductive",
                    rule_id="llm",
                    premises=list(step.premises),
                    conditions=list(step.conditions),
                    critical_questions=[q.to_dict() for q in q_results],
                )
                accepted_steps.append(step)
                continue

            # Gather Ladder (bounded to 1 pass per deduction turn)
            missing_premise = unverified[0]
            logger.info("gather_ladder_started", missing_premise=missing_premise)

            # 1. Revise once
            error_payload = json.dumps({"error": "unverified_premise", "premise": missing_premise})
            revised_text = ""
            for event in effective_llm.stream_turn(
                current_text=f"Revise inference step: {error_payload}",
                trace_id=trace_id,
            ):
                if isinstance(event, TokenDelta):
                    revised_text += event.delta

            revised_step: InferenceStep | None = None
            try:
                r_steps = orch._parse_inference_steps(revised_text)
                if r_steps:
                    revised_step = r_steps[0]
            except Exception as exc:  # noqa: BLE001
                logger.warning("gather_ladder_revise_parse_failed", error=str(exc))

            step_to_evaluate = revised_step
            still_unverified: list[str] = []
            if step_to_evaluate is not None:
                for prem in step_to_evaluate.premises:
                    if re.match(r"^(.+?)\s+asserts\s+(.+)$", prem.strip(), re.IGNORECASE):
                        if (
                            prem not in step_to_evaluate.conditions
                            and len(step_to_evaluate.conditions) < 8
                        ):
                            step_to_evaluate.conditions.append(prem)
                    ok, _ = orch._validate_premise(prem, ctx)
                    if not ok:
                        still_unverified.append(prem)

                if not still_unverified:
                    q_results = orch._evaluate_step_corroboration(step_to_evaluate)
                    action = AssertFact(
                        s=step_to_evaluate.s, p=step_to_evaluate.p, o=step_to_evaluate.o
                    )
                    signed = orch._commit_lisp_assertion(action, trace, llm_inferred=True)
                    env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
                    ctx.add_intermediate(
                        envelope_id=env_id,
                        s=step_to_evaluate.s,
                        p=step_to_evaluate.p,
                        o=step_to_evaluate.o,
                        confidence=step_to_evaluate.confidence,
                        step_kind="llm_abductive",
                        rule_id="llm",
                        premises=list(step_to_evaluate.premises),
                        conditions=list(step_to_evaluate.conditions),
                        critical_questions=[q.to_dict() for q in q_results],
                    )
                    accepted_steps.append(step_to_evaluate)
                    continue

            # 2. Memory retry
            retry_premise = still_unverified[0] if still_unverified else missing_premise
            recovered = orch._search_memory_for_premise(retry_premise)
            if recovered:
                target = step_to_evaluate if step_to_evaluate is not None else step
                q_results = orch._evaluate_step_corroboration(target)
                action = AssertFact(s=target.s, p=target.p, o=target.o)
                signed = orch._commit_lisp_assertion(action, trace, llm_inferred=True)
                env_id = signed.entry_id if signed else f"lisp-{ulid.ULID()}"
                ctx.add_intermediate(
                    envelope_id=env_id,
                    s=target.s,
                    p=target.p,
                    o=target.o,
                    confidence=target.confidence,
                    step_kind="llm_abductive",
                    rule_id="llm",
                    premises=list(target.premises),
                    conditions=list(target.conditions),
                    critical_questions=[q.to_dict() for q in q_results],
                )
                accepted_steps.append(target)
                continue

            # 3. Ask the user (named-gap question) vs 4. Named-gap abstention
            is_personal = any(
                k in retry_premise.lower()
                for k in ("user", "you", "live", "from", "born", "home", "partner")
            )
            if is_personal:
                spoken = f"I don't have anything verified about {retry_premise} — can you tell me about it?"
            else:
                spoken = f"I can't verify {retry_premise}, so I can't deduce that yet."

            logger.info("gather_ladder_terminated", outcome=spoken, missing_premise=retry_premise)
            if hasattr(orch, "_speak_text") and trace:
                orch._speak_text(trace, spoken)
            return (accepted_steps, spoken)

        if accepted_steps and len(ctx) > 0:
            committed = orch.finalize_chain(ctx, trace)
            if committed is None:
                final_entry = ctx[-1]
                proof_trace_steps = ctx.proof_trace()
                conf = min(s.confidence for s in proof_trace_steps) if proof_trace_steps else 1.0
                if conf < 0.50:
                    spoken = f"I'm guessing {final_entry.s} {final_entry.p} {final_entry.o}, but that's just speculation."
                else:
                    spoken = f"I think {final_entry.s} {final_entry.p} {final_entry.o}, but I'm not sure enough to keep it."
                logger.info(
                    "chain_concluded_speculation",
                    confidence=conf,
                    spoken=spoken,
                    conclusion=f"{final_entry.s} {final_entry.p} {final_entry.o}",
                )
                if hasattr(orch, "_speak_text") and trace:
                    orch._speak_text(trace, spoken)
                return (accepted_steps, spoken)
            else:
                final_entry = ctx[-1]
                conditions = list(final_entry.conditions or [])
                if conditions:
                    spoken = orch._format_conditioned_speech(final_entry, conditions)
                    if spoken:
                        logger.info(
                            "chain_concluded_conditioned",
                            confidence=final_entry.confidence,
                            spoken=spoken,
                            conclusion=f"{final_entry.s} {final_entry.p} {final_entry.o}",
                        )
                        if hasattr(orch, "_speak_text") and trace:
                            orch._speak_text(trace, spoken)
                        return (accepted_steps, spoken)
        return (accepted_steps, None)

    def format_conditioned_speech(
        self, final_entry: ReasoningEntry, conditions: list[str]
    ) -> str | None:
        """Formats spoken output for a committed chain with carried conditions (WO-21 Phase 6)."""
        _ = final_entry
        if not conditions:
            return None

        if_cond = next(
            (
                c.strip()
                for c in conditions
                if re.match(r"^(?:…|\.\.\.)?\s*if\b", c.strip(), re.IGNORECASE)
            ),
            None,
        )
        if if_cond:
            clean = if_cond
            if not clean.startswith("…") and not clean.startswith("..."):
                clean = f"…{clean}"
            if not clean.endswith("."):
                clean = f"{clean}."
            return clean

        attr_cond = next(
            (
                c.strip()
                for c in conditions
                if re.match(r"^(.+?)\s+asserts\s+(.+)$", c.strip(), re.IGNORECASE)
            ),
            None,
        )
        if attr_cond:
            m = re.match(r"^(.+?)\s+asserts\s+(.+)$", attr_cond, re.IGNORECASE)
            if m:
                src, claim = m.group(1).strip(), m.group(2).strip()
                return f"…if {src} is right about {claim}."

        cond_text = conditions[0].strip()
        if not cond_text.startswith("…") and not cond_text.startswith("..."):
            cond_text = f"…{cond_text}"
        if not cond_text.endswith("."):
            cond_text = f"{cond_text}."
        return cond_text

    def parse_and_validate_plan(
        self, text: str, default_goal: str
    ) -> tuple[GoalPlan | None, str | None]:
        """Parses and validates a GoalPlan from LLM response text (WO-22 Phase 1)."""
        orch = self._orch
        clean_text = text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text)
        if fence_match:
            clean_text = fence_match.group(1).strip()

        obj_match = re.search(r"\{[\s\S]*\}", clean_text)
        if not obj_match:
            return None, f"No JSON object found in response: {text[:100]}"

        try:
            raw_data = json.loads(obj_match.group(0))
        except Exception as exc:  # noqa: BLE001
            logger.debug("plan_json_parse_failed", error=str(exc))
            return None, f"Malformed JSON in plan: {exc}"

        if not isinstance(raw_data, dict):
            return None, "Expected a JSON object for GoalPlan, got list or scalar."

        if not raw_data.get("plan_id"):
            raw_data["plan_id"] = f"plan-{ulid.ULID()}"
        if not raw_data.get("goal"):
            raw_data["goal"] = default_goal

        try:
            plan = GoalPlan.model_validate(raw_data)
        except ValidationError as exc:
            return None, f"GoalPlan schema validation failed: {exc}"

        for step in plan.steps:
            schema_cls = TOOL_ARG_SCHEMAS.get(step.tool) or EXTRA_TOOL_SCHEMAS.get(step.tool)
            if schema_cls is None:
                return None, f"Step {step.order}: Tool '{step.tool}' is not registered."
            try:
                schema_cls.model_validate(step.args)
            except ValidationError as exc:
                return (
                    None,
                    f"Step {step.order} ({step.tool}) argument schema validation failed: {exc}",
                )

        bdi_validator = getattr(orch, "bdi_validator", None)
        if bdi_validator is not None:
            taint = getattr(getattr(orch, "sandbox", None), "taint_flags", 0)
            for step in plan.steps:
                bdi_res = bdi_validator.validate_tool_call(step.tool, step.args, taint_flags=taint)
                if not bdi_res.is_valid:
                    reason = bdi_res.reason or "Action prohibited"
                    return (
                        None,
                        f"Step {step.order} ({step.tool}) deontic violation: {reason}",
                    )

        return plan, None

    def run_planning_step(
        self,
        goal: str,
        trace: TurnTrace | None = None,
        llm: object | None = None,
        context: ReasoningContext | None = None,
    ) -> GoalPlan | None:
        """Executes a bounded, validated means-ends plan for a goal (WO-22 Phase 1)."""
        orch = self._orch
        effective_llm = llm if llm is not None else getattr(orch, "llm", None)
        if effective_llm is None:
            logger.warning("no_llm_available_for_planning")
            return None

        ctx = (
            context
            if context is not None
            else (getattr(orch, "current_reasoning_context", None) or ReasoningContext())
        )
        orch.current_reasoning_context = ctx

        if trace is None:
            trace = getattr(orch, "active_trace", None) or TurnTrace(
                trace_id=f"plan-{ulid.ULID()}",
                session_id=getattr(orch, "session_id", "session-plan"),
                origin="text",
            )
        trace_id = trace.trace_id

        available_tools = list(TOOL_ARG_SCHEMAS.keys())
        verified_facts: list[str] = [entry.conclusion for entry in ctx.intermediates]

        planning_msgs = build_planning_messages(
            goal=goal,
            available_tools=available_tools,
            verified_facts=verified_facts,
            history=getattr(orch, "history", []),
        )

        full_text = ""
        for event in effective_llm.stream_turn(
            current_text=goal,
            memories=[],
            history=getattr(orch, "history", []),
            trace_id=trace_id,
            messages=planning_msgs,
        ):
            if isinstance(event, TokenDelta):
                full_text += event.delta

        plan, err = orch._parse_and_validate_plan(full_text, default_goal=goal)
        if plan is None:
            logger.warning("planning_initial_validation_failed", error=err, raw=full_text)
            revision_msgs = build_planning_messages(
                goal=goal,
                available_tools=available_tools,
                verified_facts=verified_facts,
                error_feedback=err,
                history=getattr(orch, "history", []),
            )
            revised_text = ""
            for event in effective_llm.stream_turn(
                current_text=f"Revise plan to fix error: {err}",
                memories=[],
                history=getattr(orch, "history", []),
                trace_id=trace_id,
                messages=revision_msgs,
            ):
                if isinstance(event, TokenDelta):
                    revised_text += event.delta

            plan, err = orch._parse_and_validate_plan(revised_text, default_goal=goal)
            if plan is None:
                logger.warning("planning_revision_validation_failed", error=err, raw=revised_text)
                refusal_msg = f"I can't plan that safely because: {err}"
                orch._speak_text(trace, refusal_msg)
                orch.current_turn_tool_spoken.append(refusal_msg)
                return None

        orch.current_turn_plan = plan
        executed_tuples: list[tuple[str, dict[str, JsonValue], bool, str]] = []
        cancelled_tuples: list[tuple[str, dict[str, JsonValue]]] = []
        failed_step_order: int | None = None

        for i, step in enumerate(plan.steps):
            resolved_intermediates: list[str] = []
            if ctx is not None and step.purpose:
                resolved_entries = ctx.resolve_purpose_intermediates(step.purpose)
                resolved_intermediates = [e.envelope_id for e in resolved_entries]

            res = orch._handle_tool_call(trace, step.tool, dict(step.args), speak=False)
            ok = (res is None) or getattr(res, "ok", True)
            raw_out = ""
            if res is not None:
                raw_out = str(
                    getattr(res, "content", "")
                    or getattr(res, "structured", "")
                    or getattr(res, "stderr", "")
                )

            receipt_entry: dict[str, JsonValue] = {
                "order": step.order,
                "tool": step.tool,
                "args": step.args,
                "ok": ok,
                "result": raw_out,
                "resolved_intermediates": resolved_intermediates,
            }
            plan.receipts.append(receipt_entry)
            executed_tuples.append((step.tool, dict(step.args), ok, raw_out))

            if not ok:
                failed_step_order = step.order
                for rem_step in plan.steps[i + 1 :]:
                    cancelled_tuples.append((rem_step.tool, dict(rem_step.args)))
                break

        narration = synthesize_plan_narration(
            executed_steps=executed_tuples,
            cancelled_steps=cancelled_tuples if failed_step_order is not None else None,
            failed_step_order=failed_step_order,
        )
        plan.narration = narration
        orch.last_spoken_plan_narration = narration
        orch._speak_text(trace, narration)
        orch.current_turn_tool_spoken.append(narration)

        return plan

    # ------------------------------------------------------------------------
    # WO-21 Phase 3: Proactive Web-Fact Ratification & Cross-Reference
    # ------------------------------------------------------------------------

    def extract_receipt_domain(self, r: ToolReceipt) -> str:
        args = getattr(r, "args", {}) or {}
        if isinstance(args, dict):
            domain_val = args.get("domain", "")
            if domain_val and isinstance(domain_val, str):
                return domain_val.strip().lower()
            url_val = args.get("url", "")
            if url_val and isinstance(url_val, str):
                try:
                    parsed = urllib.parse.urlsplit(url_val)
                    if parsed.netloc:
                        return parsed.netloc.lower().split(":")[0]
                except Exception as exc:  # noqa: BLE001
                    logger.debug("extract_receipt_domain_urlsplit_failed", error=str(exc))
        src = extract_receipt_source(r)
        if "." in src and not src.startswith("tool"):
            return src.lower()
        return ""

    def is_domain_whitelisted(self, domain: str) -> bool:
        if not domain:
            return False
        d_clean = domain.strip().lower()
        whitelist = getattr(self._orch, "ratification_domains", None) or set()
        if d_clean in whitelist:
            return True
        return any(d_clean == w or d_clean.endswith("." + w) for w in whitelist)

    def extract_durable_claim(self, r: ToolReceipt) -> str | None:
        args = getattr(r, "args", {}) or {}
        if isinstance(args, dict) and "claim" in args and isinstance(args["claim"], str):
            c = args["claim"].strip()
            if c:
                return c

        text = str(getattr(r, "output", "") or getattr(r, "content", "") or "")
        return self._orch._extract_durable_claim_from_text(text)

    def extract_durable_claim_from_text(self, text: str) -> str | None:
        cleaned = text.strip()
        if not cleaned or len(cleaned) < 5:
            return None
        lower = cleaned.lower()
        if any(
            err in lower for err in ("error:", "404 not found", "access denied", "failed to fetch")
        ):
            return None

        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        copula_pattern = re.compile(
            r"\b(?:is|was|are|were|has|have|had|features|released|announced|supports|became|born|won|contains)\b",
            re.IGNORECASE,
        )
        for s in sentences:
            s_clean = s.strip()
            s_clean = re.sub(r"^#+\s*", "", s_clean)
            s_clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s_clean)
            if 10 <= len(s_clean) <= 150 and not s_clean.endswith("?"):
                if copula_pattern.search(s_clean):
                    return s_clean.rstrip(".! ")

        if 10 <= len(cleaned) <= 120 and not cleaned.endswith("?"):
            return cleaned.rstrip(".! ")
        return None

    def check_and_offer_ratification(self, trace: TurnTrace) -> str | None:
        orch = self._orch
        if getattr(orch, "_ratification_offered_this_turn", False):
            return None
        receipts = getattr(orch, "current_turn_receipts", []) or []
        for r in receipts:
            tool_name = getattr(r, "tool", "") or getattr(r, "tool_name", "")
            if tool_name not in ("fetch_url", "search_web", "web_search", "browse_page"):
                continue
            if not getattr(r, "ok", True):
                continue
            domain = orch._extract_receipt_domain(r)
            if not domain or not orch._is_domain_whitelisted(domain):
                continue
            claim = orch._extract_durable_claim(r)
            if not claim:
                continue

            args = getattr(r, "args", {}) or {}
            url = ""
            if isinstance(args, dict):
                url = str(args.get("url", "") or args.get("domain", "") or domain)

            offer_text = f"I found on {domain} that {claim} \u2014 want me to remember that?"
            orch._ratification_offered_this_turn = True

            orch._pending_ratification = PendingRatification(
                call_id=getattr(r, "call_id", ""),
                domain=domain,
                claim=claim,
                source_url=url,
                fetch_receipt_entry_id=getattr(r, "entry_id", "") or getattr(r, "call_id", ""),
            )
            orch._speak_text(trace, offer_text)
            orch._publish_caption(offer_text, source="assistant", is_final=True)
            return offer_text
        return None

    def commit_ratified_fact(self, pending: PendingRatification, trace: TurnTrace) -> str | None:
        orch = self._orch
        if not orch.memory_store:
            return None
        signer = orch.signer_factory.derived_fact()
        now = orch.clock.now_utc() if hasattr(orch, "clock") and orch.clock else time.time()
        source_id = pending.fetch_receipt_entry_id or f"fetch-{pending.call_id}"
        unsigned = UnsignedPayload(
            content=pending.claim,
            provenance=Provenance.USER_DERIVED,
            kind="fact",
            nonce=os.urandom(16).hex(),
            created_at=now,
            trace_id=trace.trace_id,
            confidence=1.0,
            source_entry_ids=[source_id],
            structured={
                "source_url": pending.source_url,
                "fetch_receipt_entry_id": source_id,
                "confirmed_by_user": True,
            },
        )
        signed = signer.sign(unsigned)
        orch.memory_store.commit(signed, now=now)
        orch._last_ratified_claim = pending.claim
        return signed.entry_id

    def resolve_cross_reference_claim(self, user_text: str) -> str | None:
        orch = self._orch
        cross_ref_pat = (
            r"(?:cross[\s-]?reference|find more sources on|check more sources on|verify)"
            r"\s+(?:that\s+)?(.+)"
        )
        m = re.search(cross_ref_pat, user_text, re.IGNORECASE)
        if m:
            explicit_claim = m.group(1).strip().rstrip(".!?")
            if explicit_claim.lower() not in ("that", "this", "it"):
                return explicit_claim

        if getattr(orch, "_pending_ratification", None) is not None:
            return orch._pending_ratification.claim

        if getattr(orch, "_last_ratified_claim", None):
            return orch._last_ratified_claim

        for msg in reversed(orch.history):
            if msg.get("role") == "assistant":
                content = str(msg.get("content", ""))
                offer_match = re.search(
                    r"I found on .+? that (.+?) [—\-] want me to remember that\?",
                    content,
                )
                if offer_match:
                    return offer_match.group(1).strip()
                c = orch._extract_durable_claim_from_text(content)
                if c:
                    return c
        return None

    @staticmethod
    def extract_claim_aligned_sentences(
        claim: str,
        page_text: str,
        fallback_snippet: str,
        max_sentences: int = 2,
    ) -> str:
        """Extracts the top 1-2 claim-aligned sentences from Scrapling page text."""
        if not page_text or not page_text.strip():
            return fallback_snippet
        claim_tokens = {
            tok
            for tok in re.findall(r"[a-z0-9]+", claim.lower())
            if len(tok) > 2
            and tok
            not in {
                "the",
                "and",
                "for",
                "that",
                "with",
                "from",
                "this",
                "what",
                "when",
                "where",
                "who",
                "was",
                "are",
                "is",
            }
        }
        if not claim_tokens:
            return fallback_snippet

        raw_sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+|\n+", page_text)
            if 15 <= len(s.strip()) <= 500
        ]
        if not raw_sentences:
            return fallback_snippet

        scored: list[tuple[float, int, str]] = []
        for idx, sent in enumerate(raw_sentences):
            sent_tokens = set(re.findall(r"[a-z0-9]+", sent.lower()))
            overlap = len(claim_tokens & sent_tokens)
            if overlap == 0:
                continue
            ratio = overlap / max(len(claim_tokens), 1)
            scored.append((ratio, -idx, sent))

        if not scored:
            return fallback_snippet

        scored.sort(reverse=True)
        top_sents = [s for _r, _i, s in scored[:max_sentences]]
        combined = " ".join(top_sents).strip()
        if fallback_snippet and fallback_snippet not in combined:
            return f"{fallback_snippet} {combined}".strip()
        return combined

    def fetch_cross_reference_page(self, url: str) -> str:
        """Fetches clean article text via Scrapling web_tool for cross-reference corroboration."""
        orch = self._orch
        if not url:
            return ""
        is_mock_sandbox = orch.sandbox is not None and type(
            orch.sandbox
        ).__module__.startswith("unittest.mock")
        default_enabled = not is_mock_sandbox
        if not getattr(orch, "enable_deep_cross_reference", default_enabled):
            return ""
        try:
            from lucca.sandbox.web_tool import fetch_url

            structured, content = fetch_url(url=url, max_chars=6000)
            if structured.get("ok") and isinstance(content, str):
                return content
        except Exception as exc:  # noqa: BLE001
            logger.debug("cross_ref_deep_fetch_error", url=url, error=str(exc))
        return ""

    def execute_cross_reference_searches(
        self, claim: str, max_searches: int = 3
    ) -> list[ToolReceipt]:
        orch = self._orch
        custom_search = getattr(orch, "cross_reference_search_fn", None)
        if custom_search is not None and callable(custom_search):
            res_list = custom_search(claim, max_searches)
            if isinstance(res_list, list):
                return [r for r in res_list if isinstance(r, ToolReceipt)]

        receipts: list[ToolReceipt] = []
        if orch.sandbox:
            call_id = str(ulid.ULID())
            res = orch.sandbox.execute_tool(
                call_id=call_id,
                tool_name="search_web",
                args={"query": claim, "max_results": max_searches},
                confirmed=True,
            )
            if (
                res.structured
                and "results" in res.structured
                and isinstance(res.structured["results"], list)
            ):
                for item in res.structured["results"][:max_searches]:
                    url = item.get("url", "")
                    domain = ""
                    if url:
                        try:
                            domain = urllib.parse.urlsplit(url).netloc.lower()
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("search_receipt_domain_urlsplit_error", error=str(exc))
                    content = f"{item.get('title', '')} {item.get('snippet', '')}".strip()
                    page_text = orch._fetch_cross_reference_page(url) if url else ""
                    if page_text:
                        content = orch._extract_claim_aligned_sentences(
                            claim=claim,
                            page_text=page_text,
                            fallback_snippet=content,
                        )
                    rcpt = ToolReceipt(
                        tool="search_web",
                        tool_name="search_web",
                        ok=True,
                        call_id=str(ulid.ULID()),
                        args={"url": url, "domain": domain, "query": claim},
                        output=content,
                        timestamp=time.time(),
                    )
                    receipts.append(rcpt)
                    orch.current_turn_receipts.append(rcpt)
            elif res.content:
                rcpt = ToolReceipt(
                    tool="search_web",
                    tool_name="search_web",
                    ok=res.ok,
                    call_id=call_id,
                    args={"query": claim},
                    output=str(res.content),
                    timestamp=time.time(),
                )
                receipts.append(rcpt)
                orch.current_turn_receipts.append(rcpt)
        return receipts

    def handle_cross_reference(self, trace: TurnTrace, user_text: str) -> None:
        orch = self._orch
        claim = orch._resolve_cross_reference_claim(user_text)
        if not claim:
            msg = "I don't have a recent claim to cross-reference."
            orch._speak_text(trace, msg)
            orch._publish_caption(msg, source="assistant", is_final=True)
            orch.history.append({"role": "user", "content": user_text})
            orch.history.append({"role": "assistant", "content": msg})
            orch.play_ring.set_flag(FLAG_EOS)
            orch._finalize_turn(trace, None)
            return

        if getattr(orch, "_pending_ratification", None) is not None:
            orch._pending_ratification = None

        receipts = orch._execute_cross_reference_searches(claim, max_searches=3)
        step = InferenceStep(
            s=claim,
            p="is_verified",
            o="true",
            premises=[f"web asserts {claim}"],
            confidence=0.70,
            rationale="cross_reference",
        )
        q_results = critical_questions(
            scheme=Scheme.AUTHORITY,
            step=step,
            store=orch.memory_store,
            receipts=receipts,
        )
        initial_conf = 0.70
        new_conf, _conditions = adjust_confidence(initial_conf, q_results)
        std = standard_for_confidence(new_conf)

        q2 = next(
            (
                q
                for q in q_results
                if "corroborated" in q.question.lower() and q.answer == CQAnswer.SATISFIED
            ),
            None,
        )
        corrob_count = q2.count if q2 else 0
        disputes = [
            q
            for q in q_results
            if "disputed" in q.question.lower() and q.answer == CQAnswer.SATISFIED
        ]

        if disputes:
            report = (
                f"Cross-reference found disputing evidence. "
                f"Confidence docked to {new_conf:.2f} \u2014 {std.value}."
            )
        elif corrob_count > 0:
            sources_str = f"{corrob_count} independent source{'s' if corrob_count != 1 else ''}"
            report = (
                f"Cross-referenced across {sources_str}: "
                f"confidence {new_conf:.2f} \u2014 {std.value}."
            )
        else:
            report = (
                f"Cross-reference found no independent corroboration. "
                f"Confidence remains {new_conf:.2f} \u2014 {std.value}."
            )

        orch._speak_text(trace, report)
        orch._publish_caption(report, source="assistant", is_final=True)
        orch.history.append({"role": "user", "content": user_text})
        orch.history.append({"role": "assistant", "content": report})
        orch.play_ring.set_flag(FLAG_EOS)
        orch._finalize_turn(trace, None)
