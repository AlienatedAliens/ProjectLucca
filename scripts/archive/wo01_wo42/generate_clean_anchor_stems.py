import soundfile as sf
import librosa
import numpy as np
from pathlib import Path

voc_path = Path(r"C:\Projects\ProjectLucca\harvest\vocals\htdemucs\source_00\vocals.wav")
audio, sr = sf.read(str(voc_path))
if len(audio.shape) > 1:
    audio = audio.mean(axis=1)

# 1. Master Anchor German Banter: 24.18s to 28.62s
# Completely untruncated with 50ms silence padding on both ends
start_1 = int(24.18 * sr)
end_1 = int(28.62 * sr)
chunk_1 = audio[start_1:end_1]
chunk_1_24k = librosa.resample(chunk_1, orig_sr=sr, target_sr=24000)
# Gentle 20ms fade-in / fade-out to ensure 0 pop/click at zero crossings
fade_len = int(0.02 * 24000)
fade_in = np.linspace(0.0, 1.0, fade_len)
fade_out = np.linspace(1.0, 0.0, fade_len)
chunk_1_24k[:fade_len] *= fade_in
chunk_1_24k[-fade_len:] *= fade_out

max_amp_1 = float(np.max(np.abs(chunk_1_24k)))
if max_amp_1 > 0:
    chunk_1_24k = (chunk_1_24k / max_amp_1) * 0.90

# 2. Master Reprimand Anchor: 65.10s to 66.95s ("I thought I told you not to get in my way!")
start_2 = int(65.10 * sr)
end_2 = int(66.95 * sr)
chunk_2 = audio[start_2:end_2]
chunk_2_24k = librosa.resample(chunk_2, orig_sr=sr, target_sr=24000)
chunk_2_24k[:fade_len] *= fade_in
chunk_2_24k[-fade_len:] *= fade_out
max_amp_2 = float(np.max(np.abs(chunk_2_24k)))
if max_amp_2 > 0:
    chunk_2_24k = (chunk_2_24k / max_amp_2) * 0.90

dest_dirs = [
    Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka"),
    Path(r"C:\ProjectLucca\app\CosyVoice\asset"),
]

for d in dest_dirs:
    d.mkdir(parents=True, exist_ok=True)
    out1 = d / "asuka_anchor_german_banter.wav"
    sf.write(str(out1), chunk_1_24k, 24000)
    print(f"Wrote {out1}: {len(chunk_1_24k)/24000:.2f}s @ 24kHz")

    out2 = d / "asuka_reprimand_dry.wav"
    sf.write(str(out2), chunk_2_24k, 24000)
    print(f"Wrote {out2}: {len(chunk_2_24k)/24000:.2f}s @ 24kHz")

print("Anchor stems generated successfully.")
