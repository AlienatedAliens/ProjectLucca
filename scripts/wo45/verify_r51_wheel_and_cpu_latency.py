"""Build `lucca-epistemic` wheel, verify clean-venv install + pytest + import-linter, and measure CPU latency (`WO-45 R-51`)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_DIR = REPO_ROOT / "packages" / "lucca-epistemic"
DIST_DIR = PKG_DIR / "dist"
OUT_REPORT = REPO_ROOT / "logs" / "test_reports" / "wo45" / "r51_lucca_epistemic_wheel_report.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    out = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode, out


def main() -> None:
    for old_whl in DIST_DIR.glob("*.whl"):
        old_whl.unlink()

    rc_build, out_build = run_cmd(["uv", "build", "--wheel", "--out-dir", "dist"], cwd=PKG_DIR)
    if rc_build != 0:
        raise RuntimeError(f"Wheel build failed:\n{out_build}")

    wheels = sorted(DIST_DIR.glob("lucca_epistemic-*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel, got {wheels}"
    whl_path = wheels[0]
    whl_sha = sha256_file(whl_path)

    rc_root_il, out_root_il = run_cmd(["uv", "run", "lint-imports"], cwd=REPO_ROOT)
    if rc_root_il != 0:
        raise RuntimeError(f"Root lint-imports failed:\n{out_root_il}")

    with tempfile.TemporaryDirectory(prefix="lucca_epistemic_clean_") as tmp:
        venv_dir = Path(tmp) / "venv"
        rc_v, out_v = run_cmd(["uv", "venv", str(venv_dir), "--python", "3.12"], cwd=REPO_ROOT)
        if rc_v != 0:
            raise RuntimeError(f"Clean venv creation failed:\n{out_v}")

        py_exe = venv_dir / "Scripts" / "python.exe"
        pytest_exe = venv_dir / "Scripts" / "pytest.exe"
        lint_exe = venv_dir / "Scripts" / "lint-imports.exe"

        rc_inst, out_inst = run_cmd(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(py_exe),
                str(whl_path),
                "pytest",
                "import-linter",
            ],
            cwd=REPO_ROOT,
        )
        if rc_inst != 0:
            raise RuntimeError(f"Wheel install failed:\n{out_inst}")

        rc_list, out_list = run_cmd(["uv", "pip", "list", "--python", str(py_exe)], cwd=REPO_ROOT)
        rc_test, out_test = run_cmd([str(pytest_exe), "-o", "addopts=", "tests", "-v"], cwd=PKG_DIR)
        if rc_test != 0:
            raise RuntimeError(f"Clean-venv pytest failed:\n{out_test}")

        rc_pkg_il, out_pkg_il = run_cmd([str(lint_exe)], cwd=PKG_DIR)
        if rc_pkg_il != 0:
            raise RuntimeError(f"Clean-venv lint-imports failed:\n{out_pkg_il}")

        bench_code = (
            "import json, time\n"
            "from pathlib import Path\n"
            "from lucca_epistemic import OpenVINOHazardClassifier, evaluate_web_evidence_burden\n"
            "model_dir = Path(r'C:/Projects/ProjectLucca/models/proof_policy_hazard_ov')\n"
            "clf = OpenVINOHazardClassifier(model_dir=model_dir, device='CPU')\n"
            "snippets = [\n"
            "  {'url': 'https://docs.python.org/3/whatsnew/3.12.html', 'snippet': 'Python 3.12 improved error messages and f-string parsing.'},\n"
            "  {'url': 'https://realpython.com/python312-new-features/', 'snippet': 'Python 3.12 introduced flexible f-string parsing and type parameter syntax.'}\n"
            "]\n"
            "for _ in range(3):\n"
            "  evaluate_web_evidence_burden('What new syntax features shipped in Python 3.12?', snippets, classifier=clf)\n"
            "lats = []\n"
            "for i in range(100):\n"
            "  t0 = time.perf_counter()\n"
            "  evaluate_web_evidence_burden(f'What new syntax features shipped in Python 3.12 ({i})?', snippets, classifier=clf)\n"
            "  lats.append((time.perf_counter() - t0) * 1000.0)\n"
            "lats.sort()\n"
            "print(json.dumps({\n"
            "  'active_device': clf.active_device,\n"
            "  'n_runs': len(lats),\n"
            "  'mean_ms': round(sum(lats)/len(lats), 3),\n"
            "  'p50_ms': round(lats[50], 3),\n"
            "  'p95_ms': round(lats[95], 3),\n"
            "  'p99_ms': round(lats[99], 3),\n"
            "}))\n"
        )
        rc_lat, out_lat = run_cmd([str(py_exe), "-c", bench_code], cwd=REPO_ROOT)
        if rc_lat != 0:
            raise RuntimeError(f"Clean-venv CPU latency benchmark failed:\n{out_lat}")
        cpu_latency = json.loads(out_lat.splitlines()[-1])

    forbidden_deps = ("pyqt6", "sounddevice", "faster-whisper", "kokoro", "docker", "pyzmq", "z3")
    installed_lower = out_list.lower()
    leaked = [d for d in forbidden_deps if d in installed_lower]
    assert not leaked, f"Forbidden dependencies leaked into clean venv: {leaked}"

    report = {
        "task_id": "WO-45 R-51",
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "package_name": "lucca-epistemic",
        "package_version": "0.1.0",
        "license_declared": "AGPL-3.0-or-later",
        "wheel_rel_path": str(whl_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "wheel_bytes": whl_path.stat().st_size,
        "wheel_sha256": whl_sha,
        "zero_ui_audio_docker_deps_verified": True,
        "clean_venv_installed_packages": out_list,
        "clean_venv_pytest_output": out_test,
        "clean_venv_import_linter_output": out_pkg_il,
        "monorepo_import_linter_output": out_root_il,
        "cpu_only_latency_emulated_device_cpu": {
            "measurement_mode": "explicit device='CPU' on Intel Core Ultra 9 275HX inside isolated clean venv",
            **cpu_latency,
        },
        "r06_360_corpus_reference_artifact": "logs/test_reports/wo45/r06_gate_latency_npu_vs_cpu.json",
    }
    OUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[R-51 VERIFIED] {OUT_REPORT} (wheel_sha256={whl_sha})")
    print(f"  CPU latency (n=100, device='CPU'): {cpu_latency}")


if __name__ == "__main__":
    main()
