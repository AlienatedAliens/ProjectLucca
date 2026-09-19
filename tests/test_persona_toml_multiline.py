"""
Project Lucca — Multi-Line TOML Serialization Tests
Verifies that update_toml_content properly replaces multi-line strings without leaving orphan lines.
"""

import tomllib

from lucca.brain.prompt_builder import update_toml_content


def test_update_toml_content_replaces_multiline_losslessly() -> None:
    initial_toml = (
        'name = "Lucca"\n'
        'custom_prompt = """\n'
        "Line 1 of long prompt\n"
        "Line 2 of long prompt\n"
        '"""\n'
        "uses_your_name = true\n"
        'voice = "genki_heroine"\n'
    )

    # 1. Verify initial TOML is valid
    parsed_initial = tomllib.loads(initial_toml)
    assert "Line 1" in parsed_initial["custom_prompt"]

    # 2. Update custom_prompt to an empty single-line string
    updated = update_toml_content(initial_toml, {"custom_prompt": ""})

    # 3. Assert no orphan lines remain and TOML is valid
    assert "Line 1" not in updated
    assert "Line 2" not in updated
    parsed_updated = tomllib.loads(updated)
    assert parsed_updated["custom_prompt"] == ""
    assert parsed_updated["uses_your_name"] is True
    assert parsed_updated["voice"] == "genki_heroine"


def test_update_toml_content_from_single_to_multiline() -> None:
    initial_toml = 'name = "Lucca"\ncustom_prompt = ""\nuses_your_name = true\n'
    updated = update_toml_content(initial_toml, {"custom_prompt": "First line\nSecond line"})

    parsed = tomllib.loads(updated)
    assert parsed["custom_prompt"] == "First line\nSecond line"
    assert parsed["uses_your_name"] is True
