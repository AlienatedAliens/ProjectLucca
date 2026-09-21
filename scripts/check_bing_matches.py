import re
import html
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('data/bing_sample.html', 'r', encoding='utf-8') as f:
    text = f.read()

matches = [m.start() for m in re.finditer(r'quintos', text, re.I)]
print(f"Total occurrences: {len(matches)}")
for idx, pos in enumerate(matches[5:], 6):
    start = max(0, pos - 200)
    end = min(len(text), pos + 200)
    snippet = re.sub(r'<[^>]+>', ' ', text[start:end])
    clean = ' '.join(snippet.split())
    print(f"Match {idx}: {clean}")
    print("-" * 60)
