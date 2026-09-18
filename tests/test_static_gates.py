"""Static gate tests (T0) enforcing architectural invariants."""

import ast
import json
import re
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


def test_model_manifest_complete() -> None:
    """T0 static gate: verifies models/MANIFEST.json exists and has valid cryptographic pins."""
    manifest_path = Path(__file__).parent.parent / "models" / "MANIFEST.json"
    assert manifest_path.exists(), f"models/MANIFEST.json missing at: {manifest_path}"

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    assert "files" in data, "models/MANIFEST.json missing 'files' key"
    files = data["files"]
    assert isinstance(files, dict)

    required_entries = [
        "llm/ultravox-v0_5-llama-3_1-8b-Q6_K.gguf",
        "llm/mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf",
        "tts/kokoro-v1.0.onnx",
        "tts/voices-v1.0.bin",
    ]

    hex_pattern = re.compile(r"^[0-9a-f]{64}$")

    for req in required_entries:
        assert req in files, f"Missing required model entry in manifest: {req}"
        entry = files[req]
        assert isinstance(entry, dict), f"Entry for {req} must be a dict"
        sha = entry.get("sha256", "")
        assert hex_pattern.match(sha), f"Entry {req} has invalid sha256 hex pin: {sha}"
        size = entry.get("size_bytes", 0)
        assert isinstance(size, int) and size > 0, f"Entry {req} must have size_bytes > 0"
        source_repo = entry.get("source_repo", "")
        assert isinstance(source_repo, str) and source_repo, f"Entry {req} must define source_repo"
        source_file = entry.get("source_filename", "")
        assert isinstance(source_file, str) and source_file, (
            f"Entry {req} must define source_filename"
        )
