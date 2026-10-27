"""Pipeline so far: fetch -> clean -> hash -> diff -> noise rules -> log the change.

Changes that survive the noise rules are analyzed (Claude, or the mock stand-in) and routed.

Usage:  python -m observer.pipeline
"""
import json
from datetime import datetime, timezone

from . import alerting, analyzer, crm, db
from .cleaner import clean, content_hash
from .differ import diff_blocks
from .fetcher import fetch
from .noise_rules import classify_boilerplate, filter_noise

SHRINK_LIMIT = 0.30        # new content under 30% of old looks like a fetch problem, not a real change


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _boilerplate_changes(old, new):
    """Rule names for boilerplate entries that were added or removed."""
    old_set, new_set = set(old), set(new)
    return ([{"text": e, "rule": classify_boilerplate(e), "side": "removed"} for e in old if e not in new_set]
            + [{"text": e, "rule": classify_boilerplate(e), "side": "added"} for e in new if e not in old_set])


def check_page(conn, page):
    """Returns 'new', 'unchanged', 'error', or the status of the logged change."""
    status, html, error = fetch(page["url"])
    conn.execute("UPDATE pages SET last_checked_at = ? WHERE id = ?", (now(), page["id"]))
    if html is None:
        print(f"  ERROR {page['url']}: {error}")
        return "error"

    blocks, boilerplate = clean(html)
    new_hash = content_hash(blocks)
    prev = db.latest_snapshot(conn, page["id"])
    if prev is None:
        db.save_snapshot(conn, page["id"], now(), status, new_hash, blocks, boilerplate)
        return "new"

    content_same = prev["content_hash"] == new_hash
    old_boiler = json.loads(prev["boilerplate"])
    if content_same and old_boiler == boilerplate:
        return "unchanged"

    new_id = db.save_snapshot(conn, page["id"], now(), status, new_hash, blocks, boilerplate)
    old_blocks = json.loads(prev["blocks"])
    ignored = _boilerplate_changes(old_boiler, boilerplate)
    added, removed = [], []

    old_len, new_len = sum(map(len, old_blocks)), sum(map(len, blocks))
    if not content_same and old_len and new_len < SHRINK_LIMIT * old_len:
        outcome, reason = "review", f"possible fetch problem: content shrank to {new_len * 100 // old_len}% of previous"
    else:
        if not content_same:
            added, removed, noise = filter_noise(diff_blocks(old_blocks, blocks))
            ignored += noise
        if added or removed:
            outcome, reason = "pending_llm", "content changed beyond the noise rules"
        else:
            rules = sorted({i["rule"] for i in ignored})
            outcome, reason = "ignored_rule", ", ".join(rules)

    db.save_change(conn, page["id"], prev["id"], new_id, now(), added, removed, ignored, outcome, reason)
    print(f"  {outcome.upper():12} {page['url']}  [{reason}]")
    return outcome


def run_observer(conn=None):
    own_conn = conn is None
    conn = conn or db.connect()
    db.seed_from_csv(conn)

    started = now()
    pages = conn.execute(
        "SELECT p.* FROM pages p JOIN accounts a ON a.id = p.account_id WHERE a.active = 1 ORDER BY p.id"
    ).fetchall()
    counts = {}
    for page in pages:
        result = check_page(conn, page)
        counts[result] = counts.get(result, 0) + 1
    conn.commit()
    for status, n in analyzer.process_pending(conn).items():
        counts[status] = counts.get(status, 0) + n
    counts.pop("pending_llm", None)
    for key, n in crm.retry_failed(conn).items():            # earlier failures, before this run's new alerts
        counts[key] = counts.get(key, 0) + n
    if counts.get("alert_ready"):
        for crm_error in crm.prepare():
            print(f"  CRM unavailable: {crm_error}")
    consumed, alert_counts = alerting.send_pending(conn)
    if consumed:
        counts["alert_ready"] -= consumed
        if not counts["alert_ready"]:
            del counts["alert_ready"]
    for status, n in alert_counts.items():
        counts[status] = counts.get(status, 0) + n

    changed = sum(v for k, v in counts.items()
                  if k not in ("new", "unchanged", "error") and not k.startswith(("crm_", "airtable_")))
    conn.execute(
        "INSERT INTO runs (started_at, finished_at, pages_checked, new_pages, changed, errors) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (started, now(), len(pages), counts.get("new", 0), changed, counts.get("error", 0)))
    conn.commit()
    print(f"Run complete: {len(pages)} pages | " + " | ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    if own_conn:
        conn.close()
    return counts


if __name__ == "__main__":
    run_observer()
