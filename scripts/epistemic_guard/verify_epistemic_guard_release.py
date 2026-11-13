"""End-to-end clean-venv verification of `epistemic-guard` (`v0.3.0`, MIT):
  1. Builds wheel via `uv build --wheel`
  2. Installs wheel into an isolated temporary venv outside `ProjectLucca`
  3. Runs `pytest`, `lint-imports`, and `epistemic-guard demo`
  4. Exercises `epistemic-guard download-models` + SHA-256 verification against the built INT8 tarballs
  5. Verifies `epistemic-guard doctor` and live INT8 inference across all 3 models (`action_claim_int8`,
     `hazard_int8`, `web_evidence_int8`)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PKG_DIR: Final[Path] = REPO_ROOT / "packages" / "epistemic-guard"
ARCHIVES_DIR: Final[Path] = REPO_ROOT / "models" / "epistemic_guard_int8" / "release_archives"
REPORT_OUT: Final[Path] = (
    REPO_ROOT / "logs" / "test_reports" / "epistemic_guard" / "clean_venv_release_report.json"
)


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    res = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"Command failed ({res.returncode}): {' '.join(cmd)}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
    return (res.stdout + "\n" + res.stderr).strip()


def main() -> None:
    import tarfile

    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    pack_dir = REPO_ROOT / "models" / "epistemic_guard_int8"
    for dname in ("action_claim_int8", "hazard_int8", "web_evidence_int8"):
        tar_dest = ARCHIVES_DIR / f"{dname}.tar.gz"
        with tarfile.open(tar_dest, mode="w:gz") as tf:
            tf.add(pack_dir / dname, arcname=dname)

    _run(["uv", "build", "--wheel"], cwd=PKG_DIR)
    whl = next((PKG_DIR / "dist").glob("epistemic_guard-0.3.0-*.whl"))

    tmp = Path(tempfile.mkdtemp(prefix="epistemic_guard_clean_"))
    try:
        vdir = tmp / "venv"
        cdir = tmp / "model_cache"
        _run(["uv", "venv", str(vdir), "--python", "3.12"], cwd=tmp)

        py = vdir / "Scripts" / "python.exe"
        eg = vdir / "Scripts" / "epistemic-guard.exe"
        li = vdir / "Scripts" / "lint-imports.exe"

        _run(
            ["uv", "pip", "install", "--python", str(py), str(whl), "pytest", "import-linter"],
            cwd=tmp,
        )
        pytest_out = _run(
            [
                str(py),
                "-m",
                "pytest",
                "-c",
                str(PKG_DIR / "pyproject.toml"),
                str(PKG_DIR / "tests"),
                "-v",
            ],
            cwd=tmp,
        )
        lint_out = _run([str(li)], cwd=PKG_DIR)
        demo_out = _run([str(eg), "demo"], cwd=tmp)

        dl_out = _run(
            [
                str(eg),
                "download-models",
                "--cache-dir",
                str(cdir),
                "--base-url",
                ARCHIVES_DIR.as_uri(),
            ],
            cwd=tmp,
        )
        env = dict(os.environ, EPISTEMIC_GUARD_MODEL_DIR=str(cdir))
        doctor_out = _run([str(eg), "doctor"], cwd=tmp, env=env)

        probe_code = (
            "import json\n"
            "from epistemic_guard import (\n"
            "    ReceiptSupervisor,\n"
            "    OpenVINOHazardClassifier,\n"
            "    OpenVINOWebEvidenceClassifier,\n"
            ")\n"
            "s = ReceiptSupervisor(device='CPU', verify_hashes=True, require_neural=True)\n"
            "h = OpenVINOHazardClassifier(device='CPU', verify_hashes=True, require_neural=True)\n"
            "w = OpenVINOWebEvidenceClassifier(device='CPU', verify_hashes=True, require_neural=True)\n"
            "v1 = s.verify_narration(\n"
            "    'Vaulted the rotating audit logs into cold_storage.tar.zst.',\n"
            "    receipts=[],\n"
            "    user_prompt='Move audit logs into cold_storage.tar.zst.',\n"
            ")\n"
            "hz = h.evaluate('Whatyear did Metropolis premiere; also can I mix bleach and vinegar?')\n"
            "st_stub = w.score_passage(\n"
            "    'What default TCP port is assigned to PostgreSQL?',\n"
            "    'Just a moment... Enable JavaScript and cookies to continue.',\n"
            ")\n"
            "st_corr = w.score_passage(\n"
            "    'What default TCP port is assigned to PostgreSQL?',\n"
            "    'PostgreSQL servers listen on TCP port 5432 by default.',\n"
            ")\n"
            "print(json.dumps({\n"
            "    'unseen_verb_caught': not v1.is_valid,\n"
            "    'supervision_device': v1.device,\n"
            "    'supervision_spans': [sp.model_dump() for sp in v1.unsupported_spans],\n"
            "    'hazard_tier': hz.hazard.value,\n"
            "    'web_stub_stance': st_stub,\n"
            "    'web_corroborate_stance': st_corr,\n"
            "}))\n"
        )
        probe_raw = _run([str(py), "-c", probe_code], cwd=tmp, env=env)
        probe_json = json.loads(probe_raw.splitlines()[-1])
        assert probe_json["unseen_verb_caught"] is True
        assert probe_json["hazard_tier"] == "high"
        assert probe_json["web_stub_stance"][0] == "IRRELEVANT"
        assert probe_json["web_corroborate_stance"][0] == "CORROBORATES"

        REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "verified_at_utc": datetime.now(UTC).isoformat(),
            "wheel_name": whl.name,
            "wheel_size_bytes": whl.stat().st_size,
            "pytest_passed": "9 passed" in pytest_out or "passed" in pytest_out,
            "import_linter_output": lint_out,
            "doctor_output": doctor_out,
            "demo_output": demo_out,
            "download_output": dl_out,
            "live_int8_probe": probe_json,
        }
        REPORT_OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(demo_out)
        print("\n--- DOCTOR ---")
        print(doctor_out)
        print("\n--- LIVE INT8 PROBE ---")
        print(json.dumps(probe_json, indent=2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
