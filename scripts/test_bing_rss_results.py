import httpx
import xml.etree.ElementTree as ET
import urllib.parse
import sys
import html
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

query = "Beverly Ann F. Quintos Philippines Judge"
url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}&format=rss"
print(f"Fetching: {url}")
r = httpx.get(url, headers=headers, timeout=10.0)
print(f"Status: {r.status_code}")

root = ET.fromstring(r.text)
items = root.findall(".//item")
print(f"Total items: {len(items)}\n")
for idx, it in enumerate(items, 1):
    title = it.findtext("title") or "No title"
    link = it.findtext("link") or ""
    desc = it.findtext("description") or ""
    clean_desc = html.unescape(re.sub(r'<[^>]+>', '', desc)).strip()
    print(f"{idx}. {title}")
    print(f"   Link: {link}")
    print(f"   Snippet: {clean_desc}")
    print()
