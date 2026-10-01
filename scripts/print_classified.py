import json
from pathlib import Path

p = Path("models/tts/references/asuka/episode08/emotion_classified_manifest.json")
if p.exists():
    with open(p, encoding="utf-8") as f:
        items = json.load(f)
    print(f"Total classified items in Episode 08: {len(items)}\n")
    for it in items:
        if "asuka" in it["filename"]:
            s = it["assigned_stance"]
            pad = it["pad"]
            t = it["text"]
            fn = it["filename"]
            f0 = it["f0_median"]
            print(f"{fn[:32]:<32} | {s:<18} | F0={f0:5.1f}Hz | [{pad[0]:+0.2f}, {pad[1]:+0.2f}, {pad[2]:+0.2f}] | \"{t}\"")
