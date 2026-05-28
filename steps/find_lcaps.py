"""Step 2: Fetch each district's latest LCAP PDF.

Primary path: CDE's undocumented public API that backs the California School
Dashboard. Given a district CDS code, we get the exact LCAP PDF the district
submitted to the state.

Fallback path: Firecrawl Search (used when the CDE API has no record for a
district, e.g., very small charter LEAs).
"""
import requests
from config import FIRECRAWL_API_KEY

CDE_LCAP_API = "https://api.mycdeconnect.org/reports/lcap"
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"

# Years to try, newest first. 2025 = latest annual update, 2024 = full 3-yr LCAP.
LCAP_YEARS_TO_TRY = (2025, 2024)


def district_cds(school_cds_code):
    """A 14-digit CDS = CC-DDDDD-SSSSSSS. District-level code zeros out school portion."""
    if not school_cds_code or len(school_cds_code) != 14:
        return None
    return school_cds_code[:7] + "0000000"


def fetch_lcap_from_cde(district_cds_code):
    """Return (pdf_bytes, source_url, year) or (None, None, None)."""
    for year in LCAP_YEARS_TO_TRY:
        url = f"{CDE_LCAP_API}?cdsCode={district_cds_code}&year={year}"
        try:
            resp = requests.get(url, timeout=60)
        except Exception as e:
            print(f"[lcap] CDE API error for {district_cds_code} y{year}: {e}")
            continue
        if resp.status_code == 200 and resp.content[:4] == b"%PDF" and len(resp.content) > 10_000:
            return resp.content, url, str(year)
    return None, None, None


def _firecrawl_search(query, limit=8):
    headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}
    resp = requests.post(FIRECRAWL_SEARCH_URL, json={"query": query, "limit": limit},
                          headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json().get("data", []) or []


def _score(url, title, description):
    score = 0
    text = f"{url} {title} {description}".lower()
    if url.lower().endswith(".pdf"):
        score += 10
    if "lcap" in text:
        score += 5
    for yr in ("2025-26", "2024-25", "2025", "2024"):
        if yr in text:
            score += 3
            break
    if "board" in text or "agenda" in text:
        score -= 2
    return score


def fetch_lcap_from_firecrawl(district_name):
    """Last-resort search if the CDE API has no record. Returns (pdf_bytes, url, year)."""
    queries = [
        f"{district_name} LCAP 2024-25 pdf",
        f"{district_name} Local Control Accountability Plan 2024 2025",
    ]
    best = None
    best_score = -999
    seen = set()
    for q in queries:
        try:
            for r in _firecrawl_search(q, limit=6):
                url = r.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                s = _score(url, r.get("title", ""), r.get("description", ""))
                if s > best_score:
                    best_score = s
                    best = url
        except Exception as e:
            print(f"[lcap] firecrawl search error: {e}")
    if not best:
        return None, None, None
    try:
        resp = requests.get(best, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
        if resp.content[:4] == b"%PDF":
            return resp.content, best, ""
    except Exception as e:
        print(f"[lcap] firecrawl PDF download error: {e}")
    return None, None, None


def fetch_lcap(school_cds_code, district_name):
    """High-level: try CDE API first, fall back to Firecrawl Search.
    Returns dict with keys: pdf_bytes, source_url, year, source ('cde'|'firecrawl'|None)."""
    dcds = district_cds(school_cds_code)
    if dcds:
        pdf, url, year = fetch_lcap_from_cde(dcds)
        if pdf:
            return {"pdf_bytes": pdf, "source_url": url, "year": year, "source": "cde"}
        print(f"[lcap] CDE API had no LCAP for district {dcds}; falling back to Firecrawl")
    pdf, url, year = fetch_lcap_from_firecrawl(district_name)
    if pdf:
        return {"pdf_bytes": pdf, "source_url": url, "year": year, "source": "firecrawl"}
    return {"pdf_bytes": None, "source_url": None, "year": None, "source": None}


if __name__ == "__main__":
    result = fetch_lcap("01611190000000", "Alameda Unified")
    print(f"source={result['source']}  year={result['year']}  bytes={len(result['pdf_bytes']) if result['pdf_bytes'] else 0}  url={result['source_url']}")
