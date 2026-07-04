# Reclaim CA Automation Pipeline

Automation stack for California unclaimed-property recovery — from the State
Controller's Office (SCO) public data download, through skip tracing, to
compliant letters and agreements.

> California workflow. Operates under the California Unclaimed Property Law
> (CCP §§ 1500–1582). Fees are hard-capped at 10% (CCP § 1582). See
> `CA_COMPLIANCE.md` before sending anything real.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Fill in your API keys and business info

# 3. Preview with a dry run (no real mail sent, no compliance flag needed)
python pipeline.py --download --band 500+
python pipeline.py --load-file data/sco/<downloaded-file>.zip
python pipeline.py --letters-only --dry-run
```

## Pipeline Steps

```
California SCO public database  (updated every Thursday)
       |  ca_sco_parser.py  --download  (ZIP of CSV, value-banded)
       v
   ca_sco_parser.py     <- parses the SCO file, filters by min value
       |
   skip_trace.py        <- BatchData API -> current address + phone
       |
   mailer.py            <- PostGrid API -> physical letter (CA disclosures)
       |
   agreement.py         <- PDF recovery agreement, 10% cap (CCP 1582)
       |
   dashboard export     <- syncs to the Reclaim CA dashboard
```

## Weekly run (Thursdays, after the SCO refresh)

```bash
# One shot: download the $500+ band, then run everything
python pipeline.py --full --download --band 500+ --dry-run

# Or step by step
python pipeline.py --download --band 500+
python pipeline.py --load-file data/sco/2026-07-02_04_From_500_To_Beyond.zip
python pipeline.py --skip-trace-only
python pipeline.py --letters-only --limit 20 --dry-run
python pipeline.py --export
```

## SCO data bands

| Band | File | Notes |
|---|---|---|
| `500+` | `04_From_500_To_Beyond.zip` | Default — matches MIN_PROPERTY_VALUE=500 |
| `100-500` | `03_From_100_To_Below_500.zip` | |
| `10-100` | `02_From_10_To_Below_100.zip` | |
| `0-10` | `01_From_0_To_Below_10.zip` | |
| `all` | `00_All_Records.zip` | Everything (very large) |

Source: https://www.sco.ca.gov/upd_download_property_records.html (updated every Thursday)

## API Keys Needed

| Service | Purpose | Get at |
|---|---|---|
| BatchData | Skip tracing | batchdata.io |
| PostGrid | Physical mail | postgrid.com |
| Anthropic | AI call notes (in dashboard) | anthropic.com |

## California fee cap

CCP § 1582 caps investigator/locator fees at **10% of the recovered property**
(the only carve-out is County Probated Estates, which is not automated here).
This is enforced as a hard ceiling in `agreement.py` and `mailer.py`.

## Output Files

- `reclaim_ca.db` — SQLite database (all leads)
- `data/sco/` — downloaded SCO ZIP files (dated)
- `output/letters/` — HTML copies of every letter
- `output/agreements/` — PDF agreements per claimant
- `output/exports/reclaim_ca_leads_export.json` — import into the dashboard
