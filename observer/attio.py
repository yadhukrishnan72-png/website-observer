"""Attio CRM client (REST v2). Upserts are idempotent: the same company or person is updated, never duplicated.

The API key comes from ATTIO_API_KEY in .env and is never logged or included in errors.
"""
import os
import time
from urllib.parse import urlparse

import requests

from . import config  # noqa: F401  (loads .env)

BASE = "https://api.attio.com/v2"


class AttioError(Exception):
    pass


def api_key():
    return os.environ.get("ATTIO_API_KEY", "").strip()


def enabled():
    return bool(api_key())


def _request(method, path, retries=2, retry_network=True, **kwargs):
    """retry_network=False for creates: after a timeout the entry may already exist, so resending would duplicate it."""
    headers = {"Authorization": f"Bearer {api_key()}"}
    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, BASE + path, headers=headers, timeout=15, **kwargs)
        except requests.RequestException as e:
            if attempt == retries or not retry_network:
                raise AttioError(f"{type(e).__name__}: {e}") from None
            time.sleep(1 + attempt)
            continue
        if resp.status_code == 429 and attempt < retries:
            time.sleep(float(resp.headers.get("Retry-After", 1)))
            continue
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message", "")
            except ValueError:
                detail = resp.text[:200]
            raise AttioError(f"HTTP {resp.status_code} on {method} {path}: {detail}")
        return resp.json()


def check():
    """Returns the workspace name and slug for the configured key."""
    d = _request("GET", "/self")
    return d.get("workspace_name"), d.get("workspace_slug")


def _record_summary(data):
    return {"id": data["id"]["record_id"], "web_url": data.get("web_url")}


def assert_company(name, domain, description=None):
    values = {"name": [{"value": name}], "domains": [{"domain": domain}]}
    if description:
        values["description"] = [{"value": description}]
    d = _request("PUT", "/objects/companies/records", params={"matching_attribute": "domains"},
                 json={"data": {"values": values}})
    return _record_summary(d["data"])


def assert_person(full_name, job_title, email, company_record_id):
    first, _, last = full_name.partition(" ")
    values = {
        "name": [{"first_name": first, "last_name": last, "full_name": full_name}],
        "email_addresses": [{"email_address": email}],
        "job_title": [{"value": job_title}],
        "company": [{"target_object": "companies", "target_record_id": company_record_id}],
    }
    d = _request("PUT", "/objects/people/records", params={"matching_attribute": "email_addresses"},
                 json={"data": {"values": values}})
    return _record_summary(d["data"])


# --------------------------------------------------------------------------- lists

SIGNAL_TYPES = [
    "New Product Launch", "New Product Category", "Pricing Change", "Leadership Change",
    "Funding Announcement", "Major Partnership", "Market Expansion", "Strategic Initiative",
    "Hiring / Growth Signal",
]

# list slug -> (title, parent object, [(attribute slug, title, type, select options)])
SCHEMA = {
    "gtm_triggers": ("GTM Triggers", "companies", [
        ("signal_type", "Signal type", "select", SIGNAL_TYPES),
        ("confidence", "Confidence", "select", ["High", "Medium", "Low"]),
        ("summary", "Change summary", "text", None),
        ("why_it_matters", "Why it matters", "text", None),
        ("outreach_angle", "Suggested outreach angle", "text", None),
        ("evidence", "Evidence", "text", None),
        ("source_url", "Source URL", "text", None),
        ("detected_at", "Detected at", "timestamp", None),
    ]),
    "outreach_messages": ("Outreach Messages", "people", [
        ("subject", "Subject", "text", None),
        ("message_body", "Message", "text", None),
        ("status", "Status", "select", ["Draft", "Approved", "Sent"]),
        ("signal", "Signal", "text", None),
        ("company", "Company", "text", None),
        ("account_owner", "Account owner", "text", None),
        ("drafted_by", "Drafted by", "text", None),
        ("created_at", "Created at", "timestamp", None),
    ]),
}


def ensure_schema():
    """Create the lists, attributes and select options that are missing. Safe to re-run.
    Returns the list of things it created."""
    created = []
    existing = {l["api_slug"] for l in _request("GET", "/lists")["data"]}
    for slug, (title, parent, attrs) in SCHEMA.items():
        if slug not in existing:
            _request("POST", "/lists", json={"data": {
                "name": title, "api_slug": slug, "parent_object": parent,
                "workspace_access": "full-access", "workspace_member_access": []}})
            created.append(f"list {title}")
        have = {a["api_slug"] for a in _request("GET", f"/lists/{slug}/attributes")["data"]}
        for a_slug, a_title, a_type, options in attrs:
            if a_slug in have:
                continue
            _request("POST", f"/lists/{slug}/attributes", json={"data": {
                "title": a_title, "description": "", "api_slug": a_slug, "type": a_type,
                "is_required": False, "is_unique": False, "is_multiselect": False,
                "default_value": None, "config": {}}})
            for option in options or []:
                _request("POST", f"/lists/{slug}/attributes/{a_slug}/options", json={"data": {"title": option}})
            created.append(f"{title}.{a_title}")
    return created


def add_entry(list_slug, parent_object, parent_record_id, values):
    d = _request("POST", f"/lists/{list_slug}/entries", retry_network=False, json={"data": {
        "parent_object": parent_object, "parent_record_id": parent_record_id, "entry_values": values}})
    return d["data"]["id"]["entry_id"]


def delete_entry(list_slug, entry_id):
    _request("DELETE", f"/lists/{list_slug}/entries/{entry_id}")


def clear_entries():
    """Demo reset: delete every entry in the two tool-created lists (never touches companies or people).
    Returns the number deleted."""
    n = 0
    for slug in SCHEMA:
        for row in _request("POST", f"/lists/{slug}/entries/query", json={"limit": 500})["data"]:
            try:
                delete_entry(slug, row["id"]["entry_id"])
            except AttioError as e:
                if "HTTP 404" not in str(e):
                    raise
                continue                          # already gone: Attio's list queries can lag behind deletes
            n += 1
    return n


# --------------------------------------------------------------------------- contacts

def placeholder_domain(website_url):
    """The demo sites live on localhost, which Attio cannot match on, so each company gets a
    stand-in domain that exists only in Attio. Attio rejects the bare .example TLD and matches
    on the full subdomain, so <slug>.example.com keeps every company a separate record."""
    return urlparse(website_url).path.strip("/") + ".example.com"


def find_contacts(company_record_id):
    """People linked to a company record, oldest first (the BDR's decision makers)."""
    d = _request("POST", "/objects/people/records/query", json={
        "filter": {"company": {"target_object": "companies", "target_record_id": company_record_id}},
        "sorts": [{"direction": "asc", "attribute": "created_at"}], "limit": 20})
    contacts = []
    for rec in d["data"]:
        v = rec["values"]
        contacts.append({
            "id": rec["id"]["record_id"], "web_url": rec.get("web_url"),
            "name": (v.get("name") or [{}])[0].get("full_name", ""),
            "title": (v.get("job_title") or [{}])[0].get("value", ""),
            "email": (v.get("email_addresses") or [{}])[0].get("email_address", "")})
    return contacts
