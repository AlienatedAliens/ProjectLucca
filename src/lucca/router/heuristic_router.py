"""
Project Lucca — Phase 4 Heuristic Executive Router & Telemetry Logger
Directs incoming queries across LLM, LISP, and Tool branches, logging every decision.
"""

import time
import uuid
from typing import List, Dict, Any, Optional
from lucca.core.schemas import RouteAction, DecisionRecord

class HeuristicRouter:
    def __init__(self, log_path: Optional[str] = None):
        self._log_path = log_path
        self._logged_records: List[DecisionRecord] = []

    def route_query(self, raw_query: str, active_state: Dict[str, Any] = None) -> DecisionRecord:
        t_start = time.perf_counter()
        normalized = raw_query.lower().strip()
        state = active_state or {}

        # Heuristic 1: Explicit File or App tools
        if any(keyword in normalized for keyword in ["open app", "launch", "run", "start "]):
            chosen_action = RouteAction.CALL_COMPILED_TOOL
        # Heuristic 2: Parameterized / repeated routines mapped to LISP
        elif any(keyword in normalized for keyword in ["clean workspace", "cleanup", "organize downloads", "system status"]):
            chosen_action = RouteAction.CHECK_LISP_FIRST
        # Heuristic 3: Default conversational / complex reasoning
        else:
            chosen_action = RouteAction.DIRECT_TO_LLM

        duration_ms = (time.perf_counter() - t_start) * 1000.0

        record = DecisionRecord(
            record_id=str(uuid.uuid4()),
            timestamp_utc=time.time(),
            raw_query=raw_query,
            tabular_features={
                "char_length": float(len(raw_query)),
                "word_count": float(len(raw_query.split())),
                "task_depth": float(state.get("step_count", 0)),
            },
            heuristic_recommendation=chosen_action,
            final_dispatched_action=chosen_action,
            execution_duration_ms=duration_ms,
        )

        self._logged_records.append(record)
        return record

    def get_logged_records_count(self) -> int:
        return len(self._logged_records)

    def get_all_records(self) -> List[DecisionRecord]:
        return list(self._logged_records)
