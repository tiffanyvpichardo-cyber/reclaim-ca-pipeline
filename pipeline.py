"""
Reclaim CA Automation — Main Pipeline Orchestrator (California SCO Workflow)
===========================================================================
California publishes its entire public unclaimed-property database for free,
refreshed every Thursday. So the flow is simpler than the Georgia CDR version:
there is no registration-gated file — you download the SCO band directly.

Real workflow (run weekly, on/after Thursday's SCO refresh):
  1. python pipeline.py --download --band 500+         <- pull the SCO ZIP
  2. python pipeline.py --load-file data/sco/<file>.zip <- parse & load leads
  3. python pipeline.py --skip-trace-only               <- enrich contact info
  4. python pipeline.py --letters-only                  <- mail letters
  5. python pipeline.py --export                        <- sync to dashboard

Or run it all in one shot (downloads first):
  python pipeline.py --full --download --band 500+

⚠ COMPLIANCE GATE: real (non-dry-run) letters are blocked until CA_COMPLIANCE_OK
is set true in .env. That flag should only be flipped AFTER a California
attorney has reviewed your agreement + letter language and confirmed your
licensing status. See CA_COMPLIANCE.md. Dry runs work without it.
"""
import argparse
import os
import time
from datetime import datetime

import db
from config import MIN_PROPERTY_VALUE, OUTPUT_DIR, EXPORTS_DIR, CA_COMPLIANCE_OK, SCO_DATA_BAND
from skip_trace import skip_trace_batch
from mailer import send_letter
from ca_sco_parser import parse_sco_file, download_sco_data


def check_compliance_status():
    """Warn if the California compliance review flag hasn't been set."""
    if not CA_COMPLIANCE_OK:
        print("\n" + "!"*64)
        print("  CA_COMPLIANCE_OK is not set in your .env file.")
        print("  Real letters CANNOT be sent until a California attorney has")
        print("  reviewed your agreement + solicitation language (CCP §§ 1580–1582)")
        print("  and you set CA_COMPLIANCE_OK=true in .env.")
        print("  See CA_COMPLIANCE.md. You can still run --dry-run to preview.")
        print("!"*64 + "\n")
        return False
    return True


def download_step(band):
    print(f"\n{'='*50}")
    print("STEP 0: DOWNLOADING CA SCO DATA")
    print(f"{'='*50}")
    return download_sco_data(band=band)


def load_file_step(filepath, min_value):
    """Parse the CA SCO file and load qualifying leads."""
    print(f"\n{'='*50}")
    print("STEP 1: LOADING CA SCO DATA FILE")
    print(f"{'='*50}")

    conn = db.connect()
    existing_ids = {
        row[0] for row in conn.execute(
            "SELECT property_id FROM leads WHERE property_id != ''"
        ).fetchall()
    }
    conn.close()

    inserted = 0
    skipped_dupe = 0
    for lead in parse_sco_file(filepath, min_value=min_value, state_code="CA"):
        if lead["property_id"] and lead["property_id"] in existing_ids:
            skipped_dupe += 1
            continue
        lead_id = db.upsert_lead(lead)
        db.log_activity(lead_id, "Lead loaded from CA SCO data file")
        if lead["property_id"]:
            existing_ids.add(lead["property_id"])
        inserted += 1

    print(f"\n✓ Loaded {inserted} new leads ({skipped_dupe} duplicates skipped)")
    return inserted


def skip_trace_step(batch_size=50):
    """Skip trace all new leads without verified contact info."""
    print(f"\n{'='*50}")
    print("STEP 2: SKIP TRACING")
    print(f"{'='*50}")

    leads = db.get_leads_for_skip_trace()
    if not leads:
        print("  No leads need skip tracing.")
        return 0

    print(f"  {len(leads)} leads to skip trace…")
    enriched_count = 0

    for i in range(0, len(leads), batch_size):
        batch = leads[i:i+batch_size]
        print(f"  Batch {i//batch_size + 1}: {len(batch)} leads…")
        pairs = skip_trace_batch(batch)

        for lead, enriched in pairs:
            if enriched and (enriched.get("phone") or enriched.get("address")):
                db.mark_skip_traced(
                    lead["id"],
                    phone=enriched.get("phone", ""),
                    address=enriched.get("address", ""),
                    city=enriched.get("city", ""),
                    state=enriched.get("state", ""),
                    zip_=enriched.get("zip", ""),
                )
                db.update_stage(lead["id"], "verified")
                enriched_count += 1
            else:
                db.log_activity(lead["id"], "Skip trace: no match found")

        time.sleep(2)

    print(f"\n✓ Skip trace complete — {enriched_count}/{len(leads)} enriched")
    return enriched_count


