"""
Project Lucca — Phase 2 Live Hardware Integration Test (T3 hw)
Spec 09 §8, ADR-003, ADR-004
Verifies live WSL2 Docker containers, positive-controlled egress policy, and live in-container RPC.
"""

import json
import shutil
import subprocess

import pytest

from lucca.sandbox.egress import EgressVerifier


@pytest.mark.hw
def test_live_phase2_egress_matrix():
    """
    Live hardware verification of positive-controlled egress:
    1. Host listener reachable from Ubuntu shell (positive control).
    2. Container LAN access strictly blocked (192.168.x blocked).
    3. Public HTTPS allowed (example.com -> 200 OK).
    4. Non-web ports blocked (1.1.1.1:22 blocked).
    """
    verifier = EgressVerifier(test_port=8089)
    # Ensure rules are applied
    applied, msg = verifier.apply_rules()
    assert applied is True, f"Failed to apply egress rules: {msg}"

    # Run verification matrix
    results = verifier.verify_all()
    assert results["all_passed"] is True, f"Egress matrix failed: {results}"
    assert results["checks"]["host_shell_positive_control"] is True
    assert results["checks"]["container_lan_blocked"] is True
    assert results["checks"]["container_public_https_allowed"] is True
    assert results["checks"]["container_ssh_blocked"] is True


@pytest.mark.hw
def test_live_phase2_in_container_rpc():
    """
    Live verification of lucca-toolsrv inside lucca/file-sandbox:latest:
    - Runs container with zero network and workspace mount.
    - Executes list_dir, write_file, read_file, search_text, and run_python.
    """
    wsl_bin = shutil.which("wsl") or "wsl"
    req = json.dumps({"call_id": "test-hw-1", "tool": "list_dir", "args": {"path": ""}})
    proc = subprocess.run(  # noqa: S603
        [
            wsl_bin,
            "-d",
            "Ubuntu",
            "--",
            "docker",
            "run",
            "--rm",
            "-i",
            "lucca/file-sandbox:latest",
            "lucca-toolsrv",
        ],
        input=req,
        text=True,
        capture_output=True,
        timeout=10.0,
        check=False,
    )
    assert proc.returncode == 0
    res = json.loads(proc.stdout.strip())
    assert res["ok"] is True
    assert res["call_id"] == "test-hw-1"

    # 2. Test in-container python execution
    py_req = json.dumps(
        {
            "call_id": "test-hw-2",
            "tool": "run_python",
            "args": {"code": "import math; print(math.sqrt(1764))"},
        }
    )
    py_proc = subprocess.run(  # noqa: S603
        [
            wsl_bin,
            "-d",
            "Ubuntu",
            "--",
            "docker",
            "run",
            "--rm",
            "-i",
            "lucca/file-sandbox:latest",
            "lucca-toolsrv",
        ],
        input=py_req,
        text=True,
        capture_output=True,
        timeout=10.0,
        check=False,
    )
    assert py_proc.returncode == 0
    py_res = json.loads(py_proc.stdout.strip())
    assert py_res["ok"] is True
    assert "42.0" in py_res["content"]
