"""
Project Lucca — ContainerWorld Spatial & Theory-of-Mind State Tracker
Spec 09 / Neurosymbolic Tool Engine
Provides deterministic tracking of physical locations, initial shared knowledge,
and per-agent belief states to eliminate autoregressive attention collapse on spatial object tracking.
"""

from __future__ import annotations

import json
import re


class ContainerWorld:
    """
    Deterministic Theory-of-Mind & Spatial State Tracker.
    Maintains ground-truth physical locations, initial shared locations, and per-agent belief states.
    """

    def __init__(self) -> None:
        self.world: dict[str, str] = {}  # item -> current physical location
        self.initial_world: dict[str, str] = {}  # item -> initial location at start of narrative
        self.beliefs: dict[str, dict[str, str]] = {}  # agent -> item -> believed location

    def process_event(self, ev: dict[str, object]) -> None:
        """
        Process a single physical, initial, or perceptual event.
        Expected keys:
        - agent (str | None): Character performing the action
        - action (str): 'initial', 'place', 'move', 'put', 'glimpse', 'see', 'observe'
        - item (str): Name of the entity/object
        - location (str) / dst (str): Target container or location
        - observed_by (list[str]): Other agents who witnessed this event
        """
        agent = str(ev.get("agent") or ev.get("actor") or "").strip().lower()
        action = str(ev.get("action") or "move").strip().lower()
        item = str(ev.get("item") or "").strip().lower()
        loc = str(ev.get("location") or ev.get("dst") or ev.get("to_loc") or "").strip().lower()
        raw_observers = ev.get("observed_by") or []
        observers = (
            [str(o).strip().lower() for o in raw_observers if o]
            if isinstance(raw_observers, list)
            else []
        )

        if not item or not loc:
            return

        # Record initial shared state the first time an item's location is established
        if item not in self.initial_world or action in ("initial", "start", "starting", "located"):
            self.initial_world.setdefault(item, loc)

        # 1. Physical world update
        if action in (
            "initial", "start", "starting", "located",
            "move", "place", "put", "relocate", "transfer", "set", "leave", "drop",
        ):
            self.world[item] = loc

        # 2. Acting agent belief update
        if agent and agent not in ("none", "null", "all", "everyone"):
            if agent not in self.beliefs:
                self.beliefs[agent] = {}
            self.beliefs[agent][item] = loc

        # 3. Explicit observer belief update
        for obs in observers:
            if obs and obs not in ("none", "null"):
                if obs not in self.beliefs:
                    self.beliefs[obs] = {}
                self.beliefs[obs][item] = loc

    def place(
        self,
        arg1: str | None,
        arg2: str,
        arg3: str | None = None,
        observed_by: list[str] | None = None,
        actor: str | None = None,
    ) -> None:
        """Convenience method to record a placement event (supports (agent, item, loc) or (item, loc))."""
        if arg3 is None:
            agent_val, item_val, loc_val = (actor or ""), (arg1 or ""), arg2
        else:
            agent_val, item_val, loc_val = (arg1 or actor or ""), arg2, arg3
        self.process_event(
            {
                "agent": agent_val,
                "action": "place",
                "item": item_val,
                "location": loc_val,
                "observed_by": observed_by or [],
            }
        )

    def move(
        self,
        arg1: str | None,
        arg2: str,
        arg3: str | None = None,
        observed_by: list[str] | None = None,
        actor: str | None = None,
    ) -> None:
        """Convenience method to record a movement event (supports (agent, item, loc) or (item, loc))."""
        if arg3 is None:
            agent_val, item_val, loc_val = (actor or ""), (arg1 or ""), arg2
        else:
            agent_val, item_val, loc_val = (arg1 or actor or ""), arg2, arg3
        self.process_event(
            {
                "agent": agent_val,
                "action": "move",
                "item": item_val,
                "location": loc_val,
                "observed_by": observed_by or [],
            }
        )

    def reset(self) -> None:
        """Reset all world, initial_world, and belief dictionaries."""
        self.world.clear()
        self.initial_world.clear()
        self.beliefs.clear()

    def simulate(
        self,
        events: list[dict[str, object]],
        query_agent: str | None = None,
        query_item: str = "",
    ) -> dict[str, object]:
        """Process events and return physical + believed location for query_agent and query_item."""
        self.process_events(events)
        phys = self.query(None, query_item) or "unknown"
        bel = self.query(query_agent, query_item) or phys
        return {
            "physical_location": phys,
            "believed_location": bel,
            "world": dict(self.world),
            "initial_world": dict(self.initial_world),
        }

    def process_events(self, events: list[dict[str, object]]) -> None:
        """Batch process an ordered sequence of events."""
        for ev in events:
            self.process_event(ev)

    def query(self, target_agent: str | None, item: str) -> str | None:
        """
        Query location of item. If target_agent is specified:
        1. Returns target_agent's explicit belief if recorded.
        2. If target_agent never observed any subsequent move, returns initial_world[item]
           (initial shared knowledge from the start of the narrative).
        3. Otherwise falls back to physical world state.
        """
        target_item = item.strip().lower()

        if target_agent:
            agent = target_agent.strip().lower()
            if agent in self.beliefs:
                if target_item in self.beliefs[agent]:
                    return self.beliefs[agent][target_item]
                for k, v in self.beliefs[agent].items():
                    if target_item in k or k in target_item:
                        return v

            # Agent did not observe any subsequent moves -> retain initial shared knowledge
            if target_item in self.initial_world:
                return self.initial_world[target_item]
            for k, v in self.initial_world.items():
                if target_item in k or k in target_item:
                    return v

        # Fallback to physical world state
        if target_item in self.world:
            return self.world[target_item]
        for k, v in self.world.items():
            if target_item in k or k in target_item:
                return v

        return None

    def export_state(self) -> dict[str, object]:
        """Export current state for serialization."""
        return {
            "world": dict(self.world),
            "initial_world": dict(self.initial_world),
            "beliefs": {k: dict(v) for k, v in self.beliefs.items()},
        }

    def load_state(self, state: dict[str, object]) -> None:
        """Restore state from serialized dictionary."""
        w = state.get("world")
        iw = state.get("initial_world")
        b = state.get("beliefs")
        self.world = dict(w) if isinstance(w, dict) else {}
        self.initial_world = dict(iw) if isinstance(iw, dict) else {}
        self.beliefs = {k: dict(v) for k, v in b.items() if isinstance(v, dict)} if isinstance(b, dict) else {}

    # Method aliases for common LLM hallucinations
    put = place
    relocate = move
    ask = query


def extract_events_from_json_text(text: str) -> tuple[list[dict[str, object]], bool]:
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
        except (json.JSONDecodeError, ValueError):
            pass

    # 2. Markdown fenced list
    m_list = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m_list:
        try:
            arr = json.loads(m_list.group(1))
            if isinstance(arr, list):
                return arr, True
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Raw JSON object
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and "events" in data and isinstance(data["events"], list):
            return data["events"], True
        if isinstance(data, list):
            return data, True
    except (json.JSONDecodeError, ValueError):
        pass

    # 4. Regex fallback searching for array in text
    m_arr = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if m_arr:
        try:
            arr = json.loads(m_arr.group(0))
            if isinstance(arr, list):
                return arr, True
        except (json.JSONDecodeError, ValueError):
            pass

    return [], False


# Common aliases for LLMs importing World, KnowledgeBase, etc.
World = ContainerWorld
KnowledgeBase = ContainerWorld
BeliefTracker = ContainerWorld

__all__ = ["ContainerWorld", "World", "KnowledgeBase", "BeliefTracker", "extract_events_from_json_text"]
