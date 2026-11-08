import soundfile as sf
import librosa
from pathlib import Path

voc_path = Path(r"C:\Projects\ProjectLucca\harvest\vocals\htdemucs\source_00\vocals.wav")
audio, sr = sf.read(str(voc_path))
if len(audio.shape) > 1:
    audio = audio.mean(axis=1)

# Lines 11 & 12: 24.30s to 28.35s
start_samp = int(24.30 * sr)
end_samp = int(28.35 * sr)
chunk = audio[start_samp:end_samp]

# Resample to 24000 Hz
chunk_24k = librosa.resample(chunk, orig_sr=sr, target_sr=24000)
max_amp = float(max(abs(chunk_24k)))
if max_amp > 0:
    chunk_24k = (chunk_24k / max_amp) * 0.89

out_file = Path(r"C:\Projects\ProjectLucca\models\tts\references\asuka\asuka_anchor_german_banter.wav")
sf.write(str(out_file), chunk_24k, 24000)

print(f"Created {out_file.name}: {len(chunk_24k)/24000:.2f}s @ 24kHz.")
print('Transcript: "You\'re thinking in Japanese aren\'t you? If you must think to do it in German."')
