import httpx
import re
import urllib.parse
import json

# Test 1: DuckDuckGo API endpoint used by ddgs (vqd token)
# First get vqd token from https://duckduckgo.com/?q=...
q = "Beverly Ann F. Quintos Philippines Judge"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

print("=== Testing DuckDuckGo vqd flow ===")
try:
    with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
        r1 = client.get(f"https://duckduckgo.com/?q={urllib.parse.quote_plus(q)}")
        print("DDG main page status:", r1.status_code)
        vqd_match = re.search(r'vqd=([\d-]+)', r1.text) or re.search(r'vqd=([a-zA-Z0-9_-]+)', r1.text)
        if vqd_match:
            vqd = vqd_match.group(1)
            print("Found vqd:", vqd)
            r2 = client.get(f"https://links.duckduckgo.com/d.js?q={urllib.parse.quote_plus(q)}&vqd={vqd}")
            print("DDG d.js status:", r2.status_code, "len:", len(r2.text))
            if "quintos" in r2.text.lower():
                print("DDG d.js returned results with quintos!")
        else:
            print("No vqd found")
except Exception as e:
    print("DDG vqd flow error:", e)

print("\n=== Testing Startpage ===")
try:
    with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
        r = client.post("https://www.startpage.com/do/dsearch", data={"query": q, "cat": "web"})
        print("Startpage status:", r.status_code, "len:", len(r.text))
        if "quintos" in r.text.lower():
            print("Startpage has quintos!")
except Exception as e:
    print("Startpage error:", e)

print("\n=== Testing Google via mobile/lite or serp ===")
# Mobile User Agent often gives clean HTML without JS requirements
mobile_headers = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
try:
    with httpx.Client(timeout=10.0, follow_redirects=True, headers=mobile_headers) as client:
        r = client.get(f"https://www.google.com/search?q={urllib.parse.quote_plus(q)}&hl=en")
        print("Google mobile status:", r.status_code, "len:", len(r.text))
        if "quintos" in r.text.lower():
            print("Google mobile has quintos!")
            # check snippets
            blocks = re.findall(r'<div[^>]*>(.*?)</div>', r.text)
            matches = [b for b in blocks if "quintos" in b.lower() and len(b) < 300]
            for m in matches[:3]:
                print("  Google snippet:", re.sub(r'<[^>]+>', '', m).strip())
except Exception as e:
    print("Google mobile error:", e)
