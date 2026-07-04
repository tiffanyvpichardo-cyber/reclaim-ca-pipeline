"""
California SCO Unclaimed Property Data Parser + Downloader
==========================================================
Replaces the Georgia CDR bulk-file parser (ucp_file_parser.py).

Unlike Georgia — which gates its bulk file behind CDR registration — California
publishes its ENTIRE public unclaimed-property database for free, as ZIP-wrapped
CSV files, refreshed every Thursday:

    https://www.sco.ca.gov/upd_download_property_records.html

Files (hosted on claimit.ca.gov), banded by reported value:
    01_From_0_To_Below_10.zip
    02_From_10_To_Below_100.zip
    03_From_100_To_Below_500.zip
    04_From_500_To_Beyond.zip     <- default (matches MIN_PROPERTY_VALUE = 500)
    00_All_Records.zip            <- everything (very large)

Typical weekly use (run every Thursday, after the SCO refresh):
    python ca_sco_parser.py --download --band 500+
    python ca_sco_parser.py --file data/sco/2026-07-02_04_From_500_To_Beyond.zip --min-value 500

The parser streams the CSV row-by-row straight out of the ZIP, so the multi-
hundred-MB file is never fully loaded into memory.

⚠ COLUMN MAPPING: The default column names below reflect the CA SCO public CSV
layout as commonly documented, but the SCO can change headers without notice.
On the first run the parser prints the ACTUAL header it found and warns if it
doesn't line up — verify once against a freshly downloaded file and adjust
COLUMN_ALIASES if needed.
"""
import csv
import io
import sys
import zipfile
import argparse
from datetime import date
from pathlib import Path

import requests

from config import (
    SCO_DATA_BASE_URL, SCO_DATA_FILES, SCO_DATA_BAND, SCO_DATA_DIR,
    MIN_PROPERTY_VALUE, CA_FEE_CAP,
)

# CSV parses very wide rows; lift the field-size limit so a fat row never crashes.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

# ── Column mapping ───────────────────────────────────────────────────────────
# Left = the internal key we use. Right = candidate header names in the SCO CSV
# (checked case-insensitively, first match wins). Add aliases here if the SCO
# renames a column.
COLUMN_ALIASES = {
    "property_id":     ["PROPERTY_ID", "PROPERTYID", "PROPERTY_ID_NUMBER"],
    "owner_name":      ["OWNER_NAME", "OWNERNAME", "OWNER_FULL_NAME"],
    "owner_last":      ["OWNER_LAST_NAME", "OWNER_LASTNAME", "LAST_NAME"],
    "owner_first":     ["OWNER_FIRST_NAME", "OWNER_FIRSTNAME", "FIRST_NAME"],
    "owner_street":    ["OWNER_STREET_1", "OWNER_STREET1", "OWNER_ADDRESS", "OWNER_STREET"],
    "owner_city":      ["OWNER_CITY", "OWNERCITY"],
    "owner_state":     ["OWNER_STATE", "OWNERSTATE"],
    "owner_zip":       ["OWNER_ZIP", "OWNERZIP", "OWNER_ZIP_CODE"],
    "cash_current":    ["CURRENT_CASH_BALANCE", "CURRENTCASHBALANCE", "CASH_BALANCE"],
    "cash_reported":   ["CASH_REPORTED", "CASHREPORTED", "AMOUNT_REPORTED"],
    "property_type":   ["PROPERTY_TYPE", "PROPERTYTYPE", "PROPERTY_TYPE_CODE"],
    "holder_name":     ["HOLDER_NAME", "HOLDERNAME", "BUSINESS_NAME"],
    "shares":          ["SHARES_REPORTED", "NO_OF_SHARES", "NUMBER_OF_SHARES"],
    "pending_claims":  ["NUMBER_OF_PENDING_CLAIMS", "PENDING_CLAIMS"],
    "paid_claims":     ["NUMBER_OF_PAID_CLAIMS", "PAID_CLAIMS"],
}

