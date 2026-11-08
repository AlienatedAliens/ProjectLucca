import sys
import soundfile as sf
from pathlib import Path

# Force UTF-8 on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

out_dir = Path(r"C:\Projects\ProjectLucca\models\tts\references\test_output")

try:
    import whisper
    model = whisper.load_model("base")
    for p in sorted(out_dir.glob("*.wav")):
        res = model.transcribe(str(p))
        text = res['text'].strip()
        dur = sf.info(str(p)).duration
        print(f"[{p.name}] dur={dur:.2f}s -> text: '{text}'")
except Exception as e:
    print(f"Whisper failed: {e}")
