"""
Project Lucca — LLM Server Control & GGUF Model Registry
Spec 02, Spec 08, ADR-001
Provides strictly-typed server process orchestration (start/stop/restart/health)
and GGUF binary header metadata inspection.
"""

import hashlib
import io
import json
import logging
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import psutil

from lucca.core.config import LLMSettings
from lucca.core.schemas import ModelRegistryEntry

logger = logging.getLogger(__name__)



@dataclass
class GGUFMetadata:
    magic: str
    version: int
    tensor_count: int
    kv_count: int
    architecture: str
    name: str
    quantization: str
    file_size_bytes: int
    is_valid_gguf: bool


def parse_gguf_file(path: Path) -> GGUFMetadata:
    """Parses binary GGUF header key-value pairs from a file on disk."""
    if not path.exists() or not path.is_file():
        return GGUFMetadata(
            magic="",
            version=0,
            tensor_count=0,
            kv_count=0,
            architecture="unknown",
            name=path.name,
            quantization=_derive_quant_from_filename(path.name),
            file_size_bytes=0,
            is_valid_gguf=False,
        )

    file_size = path.stat().st_size
    try:
        with open(path, "rb") as f:
            magic_bytes = f.read(4)
            if magic_bytes != b"GGUF":
                return GGUFMetadata(
                    magic=magic_bytes.decode("latin1", errors="replace"),
                    version=0,
                    tensor_count=0,
                    kv_count=0,
                    architecture="unknown",
                    name=path.name,
                    quantization=_derive_quant_from_filename(path.name),
                    file_size_bytes=file_size,
                    is_valid_gguf=False,
                )

            version = struct.unpack("<I", f.read(4))[0]
            tensor_count = struct.unpack("<Q", f.read(8))[0]
            kv_count = struct.unpack("<Q", f.read(8))[0]

            metadata: dict[str, str] = {}

            def read_str() -> str:
                s_len = struct.unpack("<Q", f.read(8))[0]
                if s_len > 10000:
                    return ""
                raw = f.read(s_len)
                return raw.decode("utf-8", errors="replace")

            # Read key-values up to kv_count or max 128 keys
            max_keys = min(kv_count, 128)
            for _ in range(max_keys):
                try:
                    key = read_str()
                    if not key:
                        break
                    val_type = struct.unpack("<I", f.read(4))[0]
                    if val_type == 8:  # string
                        metadata[key] = read_str()
                    elif val_type in (0, 1):  # uint8, int8, bool
                        v = struct.unpack("<b", f.read(1))[0]
                        metadata[key] = str(v)
                    elif val_type in (2, 3):  # uint16, int16
                        v = struct.unpack("<h", f.read(2))[0]
                        metadata[key] = str(v)
                    elif val_type in (4, 5):  # uint32, int32
                        v = struct.unpack("<i", f.read(4))[0]
                        metadata[key] = str(v)
                    elif val_type == 6:  # float32
                        v = struct.unpack("<f", f.read(4))[0]
                        metadata[key] = str(v)
                    elif val_type == 7:  # bool
                        v = struct.unpack("<?", f.read(1))[0]
                        metadata[key] = str(v)
                    elif val_type in (10, 11):  # uint64, int64
                        v = struct.unpack("<q", f.read(8))[0]
                        metadata[key] = str(v)
                    elif val_type == 12:  # float64
                        v = struct.unpack("<d", f.read(8))[0]
                        metadata[key] = str(v)
                    elif val_type == 9:  # ARRAY
                        arr_type = struct.unpack("<I", f.read(4))[0]
                        arr_len = struct.unpack("<Q", f.read(8))[0]
                        if arr_type == 8:
                            for _ in range(min(arr_len, 256)):
                                read_str()
                        elif arr_type in (0, 1, 7):
                            f.seek(arr_len * 1, io.SEEK_CUR)
                        elif arr_type in (2, 3):
                            f.seek(arr_len * 2, io.SEEK_CUR)
                        elif arr_type in (4, 5, 6):
                            f.seek(arr_len * 4, io.SEEK_CUR)
                        elif arr_type in (10, 11, 12):
                            f.seek(arr_len * 8, io.SEEK_CUR)
                    else:
                        break
                except Exception as exc:  # noqa: BLE001
                    logger.debug("parse_gguf_kv_failed: %s", exc)
                    break

            arch = metadata.get("general.architecture", "llama")
            name = metadata.get("general.name", path.stem)
            quant = metadata.get("general.quantization_version", "")
            if not quant or quant == "0":
                quant = _derive_quant_from_filename(path.name)

            return GGUFMetadata(
                magic="GGUF",
                version=version,
                tensor_count=tensor_count,
                kv_count=kv_count,
                architecture=arch,
                name=name,
                quantization=quant,
                file_size_bytes=file_size,
                is_valid_gguf=True,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("parse_gguf_file_failed: %s", exc)
        return GGUFMetadata(
            magic="GGUF",
            version=0,
            tensor_count=0,
            kv_count=0,
            architecture="unknown",
            name=path.name,
            quantization=_derive_quant_from_filename(path.name),
            file_size_bytes=file_size,
            is_valid_gguf=True,
        )


def _derive_quant_from_filename(filename: str) -> str:
    parts = filename.replace(".gguf", "").split("-")
    for part in reversed(parts):
        if part.upper().startswith("Q") or part.upper() in ("FP16", "FP32", "BF16", "F16", "F32"):
            return part.upper()
    return "UNKNOWN"


def scan_model_registry(models_dir: Path, active_model_rel: str = "") -> list[ModelRegistryEntry]:
    """
    Scans models_dir for all *.gguf files, extracts GGUF metadata,
    and assigns binary audio compatibility badges.
    """
    registry: list[ModelRegistryEntry] = []
    if not models_dir.exists():
        return registry

    gguf_files = sorted(models_dir.glob("*.gguf"))
    all_names = {f.name for f in gguf_files}

    for path in gguf_files:
        # Skip projectors from the primary model listing (they are paired)
        if "mmproj" in path.name.lower():
            continue

        meta = parse_gguf_file(path)
        size_gb = meta.file_size_bytes / (1024**3)

        # Check audio compatibility badge
        # Check if an mmproj file exists that matches this model
        paired_mmproj: Path | None = None
        for cand_name in all_names:
            if "mmproj" in cand_name.lower():
                # Prefer model-specific match
                if "gemma" in path.name.lower() and "gemma" in cand_name.lower():
                    paired_mmproj = models_dir / cand_name
                    break
                if "ultravox" in path.name.lower() and "ultravox" in cand_name.lower():
                    paired_mmproj = models_dir / cand_name
                    break
                if paired_mmproj is None:
                    paired_mmproj = models_dir / cand_name

        is_audio_model = "ultravox" in path.name.lower() or "audio" in path.name.lower()
        is_vision_model = "gemma-4" in path.name.lower() or "vision" in path.name.lower()

        if is_audio_model and paired_mmproj is not None and paired_mmproj.exists():
            badge = "🎙 Audio-Native"
            badge_type = "audio"
        elif is_vision_model and paired_mmproj is not None and paired_mmproj.exists():
            badge = "👁️ Vision-Ready (mmproj)"
            badge_type = "vision"
        elif is_audio_model:
            badge = "⚠ mmproj required"
            badge_type = "missing_mmproj"
        elif is_vision_model:
            badge = "👁️ Vision-Capable (mmproj optional)"
            badge_type = "vision_optional"
        else:
            badge = "📄 Text via Whisper"
            badge_type = "transcript"

        rel_path = f"llm/{path.name}"
        is_active = (
            rel_path == active_model_rel
            or path.name in active_model_rel
            or (not active_model_rel and "ultravox" in path.name.lower())
        )

        registry.append(
            ModelRegistryEntry(
                path=path,
                filename=path.name,
                rel_path=rel_path,
                name=meta.name,
                architecture=meta.architecture,
                quantization=meta.quantization,
                size_gb=size_gb,
                tensor_count=meta.tensor_count,
                badge=badge,
                badge_type=badge_type,
                is_active=is_active,
                paired_mmproj=paired_mmproj,
            )
        )

    return registry


def resolve_model_path(rel_or_abs: str | Path, home_dir: Path) -> Path:
    """Resolves a model path robustly against home_dir, models/ subfolder, or absolute path."""
    p = Path(rel_or_abs)
    if p.is_absolute() and p.exists():
        return p
    for cand in [
        home_dir / "models" / p,
        home_dir / p,
        home_dir / "models" / "llm" / p.name,
    ]:
        if cand.exists():
            return cand
    return home_dir / "models" / p


def resolve_server_bin(cfg: LLMSettings, home_dir: Path) -> Path:
    """Resolves the llama-server binary from config (absolute, or relative to LUCCA_HOME)."""
    p = Path(cfg.server_bin)
    return p if p.is_absolute() else home_dir / p


def resolve_template_file(cfg: LLMSettings, home_dir: Path) -> Path | None:
    """
    Resolves cfg.chat_template_file against LUCCA_HOME, then the repo root.
    Returns None when unset or when no candidate exists (caller falls back to
    cfg.chat_template, then to the GGUF-embedded template).
    """
    if not cfg.chat_template_file:
        return None
    p = Path(cfg.chat_template_file)
    if p.is_absolute():
        return p if p.exists() else None
    repo_root = Path(__file__).resolve().parents[3]
    for cand in (home_dir / p, repo_root / p):
        if cand.exists():
            return cand
    return None


def build_launch_command(cfg: LLMSettings, home_dir: Path) -> list[str]:
    """
    Constructs the native llama-server CLI invocation command purely from LLMSettings.
    No model-name sniffing: binary, template, and thinking behaviour are all config.
    """
    llama_exe = resolve_server_bin(cfg, home_dir)
    model_gguf = resolve_model_path(cfg.model, home_dir)
    mmproj_gguf = resolve_model_path(cfg.mmproj, home_dir)

    cmd = [
        str(llama_exe),
        "--model",
        str(model_gguf),
        "--n-gpu-layers",
        "99",
        "--ctx-size",
        str(cfg.ctx),
        "--cache-type-k",
        cfg.kv_type,
        "--cache-type-v",
        cfg.kv_type,
        "--cache-ram",
        str(cfg.cache_ram_mib),
        "--parallel",
        "1",
        "--flash-attn",
        "on",
        "--host",
        cfg.host,
        "--port",
        str(cfg.port),
        "--no-webui",
        "--jinja",
    ]

    template_file = resolve_template_file(cfg, home_dir)
    if template_file is not None:
        cmd.extend(["--chat-template-file", str(template_file)])
    elif cfg.chat_template:
        cmd.extend(["--chat-template", cfg.chat_template])
    # else: rely on the template embedded in the GGUF (--jinja already set)

    # Multimodal projector matching:
    # Only attach --mmproj in audio or vision mode, and ensure architectural compatibility
    # (e.g. Gemma 4 models n_embd=3840 must NEVER load LLaMA Ultravox n_embd=4096 mmproj)
    matched_mmproj: Path | None = None
    if cfg.mode in ("audio", "vision"):
        if "gemma" in model_gguf.name.lower():
            if mmproj_gguf.exists() and "gemma" in mmproj_gguf.name.lower():
                matched_mmproj = mmproj_gguf
            else:
                models_dir = home_dir / "models" / "llm"
                if models_dir.exists():
                    for p in models_dir.glob("*gemma*mmproj*.gguf"):
                        matched_mmproj = p
                        break
                    if not matched_mmproj:
                        for p in models_dir.glob("*mmproj*gemma*.gguf"):
                            matched_mmproj = p
                            break
        elif "ultravox" in model_gguf.name.lower() or "llama" in model_gguf.name.lower():
            if mmproj_gguf.exists() and ("ultravox" in mmproj_gguf.name.lower() or "llama" in mmproj_gguf.name.lower()):
                matched_mmproj = mmproj_gguf
        elif mmproj_gguf.exists():
            matched_mmproj = mmproj_gguf

    if matched_mmproj is not None and matched_mmproj.exists():
        cmd.extend(["--mmproj", str(matched_mmproj)])

    return cmd


def check_server_status(
    host: str, port: int, timeout: float = 1.0
) -> Literal["ready", "loading", "offline"]:
    """Queries GET /health to check if llama-server is ready, loading, or offline."""
    url = f"http://{host}:{port}/health"
    try:
        r = httpx.get(url, timeout=timeout)
        if r.status_code == 200:
            return "ready"
        if r.status_code == 503:
            return "loading"
        return "loading"
    except (httpx.HTTPError, OSError):
        return "offline"


def is_healthy(host: str, port: int, timeout: float = 1.0) -> bool:
    """Queries GET /health on the active llama-server."""
    return check_server_status(host, port, timeout=timeout) == "ready"


def compute_sha256(path: Path) -> str:
    """Computes SHA256 hex digest of a file in 1 MiB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verify_model_files(cfg: LLMSettings, home_dir: Path) -> None:
    """
    Cryptographically verifies that required model weights match the sha256 manifest.
    Checks home_dir/models/MANIFEST.json (falling back to repository models/MANIFEST.json).
    Raises FileNotFoundError if manifest or any model file is missing.
    Raises RuntimeError if a sha256 checksum mismatch is detected.
    """
    manifest_path = home_dir / "models" / "MANIFEST.json"
    if not manifest_path.exists():
        repo_manifest = Path(__file__).resolve().parents[3] / "models" / "MANIFEST.json"
        if repo_manifest.exists():
            manifest_path = repo_manifest
        else:
            raise FileNotFoundError(f"Model manifest not found at: {manifest_path}")

    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load manifest at {manifest_path}: {e}") from e

    files_map = data.get("files", {})
    if not isinstance(files_map, dict):
        raise RuntimeError(
            f"Invalid manifest format in {manifest_path}: 'files' key must be a dict"
        )

    models_to_check: list[Path] = [resolve_model_path(cfg.model, home_dir)]
    if cfg.mode == "audio" and cfg.mmproj:
        mmproj_path = resolve_model_path(cfg.mmproj, home_dir)
        if mmproj_path.exists() or cfg.mode == "audio":
            models_to_check.append(mmproj_path)

    for mpath in models_to_check:
        if not mpath.exists():
            raise FileNotFoundError(f"Model file not found: {mpath}")

        expected_sha: str | None = None
        try:
            rel = str(mpath.relative_to(home_dir / "models")).replace("\\", "/")
        except ValueError:
            rel = mpath.name

        entry = files_map.get(rel)
        if entry is None:
            for k, v in files_map.items():
                if k == rel or Path(k).name == mpath.name:
                    entry = v
                    break

        if entry is None:
            raise RuntimeError(
                f"Model file '{mpath.name}' has no entry in manifest {manifest_path}"
            )

        if isinstance(entry, dict):
            sha_val = entry.get("sha256")
            if isinstance(sha_val, str):
                expected_sha = sha_val
        elif isinstance(entry, str):
            expected_sha = entry

        if not expected_sha:
            raise RuntimeError(f"No sha256 hash specified for '{mpath.name}' in manifest")

        actual_sha = compute_sha256(mpath)
        if actual_sha.lower() != expected_sha.lower():
            raise RuntimeError(
                f"Model hash mismatch for {mpath.name}: expected {expected_sha}, got {actual_sha}"
            )


def start_server(cfg: LLMSettings, home_dir: Path) -> subprocess.Popen[bytes]:
    """
    Starts llama-server as a child process.
    Raises if executable, model, or verification fails.
    """
    llama_exe = resolve_server_bin(cfg, home_dir)
    if not llama_exe.exists():
        raise FileNotFoundError(f"llama-server executable not found at: {llama_exe}")

    model_gguf = resolve_model_path(cfg.model, home_dir)
    if not model_gguf.exists():
        raise FileNotFoundError(f"Model GGUF file not found at: {model_gguf}")

    verify_model_files(cfg, home_dir)

    cmd = build_launch_command(cfg, home_dir)
    log_file = home_dir / "logs" / "llama-server.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fp = open(log_file, "wb")
    return subprocess.Popen(  # noqa: S603
        cmd,
        stdout=fp,
        stderr=subprocess.STDOUT,
    )


def stop_server(
    host: str,
    port: int,
    proc: subprocess.Popen[bytes] | None = None,
) -> None:
    """Gracefully terminates active llama-server process and kills if unresponsive."""
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3.0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("proc_terminate_failed: %s", exc)
            try:
                proc.kill()
            except Exception as exc2:  # noqa: BLE001, S110
                logger.debug("proc_kill_failed: %s", exc2)

    # Terminate any lingering llama-server process on Windows
    try:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = p.info.get("name") or ""
                if "llama-server" in name.lower():
                    p.terminate()
                    try:
                        p.wait(timeout=2.0)
                    except psutil.TimeoutExpired:
                        p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as exc:  # noqa: BLE001, S110
        logger.debug("psutil_process_iter_failed: %s", exc)