# Human-readable labels for the SCO's terse property-type codes. Unknown codes
# pass through unchanged; extend as you learn the SCO's code list.
PROPERTY_TYPE_LABELS = {
    "AC": "Bank Account", "CK": "Uncashed Check", "IN": "Insurance Policy",
    "SC": "Stocks / Securities", "WG": "Wages / Payroll", "UT": "Utility Deposit",
    "SD": "Safe Deposit Box", "MS": "Miscellaneous",
}


def _build_header_map(fieldnames):
    """Map our internal keys -> the actual column name present in this file."""
    present = {c.strip().upper(): c for c in (fieldnames or [])}
    resolved = {}
    for key, candidates in COLUMN_ALIASES.items():
        for cand in candidates:
            if cand.upper() in present:
                resolved[key] = present[cand.upper()]
                break
    return resolved


def _get(row, header_map, key, default=""):
    col = header_map.get(key)
    if not col:
        return default
    return (row.get(col) or "").strip()


def _parse_value(s):
    if not s:
        return 0.0
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except ValueError:
        return 0.0


def _split_name(row, header_map):
    """
    CA SCO usually ships a single OWNER_NAME field. Common formats:
      "LAST FIRST MIDDLE"  |  "LAST, FIRST"  |  a business/entity name.
    Prefer explicit first/last columns if they exist.
    """
    first = _get(row, header_map, "owner_first")
    last = _get(row, header_map, "owner_last")
    if first or last:
        return first, last

    full = _get(row, header_map, "owner_name")
    if not full:
        return "", ""
    if "," in full:                       # "LAST, FIRST ..."
        last_part, first_part = full.split(",", 1)
        return first_part.strip(), last_part.strip()
    parts = full.split()
    if len(parts) >= 2:                    # assume "LAST FIRST [MIDDLE]"
        return " ".join(parts[1:]), parts[0]
    return "", full                        # single token → treat as entity/last


def _label_property_type(code):
    if not code:
        return "Unclaimed Property"
    return PROPERTY_TYPE_LABELS.get(code.strip().upper(), code.strip())


def _open_csv_streams(zip_path):
    """Yield (member_name, text_stream) for every .csv inside the ZIP."""
    zf = zipfile.ZipFile(zip_path)
    csv_members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not csv_members:
        # Some SCO bundles name the file without .csv — fall back to the largest member.
        csv_members = sorted(zf.namelist(), key=lambda n: zf.getinfo(n).file_size, reverse=True)[:1]
    for member in csv_members:
        raw = zf.open(member, "r")
        yield member, io.TextIOWrapper(raw, encoding="utf-8", errors="ignore")


