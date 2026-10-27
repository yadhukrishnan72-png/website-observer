"""Test every demo scenario against the real pipeline: apply it, run the observer, check the outcome.

    python demo_scripts/test_scenarios.py              # whole bundle at once, then checks each company (a few minutes)
    python demo_scripts/test_scenarios.py --isolated   # each scenario alone from a clean baseline (slow)
    python demo_scripts/test_scenarios.py --slack      # post the alerts to the real Slack channel

Checks: every signal scenario alerts exactly once per expected signal and only for its own company; the
insignificant changes are detected but ignored; the Attio entries and Airtable rows match the alerts (when
configured); the combined-signals line appears; a second run does nothing; and a repeated alert is blocked
as a duplicate. Alerts print to the console unless --slack is given.
"""
import argparse
import os
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--isolated", action="store_true", help="run each scenario alone from a clean baseline")
parser.add_argument("--slack", action="store_true", help="post alerts to the real Slack channel")
args = parser.parse_args()
if not args.slack:
    os.environ["SLACK_WEBHOOK_URL"] = ""        # set before observer.config loads .env, which never overrides it

import _demo  # noqa: E402
import scenarios  # noqa: E402
from observer import airtable, alerting, attio, db  # noqa: E402

IGNORED = {"ignored_rule", "ignored_llm"}
failures = []


def report(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def change_rows():
    conn = db.connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT a.company_name AS company, p.page_type AS page, ch.status, ch.reason, an.signal_type "
            "FROM changes ch JOIN pages p ON p.id = ch.page_id JOIN accounts a ON a.id = p.account_id "
            "LEFT JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id) "
            "ORDER BY ch.id")]
    finally:
        conn.close()


def check_scenario(s, rows):
    """Returns (ok, detail) for one scenario given all change rows."""
    mine = [r for r in rows if r["company"] == s["company"] and r["page"] in s["pages"]]
    alerted = [r for r in mine if r["status"] == "alerted"]
    if s["kind"] == "ignored":
        ok = bool(mine) and not alerted and all(r["status"] in IGNORED for r in mine)
        how = ", ".join(sorted({r["status"] for r in mine})) or "no change detected"
        return ok, f"{s['company']}: detected and ignored ({how})" if ok else f"{s['company']}: {how}; alerted={len(alerted)}"
    pool, matched = list(alerted), []
    for acceptable in s["alerts"]:
        hit = next((r for r in pool if r["signal_type"] in acceptable), None)
        if hit:
            pool.remove(hit)
            matched.append(hit["signal_type"])
    others = [r["status"] for r in mine if r["status"] != "alerted"]
    ok = len(matched) == len(s["alerts"]) and not pool and not others
    return ok, f"{s['company']}: " + (" + ".join(matched) if ok else f"expected {s['alerts']}, got {[r['signal_type'] for r in alerted]} {others}")


def attio_counts(expected, timeout=40):
    deadline = time.time() + timeout
    while True:
        counts = {slug: len(attio._request("POST", f"/lists/{slug}/entries/query", json={"limit": 500})["data"])
                  for slug in attio.SCHEMA}
        if counts == expected or time.time() >= deadline:
            return counts
        time.sleep(1)


def table_rows(expected_count, timeout=40):
    deadline = time.time() + timeout
    while True:
        rows = [r["fields"] for r in airtable.list_rows()]
        if len(rows) == expected_count or time.time() >= deadline:
            return rows
        time.sleep(1)


def check_destinations(alert_rows):
    n = len(alert_rows)
    if attio.enabled():
        counts = attio_counts({"gtm_triggers": n, "outreach_messages": n})
        report("Attio has one trigger and one draft per alert", counts == {"gtm_triggers": n, "outreach_messages": n}, str(counts))
    if airtable.enabled():
        rows = table_rows(n)
        want = sorted((r["company"], r["signal_type"]) for r in alert_rows)
        got = sorted((r.get("Company"), r.get("Trigger type")) for r in rows)
        report("Airtable has one complete Draft row per alert", want == got and all(
            r.get("Status") == "Draft" and r.get("Email subject") and r.get("Email body") for r in rows),
            f"{len(rows)} rows")


def run_together():
    print("Reset, apply the whole bundle, run the observer once")
    _demo.reset()
    for sid, ok, message in scenarios.apply_bundle():
        if not ok:
            report(f"apply {sid}", False, message)
    counts, out = _demo.run_observer()
    rows = change_rows()
    alert_rows = [r for r in rows if r["status"] == "alerted"]
    print()
    for s in (x for x in scenarios.SCENARIOS if x["bundle"]):
        ok, detail = check_scenario(s, rows)
        report(f"{s['id']:22} {s['title']}", ok, detail)
    expected = scenarios.expected_alerts()
    companies = {r["company"] for r in alert_rows}
    report("alerts only for the assigned companies", len(alert_rows) == expected and companies == {
        s["company"] for s in scenarios.SCENARIOS if s["bundle"] and s["alerts"]},
        f"{len(alert_rows)} alerts across {len(companies)} companies (expected {expected})")
    if not args.slack:
        report("combined signals shown on the later Orbit CRM alerts", "*Also on this account:*" in out
               and out.count("*Also on this account:*") == 3, f"{out.count('*Also on this account:*')} 'also' lines (Acme has 2 alerts, Orbit 3)")
    check_destinations(alert_rows)

    counts2, _ = _demo.run_observer()
    report("a second run changes nothing", counts2 == {"unchanged": _demo.EXPECTED_PAGES}, str(counts2))

    # duplicate prevention: push a delivered alert back to alert_ready and run delivery again
    conn = db.connect()
    cid = conn.execute("SELECT id FROM changes WHERE status = 'alerted' ORDER BY id LIMIT 1").fetchone()["id"]
    conn.execute("UPDATE changes SET status = 'alert_ready' WHERE id = ?", (cid,)); conn.commit()
    _, dup_counts = alerting.send_pending(conn)
    conn.close()
    report("a repeated alert is blocked as a duplicate", dup_counts == {"duplicate": 1}, str(dup_counts))
    if attio.enabled():
        report("the duplicate wrote nothing new to Attio",
               attio_counts({"gtm_triggers": len(alert_rows), "outreach_messages": len(alert_rows)}, timeout=5)
               == {"gtm_triggers": len(alert_rows), "outreach_messages": len(alert_rows)})


def run_isolated():
    for s in scenarios.SCENARIOS:
        print(f"\n{s['id']}: reset, apply, run")
        _demo.reset()
        ok, message = scenarios.apply(s["id"])
        if not ok:
            report(f"apply {s['id']}", False, message)
            continue
        _demo.run_observer()
        rows = change_rows()
        alert_rows = [r for r in rows if r["status"] == "alerted"]
        ok, detail = check_scenario(s, rows)
        report(f"{s['id']:22} {s['title']}", ok, detail)
        report("no alert for any other company", all(r["company"] == s["company"] for r in alert_rows)
               and len(alert_rows) == len(s["alerts"]), f"{len(alert_rows)} alerts")
        if attio.enabled() or airtable.enabled():
            check_destinations(alert_rows)


with _demo.site_server():
    try:
        run_isolated() if args.isolated else run_together()
    finally:
        _demo.reset()
print(f"\n{'All checks passed' if not failures else str(len(failures)) + ' check(s) failed: ' + ', '.join(failures)}. Demo reset to baseline.")
sys.exit(1 if failures else 0)
