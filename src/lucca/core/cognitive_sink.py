"""
Project Lucca — Sovereign Cognitive Outcome Sink
Spec D-AUD-01, D-AUD-13, WO-36 Milestone 36.1, G-WO36-OUTCOME-SINK

Unifies CEGIS program induction and self-repair outcomes across:
1. Cryptographic Provenance Receipting: Signs ASSISTANT_ACTION envelope via ToolResultSigner.
2. Working Memory Proof Tracing: Appends intermediate CEGIS repair steps to ReasoningContext.proof_trace().
3. Case-Based Reasoning Fast Path: Persists multi-turn repair episodes to EpisodeRecall and execution_triples.
4. Deterministic Affective Appraisal: Injects EUREKA_DISCOVERY / TASK_SUCCESS / TOOL_FAILURE into AffectiveODEMachine.
   Evidential weight strictly stays 0.0 per personhood invariants.

Zero-Any typing invariant strictly enforced per D-AUD-01.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING

import structlog

from lucca.core.affective_ode import AffectSignal3D, AffectiveODEMachine
from lucca.core.config import resolve_or_create_master_key
from lucca.core.episode_recall import EpisodeRecall
from lucca.core.reasoning_context import ReasoningContext
from lucca.core.schemas import Provenance, RecallEpisode, SignedPayload, UnsignedPayload
from lucca.memory.signers import ToolResultSigner, create_tool_result_signer

if TYPE_CHECKING:
    from lucca.memory.db import DatabaseManager

logger = structlog.get_logger(__name__)


class CognitiveOutcomeSink:
    """
    Sovereign Cognitive Outcome Sink unifying CEGIS outcomes into working memory,
    episodic recall, and continuous affective dynamics.
    """

    def __init__(
        self,
        action_signer: ToolResultSigner | None = None,
        reasoning_context: ReasoningContext | None = None,
        episode_recall: EpisodeRecall | None = None,
        affect_machine: AffectiveODEMachine | None = None,
        db: DatabaseManager | None = None,
    ) -> None:
        self.action_signer = action_signer
        self.reasoning_context = reasoning_context
        self.episode_recall = episode_recall
        self.affect_machine = affect_machine
        self.db = db

    def record_cegis_outcome(
        self,
        task_id: str,
        problem_summary: str,
        engine_name: str,
        success: bool,
        turns_taken: int,
        final_code: str | None = None,
        turn_1_error: str | None = None,
        verified_strategy: str | None = None,
        turn_traces: list[dict[str, object]] | None = None,
        status_label: str = "VERIFIED_REPAIRED_PROGRAM",
        action_signer: ToolResultSigner | None = None,
        reasoning_context: ReasoningContext | None = None,
        episode_recall: EpisodeRecall | None = None,
        affect_machine: AffectiveODEMachine | None = None,
        db: DatabaseManager | None = None,
    ) -> dict[str, object]:
        """
        Processes and records a completed CEGIS induction/repair run into all cognitive substrates.
        Enforces G-WO36-OUTCOME-SINK pre-registered acceptance criteria.
        """
        signer = action_signer or self.action_signer
        r_ctx = reasoning_context or self.reasoning_context
        cbr = episode_recall or self.episode_recall
        ode = affect_machine or self.affect_machine
        db_mgr = db or self.db

        turn_1_err = turn_1_error or ("Initial syntax/semantic error" if turns_taken >= 2 else None)
        repair_strat = verified_strategy or ("Counterexample-guided repair" if turns_taken >= 2 else None)

        # 1. Sign ASSISTANT_ACTION Provenance Receipt
        signed_receipt: SignedPayload | None = None
        if signer is None:
            resolved_key = resolve_or_create_master_key()
            signer = create_tool_result_signer(master_key=resolved_key, signer_id=f"cegis@{engine_name}")

        receipt_content = (
            f"CEGIS Execution Receipt: task={task_id} engine={engine_name} success={success} "
            f"turns={turns_taken} status={status_label}"
        )
        now = time.time()
        unsigned = UnsignedPayload(
            provenance=Provenance.ASSISTANT_ACTION,
            kind="action_receipt",
            content=receipt_content,
            created_at=now,
            nonce=uuid.uuid4().hex,
        )
        signed_receipt = signer.sign(unsigned)
        logger.debug(
            "cognitive_sink_action_signed",
            entry_id=signed_receipt.entry_id,
            task_id=task_id,
            turns=turns_taken,
            success=success,
        )

        # 2. Append CEGIS Repair Steps to Working Memory Proof Trace
        if r_ctx is not None:
            traces = turn_traces or []
            if not traces:
                # Synthesize standard multi-turn trace steps
                for t_idx in range(1, turns_taken + 1):
                    step_name = "initial_synthesis" if t_idx == 1 else f"repair_turn_{t_idx}"
                    step_status = "error_detected" if (t_idx < turns_taken or not success) else "verified_repair"
                    step_obj = f"status={step_status}; code_len={len(final_code or '')}"
                    traces.append(
                        {
                            "turn": t_idx,
                            "name": step_name,
                            "summary": step_obj,
                        }
                    )

            for t_item in traces:
                t_num = str(t_item.get("turn", 1))
                t_name = str(t_item.get("name", "step"))
                t_sum = str(t_item.get("summary", "evaluated"))
                r_ctx.add_intermediate(
                    envelope_id=signed_receipt.entry_id,
                    s=f"task:{task_id}",
                    p=f"turn_{t_num}:{t_name}",
                    o=t_sum,
                    confidence=1.0 if success else 0.5,
                    step_kind="cegis_repair",
                    rule_id=f"cegis:{engine_name}",
                )

        # 3. Fast-Path Episodic Memory Recording (Turns >= 2 and Success == True)
        episode_created: RecallEpisode | None = None
        if success and turns_taken >= 2 and cbr is not None:
            ep_summary = (
                f"CEGIS repaired solution for {problem_summary}: "
                f"Turn 1 error [{turn_1_err or 'None'}] fixed by [{repair_strat or 'program synthesis'}]"
            )
            episode_created = RecallEpisode(
                source="execution_triples",
                record_id=f"ep-cegis-{uuid.uuid4().hex[:12]}",
                ts=time.time(),
                match_score=10,
                tokens_total=len(ep_summary.split()),
                summary=ep_summary,
                payload={
                    "task_id": task_id,
                    "engine": engine_name,
                    "turns_taken": turns_taken,
                    "turn_1_error": turn_1_err or "",
                    "verified_repair_strategy": repair_strat or "",
                    "final_code": final_code or "",
                    "envelope_id": signed_receipt.entry_id,
                },
            )
            cbr.add_episode(episode_created)
            logger.info(
                "cognitive_sink_episode_recorded",
                record_id=episode_created.record_id,
                task_id=task_id,
            )

            # Persistence to SQLite execution_triples (0004_execution_triples.sql schema)
            if db_mgr is not None:
                try:
                    writer = db_mgr.get_writer() if hasattr(db_mgr, "get_writer") else getattr(db_mgr, "conn", None)
                    if writer is not None:
                        prop_json = json.dumps(
                            {
                                "task_id": task_id,
                                "transcript": problem_summary,
                                "summary": ep_summary,
                                "turn_1_error": turn_1_err or "",
                            }
                        )
                        dec_json = json.dumps(
                            {
                                "action": f"cegis:{engine_name}",
                                "turns_taken": turns_taken,
                                "strategy": repair_strat or "",
                            }
                        )
                        out_json = json.dumps(
                            {
                                "ok": True,
                                "status": status_label,
                                "envelope_id": signed_receipt.entry_id,
                            }
                        )
                        writer.execute(
                            """
                            INSERT OR IGNORE INTO execution_triples
                            (triple_id, proposal_json, decision_json, outcome_json, created_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                episode_created.record_id,
                                prop_json,
                                dec_json,
                                out_json,
                                time.time(),
                            ),
                        )
                        if hasattr(writer, "commit"):
                            writer.commit()
                except Exception as db_err:  # noqa: BLE001
                    logger.debug("execution_triples_write_ignored", error=str(db_err))

        # 4. Deterministic 3D PAD Continuous Affective Appraisal
        affect_signal_injected: AffectSignal3D | None = None
        dominance_before: float | None = None
        dominance_after: float | None = None
        if ode is not None:
            dominance_before = ode.state.dominance
            if success:
                if turns_taken >= 2 or status_label == "VERIFIED_REPAIRED_PROGRAM":
                    affect_signal_injected = AffectSignal3D.EUREKA_DISCOVERY
                else:
                    affect_signal_injected = AffectSignal3D.TASK_SUCCESS
            else:
                affect_signal_injected = AffectSignal3D.TOOL_FAILURE

            ode.inject_signal(affect_signal_injected)
            dominance_after = ode.state.dominance
            logger.info(
                "cognitive_sink_affect_appraised",
                signal=affect_signal_injected.value,
                dominance_delta=(dominance_after - dominance_before),
            )

        return {
            "signed_receipt": signed_receipt,
            "receipt_id": signed_receipt.entry_id if signed_receipt else None,
            "proof_steps": r_ctx.proof_trace() if r_ctx is not None else [],
            "episode": episode_created,
            "affect_signal": affect_signal_injected.value if affect_signal_injected else None,
            "dominance_delta": (
                (dominance_after - dominance_before)
                if (dominance_before is not None and dominance_after is not None)
                else 0.0
            ),
            "evidential_weight": 0.0,
        }
