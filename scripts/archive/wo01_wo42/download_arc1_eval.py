import json
import urllib.request
from pathlib import Path

dest = Path("data/benchmarks/arc_agi_1")
dest.mkdir(parents=True, exist_ok=True)

req = urllib.request.Request(
    "https://api.github.com/repos/fchollet/ARC-AGI/contents/data/evaluation",
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
)
files = json.loads(urllib.request.urlopen(req, timeout=10).read())
eval_files = [f["name"] for f in files if f["name"].endswith(".json")][:20]

print(f"Downloading {len(eval_files)} official ARC-1 evaluation tasks...")
for fname in eval_files:
    out_path = dest / fname
    if not out_path.exists():
        url = f"https://raw.githubusercontent.com/fchollet/ARC-AGI/master/data/evaluation/{fname}"
        content = urllib.request.urlopen(url, timeout=10).read()
        out_path.write_bytes(content)

downloaded = list(dest.glob("*.json"))
print(f"Successfully downloaded {len(downloaded)} tasks to {dest}")
