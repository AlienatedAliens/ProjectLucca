import os
import sys
import time
from pathlib import Path
from huggingface_hub import hf_hub_download

dest_dir = Path(r"C:\ProjectLucca\models\llm")
dest_dir.mkdir(parents=True, exist_ok=True)

target_filename = "gemma-4-E4B-it-uncensored-heretic-Q6_K.gguf"
target_path = dest_dir / target_filename

if target_path.exists():
    print(f"Target model already exists at {target_path} (size: {target_path.stat().st_size / (1024**3):.2f} GB)")
    sys.exit(0)

print(f"Downloading {target_filename} from llmfan46/gemma-4-E4B-it-uncensored-heretic-GGUF...")
t0 = time.time()
downloaded = hf_hub_download(
    repo_id="llmfan46/gemma-4-E4B-it-uncensored-heretic-GGUF",
    filename=target_filename,
    local_dir=str(dest_dir),
    local_dir_use_symlinks=False
)
elapsed = time.time() - t0
size_gb = target_path.stat().st_size / (1024**3)
print(f"Downloaded {target_filename} successfully in {elapsed:.1f}s ({size_gb:.2f} GB, {size_gb / elapsed * 1024:.1f} MB/s)")
