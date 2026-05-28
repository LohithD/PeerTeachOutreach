"""Master sheet sync: populate once, then pull/update batches per run.

Sheet layout (row 1 = header):
  A status   B school   C district   D county   E city
  F admin_name   G admin_email   H admin_phone   I admin_linkedin
  J school_website   K lcap_year   L lcap_url
  M top_angles   N key_metrics   O stated_priorities   P warning_flags
  Q last_processed   R notes
"""
import datetime
import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON

SHEET_TAB = "PeerTeach Outreach"
HEADERS = [
    "status", "cds_code", "school", "district", "county", "city",
    "admin_name", "admin_email", "admin_phone", "admin_linkedin",
    "school_website", "lcap_year", "lcap_url", "lcap_source",
    "top_angles", "key_metrics", "stated_priorities", "warning_flags",
    "last_processed", "notes", "email_1",
]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_worksheet():
    creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    try:
        ws = sh.worksheet(SHEET_TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_TAB, rows=2500, cols=len(HEADERS))
    return ws


def populate_master_sheet(schools, clear_existing=False):
    """Write every middle school as a pending row. Idempotent — skips rows already present
    (matched by CDS code stored in notes column? No — by school+district combo)."""
    ws = _get_worksheet()
    if clear_existing:
        ws.clear()

    existing_values = ws.get_all_values()
    if not existing_values or existing_values[0] != HEADERS:
        ws.update("A1", [HEADERS])
        existing_keys = set()
    else:
        # build set of cds codes already in sheet
        cds_col = HEADERS.index("cds_code")
        existing_keys = {r[cds_col] for r in existing_values[1:] if len(r) > cds_col and r[cds_col]}

    new_rows = []
    for s in schools:
        if s.get("cds_code") in existing_keys:
            continue
        admin_name = f"{s.get('admin_first','')} {s.get('admin_last','')}".strip()
        new_rows.append([
            "pending",                # status
            s.get("cds_code", ""),
            s.get("school", ""),
            s.get("district", ""),
            s.get("county", ""),
            s.get("city", ""),
            admin_name,
            "",                       # admin_email (filled later)
            s.get("phone", ""),
            "",                       # admin_linkedin
            s.get("website", ""),
            "", "", "",               # lcap_year, lcap_url, lcap_source
            "", "", "", "",           # angles/metrics/priorities/warnings
            "",                       # last_processed
            "",                       # notes
            "",                       # email_1
        ])

    if not new_rows:
        print(f"[sync] No new schools to add; sheet already has them.")
        return 0

    # gspread batch append in chunks (API limit ~10MB per request)
    BATCH = 500
    for i in range(0, len(new_rows), BATCH):
        ws.append_rows(new_rows[i:i+BATCH], value_input_option="RAW")
        print(f"[sync] Appended rows {i+1}-{min(i+BATCH, len(new_rows))}")
    return len(new_rows)


def get_pending_rows(limit=10):
    """Return list of (row_index_1based, dict-of-fields) for pending rows."""
    ws = _get_worksheet()
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        return []
    headers = all_values[0]
    out = []
    for idx, row in enumerate(all_values[1:], start=2):  # row indices are 1-based; +1 for header
        row = row + [""] * (len(headers) - len(row))
        record = dict(zip(headers, row))
        if record.get("status", "").lower() == "pending":
            out.append((idx, record))
            if len(out) >= limit:
                break
    return out


def update_row(row_index, updates, status="done"):
    """Patch specific cells in a row. updates: dict of column-name -> value."""
    ws = _get_worksheet()
    updates = dict(updates)
    updates["status"] = status
    updates["last_processed"] = datetime.datetime.now().isoformat(timespec="seconds")

    cells = []
    for col_name, val in updates.items():
        if col_name not in HEADERS:
            continue
        col_letter = chr(ord("A") + HEADERS.index(col_name))
        cells.append({"range": f"{col_letter}{row_index}", "values": [[val or ""]]})
    if cells:
        ws.batch_update(cells, value_input_option="RAW")


def mark_failed(row_index, error_msg):
    update_row(row_index, {"notes": f"FAILED: {error_msg[:300]}"}, status="failed")
