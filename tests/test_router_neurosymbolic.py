"""
Project Lucca — Dynamic Tiered Neurosymbolic Routing Tests
Verifies multi-hop spatial tracking, SMT solver dispatch, and model-tiered thinking modes.
"""

import pytest
from lucca.core.schemas import RouteAction, ExecutionTier
from lucca.router.heuristic import HeuristicRouter


def test_routing_spatial_relocation_container_world() -> None:
    router = HeuristicRouter()
    queries = [
        "Where would Danny look to find the earphones given the story?",
        "Who moved the keys from the kitchen to the desk?",
        "Find the notebook given the following placements and movements.",
        "What is the location of the toolbox?",
    ]
    for q in queries:
        dec = router.route(transcript=q)
        assert dec.action == RouteAction.LLM
        assert dec.solver_tool == "container_world"
        assert dec.reasoning_domain == "spatial_relocation"
        assert dec.thinking_mode == "direct"


def test_routing_combinatorial_z3_smt() -> None:
    router = HeuristicRouter()
    queries = [
        "Solve the zebra puzzle with five houses of different colors.",
        "Einstein's puzzle: who owns the fish?",
        "Find an assignment that can satisfy the following constraints using z3 smt solver.",
        "On an island of knights and knaves, A says B is a knave.",
    ]
    for q in queries:
        dec = router.route(transcript=q)
        assert dec.action == RouteAction.LLM
        assert dec.solver_tool == "z3_smt"
        assert dec.reasoning_domain == "combinatorial_smt"
        assert dec.thinking_mode == "direct"


def test_routing_soft_logic_model_tiered_policy() -> None:
    router = HeuristicRouter()
    query = "Based on the story, which statement logically follows about the murder mystery?"

    # 12B unified tier: route to direct zero-shot to avoid overthinking degradation
    dec_12b = router.route(transcript=query, model_tier="12B")
    assert dec_12b.reasoning_domain == "soft_logic"
    assert dec_12b.thinking_mode == "direct"

    # E4B edge tier: route to extended thinking to capture +30-40pp lift
    dec_e4b = router.route(transcript=query, model_tier="E4B")
    assert dec_e4b.reasoning_domain == "soft_logic"
    assert dec_e4b.thinking_mode == "thinking"

    # E2B resident edge tier: route to extended thinking
    dec_e2b = router.route(transcript=query, model_tier="E2B")
    assert dec_e2b.reasoning_domain == "soft_logic"
    assert dec_e2b.thinking_mode == "thinking"


def test_routing_mathematics_sympy_sandbox() -> None:
    router = HeuristicRouter()
    queries = [
        "Find the sum of the squares of all the items in the list given sum is 30.",
        "Solve the system of equations for x, y, and z.",
        "How many ways to place a digit in each cell of a 2x3 grid so row sum is 999?",
        "Find the number of residents of Aimeville who own all four items.",
        "Calculate the determinant and eigenvalues of the matrix using sympy.",
        "Compute the prime factors and gcd of 1024 and 768.",
        "Evaluate the expression \\log_2(x / (y*z)) given the system.",
    ]
    for q in queries:
        dec = router.route(transcript=q)
        assert dec.action == RouteAction.LLM
        assert dec.solver_tool == "sympy_sandbox"
        assert dec.reasoning_domain == "mathematics"
        assert dec.thinking_mode == "direct"


def test_routing_general_conversational_intents_unaffected() -> None:
    router = HeuristicRouter()
    # Reflex
    dec_stop = router.route(transcript="Lucca stop right now")
    assert dec_stop.action == RouteAction.RULE
    assert dec_stop.tier == ExecutionTier.REFLEX
    assert dec_stop.solver_tool is None

    # Chit chat
    dec_chat = router.route(transcript="Hello Lucca, how are you today?")
    assert dec_chat.action == RouteAction.LLM
    assert dec_chat.solver_tool is None
    assert dec_chat.reasoning_domain is None
    assert dec_chat.thinking_mode == "adaptive"


