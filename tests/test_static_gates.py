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
    WO-11.1 & WO-12.2 static parity gate: ensures no turn-path divergence between
    voice (_run_turn) and text (_run_text_turn).
    All unified logic resides in turn_pipeline.py (each marker appears exactly once),
    while orchestrator.py contains zero duplicate logic and strictly delegates to
    TurnPipeline.run().
    """
    repo_root = Path(__file__).parent.parent
    pipeline_path = repo_root / "src" / "lucca" / "core" / "turn_pipeline.py"
    orch_path = repo_root / "src" / "lucca" / "core" / "orchestrator.py"

    assert pipeline_path.exists(), f"turn_pipeline.py does not exist at {pipeline_path}"
    assert orch_path.exists(), f"orchestrator.py does not exist at {orch_path}"

    pipeline_text = pipeline_path.read_text(encoding="utf-8")
    orch_text = orch_path.read_text(encoding="utf-8")

    markers = [
        (
            "exec_lines: list[str] = []",
            "F11 multi-action plan narration in execute_act_then_narrate",
        ),
        (
            'detail="REFLEX execution"',
            "REFLEX execution triple emission in execute_reflex",
        ),
        (
            'load_heuristics("follow_up_patterns")',
            "F20 config-driven follow-up patterns in detect_follow_up_and_gate_tools",
        ),
        (
            "[Clarify Mode: The user's utterance was very short or ambiguous.",
            "F13 clarify mode hint in build_epistemic_context",
        ),
    ]

    for marker, description in markers:
        pipe_count = pipeline_text.count(marker)
        assert pipe_count == 1, (
            f"Parity gate violation: marker '{marker}' ({description}) must appear exactly once "
            f"in turn_pipeline.py, but found {pipe_count} occurrences."
        )

        orch_count = orch_text.count(marker)
        assert orch_count == 0, (
            f"Parity gate violation: marker '{marker}' ({description}) has leaked into "
            f"orchestrator.py ({orch_count} occurrences). All unified logic must reside "
            f"exclusively in turn_pipeline.py."
        )

    # Verify orchestrator delegates to turn_pipeline.run
    assert "self.turn_pipeline.run(turn_input)" in orch_text, (
        "Orchestrator must delegate turn execution to self.turn_pipeline.run(turn_input)"
    )
    assert orch_text.count("self.turn_pipeline.run(turn_input)") == 2, (
        "Both _run_turn and _run_text_turn must delegate to self.turn_pipeline.run(turn_input)"
    )


def test_active_docs_staleness_lint() -> None:
    """
    WO-11.6: Staleness lint on active docs (AGENTS.md, GEMINI.md, ARCHITECTURE.md, DECISIONS.md).
    Guarantees no known-superseded terms (M=3, NeMo as primary, Chroma as live) linger in docs.
    """
    repo_root = Path(__file__).parent.parent
    active_docs = [
        repo_root / "AGENTS.md",
        repo_root / "GEMINI.md",
        repo_root / "README.md",
        repo_root / "docs" / "README.md",
        repo_root / "docs" / "ARCHITECTURE.md",
        repo_root / "docs" / "DECISIONS.md",
        repo_root / "docs" / "MODEL_STRATEGY.md",
        repo_root / "docs" / "USER_GUIDE_WHAT_LUCCA_DOES.md",
        repo_root / "docs" / "V2_BACKLOG.md",
        repo_root / "docs" / "specs" / "STUDIO_CAPABILITY_ROADMAP.md",
        repo_root / "docs" / "audit" / "findings" / "V1_RELEASE_AUDIT.md",
        repo_root / "docs" / "adr" / "0009_audio_concurrency_contract.md",
    ]

    violations: list[str] = []
    forbidden_terms = [
        (re.compile(r"\bM=3\b"), "superseded M=3 round cap (cap is M=4 per D-BRAIN-05 v2)"),
        (
            re.compile(r"primary brain:\s*mistral nemo", re.IGNORECASE),
            "NeMo as primary brain (superseded by Gemma 4 12B per D-BRAIN-05 v2)",
        ),
        (
            re.compile(r"chroma(?:\s+db)?\s+(?:is\s+)?(?:live|active|primary)", re.IGNORECASE),
            "Chroma as live vector store (retired in favor of sqlite-vec per D-MEM-03)",
        ),
        (
            re.compile(r"hosting\s+`?Mistral-Nemo", re.IGNORECASE),
            "llama-server hosting NeMo as active runtime (superseded by Gemma 4 12B)",
        ),
        (
            re.compile(r"llama-server(?:\.exe)?\s*\(\s*(?:Mistral-)?NeMo", re.IGNORECASE),
            "llama-server described as running NeMo",
        ),
        (
            re.compile(r"\(\s*NeMo\s*12B\s*\)", re.IGNORECASE),
            "NeMo 12B named as the language model",
        ),
        (
            re.compile(r"Mistral-NeMo-12B\s+Q6_K", re.IGNORECASE),
            "NeMo Q6_K named as the loaded GGUF",
        ),
        (
            re.compile(r"\b5-substrate\b", re.IGNORECASE),
            "superseded 5-substrate reference (actual count is 8 substrates in EpistemicSubstrate)",
        ),
        (
            re.compile(r"never what she herself said", re.IGNORECASE),
            "stale pre-A1 autobiographical memory denial",
        ),
        (
            re.compile(r"Not yet enforced", re.IGNORECASE),
            "unratified status on active v1.0 decision",
        ),
        (
            re.compile(r"MAX_REGISTRY_TOOLS\s*=\s*18\b"),
            "superseded tool cap 18 (actual cap is MAX_REGISTRY_TOOLS = 19 per WO-17)",
        ),
        (
            re.compile(r"\b18 native tools\b", re.IGNORECASE),
            "superseded 18 native tools count (actual count is 19 per WO-17 calc_math)",
        ),
        (
            re.compile(r"capped at 18\b", re.IGNORECASE),
            "superseded cap at 18 tools (actual cap is 19 per WO-17)",
        ),
        (
            re.compile(r"_tts_queue.*maxsize=8\b"),
            "superseded TTS queue maxsize=8 (actual size is 32 per WO-17 Phase 7)",
        ),
        (
            re.compile(r"queue.*capacity\s+8\b", re.IGNORECASE),
            "superseded TTS queue capacity 8 (actual capacity is 32 per WO-17 Phase 7)",
        ),
    ]

    for doc_path in active_docs:
        assert doc_path.exists(), f"Active doc {doc_path} does not exist"
        text = doc_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            for pattern, reason in forbidden_terms:
                if pattern.search(line):
                    violations.append(
                        f"{doc_path.name}:{lineno}: matched '{pattern.pattern}' ({reason})\n"
                        f"  Line: {line.strip()}"
                    )

    assert not violations, "Staleness lint failed in active docs:\n" + "\n".join(violations)


def test_registry_tool_count_consistency() -> None:
    """WO-17 drift gate (code <-> docs): the number of ToolSchema entries defined in
    get_default_native_tools() must equal MAX_REGISTRY_TOOLS, and the active docs'
    positive tool-count claims must cite that same number. Catches the class of
    drift where a work order adds a tool (or edits docs) without propagating the
    count everywhere (the 18-vs-19 incident)."""
    repo_root = Path(__file__).parent.parent
    caps_text = (repo_root / "src" / "lucca" / "core" / "capabilities.py").read_text(
        encoding="utf-8"
    )

    cap_match = re.search(r"MAX_REGISTRY_TOOLS:\s*Final\[int\]\s*=\s*(\d+)", caps_text)
    assert cap_match, "MAX_REGISTRY_TOOLS constant not found in capabilities.py"
    cap = int(cap_match.group(1))

    registered = len(re.findall(r'"[a-z_]+": ToolSchema\(', caps_text))
    assert registered == cap, (
        f"Registry defines {registered} ToolSchema entries but MAX_REGISTRY_TOOLS={cap}. "
        "A tool was added or removed without updating the cap (or vice versa)."
    )

    # Active docs must cite the live count in their positive claims.
    doc_claims: list[tuple[str, int]] = []
    doc_paths = [
        repo_root / "docs" / "README.md",
        repo_root / "docs" / "USER_GUIDE_WHAT_LUCCA_DOES.md",
    ]
    for doc_path in doc_paths:
        text = doc_path.read_text(encoding="utf-8")
        for m in re.finditer(r"(\d+)\s+native tools", text):
            doc_claims.append((doc_path.name, int(m.group(1))))
    assert doc_claims, "No '<N> native tools' claim found in active docs"
    for name, claimed in doc_claims:
        assert claimed == cap, (
            f"{name} claims {claimed} native tools but the registry defines {cap} "
            f"(MAX_REGISTRY_TOOLS={cap}). Update the doc or the registry."
        )


def test_package_version_matches_release_baseline() -> None:
    """Version drift gate: pyproject.toml version must match the release baseline
    cited in docs/README.md ('Git Baseline: Project Lucca vX.Y.Z ...'). Catches
    the pyproject 0.2.0 vs v1.0.0 drift found in the 2026-09 external review."""
    repo_root = Path(__file__).parent.parent
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    pkg_match = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', pyproject, re.MULTILINE)
    assert pkg_match, "package version not found in pyproject.toml"
    pkg_version = pkg_match.group(1)

    docs_readme = (repo_root / "docs" / "README.md").read_text(encoding="utf-8")
    baseline_match = re.search(r"Git Baseline:\*\* Project Lucca\s+v(\d+\.\d+\.\d+)", docs_readme)
    assert baseline_match, "release baseline version not found in docs/README.md"
    baseline_version = baseline_match.group(1)

    assert pkg_version == baseline_version, (
        f"pyproject.toml version {pkg_version} does not match the release baseline "
        f"v{baseline_version} cited in docs/README.md. Bump one or the other."
    )


def _find_silent_broad_excepts(source: str, filename: str) -> list[str]:
    violations: list[str] = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        t = node.type
        is_broad = (
            t is not None and isinstance(t, ast.Name) and t.id == "Exception"
        ) or (
            t is not None and isinstance(t, ast.Attribute) and t.attr == "Exception"
        )
        if not is_broad:
            continue
        body_src = ast.dump(node)
        has_log = "id='logger'" in body_src or "id='_LOG'" in body_src
        has_raise = any(isinstance(n, ast.Raise) for n in ast.walk(node))
        if has_log or has_raise:
            continue
        violations.append(f"{filename}:{node.lineno}")
    return violations


def test_no_silent_broad_excepts() -> None:
    """F-ARCH-105 gate: every 'except Exception' handler across src/lucca/
    must either log (logger.* / _LOG.*) or re-raise. No silent swallowing.
    Includes positive controls for detection and acceptance."""
    # Positive control 1: verify that synthetic silent broad except is detected
    bad_sample = "try:\n    x = 1\nexcept Exception:\n    pass\n"
    silent_violations = _find_silent_broad_excepts(bad_sample, "bad_sample.py")
    assert len(silent_violations) == 1, (
        f"Positive control failed: expected 1 violation for silent except, got {len(silent_violations)}"
    )

    # Positive control 2: verify that synthetic logged broad except is permitted
    good_sample = "try:\n    x = 1\nexcept Exception as exc:\n    logger.debug('failed', error=str(exc))\n"
    logged_violations = _find_silent_broad_excepts(good_sample, "good_sample.py")
    assert len(logged_violations) == 0, (
        f"Positive control failed: expected 0 violations for logged except, got {len(logged_violations)}"
    )

    # Positive control 3: verify that synthetic re-raising broad except is permitted
    reraise_sample = "try:\n    x = 1\nexcept Exception:\n    raise\n"
    reraise_violations = _find_silent_broad_excepts(reraise_sample, "reraise_sample.py")
    assert len(reraise_violations) == 0, (
        f"Positive control failed: expected 0 violations for re-raised except, got {len(reraise_violations)}"
    )

    # Tree-wide check over all src/lucca/*.py
    root = Path(__file__).parent.parent / "src" / "lucca"
    all_violations: list[str] = []
    for py_path in sorted(root.rglob("*.py")):
        rel = py_path.relative_to(root)
        source = py_path.read_text(encoding="utf-8")
        all_violations.extend(_find_silent_broad_excepts(source, str(rel)))

    assert not all_violations, (
        f"Found {len(all_violations)} silent broad except handler(s) in src/lucca:\n"
        + "\n".join(all_violations)
    )


def test_memory_commit_service_decomposition() -> None:
    """WO-18b (F-ARCH-103) static parity gate: ensures memory commit operations
    are encapsulated in MemoryCommitService.
    Canonical method definitions must appear in MemoryCommitService and not in
    orchestrator.py (which delegates).
    """
    repo_root = Path(__file__).parent.parent
    mcs_path = repo_root / "src" / "lucca" / "core" / "memory_commit_service.py"
    orch_path = repo_root / "src" / "lucca" / "core" / "orchestrator.py"

    assert mcs_path.exists(), f"memory_commit_service.py does not exist at {mcs_path}"
    assert orch_path.exists(), f"orchestrator.py does not exist at {orch_path}"

    mcs_text = mcs_path.read_text(encoding="utf-8")
    orch_text = orch_path.read_text(encoding="utf-8")

    mcs_tree = ast.parse(mcs_text, filename=str(mcs_path))
    orch_tree = ast.parse(orch_text, filename=str(orch_path))

    mcs_methods = {
        n.name
        for n in ast.walk(mcs_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    orch_methods = {
        n.name
        for n in ast.walk(orch_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    target_methods = [
        "commit_transcript",
        "commit_action_receipts",
        "maybe_extract_facts",
        "commit_assistant_utterance",
        "commit_coherence_breach",
        "maybe_form_belief",
    ]

    for m in target_methods:
        assert m in mcs_methods, f"Expected '{m}' to be defined in MemoryCommitService"
        assert m not in orch_methods, f"Expected '{m}' not to be defined in Orchestrator (use delegate _...)"

    # Text marker check: each canonical 'def <method>(' appears exactly once in MCS and 0 in orchestrator
    for m in target_methods:
        def_marker = f"def {m}("
        assert mcs_text.count(def_marker) == 1, (
            f"Parity gate violation: '{def_marker}' must appear exactly once in memory_commit_service.py, "
            f"got {mcs_text.count(def_marker)}"
        )
        assert orch_text.count(def_marker) == 0, (
            f"Parity gate violation: '{def_marker}' must not appear in orchestrator.py, "
            f"got {orch_text.count(def_marker)}"
        )


def test_belief_service_decomposition() -> None:
    """WO-18b (F-ARCH-103) static parity gate: ensures belief contradiction
    and pending spoken update operations are encapsulated in BeliefService.
    Canonical method definitions must appear in BeliefService and not in
    orchestrator.py (which delegates).
    """
    repo_root = Path(__file__).parent.parent
    bs_path = repo_root / "src" / "lucca" / "core" / "belief_service.py"
    orch_path = repo_root / "src" / "lucca" / "core" / "orchestrator.py"

    assert bs_path.exists(), f"belief_service.py does not exist at {bs_path}"
    assert orch_path.exists(), f"orchestrator.py does not exist at {orch_path}"

    bs_text = bs_path.read_text(encoding="utf-8")
    orch_text = orch_path.read_text(encoding="utf-8")

    bs_tree = ast.parse(bs_text, filename=str(bs_path))
    orch_tree = ast.parse(orch_text, filename=str(orch_path))

    bs_methods = {
        n.name
        for n in ast.walk(bs_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    orch_methods = {
        n.name
        for n in ast.walk(orch_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    target_methods = [
        "check_contradictions",
        "maybe_speak_pending_updates",
    ]

    for m in target_methods:
        assert m in bs_methods, f"Expected '{m}' to be defined in BeliefService"
        assert m not in orch_methods, f"Expected '{m}' not to be defined in Orchestrator (use delegate _...)"

    for m in target_methods:
        def_marker = f"def {m}("
        assert bs_text.count(def_marker) == 1, (
            f"Parity gate violation: '{def_marker}' must appear exactly once in belief_service.py, "
            f"got {bs_text.count(def_marker)}"
        )
        assert orch_text.count(def_marker) == 0, (
            f"Parity gate violation: '{def_marker}' must not appear in orchestrator.py, "
            f"got {orch_text.count(def_marker)}"
        )


def test_confirmation_manager_decomposition() -> None:
    """WO-18b (F-ARCH-103) static parity gate: ensures confirmation lifecycle
    and prompt audio abort operations are encapsulated in ConfirmationManager.
    Canonical method definitions must appear in ConfirmationManager and not in
    orchestrator.py (which delegates).
    """
    repo_root = Path(__file__).parent.parent
    cm_path = repo_root / "src" / "lucca" / "core" / "confirmation_manager.py"
    orch_path = repo_root / "src" / "lucca" / "core" / "orchestrator.py"

    assert cm_path.exists(), f"confirmation_manager.py does not exist at {cm_path}"
    assert orch_path.exists(), f"orchestrator.py does not exist at {orch_path}"

    cm_text = cm_path.read_text(encoding="utf-8")
    orch_text = orch_path.read_text(encoding="utf-8")

    cm_tree = ast.parse(cm_text, filename=str(cm_path))
    orch_tree = ast.parse(orch_text, filename=str(orch_path))

    cm_methods = {
        n.name
        for n in ast.walk(cm_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    orch_methods = {
        n.name
        for n in ast.walk(orch_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "confirm_action" in cm_methods, "Expected 'confirm_action' to be defined in ConfirmationManager"
    assert "request_confirmation" in cm_methods, "Expected 'request_confirmation' to be defined in ConfirmationManager"
    assert "abort_confirmation_prompt_playback" in cm_methods, "Expected 'abort_confirmation_prompt_playback' in ConfirmationManager"

    assert "request_confirmation" not in orch_methods, "Expected 'request_confirmation' not in Orchestrator (use delegate _request_confirmation)"
    assert "abort_confirmation_prompt_playback" not in orch_methods, "Expected 'abort_confirmation_prompt_playback' not in Orchestrator (use delegate _abort_confirmation_prompt_playback)"

    delegated_methods = [
        "request_confirmation",
        "abort_confirmation_prompt_playback",
    ]
    for m in delegated_methods:
        def_marker = f"def {m}("
        assert cm_text.count(def_marker) == 1, (
            f"Parity gate violation: '{def_marker}' must appear exactly once in confirmation_manager.py, "
            f"got {cm_text.count(def_marker)}"
        )
        assert orch_text.count(def_marker) == 0, (
            f"Parity gate violation: '{def_marker}' must not appear in orchestrator.py, "
            f"got {orch_text.count(def_marker)}"
        )


def _find_ui_domain_import_violations(source: str, filename: str) -> list[str]:
    """Scans Python source code for forbidden direct domain imports from UI."""
    tree = ast.parse(source, filename=filename)
    forbidden_prefixes = ("lucca.memory", "lucca.reasoning", "lucca.sandbox")
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden_prefixes:
                    if alias.name == prefix or alias.name.startswith(f"{prefix}."):
                        violations.append(
                            f"{filename}:{node.lineno}: direct domain import '{alias.name}'"
                        )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for prefix in forbidden_prefixes:
                    if node.module == prefix or node.module.startswith(f"{prefix}."):
                        violations.append(
                            f"{filename}:{node.lineno}: direct domain import 'from {node.module}'"
                        )
    return violations


def test_ui_no_direct_domain_imports() -> None:
    """WO-18e (F-ARCH-104) static architecture gate: ensures src/lucca/ui/
    has zero direct imports into lucca.memory, lucca.reasoning, or lucca.sandbox.
    All domain access must route through StudioFacade in lucca.core.
    Includes positive controls for detection and acceptance.
    """
    # Positive control 1: memory import detected
    mem_sample = "from lucca.memory.store import MemoryStore\n"
    mem_v = _find_ui_domain_import_violations(mem_sample, "test_mem.py")
    assert len(mem_v) == 1, f"Positive control failed for memory import: {mem_v}"

    # Positive control 2: reasoning import detected
    reas_sample = "from lucca.reasoning.scheme import parse_rule\n"
    reas_v = _find_ui_domain_import_violations(reas_sample, "test_reas.py")
    assert len(reas_v) == 1, f"Positive control failed for reasoning import: {reas_v}"

    # Positive control 3: sandbox import detected
    sbx_sample = "import lucca.sandbox.system_tools as st\n"
    sbx_v = _find_ui_domain_import_violations(sbx_sample, "test_sbx.py")
    assert len(sbx_v) == 1, f"Positive control failed for sandbox import: {sbx_v}"

    # Positive control 4: studio_facade import accepted
    facade_sample = "from lucca.core.studio_facade import StudioFacade\n"
    facade_v = _find_ui_domain_import_violations(facade_sample, "test_facade.py")
    assert len(facade_v) == 0, f"Positive control failed for facade import: {facade_v}"

    # Real UI codebase scan
    ui_root = Path(__file__).parent.parent / "src" / "lucca" / "ui"
    assert ui_root.exists(), f"UI root does not exist at {ui_root}"

    ALLOWLIST: set[str] = set()

    all_violations: list[str] = []
    for py_file in sorted(ui_root.rglob("*.py")):
        rel = py_file.relative_to(ui_root).as_posix()
        if rel in ALLOWLIST:
            continue
        source = py_file.read_text(encoding="utf-8")
        all_violations.extend(_find_ui_domain_import_violations(source, f"ui/{rel}"))

    assert not all_violations, (
        f"Found {len(all_violations)} direct domain import(s) in src/lucca/ui:\n"
        + "\n".join(all_violations)
    )




