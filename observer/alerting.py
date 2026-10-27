"""Decision D5, last gate: dedupe, then deliver every 'alert_ready' change."""
import hashlib
import re
from datetime import datetime, timedelta, timezone

from . import crm, db, slack

DEDUPE_DAYS = 30


def _now():
    return datetime.now(timezone.utc)


def fingerprint(company, page_type, signal_type, evidence):
    norm = re.sub(r"\s+", " ", evidence or "").strip().lower()
    return hashlib.sha256(f"{company}|{page_type}|{signal_type}|{norm}".encode("utf-8")).hexdigest()


def _already_alerted(conn, fp):
    cutoff = (_now() - timedelta(days=DEDUPE_DAYS)).isoformat(timespec="seconds")
    return conn.execute("SELECT 1 FROM alerts WHERE fingerprint = ? AND success = 1 AND sent_at >= ?",
                        (fp, cutoff)).fetchone() is not None


def _other_signals(conn, company, change_id):
    """Signal types already alerted for this company within the dedupe window, so a combined growth picture
    (funding + hiring + a new leader) shows up on the later alerts."""
    cutoff = (_now() - timedelta(days=DEDUPE_DAYS)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT DISTINCT an.signal_type FROM changes ch JOIN pages p ON p.id = ch.page_id "
        "JOIN accounts a ON a.id = p.account_id "
        "JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id) "
        "WHERE a.company_name = ? AND ch.status = 'alerted' AND ch.id != ? AND ch.detected_at >= ? "
        "ORDER BY ch.id", (company, change_id, cutoff)).fetchall()
    return [r["signal_type"] for r in rows]


def send_pending(conn):
    """Deliver all changes with status 'alert_ready'. Returns (consumed, {status: count})."""
    rows = conn.execute(
        "SELECT ch.id AS change_id, p.url, p.page_type, a.company_name, a.owner, a.priority, "
        "an.signal_type, an.confidence, an.change_summary, an.why_it_matters, an.outreach_angle, an.evidence "
        "FROM changes ch JOIN pages p ON p.id = ch.page_id JOIN accounts a ON a.id = p.account_id "
        "JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id) "
        "WHERE ch.status = 'alert_ready' ORDER BY ch.id").fetchall()
    counts = {}
    for r in rows:
        fp = fingerprint(r["company_name"], r["page_type"], r["signal_type"], r["evidence"])
        if _already_alerted(conn, fp):
            status, reason = "duplicate", f"same {r['signal_type']} already alerted within {DEDUPE_DAYS} days"
        else:
            sync = crm.sync_change(conn, r["change_id"])      # trigger + draft in Attio; never blocks the alert
            text = slack.format_alert({
                "other_signals": _other_signals(conn, r["company_name"], r["change_id"]),
                "company": r["company_name"], "change_summary": r["change_summary"], "signal_type": r["signal_type"],
                "why_it_matters": r["why_it_matters"], "outreach_angle": r["outreach_angle"], "url": r["url"],
                "confidence": r["confidence"], "owner": r["owner"], "priority": r["priority"],
                **crm.slack_fields(sync)})
            if slack.webhook_url():
                ok, error = slack.post_to_slack(text)
                channel = "slack"
                if not ok:
                    slack.print_console(text)       # never lose an alert
            else:
                slack.print_console(text)
                ok, error, channel = True, None, "console"
            conn.execute("INSERT INTO alerts (change_id, fingerprint, channel, sent_at, success, error) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (r["change_id"], fp, channel, _now().isoformat(timespec="seconds"), int(ok), error))
            status, reason = ("alerted", f"sent via {channel}") if ok else ("alert_failed", f"Slack failed: {error}")
        db.set_change_status(conn, r["change_id"], status, reason)
        counts[status] = counts.get(status, 0) + 1
        print(f"  {status.upper():12} {r['url']}  [{reason}]")
    conn.commit()
    return len(rows), counts
