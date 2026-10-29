"""Bulk import of target accounts from a CSV. Preview first, write only on confirm."""
import csv
import io
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from . import db
from .fetcher import fetch

PAGE_TYPES = ["products", "pricing", "careers", "news", "about"]
PRIORITIES = {"high": "High", "medium": "Medium", "low": "Low"}
MAX_ROWS = 500
ALIASES = {"company_name": "company", "website_url": "website", "account_owner": "owner"}

TEMPLATE = ("company,website,industry,owner,priority," + ",".join(f"{t}_url" for t in PAGE_TYPES) + "\n"
            "Example Co,https://example.com/,SaaS,Your Name,High,,,,,\n")


def parse(text):
    """Return (rows, error). Header names are case-insensitive; website_url/account_owner are accepted."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = next(reader, [])
    fields = [ALIASES.get(f.strip().lower(), f.strip().lower()) for f in header]
    if "company" not in fields:
        return [], "The CSV needs a 'company' column (see the template)."
    if "website" not in fields and not any(f.endswith("_url") for f in fields):
        return [], "The CSV needs a 'website' column or at least one '<type>_url' column."
    rows = []
    for raw in reader:
        if not any(c.strip() for c in raw):
            continue
        rows.append({k: v.strip() for k, v in zip(fields, raw)})
        if len(rows) > MAX_ROWS:
            return [], f"Too many rows: the limit is {MAX_ROWS} accounts per import."
    return rows, None


def _discover(website):
    """Probe the usual paths under the site root; keep the first one that answers 200 per page type."""
    base = website if website.endswith("/") else website + "/"
    found = []
    for page_type in PAGE_TYPES:
        for path in (page_type, f"{page_type}.html"):
            url = urljoin(base, path)
            if fetch(url, timeout=5, retries=0)[0] == 200:
                found.append((page_type, url))
                break
    return found


def _check(row, conn, seen, discover):
    company, website = row.get("company", ""), row.get("website", "")
    out = {"Company": company, "Website": website, "Industry": row.get("industry", ""),
           "Owner": row.get("owner", ""), "pages": [], "Status": "error", "Note": ""}
    priority = PRIORITIES.get(row.get("priority", "medium").lower() or "medium")
    out["Priority"] = priority or row.get("priority", "")
    if not company:
        out["Note"] = "Missing company name."
    elif not priority:
        out["Note"] = f"Priority must be High, Medium or Low (got '{row['priority']}')."
    elif company.lower() in seen:
        out["Status"], out["Note"] = "skip", "Duplicate row in this file."
    elif conn.execute("SELECT 1 FROM accounts WHERE company_name = ?", (company,)).fetchone():
        out["Status"], out["Note"] = "skip", "Already in the account list."
    elif website and not website.startswith(("http://", "https://")):
        out["Note"] = "Website must start with http:// or https://"
    else:
        pages = [(t, row[f"{t}_url"]) for t in PAGE_TYPES if row.get(f"{t}_url")]
        if not pages and discover and website:
            pages = _discover(website)
        bad = next((u for _, u in pages if not u.startswith(("http://", "https://"))), None)
        taken = next((u for _, u in pages if conn.execute("SELECT 1 FROM pages WHERE url = ?", (u,)).fetchone()), None)
        if bad:
            out["Note"] = f"Page URL must start with http:// or https:// ({bad})"
        elif taken:
            out["Status"], out["Note"] = "skip", f"{taken} is already monitored."
        elif not pages:
            out["Note"] = "No monitorable pages found. Add <type>_url columns."
        else:
            out["pages"], out["Status"] = pages, "ready"
            out["Note"] = f"{len(pages)} pages: " + ", ".join(t for t, _ in pages)
    seen.add(company.lower())
    return out


def preview(rows, conn, discover=True):
    """Validate every row without writing. Each result has Status ready / skip / error."""
    seen = set()
    results = []
    # Duplicate/seen tracking is order-dependent, so check serially but probe sites in parallel first.
    if discover:
        with ThreadPoolExecutor(8) as pool:
            probes = {i: pool.submit(_discover, r["website"]) for i, r in enumerate(rows)
                      if r.get("company") and r.get("website", "").startswith(("http://", "https://"))
                      and not any(r.get(f"{t}_url") for t in PAGE_TYPES)}
            cache = {i: f.result() for i, f in probes.items()}
    else:
        cache = {}
    for i, row in enumerate(rows):
        if i in cache:
            row = {**row, **{f"{t}_url": u for t, u in cache[i]}}
        results.append(_check(row, conn, seen, discover=False))
    return results


def commit(results, conn):
    """Insert the ready rows. Returns (added, failures) where failures are (company, message)."""
    added, failures = 0, []
    for r in results:
        if r["Status"] != "ready":
            continue
        error = db.add_account(conn, r["Company"], r["Website"], r["Industry"], r["Owner"], r["Priority"], r["pages"])
        if error:
            failures.append((r["Company"], error))
        else:
            added += 1
    return added, failures
