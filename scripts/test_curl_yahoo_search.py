import subprocess
import re
import html
import urllib.parse
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

query = "Beverly Ann F. Quintos Philippines Judge"
quoted_q = urllib.parse.quote_plus(query)

print("=== TESTING YAHOO VIA CURL.EXE ===")
cmd = [
    "curl.exe", "-s", "-c", "data/curl_cookies.txt", "-b", "data/curl_cookies.txt", "-L",
    f"https://search.yahoo.com/search?p={quoted_q}"
]
proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(f"Curl returncode: {proc.returncode}, Output len: {len(proc.stdout)}")

# Parse results from Yahoo HTML
items = re.finditer(r'<h3[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a></h3>.*?<div[^>]*class="[^"]*compText[^"]*"[^>]*>(.*?)</div>', proc.stdout, re.DOTALL)
results = []
for m in items:
    raw_url = m.group(1)
    raw_title = m.group(2)
    raw_snippet = m.group(3)
    
    title = html.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()
    snippet = html.unescape(re.sub(r'<[^>]+>', '', raw_snippet)).strip()
    
    clean_url = raw_url
    ru_m = re.search(r'/RU=([^/]+)/', raw_url)
    if ru_m:
        clean_url = urllib.parse.unquote(ru_m.group(1))
        
    if title or snippet:
        results.append({"title": title, "url": clean_url, "snippet": snippet})

print(f"Parsed {len(results)} results from Yahoo via curl:")
for idx, res in enumerate(results[:5], 1):
    print(f"{idx}. {res['title']}")
    print(f"   URL:     {res['url']}")
    print(f"   Snippet: {res['snippet']}")
    print()
