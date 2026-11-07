import os
import sys
import time
from pathlib import Path
import soundfile as sf
import torch
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

COSYVOICE_DIR = Path(r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, str(COSYVOICE_DIR))
sys.path.insert(0, str(COSYVOICE_DIR / "third_party" / "Matcha-TTS"))

from cosyvoice.cli.cosyvoice import CosyVoice3

def main():
    model_dir = r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512"
    cv3 = CosyVoice3(model_dir, fp16=True)
    ref_wav = r"C:\ProjectLucca\app\CosyVoice\asset\cross_lingual_prompt.wav"
    instruct = "You are a helpful assistant.<|endofprompt|>"
    text = "Testing real-time streaming audio generation on CosyVoice 3."

    print("Starting streaming synthesis...")
    t0 = time.perf_counter()
    ttfa = None
    chunks = []
    for c in cv3.inference_instruct2(text, instruct, prompt_wav=ref_wav, stream=True, speed=1.0):
        chunk_audio = c["tts_speech"].squeeze().cpu().numpy()
        chunks.append(chunk_audio)
        if ttfa is None:
            ttfa = (time.perf_counter() - t0) * 1000
            print(f"TTFA: {ttfa:.1f}ms (First chunk duration: {len(chunk_audio)/24000:.2f}s)")
    
    total_ms = (time.perf_counter() - t0) * 1000
    print(f"Total chunks: {len(chunks)}, Total generation time: {total_ms:.1f}ms")
    full_audio = np.concatenate(chunks)
    print(f"Total audio length: {len(full_audio)/24000:.2f}s")

if __name__ == "__main__":
    main()
