import httpx
import re
import urllib.parse
import xml.etree.ElementTree as ET

q = "Beverly Ann F. Quintos Philippines Judge"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

print("=== 1. Testing Bing RSS ===")
try:
    url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(q)}&format=rss"
    r = httpx.get(url, headers=headers, timeout=10.0)
    print("Bing RSS status:", r.status_code, "len:", len(r.text))
    if r.status_code == 200:
        print("Starts with:", r.text[:200])
        # Parse XML
        root = ET.fromstring(r.text)
        items = root.findall(".//item")
        print(f"Found {len(items)} RSS items!")
        for it in items[:5]:
            title = it.findtext("title")
            link = it.findtext("link")
            desc = it.findtext("description")
            print("  Title:", title)
            print("  Link :", link)
            print("  Desc :", desc[:150] if desc else "")
            print()
except Exception as e:
    print("Bing RSS error:", e)

print("=== 2. Testing Qwant Lite ===")
try:
    url = f"https://lite.qwant.com/?q={urllib.parse.quote_plus(q)}"
    r = httpx.get(url, headers=headers, timeout=10.0)
    print("Qwant Lite status:", r.status_code, "len:", len(r.text))
    if "quintos" in r.text.lower():
        print("Qwant Lite contains quintos!")
except Exception as e:
    print("Qwant Lite error:", e)

print("=== 3. Testing Yahoo with proper browser headers ===")
try:
    y_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    r = httpx.get(f"https://search.yahoo.com/search?p={urllib.parse.quote_plus(q)}", headers=y_headers, timeout=10.0)
    print("Yahoo status:", r.status_code, "len:", len(r.text))
    if "quintos" in r.text.lower():
        print("Yahoo contains quintos!")
        # check snippets
        matches = re.findall(r'<div class="compText aAbs"[^>]*>(.*?)</div>', r.text)
        print(f"Found {len(matches)} Yahoo compText snippets")
        for m in matches[:3]:
            print("  YAHOO:", re.sub(r'<[^>]+>', '', m).strip()[:150])
except Exception as e:
    print("Yahoo error:", e)
