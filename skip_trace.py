"""
Skip Tracer -- Tracerfy API  (pay-as-you-go)
============================================
Tracerfy is pay-per-hit: $0.02/credit. The synchronous skip-trace lookup is
5 credits (~$0.10) per HIT, and misses are FREE (0 credits). No subscription.

    Sign up (no card):  https://www.tracerfy.com/auth/sign-up/
    API key:            Profile icon > Settings > API Key
    Add it as the TRACERFY_API_KEY secret in GitHub.

Endpoint: POST /v1/api/trace/lookup/  (synchronous, no polling)
Auth:     Authorization: Api-Key <YOUR_KEY>
Mode:     find_owner=false + first_name/last_name  -> find THIS person at/near the
          last-known address (rather than whoever owns that address now).

Response carries a top-level "hit" (true/false). On a hit, each person has phones
(with dnc / litigator / carrier / type / rank), emails, and a mailing address. We
pick the best reachable phone (prefer mobile, skip DNC + litigator numbers).

The first couple of raw responses are printed so we can confirm the exact shape;
if a hit ever parses empty, send me that printed JSON and it's a 2-minute fix.
Base URL / path / auth scheme are env-overridable if their docs ever change.
"""
import os
import json
import requests
from config import SKIPTRACE_API_KEY

BASE = os.getenv("TRACERFY_BASE_URL", "https://www.tracerfy.com/v1/api").rstrip("/")
LOOKUP_PATH = os.getenv("TRACERFY_LOOKUP_PATH", "/trace/lookup/")
LOOKUP_URL = f"{BASE}{LOOKUP_PATH}"
AUTH_HEADER = os.getenv("TRACERFY_AUTH_HEADER", "Authorization")
AUTH_SCHEME = os.getenv("TRACERFY_AUTH_SCHEME", "Bearer")   # Tracerfy docs: Authorization: Bearer <token>
API_KEY = (SKIPTRACE_API_KEY or "").strip()   # trim stray spaces/newlines from pasting

_raw_dumped = 0
_auth_diag_done = False


def _headers():
    value = f"{AUTH_SCHEME} {API_KEY}".strip() if AUTH_SCHEME else API_KEY
    return {AUTH_HEADER: value, "Content-Type": "application/json"}


def _auth_diagnostic():
    """Print once: what auth we're sending (never the key itself)."""
    global _auth_diag_done
    if _auth_diag_done:
        return
    _auth_diag_done = True
    raw = SKIPTRACE_API_KEY or ""
    ws = "  (trimmed surrounding whitespace!)" if raw != raw.strip() else ""
    print(f"  auth check -> header='{AUTH_HEADER}', scheme='{AUTH_SCHEME}', key_length={len(API_KEY)}{ws}")
    if not API_KEY:
        print("  !! API key is EMPTY after trimming - check the TRACERFY_API_KEY secret.")


def _persons(data):
    """Find the list of people in the response, tolerating key-name variations."""
    if not isinstance(data, dict):
        return []
    for key in ("persons", "people", "results", "owners", "matches", "data"):
        v = data.get(key)
        if isinstance(v, list) and v:
            return v
        if isinstance(v, dict):
            return [v]
    # The record itself might be the person.
    if any(k in data for k in ("phones", "emails", "mailingAddress", "mailing_address")):
        return [data]
    return []


def _best_phone(person):
    phones = person.get("phones") or person.get("phoneNumbers") or []
    if isinstance(phones, str):
        return phones
    def num(p):
        return (p.get("number") or p.get("phoneNumber") or p.get("phone") or "") if isinstance(p, dict) else str(p)
    def ok(p):  # reachable = not DNC and not litigator
        return isinstance(p, dict) and not p.get("dnc") and not p.get("litigator")
    def mobile(p):
        return isinstance(p, dict) and str(p.get("type", "")).lower() in ("mobile", "cell", "wireless")
    for pred in (lambda p: ok(p) and mobile(p), ok, mobile, lambda p: True):
        for p in phones:
            if pred(p) and num(p):
                return num(p)
    return ""


def _best_email(person):
    emails = person.get("emails") or person.get("emailAddresses") or []
    if isinstance(emails, str):
        return emails
    for e in emails:
        addr = (e.get("email") or e.get("address")) if isinstance(e, dict) else e
        if addr:
            return str(addr)
    return ""


def _mailing(person):
    a = (person.get("mailingAddress") or person.get("mailing_address")
         or person.get("address") or {})
    if not isinstance(a, dict):
        a = {}
    def g(*names):
        for n in names:
            if a.get(n):
                return a[n]
        return ""
    return {
        "address": g("address", "line1", "street", "streetAddress"),
        "city": g("city"),
        "state": g("state"),
        "zip": g("zip_code", "zip", "postalCode", "zipCode"),
    }


def skip_trace_lead(lead: dict):
    """One synchronous Tracerfy lookup. Returns enriched contact dict or None."""
    global _raw_dumped
    _auth_diagnostic()
    if not API_KEY:
        print("  TRACERFY_API_KEY not set - skip trace skipped")
        return None

    payload = {
        "find_owner": False,   # search for THIS person, not the current address owner
        "first_name": lead.get("first_name", ""),
        "last_name": lead.get("last_name", ""),
        "address": lead.get("address", ""),
        "city": lead.get("city", ""),
        "state": lead.get("state", "") or lead.get("property_state", ""),
        "zip": lead.get("zip", ""),
    }

    try:
        resp = requests.post(LOOKUP_URL, json=payload, headers=_headers(), timeout=30)
    except Exception as e:
        print(f"  Tracerfy error: {e}")
        return None

    if resp.status_code not in (200, 201):
        print(f"  Tracerfy: HTTP {resp.status_code} - {resp.text[:200]}")
        return None

    try:
        data = resp.json()
    except Exception:
        print(f"  Tracerfy: non-JSON response - {resp.text[:200]}")
        return None

    if _raw_dumped < 2:
        print("  -- raw Tracerfy response (for calibration) --")
        print("  " + json.dumps(data)[:1200])
        print("  ---------------------------------------------")
        _raw_dumped += 1

    name = f"{lead.get('first_name','')} {lead.get('last_name','')}".strip()

    # Explicit miss.
    if isinstance(data, dict) and data.get("hit") is False:
        print(f"  Tracerfy: no match for {name}")
        return None

    people = _persons(data)
    if not people:
        print(f"  Tracerfy: no match for {name}")
        return None

    person = people[0]
    m = _mailing(person)
    enriched = {
        "phone": _best_phone(person),
        "email": _best_email(person),
        "address": m["address"], "city": m["city"], "state": m["state"], "zip": m["zip"],
    }
    if not (enriched["phone"] or enriched["email"] or enriched["address"]):
        print(f"  Tracerfy: matched but no contact parsed for {name} - send me the raw JSON above.")
        return None

    print(f"  Tracerfy: OK {name} -> {enriched['phone'] or 'no phone'}")
    return enriched


def skip_trace_batch(leads: list) -> list:
    """Sync endpoint is one-at-a-time, so loop. Returns [(lead, enriched|None)]."""
    if not API_KEY:
        print("  TRACERFY_API_KEY not set")
        return [(l, None) for l in leads]
    paired = [(lead, skip_trace_lead(lead)) for lead in leads]
    matched = sum(1 for _, e in paired if e)
    print(f"  Tracerfy: {matched}/{len(leads)} matched")
    return paired
