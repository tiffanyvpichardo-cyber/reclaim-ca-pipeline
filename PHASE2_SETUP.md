# Reclaim CA — Phase 2 setup (automatic weekly lead ingest)

This puts your Python scraper on a **weekly schedule in the cloud** (GitHub
Actions — free). Every week it downloads the California SCO public data and drops
the **top new high-value leads** straight into the same dashboard you set up in
Phase 1. No server to run, nothing on your computer.

What it does, in plain terms:
- Pulls the CA SCO "$500 and up" data file.
- Adds only **new** leads it hasn't seen before — it will **never** overwrite a
  lead you've already worked. (Insert-only.)
- Adds only the **top 500 by value** each run, so you get a workable batch of the
  best leads instead of tens of thousands. (You can change this number.)

---

## Before you start
You'll need two things from Supabase (you already have the first):
- **Project URL** — `https://svmssswepkkcwlvujyjy.supabase.co`
- **Secret key** — the `sb_secret_…` one. This is the *server-side* key (the one
  we deliberately kept OUT of the browser). It lives only in GitHub, encrypted.
  Get it: Supabase → Project Settings → API → **Publishable and secret API keys**
  → **Secret keys** → reveal/copy the `default` `sb_secret_…` value.

> Publishable key = browser (Netlify). Secret key = server (GitHub Actions).
> Never swap them.

---

## Step 1 — Make a new GitHub repo for the pipeline
1. GitHub → **New repository** → name it **`reclaim-ca-pipeline`** → **Private**
   is fine (this is your engine, not a public site) → Create.

## Step 2 — Upload the pipeline files
1. Open the repo → **Add file → Upload files**.
2. From this `reclaim_ca_pipeline` folder, drag in the visible files:
   `sco_to_supabase.py`, `ca_sco_parser.py`, `config.py`, `requirements.txt`
   (the other `.py` files are for later phases — include them too, they're
   harmless).
3. **Commit changes.**

## Step 3 — Add the schedule file (do this one on GitHub directly)
The scheduled-job file lives in a hidden `.github` folder that Mac Finder hides,
so the easiest way is to create it right on GitHub:
1. In the repo → **Add file → Create new file**.
2. In the filename box type exactly: `.github/workflows/ingest.yml`
   (typing the slashes creates the folders automatically).
3. Paste in the contents of the `ingest.yml` file from this folder
   (`.github/workflows/ingest.yml`), or copy it from PHASE2_SETUP notes.
4. **Commit changes.**

## Step 4 — Add your two secrets
1. Repo → **Settings → Secrets and variables → Actions**.
2. **New repository secret**, add these two (names exactly):
   - `SUPABASE_URL` = your `https://…supabase.co` URL
   - `SUPABASE_SERVICE_KEY` = your `sb_secret_…` key
3. (Optional) Under the **Variables** tab you can add `INGEST_MAX_NEW` (e.g. `250`
   or `1000`) or `MIN_PROPERTY_VALUE` to tune volume. Skip for now if unsure.

## Step 5 — Run it once, manually
1. Repo → **Actions** tab. If it asks to enable workflows, enable them.
2. Click **Weekly CA SCO ingest** → **Run workflow** → **Run workflow**.
3. Click into the run and watch the log. Success looks like:
   `✓ Ingest complete — added up to N new lead(s).`
4. Open your dashboard, sign in — the new leads are there. 🎉

After this, it runs **automatically every Friday**. You don't have to touch it.

---

## Honest heads-up on the first run
I couldn't run the live California download from my side, and the SCO occasionally
changes its file names or column headers without notice. So the **first run is the
real-world test.** In the Actions log, watch for:
- A line like `⚠ WARNING: file headers don't match…` — if you see it, the SCO
  renamed columns; screenshot the "Headers found" line and send it to me, and
  I'll update the mapping in 2 minutes.
- A download error (404 / wrong file) — means the SCO changed the file URL; same
  deal, send me the log line and I'll fix the address.
If it just prints "added up to N new leads," you're golden.

## Tuning later
- Too many/few leads per week? Change the `INGEST_MAX_NEW` repo Variable.
- Only want bigger claims? Raise `MIN_PROPERTY_VALUE` (e.g. `2000`).
- Different day/time? Edit the `cron:` line in `.github/workflows/ingest.yml`
  (crontab.guru explains the format).

## What this does NOT do
It only **fills the top of the funnel** — finds leads and lists them. It does not
contact anyone, skip-trace, or mail. Those are the human-gated Phase 3/4 steps,
on purpose.
