import httpx
import re
import sys

headers = {
    "Host": "www.google.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

try:
    with httpx.Client(http2=True, timeout=10.0, follow_redirects=True) as client:
        r = client.get("https://www.google.com/search?q=Beverly+Ann+F.+Quintos+Philippines+Judge", headers=headers)
        print("Google HTTP/2 Status:", r.status_code, "Length:", len(r.text))
        print("Blocked?", "having trouble accessing" in r.text)
        print("Quintos occurrences:", len(re.findall(r'quintos', r.text, re.I)))
except Exception as e:
    print("Error:", e)
