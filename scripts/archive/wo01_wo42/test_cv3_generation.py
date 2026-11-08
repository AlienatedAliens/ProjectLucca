import os
import sys
import time
from pathlib import Path
import soundfile as sf
import torch

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

COSYVOICE_DIR = Path(r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, str(COSYVOICE_DIR))
sys.path.insert(0, str(COSYVOICE_DIR / "third_party" / "Matcha-TTS"))

from cosyvoice.cli.cosyvoice import CosyVoice3

def main():
    model_dir = r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512"
    print("Initializing CosyVoice3 on CUDA...")
    t0 = time.perf_counter()
    cv3 = CosyVoice3(model_dir, load_trt=False, fp16=True)
    init_ms = (time.perf_counter() - t0) * 1000
    print(f"CosyVoice3 initialized in {init_ms:.1f}ms")

    # Pick a clean reference prompt
    # Check if there is an expressive English voice stem
    ref_files = list(Path(r"C:\Projects\ProjectLucca\models\tts\references").glob("*.wav"))
    if not ref_files:
        print("No wav references found")
        return
    ref_wav = str(ref_files[0])
    print(f"Using reference wav: {ref_wav}")

    test_text = "All systems operational! The upgraded pipeline is online and ready for our next experiment."
    print(f"Synthesizing: '{test_text}'")

    t1 = time.perf_counter()
    chunks = []
    # Test cross-lingual zero-shot
    for chunk in cv3.inference_cross_lingual(
        test_text,
        prompt_wav=ref_wav,
        stream=False,
        speed=1.0
    ):
        chunks.append(chunk["tts_speech"].squeeze().cpu().numpy())
    
    synth_ms = (time.perf_counter() - t1) * 1000
    print(f"Synthesis completed in {synth_ms:.1f}ms")

    if chunks:
        import numpy as np
        audio = np.concatenate(chunks)
        out_dir = Path(r"C:\Projects\ProjectLucca\models\tts\references\test_output")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "cv3_test_crosslingual.wav"
        sf.write(str(out_path), audio, 24000)
        print(f"Saved {len(audio)} samples ({len(audio)/24000:.2f}s) to {out_path}")

if __name__ == "__main__":
    main()
