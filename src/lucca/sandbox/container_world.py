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
        self.room_occupants: dict[str, list[str]] = {}  # room -> list of occupants
        self.agent_locations: dict[str, str] = {}  # agent -> current room
        self.event_log: list[dict[str, object]] = []  # ordered epistemic event log for arbitrary depth k>=3 ToM

    @property
    def rooms(self) -> dict[str, list[str]]:
        """Dictionary of rooms to occupant lists."""
        return self.room_occupants

    @staticmethod
    def _coerce_observer_list(val: object) -> list[str]:
        """Coerces a single string, comma-separated string, or iterable into a clean lowercase observer list."""
        if val is None:
            return []
        if isinstance(val, str):
            cleaned = val.strip()
            if not cleaned or cleaned.lower() in ("none", "null", "nobody", "no one", "alone"):
                return []
            if "," in cleaned:
                parts = [p.strip().removeprefix("and ").strip() for p in cleaned.split(",")]
                return [p.lower() for p in parts if p and p.lower() not in ("none", "null", "nobody", "no one", "alone")]
            return [cleaned.lower()]
        if isinstance(val, (list, tuple, set)):
            out: list[str] = []
            for elem in val:
                out.extend(ContainerWorld._coerce_observer_list(elem))
            return out
        s_val = str(val).strip().lower()
        return [s_val] if s_val and s_val not in ("none", "null", "nobody", "no one", "alone") else []

    def process_event(self, ev: dict[str, object]) -> None:
        """
        Process a single physical, initial, or perceptual event.
        Expected keys:
        - agent (str | list[str] | None): Character(s) performing the action
        - action (str): 'initial', 'place', 'move', 'put', 'glimpse', 'see', 'observe'
        - item (str): Name of the entity/object
        - location (str) / dst (str): Target container or location
        - observed_by (list[str] | str): Other agents who witnessed this event
        """
        raw_agent = ev.get("agent") if "agent" in ev else ev.get("actor")
        action = str(ev.get("action") or "move").strip().lower()
        item = str(ev.get("item") or ev.get("obj") or ev.get("object") or ev.get("entity") or "").strip().lower()
        loc = str(
            ev.get("location")
            or ev.get("loc")
            or ev.get("dst")
            or ev.get("to_loc")
            or ev.get("container")
            or ev.get("room")
            or ""
        ).strip().lower()

        raw_observers: object = (
            ev.get("observed_by")
            if ev.get("observed_by") is not None
            else (
                ev.get("observers")
                if ev.get("observers") is not None
                else (
                    ev.get("witnesses")
                    if ev.get("witnesses") is not None
                    else (
                        ev.get("witnessed_by")
                        if ev.get("witnessed_by") is not None
                        else (
                            ev.get("present")
                            if ev.get("present") is not None
                            else ev.get("known_by")
                        )
                    )
                )
            )
        )
        observers = self._coerce_observer_list(raw_observers)

        if isinstance(raw_agent, (list, tuple, set)) or (isinstance(raw_agent, str) and "," in raw_agent):
            observers.extend(self._coerce_observer_list(raw_agent))
            agent = ""
        else:
            agent = str(raw_agent or "").strip().lower()

        if not item or not loc:
            return

        is_first_for_item = item not in self.initial_world
        is_explicit_init = action in ("initial", "start", "starting", "located")

        # Record initial shared state the first time an item's location is established
        if is_first_for_item or is_explicit_init:
            self.initial_world.setdefault(item, loc)

        # 1. Physical world update
        if action in (
            "initial", "start", "starting", "located",
            "move", "place", "put", "relocate", "transfer", "set", "leave", "drop",
        ):
            self.world[item] = loc

        # 2. Acting agent belief update
        if agent and agent not in ("none", "null", "all", "everyone", "nobody", "no one", "alone"):
            if agent not in self.beliefs:
                self.beliefs[agent] = {}
            self.beliefs[agent][item] = loc

        # 3. Explicit observer belief update
        for obs in observers:
            if obs and obs not in ("none", "null", "all", "everyone", "nobody", "no one", "alone"):
                if obs not in self.beliefs:
                    self.beliefs[obs] = {}
                self.beliefs[obs][item] = loc

        # 3b. Implicit room co-presence witness update (Milestone 36.5)
        implicit_witnesses: list[str] = []
        if hasattr(self, "agent_locations") and hasattr(self, "room_occupants"):
            if agent and agent in self.agent_locations:
                ag_room = self.agent_locations[agent]
                implicit_witnesses.extend(self.room_occupants.get(ag_room, []))
            if loc in self.room_occupants:
                implicit_witnesses.extend(self.room_occupants[loc])
        for wit in implicit_witnesses:
            if wit and wit not in ("none", "null", "all", "everyone", "nobody", "no one", "alone"):
                if wit not in self.beliefs:
                    self.beliefs[wit] = {}
                self.beliefs[wit][item] = loc

        # 4. Second-order belief update (Hintikka epistemic model)
        present = set()
        if agent and agent not in ("none", "null", "all", "everyone", "nobody", "no one", "alone"):
            present.add(agent)
        for obs in observers:
            if obs and obs not in ("none", "null", "all", "everyone", "nobody", "no one", "alone"):
                present.add(obs)
        for wit in implicit_witnesses:
            if wit and wit not in ("none", "null", "all", "everyone", "nobody", "no one", "alone"):
                present.add(wit)

        for x in present:
            if x not in self.second_order_beliefs:
                self.second_order_beliefs[x] = {}
            for y in present:
                if y not in self.second_order_beliefs[x]:
                    self.second_order_beliefs[x][y] = {}
                self.second_order_beliefs[x][y][item] = loc

        if not hasattr(self, "event_log"):
            self.event_log = []
        self.event_log.append(
            {
                "type": "event",
                "agent": agent,
                "action": action,
                "item": item,
                "location": loc,
                "witnesses": sorted(present),
                "is_shared_init": bool(is_explicit_init or is_first_for_item),
            }
        )

    def _dispatch_action(self, action: str, *args: object, **kwargs: object) -> None:
        """
        Normalizes flexible positional and keyword signatures for place/move/init/observe:
        - (item, location)
        - (item, location, observed_by=[...])
        - (item, location, [obs1, obs2, ...])
        - ([obs1, obs2, ...], item, location)
        - (agent, item, location)
        - (agent, item, location, observed_by=[...])
        - (agent, item, location, [obs1, ...]) or (agent, item, location, "obs1")
        - (agent, item, from_loc, to_loc, ...)
        """
        if len(args) == 1 and isinstance(args[0], dict):
            ev = dict(args[0])
            ev.setdefault("action", action)
            self.process_event(ev)
            return

        kw_obs = (
            kwargs.get("observed_by")
            if kwargs.get("observed_by") is not None
            else (
                kwargs.get("observers")
                if kwargs.get("observers") is not None
                else (
                    kwargs.get("witnesses")
                    if kwargs.get("witnesses") is not None
                    else (
                        kwargs.get("witnessed_by")
                        if kwargs.get("witnessed_by") is not None
                        else (
                            kwargs.get("present")
                            if kwargs.get("present") is not None
                            else kwargs.get("known_by")
                        )
                    )
                )
            )
        )
        observers = self._coerce_observer_list(kw_obs)
        kw_agent = kwargs.get("agent") if "agent" in kwargs else kwargs.get("actor")
        kw_item = kwargs.get("item") or kwargs.get("obj") or kwargs.get("object") or kwargs.get("entity")
        kw_loc = (
            kwargs.get("location")
            or kwargs.get("loc")
            or kwargs.get("dst")
            or kwargs.get("to_loc")
            or kwargs.get("container")
            or kwargs.get("room")
        )

        agent_val: object = kw_agent
        item_val: object = kw_item
        loc_val: object = kw_loc

        if len(args) == 1:
            if kw_item is None:
                item_val = args[0]
            elif kw_loc is None:
                loc_val = args[0]
        elif len(args) == 2:
            a1, a2 = args
            if kw_loc is not None and kw_item is None:
                agent_val, item_val, loc_val = a1, a2, kw_loc
            elif kw_item is not None and kw_loc is None:
                agent_val, item_val, loc_val = a1, kw_item, a2
            else:
                agent_val, item_val, loc_val = kw_agent, a1, a2
        elif len(args) == 3:
            a1, a2, a3 = args
            s1 = str(a1).strip().lower() if isinstance(a1, str) else ""
            s2 = str(a2).strip().lower() if isinstance(a2, str) else ""
            if isinstance(a3, (list, tuple, set)):
                # (item, location, [observers...])
                agent_val = kw_agent
                item_val = a1
                loc_val = a2
                observers.extend(self._coerce_observer_list(a3))
            elif isinstance(a1, (list, tuple, set)):
                # ([observers...], item, location)
                agent_val = kw_agent
                item_val = a2
                loc_val = a3
                observers.extend(self._coerce_observer_list(a1))
            elif s1 and s1 in self.world:
                # a1 is an already-known item!
                if s2 == self.world.get(s1):
                    # (item, from_loc, to_loc)
                    agent_val = kw_agent
                    item_val = a1
                    loc_val = a3
                else:
                    # (item, to_loc, single_observer)
                    agent_val = kw_agent
                    item_val = a1
                    loc_val = a2
                    observers.extend(self._coerce_observer_list(a3))
            else:
                agent_val = a1 if a1 is not None else kw_agent
                item_val = a2
                loc_val = a3
        elif len(args) >= 4:
            a1, a2, a3, a4 = args[:4]
            s2 = str(a2).strip().lower() if isinstance(a2, str) else ""
            s3 = str(a3).strip().lower() if isinstance(a3, str) else ""
            if isinstance(a4, str) and s2 in self.world and s3 == self.world.get(s2):
                # (agent, item, from_loc, to_loc, [optional_observers])
                agent_val = a1 if a1 is not None else kw_agent
                item_val = a2
                loc_val = a4
                if len(args) >= 5:
                    observers.extend(self._coerce_observer_list(args[4]))
            else:
                # (agent, item, location, observed_by)
                agent_val = a1 if a1 is not None else kw_agent
                item_val = a2
                loc_val = a3
                observers.extend(self._coerce_observer_list(a4))

        self.process_event(
            {
                "agent": agent_val,
                "action": action,
                "item": item_val,
                "location": loc_val,
                "observed_by": observers,
            }
        )

    def place(self, *args: object, **kwargs: object) -> None:
        """Convenience method to record a placement event (supports (agent, item, loc), (item, loc), or (item, loc, observers))."""
        self._dispatch_action("place", *args, **kwargs)

    def move(self, *args: object, **kwargs: object) -> None:
        """Convenience method to record a movement event (supports (agent, item, loc), (item, loc), or (agent, item, loc, observers))."""
        self._dispatch_action("move", *args, **kwargs)

    def set_room_occupants(self, room: str, occupants: list[str]) -> None:
        """Sets the current occupant list for a given room/location (Milestone 36.5)."""
        clean_room = room.strip().lower()
        clean_occupants = [str(o).strip().lower() for o in occupants if str(o).strip()]
        if not hasattr(self, "room_occupants"):
            self.room_occupants = {}
        self.room_occupants[clean_room] = clean_occupants
        if not hasattr(self, "agent_locations"):
            self.agent_locations = {}
        for occ in clean_occupants:
            self.agent_locations[occ] = clean_room

    def tell(self, speaker: str, listener: str, item: str, location: str | None = None) -> None:
        """
        Agent communication action: speaker tells listener that item is at location (Milestone 36.5).
        If location is omitted, uses speaker's current belief (or ground-truth world state) for item.
        Updates listener's belief about item, and speaker's second-order belief about listener.
        """
        spk = speaker.strip().lower()
        lis = listener.strip().lower()
        it = item.strip().lower()
        resolved_loc = location.strip().lower() if location is not None else (self.query(spk, it) or "")
        if not resolved_loc:
            return
        loc = resolved_loc

        if lis not in self.beliefs:
            self.beliefs[lis] = {}
        self.beliefs[lis][it] = loc

        if spk not in self.second_order_beliefs:
            self.second_order_beliefs[spk] = {}
        if lis not in self.second_order_beliefs[spk]:
            self.second_order_beliefs[spk][lis] = {}
        self.second_order_beliefs[spk][lis][it] = loc

        if not hasattr(self, "event_log"):
            self.event_log = []
        self.event_log.append(
            {
                "type": "tell",
                "speaker": spk,
                "listener": lis,
                "item": it,
                "location": loc,
                "witnesses": sorted({spk, lis}),
            }
        )

    def reset(self) -> None:
        """Reset all world, initial_world, and belief dictionaries."""
        self.world.clear()
        self.initial_world.clear()
        self.beliefs.clear()
        self.second_order_beliefs.clear()
        if hasattr(self, "room_occupants"):
            self.room_occupants.clear()
        if hasattr(self, "agent_locations"):
            self.agent_locations.clear()
        if hasattr(self, "event_log"):
            self.event_log.clear()

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

    def query(self, *args: object, **kwargs: object) -> str | None:
        """
        Query location of item. Supports:
        - w.query(agent, item) -> 1st-order belief (or None for physical location)
        - w.query(observer, target, item) -> 2nd-order belief (delegates to query_second_order)
        - w.query([a1, a2, ...], item) -> k-order belief chain (delegates to query_recursive)
        - w.query(item) -> ground-truth physical location
        """
        kw_obs = kwargs.get("observer") or kwargs.get("observer_agent") or kwargs.get("agent1")
        kw_tgt = kwargs.get("target") or kwargs.get("target_agent") or kwargs.get("agent") or kwargs.get("agent2")
        kw_item = kwargs.get("item") or kwargs.get("obj") or kwargs.get("object") or kwargs.get("entity")

        if len(args) >= 3:
            return self.query_second_order(args[0], args[1], args[2])
        if kw_obs is not None and kw_tgt is not None:
            it = str(args[0] if len(args) == 1 else (kw_item or ""))
            return self.query_second_order(kw_obs, kw_tgt, it)

        if len(args) == 2:
            a1, a2 = args
            if isinstance(a1, (list, tuple)):
                return self.query_recursive([str(x) for x in a1], str(a2))
            target_agent: str | None = str(a1) if a1 is not None else None
            item = str(a2)
        elif len(args) == 1:
            a1 = args[0]
            if isinstance(a1, (list, tuple)) and kw_item is not None:
                return self.query_recursive([str(x) for x in a1], str(kw_item))
            if kw_item is not None:
                target_agent = str(a1) if a1 is not None else None
                item = str(kw_item)
            elif kw_tgt is not None:
                target_agent = str(kw_tgt)
                item = str(a1)
            else:
                target_agent = None
                item = str(a1)
        else:
            if isinstance(kw_tgt, (list, tuple)):
                return self.query_recursive([str(x) for x in kw_tgt], str(kw_item or ""))
            target_agent = str(kw_tgt) if kw_tgt is not None else None
            item = str(kw_item or "")

        target_item = item.strip().lower()
        if target_agent:
            agent = target_agent.strip().lower()
            # If caller swapped (item, agent), detect when `agent` is a known item and `target_item` is not
            if agent in self.world and target_item not in self.world:
                agent, target_item = target_item, agent

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
        *args: object,
        **kwargs: object,
    ) -> str | None:
        """
        Query second-order belief: What does observer_agent believe that target_agent believes
        is the location of item? (B_observer(B_target(item)))
        """
        kw_obs = (
            kwargs.get("observer_agent")
            or kwargs.get("observer")
            or kwargs.get("agent1")
            or kwargs.get("a1")
            or kwargs.get("outer_agent")
        )
        kw_tgt = (
            kwargs.get("target_agent")
            or kwargs.get("target")
            or kwargs.get("agent2")
            or kwargs.get("a2")
            or kwargs.get("inner_agent")
            or kwargs.get("agent")
        )
        kw_item = kwargs.get("item") or kwargs.get("obj") or kwargs.get("object") or kwargs.get("entity")

        if len(args) == 2 and isinstance(args[0], (list, tuple)):
            return self.query_recursive([str(x) for x in args[0]], str(args[1]))
        if len(args) >= 3:
            a1, a2, a3 = str(args[0] or ""), str(args[1] or ""), str(args[2] or "")
            # Detect if item was passed first: (item, observer, target)
            if a1.strip().lower() in self.world and a3.strip().lower() not in self.world:
                observer_agent, target_agent, item = a2, a3, a1
            else:
                observer_agent, target_agent, item = a1, a2, a3
        elif len(args) == 2:
            a1, a2 = str(args[0] or ""), str(args[1] or "")
            if kw_item is not None:
                observer_agent, target_agent, item = a1, a2, str(kw_item)
            elif kw_obs is not None:
                observer_agent, target_agent, item = str(kw_obs), a1, a2
            else:
                observer_agent, target_agent, item = a1, a1, a2
        elif len(args) == 1:
            arg_single = args[0]
            if isinstance(arg_single, (list, tuple)):
                return self.query_recursive([str(x) for x in arg_single], str(kw_item or ""))
            observer_agent = str(kw_obs or "")
            target_agent = str(kw_tgt or "")
            item = str(arg_single if kw_item is None else kw_item)
        else:
            observer_agent = str(kw_obs or "")
            target_agent = str(kw_tgt or "")
            item = str(kw_item or "")

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

    def _project_world_for_observer(self, observer: str) -> ContainerWorld:
        """
        Constructs a projected ContainerWorld representing `observer`'s epistemic perspective
        by filtering the event log to initial shared state and events witnessed by `observer`.
        """
        obs = observer.strip().lower()
        projected = ContainerWorld()
        projected.initial_world = dict(self.initial_world)
        projected.world = dict(self.initial_world)

        for entry in getattr(self, "event_log", []):
            etype = entry.get("type")
            raw_wit = entry.get("witnesses", [])
            witnesses = [str(w) for w in raw_wit] if isinstance(raw_wit, list) else []
            if etype == "tell":
                if obs in witnesses:
                    projected.tell(
                        speaker=str(entry.get("speaker", "")),
                        listener=str(entry.get("listener", "")),
                        item=str(entry.get("item", "")),
                        location=str(entry.get("location", "")),
                    )
            else:
                is_shared = bool(entry.get("is_shared_init", False))
                if is_shared or obs in witnesses:
                    projected.process_event(
                        {
                            "agent": str(entry.get("agent", "")),
                            "action": str(entry.get("action", "move")),
                            "item": str(entry.get("item", "")),
                            "location": str(entry.get("location", "")),
                            "observed_by": witnesses,
                        }
                    )
        return projected

    def query_recursive(self, agent_chain: list[str], item: str) -> str | None:
        """
        Recursive N-th order Theory of Mind query:
        B_{a_0}(B_{a_1}(...B_{a_{N-1}}(item)...))
        Properly projects the epistemic event history through each hop in `agent_chain`
        from `a_0` down to `a_{N-1}` for arbitrary depth k >= 3.
        """
        # Collapse adjacent identical agents via positive introspection: B_a(B_a(p)) = B_a(p)
        collapsed: list[str] = []
        for ag in agent_chain:
            clean_ag = str(ag).strip().lower()
            if clean_ag and (not collapsed or collapsed[-1] != clean_ag):
                collapsed.append(clean_ag)

        if not collapsed:
            return self.query(None, item)
        if len(collapsed) == 1:
            return self.query(collapsed[0], item)
        if len(collapsed) == 2:
            return self.query_second_order(collapsed[0], collapsed[1], item)

        obs = collapsed[0]
        sub = collapsed[1:]

        # When event_log is populated, project the world state through obs's epistemic window
        if getattr(self, "event_log", None):
            projected = self._project_world_for_observer(obs)
            return projected.query_recursive(sub, item)

        # Fallback when state dicts were populated directly without event_log
        t_item = item.strip().lower()
        cur_obs = obs
        for nxt in sub:
            if cur_obs not in self.second_order_beliefs or nxt not in self.second_order_beliefs[cur_obs]:
                if t_item in self.initial_world:
                    return self.initial_world[t_item]
                return self.query(None, t_item)
            cur_obs = nxt
        return self.query_second_order(collapsed[-2], collapsed[-1], t_item)

    # Method aliases for common LLM hallucinations & edge models
    put = place
    init = place
    initialize = place
    set_initial = place
    set_initial_location = place
    observe = place
    relocate = move
    transfer = move
    ask = query
    get_belief = query
    query_2nd = query_second_order
    get_second_order_belief = query_second_order
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

    def add_agent(self, *args: object, **kwargs: object) -> None:
        """No-op method alias for LLM agent registration."""

    def record_observation(self, *args: object, **kwargs: object) -> None:
        """No-op method alias for LLM observation logging."""


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

    def __init__(self, name: str = "", *args: object, **kwargs: object) -> None:
        self.name = str(name)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Agent({self.name!r})"


__all__ = ["ContainerWorld", "World", "KnowledgeBase", "BeliefTracker", "Agent", "extract_events_from_json_text"]

