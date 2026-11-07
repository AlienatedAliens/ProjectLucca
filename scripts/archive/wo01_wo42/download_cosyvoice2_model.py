import os
import truststore
truststore.inject_into_ssl()

from huggingface_hub import snapshot_download

target_dir = r"C:\ProjectLucca\app\CosyVoice\pretrained_models\CosyVoice2-0.5B"
os.makedirs(target_dir, exist_ok=True)

print(f"Downloading FunAudioLLM/CosyVoice2-0.5B to {target_dir}...")
snapshot_download(
    repo_id="FunAudioLLM/CosyVoice2-0.5B",
    local_dir=target_dir,
)
print(f"CosyVoice2-0.5B download complete!")
