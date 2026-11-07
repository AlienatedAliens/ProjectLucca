import os
import sys
import time
from pathlib import Path
import soundfile as sf
import torch
import whisper

# Force UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

COSYVOICE_DIR = Path(r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, str(COSYVOICE_DIR))
sys.path.insert(0, str(COSYVOICE_DIR / "third_party" / "Matcha-TTS"))

from cosyvoice.cli.cosyvoice import CosyVoice2

def test_inference():
    print("Loading Whisper base...")
    whisper_model = whisper.load_model("base")

    model_dir = r"C:\ProjectLucca\app\CosyVoice\pretrained_models\CosyVoice2-0.5B"
    print("Loading CosyVoice2 (fp16=False for precise debugging)...")
    cosyvoice = CosyVoice2(model_dir, load_jit=False, load_trt=False, fp16=False)

    # Let's inspect the Qwen2 dtype
    # Notice: Qwen2ForCausalLM is bfloat16, but speech_embedding is float32
    # Let's make sure the whole LLM has consistent dtype:
    cosyvoice.model.llm.llm.model.to(torch.float32)
    print("Converted Qwen2 to float32 for clean unified precision.")

    ref_wav = r"C:\Projects\ProjectLucca\models\tts\references\asuka\asuka_ref_01.wav"
    ref_txt = "Supercomputers, Melchior, Balthazar and Casper are based on the traditional names of the three"
    
    # Test 1: Short prompt matching synthesis length or cross-lingual style
    test_text = "Check out my sync rate! Try to keep up for once, okay?"
    print(f"\n--- Testing synthesis: '{test_text}' ---")
    
    # We will test both zero_shot with prompt_text, and zero_shot with empty prompt_text (cross-lingual style)
    for mode in ["with_prompt_text", "empty_prompt_text"]:
        p_txt = ref_txt if mode == "with_prompt_text" else ""
        print(f"\nMode: {mode} (prompt_text='{p_txt[:30]}...')")
        
        chunks = []
        t0 = time.perf_counter()
        for chunk in cosyvoice.inference_zero_shot(
            test_text,
            prompt_text=p_txt,
            prompt_wav=ref_wav,
            speed=1.0,
            stream=False
        ):
            chunks.append(chunk["tts_speech"].squeeze().cpu().numpy())
        
        dur = time.perf_counter() - t0
        if chunks:
            import numpy as np
            audio = np.concatenate(chunks)
            out_path = Path(r"C:\Projects\ProjectLucca\models\tts\references\test_output") / f"diag_{mode}.wav"
            sf.write(str(out_path), audio, 24000)
            res = whisper_model.transcribe(str(out_path))
            print(f"[{mode}] Audio duration: {len(audio)/24000:.2f}s, Time: {dur:.2f}s")
            print(f"[{mode}] Whisper transcript: '{res['text'].strip()}'")
        else:
            print(f"[{mode}] FAILED: no audio chunks")

if __name__ == "__main__":
    test_inference()
