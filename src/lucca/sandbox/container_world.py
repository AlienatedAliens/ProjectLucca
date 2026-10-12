"""
Project Lucca — ContainerWorld Spatial & Theory-of-Mind State Tracker
Spec 09 / Neurosymbolic Tool Engine
Provides deterministic tracking of physical locations and per-agent belief states
to eliminate autoregressive attention collapse on spatial object tracking.
"""

from __future__ import annotations

import json
import re
from typing import Any


class ContainerWorld:
    """
    Deterministic Theory-of-Mind & Spatial State Tracker.
    Maintains ground-truth physical locations and per-agent belief states across narrative events.
    """

    def __init__(self) -> None:
        self.world: dict[str, str] = {}  # item -> current physical location
        self.beliefs: dict[str, dict[str, str]] = {}  # agent -> item -> believed location

    def process_event(self, ev: dict[str, Any]) -> None:
        """
        Process a single physical or perceptual event.
        Expected keys:
        - agent (str | None): Character performing the action
        - action (str): 'place', 'move', 'glimpse', 'see', 'observe'
        - item (str): Name of the entity/object
        - location (str) / dst (str): Target container or location
        - observed_by (list[str]): Other agents who witnessed this event
        """
        agent = str(ev.get("agent") or "").strip().lower()
        action = str(ev.get("action") or "").strip().lower()
        item = str(ev.get("item") or "").strip().lower()
        loc = str(ev.get("location") or ev.get("dst") or "").strip().lower()
        raw_observers = ev.get("observed_by") or []
        observers = [str(o).strip().lower() for o in raw_observers if o]

        if not item or not loc:
            return

        # 1. Physical world update
        if action in ("move", "place", "put", "relocate", "transfer", "set", "leave", "drop"):
            self.world[item] = loc

        # 2. Acting agent belief update
        if agent:
            if agent not in self.beliefs:
                self.beliefs[agent] = {}
            self.beliefs[agent][item] = loc

        # 3. Explicit observer belief update
        for obs in observers:
            if obs not in self.beliefs:
                self.beliefs[obs] = {}
            self.beliefs[obs][item] = loc

    def process_events(self, events: list[dict[str, Any]]) -> None:
        """Batch process an ordered sequence of events."""
        for ev in events:
            self.process_event(ev)

    def query(self, target_agent: str | None, item: str) -> str | None:
        """
        Query location of item. If target_agent is specified, queries the agent's belief state;
        otherwise queries true physical world state.
        """
        target_item = item.strip().lower()

        # Check target agent's belief first
        if target_agent:
            agent = target_agent.strip().lower()
            if agent in self.beliefs:
                if target_item in self.beliefs[agent]:
                    return self.beliefs[agent][target_item]
                # Substring matching for compound item names (e.g. 'earphones' in 'wireless earphones')
                for k, v in self.beliefs[agent].items():
                    if target_item in k or k in target_item:
                        return v

        # Fallback to physical world state
        if target_item in self.world:
            return self.world[target_item]
        for k, v in self.world.items():
            if target_item in k or k in target_item:
                return v

        return None

    def export_state(self) -> dict[str, Any]:
        """Export current state for serialization."""
        return {
            "world": dict(self.world),
            "beliefs": {k: dict(v) for k, v in self.beliefs.items()},
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore state from serialized dictionary."""
        self.world = dict(state.get("world", {}))
        self.beliefs = {k: dict(v) for k, v in state.get("beliefs", {}).items()}


def extract_events_from_json_text(text: str) -> tuple[list[dict[str, Any]], bool]:
    """Extracts events list from LLM output, handling markdown fences and JSON arrays."""
    if not text:
        return [], False

    # 1. Direct markdown fenced JSON
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if "events" in data and isinstance(data["events"], list):
                return data["events"], True
        except Exception:
            pass

    # 2. Markdown fenced list
    m_list = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m_list:
        try:
            arr = json.loads(m_list.group(1))
            if isinstance(arr, list):
                return arr, True
        except Exception:
            pass

    # 3. Raw JSON object
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and "events" in data and isinstance(data["events"], list):
            return data["events"], True
        if isinstance(data, list):
            return data, True
    except Exception:
        pass

    # 4. Regex fallback searching for array in text
    m_arr = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if m_arr:
        try:
            arr = json.loads(m_arr.group(0))
            if isinstance(arr, list):
                return arr, True
        except Exception:
            pass

    return [], False
