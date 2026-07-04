"""
Agreement Generator — California
Creates a PDF locator/recovery agreement for each claimant, built to track the
California Unclaimed Property Law (Code of Civil Procedure §§ 1580–1582).

Uses fpdf2 — no external dependencies needed.

────────────────────────────────────────────────────────────────────────────
⚠ LEGAL REVIEW REQUIRED. The language below is a good-faith DRAFT that reflects
the plain text of CCP § 1582 and the SCO's published investigator rules. It is
NOT legal advice and must be reviewed and approved by a California attorney
before you send it to any real claimant. Two CA-specific rules in particular
shape when this agreement is even valid — see CA_COMPLIANCE.md:
  • § 1582(a)(1)(A): an agreement is INVALID if signed during the window
    between the holder's report to the SCO and the SCO's payment/delivery.
  • § 1582(a)(1)(B): you may not require any fee before the claim is approved
    and paid to the owner.
The hard 10% fee cap (§ 1582) is enforced in code and cannot be overridden.
────────────────────────────────────────────────────────────────────────────
"""
import os
from datetime import date
from fpdf import FPDF
from config import (
    AGENT_NAME, AGENT_COMPANY, AGENT_PHONE, AGENT_EMAIL,
    AGENT_ADDRESS, AGENT_CITY_STATE, AGREEMENTS_DIR, CA_FEE_CAP,
)

# SCO address where owners may claim directly, free of charge (required disclosure).
SCO_CLAIM_ADDRESS = (
    "California State Controller's Office, Unclaimed Property Division, "
    "P.O. Box 942850, Sacramento, CA 94250-5873 | claimit.ca.gov | (800) 992-4647"
)


# fpdf2's core fonts (Helvetica) are latin-1 only. Transliterate the common
# Unicode punctuation that tends to sneak into copy so the PDF never crashes.
_LATIN1_MAP = {
    "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u00a7": "Section ", "\u2022": "-",
    "\u2713": "x", "\u2026": "...", "\u00a0": " ",
}


def _latin1(text):
    for uni, ascii_ in _LATIN1_MAP.items():
        text = text.replace(uni, ascii_)
    return text.encode("latin-1", "replace").decode("latin-1")


class AgreementPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "UNCLAIMED PROPERTY RECOVERY AGREEMENT", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, "Pursuant to California Code of Civil Procedure Sections 1580-1582",
                  align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, "Contingency Fee Agreement - No Recovery, No Fee", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_draw_color(30, 58, 95)   # navy, to match the Reclaim brand
        self.set_line_width(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150)
        self.cell(0, 10, f"Page {self.page_no()} - {AGENT_COMPANY} - {AGENT_EMAIL}", align="C")


