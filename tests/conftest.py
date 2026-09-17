"""
Project Lucca — Pytest Shared Fixtures
"""

import pytest
from pathlib import Path
from lucca.memory.provenance_gate import MemoryProvenanceGate
from lucca.reasoning.micro_scheme import MicroSchemeInterpreter
from lucca.sandbox.safe_file_tool import SafeFileTool
from lucca.voice.streaming_chunker import StreamingSentenceChunker
from lucca.router.conformal_guard import ConformalPredictionGuard

@pytest.fixture
def provenance_gate():
    return MemoryProvenanceGate(secret_key="test_secret_key_lucca_12345")

@pytest.fixture
def lisp_interpreter():
    return MicroSchemeInterpreter(default_gas=500)

@pytest.fixture
def sandbox_file_tool(tmp_path):
    workspace = tmp_path / "sandbox_workspace"
    return SafeFileTool(workspace_root=workspace)

@pytest.fixture
def streaming_chunker():
    return StreamingSentenceChunker(min_first_chunk_tokens=5)

@pytest.fixture
def conformal_guard():
    return ConformalPredictionGuard(alpha=0.05, quantile_threshold=0.80)
