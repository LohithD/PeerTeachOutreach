"""Step 1: Find California middle schools from CDE directory."""
import csv
import requests
from config import CDE_DIRECTORY_URL, SCHOOLS_CACHE, MIDDLE_SCHOOLS_CACHE

CDE_MANUAL_INSTRUCTIONS = f"""
CDE blocked the automated download (Radware bot protection).

ONE-TIME SETUP — download the school directory manually:
  1. Open in a browser: {CDE_DIRECTORY_URL}
  2. The file will download as 'pubschls.txt' (tab-separated)
  3. Save it to: {SCHOOLS_CACHE}

The file is updated infrequently; you only need to re-do this when you want
fresh data.
"""


def download_cde_directory(force=False):
    if SCHOOLS_CACHE.exists() and SCHOOLS_CACHE.stat().st_size > 100_000 and not force:
        return SCHOOLS_CACHE
    print(f"[schools] Attempting CDE download...")
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"}
    try:
        resp = requests.get(CDE_DIRECTORY_URL, timeout=60, headers=headers)
        if resp.status_code == 200 and b"<html" not in resp.content[:200].lower() and len(resp.content) > 100_000:
            SCHOOLS_CACHE.write_bytes(resp.content)
            print(f"[schools] Saved {len(resp.content):,} bytes to {SCHOOLS_CACHE}")
            return SCHOOLS_CACHE
    except Exception as e:
        print(f"[schools] Direct download failed: {e}")
    raise RuntimeError(CDE_MANUAL_INSTRUCTIONS)


def parse_middle_schools(county=None, district=None, limit=None):
    """Filter the CDE TSV down to active middle schools.

    EILCode == 'INTMIDJR' identifies intermediate / middle / junior highs.
    """
    download_cde_directory()
    rows = []
    with open(SCHOOLS_CACHE, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("StatusType") != "Active":
                continue
            if row.get("EILCode") != "INTMIDJR":
                continue
            if county and county.lower() not in row.get("County", "").lower():
                continue
            if district and district.lower() not in row.get("District", "").lower():
                continue
            rows.append({
                "cds_code": row.get("CDSCode", ""),
                "school": row.get("School", ""),
                "district": row.get("District", ""),
                "county": row.get("County", ""),
                "city": row.get("City", ""),
                "zip": row.get("Zip", ""),
                "phone": row.get("Phone", ""),
                "website": row.get("WebSite", ""),
                "admin_first": row.get("AdmFName", ""),
                "admin_last": row.get("AdmLName", ""),
                "grades": row.get("GSserved", ""),
            })
            if limit and len(rows) >= limit:
                break
    return rows


def save_middle_schools(rows):
    if not rows:
        return
    with open(MIDDLE_SCHOOLS_CACHE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[schools] Wrote {len(rows)} middle schools to {MIDDLE_SCHOOLS_CACHE}")


if __name__ == "__main__":
    rows = parse_middle_schools(county="Los Angeles", limit=5)
    for r in rows:
        print(f"  - {r['school']} ({r['district']}) — Admin: {r['admin_first']} {r['admin_last']}")
    save_middle_schools(rows)
