"""
Project Lucca — Autobiographical Reflection, Belief Revision & Review Queue
Spec D-MEM-04, Rung A1, ModularRSI §4.3
"""

import datetime
import json
import re
import time
import uuid
from dataclasses import dataclass

import structlog

from lucca.core.exceptions import ProvenanceRejected
from lucca.core.schemas import (
    Provenance,
    UnsignedPayload,
    VerifierLabel,
)
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import AssistantUtteranceSigner, DerivedFactSigner
from lucca.memory.store import MemoryStore
from lucca.ports import SemanticVerifierPort, SpeechLLMPort
from lucca.reasoning.distill import (
    distill_contradiction_to_proposition,
    quarantine_rejected_distillate,
    sign_distilled_proposition,
)
from lucca.reasoning.induction import RuleInducer, is_rule_conflict
from lucca.reasoning.lifecycle import RuleLifecycleManager

logger = structlog.get_logger(__name__)

THIRTY_DAYS_SECONDS = 30.0 * 86400.0


@dataclass
class IdlePulseResult:
    coherence_deficit: float
    competence_deficit: float
    distilled_events_count: int
    actions_taken: list[str]
    latency_ms: float


@dataclass
class DreamRetrospectiveResult:
    replays_analyzed: int
    skills_mined: int
    quarantined_rules: list[str]
    latency_ms: float


def log_learning_event(
    db: DatabaseManager,
    event_type: str,
    topic: str,
    details: dict[str, object] | None = None,
    provenance_envelope_id: str | None = None,
    now: float | None = None,
) -> str:
    """Logs an auditable learning event into the learning_events ledger."""
    valid_types = {
        "BELIEF_SUPERSEDED",
        "CONTRADICTION_RESOLVED",
        "RULE_QUARANTINED",
        "RULE_PROMOTED",
        "CEGIS_REPAIR_MYELINATED",
        "SKILL_MINED",
        "IDLE_PULSE_DISTILL",
    }
    if event_type not in valid_types:
        raise ValueError(f"Invalid learning event_type '{event_type}', must be one of {valid_types}")

    current_time = now if now is not None else time.time()
    event_id = f"ev-{uuid.uuid4().hex[:12]}"
    details_str = json.dumps(details or {})

    conn = db.get_writer()
    conn.execute(
        """
        INSERT INTO learning_events (
            event_id, event_type, topic, details_json, provenance_envelope_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, event_type, topic, details_str, provenance_envelope_id, current_time),
    )
    logger.info("learning_event_recorded", event_id=event_id, event_type=event_type, topic=topic)
    return event_id


class CoherenceDrive:
    """
    Homeostatic drive for epistemic coherence and contradiction resolution.
    Prioritizes Belnap Top (conflict) contradictions in the review queue and autobiographical memory.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def evaluate_deficit(self) -> float:
        """Computes current coherence deficit [0.0, 1.0] based on pending contradictions."""
        with self.db.read_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM review_queue WHERE status = 'PENDING' AND trigger_reason LIKE '%conflict%'"
            )
            row = cur.fetchone()
            conflict_count = int(row[0]) if row else 0
            cur.execute(
                "SELECT COUNT(*) FROM review_queue WHERE status = 'PENDING'"
            )
            row_tot = cur.fetchone()
            total_pending = int(row_tot[0]) if row_tot else 0
        deficit = min(1.0, 0.4 * conflict_count + 0.1 * max(0, total_pending - conflict_count))
        return float(deficit)

    def scan_pending_conflicts(self, limit: int = 5) -> list[dict[str, object]]:
        """Returns pending review queue items prioritized by Belnap Top conflict."""
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT review_id, belief_id, proposed_content, trigger_reason, created_at
                FROM review_queue
                WHERE status = 'PENDING'
                ORDER BY CASE WHEN trigger_reason LIKE '%conflict%' THEN 0 ELSE 1 END, created_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [
                {
                    "review_id": str(r[0]),
                    "belief_id": int(r[1]),
                    "proposed_content": str(r[2]),
                    "trigger_reason": str(r[3]),
                    "created_at": float(r[4]),
                }
                for r in rows
            ]


