"""
Project Lucca — Milestone 7 Packaging & Desktop Release Tests
Validates the frozen PyInstaller distribution (Lucca.exe), bundled DLLs,
native SMT verifier, OpenVINO NPU runtimes, templates, and CLI flags.
Spec 01 §1, Spec 16 §3, D-PKG-01
"""

import subprocess
from pathlib import Path

from lucca import __version__
from lucca.core.config import get_resource_path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist" / "Lucca"
EXE_PATH = DIST_DIR / "Lucca.exe"
INTERNAL_DIR = DIST_DIR / "_internal"


def test_frozen_binary_exists() -> None:
    """Verifies that Lucca.exe and its internal bundle directory exist."""
    assert EXE_PATH.exists(), f"Lucca.exe not found at {EXE_PATH}"
    assert INTERNAL_DIR.exists(), f"_internal bundle dir not found at {INTERNAL_DIR}"
    assert EXE_PATH.stat().st_size > 1_000_000, "Lucca.exe suspiciously small"


def test_frozen_binary_version_flag() -> None:
    """Verifies that Lucca.exe --version reports canonical application version with code 0."""
    # S603: EXE_PATH is a repo-relative constant, not untrusted input; check=False because the
    # assertions below inspect returncode explicitly.
    res = subprocess.run(  # noqa: S603
        [str(EXE_PATH), "--version"], capture_output=True, text=True, timeout=15, check=False
    )
    assert res.returncode == 0
    assert f"Lucca {__version__}" in res.stdout


def test_frozen_binary_help_flag() -> None:
    """Verifies that Lucca.exe --help prints usage information with code 0."""
    res = subprocess.run(  # noqa: S603 — repo-relative constant path; returncode asserted below
        [str(EXE_PATH), "--help"], capture_output=True, text=True, timeout=15, check=False
    )
    assert res.returncode == 0
    assert "Project Lucca" in res.stdout
    assert "--check" in res.stdout
    assert "--headless" in res.stdout


def test_frozen_binary_check_flag() -> None:
    """Verifies that Lucca.exe --check passes all hardware environment checks."""
    import os

    env = dict(os.environ)
    env["LUCCA_HOME"] = "C:/ProjectLucca"
    res = subprocess.run(  # noqa: S603 — repo-relative constant path; returncode asserted below
        [str(EXE_PATH), "--check"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert res.returncode == 0, f"Check failed with stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert "[SUCCESS] All system environment criteria passed!" in res.stdout
    assert "Intel NPU detected by OpenVINO" in res.stdout
    assert "sqlite-vec loaded successfully" in res.stdout


def test_bundled_data_assets() -> None:
    """Verifies that essential runtime templates, configs, migrations, and assets are bundled."""
    template_path = INTERNAL_DIR / "templates" / "mistral_nemo.jinja"
    assert template_path.exists(), f"Missing template: {template_path}"
    assert "system_message" in template_path.read_text(encoding="utf-8")

    persona_path = INTERNAL_DIR / "config" / "persona.toml"
    assert persona_path.exists(), f"Missing persona config: {persona_path}"

    migration_path = INTERNAL_DIR / "lucca" / "memory" / "migrations" / "0001_init.sql"
    assert migration_path.exists(), f"Missing schema migration: {migration_path}"

    icon_path = INTERNAL_DIR / "assets" / "icon.png"
    assert icon_path.exists(), f"Missing icon: {icon_path}"

    sprite_manifest = INTERNAL_DIR / "assets" / "sprites" / "lucca" / "manifest.json"
    assert sprite_manifest.exists(), f"Missing sprite manifest: {sprite_manifest}"


def test_bundled_native_binaries() -> None:
    """Verifies that Z3 SMT solver, sqlite-vec, and OpenVINO NPU dynamic libraries are bundled."""
    z3_dll = INTERNAL_DIR / "z3" / "lib" / "libz3.dll"
    assert z3_dll.exists(), f"Missing Z3 DLL: {z3_dll}"

    vec_dll = INTERNAL_DIR / "sqlite_vec" / "vec0.dll"
    assert vec_dll.exists(), f"Missing sqlite-vec DLL: {vec_dll}"

    npu_plugin = INTERNAL_DIR / "openvino" / "libs" / "openvino_intel_npu_plugin.dll"
    assert npu_plugin.exists(), f"Missing OpenVINO NPU plugin: {npu_plugin}"


def test_get_resource_path_resolution() -> None:
    """Verifies get_resource_path resolution logic across repo and relative paths."""
    resolved_assets = get_resource_path("assets/icon.png")
    assert resolved_assets.exists()

    resolved_templates = get_resource_path("templates/mistral_nemo.jinja")
    assert resolved_templates.exists()