def test_routing_shared_python_workspace_and_deliberation_lane() -> None:
    """Verifies multi-library exposure (D-REAS-10) and deliberation lane floor-hold cue (D-DUAL-01)."""
    from lucca.sandbox.rpc import _inject_shared_workspace_prelude

    router = HeuristicRouter()
    hybrid_query = (
        "Where is the location of the toolbox after Alice moved it to the study, "
        "and solve the equation for the total number of items?"
    )
    dec = router.route(transcript=hybrid_query)
    assert "container_world" in dec.exposed_libraries
    assert "sympy" in dec.exposed_libraries
    assert dec.deliberation_lane is True
    assert dec.floor_hold_cue is not None

    # Verify shared workspace prelude allows importing ContainerWorld in isolated exec
    user_script = (
        "from container_world import ContainerWorld\n"
        "cw = ContainerWorld()\n"
        "cw.process_event({'agent': 'Alice', 'action': 'move', 'item': 'toolbox', 'location': 'study'})\n"
        "loc = cw.query('Alice', 'toolbox')\n"
    )
    injected = _inject_shared_workspace_prelude(user_script)
    ns: dict[str, object] = {}
    exec(injected, ns)  # noqa: S102
    assert ns["loc"] == "study"
    from lucca.sandbox.container_world import ContainerWorld
    cw_direct = ContainerWorld()
    cw_direct.place("Alice", "box", "kitchen", observed_by=["Alice", "Bob"])
    cw_direct.move("Bob", "box", "attic", observed_by=["Bob"])
    assert cw_direct.query("Alice", "box") == "kitchen"


def test_routing_spatial_grid_arc() -> None:
    router = HeuristicRouter()
    queries = [
        "Transform this concept arc visual reasoning task by flood filling the shapes.",
        "Rotate the 2D grid matrix 90 degrees counter-clockwise.",
        "Apply gravity drop to the falling objects in the demonstration grids.",
        "Solve this ARC-AGI task given the input grid and output grid examples.",
    ]
    for q in queries:
        dec = router.route(transcript=q)
        assert dec.action == RouteAction.LLM
        assert dec.solver_tool == "arc_primitives"
        assert dec.reasoning_domain == "spatial_grid"
        assert dec.thinking_mode == "thinking"
        assert "arc_primitives" in dec.exposed_libraries


def test_routing_code_repair_swe_bench() -> None:
    router = HeuristicRouter()
    queries = [
        "Diagnose and fix the failing unit test in the requests library using pytest.",
        "Apply a patch to resolve the failing test suite in the marshmallow repository.",
        "Grep the tree for the traceback and run pytest to verify the bug fix.",
        "Investigate the issue in the codebase and reproduce the issue.",
    ]
    for q in queries:
        dec = router.route(transcript=q)
        assert dec.action == RouteAction.LLM
        assert dec.solver_tool == "apply_patch"
        assert dec.reasoning_domain == "code_repair"
        assert dec.thinking_mode == "thinking"
        assert "swe_bench" in dec.exposed_libraries


def test_routing_web_search_searxng() -> None:
    router = HeuristicRouter()
    queries = [
        "Search the web for the latest financial reports of Nvidia.",
        "Look up online what the population of Tokyo is in 2026.",
        "Perform a web search using searxng for recent quantum computing discoveries.",
    ]
    for q in queries:
        dec = router.route(transcript=q)
        assert dec.action == RouteAction.LLM
        assert dec.solver_tool == "search_web"
        assert dec.reasoning_domain == "web_search"
        assert dec.thinking_mode == "thinking"
        assert "research" in dec.exposed_libraries


def test_semantic_anchor_vectorized_classification() -> None:
    from unittest.mock import MagicMock
    from lucca.senses.embed import EmbedWorker

    mock_worker = MagicMock(spec=EmbedWorker)

    def fake_embed(texts: list[str]) -> tuple[list[list[float]], int, float]:
        vecs: list[list[float]] = []
        for t in texts:
            tl = t.lower()
            if any(w in tl for w in ("grid", "flood fill", "gravity drop", "concept arc", "blocks")):
                vecs.append([0.0, 1.0, 0.0, 0.0])
            elif any(w in tl for w in ("pytest", "patch", "traceback", "repair")):
                vecs.append([0.0, 0.0, 1.0, 0.0])
            else:
                vecs.append([1.0, 0.0, 0.0, 0.0])
        return vecs, 4, 0.5

    mock_worker.embed_text = fake_embed
    router = HeuristicRouter(embed_worker=mock_worker)

    # Colloquial spatial query without regex keywords
    intent, conf, _ = router.classify_intent("can you shift these colored blocks downward")
    assert intent == "spatial_grid"
    assert conf >= 0.28

