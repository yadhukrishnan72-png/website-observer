"""Airtable client: one row per alert in the "Trigger Outreach" table (the BDR's flat working list).

Rows are upserted on "Change ID", so a retry updates the row instead of duplicating it. "Status" is set to
Draft only when a row is first created, so a retry never overwrites an Approved status the BDR set.
The token and base come from .env and are never logged or included in errors.

.env accepts AIRTABLE_BASE_ID as a bare id (app...) or a pasted Airtable URL; the base id (and the table id,
if the URL contains it) are extracted. AIRTABLE_TABLE is used when no table id is given.
"""
import os
import re
import time

import requests

from . import analyzer, config  # noqa: F401  (config loads .env)

API = "https://api.airtable.com/v0"
PRIMARY = "Trigger"
MERGE_FIELD = "Change ID"
BATCH = 10                                   # Airtable's limit per request

DATETIME = {"timeZone": "utc", "dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"}}


def _choices(names):
    return {"choices": [{"name": n} for n in names]}


# (field name, Airtable type, options). The primary field is renamed to PRIMARY, not created.
FIELDS = [
    (MERGE_FIELD, "number", {"precision": 0}),
    ("First name", "singleLineText", None),
    ("Last name", "singleLineText", None),
    ("Title", "singleLineText", None),
    ("Company", "singleLineText", None),
    ("Contact email", "email", None),
    ("Trigger type", "singleSelect", _choices(analyzer.SIGNAL_TYPES)),
    ("Trigger reason", "multilineText", None),
    ("What changed on the website", "multilineText", None),
    ("Evidence", "multilineText", None),
    ("Source page", "url", None),
    ("Confidence", "singleSelect", _choices(["High", "Medium", "Low"])),
    ("Suggested angle", "multilineText", None),
    ("Email subject", "singleLineText", None),
    ("Email body", "multilineText", None),
    ("Status", "singleSelect", _choices(["Draft", "Approved"])),
    ("Drafted by", "singleLineText", None),
    ("Account owner", "singleLineText", None),
    ("Detected at", "dateTime", DATETIME),
    ("Attio link", "url", None),
]


class AirtableError(Exception):
    pass


def token():
    return os.environ.get("AIRTABLE_TOKEN", "").strip()


def ids():
    """(base id, table name or id) from .env. AIRTABLE_TABLE wins; a table id pasted inside AIRTABLE_BASE_ID
    is the fallback."""
    raw = os.environ.get("AIRTABLE_BASE_ID", "")
    base = re.search(r"app[A-Za-z0-9]{14}", raw)
    table_in_url = re.search(r"tbl[A-Za-z0-9]{14}", raw)
    table = os.environ.get("AIRTABLE_TABLE", "").strip() or (table_in_url.group() if table_in_url else "")
    return (base.group() if base else ""), table


def enabled():
    base, table = ids()
    return bool(token() and base and table)


def _request(method, url, retries=1, **kwargs):
    headers = {"Authorization": f"Bearer {token()}"}
    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, url, headers=headers, timeout=20, **kwargs)
        except requests.RequestException as e:
            if attempt == retries:
                raise AirtableError(f"{type(e).__name__}: {e}") from None
            time.sleep(1 + attempt)
            continue
        if resp.status_code in (500, 502, 503, 504) and attempt < retries:        # transient server trouble
            time.sleep(1 + attempt)
            continue
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
                detail = err.get("message", "") if isinstance(err, dict) else str(err)
            except ValueError:
                detail = resp.text[:200]
            raise AirtableError(f"HTTP {resp.status_code} on {method} {url.split('?')[0].rsplit('/', 1)[-1]}: {detail}")
        return resp.json()


_table_id_cache = {}


def table_id():
    """The table's id (browser links need the id, not the name). Looked up once from the base's schema."""
    base, table = ids()
    if table.startswith("tbl"):
        return table
    if (base, table) not in _table_id_cache:
        tables = _request("GET", f"{API}/meta/bases/{base}/tables")["tables"]
        found = next((t for t in tables if t["name"] == table), None)
        if found is None:
            raise AirtableError(f"table {table!r} not found in the base; run ensure_schema() to create it")
        _table_id_cache[(base, table)] = found["id"]
    return _table_id_cache[(base, table)]


def _table_url():
    return f"{API}/{ids()[0]}/{table_id()}"


def row_url(record_id):
    return f"https://airtable.com/{ids()[0]}/{table_id()}/{record_id}"


# --------------------------------------------------------------------------- schema

def _field_body(name, ftype, options):
    body = {"name": name, "type": ftype}
    if options:
        body["options"] = options
    return body


def ensure_schema():
    """Create the table if it does not exist, or add any missing fields to it. Needs schema.bases:read and
    :write. A table that is not ours (its first field is not "Trigger") is never modified. Returns what it created."""
    base, table = ids()
    tables = _request("GET", f"{API}/meta/bases/{base}/tables")["tables"]
    found = next((t for t in tables if table in (t["id"], t["name"])), None)
    if found is None:
        made = _request("POST", f"{API}/meta/bases/{base}/tables", json={
            "name": table, "description": "Created by the Daily Website Observer: one row per alert.",
            "fields": [_field_body(PRIMARY, "singleLineText", None)] + [_field_body(*f) for f in FIELDS]})
        _table_id_cache[(base, table)] = made["id"]
        return [f"table {table}"]
    primary = next(f for f in found["fields"] if f["id"] == found["primaryFieldId"])
    if primary["name"] != PRIMARY:
        raise AirtableError(f"table {table!r} already exists and is not an Observer table; "
                            f"set AIRTABLE_TABLE to a new name and it will be created")
    have = {f["name"] for f in found["fields"]}
    created = []
    for name, ftype, options in FIELDS:
        if name not in have:
            _request("POST", f"{API}/meta/bases/{base}/tables/{found['id']}/fields", json=_field_body(name, ftype, options))
            created.append(name)
    return created


# --------------------------------------------------------------------------- rows

def push_row(fields):
    """Upsert one row keyed on Change ID. Returns {'record_id', 'url', 'created'}."""
    d = _request("PATCH", _table_url(), json={
        "performUpsert": {"fieldsToMergeOn": [MERGE_FIELD]}, "typecast": False,
        "records": [{"fields": fields}]})
    record = d["records"][0]
    created = record["id"] in d.get("createdRecords", [])
    if not record["fields"].get("Status"):        # only when empty, so a retry never undoes an approval but
        _request("PATCH", f"{_table_url()}/{record['id']}", json={"fields": {"Status": "Draft"}})  # a row that
    return {"record_id": record["id"], "url": row_url(record["id"]), "created": created}          # missed it is fixed


def list_rows():
    rows, offset = [], None
    while True:
        d = _request("GET", _table_url(), params={"pageSize": 100, **({"offset": offset} if offset else {})})
        rows += d["records"]
        offset = d.get("offset")
        if not offset:
            return rows


def clear_rows():
    """Demo reset: delete every row in the Trigger Outreach table. Returns the number deleted."""
    rows = list_rows()
    for i in range(0, len(rows), BATCH):
        _request("DELETE", _table_url(), params=[("records[]", r["id"]) for r in rows[i:i + BATCH]])
    return len(rows)
