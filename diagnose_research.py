from ddgs import DDGS
from research_tools import is_public_https, get_page_text
import httpx

query = "AI agents cybersecurity applications"

print("1. Testing search...")
try:
    results = DDGS(timeout=10).text(query, max_results=5)
    print("Search results:", len(results))
except Exception as e:
    print("Search failed:", repr(e))
    raise SystemExit(1)

for item in results:
    url = item.get("href", "")
    print("\nURL:", url)
    print("Title:", item.get("title"))
    print("Search snippet:", len(item.get("body", "")), "characters")

    allowed = is_public_https(url)
    print("Security filter:", "PASS" if allowed else "REJECTED")

    if not allowed:
        continue

    try:
        r = httpx.get(
            url,
            timeout=8,
            follow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        print("HTTP status:", r.status_code)
        print("Content type:", r.headers.get("content-type"))
        print("Redirect:", r.headers.get("location", "None"))
    except Exception as e:
        print("HTTP error:", repr(e))
        continue

    text = get_page_text(url)
    print("Extracted text:", len(text), "characters")

    if len(text) >= 150:
        print("RESULT: READABLE PAGE")
    else:
        print("RESULT: PAGE REJECTED")
