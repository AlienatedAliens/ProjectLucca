"""
Unit tests for regex-free tool call extraction using standard JSONDecoder.
"""
import json
from typing import Any


def extract_tool_call_json_decoder(response: str) -> tuple[str | None, dict[str, Any] | None]:
    """Extracts tool name and arguments from model response using JSONDecoder without regex."""
    if not response:
        return None, None

    decoder = json.JSONDecoder()
    pos = 0
    while True:
        idx = response.find("{", pos)
        if idx == -1:
            break
        try:
            obj, _ = decoder.raw_decode(response, idx)
            if isinstance(obj, dict) and "tool" in obj and "args" in obj:
                return str(obj["tool"]), dict(obj.get("args") or {})
            pos = idx + 1
        except json.JSONDecodeError:
            pos = idx + 1

    return None, None


def test_simple_tool_call():
    text = '```tool\n{"tool": "run_pytest", "args": {"test_path": "tests/test_foo.py"}}\n```'
    tool, args = extract_tool_call_json_decoder(text)
    assert tool == "run_pytest"
    assert args == {"test_path": "tests/test_foo.py"}


def test_tool_call_with_nested_braces_in_strings():
    text = (
        'Here is the patch:\n'
        '```tool\n'
        '{\n'
        '  "tool": "apply_patch",\n'
        '  "args": {\n'
        '    "path": "src/params.py",\n'
        '    "target_chunk": "def foo():\\n    return {\\"a\\": {\\"b\\": 1}}",\n'
        '    "replacement_chunk": "def foo():\\n    return {\\"a\\": {\\"b\\": 2}}"\n'
        '  }\n'
        '}\n'
        '```\n'
        'Please review.'
    )
    tool, args = extract_tool_call_json_decoder(text)
    assert tool == "apply_patch"
    assert args["path"] == "src/params.py"
    assert '{"b": 1}' in args["target_chunk"]
    assert '{"b": 2}' in args["replacement_chunk"]


def test_tool_call_with_unquoted_preceding_text():
    text = 'I will now view the file.\n{"tool": "view_slice", "args": {"path": "a.py", "start_line": 1, "end_line": 10}}'
    tool, args = extract_tool_call_json_decoder(text)
    assert tool == "view_slice"
    assert args == {"path": "a.py", "start_line": 1, "end_line": 10}