def generate_agreement(lead: dict, fee_percent: float = None) -> str:
    """Generate a PDF agreement for the lead. Returns file path."""
    os.makedirs(AGREEMENTS_DIR, exist_ok=True)

    requested_fee = fee_percent if fee_percent is not None else lead.get("fee_percent", CA_FEE_CAP)
    # HARD CAP — CCP § 1582. No path sets a fee above 10%. County Probated
    # Estate exceptions require a lawyer's judgment and are intentionally not
    # automated here.
    effective_fee = min(float(requested_fee), CA_FEE_CAP)

    claimant_name = f"{lead.get('first_name','')} {lead.get('last_name','')}".strip()
    prop_type = lead.get("property_type", "property")
    holder = lead.get("holding_entity", "")
    value = lead.get("property_value", 0)
    today = date.today().strftime("%B %d, %Y")

    pdf = AgreementPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)

    def section(title):
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(232, 238, 246)   # pale navy tint
        pdf.cell(0, 8, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)

    def para(text):
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _latin1(text))
        pdf.ln(3)

    def field_row(label, value_str, blank=False):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(55, 7, _latin1(label) + ":")
        pdf.set_font("Helvetica", "", 9)
        if blank:
            pdf.cell(0, 7, "", border="B", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.cell(0, 7, _latin1(value_str), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Date: {today}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    section("PARTIES")
    field_row("Recovery Agent", AGENT_NAME)
    field_row("Company", AGENT_COMPANY)
    field_row("Agent Address", f"{AGENT_ADDRESS}, {AGENT_CITY_STATE}")
    field_row("Agent Phone / Email", f"{AGENT_PHONE} | {AGENT_EMAIL}")
    pdf.ln(3)
    field_row("Claimant Name", claimant_name)
    field_row("Claimant Address",
              f"{lead.get('address','')} {lead.get('city','')} {lead.get('state','')} {lead.get('zip','')}".strip())
    field_row("Claimant Phone", lead.get("phone", "") or "")
    pdf.ln(6)

    section("PROPERTY DESCRIPTION (Nature and Value)")
    field_row("Property Type", prop_type)
    field_row("Held By (State Custodian)", "California State Controller's Office")
    if holder:
        field_row("Originally Reported By", holder)
    if value:
        field_row("Reported Value", f"${value:,.2f}")
    pdf.ln(4)
    para(
        "Where the owner can claim this property directly, free of charge: "
        + SCO_CLAIM_ADDRESS
    )
    pdf.ln(2)

    section("AGREEMENT TERMS")
    para(
        "This Agreement is governed by the California Unclaimed Property Law, "
        "Code of Civil Procedure Sections 1580-1582."
    )
    para(
        "1. SERVICES. The Recovery Agent agrees to locate, document, and file a "
        "claim for the above-described unclaimed property with the California "
        "State Controller's Office on behalf of the Claimant, at no upfront cost."
    )
    para(
        f"2. FEE. Upon successful recovery, the Claimant agrees the Recovery Agent "
        f"shall receive a fee of {effective_fee:.0f}% of the value of the property "
        f"recovered. Under California Code of Civil Procedure Section 1582, this fee "
        f"may not exceed 10% of the recovered property."
    )
    para(
        "3. NO UPFRONT FEE. Consistent with Section 1582(a)(1)(B), the Claimant is "
        "not required to pay any fee or compensation before the claim is approved "
        "and the recovered property is paid or delivered to the Claimant by the "
        "State Controller."
    )
    para(
        "4. TIMING / VALIDITY. Consistent with Section 1582(a)(1)(A), this Agreement "
        "is not valid if entered into between the date the property was reported to "
        "the State Controller and the date the property is paid or delivered. The "
        "Recovery Agent represents that this Agreement is offered only for property "
        "eligible to be recovered under Section 1582."
    )
    para(
        "5. RIGHT TO CLAIM DIRECTLY. The Claimant is not required to use a recovery "
        "service. The Claimant may search for and claim this property directly from "
        "the California State Controller's Office, free of charge, at the address "
        "and contact information listed above."
    )
    para(
        "6. CLAIMANT COOPERATION. The Claimant agrees to provide documentation as "
        "reasonably requested, including government-issued ID and any supporting "
        "documents required by the State Controller for the property type."
    )
    para(
        "7. NO GOVERNMENT AFFILIATION. The Recovery Agent is not an employee, "
        "contractor, or agent of the State of California or the State Controller's "
        "Office. This Agreement is not an official government document."
    )
    para(
        "8. REVOCATION. The Claimant may revoke this Agreement for any reason "
        "permitted by law. Nothing in this Agreement prevents the Claimant from "
        "asserting at any time that the fee is excessive or unjust (Section 1582)."
    )
    pdf.ln(4)

    section("SIGNATURES")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(90, 6, "Claimant Signature:", new_x="RIGHT", new_y="LAST")
    pdf.cell(0, 6, "Recovery Agent Signature:", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_draw_color(0)
    pdf.set_line_width(0.3)
    pdf.cell(85, 0, "", border="B", new_x="RIGHT", new_y="LAST")
    pdf.cell(10, 0, "")
    pdf.cell(0, 0, "", border="B", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.cell(90, 5, _latin1(f"Print Name: {claimant_name}"), new_x="RIGHT", new_y="LAST")
    pdf.cell(0, 5, _latin1(f"Print Name: {AGENT_NAME}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.cell(85, 0, "", border="B", new_x="RIGHT", new_y="LAST")
    pdf.cell(10, 0, "")
    pdf.cell(0, 0, "", border="B", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.cell(90, 5, "Date: ___________________", new_x="RIGHT", new_y="LAST")
    pdf.cell(0, 5, f"Date: {today}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    para("By signing above, both parties agree to the terms set forth in this agreement.")

    filename = f"agreement_{lead.get('last_name','')}_{lead.get('first_name','')}_{lead.get('id','')}".replace(" ", "_") + ".pdf"
    path = os.path.join(AGREEMENTS_DIR, filename)
    pdf.output(path)
    print(f"  ✓ Agreement saved: {path}")
    return path
