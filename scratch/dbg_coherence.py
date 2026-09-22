from lucca.core.coherence import ToolReceipt, detect_ungrounded_action_claims

scenarios = [
    ("I've saved test_note.txt to your workspace.", "write_file", True),
    ("I searched for Python 3.12.", "search_web", True),
    ("I fetched the Python docs page.", "fetch_url", True),
    ("The test script ran successfully.", "run_python", True),
    ("Data processing completed.", "run_python", True),
    ("I completed the search.", "search_web", True),
    ("The search returned results.", "search_web", True),
    ("The script ran without errors.", "run_python", False),
    ("I completed the search.", "search_web", False),
]
for narration, tool, ok in scenarios:
    claims = detect_ungrounded_action_claims(narration, [ToolReceipt(tool=tool, ok=ok, trace_id="x")])
    print(repr(narration), "ok=", ok, "->", [(c.claimed_verb, c.tool_family, c.grounded) for c in claims])
