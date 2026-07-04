"""
Mailer — PostGrid API (California)
Sends physical solicitation letters to potential claimants.
PostGrid API docs: https://docs.postgrid.com

────────────────────────────────────────────────────────────────────────────
⚠ LEGAL REVIEW REQUIRED. The letter language below is a good-faith DRAFT built
around CCP §§ 1580–1582 and the SCO's published investigator rules. It is not
legal advice. Have a California attorney review the solicitation copy and
confirm any state/local disclosure or licensing requirements before you mail
anything for real. Real sends are hard-blocked until CA_COMPLIANCE_OK=true.
────────────────────────────────────────────────────────────────────────────
"""
import requests
import os
from datetime import date
from config import (
    POSTGRID_API_KEY, CA_FEE_CAP, CA_COMPLIANCE_OK,
    POSTGRID_FROM_NAME, POSTGRID_FROM_LINE1,
    POSTGRID_FROM_CITY, POSTGRID_FROM_STATE,
    POSTGRID_FROM_ZIP, POSTGRID_FROM_COUNTRY,
    AGENT_NAME, AGENT_PHONE, AGENT_EMAIL, AGENT_COMPANY,
    DEFAULT_FEE_PERCENT, LETTERS_DIR,
)

POSTGRID_URL = "https://api.postgrid.com/v1"

SCO_CLAIM_LINE = "claimit.ca.gov or (800) 992-4647"


def _generate_letter_html(lead: dict) -> str:
    """
    Generate a California unclaimed-property solicitation letter.

    Includes a clear, prominent notice that this is a solicitation and not an
    official government mailing, that the recipient may claim the property for
    free directly from the SCO, and that any fee is capped at 10% (CCP § 1582).
    """
    fee = min(lead.get("fee_percent", DEFAULT_FEE_PERCENT), CA_FEE_CAP)
    prop_type = lead.get("property_type", "property").lower()
    holder = lead.get("holding_entity", "")
    holder_phrase = f", originally reported by {holder}," if holder else ""
    value = lead.get("property_value", 0)
    value_phrase = f" valued at approximately ${value:,.0f}" if value > 0 else ""
    today_str = date.today().strftime("%B %d, %Y")
    first_name = lead.get("first_name", "")
    last_name = lead.get("last_name", "")
    address = lead.get("address", "")
    city = lead.get("city", "")
    state = lead.get("state", "")
    zip_code = lead.get("zip", "")

    notice = (
        "THIS IS A SOLICITATION. THIS IS NOT A BILL OR AN OFFICIAL GOVERNMENT "
        "DOCUMENT AND HAS NOT BEEN SENT BY THE STATE OF CALIFORNIA. YOU ARE NOT "
        "REQUIRED TO USE THE SERVICES OFFERED. YOU MAY CLAIM YOUR PROPERTY FOR "
        "FREE DIRECTLY FROM THE CALIFORNIA STATE CONTROLLER'S OFFICE."
    )

    html = "<html><body style=\"font-family: Georgia, serif; max-width: 600px; margin: 40px auto; color: #1a1a1a; line-height: 1.7;\">"
    html += "<div style=\"border: 3px solid #1a1a1a; padding: 14px; margin-bottom: 24px; text-align: center;\">"
    html += "<p style=\"font-size: 13px; font-weight: bold; letter-spacing: 0.3px; margin: 0; text-transform: uppercase;\">"
    html += notice
    html += "</p></div>"
    html += f"<p style=\"text-align:right; color:#666; font-size:13px;\">{today_str}</p>"
    html += f"<p>{first_name} {last_name}<br>{address}<br>{city}, {state} {zip_code}</p>"
    html += f"<p>Dear {first_name},</p>"
    html += (
        f"<p>My company, {AGENT_COMPANY}, helps California residents recover unclaimed "
        f"property being held by the <strong>California State Controller's Office</strong>. "
        f"Public records indicate the State may be holding funds in your name -- "
        f"specifically a {prop_type}{holder_phrase}{value_phrase}.</p>"
    )
    html += (
        "<p>Unclaimed property is common. Banks, insurers, and employers transfer "
        "dormant funds to the State after a period of inactivity. "
        "<strong>You are not required to use a recovery service.</strong> You may "
        f"search for and claim this property yourself, free of charge, directly from "
        f"the State Controller's Office at {SCO_CLAIM_LINE}.</p>"
    )
    html += (
        f"<p><strong>If you'd prefer help with the process:</strong><br>"
        f"I locate the funds, prepare the required recovery agreement, and file the "
        f"claim with the State Controller's Office on your behalf. There is no upfront "
        f"cost, and no fee is owed unless and until your claim is approved and paid. "
        f"My fee is capped by California law (Code of Civil Procedure Section 1582) at "
        f"no more than {fee:.0f}% of the recovered amount.</p>"
    )
    html += (
        f"<p>If you'd like to proceed or have questions, call or text me at "
        f"<strong>{AGENT_PHONE}</strong>, or email <strong>{AGENT_EMAIL}</strong>.</p>"
    )
    html += "<p>Sincerely,</p>"
    html += (
        f"<p><strong>{AGENT_NAME}</strong><br>"
        f"{AGENT_COMPANY}<br>"
        f"{AGENT_PHONE}<br>{AGENT_EMAIL}</p>"
    )
    html += (
        "<p style=\"font-size:11px; color:#888; border-top:1px solid #ddd; padding-top:10px; margin-top:40px;\">"
        "This letter was sent because your name appears in the California State "
        "Controller's Office public unclaimed property database. To be removed from "
        "future contact, reply \"remove\" to this letter or call the number above."
        "</p>"
    )
    html += "</body></html>"
    return html


