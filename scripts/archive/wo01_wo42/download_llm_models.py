import hashlib
import json
import os
import sys
import time
from pathlib import Path

from huggingface_hub import hf_hub_download

try:
    import certifi

    if "SSL_CERT_FILE" not in os.environ:
        os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

dest_dir = Path(r"C:\ProjectLucca\models\llm")
dest_dir.mkdir(parents=True, exist_ok=True)

manifest_path = Path(r"C:\ProjectLucca\models\MANIFEST.json")
if not manifest_path.exists():
    manifest_path = Path(__file__).resolve().parent.parent / "models" / "MANIFEST.json"

manifest: dict[str, object] = {}
if manifest_path.exists():
    with open(manifest_path, encoding="utf-8") as f:
        raw = json.load(f)
        manifest = raw.get("files", {})


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verify_hash_or_exit(target: Path, manifest_key: str) -> None:
    entry = manifest.get(manifest_key)
    if not entry:
        print(f"[WARN] No manifest entry found for {manifest_key}, skipping sha256 check.")
        return
    expected_sha = entry.get("sha256") if isinstance(entry, dict) else entry
    if not isinstance(expected_sha, str):
        print(f"[WARN] No sha256 string found for {manifest_key}.")
        return
    print(f"Verifying sha256 for {target.name}...")
    actual_sha = compute_sha256(target)
    if actual_sha.lower() != expected_sha.lower():
        print(f"[ERROR] SHA256 mismatch for {target.name}!")
        print(f"  Expected: {expected_sha}")
        print(f"  Actual:   {actual_sha}")
        if target.exists():
            target.unlink()
            print(f"[CLEANUP] Deleted corrupted file: {target}")
        sys.exit(1)
    print(f"[OK] SHA256 verified for {target.name}: {actual_sha[:16]}...")


# 1. Projector & Ultravox Backbone
target_choice = sys.argv[1] if len(sys.argv) > 1 else "all"

if target_choice in ("ultravox", "all"):
    mmproj_target = dest_dir / "mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf"
    if not mmproj_target.exists():
        print("Downloading Ultravox mmproj...")
        t0 = time.time()
        hf_hub_download(
            repo_id="ggml-org/ultravox-v0_5-llama-3_1-8b-GGUF",
            filename="mmproj-ultravox-v0_5-llama-3_1-8b-f16.gguf",
            local_dir=str(dest_dir),
        )
        downloaded_file = dest_dir / "mmproj-ultravox-v0_5-llama-3_1-8b-f16.gguf"
        if downloaded_file.exists() and downloaded_file != mmproj_target:
            downloaded_file.rename(mmproj_target)
        print(
            f"Downloaded mmproj in {time.time() - t0:.1f}s: {mmproj_target.stat().st_size / (1024 * 1024):.1f} MB"
        )
    else:
        print(f"mmproj already exists: {mmproj_target.stat().st_size / (1024 * 1024):.1f} MB")

    verify_hash_or_exit(mmproj_target, "llm/mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf")

    # Q6_K Backbone
    backbone_target = dest_dir / "ultravox-v0_5-llama-3_1-8b-Q6_K.gguf"
    if not backbone_target.exists():
        print("Downloading Meta-Llama-3.1-8B-Instruct-Q6_K.gguf...")
        t0 = time.time()
        hf_hub_download(
            repo_id="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
            filename="Meta-Llama-3.1-8B-Instruct-Q6_K.gguf",
            local_dir=str(dest_dir),
        )
        downloaded_file = dest_dir / "Meta-Llama-3.1-8B-Instruct-Q6_K.gguf"
        if downloaded_file.exists() and downloaded_file != backbone_target:
            downloaded_file.rename(backbone_target)
        print(
            f"Downloaded backbone in {time.time() - t0:.1f}s: {backbone_target.stat().st_size / (1024 * 1024):.1f} MB"
        )
    else:
        print(f"Backbone already exists: {backbone_target.stat().st_size / (1024 * 1024):.1f} MB")

    verify_hash_or_exit(backbone_target, "llm/ultravox-v0_5-llama-3_1-8b-Q6_K.gguf")

# 2. Mistral NeMo 12B Instruct (Cascade Primary Candidate)
if target_choice in ("mistral-nemo", "nemo", "all"):
    nemo_target = dest_dir / "Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
    if not nemo_target.exists():
        print("Downloading Mistral-Nemo-Instruct-2407-Q5_K_M.gguf...")
        t0 = time.time()
        hf_hub_download(
            repo_id="bartowski/Mistral-Nemo-Instruct-2407-GGUF",
            filename="Mistral-Nemo-Instruct-2407-Q5_K_M.gguf",
            local_dir=str(dest_dir),
        )
        print(
            f"Downloaded Mistral-Nemo-12B in {time.time() - t0:.1f}s: {nemo_target.stat().st_size / (1024 * 1024):.1f} MB"
        )
    else:
        print(
            f"Mistral-Nemo-12B already exists: {nemo_target.stat().st_size / (1024 * 1024):.1f} MB"
        )

    verify_hash_or_exit(nemo_target, "llm/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf")

# 3. Mistral NeMo 12B Instruct Abliterated (Uncensored / De-aligned Q6_K)
if target_choice in ("abliterated-nemo", "nemo-abliterated", "abliterated"):
    nemo_abl_target = dest_dir / "Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf"
    if not nemo_abl_target.exists():
        print("Downloading Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf...")
        t0 = time.time()
        hf_hub_download(
            repo_id="QuantFactory/Mistral-Nemo-Instruct-2407-abliterated-GGUF",
            filename="Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf",
            local_dir=str(dest_dir),
        )
        print(
            f"Downloaded Mistral-Nemo-12B Abliterated in {time.time() - t0:.1f}s: {nemo_abl_target.stat().st_size / (1024 * 1024):.1f} MB"
        )
    else:
        print(
            f"Mistral-Nemo-12B Abliterated already exists: {nemo_abl_target.stat().st_size / (1024 * 1024):.1f} MB"
        )

    verify_hash_or_exit(nemo_abl_target, "llm/Mistral-Nemo-Instruct-2407-abliterated.Q6_K.gguf")

print("All requested LLM models verified and ready!")
