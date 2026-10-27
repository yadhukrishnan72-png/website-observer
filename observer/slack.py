"""Alert formatting and delivery: Slack incoming webhook, with a console fallback."""
import os
import sys

import requests


def _airtable_section(a):
    status = a.get("airtable_status")
    if status == "pushed" and a.get("airtable_url"):
        return f"\n\n*Airtable:*\n<{a['airtable_url']}|Row in Airtable>"
    if status in ("failed", "pending"):
        why = a.get("airtable_error") or "waiting for the Attio save"
        return f"\n\n*Airtable:*\nRow not saved yet ({why}). It will be retried on the next run."
    return ""


def _crm_section(a):
    """Decision maker and Attio links, then the Airtable row link (the email draft is not repeated in Slack).
    Each part is empty when that destination is not configured."""
    return _attio_section(a) + _airtable_section(a)


def _attio_section(a):
    status = a.get("crm_status")
    if not status:
        return ""
    links = " · ".join(f"<{a[k]}|{label}>" for k, label in (("company_url", "Company in Attio"),
                                                          ("person_url", "Contact in Attio")) if a.get(k))
    if status == "crm_failed":
        return f"\n\n*CRM:*\nNot saved to Attio ({a.get('crm_error')}). It will be retried on the next run."
    contact = (f"{a['contact_name']}, {a['contact_title']}" if a.get("contact_name")
               else "no decision maker on file for this company")
    section = f"\n\n*Decision maker:*\n{contact}" + (f"\n\n*Attio:*\n{links}" if links else "")
    if status == "draft_failed":                      # the draft itself lives in Airtable and Attio, not in Slack
        section += f"\n\n*Draft message:*\nNot created ({a.get('crm_error')})."
    return section


def format_alert(a):
    """a: dict with company, change_summary, signal_type, why_it_matters, outreach_angle, url,
    confidence, owner, priority. Optional Attio fields come from crm.slack_fields()."""
    return (
        f"🚨 *New GTM Trigger — {a['company']}*\n\n"
        f"*Change:*\n{a['change_summary']}\n\n"
        f"*Signal type:*\n{a['signal_type']}\n\n"
        f"*Why it matters:*\n{a['why_it_matters']}\n\n"
        f"*Suggested outreach angle:*\n{a['outreach_angle']}\n\n"
        f"*Source:*\n{a['url']}\n\n"
        f"*Confidence:*\n{a['confidence']}"
        f"{_crm_section(a)}{_also_section(a)}\n\n"
        f"_Account owner: {a['owner']} · Priority: {a['priority']}_"
    )


def _also_section(a):
    """Other signals already alerted for this account: the combined growth picture."""
    others = a.get("other_signals")
    return f"\n\n*Also on this account:*\n{' · '.join(others)}" if others else ""


def webhook_url():
    return os.environ.get("SLACK_WEBHOOK_URL", "").strip()


def post_to_slack(text, url=None, timeout=10):
    """Returns (ok, error)."""
    url = url or webhook_url()
    try:
        resp = requests.post(url, json={"text": text}, timeout=timeout)
    except requests.RequestException as e:
        return False, f"{type(e).__name__}: {e}"
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    return True, None


def print_console(text):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    bar = "=" * 60
    print(f"\n{bar}\n[CONSOLE ALERT]\n{text}\n{bar}\n")
