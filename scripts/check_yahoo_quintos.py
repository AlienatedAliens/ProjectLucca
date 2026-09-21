import re
import html
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('data/yahoo_cookie.html', 'r', encoding='utf-8') as f:
    text = f.read()

matches = [m.start() for m in re.finditer(r'quintos', text, re.I)]
print(f"Occurrences of quintos in Yahoo: {len(matches)}")
for idx, pos in enumerate(matches[:10]):
    start = max(0, pos - 150)
    end = min(len(text), pos + 150)
    snippet = re.sub(r'<[^>]+>', ' ', text[start:end])
    clean = ' '.join(snippet.split())
    print(f"Match {idx+1}: {clean}")
    print("-" * 50)
