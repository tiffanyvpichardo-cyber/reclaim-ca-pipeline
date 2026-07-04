"""
Reclaim CA Automation — SQLite Database
All leads live here. The dashboard syncs from this via export_json().
"""
import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id              TEXT PRIMARY KEY,
            first_name      TEXT NOT NULL,
            last_name       TEXT NOT NULL,
            phone           TEXT,
            email           TEXT,
            address         TEXT,
            city            TEXT,
            state           TEXT,
            zip             TEXT,
            property_type   TEXT,
            property_value  REAL,
            property_state  TEXT,
            holding_entity  TEXT,
            property_id     TEXT,
            stage           TEXT DEFAULT 'new',
            fee_percent     REAL DEFAULT 10,
            fee_amount      REAL,
            paid_date       TEXT,
            source          TEXT,
            lead_date       TEXT,
            notes           TEXT,
            ai_notes        TEXT,
            skip_traced     INTEGER DEFAULT 0,
            letter_sent     INTEGER DEFAULT 0,
            letter_date     TEXT,
            agreement_sent  INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS outreach_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     TEXT NOT NULL,
            date        TEXT NOT NULL,
            method      TEXT NOT NULL,
            notes       TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     TEXT NOT NULL,
            date        TEXT NOT NULL,
            action      TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        CREATE TABLE IF NOT EXISTS documents (
            lead_id             TEXT PRIMARY KEY,
            agreement_signed    INTEGER DEFAULT 0,
            id_verified         INTEGER DEFAULT 0,
            proof_of_ownership  INTEGER DEFAULT 0,
            claim_submitted     INTEGER DEFAULT 0,
            payment_received    INTEGER DEFAULT 0,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );
    """)
    conn.commit()
    conn.close()
    print("✓ Database initialized")


def upsert_lead(lead: dict) -> str:
    """Insert or update a lead. Returns lead id."""
    conn = connect()
    lead_id = lead.get("id") or f"lead_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    fee_amount = round(
        float(lead.get("property_value", 0)) * float(lead.get("fee_percent", 10)) / 100, 2
    )

    # ensure all fields present
    lead.setdefault("phone","")
    lead.setdefault("email","")
    lead.setdefault("address","")
    lead.setdefault("city","")
    lead.setdefault("state","")
    lead.setdefault("zip","")
    lead.setdefault("notes","")
    lead.setdefault("lead_date","")
    conn.execute("""
        INSERT INTO leads (
            id, first_name, last_name, phone, email, address, city, state, zip,
            property_type, property_value, property_state, holding_entity, property_id,
            stage, fee_percent, fee_amount, source, lead_date, notes, updated_at
        ) VALUES (
            :id,:first_name,:last_name,:phone,:email,:address,:city,:state,:zip,
            :property_type,:property_value,:property_state,:holding_entity,:property_id,
            :stage,:fee_percent,:fee_amount,:source,:lead_date,:notes,datetime('now')
        )
        ON CONFLICT(id) DO UPDATE SET
            phone=excluded.phone, email=excluded.email, address=excluded.address,
            city=excluded.city, state=excluded.state, zip=excluded.zip,
            stage=excluded.stage, fee_amount=excluded.fee_amount,
            skip_traced=excluded.skip_traced, letter_sent=excluded.letter_sent,
            letter_date=excluded.letter_date, notes=excluded.notes,
            updated_at=datetime('now')
    """, {**lead, "id": lead_id, "fee_amount": fee_amount})

    # Init documents row
    conn.execute("""
        INSERT OR IGNORE INTO documents (lead_id) VALUES (?)
    """, (lead_id,))

    conn.commit()
    conn.close()
    return lead_id


def log_activity(lead_id: str, action: str):
    conn = connect()
    conn.execute(
        "INSERT INTO activity_log (lead_id, date, action) VALUES (?, date('now'), ?)",
        (lead_id, action)
    )
    conn.execute("UPDATE leads SET updated_at=datetime('now') WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()


def log_outreach(lead_id: str, method: str, notes: str):
    conn = connect()
    conn.execute(
        "INSERT INTO outreach_log (lead_id, date, method, notes) VALUES (?, date('now'), ?, ?)",
        (lead_id, method, notes)
    )
    conn.commit()
    conn.close()


def update_stage(lead_id: str, stage: str):
    conn = connect()
    conn.execute(
        "UPDATE leads SET stage=?, updated_at=datetime('now') WHERE id=?",
        (stage, lead_id)
    )
    conn.commit()
    conn.close()
    log_activity(lead_id, f"Stage → {stage}")


def mark_letter_sent(lead_id: str):
    conn = connect()
    conn.execute(
        "UPDATE leads SET letter_sent=1, letter_date=date('now'), stage='letter', updated_at=datetime('now') WHERE id=?",
        (lead_id,)
    )
    conn.commit()
    conn.close()
    log_activity(lead_id, "Letter sent via PostGrid")
    log_outreach(lead_id, "Letter", "Initial outreach letter mailed via PostGrid")


def mark_skip_traced(lead_id: str, phone: str, address: str, city: str, state: str, zip_: str):
    conn = connect()
    conn.execute("""
        UPDATE leads SET skip_traced=1, phone=?, address=?, city=?, state=?, zip=?,
        updated_at=datetime('now') WHERE id=?
    """, (phone, address, city, state, zip_, lead_id))
    conn.commit()
    conn.close()
    log_activity(lead_id, "Skip traced — contact info updated")


def get_leads_for_skip_trace():
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM leads WHERE skip_traced=0 AND stage='new' ORDER BY property_value DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_leads_for_letters():
    conn = connect()
    rows = conn.execute("""
        SELECT * FROM leads WHERE letter_sent=0 AND skip_traced=1
        AND (phone IS NOT NULL OR address IS NOT NULL)
        AND stage IN ('new','verified')
        ORDER BY property_value DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_leads():
    conn = connect()
    rows = conn.execute("SELECT * FROM leads ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def export_json(path: str):
    """Export all leads to JSON for the Reclaim CA dashboard."""
    import os
    conn = connect()
    leads = [dict(r) for r in conn.execute("SELECT * FROM leads ORDER BY updated_at DESC").fetchall()]
    
    for lead in leads:
        lid = lead["id"]
        lead["outreachLog"] = [
            dict(r) for r in conn.execute(
                "SELECT date, method, notes FROM outreach_log WHERE lead_id=? ORDER BY date", (lid,)
            ).fetchall()
        ]
        lead["activity"] = [
            {"date": r["date"], "action": r["action"]} for r in conn.execute(
                "SELECT date, action FROM activity_log WHERE lead_id=? ORDER BY date", (lid,)
            ).fetchall()
        ]
        docs = conn.execute("SELECT * FROM documents WHERE lead_id=?", (lid,)).fetchone()
        docs = dict(docs) if docs else {}
        # Emit dashboard-shaped (camelCase) docs; drop the internal lead_id.
        lead["docs"] = {
            "agreementSigned":  bool(docs.get("agreement_signed", 0)),
            "idVerified":       bool(docs.get("id_verified", 0)),
            "proofOfOwnership": bool(docs.get("proof_of_ownership", 0)),
            "claimSubmitted":   bool(docs.get("claim_submitted", 0)),
            "paymentReceived":  bool(docs.get("payment_received", 0)),
        }

        # Map internal pipeline stages -> the dashboard's Reclaim CA SOP stages.
        _SOP = {"new": "lead", "verified": "lead", "letter": "contacted"}
        lead["stage"] = _SOP.get(lead.get("stage"), lead.get("stage") or "lead")

        # Map snake_case → camelCase for dashboard
        lead["firstName"]      = lead.pop("first_name")
        lead["lastName"]       = lead.pop("last_name")
        lead["propertyType"]   = lead.pop("property_type")
        lead["propertyValue"]  = lead.pop("property_value")
        lead["propertyState"]  = lead.pop("property_state")
        lead["holdingEntity"]  = lead.pop("holding_entity")
        lead["propertyId"]     = lead.pop("property_id", "")
        lead["feePercent"]     = lead.pop("fee_percent")
        lead["feeAmount"]      = lead.pop("fee_amount")
        lead["paidDate"]       = lead.pop("paid_date")
        lead["leadDate"]       = lead.pop("lead_date")
        lead["aiNotes"]        = lead.pop("ai_notes", "")

    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(leads, f, indent=2)
    conn.close()
    print(f"✓ Exported {len(leads)} leads to {path}")
    return leads
