"""
Reclaim CA Automation — Configuration
Copy .env.example to .env and fill in your keys.

CALIFORNIA WORKFLOW. This pipeline pulls the California State Controller's
Office (SCO) public unclaimed-property database and operates under the
California Unclaimed Property Law (Code of Civil Procedure §§ 1500 et seq.),
NOT the Georgia CDR regime the earlier "Found" build was written for.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ────────────────────────────────────────────────────────────────
BATCHDATA_API_KEY   = os.getenv("BATCHDATA_API_KEY", "")
# Skip-trace provider key (Tracerfy). Falls back to legacy names.
SKIPTRACE_API_KEY   = (os.getenv("TRACERFY_API_KEY", "")
                       or os.getenv("SKIPTRACE_API_KEY", "")
                       or os.getenv("BATCHDATA_API_KEY", ""))
POSTGRID_API_KEY    = os.getenv("POSTGRID_API_KEY", "")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")

# ── Your Business Info (goes in letters + agreements) ───────────────────────
AGENT_NAME          = os.getenv("AGENT_NAME", "Your Name")
AGENT_COMPANY       = os.getenv("AGENT_COMPANY", "Reclaim CA")
AGENT_PHONE         = os.getenv("AGENT_PHONE", "555-000-0000")
AGENT_EMAIL         = os.getenv("AGENT_EMAIL", "you@reclaimca.com")
AGENT_ADDRESS       = os.getenv("AGENT_ADDRESS", "123 Main St")
AGENT_CITY_STATE    = os.getenv("AGENT_CITY_STATE", "Carlsbad, CA 92008")

# ── Pipeline Settings ───────────────────────────────────────────────────────
# California caps investigator/locator fees at 10% (CCP § 1582), so the default
# fee IS the cap. See CA_FEE_CAP below — the cap is enforced as a hard ceiling
# in agreement.py, not merely a default.
DEFAULT_FEE_PERCENT = float(os.getenv("DEFAULT_FEE_PERCENT", "10"))
MIN_PROPERTY_VALUE  = float(os.getenv("MIN_PROPERTY_VALUE", "500"))   # skip anything below this
TARGET_STATES       = os.getenv("TARGET_STATES", "CA").split(",")

# ── California Unclaimed Property Compliance ────────────────────────────────
# CCP § 1582 caps an investigator/heir-finder fee at 10% of the recovered
# property. This is a HARD statutory ceiling (the only carve-out is County
# Probated Estates, which is a fact-specific legal call and is NOT auto-applied
# here). agreement.py clamps every fee to this number with no override.
CA_FEE_CAP          = 10.0   # CCP § 1582 — max 10% of recovered property

# California does NOT have a Georgia-style CDR registration number. Locators
# operate under CCP §§ 1580–1582. The old CDR_REG_NUMBER gate is retired.
# Instead we gate real sends behind an explicit "compliance reviewed" flag you
# set only AFTER a California attorney signs off on your agreement/letter
# language and confirms your licensing status (see CA_COMPLIANCE.md).
CA_COMPLIANCE_OK    = os.getenv("CA_COMPLIANCE_OK", "").strip().lower() in ("1", "true", "yes")

# ── California SCO Bulk Data Source ─────────────────────────────────────────
# The SCO publishes its full public database as ZIP-wrapped CSV files, refreshed
# every Thursday. Value-banded files let us skip the giant "all records" file.
# Landing page: https://www.sco.ca.gov/upd_download_property_records.html
SCO_DATA_BASE_URL   = os.getenv(
    "SCO_DATA_BASE_URL", "https://claimit.ca.gov/upd-property-records"
)
SCO_DATA_FILES = {
    "0-10":     "01_From_0_To_Below_10.zip",
    "10-100":   "02_From_10_To_Below_100.zip",
    "100-500":  "03_From_100_To_Below_500.zip",
    "500+":     "04_From_500_To_Beyond.zip",
    "all":      "00_All_Records.zip",
}
# Default to the $500-and-up band since MIN_PROPERTY_VALUE is 500.
SCO_DATA_BAND       = os.getenv("SCO_DATA_BAND", "500+")
SCO_DATA_DIR        = os.getenv("SCO_DATA_DIR", "data/sco")   # where downloads land

# ── File Paths ───────────────────────────────────────────────────────────────
DB_PATH             = os.getenv("DB_PATH", "reclaim_ca.db")
OUTPUT_DIR          = os.getenv("OUTPUT_DIR", "output")
AGREEMENTS_DIR      = f"{OUTPUT_DIR}/agreements"
LETTERS_DIR         = f"{OUTPUT_DIR}/letters"
EXPORTS_DIR         = f"{OUTPUT_DIR}/exports"

# ── PostGrid ─────────────────────────────────────────────────────────────────
POSTGRID_FROM_NAME  = AGENT_NAME
POSTGRID_FROM_LINE1 = AGENT_ADDRESS
POSTGRID_FROM_CITY  = AGENT_CITY_STATE.split(",")[0].strip()
POSTGRID_FROM_STATE = AGENT_CITY_STATE.split(",")[1].strip()[:2] if "," in AGENT_CITY_STATE else "CA"
POSTGRID_FROM_ZIP   = AGENT_CITY_STATE.split()[-1] if AGENT_CITY_STATE else "92008"
POSTGRID_FROM_COUNTRY = "US"
