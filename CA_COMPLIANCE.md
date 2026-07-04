# California Unclaimed Property — Compliance Notes (Reclaim CA)

This replaces the Georgia `CDR_REGISTRATION.md`. California does **not** have a
Georgia-style "Claimant's Designated Representative" registration. Locators
(a.k.a. "investigators," "asset locators," "heir finders") operate under the
**California Unclaimed Property Law, Code of Civil Procedure §§ 1500–1582.**

> ⚠ This is a plain-language summary of what the statute and the State
> Controller's Office (SCO) say publicly. It is **not legal advice.** Before you
> send a single real letter or agreement, have a California attorney review your
> solicitation copy, your agreement, and your licensing status, and confirm the
> timing rules below against the specific properties you're working. The code
> hard-blocks real sends until you set `CA_COMPLIANCE_OK=true` in `.env`.

## The three rules baked into this pipeline

| Rule | Where it comes from | How the code handles it |
|---|---|---|
| **Fee cap: 10% of recovered property** | CCP § 1582; SCO investigator page | Hard-clamped in `agreement.py` and `mailer.py` — no override |
| **No upfront fee** | CCP § 1582(a)(1)(B) | Agreement states fee is owed only after the claim is approved and paid |
| **Timing / validity window** | CCP § 1582(a)(1)(A) | Agreement recites the restriction; **you must confirm eligibility per property** |

## The timing rule is the one to watch

Under **CCP § 1582(a)(1)(A)**, an agreement to locate/recover property is
**invalid** if it's signed during the window between when the holder reports the
property to the SCO and when the SCO pays or delivers it. California case law
(e.g., *Goodman v. Cory*) has read this as: a private locator may contract only
**after** the Controller has been unable to reunite the owner within a set
period after delivery. The SCO's own consumer page puts it plainly: an
investigator can't contract with an owner once a business has notified the SCO
that the property will be transferred — the owner can recover it free until then.

**Practical consequence:** not every record in the SCO download is one you can
legally sign a client on today. Your attorney should help you define which
records are "eligible" so you're not sending agreements that are void on arrival.

## Required disclosures in the agreement (CCP § 1582, as amended by AB 2280, 2022)

A valid post-notice agreement must be in writing, signed by the owner, and
disclose:
- the **nature and value** of the property,
- that the **State Controller's Office holds it**, and
- the **address where the owner can claim it directly, free of charge**.

All three are already in the generated agreement (`agreement.py`).

## Licensing — open question for your attorney

California regulates private investigators (Bus. & Prof. Code § 7520 et seq.).
Whether your specific heir-finder / asset-locator activity requires a PI license
or any other registration is a **fact-specific legal question** this project does
not answer. Confirm it before operating.

## Where to verify

- Statute (CCP § 1582): https://codes.findlaw.com/ca/code-of-civil-procedure/ccp-sect-1582/
- SCO — About Investigators: https://sco.ca.gov/upd_investigator_about.html
- SCO — Claiming Property (fees): https://www.sco.ca.gov/upd_faq_claiming-property.html
- Bulk data download: https://www.sco.ca.gov/upd_download_property_records.html

## Status of this build

The pipeline downloads real SCO data and generates compliant-*looking* letters
and agreements, but it is **hard-blocked from sending real mail** until
`CA_COMPLIANCE_OK=true` in `.env`. That flag exists so the block is a deliberate,
attorney-gated decision — not an accident. Dry runs (`--dry-run`) work without it
so you can preview the full flow.
