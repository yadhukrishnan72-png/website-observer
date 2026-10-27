"""Save an alert in the CRM destinations, just before the Slack message is sent.

  Attio     the trigger on the company, and a draft message for its decision maker
  Airtable  one flat row per alert: contact, trigger, what changed, and the email draft

Either destination failing never blocks the alert: the failure is recorded and retried on the next run.
"""
import json
from datetime import datetime, timezone

from . import airtable, attio, outreach

MAX_CHANGE_CHARS = 1500
COLUMNS = ["status", "company_url", "person_url", "trigger_entry_id", "message_entry_id", "contact_name",
           "contact_title", "contact_email", "subject", "body", "model", "error", "airtable_status",
           "airtable_record_id", "airtable_url", "airtable_error"]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def prepare():
    """Create whatever is missing in Attio and Airtable. Returns a list of error strings (empty = ready)."""
    errors = []
    if attio.enabled():
        try:
            attio.ensure_schema()
        except attio.AttioError as e:
            errors.append(f"Attio: {e}")
    if airtable.enabled():
        try:
            airtable.ensure_schema()
        except airtable.AirtableError as e:
            errors.append(f"Airtable: {e}")
    return errors


def _load_alert(conn, change_id):
    row = conn.execute(
        "SELECT ch.id AS change_id, ch.detected_at, ch.added_blocks, ch.removed_blocks, a.company_name AS company, "
        "a.website_url, a.owner, p.url, p.page_type, an.signal_type, an.confidence, an.change_summary, "
        "an.why_it_matters, an.outreach_angle, an.evidence FROM changes ch JOIN pages p ON p.id = ch.page_id "
        "JOIN accounts a ON a.id = p.account_id "
        "JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id) WHERE ch.id = ?",
        (change_id,)).fetchone()
    return dict(row)


def _trigger_values(alert):
    return {"signal_type": alert["signal_type"], "confidence": alert["confidence"],
            "summary": alert["change_summary"], "why_it_matters": alert["why_it_matters"],
            "outreach_angle": alert["outreach_angle"], "evidence": alert["evidence"],
            "source_url": alert["url"], "detected_at": alert["detected_at"]}


def _what_changed(alert):
    """The summary, then the page text that was added and removed, capped for a table cell."""
    parts = [alert["change_summary"]]
    for label, key in (("Added on the page", "added_blocks"), ("Removed from the page", "removed_blocks")):
        blocks = json.loads(alert[key])
        if blocks:
            parts.append(f"{label}:\n" + "\n".join(f"- {b}" for b in blocks))
    text = "\n\n".join(parts)
    return text if len(text) <= MAX_CHANGE_CHARS else text[:MAX_CHANGE_CHARS - 1].rstrip() + "…"


def _airtable_fields(alert, result):
    first, _, last = (result.get("contact_name") or "").partition(" ")
    fields = {
        airtable.PRIMARY: f"{alert['company']}: {alert['signal_type']}", airtable.MERGE_FIELD: alert["change_id"],
        "Company": alert["company"], "Trigger type": alert["signal_type"], "Trigger reason": alert["why_it_matters"],
        "What changed on the website": _what_changed(alert), "Evidence": alert["evidence"],
        "Source page": alert["url"], "Confidence": alert["confidence"], "Suggested angle": alert["outreach_angle"],
        "Account owner": alert["owner"], "Detected at": alert["detected_at"],
        "First name": first, "Last name": last, "Title": result.get("contact_title"),
        "Contact email": result.get("contact_email"), "Email subject": result.get("subject"),
        "Email body": result.get("body"), "Drafted by": result.get("model"),
        "Attio link": result.get("person_url") or result.get("company_url")}
    return {k: v for k, v in fields.items() if v not in (None, "")}      # empty email/url cells are invalid


def get(conn, change_id):
    row = conn.execute("SELECT * FROM crm_sync WHERE change_id = ?", (change_id,)).fetchone()
    return dict(row) if row else None


