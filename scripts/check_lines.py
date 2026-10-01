import json

with open(r"C:\Projects\ProjectLucca\models\tts\references\asuka\episode08\manifest.json") as f:
    items = json.load(f)

for it in items:
    if it.get("is_asuka"):
        print(f"{it['filename']}: dur={it['duration']:.2f}s, f0={it['f0_hz']:.1f}Hz, text='{it['text']}'")
