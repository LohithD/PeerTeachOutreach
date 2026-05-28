"""Step 5: Write results to CSV (always) and Google Sheets (if configured)."""
import csv
import json
from pathlib import Path
from config import OUTPUT_DIR, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON

COLUMNS = [
    "school", "district", "county", "city",
    "admin_name", "admin_email", "admin_phone", "admin_linkedin",
    "school_website", "lcap_year", "lcap_url",
    "top_angles", "key_metrics", "stated_priorities", "warning_flags",
    "raw_analysis_json",
]


def _flatten_row(school, lcap_meta, analysis, admin):
    top_angles = analysis.get("top_angles") or []
    angles_str = "\n\n".join(
        f"• {a.get('angle','')}\n   Evidence: {a.get('evidence','')}\n   Why it lands: {a.get('why_it_lands','')}"
        for a in top_angles
    )
    return {
        "school": school.get("school", ""),
        "district": school.get("district", ""),
        "county": school.get("county", ""),
        "city": school.get("city", ""),
        "admin_name": admin.get("admin_name", ""),
        "admin_email": admin.get("admin_email") or "",
        "admin_phone": admin.get("admin_phone", ""),
        "admin_linkedin": admin.get("admin_linkedin") or "",
        "school_website": school.get("website", ""),
        "lcap_year": analysis.get("lcap_year", ""),
        "lcap_url": lcap_meta.get("url", "") if lcap_meta else "",
        "top_angles": angles_str,
        "key_metrics": "\n".join(f"• {m}" for m in (analysis.get("key_metrics") or [])),
        "stated_priorities": "\n".join(f"• {p}" for p in (analysis.get("stated_priorities") or [])),
        "warning_flags": "\n".join(f"• {w}" for w in (analysis.get("warning_flags") or [])),
        "raw_analysis_json": json.dumps(analysis, ensure_ascii=False),
    }


def write_csv(rows, filename="peerteach_outreach.csv"):
    path = OUTPUT_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"[output] Wrote {len(rows)} rows -> {path}")
    return path


def write_google_sheet(rows):
    if not GOOGLE_SHEET_ID:
        print("[output] GOOGLE_SHEET_ID not set — skipping Sheets push")
        return False
    if not Path(GOOGLE_SERVICE_ACCOUNT_JSON).exists():
        print(f"[output] {GOOGLE_SERVICE_ACCOUNT_JSON} not found — skipping Sheets push")
        return False
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("[output] gspread not installed — skipping Sheets push")
        return False

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_JSON, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    try:
        ws = sh.worksheet("PeerTeach Outreach")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="PeerTeach Outreach", rows=1000, cols=len(COLUMNS))

    ws.clear()
    ws.append_row(COLUMNS)
    for r in rows:
        ws.append_row([r.get(c, "") for c in COLUMNS])
    print(f"[output] Pushed {len(rows)} rows to Google Sheet {GOOGLE_SHEET_ID}")
    return True


def build_and_write(records):
    """records: list of dicts with keys: school, lcap_meta, analysis, admin"""
    rows = [_flatten_row(r["school"], r.get("lcap_meta"), r.get("analysis", {}), r.get("admin", {}))
            for r in records]
    write_csv(rows)
    write_google_sheet(rows)
    return rows