# ── Parse ────────────────────────────────────────────────────────────────────
def parse_sco_file(filepath, min_value=MIN_PROPERTY_VALUE, state_code="CA"):
    """
    Stream-parse a downloaded CA SCO file (.zip of CSV, or a plain .csv) and
    yield lead dicts for records at/above min_value. Generator — safe on the
    full multi-hundred-MB file.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(
            f"SCO data file not found at {filepath}. Download it first:\n"
            f"    python ca_sco_parser.py --download --band {SCO_DATA_BAND}"
        )

    is_zip = zipfile.is_zipfile(path)
    streams = _open_csv_streams(path) if is_zip else [(path.name, open(path, "r", encoding="utf-8", errors="ignore"))]

    count_total = 0
    count_qualified = 0
    warned = False

    for member, stream in streams:
        print(f"  Parsing {member} …")
        reader = csv.DictReader(stream)
        header_map = _build_header_map(reader.fieldnames)

        if not warned and len(header_map) < 3:
            print("  ⚠ WARNING: file headers don't match the expected CA SCO layout.")
            print(f"    Headers found: {reader.fieldnames}")
            print("    Update COLUMN_ALIASES in ca_sco_parser.py to match, then re-run.")
            warned = True

        for row in reader:
            count_total += 1

            # Prefer current balance; fall back to originally reported cash.
            value = _parse_value(_get(row, header_map, "cash_current"))
            if value <= 0:
                value = _parse_value(_get(row, header_map, "cash_reported"))
            if value < min_value:
                continue

            # Skip anything already paid out. (CA doesn't publish a claim status
            # column; a paid-claims count > 0 is the closest signal.)
            paid = _parse_value(_get(row, header_map, "paid_claims"))
            if paid and paid > 0:
                continue

            first_name, last_name = _split_name(row, header_map)
            if not (first_name or last_name):
                continue

            count_qualified += 1
            yield {
                "first_name": first_name,
                "last_name": last_name,
                "property_type": _label_property_type(_get(row, header_map, "property_type")),
                "property_value": value,
                "property_state": state_code,           # always CA for this pipeline
                "holding_entity": _get(row, header_map, "holder_name"),
                "property_id": _get(row, header_map, "property_id"),
                "source": "CA SCO Public Data File",
                "stage": "new",
                "fee_percent": CA_FEE_CAP,              # 10% — CCP § 1582
                "phone": "", "email": "",
                "address": _get(row, header_map, "owner_street"),  # last known, usually stale
                "city": _get(row, header_map, "owner_city"),
                "state": _get(row, header_map, "owner_state"),
                "zip": _get(row, header_map, "owner_zip"),
                "notes": "Imported from CA SCO public database.",
            }

        stream.close()

    print(f"  ✓ Parsed {count_total:,} records, {count_qualified:,} qualified "
          f"(>= ${min_value:,.0f}, unpaid)")


# ── Download ─────────────────────────────────────────────────────────────────
def download_sco_data(band=None, dest_dir=None):
    """
    Download one SCO value-band ZIP. Saves as <YYYY-MM-DD>_<original>.zip so
    weekly Thursday pulls don't overwrite each other. Returns the saved path.
    """
    band = band or SCO_DATA_BAND
    dest_dir = dest_dir or SCO_DATA_DIR
    if band not in SCO_DATA_FILES:
        raise ValueError(f"Unknown band '{band}'. Choose one of: {', '.join(SCO_DATA_FILES)}")

    fname = SCO_DATA_FILES[band]
    url = f"{SCO_DATA_BASE_URL}/{fname}"
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(dest_dir) / f"{date.today().isoformat()}_{fname}"

    print(f"  Downloading SCO band '{band}' → {url}")
    print("  (These files are large; a broadband connection is recommended.)")
    with requests.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):  # 1 MB
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done / total * 100
                    print(f"\r  {done/1e6:,.1f} / {total/1e6:,.1f} MB ({pct:4.1f}%)", end="")
        print()
    print(f"  ✓ Saved {out_path}")
    return str(out_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="California SCO unclaimed-property data tool")
    ap.add_argument("--download", action="store_true", help="Download the SCO band ZIP first")
    ap.add_argument("--band", default=SCO_DATA_BAND, choices=list(SCO_DATA_FILES),
                    help="Value band to download (default from config)")
    ap.add_argument("--file", default=None, help="Path to a downloaded SCO .zip/.csv to parse")
    ap.add_argument("--min-value", type=float, default=MIN_PROPERTY_VALUE)
    ap.add_argument("--load-db", action="store_true", help="Insert parsed leads into the database")
    args = ap.parse_args()

    target = args.file
    if args.download:
        target = download_sco_data(band=args.band)

    if not target:
        ap.error("Nothing to parse. Pass --download and/or --file.")

    if args.load_db:
        import db
        db.init_db()
        inserted = 0
        for lead in parse_sco_file(target, min_value=args.min_value):
            lead_id = db.upsert_lead(lead)
            db.log_activity(lead_id, "Lead loaded from CA SCO data file")
            inserted += 1
        print(f"\n✓ Inserted {inserted} leads into database")
    else:
        # Dry preview: count + show the first few.
        preview = []
        for i, lead in enumerate(parse_sco_file(target, min_value=args.min_value)):
            if i < 5:
                preview.append(f"    {lead['first_name']} {lead['last_name']} — "
                               f"{lead['property_type']} — ${lead['property_value']:,.2f} "
                               f"(held by {lead['holding_entity'] or 'unknown'})")
        print("\n  Sample of qualified leads:")
        print("\n".join(preview) if preview else "    (none)")
        print("\n  Re-run with --load-db to insert these into the database.")
