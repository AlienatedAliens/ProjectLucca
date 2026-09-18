"""Static gate tests (T0) enforcing architectural invariants."""

import ast
from pathlib import Path


def test_no_any_in_core_public_api() -> None:
    root = Path(__file__).parent.parent / "src" / "lucca"
    targets: list[Path] = list((root / "core").glob("*.py")) + [root / "ports.py"]

    violations: list[str] = []
    for file_path in targets:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "Any":
                violations.append(f"{file_path.name}:{node.lineno}: Name 'Any'")
            elif isinstance(node, ast.alias) and (node.name == "Any" or node.asname == "Any"):
                violations.append(f"{file_path.name}:{node.lineno}: import 'Any'")
            elif isinstance(node, ast.Attribute) and node.attr == "Any":
                violations.append(f"{file_path.name}:{node.lineno}: Attribute 'Any'")

    assert not violations, f"Forbidden 'Any' found in core public API: {violations}"


def test_no_any_in_brain_public_api() -> None:
    root = Path(__file__).parent.parent / "src" / "lucca"
    targets: list[Path] = list((root / "brain").glob("*.py"))

    violations: list[str] = []
    for file_path in targets:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "Any":
                violations.append(f"{file_path.name}:{node.lineno}: Name 'Any'")
            elif isinstance(node, ast.alias) and (node.name == "Any" or node.asname == "Any"):
                violations.append(f"{file_path.name}:{node.lineno}: import 'Any'")
            elif isinstance(node, ast.Attribute) and node.attr == "Any":
                violations.append(f"{file_path.name}:{node.lineno}: Attribute 'Any'")

    assert not violations, f"Forbidden 'Any' found in brain public API: {violations}"


def test_no_any_in_reasoning_public_api() -> None:
    root = Path(__file__).parent.parent / "src" / "lucca"
    targets: list[Path] = list((root / "reasoning").glob("**/*.py"))

    violations: list[str] = []
    for file_path in targets:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "Any":
                violations.append(f"{file_path.name}:{node.lineno}: Name 'Any'")
            elif isinstance(node, ast.alias) and (node.name == "Any" or node.asname == "Any"):
                violations.append(f"{file_path.name}:{node.lineno}: import 'Any'")
            elif isinstance(node, ast.Attribute) and node.attr == "Any":
                violations.append(f"{file_path.name}:{node.lineno}: Attribute 'Any'")

    assert not violations, f"Forbidden 'Any' found in reasoning public API: {violations}"


def test_tier2_marker_registered() -> None:
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    content = pyproject_path.read_text(encoding="utf-8")
    assert "tier2: Fake-backed integration tests (no hardware)" in content
    assert "not tier2" in content