def _sync_attio(alert, result):
    result.update(status="synced", error=None)
    try:
        company = attio.assert_company(alert["company"], attio.placeholder_domain(alert["website_url"]))
        result["company_url"] = company["web_url"]
        if not result["trigger_entry_id"]:
            result["trigger_entry_id"] = attio.add_entry("gtm_triggers", "companies", company["id"],
                                                         _trigger_values(alert))
        if not result["message_entry_id"]:
            draft = outreach.create_draft(alert, company=company)
            if draft["status"] == "crm_failed":
                raise attio.AttioError(draft["error"])
            contact = draft.get("contact") or {}
            result.update(contact_name=contact.get("name"), contact_title=contact.get("title"),
                          contact_email=contact.get("email"), person_url=contact.get("web_url"))
            if draft["status"] == "drafted":
                result.update(message_entry_id=draft["entry_id"], subject=draft["subject"], body=draft["body"],
                              model=draft["model"])
            else:
                result.update(status=draft["status"], error=draft.get("error"))
    except attio.AttioError as e:
        result.update(status="crm_failed", error=str(e))


def _sync_local(alert, result):
    """Safe demo mode (no Attio): decision maker from contacts.csv, draft kept in the local database only."""
    draft = outreach.create_local_draft(alert)
    contact = draft.get("contact") or {}
    result.update(status="local", error=None, contact_name=contact.get("name"), contact_title=contact.get("title"),
                  contact_email=contact.get("email"))
    if draft["status"] == "drafted":
        result.update(subject=draft["subject"], body=draft["body"], model=draft["model"])
    else:
        result.update(status=draft["status"], error=draft.get("error"))


def _sync_airtable(alert, result):
    if result["status"] == "crm_failed":                 # wait for Attio so the row carries the contact and draft
        result["airtable_status"] = "pending"
        return
    try:
        pushed = airtable.push_row(_airtable_fields(alert, result))
        result.update(airtable_status="pushed", airtable_record_id=pushed["record_id"], airtable_url=pushed["url"],
                      airtable_error=None)
    except airtable.AirtableError as e:
        result.update(airtable_status="failed", airtable_error=str(e))


def sync_change(conn, change_id):
    """Save one change in Attio and Airtable (or, with Attio off, keep the contact and draft locally). Returns the
    crm_sync row as a dict. Re-running continues where an earlier failed attempt stopped."""
    attio_on, airtable_on = attio.enabled(), airtable.enabled()
    alert = _load_alert(conn, change_id)
    row = get(conn, change_id) or {}
    result = {c: row.get(c) for c in COLUMNS}
    result.update(change_id=change_id, status=row.get("status") or ("synced" if attio_on else "local"))
    if attio_on and (not row or row["status"] == "crm_failed"):
        _sync_attio(alert, result)
    elif not attio_on and not row:
        _sync_local(alert, result)
    if airtable_on and result.get("airtable_status") != "pushed":
        _sync_airtable(alert, result)

    cols = ", ".join(COLUMNS)
    conn.execute(
        f"INSERT INTO crm_sync (change_id, synced_at, {cols}) VALUES (:change_id, :synced_at, "
        + ", ".join(f":{c}" for c in COLUMNS) + ") ON CONFLICT(change_id) DO UPDATE SET synced_at = :synced_at, "
        + ", ".join(f"{c} = :{c}" for c in COLUMNS),
        dict(result, synced_at=_now()))
    conn.commit()
    return result


def retry_failed(conn):
    """Retry changes whose Attio save or Airtable push failed. Call it before this run's new alerts are synced,
    so only failures from earlier runs are retried. Returns {'crm_<status>' / 'airtable_<status>': n}."""
    counts = {}
    rows = conn.execute("SELECT change_id, status, airtable_status FROM crm_sync WHERE status = 'crm_failed' "
                        "OR airtable_status IN ('failed', 'pending')").fetchall()
    for row in rows:
        result = sync_change(conn, row["change_id"])
        keys = []
        if row["status"] == "crm_failed":
            keys.append("crm_" + result["status"].removeprefix("crm_"))
        if row["airtable_status"] in ("failed", "pending"):
            keys.append("airtable_" + (result["airtable_status"] or "skipped"))
        for key in keys:
            counts[key] = counts.get(key, 0) + 1
        print(f"  CRM RETRY    change {row['change_id']}  [{', '.join(keys)}]")
    return counts


def slack_fields(sync):
    """Extra fields for the Slack alert from a crm_sync row."""
    if not sync:
        return {}
    return {"airtable_url": sync["airtable_url"], "airtable_status": sync["airtable_status"],
            "airtable_error": sync["airtable_error"], "crm_status": sync["status"], "crm_error": sync["error"],
            "company_url": sync["company_url"], "person_url": sync["person_url"],
            "contact_name": sync["contact_name"], "contact_title": sync["contact_title"],
            "draft_subject": sync["subject"], "draft_body": sync["body"]}
