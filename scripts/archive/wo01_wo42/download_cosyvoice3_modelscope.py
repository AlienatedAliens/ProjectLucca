import os
from pathlib import Path
from modelscope import snapshot_download

TARGET_DIR = r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512"
print(f"Downloading FunAudioLLM/Fun-CosyVoice3-0.5B-2512 from ModelScope CDN to {TARGET_DIR}...")

model_dir = snapshot_download(
    "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
    local_dir=TARGET_DIR
)

print(f"\nModelScope download finished! Path: {model_dir}")
