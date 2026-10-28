"""SQLite storage. Phase 2 tables: accounts, pages, snapshots, runs."""
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "observer.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    company_name TEXT UNIQUE NOT NULL,
    website_url TEXT,
    industry TEXT,
    owner TEXT,
    priority TEXT,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    page_type TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    last_checked_at TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id),
    fetched_at TEXT NOT NULL,
    http_status INTEGER,
    content_hash TEXT NOT NULL,
    blocks TEXT NOT NULL,           -- JSON list of cleaned text blocks
    boilerplate TEXT NOT NULL       -- JSON list of "kind: text" entries stripped by the cleaner
);
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id),
    old_snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    new_snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    detected_at TEXT NOT NULL,
    added_blocks TEXT NOT NULL,     -- JSON: content blocks that survived the noise rules
    removed_blocks TEXT NOT NULL,
    ignored TEXT NOT NULL,          -- JSON list of {"text", "rule"} the noise rules dropped
    status TEXT NOT NULL,           -- ignored_rule | pending_llm | ignored_llm | rejected | review | alert_ready | alerted | duplicate | alert_failed
    reason TEXT
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY,
    change_id INTEGER NOT NULL REFERENCES changes(id),
    meaningful INTEGER,
    signal_type TEXT,
    confidence TEXT,
    change_summary TEXT,
    why_it_matters TEXT,
    outreach_angle TEXT,
    evidence TEXT,
    reason_if_not_meaningful TEXT,
    model TEXT,                     -- 'mock-heuristic' for the stand-in, else the Claude model id
    raw_json TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    change_id INTEGER NOT NULL REFERENCES changes(id),
    fingerprint TEXT NOT NULL,
    channel TEXT NOT NULL,          -- slack | console
    sent_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS crm_sync (
    id INTEGER PRIMARY KEY,
    change_id INTEGER UNIQUE NOT NULL REFERENCES changes(id),
    status TEXT NOT NULL,           -- synced | no_contact | draft_failed | crm_failed
    company_url TEXT,
    person_url TEXT,
    trigger_entry_id TEXT,
    message_entry_id TEXT,
    contact_name TEXT,
    contact_title TEXT,
    subject TEXT,
    body TEXT,
    model TEXT,                     -- who drafted: 'mock-heuristic' or the Claude model id
    error TEXT,
    synced_at TEXT NOT NULL,
    contact_email TEXT,
    airtable_status TEXT,           -- pushed | failed | pending (waiting for Attio) | NULL when Airtable is off
    airtable_record_id TEXT,
    airtable_url TEXT,
    airtable_error TEXT,
    draft_notes TEXT                -- JSON: the internal analysis behind the draft (angle, evidence, source)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    pages_checked INTEGER DEFAULT 0,
    new_pages INTEGER DEFAULT 0,
    changed INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0
);
"""


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    have = {r["name"] for r in conn.execute("PRAGMA table_info(crm_sync)")}
    for column in ("contact_email", "airtable_status", "airtable_record_id", "airtable_url", "airtable_error", "draft_notes"):
        if column not in have:                     # database created before Airtable was added
            conn.execute(f"ALTER TABLE crm_sync ADD COLUMN {column} TEXT")
    return conn


def seed_from_csv(conn, accounts_csv=ROOT / "accounts.csv", pages_csv=ROOT / "pages.csv"):
    """Insert accounts and pages from the CSVs. Safe to run repeatedly."""
    with open(accounts_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            conn.execute(
                "INSERT OR IGNORE INTO accounts (company_name, website_url, industry, owner, priority) "
                "VALUES (?, ?, ?, ?, ?)",
                (r["company_name"], r["website_url"], r["industry"], r["account_owner"], r["priority"]))
    with open(pages_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            acct = conn.execute("SELECT id FROM accounts WHERE company_name = ?",
                                (r["company_name"],)).fetchone()
            if acct is None:
                continue
            conn.execute("INSERT OR IGNORE INTO pages (account_id, page_type, url) VALUES (?, ?, ?)",
                         (acct["id"], r["page_type"], r["url"]))
    conn.commit()


def latest_snapshot(conn, page_id):
    return conn.execute("SELECT * FROM snapshots WHERE page_id = ? ORDER BY id DESC LIMIT 1",
                        (page_id,)).fetchone()


def save_snapshot(conn, page_id, fetched_at, http_status, content_hash, blocks, boilerplate):
    cur = conn.execute(
        "INSERT INTO snapshots (page_id, fetched_at, http_status, content_hash, blocks, boilerplate) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (page_id, fetched_at, http_status, content_hash, json.dumps(blocks), json.dumps(boilerplate)))
    return cur.lastrowid


def save_change(conn, page_id, old_id, new_id, detected_at, added, removed, ignored, status, reason):
    cur = conn.execute(
        "INSERT INTO changes (page_id, old_snapshot_id, new_snapshot_id, detected_at, added_blocks, "
        "removed_blocks, ignored, status, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (page_id, old_id, new_id, detected_at, json.dumps(added), json.dumps(removed),
         json.dumps(ignored), status, reason))
    return cur.lastrowid


def save_analysis(conn, change_id, result, model):
    conn.execute(
        "INSERT INTO analyses (change_id, meaningful, signal_type, confidence, change_summary, why_it_matters, "
        "outreach_angle, evidence, reason_if_not_meaningful, model, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (change_id, int(bool(result.get("meaningful"))), result.get("signal_type"), result.get("confidence"),
         result.get("change_summary"), result.get("why_it_matters"), result.get("outreach_angle"),
         result.get("evidence"), result.get("reason_if_not_meaningful"), model, json.dumps(result)))


def set_change_status(conn, change_id, status, reason):
    conn.execute("UPDATE changes SET status = ?, reason = ? WHERE id = ?", (status, reason, change_id))


def add_account(conn, company, website_url, industry, owner, priority, pages):
    """pages: list of (page_type, url). Returns an error string, or None on success."""
    if not company.strip():
        return "Company name is required."
    if not pages:
        return "Add at least one page URL to monitor."
    if conn.execute("SELECT 1 FROM accounts WHERE company_name = ?", (company.strip(),)).fetchone():
        return f"{company.strip()} is already in the account list."
    for _, url in pages:
        if not url.startswith(("http://", "https://")):
            return f"Page URL must start with http:// or https:// ({url})"
        if conn.execute("SELECT 1 FROM pages WHERE url = ?", (url,)).fetchone():
            return f"{url} is already monitored."
    cur = conn.execute(
        "INSERT INTO accounts (company_name, website_url, industry, owner, priority) VALUES (?, ?, ?, ?, ?)",
        (company.strip(), website_url.strip(), industry.strip(), owner.strip(), priority))
    for page_type, url in pages:
        conn.execute("INSERT INTO pages (account_id, page_type, url) VALUES (?, ?, ?)",
                     (cur.lastrowid, page_type, url))
    conn.commit()
    return None
