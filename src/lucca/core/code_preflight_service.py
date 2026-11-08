"""
Project Lucca — Code Preflight & Case-Based Reasoning Synthesis Service (WO-43 Phase 2, Sub-Step
2.5)
WO-26 Phase 4 & WO-39 Milestone 2.2

Encapsulates Tier 3 code synthesis with Case-Based Reasoning (4 Rs: Retrieve, Reuse,
Revise, Retain), autonomous Docker pre-flight verification, 1-shot self-repair,
and impasse_backlog persistence.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
import ulid

from lucca.core.ipc_schemas import Envelope, PlayBeginPayload
from lucca.core.schemas import MemoryHit, TokenDelta
from lucca.core.trace import TurnTrace, now_ns
from lucca.sandbox.preflight import extract_python_code
from lucca.sandbox.schemas import PreflightResult
from lucca.senses.ring_buffer import FLAG_EOS

if TYPE_CHECKING:
    from lucca.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


class CodePreflightService:
    """Executes CBR-assisted code synthesis, Docker pre-flight verification, and impasse logging."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orch = orchestrator

    def ensure_impasse_backlog_table(self) -> None:
        orch = self._orch
        if orch.db is None or not hasattr(orch.db, "write_transaction"):
            return
        try:
            with orch.db.write_transaction() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS impasse_backlog (
                        id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        code TEXT NOT NULL,
                        error_trace TEXT NOT NULL,
                        resolved_code TEXT NOT NULL DEFAULT '',
                        surprise_score REAL NOT NULL DEFAULT 0.85,
                        created_at TEXT NOT NULL,
                        processed INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("impasse_backlog_table_init_error", error=str(exc))

    def log_impasse_to_backlog(
        self,
        query: str,
        code: str,
        error_trace: str,
        resolved_code: str = "",
        surprise_score: float = 0.85,
    ) -> None:
        """
        Records a failed or repaired code synthesis episode into impasse_backlog for offline
        consolidation.
        """
        orch = self._orch
        if orch.db is None or not hasattr(orch.db, "write_transaction"):
            return
        try:
            self.ensure_impasse_backlog_table()
            impasse_id = f"imp-{ulid.ULID()}"
            created_iso = str(time.time())
            with orch.db.write_transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO impasse_backlog (
                        id, query, code, error_trace, resolved_code, surprise_score, created_at,
                        processed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        impasse_id,
                        query[:1000],
                        code[:4000],
                        error_trace[:2000],
                        resolved_code[:4000],
                        float(surprise_score),
                        created_iso,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("log_impasse_to_backlog_failed", error=str(exc))

    def synthesize_code_with_preflight(
        self,
        prompt: str,
        initial_code: str | None = None,
        trace: TurnTrace | None = None,
        docstring_examples: list[str] | None = None,
        max_repair_rounds: int = 1,
        enable_preflight: bool = True,
    ) -> tuple[str, PreflightResult]:
        """
        WO-26 Phase 4 & WO-39 Milestone 2.2: Tier 3 Code Synthesis with Case-Based Reasoning (4 Rs)
        and Autonomous Docker Pre-Flight Verification Loop.
        """
        orch = self._orch
        t0 = time.perf_counter()
        code_candidate = initial_code
        cbr_cache = getattr(orch, "episodic_code_cache", None)
        used_precedent = None

        # CBR Step 1 & 2: Retrieve & Reuse precedent before raw LLM synthesis
        if code_candidate is None and cbr_cache is not None and prompt.strip():
            try:
                precedent = cbr_cache.retrieve_precedent(query=prompt)
                if precedent is not None:
                    adapted = cbr_cache.adapt_and_reuse(precedent, prompt)
                    if adapted and adapted.strip():
                        if not enable_preflight:
                            cbr_cache.record_reuse_outcome(precedent.task_hash, success=True)
                            elapsed = (time.perf_counter() - t0) * 1000.0
                            return adapted, PreflightResult(
                                success=True,
                                error_msg=None,
                                elapsed_ms=elapsed,
                                assertions_run=0,
                                fail_open=False,
                            )
                        cbr_check = orch.sandbox.preflight_verify_code(
                            code=adapted, docstring_examples=docstring_examples
                        )
                        if cbr_check.success:
                            cbr_cache.record_reuse_outcome(precedent.task_hash, success=True)
                            cbr_cache.retain_episode(
                                query=prompt,
                                code=adapted,
                                method="CBR_REUSE",
                                turns_taken=1,
                            )
                            return adapted, cbr_check
                        cbr_cache.record_reuse_outcome(precedent.task_hash, success=False)
                        used_precedent = precedent
            except Exception as cbr_exc:  # noqa: BLE001
                logger.debug("cbr_retrieve_reuse_failed", error=str(cbr_exc))

        if code_candidate is None:
            instruction = (
                "Complete the following Python coding task. Put all Python code inside a ```python "
                "... ``` block.\n\n"
                f"{prompt}"
            )
            if used_precedent is not None:
                instruction += (
                    f"\n\nNote: A prior precedent exists but required adaptation:\n"
                    f"```python\n{used_precedent.code}\n```"
                )
            resp_parts: list[str] = []
            for event in orch.llm.stream_turn(
                current_text=instruction,
                max_tokens=1024,
                enable_thinking=False,
            ):
                if isinstance(event, TokenDelta) and event.delta:
                    resp_parts.append(event.delta)
            raw_resp = "".join(resp_parts)
            code_candidate = extract_python_code(raw_resp)

        if not enable_preflight:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return code_candidate, PreflightResult(
                success=True, error_msg=None, elapsed_ms=elapsed, assertions_run=0, fail_open=False
            )

        # CBR Step 3 (Revise): Preflight verification against Docker sandbox
        preflight_res = orch.sandbox.preflight_verify_code(
            code=code_candidate, docstring_examples=docstring_examples
        )

        # If passed or fail-open honored (timeout/unavailable), return candidate
        if preflight_res.success or preflight_res.fail_open or max_repair_rounds <= 0:
            if preflight_res.success and cbr_cache is not None and code_candidate.strip():
                try:
                    cbr_cache.retain_episode(
                        query=prompt,
                        code=code_candidate,
                        method="PreflightCEGIS",
                        turns_taken=1,
                    )
                except Exception as retain_err:  # noqa: BLE001
                    logger.debug("cbr_retain_failed", error=str(retain_err))
            elif not preflight_res.success:
                orch._log_impasse_to_backlog(
                    query=prompt,
                    code=code_candidate,
                    error_trace=str(preflight_res.error_msg or "PreflightVerificationError"),
                )
            sink = getattr(orch, "cognitive_outcome_sink", None) or getattr(
                orch, "cognitive_sink", None
            )
            if sink is not None:
                try:
                    sink.record_cegis_outcome(
                        task_id=trace.trace_id if trace else f"preflight-{ulid.ULID()}",
                        problem_summary=prompt.strip()[:120],
                        engine_name="PreflightCEGIS",
                        success=preflight_res.success,
                        turns_taken=1,
                        final_code=code_candidate,
                        turn_1_error=preflight_res.error_msg,
                        status_label="VERIFIED_PROGRAM"
                        if preflight_res.success
                        else "INTERNAL_FALLBACK",
                        reasoning_context=getattr(orch, "current_reasoning_context", None),
                    )
                except Exception as sink_err:  # noqa: BLE001
                    logger.debug("preflight_sink_record_failed", error=str(sink_err))
            return code_candidate, preflight_res

        # 1-Shot Self-Repair Loop
        logger.warning(
            "preflight_verification_failed_triggering_self_repair",
            error=preflight_res.error_msg,
            assertions_run=preflight_res.assertions_run,
        )

        repair_prompt = (
            "The following Python code failed preflight verification against specification "
            "docstrings and test assertions in Docker:\n"
            f"```python\n{code_candidate}\n```\n\n"
            f"Preflight Error Details:\n{preflight_res.error_msg}\n\n"
            "Please fix the bug (check boundary conditions, empty sequences, zero/negative inputs, "
            "trailing punctuation, or rounding logic). "
            "Provide only the corrected complete Python implementation inside a ```python ... ``` "
            "block."
        )

        repair_parts: list[str] = []
        for event in orch.llm.stream_turn(
            current_text=repair_prompt,
            max_tokens=1024,
            enable_thinking=False,
        ):
            if isinstance(event, TokenDelta) and event.delta:
                repair_parts.append(event.delta)

        repaired_raw = "".join(repair_parts)
        repaired_code = extract_python_code(repaired_raw)
        if not repaired_code or not repaired_code.strip():
            orch._log_impasse_to_backlog(
                query=prompt,
                code=code_candidate,
                error_trace=str(preflight_res.error_msg or "PreflightVerificationError"),
            )
            return code_candidate, preflight_res

        repaired_res = orch.sandbox.preflight_verify_code(
            code=repaired_code, docstring_examples=docstring_examples
        )
        orch._log_impasse_to_backlog(
            query=prompt,
            code=code_candidate,
            error_trace=str(preflight_res.error_msg or "PreflightVerificationError"),
            resolved_code=repaired_code if repaired_res.success else "",
        )
        if repaired_res.success and cbr_cache is not None:
            try:
                cbr_cache.retain_episode(
                    query=prompt,
                    code=repaired_code,
                    method="PreflightRepair",
                    turns_taken=2,
                )
            except Exception as retain_err:  # noqa: BLE001
                logger.debug("cbr_repair_retain_failed", error=str(retain_err))
        sink = getattr(orch, "cognitive_outcome_sink", None) or getattr(
            orch, "cognitive_sink", None
        )
        if sink is not None:
            try:
                sink.record_cegis_outcome(
                    task_id=trace.trace_id if trace else f"preflight-{ulid.ULID()}",
                    problem_summary=prompt.strip()[:120],
                    engine_name="PreflightCEGIS",
                    success=repaired_res.success,
                    turns_taken=2,
                    final_code=repaired_code,
                    turn_1_error=preflight_res.error_msg,
                    verified_strategy="Preflight assertion self-repair",
                    status_label="VERIFIED_REPAIRED_PROGRAM"
                    if repaired_res.success
                    else "INTERNAL_FALLBACK",
                    reasoning_context=getattr(orch, "current_reasoning_context", None),
                )
            except Exception as sink_err:  # noqa: BLE001
                logger.debug("preflight_repair_sink_record_failed", error=str(sink_err))
        return repaired_code, repaired_res

    def stream_code_synthesis(
        self,
        trace: TurnTrace,
        user_msg: str,
        decision_id: str | None = None,
        current_text: str | None = None,
        memories: list[MemoryHit] | None = None,
        epistemic_context: str | None = None,
    ) -> None:
        """WO-26 Phase 4: Tier 3 Code Synthesis Turn Handler."""
        _ = (memories, epistemic_context)
        orch = self._orch
        begin_env = Envelope(
            type="play.begin",
            trace_id=trace.trace_id,
            ts_ns=now_ns(),
            src="core",
            payload=PlayBeginPayload(trace_id=trace.trace_id).model_dump(),
        )
        orch._publish_bus(begin_env)

        cue = "Testing implementation in the sandbox..."
        orch._speak_text(trace, cue)

        prompt = current_text or user_msg
        code, preflight_res = orch.synthesize_code_with_preflight(prompt=prompt, trace=trace)

        if preflight_res.success:
            spoken_summary = "I've written and verified the implementation in the sandbox."
            full_response = f"Here is the verified implementation:\n\n```python\n{code}\n```"
        else:
            spoken_summary = "I've generated the function, though an assertion warning was noted."
            full_response = (
                f"```python\n{code}\n```\n\n*Note: Preflight check reported:* "
                f"`{preflight_res.error_msg}`"
            )

        orch._publish_caption(full_response, source="assistant", is_final=True)
        orch._speak_text(trace, spoken_summary)
        orch.play_ring.set_flag(FLAG_EOS)

        orch.history.append({"role": "user", "content": user_msg})
        orch.history.append({"role": "assistant", "content": full_response})
        orch.current_turn_assistant_reply = full_response
        orch._finalize_turn(trace, decision_id)
