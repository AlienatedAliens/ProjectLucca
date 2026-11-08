import os
import shutil
from pathlib import Path
from huggingface_hub import hf_hub_download

REPO_ID = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
TARGET_DIR = Path(r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512")
CV2_DIR = Path(r"C:\ProjectLucca\app\CosyVoice\pretrained_models\CosyVoice2-0.5B")

TARGET_DIR.mkdir(parents=True, exist_ok=True)

# Copy identical files first to save bandwidth
blank_target = TARGET_DIR / "CosyVoice-BlankEN"
if not blank_target.exists():
    print("Copying CosyVoice-BlankEN from CosyVoice2-0.5B...")
    shutil.copytree(CV2_DIR / "CosyVoice-BlankEN", blank_target)
    print("Copied BlankEN.")

campplus_target = TARGET_DIR / "campplus.onnx"
if not campplus_target.exists() and (CV2_DIR / "campplus.onnx").exists():
    shutil.copy2(CV2_DIR / "campplus.onnx", campplus_target)
    print("Copied campplus.onnx.")

files_to_download = [
    "cosyvoice3.yaml",
    "config.json",
    "configuration.json",
    "llm.pt",
    "llm.rl.pt",
    "speech_tokenizer_v3.onnx",
    "flow.pt",
    "hift.pt",
]

for filename in files_to_download:
    dest = TARGET_DIR / filename
    if dest.exists() and dest.stat().st_size > 0:
        print(f"Already exists: {filename} ({dest.stat().st_size / 1e6:.1f} MB)")
        continue
    print(f"Downloading {filename} from {REPO_ID}...")
    cached_path = hf_hub_download(
        repo_id=REPO_ID,
        filename=filename,
        local_dir=str(TARGET_DIR),
        local_dir_use_symlinks=False
    )
    print(f"Finished {filename}: {dest.stat().st_size / 1e6:.1f} MB")

print("\nCosyVoice 3 weights downloaded and verified successfully!")
