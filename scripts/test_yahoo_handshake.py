import httpx
import re
import html
import urllib.parse
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {
    "User-Agent": "curl/8.21.0",
    "Accept": "*/*",
}

query = "Beverly Ann F. Quintos Philippines Judge"
search_url = f"https://search.yahoo.com/search?p={urllib.parse.quote_plus(query)}"

with httpx.Client(headers=headers, timeout=10.0) as client:
    # 1. First GET to search page -> returns 307 with cookie
    r1 = client.get(search_url, follow_redirects=False)
    print("Step 1:", r1.status_code, "Cookies:", dict(client.cookies))
    
    # 2. Follow redirect to /_bv/v.gif with the cookie
    loc1 = r1.headers.get("location")
    if loc1:
        if loc1.startswith("/"):
            loc1 = "https://search.yahoo.com" + loc1
        r2 = client.get(loc1, follow_redirects=False)
        print("Step 2:", r2.status_code, "Location:", r2.headers.get("location"))
        
        # 3. /_bv/v.gif returns 307 back to search page
        loc2 = r2.headers.get("location")
        if loc2:
            if loc2.startswith("/"):
                loc2 = "https://search.yahoo.com" + loc2
            r3 = client.get(loc2, follow_redirects=False)
            print("Step 3:", r3.status_code, "Length:", len(r3.text))
            
            # Extract results!
            # Pattern for Yahoo search results:
            # <div class="compText aAbs">snippet</div>
            # <h3 class="title"><a ...>title</a></h3>
            
            results = []
            # Find all result blocks
            # Look for <h3><a ... href="...">...</a></h3>
            items = re.finditer(r'<h3[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a></h3>.*?<div[^>]*class="[^"]*compText[^"]*"[^>]*>(.*?)</div>', r3.text, re.DOTALL)
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
                    
            print(f"\nExtracted {len(results)} search results from Yahoo:\n")
            for idx, res in enumerate(results[:5], 1):
                print(f"{idx}. {res['title']}")
                print(f"   URL:     {res['url']}")
                print(f"   Snippet: {res['snippet']}")
                print()
