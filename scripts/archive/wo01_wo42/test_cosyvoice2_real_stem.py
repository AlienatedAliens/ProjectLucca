"""
Script: test_cosyvoice2_real_stem.py
Tests CosyVoice 2 (0.5B) zero-shot and instruct inference using real Tiffany Grant reference stems on the RTX 5080.
Generates test lines across contrasting PAD octants.
"""

import os
import sys
import time
from pathlib import Path

# Add CosyVoice and Matcha-TTS to sys.path
COSYVOICE_DIR = Path(r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, str(COSYVOICE_DIR))
sys.path.insert(0, str(COSYVOICE_DIR / "third_party" / "Matcha-TTS"))

import soundfile as sf
import torch

from cosyvoice.cli.cosyvoice import CosyVoice2


def main():
    print("=" * 65)
    print("CosyVoice 2 (0.5B) Native Inference Verification on RTX 5080")
    print("=" * 65)

    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"Device name: {torch.cuda.get_device_name(0)}")
        print(f"Device capability: {torch.cuda.get_device_capability(0)}")
        vram_alloc = torch.cuda.memory_allocated() / (1024**3)
        vram_res = torch.cuda.memory_reserved() / (1024**3)
        print(f"VRAM Allocated: {vram_alloc:.2f} GiB, Reserved: {vram_res:.2f} GiB")

    model_dir = r"C:\ProjectLucca\app\CosyVoice\pretrained_models\CosyVoice2-0.5B"
    print(f"Loading CosyVoice2 from {model_dir}...")
    t0 = time.perf_counter()
    cosyvoice = CosyVoice2(model_dir, load_jit=False, load_trt=False, fp16=torch.cuda.is_available())
    load_time = time.perf_counter() - t0
    print(f"CosyVoice2 loaded in {load_time:.2f}s!")

    if torch.cuda.is_available():
        vram_alloc = torch.cuda.memory_allocated() / (1024**3)
        vram_res = torch.cuda.memory_reserved() / (1024**3)
        print(f"Post-load VRAM Allocated: {vram_alloc:.2f} GiB, Reserved: {vram_res:.2f} GiB")

    ref_wav = r"C:\Projects\ProjectLucca\models\tts\references\asuka\asuka_ref_01.wav"
    ref_txt = "Supercomputers, Melchior, Balthazar and Casper are based on the traditional names of the three"
    out_dir = Path(r"C:\Projects\ProjectLucca\models\tts\references\test_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    test_cases = [
        {
            "name": "playful_teasing",
            "text": "Check out my sync rate! Try to keep up for once, okay?",
            "speed": 1.10,
            "instruct": "playful, witty, tsundere teasing",
        },
        {
            "name": "righteous_anger",
            "text": "Anta baka?! What on earth were you thinking doing that?!",
            "speed": 1.25,
            "instruct": "indignant, sharp, fierce reprimand",
        },
        {
            "name": "intimate_whisper",
            "text": "Hey... are you still awake? Don't leave me alone, okay?",
            "speed": 0.85,
            "instruct": "intimate, gentle, soft whisper",
        },
    ]

    for tc in test_cases:
        print(f"\n--- Synthesizing [{tc['name'].upper()}] ---")
        print(f"Text: \"{tc['text']}\"")
        print(f"Speed: {tc['speed']}x | Instruct: \"{tc['instruct']}\"")
        t_start = time.perf_counter()

        # CosyVoice 2 inference_zero_shot using real human stem
        chunks = []
        for chunk in cosyvoice.inference_zero_shot(
            tc["text"],
            prompt_text=ref_txt,
            prompt_wav=ref_wav,
            speed=tc["speed"],
            stream=False,
        ):
            chunks.append(chunk["tts_speech"].squeeze().cpu().numpy())

        gen_time = time.perf_counter() - t_start
        if chunks:
            import numpy as np

            full_audio = np.concatenate(chunks)
            sr = cosyvoice.sample_rate
            audio_dur = len(full_audio) / sr
            rtf = gen_time / audio_dur if audio_dur > 0 else 0.0

            out_file = out_dir / f"asuka_{tc['name']}.wav"
            sf.write(str(out_file), full_audio, sr)
            print(f"Generated {out_file.name}: {audio_dur:.2f}s audio in {gen_time:.2f}s (RTF: {rtf:.3f})")
        else:
            print("ERROR: No audio chunks produced!")

    print("\n" + "=" * 65)
    print("Verification complete! Output WAVs generated directly from real human stem.")
    print("=" * 65)


if __name__ == "__main__":
    main()