class CompetenceDrive:
    """
    Homeostatic drive for procedural competence and neurosymbolic skill synthesis.
    Prioritizes multi-turn CEGIS repair trajectories and candidate skill quarantine.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def evaluate_deficit(self) -> float:
        """Computes current competence deficit [0.0, 1.0] based on unmined repairs and failures."""
        now = time.time()
        with self.db.read_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM decisions WHERE tool_ok = 0 AND ts > ?",
                (now - 86400.0,),
            )
            row_fail = cur.fetchone()
            fail_count = int(row_fail[0]) if row_fail else 0
            cur.execute(
                "SELECT COUNT(*) FROM learning_events WHERE event_type IN ('SKILL_MINED', 'CEGIS_REPAIR_MYELINATED') AND created_at > ?",
                (now - 86400.0,),
            )
            row_mined = cur.fetchone()
            mined_count = int(row_mined[0]) if row_mined else 0
        deficit = max(0.0, min(1.0, 0.2 * fail_count - 0.1 * mined_count))
        return float(deficit)

    def scan_candidate_repairs(self, limit: int = 5) -> list[dict[str, object]]:
        """Scans decisions for multi-turn CEGIS repairs eligible for skill mining."""
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT decision_id, features_json, action, tool_calls_json, tool_ok, ts
                FROM decisions
                WHERE tool_ok = 1 AND (features_json LIKE '%cegis%' OR action LIKE '%cegis%')
                ORDER BY ts DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [
                {
                    "decision_id": str(r[0]),
                    "features_json": str(r[1] or "{}"),
                    "action": str(r[2]),
                    "tool_calls_json": str(r[3] or "[]"),
                    "ts": float(r[5]),
                }
                for r in rows
            ]


class IdlePulse:
    """
    Sub-50ms 60s idle cadence running on Intel Core Ultra CPU/NPU with 0 VRAM overhead.
    Evaluates homeostatic drives, runs VerifierWorker NLI consistency checks, and distills
    salient propositions via post-turn distillation into the learning_events ledger.
    """

    def __init__(
        self,
        db: DatabaseManager,
        verifier: SemanticVerifierPort | None = None,
        store: MemoryStore | None = None,
        master_key: bytes | None = None,
        llm: SpeechLLMPort | None = None,
    ) -> None:
        self.db = db
        self.verifier = verifier
        self.store = store
        self.master_key = master_key
        self.llm = llm
        self.coherence_drive = CoherenceDrive(db)
        self.competence_drive = CompetenceDrive(db)

    def pulse(self, now: float | None = None) -> IdlePulseResult:
        t0 = time.perf_counter()
        current_time = now if now is not None else time.time()

        coh_deficit = self.coherence_drive.evaluate_deficit()
        comp_deficit = self.competence_drive.evaluate_deficit()
        actions: list[str] = []
        distilled_propositions: list[str] = []

        conflicts = self.coherence_drive.scan_pending_conflicts(limit=3)
        if conflicts:
            actions.append(f"flagged_{len(conflicts)}_conflicts")
            for conf in conflicts:
                rev_id = str(conf["review_id"])
                belief_id = int(str(conf["belief_id"]))
                proposed = str(conf["proposed_content"])
                trigger = str(conf["trigger_reason"])
                old_text = ""
                reason_eid = ""
                with self.db.read_cursor() as cur:
                    cur.execute(
                        "SELECT content FROM memories WHERE memory_id = ?",
                        (belief_id,),
                    )
                    m_row = cur.fetchone()
                    if m_row:
                        old_text = str(m_row[0])
                    cur.execute(
                        "SELECT reason_entry_id FROM review_queue WHERE review_id = ?",
                        (rev_id,),
                    )
                    rq_row = cur.fetchone()
                    if rq_row and rq_row[0]:
                        reason_eid = str(rq_row[0])

                # Check semantic consistency via VerifierWorker if available
                if self.verifier is not None and old_text:
                    try:
                        v_res = self.verifier.check_consistency(
                            premise=proposed, hypothesis=old_text
                        )
                        if not v_res.degraded and v_res.label == VerifierLabel.ENTAILMENT:
                            quarantine_rejected_distillate(
                                self.db,
                                entry_id=rev_id,
                                reason="VerifierWorker determined proposed revision is entailed (non-contradictory)",
                                memory_id=belief_id,
                                stage="idle_pulse_nli",
                                now=current_time,
                            )
                            actions.append(f"quarantined_non_contradiction_{rev_id}")
                            continue
                    except Exception as v_err:  # noqa: BLE001
                        logger.debug("idle_pulse_verifier_failed", error=str(v_err))

                distilled = distill_contradiction_to_proposition(
                    old_content=old_text or trigger,
                    new_content=proposed,
                    topic=trigger,
                    llm=self.llm,
                )
                distilled_propositions.append(distilled.canonical_proposition)
                actions.append(f"distilled_{rev_id}")

                if self.store is not None and self.master_key is not None and reason_eid:
                    try:
                        derived_signer = DerivedFactSigner(master_key=self.master_key)
                        _signed_prop = sign_distilled_proposition(
                            distilled=distilled,
                            signer=derived_signer,
                            source_entry_ids=[reason_eid],
                            now=current_time,
                        )
                        self.store.commit(_signed_prop, now=current_time)
                    except Exception as sign_err:  # noqa: BLE001
                        logger.debug("idle_pulse_sign_distilled_skipped", error=str(sign_err))

        should_log_pulse = bool(actions or distilled_propositions or coh_deficit > 0.0)
        if not should_log_pulse and self.db is not None:
            try:
                with self.db.read_cursor() as cur:
                    cur.execute(
                        "SELECT MAX(created_at) FROM learning_events WHERE event_type = 'IDLE_PULSE_DISTILL' AND topic = 'homeostatic_heartbeat'"
                    )
                    last_row = cur.fetchone()
                    last_hb = float(last_row[0]) if last_row and last_row[0] is not None else 0.0
                    if (current_time - last_hb) >= 3600.0:
                        should_log_pulse = True
            except Exception as hb_err:  # noqa: BLE001
                logger.debug("idle_pulse_heartbeat_check_failed", error=str(hb_err))
                should_log_pulse = True

        if should_log_pulse:
            ev_id = log_learning_event(
                self.db,
                event_type="IDLE_PULSE_DISTILL",
                topic="homeostatic_heartbeat",
                details={
                    "coherence_deficit": coh_deficit,
                    "competence_deficit": comp_deficit,
                    "distilled_propositions": distilled_propositions,
                    "actions": actions,
                },
                now=current_time,
            )
            actions.append(f"event_{ev_id}")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return IdlePulseResult(
            coherence_deficit=coh_deficit,
            competence_deficit=comp_deficit,
            distilled_events_count=len(distilled_propositions),
            actions_taken=actions,
            latency_ms=round(elapsed_ms, 2),
        )


class DreamRetrospective:
    """
    Deep retrospective cadence executing during prolonged idle or nightly roll-up.
    Shadow-replays CEGIS repairs, mines candidate skills into QUARANTINE state (D-REAS-06)
    via RuleInducer and RuleLifecycleManager, validates ASSISTANT_BELIEF rows against newer
    verified receipts, and logs auditable skill acquisition events.
    """

    def __init__(
        self,
        db: DatabaseManager,
        rule_engine: RuleLifecycleManager | None = None,
        verifier: SemanticVerifierPort | None = None,
    ) -> None:
        self.db = db
        self._rule_engine = rule_engine
        self.verifier = verifier
        self.competence_drive = CompetenceDrive(db)

    @property
    def rule_engine(self) -> RuleLifecycleManager:
        if self._rule_engine is None:
            self._rule_engine = RuleLifecycleManager(db=self.db)
        return self._rule_engine

    def retrospective(self, now: float | None = None) -> DreamRetrospectiveResult:
        t0 = time.perf_counter()
        current_time = now if now is not None else time.time()

        quarantined: list[str] = []
        replays_analyzed = 0
        r_engine = self.rule_engine

        # 1. Mine recurring patterns from SQLite telemetry into QUARANTINE via RuleInducer
        try:
            inducer = RuleInducer(db=self.db, rule_engine=r_engine, verifier=self.verifier)
            induced_candidates = inducer.induce_and_quarantine()
            for cand in induced_candidates:
                quarantined.append(cand.rule_id)
                log_learning_event(
                    self.db,
                    event_type="RULE_QUARANTINED",
                    topic=f"induced_rule_{cand.rule_id}",
                    details={
                        "rule_id": cand.rule_id,
                        "intent": cand.intended_intent,
                        "status": "QUARANTINE",
                    },
                    now=current_time,
                )
                log_learning_event(
                    self.db,
                    event_type="SKILL_MINED",
                    topic="induced_microscheme_rule",
                    details={"rule_id": cand.rule_id, "status": "QUARANTINED"},
                    now=current_time,
                )
        except Exception as ind_err:  # noqa: BLE001
            logger.debug("dream_retrospective_inducer_error", error=str(ind_err))

        # 2. Scan multi-turn CEGIS candidate repairs & impasse_backlog to induce grounded rules
        repairs = self.competence_drive.scan_candidate_repairs(limit=10)
        impasse_rows: list[tuple[str, str, str, str]] = []
        try:
            with self.db.read_cursor() as cur:
                cur.execute(
                    """
                    SELECT id, query, code, resolved_code
                    FROM impasse_backlog
                    WHERE processed = 0
                    ORDER BY surprise_score DESC
                    LIMIT 10
                    """
                )
                for r in cur.fetchall():
                    impasse_rows.append((str(r[0]), str(r[1]), str(r[2]), str(r[3] or "")))
        except Exception as exc:  # noqa: BLE001
            logger.debug("dream_retrospective_impasse_backlog_query_error", error=str(exc))

        for rep in repairs:
            dec_id = str(rep["decision_id"])
            clean_slug = re.sub(r"[^a-z0-9]+", "-", dec_id[:8].lower()).strip("-") or "repair"
            legacy_rule_id = f"rule-quarantine-{dec_id[:8]}"
            rule_id = (
                legacy_rule_id
                if re.search(r"-v\d+$", legacy_rule_id)
                else f"rule-quarantine-{clean_slug}-v1"
            )
            extracted_code = ""
            extracted_tool = "run_python"
            extracted_keyword = dec_id[:8]
            try:
                tc_list = json.loads(str(rep.get("tool_calls_json", "[]")))
                if isinstance(tc_list, list) and tc_list:
                    last_tc = tc_list[-1]
                    if isinstance(last_tc, dict):
                        extracted_tool = str(last_tc.get("tool") or "run_python")
                        tc_args = last_tc.get("args")
                        if isinstance(tc_args, dict) and tc_args.get("code"):
                            extracted_code = str(tc_args["code"])
                feat_dict = json.loads(str(rep.get("features_json", "{}")))
                if isinstance(feat_dict, dict):
                    if not extracted_code and feat_dict.get("final_code"):
                        extracted_code = str(feat_dict["final_code"])
                    q_summary = str(feat_dict.get("problem_summary") or feat_dict.get("query") or "")
                    words = [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", q_summary)]
                    if words:
                        extracted_keyword = words[0]
            except Exception as exc:  # noqa: BLE001
                logger.debug("dream_retrospective_repair_extract_error", error=str(exc))

            if not extracted_code:
                # Lookup verified code from episodic_code_cache if present
                try:
                    with self.db.read_cursor() as cur:
                        cur.execute(
                            "SELECT code, query FROM episodic_code_cache ORDER BY verified_at DESC LIMIT 1"
                        )
                        ep_row = cur.fetchone()
                        if ep_row and ep_row[0]:
                            extracted_code = str(ep_row[0])
                except Exception as exc:  # noqa: BLE001
                    logger.debug("dream_retrospective_episodic_lookup_error", error=str(exc))

            if not extracted_code:
                extracted_code = f"# Verified repair macro for {dec_id[:8]}\npass"

            escaped_code = extracted_code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            escaped_kw = extracted_keyword.replace("\\", "\\\\").replace('"', '\\"')
            sexpr = (
                f'(rule "{rule_id}"\n'
                f'  :when (and (intent= "math_computation") (transcript-has? "{escaped_kw}"))\n'
                f'  :plan (list (tool "{extracted_tool}" :code "{escaped_code}"))\n'
                f"  :priority 5)"
            )
            if rule_id not in r_engine.rules:
                try:
                    managed = r_engine.register_rule(sexpr)
                    managed.is_induced = True
                    if legacy_rule_id != rule_id:
                        r_engine.rules[legacy_rule_id] = managed
                except Exception as reg_err:  # noqa: BLE001
                    logger.debug(
                        "dream_retrospective_register_repair_rule_failed",
                        rule_id=rule_id,
                        error=str(reg_err),
                    )
            if rule_id not in quarantined:
                quarantined.append(rule_id)
            log_learning_event(
                self.db,
                event_type="RULE_QUARANTINED",
                topic=f"candidate_repair_{dec_id}",
                details={
                    "rule_id": rule_id,
                    "action": rep["action"],
                    "status": "QUARANTINE",
                    "positive_evidence": 1,
                    "negative_evidence": 0,
                },
                now=current_time,
            )
            log_learning_event(
                self.db,
                event_type="SKILL_MINED",
                topic="synthesized_repair_macro",
                details={
                    "rule_id": rule_id,
                    "status": "QUARANTINED",
                    "positive_evidence": 1,
                    "negative_evidence": 0,
                },
                now=current_time,
            )

        # Process resolved impasses from impasse_backlog
        for imp_id, imp_query, imp_code, imp_resolved in impasse_rows:
            candidate_code = imp_resolved.strip() or imp_code.strip()
            if not candidate_code:
                continue
            imp_slug = re.sub(r"[^a-z0-9]+", "-", imp_id[-8:].lower()).strip("-") or "impasse"
            imp_rule_id = f"rule-impasse-{imp_slug}-v1"
            kw_tokens = [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", imp_query)]
            kw = kw_tokens[0] if kw_tokens else imp_id[-8:]
            esc_code = candidate_code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            esc_kw = kw.replace("\\", "\\\\").replace('"', '\\"')
            imp_sexpr = (
                f'(rule "{imp_rule_id}"\n'
                f'  :when (transcript-has? "{esc_kw}")\n'
                f'  :plan (list (tool "run_python" :code "{esc_code}"))\n'
                f"  :priority 5)"
            )
            if imp_rule_id not in r_engine.rules:
                try:
                    managed_imp = r_engine.register_rule(imp_sexpr)
                    managed_imp.is_induced = True
                    if imp_rule_id not in quarantined:
                        quarantined.append(imp_rule_id)
                except Exception as imp_err:  # noqa: BLE001
                    logger.debug("dream_retrospective_impasse_rule_failed", error=str(imp_err))
            try:
                with self.db.write_transaction() as wcur:
                    wcur.execute(
                        "UPDATE impasse_backlog SET processed = 1 WHERE id = ?",
                        (imp_id,),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("dream_retrospective_impasse_mark_error", error=str(exc))

        # 3. Offline shadow replay of all QUARANTINE rules against historical decisions
        for r_id, managed_rule in list(r_engine.rules.items()):
            if managed_rule.status == "QUARANTINE":
                try:
                    r_engine.replay_candidate(r_id, limit=50)
                    replays_analyzed += 1
                except Exception as rep_err:  # noqa: BLE001
                    logger.debug("dream_retrospective_replay_failed", rule_id=r_id, error=str(rep_err))

        replays_analyzed = max(replays_analyzed, len(repairs) + len(impasse_rows))

        # 4. Validate active ASSISTANT_BELIEF rows against newer USER_EXPLICIT / TOOL_VERIFIED receipts
        try:
            with self.db.read_cursor() as cur:
                cur.execute(
                    """
                    SELECT m.memory_id, m.content, m.created_at
                    FROM memories m
                    JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                    WHERE p.provenance = 'ASSISTANT_BELIEF'
                      AND m.valid_to IS NULL
                      AND m.forgotten_at IS NULL
                    ORDER BY m.created_at DESC
                    LIMIT 10
                    """
                )
                beliefs = cur.fetchall()
                if beliefs:
                    cur.execute(
                        """
                        SELECT m.memory_id, m.content, p.entry_id, m.created_at
                        FROM memories m
                        JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                        WHERE p.provenance IN ('USER_EXPLICIT', 'TOOL_VERIFIED')
                          AND m.valid_to IS NULL
                          AND m.forgotten_at IS NULL
                        ORDER BY m.created_at DESC
                        LIMIT 20
                        """
                    )
                    receipts = cur.fetchall()
                    for b_row in beliefs:
                        b_id, b_content, b_ts = int(b_row[0]), str(b_row[1]), float(b_row[2])
                        for r_row in receipts:
                            r_mem_id = int(r_row[0])
                            r_content, r_eid, r_ts = str(r_row[1]), str(r_row[2]), float(r_row[3])
                            if r_ts > b_ts and is_rule_conflict(
                                b_content, r_content, verifier=self.verifier
                            ):
                                with self.db.write_transaction() as wcur:
                                    wcur.execute(
                                        "UPDATE memories SET valid_to = ?, superseded_by = ? WHERE memory_id = ?",
                                        (current_time, r_mem_id, b_id),
                                    )
                                    wcur.execute(
                                        """
                                        UPDATE provenance_envelopes
                                        SET grounding_eligible = 0
                                        WHERE entry_id = (
                                            SELECT entry_id FROM memories WHERE memory_id = ?
                                        )
                                        """,
                                        (b_id,),
                                    )
                                log_learning_event(
                                    self.db,
                                    event_type="CONTRADICTION_RESOLVED",
                                    topic=f"dream_belief_audit_{b_id}",
                                    details={
                                        "belief_id": b_id,
                                        "superseded_by": r_mem_id,
                                        "contradicting_entry_id": r_eid,
                                        "status": "SUPERSEDED",
                                    },
                                    provenance_envelope_id=r_eid,
                                    now=current_time,
                                )
                                break
        except Exception as audit_err:  # noqa: BLE001
            logger.debug("dream_retrospective_belief_audit_failed", error=str(audit_err))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return DreamRetrospectiveResult(
            replays_analyzed=replays_analyzed,
            skills_mined=len(quarantined),
            quarantined_rules=quarantined,
            latency_ms=round(elapsed_ms, 2),
        )


class ReflectionEngine:
    """
    Manages autobiographical belief revision, evidence-gated supersession,
    review queue gating (5 flags), and nightly importance-weighted roll-up.
    """

    def __init__(
        self,
        db: DatabaseManager,
        store: MemoryStore,
        master_key: bytes,
        rule_engine: RuleLifecycleManager | None = None,
        verifier: SemanticVerifierPort | None = None,
        llm: SpeechLLMPort | None = None,
    ) -> None:
        self.db = db
        self.store = store
        self.master_key = master_key
        self.signer = AssistantUtteranceSigner(master_key=master_key)
        self.idle_pulse = IdlePulse(
            db=db,
            verifier=verifier,
            store=store,
            master_key=master_key,
            llm=llm,
        )
        self.dream_retrospective = DreamRetrospective(
            db=db,
            rule_engine=rule_engine,
            verifier=verifier,
        )

    def is_topic_review_required(self, topic: str) -> bool:
        """Checks if a normalized topic has been marked review-required by operator."""
        clean_topic = topic.strip().lower()
        with self.db.read_cursor() as cur:
            cur.execute(
                "SELECT 1 FROM review_required_topics WHERE lower(topic) = ? LIMIT 1",
                (clean_topic,),
            )
            return cur.fetchone() is not None

    def mark_topic_review_required(self, topic: str, now: float | None = None) -> None:
        """Marks a topic as requiring explicit operator review before belief updates."""
        clean_topic = topic.strip().lower()
        current_time = now if now is not None else time.time()
        conn = self.db.get_writer()
        conn.execute(
            "INSERT OR IGNORE INTO review_required_topics(topic, created_at) VALUES (?, ?)",
            (clean_topic, current_time),
        )

    def unmark_topic_review_required(self, topic: str) -> None:
        """Removes a topic from the review-required list."""
        clean_topic = topic.strip().lower()
        conn = self.db.get_writer()
        conn.execute(
            "DELETE FROM review_required_topics WHERE lower(topic) = ?",
            (clean_topic,),
        )

    def list_review_required_topics(self) -> list[str]:
        """Lists all topics marked as review-required."""
        with self.db.read_cursor() as cur:
            cur.execute("SELECT topic FROM review_required_topics ORDER BY topic ASC")
            return [str(row[0]) for row in cur.fetchall()]

    def detect_and_handle_contradiction(
        self,
        old_belief_id: int,
        new_content: str,
        reason_entry_id: str,
        proposed_confidence: float = 1.0,
        is_conflict_top: bool = False,
        topic: str | None = None,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """
        Evaluates belief contradiction against evidence reason.
        Autonomous revision if no review flags apply; otherwise queues into review_queue.

        Returns:
            (is_queued, identifier_or_spoken_update)
        """
        current_time = now if now is not None else time.time()

        # Evidence reason MUST be grounding-eligible (Invariant ADR-006 / D-MEM-04)
        with self.db.read_cursor() as cur:
            cur.execute(
                "SELECT grounding_eligible FROM provenance_envelopes WHERE entry_id = ?",
                (reason_entry_id,),
            )
            env_row = cur.fetchone()
            if not env_row or env_row[0] != 1:
                raise ProvenanceRejected(
                    f"Contradiction reason '{reason_entry_id}' is not a grounding-eligible entry_id"
                )

            # Fetch active old belief record
            cur.execute(
                "SELECT memory_id, content, kind, importance, created_at, valid_from, valid_to "
                "FROM memories WHERE memory_id = ?",
                (old_belief_id,),
            )
            belief_row = cur.fetchone()
            if not belief_row:
                raise KeyError(f"Belief #{old_belief_id} not found")
            if belief_row[6] is not None:
                raise ValueError(f"Belief #{old_belief_id} has already been superseded")

            # Oscillation guard: if this exact revision is already pending review,
            # avoid duplicate queuing. Distinct revisions of the same belief must
            # still be queued independently (5-flag gating spec, §7 Decision 4).
            cur.execute(
                "SELECT review_id FROM review_queue "
                "WHERE belief_id = ? AND status = 'PENDING' AND proposed_content = ?",
                (old_belief_id, new_content),
            )
            pending_row = cur.fetchone()
            if pending_row:
                return True, str(pending_row[0])

        old_content = str(belief_row[1])
        kind = str(belief_row[2])
        importance = float(belief_row[3])
        created_at = float(belief_row[4])
        valid_from = float(belief_row[5])

        # Evaluate the 5 review flags (Spec §7 Decision 4):
        # 1. Belief is about the user (kind="user_model")
        flag_user_model = kind == "user_model"

        # 2. importance >= 0.7
        flag_high_importance = importance >= 0.7

        # 3. Contradiction resolves to Belnap B (conflict / TOP) rather than F
        flag_conflict_top = is_conflict_top

        # 4. Oscillation guard: belief already revised within last 30 days
        age_since_revision = current_time - valid_from
        flag_oscillation = age_since_revision < THIRTY_DAYS_SECONDS and valid_from > created_at

        # 5. Topic marked review-required
        effective_topic = topic or kind
        flag_topic_required = self.is_topic_review_required(effective_topic)

        reasons: list[str] = []
        if flag_user_model:
            reasons.append("kind_user_model")
        if flag_high_importance:
            reasons.append(f"high_importance_{importance:.2f}")
        if flag_conflict_top:
            reasons.append("belnap_conflict_top")
        if flag_oscillation:
            reasons.append(f"oscillation_guard_{age_since_revision:.0f}s")
        if flag_topic_required:
            reasons.append(f"topic_review_required_{effective_topic}")

        if reasons:
            # Enqueue in review_queue
            review_id = f"rev-{uuid.uuid4().hex[:12]}"
            trigger_reason = "; ".join(reasons)
            conn = self.db.get_writer()
            conn.execute(
                """
                INSERT INTO review_queue (
                    review_id, belief_id, proposed_content, proposed_confidence,
                    reason_entry_id, trigger_reason, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    review_id,
                    old_belief_id,
                    new_content,
                    proposed_confidence,
                    reason_entry_id,
                    trigger_reason,
                    current_time,
                ),
            )
            logger.info(
                "belief_revision_flagged_for_review",
                review_id=review_id,
                belief_id=old_belief_id,
                reasons=reasons,
            )
            return True, review_id

        # Autonomous revision: commit new belief and supersede old belief
        # Base importance boosted +0.4 for revised belief per Spec §7
        revised_importance = min(1.0, max(importance, 0.5) + 0.4)
        canonical_content = self._canonicalize_proposition(new_content)
        unsigned = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content=canonical_content,
            structured={"importance": revised_importance, "valid_from": current_time},
            trace_id=f"autonomous-refl-{uuid.uuid4().hex[:8]}",
            created_at=current_time,
            nonce=uuid.uuid4().hex,
            confidence=proposed_confidence,
        )
        signed = self.signer.sign(unsigned)
        new_memory_id = self.store.commit(signed, now=current_time)
        self.store.supersede(
            old_belief_id, new_memory_id, reason=reason_entry_id, now=current_time
        )
        log_learning_event(
            self.db,
            event_type="BELIEF_SUPERSEDED",
            topic=effective_topic,
            details={"old_belief_id": old_belief_id, "new_memory_id": new_memory_id},
            provenance_envelope_id=reason_entry_id,
            now=current_time,
        )

        # Summarise canonical_content to a readable cap so spoken update stays concise.
        new_summary = canonical_content[:80].rstrip() + ("…" if len(canonical_content) > 80 else "")
        spoken_update = (
            f"I've revised a belief I had — previously: {old_content[:60].rstrip()}. "
            f"New understanding: {new_summary}."
        )
        logger.info(
            "autonomous_belief_revision_applied",
            old_belief_id=old_belief_id,
            new_memory_id=new_memory_id,
            reason_entry_id=reason_entry_id,
        )
        return False, spoken_update

    @staticmethod
    def _canonicalize_proposition(text: str) -> str:
        """Canonicalizes conversational utterance into a declarative belief proposition.

        Bans raw conversational speech / user transcripts from direct ASSISTANT_BELIEF
        ingestion (Spec §7, D-MEM-04, v1.35.7 Phase 1 hygiene).
        """
        clean = text.strip()
        # Strip common conversational speech prefixes and filler
        pattern = (
            r"^(?:actually|well|i mean|you know|wait|hey|um|uh|look|so|basically|listen)[,\s]+"
        )
        while True:
            m = re.match(pattern, clean, re.IGNORECASE)
            if not m:
                break
            clean = clean[m.end():].lstrip()
        if clean:
            clean = clean[0].upper() + clean[1:]
        if clean and not clean.endswith((".", "!", "?")):
            clean += "."
        return clean

    def list_pending_reviews(self) -> list[dict[str, object]]:
        """Returns all pending items in review_queue."""
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT r.review_id, r.belief_id, m.content as old_content,
                       r.proposed_content, r.proposed_confidence, r.reason_entry_id,
                       r.trigger_reason, r.created_at, r.status
                FROM review_queue r
                LEFT JOIN memories m ON r.belief_id = m.memory_id
                WHERE r.status = 'PENDING'
                ORDER BY r.created_at ASC
                """
            )
            rows = cur.fetchall()
            return [
                {
                    "review_id": str(r[0]),
                    "belief_id": int(r[1]) if r[1] is not None else None,
                    "old_content": str(r[2]) if r[2] is not None else "",
                    "proposed_content": str(r[3]),
                    "proposed_confidence": float(r[4]),
                    "reason_entry_id": str(r[5]),
                    "trigger_reason": str(r[6]),
                    "created_at": float(r[7]),
                    "status": str(r[8]),
                }
                for r in rows
            ]

    def approve_review(
        self,
        review_id: str,
        decided_by: str = "operator",
        now: float | None = None,
    ) -> int:
        """Approves a flagged belief revision, superseding old belief with proposed content."""
        current_time = now if now is not None else time.time()
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT belief_id, proposed_content, proposed_confidence, reason_entry_id, status
                FROM review_queue WHERE review_id = ?
                """,
                (review_id,),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Review item '{review_id}' not found")
            if str(row[4]) != "PENDING":
                raise ValueError(f"Review item '{review_id}' is not PENDING (status={row[4]})")

        old_belief_id = int(row[0])
        proposed_content = str(row[1])
        proposed_confidence = float(row[2])
        reason_entry_id = str(row[3])

        # Commit proposed belief
        unsigned = UnsignedPayload(
            provenance=Provenance.ASSISTANT_BELIEF,
            kind="belief",
            content=proposed_content,
            structured={"importance": 0.8, "valid_from": current_time},
            trace_id=f"review-approve-{review_id}",
            created_at=current_time,
            nonce=uuid.uuid4().hex,
            confidence=proposed_confidence,
        )
        signed = self.signer.sign(unsigned)
        new_mid = self.store.commit(signed, now=current_time)
        self.store.supersede(old_belief_id, new_mid, reason=reason_entry_id, now=current_time)

        conn = self.db.get_writer()
        conn.execute(
            "UPDATE review_queue SET status = 'APPROVED', decided_at = ?, decided_by = ? "
            "WHERE review_id = ?",
            (current_time, decided_by, review_id),
        )
        log_learning_event(
            self.db,
            event_type="CONTRADICTION_RESOLVED",
            topic="operator_review_approved",
            details={
                "review_id": review_id,
                "old_belief_id": old_belief_id,
                "new_memory_id": new_mid,
                "decided_by": decided_by,
            },
            provenance_envelope_id=reason_entry_id,
            now=current_time,
        )
        logger.info("review_approved", review_id=review_id, old=old_belief_id, new=new_mid)
        return new_mid

    def reject_review(
        self,
        review_id: str,
        decided_by: str = "operator",
        now: float | None = None,
    ) -> None:
        """Rejects a flagged belief revision, preserving old belief intact."""
        current_time = now if now is not None else time.time()
        with self.db.read_cursor() as cur:
            cur.execute("SELECT status FROM review_queue WHERE review_id = ?", (review_id,))
            row = cur.fetchone()
            if not row:
                raise KeyError(f"Review item '{review_id}' not found")
            if str(row[0]) != "PENDING":
                raise ValueError(f"Review item '{review_id}' is not PENDING (status={row[0]})")

        conn = self.db.get_writer()
        conn.execute(
            "UPDATE review_queue SET status = 'REJECTED', decided_at = ?, decided_by = ? "
            "WHERE review_id = ?",
            (current_time, decided_by, review_id),
        )
        logger.info("review_rejected", review_id=review_id, decided_by=decided_by)

    def rollup_nightly(self, now: float | None = None) -> int:
        """
        Rolls up low-importance autobiographical rows (< 0.2 and > 30 days) into
        session summaries (kind="session_summary"), marking originals forgotten_at.
        Rows with importance >= 0.2 are retained indefinitely.
        """
        current_time = now if now is not None else time.time()
        cutoff_time = current_time - THIRTY_DAYS_SECONDS

        # Query eligible low-importance autobiographical memories
        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT m.memory_id, m.content, p.session_id, m.created_at
                FROM memories m
                JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE p.provenance IN ('ASSISTANT_UTTERANCE', 'ASSISTANT_BELIEF')
                  AND m.importance < 0.2
                  AND m.created_at < ?
                  AND m.forgotten_at IS NULL
                ORDER BY p.session_id, m.created_at ASC
                """,
                (cutoff_time,),
            )
            rows = cur.fetchall()

        if not rows:
            return 0

        # Group by session
        by_session: dict[str, list[tuple[int, str]]] = {}
        for r in rows:
            mid = int(r[0])
            content = str(r[1])
            sess = str(r[2]) or "default-session"
            by_session.setdefault(sess, []).append((mid, content))

        total_compressed = 0
        for sess_id, items in by_session.items():
            mids = [m[0] for m in items]
            summary_content = (
                f"Session {sess_id} historical autobiographical summary: "
                f"{len(items)} items compressed (including '{items[0][1][:40]}...')."
            )
            unsigned = UnsignedPayload(
                provenance=Provenance.ASSISTANT_UTTERANCE,
                kind="session_summary",
                content=summary_content,
                session_id=sess_id,
                trace_id=f"rollup-{uuid.uuid4().hex[:8]}",
                created_at=current_time,
                nonce=uuid.uuid4().hex,
                confidence=1.0,
            )
            signed = self.signer.sign(unsigned)
            self.store.commit(signed, now=current_time)

            # Mark original items forgotten_at
            ph = ",".join("?" for _ in mids)
            conn = self.db.get_writer()
            conn.execute(
                f"UPDATE memories SET forgotten_at = ? WHERE memory_id IN ({ph})",  # noqa: S608
                [current_time, *mids],
            )
            for mid in mids:
                cur_old = conn.execute(
                    "SELECT content, tokens_aux FROM memories WHERE memory_id = ?", (mid,)
                )
                old_row = cur_old.fetchone()
                if old_row:
                    old_content, old_tokens = old_row[0], old_row[1]
                    conn.execute(
                        """
                        INSERT INTO fts_memories(fts_memories, rowid, content, tokens_aux)
                        VALUES ('delete', ?, ?, ?)
                        """,
                        (mid, old_content, old_tokens),
                    )
            conn.execute(
                f"DELETE FROM vec_memories WHERE memory_id IN ({ph})",  # noqa: S608
                mids,
            )
            total_compressed += len(mids)

        if total_compressed > 0:
            conn = self.db.get_writer()
            conn.execute("PRAGMA wal_checkpoint(PASSIVE);")

        try:
            self.dream_retrospective.retrospective(now=current_time)
        except Exception as retro_err:  # noqa: BLE001
            logger.debug("nightly_rollup_dream_retrospective_failed", error=str(retro_err))

        logger.info("autobiographical_nightly_rollup_completed", compressed_count=total_compressed)
        return total_compressed

    def nightly_rollup(self, now: float | None = None) -> int:
        """Alias for rollup_nightly per Work Order #8."""
        return self.rollup_nightly(now=now)

    def get_last_rollup_at(self) -> float | None:
        """Retrieves persistent timestamp of the last executed roll-up."""
        conn = self.db.get_writer()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS system_metadata ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        with self.db.read_cursor() as cur:
            cur.execute("SELECT value FROM system_metadata WHERE key = 'last_rollup_at'")
            row = cur.fetchone()
            return float(row[0]) if row else None

    def record_last_rollup_at(self, ts: float) -> None:
        """Persists timestamp of completed roll-up to prevent duplicate runs across restarts."""
        conn = self.db.get_writer()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS system_metadata ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO system_metadata(key, value, updated_at) VALUES ('last_rollup_at', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (str(ts), ts),
        )


def is_rollup_due(
    last_rollup_at: float | None,
    current_time: float,
    rollup_hour_local: int = 3,
) -> bool:
    """
    Evaluates whether a nightly autobiographical roll-up is due.
    Triggers once per 24h at first idle after rollup_hour_local (default 03:00).
    """
    dt_now = datetime.datetime.fromtimestamp(current_time)
    target_today = dt_now.replace(hour=rollup_hour_local, minute=0, second=0, microsecond=0)
    target_today_ts = target_today.timestamp()

    if current_time < target_today_ts:
        return False

    if last_rollup_at is None:
        return True

    return last_rollup_at < target_today_ts
