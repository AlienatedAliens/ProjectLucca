import sys, time, wave
from pathlib import Path
import numpy as np

MODEL_DIR = Path(r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512")
COSYVOICE_DIR = Path(r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, str(COSYVOICE_DIR))
sys.path.insert(0, str(COSYVOICE_DIR / "third_party" / "Matcha-TTS"))

from cosyvoice.cli.cosyvoice import CosyVoice3

print("Loading CosyVoice 3 (fp16=True)...")
cv3 = CosyVoice3(str(MODEL_DIR), fp16=True)

# Test 1: with <|en|>
tts_text_1 = "You are a helpful assistant.<|endofprompt|><|en|>Hello! All systems nominal. I am Lucca, and I am ready to get to work."
ref_wav = r"C:\ProjectLucca\models\tts\samples\sample_systems_check_base.wav"

print("Testing inference_cross_lingual with '<|en|>'...")
t0 = time.time()
for i, out in enumerate(cv3.inference_cross_lingual(tts_text_1, ref_wav, stream=False)):
    samples_f32 = out["tts_speech"].cpu().numpy().flatten()
    samples_i16 = (np.clip(samples_f32, -1.0, 1.0) * 32767.0).astype(np.int16)
    out_path = r"C:\ProjectLucca\models\tts\samples\test_cross_lingual_en1.wav"
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(cv3.sample_rate)
        wf.writeframes(samples_i16.tobytes())
    print(f"Test 1 output: {len(samples_i16)} samples ({len(samples_i16)/cv3.sample_rate:.2f}s), elapsed {time.time()-t0:.2f}s")
    break

# Test 2: without <|en|>
tts_text_2 = "You are a helpful assistant.<|endofprompt|>Hello! All systems nominal. I am Lucca, and I am ready to get to work."
print("Testing inference_cross_lingual without '<|en|>'...")
t0 = time.time()
for i, out in enumerate(cv3.inference_cross_lingual(tts_text_2, ref_wav, stream=False)):
    samples_f32 = out["tts_speech"].cpu().numpy().flatten()
    samples_i16 = (np.clip(samples_f32, -1.0, 1.0) * 32767.0).astype(np.int16)
    out_path = r"C:\ProjectLucca\models\tts\samples\test_cross_lingual_en2.wav"
    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(cv3.sample_rate)
        wf.writeframes(samples_i16.tobytes())
    print(f"Test 2 output: {len(samples_i16)} samples ({len(samples_i16)/cv3.sample_rate:.2f}s), elapsed {time.time()-t0:.2f}s")
    break
