import httpx
import re
import html
import urllib.parse
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

query = "Beverly Ann F. Quintos Philippines Judge"
url = f"https://search.yahoo.com/search?p={urllib.parse.quote_plus(query)}"

print(f"Testing Yahoo with httpx.Client: {url}")
with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
    r = client.get(url)
    print(f"Final URL: {r.url}")
    print(f"Status: {r.status_code}, Length: {len(r.text)}")
    
    # Parse Yahoo search results
    # Each organic result in Yahoo is in <div class="dd algo ..."> or has class "compText" / <h3><a href="...">title</a></h3>
    # Let's extract titles, urls, snippets
    # In Yahoo: <h3 class="title"><a class="td-u" href="...">Title</a></h3>
    # Snippet: <div class="compText aAbs"> or <p class="lh-16">
    
    results = []
    # Let's search for algo blocks:
    blocks = re.findall(r'<div class="[^"]*algo[^"]*"[^>]*>(.*?)</li>', r.text, re.DOTALL)
    if not blocks:
        blocks = re.findall(r'<li[^>]*><div class="[^"]*algo[^"]*"[^>]*>(.*?)</div>\s*</li>', r.text, re.DOTALL)
    
    print(f"Found {len(blocks)} algo blocks in Yahoo HTML")
    
    # Alternatively, extract via h3 + snippet:
    items = re.finditer(r'<h3[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a></h3>.*?<div[^>]*class="[^"]*compText[^"]*"[^>]*>(.*?)</div>', r.text, re.DOTALL)
    for idx, m in enumerate(items, 1):
        raw_url = m.group(1)
        raw_title = m.group(2)
        raw_snippet = m.group(3)
        
        title = html.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()
        snippet = html.unescape(re.sub(r'<[^>]+>', '', raw_snippet)).strip()
        
        # Yahoo redirects links through /RU=.../RK=...
        clean_url = raw_url
        ru_m = re.search(r'/RU=([^/]+)/', raw_url)
        if ru_m:
            clean_url = urllib.parse.unquote(ru_m.group(1))
            
        print(f"Result {idx}:")
        print(f"  Title:   {title}")
        print(f"  URL:     {clean_url}")
        print(f"  Snippet: {snippet}")
        print()
