"""OpenVINO INT8 model discovery, SHA-256 integrity verification, and `download_models()`."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from epistemic_guard.exceptions import EpistemicModelUnavailableWarning, ModelIntegrityError

MODEL_PACK_VERSION: Final[str] = "v0.3.0"
DEFAULT_RELEASE_BASE_URL: Final[str] = (
    "https://github.com/AlienatedAliens/ProjectLucca/releases/download/"
    f"epistemic-guard-models-{MODEL_PACK_VERSION}"
)


@dataclass(frozen=True)
class ModelSpec:
    """Metadata and SHA-256 file pins for an `epistemic-guard` OpenVINO INT8 model."""

    key: str
    subdir: str
    archive_name: str
    env_var: str
    legacy_subdirs: tuple[str, ...]
    upstream_base_model: str
    upstream_license: str
    total_size_mb: float
    files_sha256: dict[str, str]


MODEL_SPECS: Final[dict[str, ModelSpec]] = {
    "action_claim": ModelSpec(
        key="action_claim",
        subdir="action_claim_int8",
        archive_name="action_claim_int8.tar.gz",
        env_var="EPISTEMIC_GUARD_ACTION_CLAIM_DIR",
        legacy_subdirs=("action_claim_verifier_ov",),
        upstream_base_model="cross-encoder/nli-MiniLM2-L6-H768",
        upstream_license="Apache-2.0",
        total_size_mb=82.67,
        files_sha256={
            "config.json": "2bee00800915393a488790cf4f59a844456f3b6026789564649503e5fbb018a4",
            "openvino_model.bin": (
                "2a4b03c49961495270e4ded86144d52ab9b94f18653cbaf127f0be032676a7f0"
            ),
            "openvino_model.xml": (
                "826b60f56148dbbd6daf0cde4d48074a7a9c7028dafe6425559fafefce9b25e5"
            ),
            "tokenizer.json": "f7eb98e28291c70cc66f5e26c9598c0111e34be81517e48d4b8de84d125c70eb",
        },
    ),
    "hazard": ModelSpec(
        key="hazard",
        subdir="hazard_int8",
        archive_name="hazard_int8.tar.gz",
        env_var="EPISTEMIC_GUARD_HAZARD_DIR",
        legacy_subdirs=("proof_policy_hazard_v3_ov", "proof_policy_hazard_ov"),
        upstream_base_model="cross-encoder/nli-MiniLM2-L6-H768",
        upstream_license="Apache-2.0",
        total_size_mb=82.65,
        files_sha256={
            "config.json": "4dfb4f482675e6b2031e5dd3cfff40ea88d14faa34d9a57db78db49a27406535",
            "openvino_model.bin": (
                "07ed2ed3d4fafdc35a565951473beb910f37c83fc2531005f581f54c4d52dbf5"
            ),
            "openvino_model.xml": (
                "491d9ed02a68e8583fad322a456557dfd44b822b051955a1fffb1f1503e0031e"
            ),
            "tokenizer.json": "52bb0ea36f84a9b5440aaed69b35f9f7d3f895084f074b07fc21edb071015a92",
        },
    ),
    "web_evidence": ModelSpec(
        key="web_evidence",
        subdir="web_evidence_int8",
        archive_name="web_evidence_int8.tar.gz",
        env_var="EPISTEMIC_GUARD_WEB_EVIDENCE_DIR",
        legacy_subdirs=(),
        upstream_base_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        upstream_license="Apache-2.0",
        total_size_mb=23.06,
        files_sha256={
            "config.json": "74894cc751049a4c6e995781e2cc1bedccb4101f99f2f7ab77657e08624126b2",
            "openvino_model.bin": (
                "ab4433633b523c4f93b17f9a69ad0cfb6311e61b589524c43c20f244730151a9"
            ),
            "openvino_model.xml": (
                "1a433cbc4d6daa563e44a689715fb80342b1cba1f3dd7583c139bd0b4758ad8c"
            ),
            "tokenizer.json": "f83a7f24eee69f73e1a5cad5a09dac6e3c6731c461540cb3498b22285d3ca6ed",
        },
    ),
}


def default_cache_root() -> Path:
    """Return OS-appropriate user cache directory for `epistemic-guard` INT8 models."""
    override = os.environ.get("EPISTEMIC_GUARD_MODEL_DIR")
    if override:
        return Path(override)
    if platform.system() == "Windows":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            return Path(local_app) / "epistemic-guard" / "models" / MODEL_PACK_VERSION
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".cache")
    return base / "epistemic-guard" / "models" / MODEL_PACK_VERSION


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_model_dir(model_dir: Path, expected_sha256: dict[str, str]) -> bool:
    """Verify every required file in `model_dir` against its pinned SHA-256 digest."""
    for fname, exp_hash in expected_sha256.items():
        fpath = model_dir / fname
        if not fpath.exists():
            raise ModelIntegrityError(f"Missing required model file: {fpath}")
        actual = _sha256_file(fpath)
        if actual != exp_hash:
            raise ModelIntegrityError(
                f"SHA-256 mismatch for {fpath}: expected {exp_hash}, got {actual}"
            )
    return True


def resolve_managed_model_dir(
    model_key: str,
    explicit_dir: Path | str | None = None,
    *,
    verify_hashes: bool = False,
    require_neural: bool = False,
    warn_on_missing: bool = True,
) -> Path | None:
    """Locate an OpenVINO model directory, warning or raising explicitly when absent."""
    spec = MODEL_SPECS[model_key]

    if explicit_dir is not None:
        p = Path(explicit_dir)
        if (p / "openvino_model.xml").exists() and (p / "tokenizer.json").exists():
            if verify_hashes and p.name == spec.subdir:
                verify_model_dir(p, spec.files_sha256)
            return p
        if require_neural:
            raise ModelIntegrityError(f"Explicit model_dir '{p}' does not contain OpenVINO IR.")
        if warn_on_missing:
            warnings.warn(
                f"Model '{model_key}' not found at '{p}'; falling back to deterministic CPU rules. "
                "Run `epistemic_guard.download_models()` to install INT8 OpenVINO weights.",
                EpistemicModelUnavailableWarning,
                stacklevel=3,
            )
        return None

    env_specific = os.environ.get(spec.env_var)
    candidates: list[Path] = []
    if env_specific:
        candidates.append(Path(env_specific))

    cache_root = default_cache_root()
    candidates.append(cache_root / spec.subdir)

    # Local ProjectLucca monorepo development roots (INT8 first, then legacy FP16)
    repo_guess = Path(__file__).resolve().parents[4]
    for base in (Path.cwd(), repo_guess, Path(r"C:\ProjectLucca")):
        candidates.append(base / "models" / "epistemic_guard_int8" / spec.subdir)
        for leg in spec.legacy_subdirs:
            candidates.append(base / "models" / leg)

    for cand in candidates:
        if (cand / "openvino_model.xml").exists() and (cand / "tokenizer.json").exists():
            if verify_hashes and cand.name == spec.subdir:
                verify_model_dir(cand, spec.files_sha256)
            return cand

    if require_neural:
        raise ModelIntegrityError(
            f"OpenVINO INT8 weights for '{model_key}' are not installed. "
            "Run `epistemic_guard.download_models()` or `epistemic-guard download-models`."
        )
    if warn_on_missing:
        warnings.warn(
            f"OpenVINO INT8 weights for '{model_key}' are not installed; deterministic CPU rules "
            "are active (lower recall on unseen phrasing). Run `epistemic_guard.download_models()` "
            "or pass `warn_on_missing=False` when deterministic-only mode is intentional.",
            EpistemicModelUnavailableWarning,
            stacklevel=3,
        )
    return None


def _safe_extract_tar(tar: tarfile.TarFile, dest: Path) -> None:
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        member_target = (dest / member.name).resolve()
        if not str(member_target).startswith(str(dest_resolved)):
            raise ModelIntegrityError(f"Unsafe path in model archive: {member.name}")
    tar.extractall(path=dest, filter="data")


def download_models(
    models: tuple[str, ...] | list[str] = ("action_claim", "hazard", "web_evidence"),
    *,
    cache_dir: Path | str | None = None,
    base_url: str | None = None,
    force: bool = False,
) -> dict[str, Path]:
    """Download and SHA-256-verify OpenVINO INT8 model archives into the local cache."""
    target_root = Path(cache_dir) if cache_dir is not None else default_cache_root()
    target_root.mkdir(parents=True, exist_ok=True)
    resolved_base = (
        base_url
        or os.environ.get("EPISTEMIC_GUARD_MODEL_BASE_URL")
        or DEFAULT_RELEASE_BASE_URL
    ).rstrip("/")

    installed: dict[str, Path] = {}
    for key in models:
        if key not in MODEL_SPECS:
            raise ValueError(f"Unknown model key '{key}'. Expected one of {tuple(MODEL_SPECS)}.")
        spec = MODEL_SPECS[key]
        dest_dir = target_root / spec.subdir

        if not force and dest_dir.exists():
            try:
                verify_model_dir(dest_dir, spec.files_sha256)
                installed[key] = dest_dir
                continue
            except ModelIntegrityError:
                shutil.rmtree(dest_dir, ignore_errors=True)

        url = f"{resolved_base}/{spec.archive_name}"
        with tempfile.TemporaryDirectory(prefix=f"eg_{key}_") as tmp:
            tmp_path = Path(tmp)
            archive_path = tmp_path / spec.archive_name
            try:
                with (
                    urllib.request.urlopen(url, timeout=120) as resp,  # noqa: S310
                    archive_path.open("wb") as out,
                ):
                    shutil.copyfileobj(resp, out)
            except Exception as exc:
                raise ModelIntegrityError(
                    f"Failed to download '{key}' model archive from {url}: {exc}"
                ) from exc

            extract_dir = tmp_path / "extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                with tarfile.open(archive_path, mode="r:gz") as tf:
                    _safe_extract_tar(tf, extract_dir)
            except Exception as exc:
                raise ModelIntegrityError(f"Invalid tar.gz archive for '{key}': {exc}") from exc

            sub_cand = extract_dir / spec.subdir
            cand = sub_cand if sub_cand.is_dir() else extract_dir
            verify_model_dir(cand, spec.files_sha256)
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.move(str(cand), str(dest_dir))
            installed[key] = dest_dir

    return installed
