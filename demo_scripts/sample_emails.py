"""Generate the outreach email for every demo scenario through the real pipeline and review them.

Runs the observer over the scenario bundle with Slack, Attio and Airtable switched off (nothing leaves this machine;
contacts come from contacts.csv), prints each email next to its internal analysis, then audits the whole set:
length, banned phrases, repeated sentences, and the four-part structure.

    python demo_scripts/sample_emails.py                      # every scenario in the bundle
    python demo_scripts/sample_emails.py --only "Cloudloom,Ledgerly"
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

parser = argparse.ArgumentParser()
parser.add_argument("--only", help="comma-separated company names to show (all are still generated)")
parser.add_argument("--scenarios", help="comma-separated scenario ids to apply (default: the whole bundle), "
                                        "e.g. acme-hiring to see a single-signal email on its own")
parser.add_argument("--keep", action="store_true", help="leave the scenarios applied afterwards")
args = parser.parse_args()
for name in ("SLACK_WEBHOOK_URL", "ATTIO_API_KEY", "AIRTABLE_TOKEN", "AIRTABLE_BASE_ID"):
    os.environ[name] = ""                       # set before observer.config loads .env, which never overrides it

import _demo  # noqa: E402
import scenarios  # noqa: E402
from observer import db, playbooks  # noqa: E402

TITLES = {s["company"]: s["title"] for s in scenarios.SCENARIOS if s["bundle"]}


def fetch():
    conn = db.connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT ch.id, a.company_name AS company, an.signal_type, cs.contact_name, cs.contact_title, cs.subject, "
            "cs.body, cs.draft_notes, cs.model FROM crm_sync cs JOIN changes ch ON ch.id = cs.change_id "
            "JOIN pages p ON p.id = ch.page_id JOIN accounts a ON a.id = p.account_id "
            "JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id) "
            "WHERE cs.body IS NOT NULL ORDER BY ch.id")]
    finally:
        conn.close()


with _demo.site_server():
    _demo.reset()
    chosen = args.scenarios.split(",") if args.scenarios else [s["id"] for s in scenarios.SCENARIOS if s["bundle"]]
    for sid in chosen:
        ok, message = scenarios.apply(sid.strip())
        if not ok:
            sys.exit(f"could not apply {sid}: {message}")
    _demo.run_observer()
    emails = fetch()
    if not args.keep:
        _demo.reset()

wanted = {c.strip() for c in args.only.split(",")} if args.only else None
for e in emails:
    if wanted and e["company"] not in wanted:
        continue
    notes = json.loads(e["draft_notes"]) if e["draft_notes"] else {}
    label = notes.get("playbook") or e["signal_type"]
    print("=" * 100)
    print(f"{e['company']}  |  {e['signal_type']}  |  playbook: {label}  |  to {e['contact_name']}, {e['contact_title']}")
    print(f"Subject: {e['subject']}\n")
    print(e["body"])
    print(f"\n  [{len(e['body'].split())} words | drafted by {e['model']}]")
    print(f"  Internal analysis: Clay angle: {notes.get('clay_angle')}")
    print(f"                     evidence: \"{notes.get('evidence')}\"   source: {notes.get('source_url')}")
    if notes.get("also_on_account"):
        print(f"                     combined with: {', '.join(notes['also_on_account'])}")

# ---- audit the whole set -------------------------------------------------------------------------------------------
print("\n" + "=" * 100 + "\nAUDIT of", len(emails), "emails")
counts = [len(e["body"].split()) for e in emails]
print(f"word count: min {min(counts)}, max {max(counts)}, target {playbooks.MIN_WORDS}-{playbooks.MAX_WORDS} ->",
      "all in range" if all(playbooks.MIN_WORDS <= c <= playbooks.MAX_WORDS for c in counts) else "OUT OF RANGE")
low = [(e["company"], p) for e in emails for p in playbooks.BANNED if p in (e["subject"] + " " + e["body"]).lower()]
print("banned phrases:", low or "none")
paras = [[p for p in e["body"].split("\n\n") if p.strip()] for e in emails]
sentence_counts = Counter(p for ps in paras for p in ps[1:-1] if not p.startswith("Saw") and not p.startswith("Noticed"))
repeated = {s[:60]: n for s, n in sentence_counts.items() if n > 1}
print("sentences reused verbatim across emails:", repeated or "none")
fits = Counter(ps[-3] for ps in paras)
print(f"distinct Clay value-proposition paragraphs: {len(fits)} of {len(emails)} emails")
print(f"distinct subject lines: {len({e['subject'] for e in emails})} of {len(emails)}")
print("openers:", Counter(re.match(r"(\w+ \w+)", ps[1]).group(1) for ps in paras).most_common())
