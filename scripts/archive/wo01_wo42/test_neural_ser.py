import torch
import soundfile as sf
import numpy as np
from pathlib import Path
from transformers import AutoModelForAudioClassification, AutoFeatureExtractor

model_id = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"
extractor = AutoFeatureExtractor.from_pretrained(model_id)
model = AutoModelForAudioClassification.from_pretrained(model_id)
model.eval()

device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)
print(f"Model loaded on {device}!")

test_files = [
    r"C:\Projects\ProjectLucca\models\tts\references\asuka\asuka_anchor_german_banter.wav",
    r"C:\Projects\ProjectLucca\models\tts\references\asuka\episode08\ep08_11_asuka_you_re_thinking_in.wav",
    r"C:\Projects\ProjectLucca\models\tts\references\asuka\episode08\ep08_09_asuka_i_told_you_not_to_.wav",
    r"C:\Projects\ProjectLucca\models\tts\references\asuka\episode08\ep08_18_asuka_switch_language_to.wav"
]

for tf in test_files:
    p = Path(tf)
    if not p.exists():
        continue
    audio, sr = sf.read(str(p))
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)
    
    # Model expects 16kHz
    if sr != 16000:
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
    
    inputs = extractor(audio, sampling_rate=16000, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    
    with torch.no_grad():
        logits = model(**inputs).logits.squeeze().cpu().numpy()
    
    # Output is [arousal, dominance, valence]
    arousal, dominance, valence = logits[0], logits[1], logits[2]
    print(f"[{p.name[:25]:<25}] -> Valence(P): {valence:+.3f} | Arousal(A): {arousal:+.3f} | Dominance(D): {dominance:+.3f}")
