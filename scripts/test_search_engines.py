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

print("=== TESTING BING ===")
try:
    r = httpx.get(f'https://www.bing.com/search?q={urllib.parse.quote_plus(query)}', headers=headers, timeout=10.0)
    print(f"Status: {r.status_code}, Length: {len(r.text)}")
    blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', r.text, re.DOTALL)
    print(f"Found {len(blocks)} b_algo blocks in Bing")
    for idx, b in enumerate(blocks[:5], 1):
        title_m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b)
        url = title_m.group(1) if title_m else ''
        title = html.unescape(re.sub(r'<[^>]+>', '', title_m.group(2))) if title_m else ''
        snippet_m = re.search(r'<p[^>]*>(.*?)</p>', b, re.DOTALL)
        snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet_m.group(1))).strip() if snippet_m else ''
        print(f"Result {idx}:")
        print(f"  Title:   {title}")
        print(f"  URL:     {url}")
        print(f"  Snippet: {snippet[:200]}")
except Exception as e:
    print(f"Bing failed: {e}")

print("\n=== TESTING GOOGLE ===")
try:
    r = httpx.get(f'https://www.google.com/search?q={urllib.parse.quote_plus(query)}', headers=headers, timeout=10.0)
    print(f"Status: {r.status_code}, Length: {len(r.text)}")
    # Google snippet blocks
    # Google uses <div class="g"> or <h3> for titles
    h3_matches = re.finditer(r'<a[^>]*href="/url\?q=([^"&]+)[^"]*"[^>]*><h3[^>]*>(.*?)</h3></a>', r.text)
    g_results = list(h3_matches)
    print(f"Found {len(g_results)} /url?q= h3 results in Google")
    if not g_results:
        # Check standard desktop Google
        h3_matches2 = re.finditer(r'<a[^>]*href="(https?://[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>', r.text, re.DOTALL)
        g_results = list(h3_matches2)
        print(f"Found {len(g_results)} standard h3 results in Google")
        for idx, m in enumerate(g_results[:5], 1):
            url = m.group(1)
            title = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
            print(f"Result {idx}:")
            print(f"  Title: {title}")
            print(f"  URL:   {url}")
except Exception as e:
    print(f"Google failed: {e}")