def _save_letter_locally(lead: dict, html: str) -> str:
    os.makedirs(LETTERS_DIR, exist_ok=True)
    name = f"{lead.get('last_name','')}{lead.get('first_name','')}".replace(" ", "_")
    path = f"{LETTERS_DIR}/letter_{name}_{lead.get('id','')}.html"
    with open(path, "w") as f:
        f.write(html)
    return path


def send_letter(lead: dict, dry_run: bool = False) -> dict:
    """
    Send a physical letter via PostGrid.
    Returns {"success": bool, "mail_id": str, "error": str}

    GUARDRAIL: real (non-dry-run) sends are blocked until CA_COMPLIANCE_OK is
    set true in .env — i.e., until a California attorney has signed off on the
    solicitation language and your licensing status. See CA_COMPLIANCE.md.
    """
    if not dry_run and not CA_COMPLIANCE_OK:
        msg = (
            "BLOCKED: CA_COMPLIANCE_OK is not set. Real letters cannot be sent "
            "until your California unclaimed-property solicitation language and "
            "licensing have been reviewed and you've set CA_COMPLIANCE_OK=true in "
            ".env. Use dry_run=True to preview."
        )
        print(f"  ⛔ {msg}")
        return {"success": False, "error": msg, "blocked": True}

    html = _generate_letter_html(lead)
    local_path = _save_letter_locally(lead, html)

    if dry_run or not POSTGRID_API_KEY:
        print(f"  [DRY RUN] Letter for {lead['first_name']} {lead['last_name']} → saved to {local_path}")
        return {"success": True, "mail_id": "dry_run", "local_path": local_path, "dry_run": True}

    if not lead.get("address") or not lead.get("city"):
        return {"success": False, "error": "Missing address — skip trace first", "local_path": local_path}

    headers = {
        "x-api-key": POSTGRID_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "to": {
            "firstName": lead.get("first_name", ""),
            "lastName":  lead.get("last_name", ""),
            "addressLine1": lead.get("address", ""),
            "city":      lead.get("city", ""),
            "provinceOrState": lead.get("state", ""),
            "postalOrZip": lead.get("zip", ""),
            "countryCode": "US",
        },
        "from": {
            "firstName":      POSTGRID_FROM_NAME,
            "company":        AGENT_COMPANY,
            "addressLine1":   POSTGRID_FROM_LINE1,
            "city":           POSTGRID_FROM_CITY,
            "provinceOrState": POSTGRID_FROM_STATE,
            "postalOrZip":    POSTGRID_FROM_ZIP,
            "countryCode":    POSTGRID_FROM_COUNTRY,
        },
        "html": html,
        "size": "us_letter",
        "color": False,
        "doubleSided": False,
        "description": f"Reclaim CA - {lead.get('first_name','')} {lead.get('last_name','')}",
        "metadata": {
            "lead_id": str(lead.get("id", "")),
            "property_state": lead.get("property_state", "CA"),
        }
    }

    try:
        resp = requests.post(f"{POSTGRID_URL}/letters", json=payload, headers=headers, timeout=30)
        if resp.status_code in (200, 201):
            data = resp.json()
            mail_id = data.get("id", "")
            print(f"  PostGrid: ✓ Letter queued for {lead['first_name']} {lead['last_name']} — {mail_id}")
            return {"success": True, "mail_id": mail_id, "local_path": local_path}
        else:
            err = resp.json().get("error", "") or resp.text[:200]
            print(f"  PostGrid: ✗ HTTP {resp.status_code} — {err}")
            return {"success": False, "error": err, "local_path": local_path}
    except Exception as e:
        print(f"  PostGrid error: {e}")
        return {"success": False, "error": str(e), "local_path": local_path}
