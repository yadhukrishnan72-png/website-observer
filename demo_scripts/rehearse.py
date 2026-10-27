"""Automated demo rehearsal: runs every scenario end to end and checks the outcome.

    A  noise only              -> 0 alerts, nothing written to Attio or Airtable
    B  new AI product          -> 1 alert, 1 trigger + 1 draft in Attio, 1 complete row in Airtable
    C  hiring push             -> 1 alert, same checks
    D  Attio down during alert -> alert still sent, Attio and Airtable saved by the retry on the next run
    E  Airtable down           -> alert and Attio unaffected, Airtable row pushed by the retry on the next run
    F  BDR approves the row    -> a retry updates the row but never undoes Status = Approved, no duplicate row

Alerts go to the console, not to Slack, unless you pass --slack (that posts real messages to your channel).
Scenarios that need Attio or Airtable are skipped when that destination is not configured in .env.

    python demo_scripts/rehearse.py [--times 3] [--slack]
"""
import argparse
import os
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--times", type=int, default=1, help="number of full rehearsals")
parser.add_argument("--slack", action="store_true", help="post alerts to the real Slack channel")
args = parser.parse_args()
if not args.slack:
    os.environ["SLACK_WEBHOOK_URL"] = ""        # set before observer.config loads .env, which never overrides it

import _demo  # noqa: E402
from observer import airtable, attio, db  # noqa: E402


def crm_rows():
    conn = db.connect()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM crm_sync")]
    finally:
        conn.close()


def alerted_signals():
    conn = db.connect()
    try:
        return [r["signal_type"] for r in conn.execute(
            "SELECT an.signal_type FROM changes ch JOIN analyses an ON an.change_id = ch.id "
            "WHERE ch.status = 'alerted'")]
    finally:
        conn.close()


ONE = {"gtm_triggers": 1, "outreach_messages": 1}
NONE = {"gtm_triggers": 0, "outreach_messages": 0}


def attio_counts(expected=None, timeout=20):
    """Entries per Attio list. Attio's list queries lag behind writes and deletes, so when `expected` is given
    this waits (up to `timeout` seconds) for the counts to settle before returning what it saw."""
    deadline = time.time() + timeout
    while True:
        counts = {slug: len(attio._request("POST", f"/lists/{slug}/entries/query", json={"limit": 500})["data"])
                  for slug in attio.SCHEMA}
        if expected is None or counts == expected or time.time() >= deadline:
            return counts
        time.sleep(1)


def table_rows():
    return [r["fields"] for r in airtable.list_rows()]


def with_env(name, value, fn):
    """Run fn with an environment variable temporarily replaced (used to simulate a destination being down)."""
    real = os.environ[name]
    os.environ[name] = value
    try:
        return fn()
    finally:
        os.environ[name] = real


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def check_complete_row(expected_signals, timeout=15):
    deadline = time.time() + timeout                 # a just-written row can take a moment to read back whole
    while True:
        rows = table_rows()
        if (len(rows) == 1 and rows[0].get("Status")) or time.time() >= deadline:
            break
        time.sleep(1)
    sync = crm_rows()[0] if crm_rows() else {}
    detail = f"(sync: airtable_status={sync.get('airtable_status')}, error={sync.get('airtable_error')})"
    check(len(rows) == 1, f"expected 1 Airtable row, found {len(rows)} {detail}")
    row = rows[0]
    check(row.get("Trigger type") in expected_signals, f"Trigger type: {row.get('Trigger type')} {detail}")
    check(row.get("Status") == "Draft", f"Status: {row.get('Status')} {detail}")
    check(row.get("First name") == "Jordan" and row.get("Last name") == "Lee", "contact name missing")
    check(row.get("Title") and row.get("Company") == "Acme AI", "title or company missing")
    check(row.get("Email subject") and row.get("Email body"), "email draft missing")
    check("Added on the page" in row.get("What changed on the website", ""), "page change text missing")
    check(row.get("Trigger reason") and row.get("Evidence") and row.get("Source page"), "trigger details missing")
    return row


def scenario_a():
    _demo.reset(); _demo.script("scenario_a_noise.py")
    counts, _ = _demo.run_observer()
    check("alerted" not in counts, f"noise produced an alert: {counts}")
    if attio.enabled():
        check(attio_counts(NONE) == NONE, "noise wrote to Attio")
    if airtable.enabled():
        check(not table_rows(), "noise wrote to Airtable")
    return f"0 alerts ({counts})"


def scenario_b():
    _demo.reset(); _demo.script("scenario_b_signal.py")
    counts, _ = _demo.run_observer()
    check(counts.get("alerted") == 1, f"expected 1 alert: {counts}")
    check(alerted_signals() in (["New Product Category"], ["New Product Launch"]), f"signal: {alerted_signals()}")
    rows = crm_rows()
    check(rows and rows[0]["status"] == "synced" and rows[0]["body"], f"draft not saved: {rows}")
    if attio.enabled():
        check(attio_counts(ONE) == ONE, f"Attio entries: {attio_counts()}")
    if airtable.enabled():
        check_complete_row(("New Product Category", "New Product Launch"))
    return f"1 alert, draft for {rows[0]['contact_name']} saved"


