"""
Skip Tracer — BatchData API
Takes a lead with just a name, returns current address + phone.
BatchData API docs: https://batchdata.io/docs
"""
import requests
from config import BATCHDATA_API_KEY

BATCH_URL = "https://api.batchdata.io/api/v1"

def skip_trace_lead(lead: dict) -> dict | None:
    """
    Given a lead dict with first_name / last_name (+ optional last known address),
    return enriched contact info or None if no match found.
    """
    if not BATCHDATA_API_KEY:
        print("  ⚠ BATCHDATA_API_KEY not set — skip trace skipped")
        return None

    headers = {
        "Authorization": f"Bearer {BATCHDATA_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "requests": [{
            "firstName":  lead.get("first_name",""),
            "lastName":   lead.get("last_name",""),
            "address":    lead.get("address",""),
            "city":       lead.get("city",""),
            "state":      lead.get("state","") or lead.get("property_state",""),
            "zip":        lead.get("zip",""),
        }]
    }

    try:
        resp = requests.post(
            f"{BATCH_URL}/person/skip-trace",
            json=payload, headers=headers, timeout=20
        )
        if resp.status_code != 200:
            print(f"  BatchData: HTTP {resp.status_code} — {resp.text[:200]}")
            return None

        data = resp.json()
        results = (data.get("results") or data.get("responses") or [{}])
        result = results[0] if results else {}

        if not result or result.get("matchStatus") == "no_match":
            print(f"  BatchData: no match for {lead['first_name']} {lead['last_name']}")
            return None

        # Extract best phone
        phones = result.get("phones") or []
        best_phone = ""
        for p in phones:
            if p.get("type") in ("mobile","cell") and p.get("dnc") is False:
                best_phone = p.get("phoneNumber",""); break
        if not best_phone and phones:
            best_phone = phones[0].get("phoneNumber","")

        # Extract best address
        addresses = result.get("addresses") or []
        best_addr = addresses[0] if addresses else {}

        enriched = {
            "phone":   best_phone,
            "email":   (result.get("emails") or [{}])[0].get("email",""),
            "address": best_addr.get("address","") or best_addr.get("line1",""),
            "city":    best_addr.get("city",""),
            "state":   best_addr.get("state",""),
            "zip":     best_addr.get("zip","") or best_addr.get("postalCode",""),
        }
        print(f"  BatchData: ✓ matched {lead['first_name']} {lead['last_name']} → {best_phone or 'no phone'}")
        return enriched

    except Exception as e:
        print(f"  BatchData error: {e}")
        return None


def skip_trace_batch(leads: list) -> list:
    """
    Skip trace up to 100 leads in a single BatchData call (more efficient).
    Returns list of (lead, enriched_or_None) tuples.
    """
    if not BATCHDATA_API_KEY:
        print("  ⚠ BATCHDATA_API_KEY not set")
        return [(l, None) for l in leads]

    headers = {
        "Authorization": f"Bearer {BATCHDATA_API_KEY}",
        "Content-Type": "application/json",
    }

    requests_payload = []
    for lead in leads:
        requests_payload.append({
            "firstName": lead.get("first_name",""),
            "lastName":  lead.get("last_name",""),
            "state":     lead.get("property_state",""),
        })

    try:
        resp = requests.post(
            f"{BATCH_URL}/person/skip-trace",
            json={"requests": requests_payload},
            headers=headers, timeout=60
        )
        if resp.status_code != 200:
            print(f"  BatchData batch: HTTP {resp.status_code}")
            return [(l, None) for l in leads]

        data = resp.json()
        results = data.get("results") or data.get("responses") or []

        paired = []
        for i, lead in enumerate(leads):
            result = results[i] if i < len(results) else {}
            if not result or result.get("matchStatus") == "no_match":
                paired.append((lead, None))
                continue

            phones = result.get("phones") or []
            best_phone = ""
            for p in phones:
                if p.get("type") in ("mobile","cell"):
                    best_phone = p.get("phoneNumber",""); break
            if not best_phone and phones:
                best_phone = phones[0].get("phoneNumber","")

            addresses = result.get("addresses") or []
            best_addr = addresses[0] if addresses else {}

            enriched = {
                "phone":   best_phone,
                "email":   (result.get("emails") or [{}])[0].get("email",""),
                "address": best_addr.get("address","") or best_addr.get("line1",""),
                "city":    best_addr.get("city",""),
                "state":   best_addr.get("state",""),
                "zip":     best_addr.get("zip","") or best_addr.get("postalCode",""),
            }
            paired.append((lead, enriched))

        matched = sum(1 for _, e in paired if e)
        print(f"  BatchData batch: {matched}/{len(leads)} matched")
        return paired

    except Exception as e:
        print(f"  BatchData batch error: {e}")
        return [(l, None) for l in leads]
