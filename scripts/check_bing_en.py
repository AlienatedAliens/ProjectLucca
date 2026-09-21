import httpx
import re
import html
import urllib.parse
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

query = 'Beverly Ann F. Quintos Philippines Judge'

# 1. Bing with English market/lang
url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}&setmkt=en-US&setlang=en-US"
print(f"Querying Bing: {url}")
r = httpx.get(url, headers=headers, timeout=10.0)
print(f"Status: {r.status_code}, Length: {len(r.text)}")

# Let's save the HTML to see what's inside
with open('data/bing_sample.html', 'w', encoding='utf-8') as f:
    f.write(r.text)

# Check for Quintos
matches = [m.start() for m in re.finditer(r'quintos', r.text, re.I)]
print(f"Occurrences of 'quintos' in Bing: {len(matches)}")
for idx, pos in enumerate(matches[:5]):
    start = max(0, pos - 150)
    end = min(len(r.text), pos + 150)
    snippet = re.sub(r'<[^>]+>', ' ', r.text[start:end])
    print(f"Match {idx+1}: {snippet.strip()}")
    print("-" * 50)
