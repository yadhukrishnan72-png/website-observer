"""Add the demo target companies and their placeholder decision makers to Attio.

Companies come from accounts.csv, contacts from contacts.csv. Re-running is safe (upserts).
The monitored sites are on localhost, which Attio cannot match on, so each company gets a
placeholder domain "<slug>.example.com" that exists only in Attio (Attio rejects the bare
".example" TLD; it matches on the full subdomain, so each company stays a separate record).

    python demo_scripts/seed_attio.py            # all companies and contacts
    python demo_scripts/seed_attio.py --only "Acme AI"
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from observer import attio  # noqa: E402


def read_csv(name):
    with open(ROOT / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="seed a single company by name")
    args = parser.parse_args()

    if not attio.enabled():
        sys.exit("ATTIO_API_KEY is not set in .env")
    workspace, slug = attio.check()
    print(f"Attio workspace: {workspace} ({slug})")

    contacts = {c["company_name"]: c for c in read_csv("contacts.csv")}
    for acct in read_csv("accounts.csv"):
        name = acct["company_name"]
        if args.only and name != args.only:
            continue
        description = f"{acct['industry']} (demo target account, owner {acct['account_owner']}, priority {acct['priority']})"
        company = attio.assert_company(name, attio.placeholder_domain(acct["website_url"]), description)
        line = f"  company {name:24} {company['id'][:8]}"
        contact = contacts.get(name)
        if contact:
            person = attio.assert_person(contact["contact_name"], contact["job_title"], contact["email"], company["id"])
            line += f"  contact {contact['contact_name']} ({contact['job_title']}) {person['id'][:8]}"
        print(line)


if __name__ == "__main__":
    main()
