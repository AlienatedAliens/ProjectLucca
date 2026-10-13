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
        self.second_order_beliefs: dict[str, dict[str, dict[str, str]]] = {}  # observer -> target -> item -> location

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

        # 4. Second-order belief update (Hintikka epistemic model)
        present = set()
        if agent and agent not in ("none", "null", "all", "everyone"):
            present.add(agent)
        for obs in observers:
            if obs and obs not in ("none", "null", "all", "everyone"):
                present.add(obs)

        for x in present:
            if x not in self.second_order_beliefs:
                self.second_order_beliefs[x] = {}
            for y in present:
                if y not in self.second_order_beliefs[x]:
                    self.second_order_beliefs[x][y] = {}
                self.second_order_beliefs[x][y][item] = loc

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
        self.second_order_beliefs.clear()

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

    def query_second_order(
        self,
        observer_agent: str,
        target_agent: str,
        item: str,
    ) -> str | None:
        """
        Query second-order belief: What does observer_agent believe that target_agent believes
        is the location of item? (B_observer(B_target(item)))
        """
        obs = observer_agent.strip().lower()
        tgt = target_agent.strip().lower()
        t_item = item.strip().lower()

        # Reflexive second-order belief reduces to first-order belief: B_A(B_A(p)) = B_A(p)
        if obs == tgt:
            return self.query(obs, t_item)

        # 1. Explicit nested belief model
        if obs in self.second_order_beliefs and tgt in self.second_order_beliefs[obs]:
            if t_item in self.second_order_beliefs[obs][tgt]:
                return self.second_order_beliefs[obs][tgt][t_item]
            for k, v in self.second_order_beliefs[obs][tgt].items():
                if t_item in k or k in t_item:
                    return v

        # 2. Target retains initial shared state in observer's mental model
        if t_item in self.initial_world:
            return self.initial_world[t_item]
        for k, v in self.initial_world.items():
            if t_item in k or k in t_item:
                return v

        # 3. Fallback to physical world state
        return self.query(None, t_item)

    def export_state(self) -> dict[str, object]:
        """Export current state for serialization."""
        return {
            "world": dict(self.world),
            "initial_world": dict(self.initial_world),
            "beliefs": {k: dict(v) for k, v in self.beliefs.items()},
            "second_order_beliefs": {
                k: {k2: dict(v2) for k2, v2 in v.items()}
                for k, v in self.second_order_beliefs.items()
            },
        }

    def load_state(self, state: dict[str, object]) -> None:
        """Restore state from serialized dictionary."""
        w = state.get("world")
        iw = state.get("initial_world")
        b = state.get("beliefs")
        sob = state.get("second_order_beliefs")
        self.world = dict(w) if isinstance(w, dict) else {}
        self.initial_world = dict(iw) if isinstance(iw, dict) else {}
        self.beliefs = {k: dict(v) for k, v in b.items() if isinstance(v, dict)} if isinstance(b, dict) else {}
        self.second_order_beliefs = (
            {k: {k2: dict(v2) for k2, v2 in v.items() if isinstance(v2, dict)} for k, v in sob.items() if isinstance(v, dict)}
            if isinstance(sob, dict)
            else {}
        )

    def query_recursive(self, agent_chain: list[str], item: str) -> str | None:
        """
        Recursive N-th order Theory of Mind query:
        B_{a_0}(B_{a_1}(...B_{a_{N-1}}(item)...))
        """
        if not agent_chain:
            return self.query(None, item)
        if len(agent_chain) == 1:
            return self.query(agent_chain[0], item)
        if len(agent_chain) == 2:
            return self.query_second_order(agent_chain[0], agent_chain[1], item)

        obs = agent_chain[0].strip().lower()
        sub = agent_chain[1:]
        first_hop = self.query_second_order(obs, sub[0], item)
        if len(sub) == 1:
            return first_hop
        return self.query_recursive(sub, item)

    # Method aliases for common LLM hallucinations & edge models
    put = place
    relocate = move
    ask = query
    query_2nd = query_second_order
    belief_of_belief = query_second_order
    query_nested = query_second_order
    query_nth = query_recursive
    belief_chain = query_recursive
    set_object_location = place
    place_object = place
    add_object = place
    set_location = place
    set_object = place
    set_object_state = place
    add_agent = lambda self, *args, **kwargs: None
    record_observation = lambda self, *args, **kwargs: None


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


# Common aliases for LLMs importing World, KnowledgeBase, Agent, etc.
World = ContainerWorld
KnowledgeBase = ContainerWorld
BeliefTracker = ContainerWorld


class Agent:
    """Helper alias for agent identification in synthesized code."""

    def __init__(self, name: str = "", *args, **kwargs) -> None:
        self.name = str(name)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Agent({self.name!r})"


__all__ = ["ContainerWorld", "World", "KnowledgeBase", "BeliefTracker", "Agent", "extract_events_from_json_text"]

