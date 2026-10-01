import sys, os, time, wave
from pathlib import Path
import numpy as np
import torch
import torchaudio
import librosa

MODEL_DIR = Path(r"C:\ProjectLucca\app\CosyVoice\pretrained_models\Fun-CosyVoice3-0.5B-2512")
COSYVOICE_DIR = Path(r"C:\ProjectLucca\app\CosyVoice")
sys.path.insert(0, str(COSYVOICE_DIR))
sys.path.insert(0, str(COSYVOICE_DIR / "third_party" / "Matcha-TTS"))

from cosyvoice.cli.cosyvoice import CosyVoice3
from cosyvoice.utils.file_utils import load_wav
from cosyvoice.utils.common import set_all_random_seed

print("Loading CosyVoice 3 (fp16=True)...")
cv3 = CosyVoice3(str(MODEL_DIR), fp16=True)

target_sr = 24000
max_val = 0.8
top_db = 60
hop_length = 220
win_length = 440

def postprocess(wav_in: str, wav_out: str) -> str:
    speech = load_wav(wav_in, target_sr=target_sr, min_sr=16000)
    speech, _ = librosa.effects.trim(
        speech, top_db=top_db, frame_length=win_length, hop_length=hop_length
    )
    if speech.abs().max() > max_val:
        speech = speech / speech.abs().max() * max_val
    speech = torch.concat([speech, torch.zeros(1, int(target_sr * 0.2))], dim=1)
    
    samples_i16 = (np.clip(speech.numpy(), -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(wav_out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(target_sr)
        wf.writeframes(samples_i16.tobytes())
    return wav_out

ref_raw = r"C:\ProjectLucca\models\tts\samples\sample_systems_check_base.wav"
ref_proc = r"C:\ProjectLucca\models\tts\samples\sample_systems_check_proc.wav"
postprocess(ref_raw, ref_proc)

prompt_text = "All systems nominal, 16K context verified, and memory telemetry is completely clear."
full_prompt_text = "You are a helpful assistant.<|endofprompt|>" + prompt_text

tts_text = "Her handwriting is very neat, which suggests she likes things tidy."

print("Running exact official zero-shot inference...")
set_all_random_seed(42)
t0 = time.time()
speech_list = []
for i in cv3.inference_zero_shot(
    tts_text,
    full_prompt_text,
    ref_proc,
    stream=False,
    speed=1.0,
):
    speech_list.append(i["tts_speech"])

audio = torch.concat(speech_list, dim=1).numpy().flatten()
samples_i16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
out_path = r"C:\ProjectLucca\models\tts\samples\test_hf_exact.wav"
with wave.open(out_path, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(target_sr)
    wf.writeframes(samples_i16.tobytes())

print(f"Generated {len(samples_i16)} samples ({len(samples_i16)/target_sr:.2f}s) in {time.time()-t0:.2f}s")
