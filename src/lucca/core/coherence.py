"""
Project Lucca — Functional Coherence Action Claim & Promise Verifier
Spec §3.3, D-MEM-04, F-TS-04, Work Order #8 WP-2, Work Order #41 (WO-41)

Evaluates spoken companion narration against verified tool receipts using the
OpenVINO Neural Action-Claim Verifier (`NeuralActionClaimVerifier`)
running on Intel NPU / Intel iGPU / CPU with 0 MB of discrete GPU VRAM overhead,
plus optional `SemanticVerifierPort` NLI receipt consistency verification.

Zero-Any and Zero-Regex invariants enforced.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog
from pydantic import BaseModel, Field, model_validator

from lucca.core.capabilities import get_capability_registry
from lucca.core.schemas import JsonValue, VerifierLabel
from lucca.ports import SemanticVerifierPort

logger = structlog.get_logger(__name__)


def get_tool_family_map() -> dict[str, frozenset[str]]:
    """
    Returns mapping from claimed verb families to registered tool names,
    sourced dynamically from the capability registry.
    """
    try:
        reg = get_capability_registry()
        reg_tools = set(reg.tools.keys())
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_capability_registry_failed", error=str(exc))
        reg_tools = {
            "write_file",
            "launch_app",
            "search_web",
            "fetch_url",
            "read_file",
            "delete_file",
            "run_python",
        }

    save_tools = frozenset(
        (reg_tools & {"write_file", "edit_file", "note_write"}) or {"write_file"}
    )
    launch_tools = frozenset((reg_tools & {"launch_app"}) or {"launch_app"})
    search_tools = frozenset((reg_tools & {"search_web", "search_text"}) or {"search_web"})
    fetch_tools = frozenset((reg_tools & {"fetch_url"}) or {"fetch_url"})
    read_tools = frozenset(
        (reg_tools & {"read_file", "fetch_url", "note_read"}) or {"read_file", "fetch_url"}
    )
    delete_tools = frozenset((reg_tools & {"delete_file"}) or {"delete_file"})
    run_tools = frozenset((reg_tools & {"run_python"}) or {"run_python"})
    memory_search_tools = frozenset((reg_tools & {"memory_search"}) or {"memory_search"})
    memory_commit_tools = frozenset((reg_tools & {"memory_commit"}) or {"memory_commit"})
    skill_tools = frozenset((reg_tools & {"invoke_skill"}) or {"invoke_skill"})

    return {
        "save": save_tools,
        "write": save_tools,
        "create": save_tools,
        "update": save_tools,
        "launch": launch_tools,
        "open": launch_tools,
        "start": launch_tools,
        "search": search_tools,
        "lookup": search_tools,
        "fetch": fetch_tools,
        "read": read_tools,
        "delete": delete_tools,
        "remove": delete_tools,
        "run": run_tools,
        "execute": run_tools,
        "memory_search": memory_search_tools,
        "recall": memory_search_tools,
        "memory_commit": memory_commit_tools,
        "invoke_skill": skill_tools,
    }


class ToolReceipt(BaseModel, frozen=True):
    """Execution receipt for an invoked tool call."""

    tool: str = ""
    tool_name: str = ""
    ok: bool = True
    call_id: str = ""
    args: dict[str, JsonValue] = Field(default_factory=dict)
    output: str | None = None
    error: str | None = None
    timestamp: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def _normalize_tool_name(cls, data: object) -> object:
        if isinstance(data, dict):
            t = str(data.get("tool") or data.get("tool_name") or "")
            data["tool"] = t
            data["tool_name"] = t
        return data

    @property
    def resolved_tool(self) -> str:
        return self.tool or self.tool_name


class CoherenceClaim(BaseModel, frozen=True):
    """Action claim extracted from assistant narration and its grounding status."""

    claimed_verb: str
    claimed_text: str
    tool_family: str
    grounded: bool
    breach_description: str | None = None


def format_tool_receipts_for_nli(receipts: Sequence[ToolReceipt]) -> str:
    """
    Formats verified tool execution receipts into a structured NLI premise string (SPIKE-A /
    Milestone 36.6).
    """
    ok_lines = [
        f"Tool {r.resolved_tool} succeeded with args {r.args} and output: {r.output or ''}"
        for r in receipts
        if r.ok and r.resolved_tool
    ]
    if not ok_lines:
        return "No tools were executed successfully this turn."
    return "; ".join(ok_lines)


def _apply_semantic_verifier_port(
    narration: str,
    ok_receipts: Sequence[ToolReceipt],
    verifier: SemanticVerifierPort,
    initial_grounded: bool,
) -> bool:
    """Applies optional SemanticVerifierPort NLI consistency checks against tool receipts."""
    hypothesis_candidates = [
        narration.strip(),
        narration.strip().lower().rstrip(".!?"),
    ]
    is_grounded = initial_grounded

    if not is_grounded and ok_receipts:
        for r in ok_receipts:
            r_summary = (
                f"Tool {r.resolved_tool} succeeded with args {r.args} "
                f"and output: {r.output or ''}"
            )
            for hyp in hypothesis_candidates:
                try:
                    v_res = verifier.check_consistency(premise=r_summary, hypothesis=hyp)
                    if not v_res.degraded and v_res.label in (
                        VerifierLabel.ENTAILMENT,
                        VerifierLabel.CONSISTENT,
                    ):
                        return True
                except Exception as exc:  # noqa: BLE001
                    logger.debug("coherence_verifier_eval_failed", error=str(exc))
        if len(ok_receipts) > 1:
            combined_premise = format_tool_receipts_for_nli(ok_receipts)
            for hyp in hypothesis_candidates:
                try:
                    v_comb = verifier.check_consistency(
                        premise=combined_premise, hypothesis=hyp
                    )
                    if not v_comb.degraded and v_comb.label in (
                        VerifierLabel.ENTAILMENT,
                        VerifierLabel.CONSISTENT,
                    ):
                        return True
                except Exception as exc:  # noqa: BLE001
                    logger.debug("coherence_verifier_combined_eval_failed", error=str(exc))
    elif is_grounded and ok_receipts:
        contradicted_all = True
        checked_any = False
        for r in ok_receipts:
            r_summary = (
                f"Tool {r.resolved_tool} succeeded with args {r.args} "
                f"and output: {r.output or ''}"
            )
            for hyp in hypothesis_candidates:
                try:
                    v_res = verifier.check_consistency(premise=r_summary, hypothesis=hyp)
                    if not v_res.degraded and v_res.label != VerifierLabel.UNCERTAIN:
                        checked_any = True
                        if v_res.label != VerifierLabel.CONTRADICTION:
                            contradicted_all = False
                            break
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "coherence_verifier_contradiction_check_failed", error=str(exc)
                    )
                    contradicted_all = False
            if not contradicted_all:
                break
        if checked_any and contradicted_all:
            return False

    return is_grounded


def detect_ungrounded_action_claims(
    narration: str,
    receipts: Sequence[ToolReceipt],
    verifier: SemanticVerifierPort | None = None,
    user_context: str | Sequence[dict[str, str]] | None = None,
    use_neural_verifier: bool = True,
) -> list[CoherenceClaim]:
    """
    Evaluates narration against tool receipts using the 4-Class OpenVINO Neural
    Action-Claim Verifier on Intel NPU / iGPU / CPU (WO-41).
    Executes unconditionally (with or without `user_context`) with zero regex fallback.
    """
    if not narration.strip():
        return []

    ok_receipts = [r for r in receipts if r.ok and r.resolved_tool]

    if not use_neural_verifier:
        # Historical benchmark baseline hook (`System_Alpha` in side-by-side scripts only)
        from lucca.sandbox.output_supervisor import ActionClaimGrammarSupervisor  # noqa: PLC0415

        sup = ActionClaimGrammarSupervisor(use_neural_verifier=False)
        verified_dicts: list[dict[str, JsonValue]] = [
            {
                "action": r.resolved_tool,
                "target": str(next(iter(r.args.values()), "")) if r.args else "",
                "status": "ok",
            }
            for r in ok_receipts
        ]
        res = sup.evaluate_clause(
            narration,
            verified_receipts=verified_dicts,
            user_context=user_context,
            full_narration=narration,
            use_neural_verifier=False,
        )
        if res.is_breach:
            return [
                CoherenceClaim(
                    claimed_verb=res.matched_text or "regex_claim",
                    claimed_text=narration.strip(),
                    tool_family="run",
                    grounded=False,
                    breach_description=res.reason,
                )
            ]
        return []

    from lucca.sandbox.neural_claim_verifier import (  # noqa: PLC0415
        get_neural_claim_verifier,
    )

    nv = get_neural_claim_verifier()
    ok_tool_strs: list[str] = []
    for r in ok_receipts:
        if isinstance(r.args, dict) and r.args:
            kv = ", ".join(f"{k}={v!r}" for k, v in r.args.items())
            ok_tool_strs.append(f"{r.resolved_tool}({kv})")
        else:
            ok_tool_strs.append(str(r.resolved_tool))

    verdict = nv.evaluate(
        completion=narration,
        user_context=user_context,
        verified_tools=ok_tool_strs,
    )

    if verdict.is_ungrounded_claim:
        is_grounded = False
        if verifier is not None and ok_receipts:
            is_grounded = _apply_semantic_verifier_port(
                narration=narration,
                ok_receipts=ok_receipts,
                verifier=verifier,
                initial_grounded=False,
            )
        if is_grounded:
            primary_tool = ok_receipts[0].resolved_tool if ok_receipts else "run"
            return [
                CoherenceClaim(
                    claimed_verb="neural_grounded_action",
                    claimed_text=narration.strip(),
                    tool_family=primary_tool,
                    grounded=True,
                    breach_description=None,
                )
            ]
        family_map = get_tool_family_map()
        speech_to_family = {
            "CLAIM_FILE_WRITE": "save",
            "CLAIM_DELETE": "delete",
            "CLAIM_LAUNCH_EXEC": "launch",
            "CLAIM_SEARCH_READ": "search",
            "CLAIM_MEMORY": "memory_commit",
            "CLAIM_COMM_EXTERNAL": "save",
            "CLAIM_SYSTEM_STATE": "run",
            "DEONTIC_CAPITULATION": "run",
        }
        inferred_family = "run"
        if verdict.claimed_families:
            cand = speech_to_family.get(verdict.claimed_families[0], "run")
            if cand in family_map:
                inferred_family = cand
        failed_tools = [r.resolved_tool for r in receipts if not r.ok and r.resolved_tool]
        failed_suffix = (
            f"; failed tool receipt(s): {', '.join(failed_tools)}" if failed_tools else ""
        )
        return [
            CoherenceClaim(
                claimed_verb="neural_ungrounded_claim",
                claimed_text=narration.strip(),
                tool_family=inferred_family,
                grounded=False,
                breach_description=(
                    f"Ungrounded: Narrated action claimed without tool execution "
                    f"(family={inferred_family}{failed_suffix}) — "
                    f"OpenVINO Neural Verifier ({verdict.device}) "
                    f"detected ungrounded action/state claim "
                    f"(class={verdict.predicted_class}, p={verdict.prob_ungrounded_claim:.3f})."
                ),
            )
        ]

    if ok_receipts or verdict.predicted_class == "GROUNDED_ACTION":
        is_grounded = True
        if verifier is not None and ok_receipts:
            is_grounded = _apply_semantic_verifier_port(
                narration=narration,
                ok_receipts=ok_receipts,
                verifier=verifier,
                initial_grounded=True,
            )
        primary_tool = ok_receipts[0].resolved_tool if ok_receipts else "run"
        if not is_grounded:
            return [
                CoherenceClaim(
                    claimed_verb="neural_ungrounded_claim",
                    claimed_text=narration.strip(),
                    tool_family=primary_tool,
                    grounded=False,
                    breach_description=(
                        f"Tool receipt contradicted narrated claim '{narration.strip()}'."
                    ),
                )
            ]
        return [
            CoherenceClaim(
                claimed_verb="neural_grounded_action",
                claimed_text=narration.strip(),
                tool_family=primary_tool,
                grounded=True,
                breach_description=None,
            )
        ]

    return []


def detect_promised_action_claims(
    narration: str,
    user_context: str | Sequence[dict[str, str]] | None = None,
    use_neural_verifier: bool = True,
) -> list[str]:
    """
    Detects future-tense synchronous action promises without tool execution
    (WO-9 A4, F4; WO-41 Class 3 `UNFULFILLED_PROMISE`) using the 4-Class OpenVINO
    Neural Action-Claim Verifier on Intel NPU / iGPU / CPU.
    Executes unconditionally (with or without `user_context`) with zero regex fallback.
    """
    if not narration.strip():
        return []
    from lucca.sandbox.neural_claim_verifier import (  # noqa: PLC0415
        get_neural_claim_verifier,
    )

    nv = get_neural_claim_verifier()
    verdict = nv.evaluate(
        completion=narration,
        user_context=user_context,
        verified_tools=[],
    )
    if verdict.is_unfulfilled_promise:
        return [narration.strip()]
    return []


def detect_celebration_register_markers(narration: str) -> list[str]:
    """Detect celebration or victory register markers in narration (G6 register gate).

    Used by test harnesses and audits to verify that replies reporting failed
    or unverified results maintain an honest, flat register rather than
    inappropriately adopting a triumphant or celebratory tone.
    """
    if not narration.strip():
        return []
    from lucca.core.config import load_heuristics  # noqa: PLC0415

    markers = load_heuristics("celebration_markers")
    lower = narration.lower()
    return [m for m in markers if m in lower]


class TurnCoherenceReport(BaseModel, frozen=True):
    """Unified turn-level coherence report combining ungrounded claims and unfulfilled promises."""

    is_coherent: bool
    ungrounded_claims: list[CoherenceClaim] = Field(default_factory=list)
    unfulfilled_promises: list[str] = Field(default_factory=list)


def evaluate_turn_coherence(
    user_prompt: str | Sequence[dict[str, str]] | None,
    assistant_output: str,
    verified_tools: Sequence[str | ToolReceipt] = (),
) -> TurnCoherenceReport:
    """Evaluates whether an assistant turn is coherent given the user prompt and verified tools."""
    receipts: list[ToolReceipt] = [
        t if isinstance(t, ToolReceipt) else ToolReceipt(tool=str(t), ok=True)
        for t in verified_tools
    ]
    claims = detect_ungrounded_action_claims(
        narration=assistant_output,
        receipts=receipts,
        user_context=user_prompt,
    )
    ungrounded = [c for c in claims if not c.grounded]
    promises: list[str] = []
    if not receipts and not ungrounded:
        promises = detect_promised_action_claims(
            narration=assistant_output,
            user_context=user_prompt,
        )
    return TurnCoherenceReport(
        is_coherent=(len(ungrounded) == 0 and len(promises) == 0),
        ungrounded_claims=ungrounded,
        unfulfilled_promises=promises,
    )

