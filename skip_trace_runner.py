"""
Reclaim CA — Skip-trace runner  (Phase 3)
=========================================
Reads the leads you flagged in the dashboard (Request skip trace → skipTrace ==
"requested"), looks up current phone / email / address via BatchData, writes the
results back into the same lead, and marks it traced.

This is the FIRST step that spends money, so it is:
  * MANUAL — runs only when you click "Run workflow" (no schedule).
  * SCOPED — touches ONLY the leads you flagged, nothing else.
  * MERGING — it fills in contact fields + a status; it never wipes your notes,
    stage, or anything else on the lead.

Env (GitHub Actions secrets):
  SUPABASE_URL, SUPABASE_SERVICE_KEY   your project + secret (service_role) key
  BATCHDATA_API_KEY                    your skip-trace provider key
  SKIP_TRACE_MAX                       safety cap on leads per run (default 200)
"""
import os
import sys
from datetime import date

from skip_trace import skip_trace_batch   # existing BatchData integration

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
SKIP_TRACE_MAX = int(os.getenv("SKIP_TRACE_MAX", "200"))
CHUNK = 100   # BatchData handles up to 100 per call


def make_client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        sys.exit("✗ Missing SUPABASE_URL or SUPABASE_SERVICE_KEY.")
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def fetch_requested(client, limit):
    """Leads the user flagged in the dashboard: data->>skipTrace == 'requested'."""
    res = (client.table("leads").select("*")
           .filter("data->>skipTrace", "eq", "requested")
           .limit(limit).execute())
    return res.data or []


def to_trace_input(lead):
    """Dashboard lead (camelCase) -> the shape skip_trace.py expects (snake)."""
    return {
        "first_name": lead.get("firstName", ""),
        "last_name": lead.get("lastName", ""),
        "address": lead.get("address", ""),
        "city": lead.get("city", ""),
        "state": lead.get("state", "") or lead.get("propertyState", "CA"),
        "zip": lead.get("zip", ""),
        "property_state": lead.get("propertyState", "CA"),
    }


def apply_result(data, enriched):
    """Merge enriched contact info into the lead, preserving everything else."""
    today = date.today().isoformat()
    if enriched:
        for k in ("phone", "email", "address", "city", "state", "zip"):
            if enriched.get(k):
                data[k] = enriched[k]
        data["skipTrace"] = "done"
        data["activity"] = (data.get("activity") or []) + [
            {"date": today, "action": "Skip traced — contact info updated"}]
    else:
        data["skipTrace"] = "no_match"
        data["activity"] = (data.get("activity") or []) + [
            {"date": today, "action": "Skip trace — no match found"}]
    return data


def main():
    client = make_client()
    rows = fetch_requested(client, SKIP_TRACE_MAX)
    print(f"→ {len(rows)} lead(s) flagged for skip trace.")
    if not rows:
        print("  Nothing to do. Flag leads in the dashboard first "
              "(open a lead → Request skip trace).")
        return

    matched = updated = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        pairs = skip_trace_batch([to_trace_input(r["data"]) for r in chunk])
        for row, (_inp, enriched) in zip(chunk, pairs):
            data = apply_result(row["data"], enriched)
            if enriched:
                matched += 1
            client.table("leads").update({"data": data}).eq("id", row["id"]).execute()
            updated += 1

    print(f"✓ Skip trace complete — {matched}/{len(rows)} matched, {updated} updated. "
          f"Fresh contact info is in your dashboard now.")


if __name__ == "__main__":
    main()
