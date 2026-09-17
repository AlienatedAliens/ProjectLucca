import os
import sys
import time
from pathlib import Path

from huggingface_hub import hf_hub_download

dest_dir = Path(r"C:\ProjectLucca\models\llm")
dest_dir.mkdir(parents=True, exist_ok=True)

# 1. Projector
mmproj_target = dest_dir / "mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf"
if not mmproj_target.exists():
    print("Downloading Ultravox mmproj...")
    t0 = time.time()
    p = hf_hub_download(
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

# 2. Q6_K Backbone
backbone_target = dest_dir / "ultravox-v0_5-llama-3_1-8b-Q6_K.gguf"
if not backbone_target.exists():
    print("Downloading Meta-Llama-3.1-8B-Instruct-Q6_K.gguf...")
    t0 = time.time()
    p = hf_hub_download(
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

print("All LLM models ready!")
