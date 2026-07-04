# Reclaim CA — Phase 3 setup (skip tracing, via Tracerfy)

Turns your leads' stale "last known" info into current phone / email / address —
but only for the leads **you** pick, and only when **you** run it.

## How it works
1. In the dashboard, open a lead worth pursuing → click **🔎 Request skip trace**.
   That just flags it (free). Flag as many as you like.
2. When ready, run the **Skip trace (manual)** job in GitHub Actions.
3. It looks up current contact info for **only the flagged leads**, writes it back,
   and marks them ✓ Skip traced. The fresh info shows up in the dashboard.

It never runs on a schedule, and never touches leads you didn't flag.

---

## Your provider: Tracerfy (pay-as-you-go, no subscription)
We swapped off BatchData (too expensive to start) to **Tracerfy**:
- **~$0.02 per credit**; a lookup is ~$0.10 per **hit**, and **misses are free**.
- **No subscription, no monthly minimum, no card to sign up.** You just drop ~$20
  of credits to start, and credits never expire.
- Because misses are free, testing is nearly free — a great way to start small.

### Get your key
1. Sign up: https://www.tracerfy.com/auth/sign-up/ (no card required).
2. Add a little credit (e.g. $20) in the dashboard.
3. Find your **API key**: Profile icon (top-right) → **Settings → API Key**.

---

## Setup steps

### 1. Deploy the updated dashboard (adds the "Request skip trace" button)
1. GitHub → **reclaim-ca** repo → **Add file → Upload files** → upload the new
   **`src/reclaim_ca_app.jsx`**. Commit. Netlify redeploys.
2. Hard-refresh, open a lead — you'll see **🔎 Request skip trace** under the
   stage dropdown.

### 2. Add your Tracerfy key to the pipeline repo
1. GitHub → **reclaim-ca-pipeline → Settings → Secrets and variables → Actions →
   New repository secret**:
   - Name: `TRACERFY_API_KEY`
   - Value: your Tracerfy API key
   (SUPABASE_URL and SUPABASE_SERVICE_KEY are already there from Phase 2.)

### 3. Upload the updated pipeline files
Re-upload these (they changed for Tracerfy) to **reclaim-ca-pipeline**:
`skip_trace.py`, `config.py`, `skip_trace_runner.py`. And add the workflow if you
haven't: **Add file → Create new file** → `.github/workflows/skiptrace.yml` →
paste the contents of that file from this folder → commit.

### 4. Try it SMALL first
1. In the dashboard, flag just **1–2 leads** (Request skip trace).
2. GitHub → **reclaim-ca-pipeline → Actions → Skip trace (manual) → Run workflow**.
3. Watch the log.

---

## First run (should just work — but it's cheap either way)
The integration is now locked to Tracerfy's **documented** sync endpoint
(`/v1/api/trace/lookup/`, `Api-Key` auth, `find_owner:false` with the name +
last-known address), and it prefers a clean **non-DNC, non-litigator mobile**
number so you don't pick a risky one.

As a safety net, the job still **prints the first couple of raw responses**. If a
lead ever shows "matched but no contact parsed" or an HTTP error, copy that line
from the log and send it to me — a ~2-minute tweak. Misses are free, so testing
1–2 leads costs almost nothing.

**Cost note:** the coded method is the sync lookup (~$0.10 per hit). If you later
want to trace in bigger, cheaper batches (~$0.02 per hit via their CSV/batch
endpoint), tell me and I'll switch it.

## Controls
- **You pick the leads** (only flagged ones are traced).
- **`SKIP_TRACE_MAX`** repo Variable caps how many per run (default 200).
- Start with 1–2 to confirm, then do a batch.

## Still human-gated after this
Skip tracing gets you *reachable* leads. It does NOT contact anyone. Outreach
(letters / calls / e-sign) is Phase 4 — behind your attorney's compliance sign-off.
