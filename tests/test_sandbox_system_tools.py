"""
Unit tests for lucca.sandbox.system_tools
Spec 01 §1, Spec 16 §3, ADR-005
"""

import os
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

import lucca.sandbox.system_tools as st
from lucca.sandbox.system_tools import (
    get_lucca_process_footprint,
    get_system_metrics,
    list_running_processes,
    query_nvidia_gpu_metrics,
)


@pytest.fixture(autouse=True)
def reset_gpu_cache() -> None:
    st._GPU_CACHE = {}
    st._LAST_GPU_QUERY = 0.0
    st._SYS_METRICS_CACHE = {}
    st._LAST_SYS_METRICS_QUERY = 0.0


def test_query_nvidia_gpu_metrics_success() -> None:
    """query_nvidia_gpu_metrics parses nvidia-smi CSV output successfully."""
    mock_csv = "NVIDIA GeForce RTX 5080 Laptop GPU, 16384, 4096, 12288, 25.0\n"
    mock_res = subprocess.CompletedProcess(
        args=["nvidia-smi"],
        returncode=0,
        stdout=mock_csv,
        stderr="",
    )

    with patch("subprocess.run", return_value=mock_res) as mock_run:
        metrics = query_nvidia_gpu_metrics()
        mock_run.assert_called_once()
        assert metrics["available"] is True
        assert metrics["name"] == "NVIDIA GeForce RTX 5080 Laptop GPU"
        assert metrics["total_mb"] == 16384.0
        assert metrics["used_mb"] == 4096.0
        assert metrics["free_mb"] == 12288.0
        assert metrics["total_gb"] == 16.0
        assert metrics["used_gb"] == 4.0
        assert metrics["free_gb"] == 12.0
        assert metrics["utilization_pct"] == 25.0


def test_query_nvidia_gpu_metrics_caching() -> None:
    """query_nvidia_gpu_metrics caches results within 1.0 second."""
    mock_csv = "RTX 5080, 16384, 1000, 15384, 10.0\n"
    mock_res = subprocess.CompletedProcess(
        args=["nvidia-smi"],
        returncode=0,
        stdout=mock_csv,
        stderr="",
    )

    with patch("subprocess.run", return_value=mock_res) as mock_run:
        m1 = query_nvidia_gpu_metrics()
        m2 = query_nvidia_gpu_metrics()
        assert m1 == m2
        assert mock_run.call_count == 1


def test_query_nvidia_gpu_metrics_failure_fallback() -> None:
    """When nvidia-smi fails or is unavailable, fallback default metrics are returned."""
    with patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi not found")):
        metrics = query_nvidia_gpu_metrics()
        assert metrics["available"] is False
        assert metrics["name"] == "NVIDIA GPU"
        assert metrics["total_gb"] == 16.0
        assert metrics["used_gb"] == 0.0
        assert metrics["free_gb"] == 16.0
        assert metrics["utilization_pct"] == 0.0

    # Also test non-zero return code
    st._GPU_CACHE = {}
    st._LAST_GPU_QUERY = 0.0
    mock_res_err = subprocess.CompletedProcess(
        args=["nvidia-smi"],
        returncode=1,
        stdout="",
        stderr="Driver error",
    )
    with patch("subprocess.run", return_value=mock_res_err):
        metrics_err = query_nvidia_gpu_metrics()
        assert metrics_err["available"] is False


def test_get_lucca_process_footprint() -> None:
    """get_lucca_process_footprint sums memory and CPU for Lucca-related processes."""
    footprint = get_lucca_process_footprint()
    assert isinstance(footprint, dict)
    assert "rss_bytes" in footprint
    assert "rss_mb" in footprint
    assert "rss_gb" in footprint
    assert "cpu_percent" in footprint
    assert "processes_tracked" in footprint
    assert footprint["rss_bytes"] >= 0
    assert footprint["processes_tracked"] >= 1


def test_get_system_metrics_structure() -> None:
    """get_system_metrics aggregates RAM, CPU, dGPU, NPU, iGPU, and time metadata."""
    metrics = get_system_metrics()
    assert "timestamp" in metrics
    assert "utc_offset" in metrics
    assert "timezone_name" in metrics

    # Substrates
    assert "ram" in metrics
    ram = metrics["ram"]
    assert isinstance(ram, dict)
    assert ram["total_gb"] > 0
    assert "percent" in ram

    assert "cpu" in metrics
    cpu = metrics["cpu"]
    assert isinstance(cpu, dict)
    assert cpu["logical_cores"] > 0
    assert "system_percent" in cpu

    assert "dgpu" in metrics
    dgpu = metrics["dgpu"]
    assert isinstance(dgpu, dict)
    assert "name" in dgpu

    assert "npu" in metrics
    npu = metrics["npu"]
    assert isinstance(npu, dict)
    assert npu["active"] is True

    assert "igpu" in metrics
    igpu = metrics["igpu"]
    assert isinstance(igpu, dict)
    assert igpu["active"] is False


def test_get_system_metrics_caching() -> None:
    """get_system_metrics caches telemetry within 1.0 second."""
    m1 = get_system_metrics()
    m2 = get_system_metrics()
    assert m1["ram"] == m2["ram"]
    assert m1["cpu"]["name"] == m2["cpu"]["name"]


def test_list_running_processes() -> None:
    """list_running_processes safely iterates active processes with filter and limit."""
    # Unfiltered
    procs = list_running_processes(limit=5)
    assert len(procs) <= 5
    assert len(procs) > 0
    for p in procs:
        assert "pid" in p
        assert "name" in p
        assert "mem_pct" in p
        assert "cpu_pct" in p

    # Filtered by current python executable name
    py_procs = list_running_processes(filter_name="python", limit=10)
    for p in py_procs:
        assert "python" in str(p["name"]).lower()