def letters_step(dry_run=False, limit=None):
    """Send letters to skip-traced leads."""
    print(f"\n{'='*50}")
    print(f"STEP 3: SENDING LETTERS{'  [DRY RUN]' if dry_run else ''}")
    print(f"{'='*50}")

    if not dry_run:
        check_compliance_status()

    leads = db.get_leads_for_letters()
    if limit:
        leads = leads[:limit]

    if not leads:
        print("  No leads ready for letters.")
        return 0

    print(f"  {len(leads)} letters to send…")
    sent_count = 0
    blocked_count = 0

    for lead in leads:
        print(f"  -> {lead['first_name']} {lead['last_name']} (${lead['property_value']:,.0f})")
        result = send_letter(lead, dry_run=dry_run)
        if result["success"]:
            if not dry_run:
                db.mark_letter_sent(lead["id"])
            sent_count += 1
        elif result.get("blocked"):
            blocked_count += 1
            break  # no point looping if compliance gate is the blocker
        else:
            db.log_activity(lead["id"], f"Letter failed: {result.get('error','')}")
        time.sleep(1)

    if blocked_count:
        print("\n⛔ Letters blocked — CA compliance review required first.")
    else:
        print(f"\n✓ Letters complete — {sent_count}/{len(leads)} sent")
    return sent_count


def export_step():
    """Export leads to JSON for the Reclaim CA dashboard."""
    print(f"\n{'='*50}")
    print("STEP 4: EXPORTING TO DASHBOARD")
    print(f"{'='*50}")
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    path = f"{EXPORTS_DIR}/reclaim_ca_leads_export.json"
    leads = db.export_json(path)
    print(f"  ✓ Dashboard export ready at: {path}")
    return path


def run_full_pipeline(filepath, min_value, dry_run=False):
    print("\n" + "="*50)
    print("RECLAIM CA AUTOMATION PIPELINE — California SCO Workflow")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)

    db.init_db()
    check_compliance_status()

    loaded   = load_file_step(filepath, min_value)
    enriched = skip_trace_step()
    sent     = letters_step(dry_run=dry_run)
    path     = export_step()

    print("\n" + "="*50)
    print("PIPELINE SUMMARY")
    print("="*50)
    print(f"  Leads loaded from file:  {loaded}")
    print(f"  Skip traced:             {enriched}")
    print(f"  Letters sent:            {sent}")
    print(f"  Dashboard export:        {path}")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reclaim CA Automation Pipeline (California SCO Workflow)")
    parser.add_argument("--download", action="store_true", help="Download the SCO band ZIP first")
    parser.add_argument("--band", default=SCO_DATA_BAND, help="SCO value band to download (e.g. 500+)")
    parser.add_argument("--load-file", type=str, default=None, help="Path to a CA SCO data file (.zip/.csv)")
    parser.add_argument("--min-value", type=float, default=MIN_PROPERTY_VALUE)
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending real mail")
    parser.add_argument("--skip-trace-only", action="store_true")
    parser.add_argument("--letters-only", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--full", action="store_true", help="Run all steps in sequence")
    parser.add_argument("--limit", type=int, default=None, help="Max letters to send per run")
    args = parser.parse_args()

    db.init_db()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # A --download with no other action just fetches the file and reports the path.
    downloaded = download_step(args.band) if args.download else None

    if args.full:
        target = args.load_file or downloaded
        if not target:
            print("⛔ --full needs data: pass --download and/or --load-file <path>")
        else:
            run_full_pipeline(target, args.min_value, dry_run=args.dry_run)
    elif args.load_file or (downloaded and not any([args.skip_trace_only, args.letters_only, args.export])):
        load_file_step(args.load_file or downloaded, args.min_value)
    elif args.skip_trace_only:
        skip_trace_step()
    elif args.letters_only:
        letters_step(dry_run=args.dry_run, limit=args.limit)
    elif args.export:
        export_step()
    elif not args.download:
        parser.print_help()
