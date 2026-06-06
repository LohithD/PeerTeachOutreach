"""PeerTeach outreach pipeline — master-sheet batched mode.

Two modes:
  --populate            One-time: fill the Google Sheet with every CA middle
                        school as a 'pending' row.
  (default)             Pull next --batch pending rows from the sheet, process
                        them (LCAP analysis + admin enrichment), and write the
                        results back to those exact rows. Idempotent — safe to
                        run repeatedly on a schedule.

Examples:
  python main.py --populate                # one-time setup
  python main.py --batch 10                # process next 10 pending rows
  python main.py --batch 25 --county "Los Angeles"   # only LA pending rows
"""
import argparse
import sys
import time
import traceback

from steps.find_schools import parse_middle_schools
from steps.find_lcaps import fetch_lcap
from steps.analyze_lcap import analyze_pdf, save_pdf_bytes
from steps.find_admins import enrich_admin
from steps.write_email import generate_email
from steps.sheet_sync import (
    populate_master_sheet, get_pending_rows, update_row, mark_failed,
)


def populate(county=None):
    print("=== Populating master sheet ===")
    schools = parse_middle_schools(county=county)
    print(f"Loaded {len(schools)} middle schools from CDE")
    added = populate_master_sheet(schools)
    print(f"Done. Added {added} new rows.")


def _process_row(row_idx, record, lcap_cache):
    district = record["district"]
    school = record["school"]
    cds = record.get("cds_code", "")
    print(f"\n[row {row_idx}] {school} — {district}  (cds={cds})")

    # Step 2 + 3: LCAP (cached per district CDS)
    district_key = cds[:7] if cds else district
    if district_key not in lcap_cache:
        lcap_meta = fetch_lcap(cds, district)
        if not lcap_meta["pdf_bytes"]:
            lcap_cache[district_key] = (lcap_meta, {"error": "no LCAP found"})
        else:
            print(f"  LCAP: {lcap_meta['source_url']}  (source={lcap_meta['source']}, year={lcap_meta['year']})")
            try:
                pdf_path = save_pdf_bytes(lcap_meta["pdf_bytes"], lcap_meta["source_url"])
                analysis = analyze_pdf(pdf_path)
                lcap_cache[district_key] = (lcap_meta, analysis)
            except Exception as e:
                print(f"  ! analyze failed: {e}")
                lcap_cache[district_key] = (lcap_meta, {"error": str(e)})
    lcap_meta, analysis = lcap_cache[district_key]

    # Step 4: admin enrichment
    school_row = {
        "admin_first": record.get("admin_name", "").split(" ", 1)[0] if record.get("admin_name") else "",
        "admin_last": record.get("admin_name", "").split(" ", 1)[-1] if record.get("admin_name") else "",
        "school": school, "city": record.get("city", ""),
        "website": record.get("school_website", ""), "phone": record.get("admin_phone", ""),
    }
    try:
        admin = enrich_admin(school_row)
    except Exception as e:
        print(f"  ! admin enrich failed: {e}")
        admin = {}

    # Build update payload — always sort by rank ascending
    top_angles = sorted(analysis.get("top_angles") or [], key=lambda a: a.get("rank", 999))
    angles_str = "\n\n".join(
        f"{a.get('rank','?')}. {a.get('angle','')}  [{a.get('strength','?')}]\n"
        f"   approach: {a.get('district_approach','')}\n"
        f"   peer insight: {a.get('peer_teaching_insight','')}"
        for a in top_angles)

    # Generate the actual email from the #1 angle
    email_1 = ""
    if top_angles:
        try:
            email_1 = generate_email(
                admin_name=record.get("admin_name", ""),
                title="Principal",
                district_name=district,
                school=school,
                top_angle=top_angles[0],
            )
        except Exception as e:
            print(f"  ! email gen failed: {e}")

    return {
        "admin_email": admin.get("admin_email") or "",
        "admin_linkedin": admin.get("admin_linkedin") or "",
        "lcap_year": analysis.get("lcap_year", "") or (lcap_meta or {}).get("year", ""),
        "lcap_url": (lcap_meta or {}).get("source_url", ""),
        "lcap_source": (lcap_meta or {}).get("source", ""),
        "top_angles": angles_str,
        "key_metrics": "\n".join(f"• {m}" for m in (analysis.get("key_metrics") or [])),
        "stated_priorities": "\n".join(f"• {p}" for p in (analysis.get("stated_priorities") or [])),
        "warning_flags": "\n".join(f"• {w}" for w in (analysis.get("warning_flags") or [])),
        "email_1": email_1,
    }, "done" if not analysis.get("error") else "failed"


def run_batch(batch_size=10):
    print(f"=== Processing batch of {batch_size} pending rows ===")
    pending = get_pending_rows(limit=batch_size)
    if not pending:
        print("No pending rows. All done!")
        return
    print(f"Pulled {len(pending)} pending rows from sheet\n")

    lcap_cache = {}
    for i, (row_idx, record) in enumerate(pending, 1):
        print(f"\n--- {i}/{len(pending)} ---")
        try:
            updates, status = _process_row(row_idx, record, lcap_cache)
            update_row(row_idx, updates, status=status)
            print(f"  ✓ row {row_idx} marked {status}")
        except Exception as e:
            traceback.print_exc()
            mark_failed(row_idx, str(e))
        time.sleep(1)
    print("\n=== Batch complete ===")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--populate", action="store_true",
                   help="One-time: fill sheet with all CA middle schools as pending")
    p.add_argument("--county", default=None,
                   help="With --populate: limit to this county. Else: ignored.")
    p.add_argument("--batch", type=int, default=10,
                   help="How many pending rows to process this run (default 10)")
    args = p.parse_args()

    try:
        if args.populate:
            populate(county=args.county)
        else:
            run_batch(batch_size=args.batch)
    except KeyboardInterrupt:
        print("\nInterrupted."); sys.exit(1)
