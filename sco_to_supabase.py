"""
Reclaim CA — CA SCO → Supabase ingest  (Phase 2)
================================================
Runs on a schedule (GitHub Actions). Downloads the California State Controller's
public unclaimed-property band, parses it, and inserts the top new high-value
leads into the SAME Supabase `leads` table your dashboard reads.

Two safety rules baked in:
  1. INSERT-ONLY. Uses "on conflict do nothing", so it can NEVER overwrite a
     lead you've already been working in the dashboard. It only adds brand-new
     ones it hasn't seen before.
  2. CAPPED + RANKED. The raw band has far more records than anyone can work (or
     store on a free tier), so each run adds only the top `INGEST_MAX_NEW` NEW
     leads by value. Highest-value first. Raise the cap as you scale.

Environment variables (set as GitHub Actions secrets / repo variables):
  SUPABASE_URL           your project URL  (https://xxxx.supabase.co)
  SUPABASE_SERVICE_KEY   the SERVICE ROLE secret key — server-side only, never
                         in a browser. (GitHub Actions secrets are encrypted.)
  INGEST_MAX_NEW         max new leads to add per run           (default 500)
  MIN_PROPERTY_VALUE     value floor, from config               (default 500)
  SCO_DATA_BAND          which value band to pull, from config  (default 500+)

Usage:
  python sco_to_supabase.py --download           # weekly job: download + ingest
  python sco_to_supabase.py --file some.zip       # parse an already-downloaded file
  python sco_to_supabase.py --download --dry-run  # see what it WOULD add, write nothing
"""
import os
import re
import sys
import heapq
import hashlib
import itertools
import argparse
from datetime import date

from config import MIN_PROPERTY_VALUE, SCO_DATA_BAND
from ca_sco_parser import parse_sco_file, download_sco_data

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
INGEST_MAX_NEW = int(os.getenv("INGEST_MAX_NEW", "500"))


def lead_id_for(rec):
    """Deterministic id so re-running weekly recognizes the same record and
    doesn't add it twice. Prefer the SCO property id; fall back to a hash."""
    pid = (rec.get("property_id") or "").strip()
    if pid:
        return "casco_" + re.sub(r"[^A-Za-z0-9_-]", "", pid)
    basis = "{}|{}|{}|{:.2f}".format(
        rec.get("first_name", ""), rec.get("last_name", ""),
        rec.get("holding_entity", ""), float(rec.get("property_value") or 0))
    return "casco_h_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def to_dashboard_lead(rec, lid):
    """Map a parser record (snake_case) into the exact shape the dashboard reads."""
    value = float(rec.get("property_value") or 0)
    today = date.today().isoformat()
    return {
        "id": lid,
        "firstName": rec.get("first_name", ""),
        "lastName": rec.get("last_name", ""),
        "phone": rec.get("phone", ""),
        "email": rec.get("email", ""),
        "address": rec.get("address", ""),
        "city": rec.get("city", ""),
        "state": rec.get("state", ""),
        "zip": rec.get("zip", ""),
        "propertyType": rec.get("property_type", "Unclaimed Property"),
        "propertyValue": value,
        "propertyState": rec.get("property_state", "CA"),
        "holdingEntity": rec.get("holding_entity", ""),
        "propertyId": rec.get("property_id", ""),
        "stage": "lead",
        "feePercent": 10,
        "feeAmount": round(value * 0.10),
        "outreachLog": [],
        "docs": {"agreementSigned": False, "idVerified": False,
                 "proofOfOwnership": False, "claimSubmitted": False,
                 "paymentReceived": False},
        "paidDate": None,
        "source": rec.get("source", "CA SCO Public Data File"),
        "leadDate": today,
        "notes": rec.get("notes", ""),
        "activity": [{"date": today, "action": "Imported from CA SCO data"}],
        "aiNotes": "",
    }


def make_client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        sys.exit("✗ Missing SUPABASE_URL or SUPABASE_SERVICE_KEY. Set them as "
                 "GitHub Actions secrets (see PHASE2_SETUP.md).")
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def fetch_existing_ids(client):
    """Pull every id already in the leads table so we never re-add one."""
    existing, frm, PAGE = set(), 0, 1000
    while True:
        res = client.table("leads").select("id").range(frm, frm + PAGE - 1).execute()
        batch = res.data or []
        existing.update(r["id"] for r in batch)
        if len(batch) < PAGE:
            break
        frm += PAGE
    return existing


def pick_top_new(records, existing_ids, max_new):
    """Stream all qualifying records and keep only the top `max_new` NEW leads
    by value. Uses a bounded heap so memory stays flat even on the full file."""
    heap = []                       # (value, tiebreak, id, record)
    counter = itertools.count()
    kept_ids = set()
    for rec in records:
        lid = lead_id_for(rec)
        if lid in existing_ids or lid in kept_ids:
            continue
        value = float(rec.get("property_value") or 0)
        item = (value, next(counter), lid, rec)
        if len(heap) < max_new:
            heapq.heappush(heap, item)
            kept_ids.add(lid)
        elif value > heap[0][0]:
            popped = heapq.heappushpop(heap, item)
            kept_ids.discard(popped[2])
            kept_ids.add(lid)
    top = sorted(heap, key=lambda x: x[0], reverse=True)   # highest value first
    return [to_dashboard_lead(rec, lid) for (_v, _c, lid, rec) in top]


def insert_new(client, leads):
    """Insert-only (on conflict do nothing) in batches — never overwrites."""
    rows = [{"id": l["id"], "data": l} for l in leads]
    for i in range(0, len(rows), 500):
        client.table("leads").upsert(
            rows[i:i + 500], on_conflict="id", ignore_duplicates=True
        ).execute()
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Ingest CA SCO leads into Supabase")
    ap.add_argument("--download", action="store_true", help="Download the SCO band first")
    ap.add_argument("--band", default=SCO_DATA_BAND)
    ap.add_argument("--file", default=None, help="Parse an already-downloaded .zip/.csv")
    ap.add_argument("--min-value", type=float, default=MIN_PROPERTY_VALUE)
    ap.add_argument("--max-new", type=int, default=INGEST_MAX_NEW)
    ap.add_argument("--dry-run", action="store_true", help="Show what would be added; write nothing")
    args = ap.parse_args()

    target = args.file
    if args.download or not target:
        target = download_sco_data(band=args.band)

    client = None if args.dry_run else make_client()
    existing = set() if args.dry_run else fetch_existing_ids(client)
    print(f"→ {len(existing):,} leads already in the database.")

    print(f"→ Parsing {target} (min ${args.min_value:,.0f}, keeping top {args.max_new} by value)…")
    new_leads = pick_top_new(parse_sco_file(target, min_value=args.min_value),
                             existing, args.max_new)
    print(f"→ Selected {len(new_leads)} new lead(s).")

    if args.dry_run:
        for l in new_leads[:10]:
            print(f"    {l['firstName']} {l['lastName']} — {l['propertyType']} — ${l['propertyValue']:,.0f}")
        print("  (dry run — nothing written)")
        return

    n = insert_new(client, new_leads)
    print(f"✓ Ingest complete — added up to {n} new lead(s). They're in your dashboard now.")


if __name__ == "__main__":
    main()
