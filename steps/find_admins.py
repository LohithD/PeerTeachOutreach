"""Step 4: Enrich the admin (name from CDE) with email + LinkedIn via Firecrawl.

CDE already gives us admin first/last name and school phone. We use Firecrawl
Search to find a public LinkedIn profile and any published email.
"""
import re
import requests
from config import FIRECRAWL_API_KEY

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?")

FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"


def _firecrawl_search(query, limit=6):
    headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post(FIRECRAWL_SEARCH_URL, json={"query": query, "limit": limit},
                          headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json().get("data", []) or []


def _firecrawl_scrape(url):
    headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post(FIRECRAWL_SCRAPE_URL,
                          json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
                          headers=headers, timeout=90)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("markdown", "")


def find_linkedin(admin_name, school, city):
    query = f"{admin_name} {school} {city} principal LinkedIn"
    try:
        results = _firecrawl_search(query, limit=8)
    except Exception as e:
        print(f"[admin] LinkedIn search error: {e}")
        return None
    for r in results:
        url = r.get("url", "")
        m = LINKEDIN_RE.search(url)
        if m and "/in/" in m.group(0):
            return m.group(0)
        # also check description
        text = f"{r.get('title','')} {r.get('description','')}"
        m = LINKEDIN_RE.search(text)
        if m:
            return m.group(0)
    return None


def find_email(admin_name, school, website):
    """Try the school website first, then a search fallback."""
    candidates = []
    # 1) Scrape school website if available
    if website and website.lower() not in ("", "no data"):
        if not website.startswith("http"):
            website = "https://" + website
        try:
            md = _firecrawl_scrape(website)
            for email in EMAIL_RE.findall(md or ""):
                if not email.lower().endswith((".png", ".jpg", ".gif")):
                    candidates.append(email)
        except Exception as e:
            print(f"[admin] scrape error {website}: {e}")

    # 2) Search fallback
    last_name = admin_name.split()[-1] if admin_name else ""
    if last_name:
        try:
            results = _firecrawl_search(f"{admin_name} {school} principal email contact", limit=5)
            for r in results:
                text = f"{r.get('description','')} {r.get('title','')}"
                for email in EMAIL_RE.findall(text):
                    candidates.append(email)
        except Exception as e:
            print(f"[admin] email search error: {e}")

    if not candidates:
        return None

    # Prefer emails whose local-part matches the admin's last name
    ln = last_name.lower()
    for e in candidates:
        if ln and ln in e.lower().split("@")[0]:
            return e
    # Otherwise return the first reasonable one
    return candidates[0]


def enrich_admin(school_row):
    first = school_row.get("admin_first", "").strip()
    last = school_row.get("admin_last", "").strip()
    name = f"{first} {last}".strip()
    school = school_row.get("school", "")
    city = school_row.get("city", "")
    website = school_row.get("website", "")

    if not name:
        return {"admin_name": "", "admin_email": None, "admin_linkedin": None}

    linkedin = find_linkedin(name, school, city)
    email = find_email(name, school, website)

    return {
        "admin_name": name,
        "admin_email": email,
        "admin_linkedin": linkedin,
        "admin_phone": school_row.get("phone", ""),
    }


if __name__ == "__main__":
    test_row = {
        "admin_first": "Alysse", "admin_last": "Castro",
        "school": "Lincoln Middle School", "city": "Santa Monica",
        "website": "", "phone": "(310) 555-0100",
    }
    print(enrich_admin(test_row))
