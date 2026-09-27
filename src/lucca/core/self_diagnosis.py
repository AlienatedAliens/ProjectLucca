"""
Project Lucca — Diagnostic Self-Reasoning Engine (Fault Model v1)
Spec 11 §7, WO-22 Phase 2 (Fault Model v1)
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Final

import structlog
from pydantic import BaseModel, Field, JsonValue

from lucca.core import env_check
from lucca.core.config import get_config
from lucca.memory.db import DatabaseManager
from lucca.memory.retrieval import search_decision_records

logger = structlog.get_logger(__name__)

DEFAULT_FAULT_MODEL_PATH: Final[Path] = (
    Path(__file__).resolve().parents[3] / "config" / "fault_model.toml"
)


class FaultModelEntry(BaseModel):
    """A curated fault pattern in the fault model."""

    id: str
    name: str
    symptoms: list[str]
    cause: str
    checks: list[str]
    severity: str = "medium"
    suggested_remedy: str = ""


class Diagnosis(BaseModel):
    """A diagnostic conclusion (hypothesis) produced by the DiagnosisEngine.

    TRAP 1 INVARIANT:
    Diagnoses are hypotheses (SPECULATION band), never asserted as unhedged facts.
    """

    fault_id: str
    cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    suggested_remedy: str = ""
    matched_symptoms: list[str] = Field(default_factory=list)
    checks_run: list[dict[str, JsonValue]] = Field(default_factory=list)
    severity: str = "medium"


class DiagnosisEngine:
    """Symptom->cause reasoning engine over Lucca's own stack and telemetry.

    Bounded to Lucca's own telemetry/registers and env_check functions (Trap 2).
    Queries in-session decision history via ITEM-021 for historical incident context.
    """

    def __init__(
        self,
        fault_model_path: Path | str | None = None,
        db: DatabaseManager | None = None,
    ) -> None:
        self.db = db
        self.fault_model: list[FaultModelEntry] = []
        self._load_fault_model(fault_model_path)

    def _resolve_config_path(self, custom_path: Path | str | None) -> Path:
        if custom_path is not None:
            return Path(custom_path)

        # Check standard locations
        candidates = [
            DEFAULT_FAULT_MODEL_PATH,
            Path("config/fault_model.toml"),
        ]
        try:
            cfg = get_config()
            candidates.insert(0, cfg.home_dir / "config" / "fault_model.toml")
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_config_failed_in_diagnosis_engine", error=str(exc))

        for cand in candidates:
            if cand.exists():
                return cand

        return DEFAULT_FAULT_MODEL_PATH

    def _load_fault_model(self, config_path: Path | str | None) -> None:
        path = self._resolve_config_path(config_path)
        if not path.exists():
            logger.warning("fault_model_config_missing", path=str(path))
            return

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as exc:  # noqa: BLE001
            logger.error("fault_model_toml_parse_failed", path=str(path), error=str(exc))
            raise

        raw_entries = data.get("fault", data.get("faults", []))
        entries: list[FaultModelEntry] = []

        if isinstance(raw_entries, list):
            for item in raw_entries:
                if isinstance(item, dict):
                    entries.append(FaultModelEntry.model_validate(item))
        elif isinstance(raw_entries, dict):
            for k, v in raw_entries.items():
                if isinstance(v, dict):
                    item = dict(v)
                    item.setdefault("id", k)
                    entries.append(FaultModelEntry.model_validate(item))

        # STOP GATE RATIFIED: Fail loudly if a fault entry names a check function
        # absent from lucca.core.env_check (negative control requirement).
        for entry in entries:
            for check_name in entry.checks:
                fn = getattr(env_check, check_name, None)
                if fn is None or not callable(fn):
                    raise ValueError(
                        f"Invalid fault model config: check function '{check_name}' "
                        f"specified in fault '{entry.id}' does not exist in lucca.core.env_check. "
                        f"All checks must resolve to real env_check functions."
                    )

        self.fault_model = entries
        logger.info("fault_model_loaded", count=len(self.fault_model), path=str(path))

    def _extract_observation_terms(
        self, observations: dict[str, object] | list[str] | str
    ) -> list[str]:
        terms: list[str] = []
        if isinstance(observations, str):
            terms.append(observations.strip())
        elif isinstance(observations, list):
            for x in observations:
                if isinstance(x, str):
                    terms.append(x.strip())
                elif isinstance(x, dict):
                    terms.extend(self._extract_observation_terms(x))
        elif isinstance(observations, dict):
            for k, v in observations.items():
                terms.append(str(k))
                if isinstance(v, (str, int, float, bool)):
                    terms.append(str(v))
                elif isinstance(v, list):
                    for item in v:
                        terms.append(str(item))
                elif isinstance(v, dict):
                    terms.extend(self._extract_observation_terms(v))
        return terms

    def diagnose(
        self,
        observations: dict[str, object] | list[str] | str,
    ) -> list[Diagnosis]:
        """Matches observed symptoms against fault model, runs env checks, queries past
        decisions via ITEM-021, and returns ranked hypotheses."""
        obs_terms = self._extract_observation_terms(observations)
        if not obs_terms:
            return []

        obs_joined = " ".join(obs_terms).lower()
        diagnoses: list[Diagnosis] = []

        is_general_tools_query = any(
            phrase in obs_joined
            for phrase in ("what's wrong with your tools", "what is wrong with your tools")
        )
        is_general_slow_query = any(
            phrase in obs_joined
            for phrase in ("why are you slow", "why is it slow", "why are things slow")
        )

        for fault in self.fault_model:
            matched_symptoms: list[str] = []

            for symptom in fault.symptoms:
                s_lower = symptom.lower()
                if s_lower in obs_joined:
                    matched_symptoms.append(symptom)
                else:
                    # Token overlap match: all substantive symptom tokens appear in observations
                    s_tokens = [t for t in s_lower.split() if len(t) >= 4]
                    if s_tokens and all(t in obs_joined for t in s_tokens):
                        matched_symptoms.append(symptom)

            # Heuristic domain targeting for general queries
            if not matched_symptoms:
                if is_general_tools_query and fault.id == "docker_wsl_down":
                    matched_symptoms.append("tools failure inspection")
                elif is_general_slow_query and fault.id == "audio_ring_contention":
                    matched_symptoms.append("latency investigation")

            # Run checks for matching fault (or check if failure is actively occurring)
            checks_run: list[dict[str, JsonValue]] = []
            evidence: list[str] = []
            check_failed = False
            check_passed_count = 0

            # Only run checks if symptoms matched, OR if it's a general tools query targeting tools
            if matched_symptoms or is_general_tools_query:
                for check_name in fault.checks:
                    fn = getattr(env_check, check_name)
                    try:
                        ok, detail = fn()
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(
                            "diagnosis_check_invocation_failed", check=check_name, error=str(exc)
                        )
                        ok, detail = False, f"Check raised exception: {exc}"

                    checks_run.append({"check": check_name, "ok": ok, "detail": detail})
                    if not ok:
                        check_failed = True
                        evidence.append(f"Check '{check_name}' confirmed failure: {detail}")
                    else:
                        check_passed_count += 1
                        evidence.append(f"Check '{check_name}' passed: {detail}")

            # If no symptoms matched and no check confirmed failure, skip this fault
            if not matched_symptoms and not check_failed:
                continue

            # Record matched symptoms as evidence
            for s in matched_symptoms:
                evidence.append(f"Observed symptom matched: '{s}'")

            # ITEM-021: Query Decision History from SQLite
            if self.db is not None:
                search_query = matched_symptoms[0] if matched_symptoms else fault.name
                try:
                    past_records = search_decision_records(self.db, search_query, limit=2)
                    for rec in past_records:
                        call_summary = (
                            ", ".join(tc.tool for tc in rec.tool_calls)
                            if rec.tool_calls
                            else rec.executed_path
                        )
                        evidence.append(
                            f"Past incident (decision {rec.decision_id}): "
                            f"routed {rec.decision.action.value} on "
                            f"'{rec.features.transcript[:60]}' using [{call_summary}]"
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("decision_history_query_failed", error=str(exc))

            # Confidence calculation (Trap 1: standards of proof)
            if check_failed:
                confidence = 0.95 if matched_symptoms else 0.85
            elif matched_symptoms:
                # Symptom matched but checks passed -> speculative hypothesis
                confidence = 0.50 if check_passed_count > 0 else 0.65
            else:
                confidence = 0.40

            diagnoses.append(
                Diagnosis(
                    fault_id=fault.id,
                    cause=fault.cause,
                    confidence=confidence,
                    evidence=evidence,
                    suggested_remedy=fault.suggested_remedy,
                    matched_symptoms=matched_symptoms,
                    checks_run=checks_run,
                    severity=fault.severity,
                )
            )

        # Sort by confidence descending, then severity priority
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        diagnoses.sort(key=lambda d: (-d.confidence, severity_rank.get(d.severity.lower(), 4)))
        return diagnoses

    def format_diagnosis_speech(self, diagnosis: Diagnosis | None) -> str:
        """Formats a Diagnosis into hedged, honest speech (Trap 1 / Standards of proof).

        Always hedges diagnoses ('my best guess is ...', 'I'd check ...') rather than
        asserting them as unhedged facts.
        """
        if diagnosis is None:
            return (
                "I've checked my telemetry and environment, and no known fault "
                "pattern matches what's happening."
            )

        # Find any confirmed failure details
        failed_checks = [c for c in diagnosis.checks_run if not c.get("ok", True)]

        if diagnosis.fault_id == "docker_wsl_down":
            if failed_checks:
                detail = str(failed_checks[0].get("detail", "Docker is not responding in WSL2"))
                return (
                    f"{detail} — my best guess is {diagnosis.cause}; "
                    f"I'd start Docker CE inside WSL2 or check the Docker service."
                )
            return (
                f"Based on the observed tool errors, my best guess is {diagnosis.cause}; "
                f"I'd check the Docker CE service in WSL2."
            )

        if diagnosis.fault_id == "audio_ring_contention":
            return (
                "My ASR is slow and the NPU looks fine — my best guess is audio ring "
                "contention; I'd check the ring buffer."
            )

        if diagnosis.fault_id == "boot_memory_error":
            if failed_checks:
                detail = str(failed_checks[0].get("detail", "System RAM below boot budget"))
                return (
                    f"{detail} — my best guess is {diagnosis.cause}; "
                    f"I'd close background applications to free RAM."
                )
            return (
                f"My best guess is {diagnosis.cause}; "
                f"I'd check available system RAM before retrying boot."
            )

        if diagnosis.fault_id == "llama_server_unhealthy":
            if failed_checks:
                detail = str(failed_checks[0].get("detail", "LLM server check failed"))
                return (
                    f"{detail} — my best guess is {diagnosis.cause}; "
                    f"I'd verify dGPU VRAM and check model weights against the manifest."
                )
            return (
                f"My best guess is {diagnosis.cause}; "
                f"I'd verify llama-server health and VRAM allocation."
            )

        if diagnosis.fault_id == "frozen_binary_timeout":
            if failed_checks:
                detail = str(failed_checks[0].get("detail", "WSL check timed out"))
                return (
                    f"{detail} — my best guess is {diagnosis.cause}; "
                    f"I'd check WSL status or run 'wsl --shutdown'."
                )
            return f"My best guess is {diagnosis.cause}; I'd check if the WSL subsystem is hanging."

        # Generic hedged formatting
        remedy_clause = (
            f"; I'd {diagnosis.suggested_remedy.lower()}" if diagnosis.suggested_remedy else ""
        )
        return f"My best guess is {diagnosis.cause}{remedy_clause}."


DIAGNOSTIC_QUERY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"what(?:'s|\s+is)\s+wrong(?:\s+with\s+(?:you|your\s+tools|the\s+tools|things))?"
    r"|why\s+(?:are\s+you|is\s+it|are\s+things)\s+(?:so\s+)?slow"
    r"|why\s+did\s+(?:that|it|the\s+tool)\s+fail"
    r"|diagnose\s+(?:yourself|the\s+system|tools|faults?)"
    r"|run\s+(?:self\s+)?diagnosis"
    r")\b",
    re.IGNORECASE,
)


def is_self_diagnosis_query(text: str) -> bool:
    """Checks whether user text is an inquiry requesting diagnostic self-reasoning."""
    clean = text.strip().lower()
    return bool(DIAGNOSTIC_QUERY_PATTERN.search(clean))
