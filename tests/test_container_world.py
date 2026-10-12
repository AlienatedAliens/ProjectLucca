"""
Project Lucca — Unit Tests for ContainerWorld Spatial & Theory-of-Mind Tracker
"""

import pytest

from lucca.sandbox.container_world import ContainerWorld, extract_events_from_json_text


def test_single_placement() -> None:
    cw = ContainerWorld()
    cw.process_event({
        "agent": "Alice",
        "action": "place",
        "item": "notebook",
        "location": "desk",
    })
    assert cw.query(None, "notebook") == "desk"
    assert cw.query("Alice", "notebook") == "desk"
    assert cw.query("Bob", "notebook") == "desk"  # falls back to world


def test_unobserved_movement_theory_of_mind() -> None:
    """
    Sally puts marble in basket.
    Sally leaves.
    Anne moves marble to box (Sally does not observe).
    Where will Sally look for the marble? Basket!
    Where is the marble physically? Box!
    """
    cw = ContainerWorld()
    # Step 1: Sally places marble in basket (Sally observes)
    cw.process_event({
        "agent": "Sally",
        "action": "place",
        "item": "marble",
        "location": "basket",
        "observed_by": ["Anne"],
    })
    assert cw.query("Sally", "marble") == "basket"
    assert cw.query("Anne", "marble") == "basket"
    assert cw.query(None, "marble") == "basket"

    # Step 2: Anne moves marble to box (Sally does not observe)
    cw.process_event({
        "agent": "Anne",
        "action": "move",
        "item": "marble",
        "location": "box",
        "observed_by": [],  # Sally is not observing
    })

    # Sally still believes it is in the basket
    assert cw.query("Sally", "marble") == "basket"
    # Anne knows it is in the box
    assert cw.query("Anne", "marble") == "box"
    # Physical world state is box
    assert cw.query(None, "marble") == "box"


def test_observed_movement_updates_belief() -> None:
    cw = ContainerWorld()
    cw.process_event({
        "agent": "Sally",
        "action": "place",
        "item": "marble",
        "location": "basket",
    })
    # Anne moves marble, Sally watches
    cw.process_event({
        "agent": "Anne",
        "action": "move",
        "item": "marble",
        "location": "box",
        "observed_by": ["Sally"],
    })
    assert cw.query("Sally", "marble") == "box"
    assert cw.query("Anne", "marble") == "box"


def test_substring_item_matching() -> None:
    cw = ContainerWorld()
    cw.process_event({
        "agent": "Danny",
        "action": "place",
        "item": "wireless studio earphones",
        "location": "recording booth",
    })
    assert cw.query("Danny", "earphones") == "recording booth"
    assert cw.query(None, "earphones") == "recording booth"


def test_serialization() -> None:
    cw = ContainerWorld()
    cw.process_event({
        "agent": "Ricky",
        "action": "place",
        "item": "guitar",
        "location": "stage",
    })
    state = cw.export_state()

    cw2 = ContainerWorld()
    cw2.load_state(state)
    assert cw2.query("Ricky", "guitar") == "stage"
    assert cw2.query(None, "guitar") == "stage"


def test_extract_events_from_json_text() -> None:
    sample_json = """```json
    {
        "events": [
            {"agent": "Alice", "action": "move", "item": "book", "location": "shelf"}
        ]
    }
    ```"""
    events, ok = extract_events_from_json_text(sample_json)
    assert ok is True
    assert len(events) == 1
    assert events[0]["item"] == "book"
    assert events[0]["location"] == "shelf"