def scenario_c():
    _demo.reset(); _demo.script("scenario_c_hiring.py")
    counts, _ = _demo.run_observer()
    check(counts.get("alerted") == 1, f"expected 1 alert: {counts}")
    check(alerted_signals() == ["Hiring / Growth Signal"], f"signal: {alerted_signals()}")
    if attio.enabled():
        check(attio_counts(ONE) == ONE, f"Attio entries: {attio_counts()}")
    if airtable.enabled():
        check_complete_row(("Hiring / Growth Signal",))
    return "1 hiring alert, draft saved"


def scenario_d():
    _demo.reset(); _demo.script("scenario_b_signal.py")
    counts, out = with_env("ATTIO_API_KEY", "invalid-key", _demo.run_observer)
    check(counts.get("alerted") == 1, f"alert lost while Attio was down: {counts}")
    check(args.slack or "Not saved to Attio" in out, "alert did not mention the failed save")
    check(crm_rows()[0]["status"] == "crm_failed", f"expected crm_failed: {crm_rows()}")
    check(attio_counts(NONE) == NONE, "something was saved to Attio while it was down")
    if airtable.enabled():
        check(not table_rows(), "Airtable row written before the Attio save finished")
    counts, _ = _demo.run_observer()
    check(counts.get("crm_synced") == 1, f"Attio retry did not succeed: {counts}")
    check(attio_counts(ONE) == ONE, f"Attio entries: {attio_counts()}")
    if airtable.enabled():
        check(counts.get("airtable_pushed") == 1, f"Airtable row not pushed by the retry: {counts}")
        check_complete_row(("New Product Category", "New Product Launch"))
    return "alert sent while Attio was down; Attio and Airtable saved by the retry"


def scenario_e():
    _demo.reset(); _demo.script("scenario_b_signal.py")
    counts, out = with_env("AIRTABLE_TOKEN", "invalid-token", _demo.run_observer)
    check(counts.get("alerted") == 1, f"alert lost while Airtable was down: {counts}")
    check(args.slack or "Row not saved yet" in out, "alert did not mention the failed Airtable push")
    row = crm_rows()[0]
    check(row["status"] == "synced" and row["airtable_status"] == "failed", f"unexpected state: {row}")
    check(attio_counts(ONE) == ONE, "Attio was affected by the Airtable failure")
    counts, _ = _demo.run_observer()
    check(counts.get("airtable_pushed") == 1, f"retry did not push the row: {counts}")
    check_complete_row(("New Product Category", "New Product Launch"))
    return "alert and Attio unaffected; Airtable row pushed by the retry"


def scenario_f():
    _demo.reset(); _demo.script("scenario_b_signal.py")
    _demo.run_observer()
    record = airtable.list_rows()[0]
    airtable._request("PATCH", f"{airtable._table_url()}/{record['id']}", json={"fields": {"Status": "Approved"}})
    conn = db.connect()                                           # force the next run to push the row again
    conn.execute("UPDATE crm_sync SET airtable_status = 'failed'"); conn.commit(); conn.close()
    counts, _ = _demo.run_observer()
    check(counts.get("airtable_pushed") == 1, f"row was not pushed again: {counts}")
    rows = airtable.list_rows()
    check(len(rows) == 1, f"retry created a duplicate row ({len(rows)} rows)")
    check(rows[0]["fields"].get("Status") == "Approved", f"retry undid the approval: {rows[0]['fields'].get('Status')}")
    return "retry updated the row, kept Status = Approved, no duplicate"


A, T = {"attio"}, {"airtable"}
SCENARIOS = [("A  noise ignored", scenario_a, set()), ("B  new AI product", scenario_b, A),
             ("C  hiring push", scenario_c, A), ("D  Attio down, then retried", scenario_d, A),
             ("E  Airtable down, then retried", scenario_e, A | T), ("F  approval survives a retry", scenario_f, A | T)]
AVAILABLE = ({"attio"} if attio.enabled() else set()) | ({"airtable"} if airtable.enabled() else set())

failures = 0
with _demo.site_server():
    for n in range(1, args.times + 1):
        print(f"\nRehearsal {n} of {args.times}")
        for name, fn, needs in SCENARIOS:
            if needs - AVAILABLE:
                print(f"  SKIP  {name}: {', '.join(sorted(needs - AVAILABLE))} not configured")
                continue
            try:
                print(f"  PASS  {name}: {fn()}")
            except Exception as e:                                  # report every failure, keep going
                failures += 1
                print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    _demo.reset()
print(f"\n{'All rehearsals passed' if not failures else str(failures) + ' check(s) failed'}. Demo reset to baseline.")
sys.exit(1 if failures else 0)
