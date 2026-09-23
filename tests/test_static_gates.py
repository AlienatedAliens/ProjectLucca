"""Static gate tests (T0) enforcing architectural invariants."""

import ast
import json
import os
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


def test_no_any_in_sandbox_public_api() -> None:
    root = Path(__file__).parent.parent / "src" / "lucca"
    targets: list[Path] = list((root / "sandbox").glob("**/*.py"))

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

    assert not violations, f"Forbidden 'Any' found in sandbox public API: {violations}"


def test_no_any_in_ui_public_api() -> None:
    root = Path(__file__).parent.parent / "src" / "lucca"
    targets: list[Path] = list((root / "ui").glob("**/*.py"))

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

    assert not violations, f"Forbidden 'Any' found in ui public API: {violations}"


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


def test_capability_claims_real() -> None:
    """
    F-ARCH-005 / F-DRIFT-006: Static gate enforcing honest capability claims.
    Ensures forbidden tokens do not appear across prompt, sandbox manifest,
    commorose actions, or UI help text.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from lucca.brain.prompt_builder import get_system_prompt
    from lucca.sandbox.service import SandboxService
    from lucca.ui.app import get_commorose_actions
    from lucca.ui.settings_dialog import SettingsDialog

    app = QApplication.instance()
    if app is None:
        app = QApplication(["test", "-platform", "offscreen"])

    forbidden = [
        "5557",
        "5558",
        "5559",
        "vram-safety-guard",
        "npu-whisper-pin",
        "temporal-logic-gate",
        "codebase-inspect-route",
        "inventor-curiosity",
        "vector-relevance-gate",
        "Codebase Inspection",
    ]

    # 1. System prompt
    prompt = get_system_prompt()
    for token in forbidden:
        assert token not in prompt, f"Forbidden token '{token}' found in system prompt"

    # 2. Sandbox capabilities manifest
    service = SandboxService(use_direct_fallback=True)
    res = service.execute_tool("gate-test", "query_capabilities", {})
    manifest_str = json.dumps(res.structured or {})
    for token in forbidden:
        assert token not in manifest_str, (
            f"Forbidden token '{token}' found in capabilities manifest"
        )

    # 3. Commorose action descriptions
    actions = get_commorose_actions()
    commorose_text = " ".join(f"{a.label} {a.description}" for a in actions)
    for token in forbidden:
        assert token not in commorose_text, f"Forbidden token '{token}' found in commorose actions"

    # 4. Settings dialog manual and about text
    dlg = SettingsDialog()
    manual_texts: list[str] = []
    for i in range(dlg.list_manual_chapters.count()):
        item = dlg.list_manual_chapters.item(i)
        if item:
            manual_texts.append(item.text())
        dlg._on_manual_chapter_selected(i)
        manual_texts.append(dlg.txt_manual_body.toPlainText())
    all_manual = " ".join(manual_texts)
    for token in forbidden:
        assert token not in all_manual, f"Forbidden token '{token}' found in settings manual"


def test_audio_concurrency_contract_exists() -> None:
    """
    F-ARCH-006: Static gate enforcing ADR-0009 audio concurrency contract.
    Ensures the audio path concurrency architecture record is present and defines
    per-resource ownership, permitted blocking, and barge-in invariants.
    """
    repo_root = Path(__file__).parent.parent
    adr_path = repo_root / "docs" / "adr" / "0009_audio_concurrency_contract.md"
    assert adr_path.exists(), f"ADR-0009 missing at {adr_path}"

    content = adr_path.read_text(encoding="utf-8")
    assert "ADR-0009" in content
    assert "Resource Ownership & Concurrency Matrix" in content
    assert "Invariant 1: Ingest Thread Non-Blocking Guarantee" in content
    assert "Invariant 2: Shared Audio Ring Mutex Protection" in content
    assert "Invariant 3: Per-Stream LLM Abort State" in content
    assert "Invariant 4: Barge-In Thread Join & State Discipline" in content
    assert "Invariant 5: Decoupled TTS Synthesis Queue" in content


def test_no_fabricated_metrics() -> None:
    """
    F-ARCH-003: Static honesty gate forbidding fabricated latency and telemetry constants.
    Ensures known fabricated constants ("382 ms", 42.5, rss_mb=50.0, rss_mb=250.0,
    compile_cache_hit=True) have zero matches across src/ and scripts/.
    """
    repo_root = Path(__file__).parent.parent
    targets: list[Path] = []
    for ext in ("*.py",):
        targets.extend((repo_root / "src").rglob(ext))
        targets.extend((repo_root / "scripts").rglob(ext))

    forbidden_patterns = [
        ('"382 ms"', "Fabricated latency badge (F-UI-001)"),
        ("rss_mb=50.0", "Fabricated audio sys.pong RSS (F-SENS-005)"),
        ("rss_mb=250.0", "Fabricated npu sys.pong RSS (F-SENS-005)"),
        ("compile_cache_hit=True", "Fabricated compile cache hit (F-SENS-013)"),
        ("42.5", "Fabricated cold startup duration (F-BRAIN-007)"),
    ]

    violations: list[str] = []
    for file_path in targets:
        text = file_path.read_text(encoding="utf-8")
        for pattern, reason in forbidden_patterns:
            if pattern in text:
                violations.append(
                    f"{file_path.relative_to(repo_root)}: matched '{pattern}' ({reason})"
                )

    assert not violations, "Fabricated metrics found:\n" + "\n".join(violations)


def test_orchestrator_turn_paths_unified_parity() -> None:
    """
    WO-11.1 static parity gate: ensures no turn-path divergence between
    voice (_run_turn) and text (_run_text_turn) in orchestrator.py.
    Diverged blocks must be extracted into shared helper methods and appear
    exactly once in src/lucca/core/orchestrator.py.
    """
    orch_path = Path(__file__).parent.parent / "src" / "lucca" / "core" / "orchestrator.py"
    text = orch_path.read_text(encoding="utf-8")

    markers = [
        (
            "exec_lines: list[str] = []",
            "F11 multi-action plan narration in _execute_act_then_narrate",
        ),
        (
            'detail="REFLEX execution"',
            "REFLEX execution triple emission in _execute_reflex",
        ),
        (
            'load_heuristics("follow_up_patterns")',
            "F20 config-driven follow-up patterns in _detect_follow_up_and_gate_tools",
        ),
        (
            "[Clarify Mode: The user's utterance was very short or ambiguous.",
            "F13 clarify mode hint in _build_epistemic_context",
        ),
    ]

    for marker, description in markers:
        count = text.count(marker)
        assert count == 1, (
            f"Parity gate violation: marker '{marker}' ({description}) must appear exactly once "
            f"in orchestrator.py, but found {count} occurrences."
        )
