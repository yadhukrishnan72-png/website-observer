"""Daily Website Observer dashboard.  Run:  streamlit run app.py"""
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

from observer import airtable, attio, config, db, pipeline, slack

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "demo_scripts"
sys.path.insert(0, str(SCRIPTS))
import scenarios  # noqa: E402  (the demo scenario registry)

STATUS_LABEL = {
    "alerted": ("Alerted", "green"),
    "alert_failed": ("Alert failed", "red"),
    "ignored_rule": ("Ignored by rule", "gray"),
    "ignored_llm": ("Ignored by analyzer", "gray"),
    "review": ("Needs review", "orange"),
    "duplicate": ("Duplicate", "blue"),
    "rejected": ("Rejected", "red"),
    "alert_ready": ("Ready to send", "green"),
    "pending_llm": ("Pending analysis", "yellow"),
}
VIEWS = ["Change feed", "Demo scenarios", "Outreach drafts", "Accounts", "Pages and snapshots", "Run log"]
PRIORITIES = ["High", "Medium", "Low"]

st.set_page_config(page_title="Website Observer", page_icon=":material/radar:", layout="wide")


def query(sql, params=()):
    conn = db.connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def run_script(name):
    result = subprocess.run([sys.executable, str(SCRIPTS / name)], capture_output=True, text=True, cwd=ROOT)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def run_observer_captured():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        counts = pipeline.run_observer()
    return counts, buf.getvalue()


@st.cache_resource
def start_site_server():
    """Make sure the dummy company sites exist and are served on localhost:8000, so the app also works on a host
    where nobody starts the server by hand (e.g. Streamlit Cloud). Does nothing if a server is already running."""
    import time

    import _demo
    if not (ROOT / "demo_sites" / "acme-ai" / "products.html").exists():
        subprocess.run([sys.executable, str(SCRIPTS / "generate_demo_sites.py")], check=True, cwd=ROOT)
    if _demo.server_up():
        return None
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(_demo.PORT), "--directory",
                             str(ROOT / "demo_sites")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if _demo.server_up():
            break
        time.sleep(0.25)
    return proc


start_site_server()
if query("SELECT COUNT(*) AS n FROM snapshots")[0]["n"] == 0:             # first start: take the baseline
    with st.spinner("First start: taking a baseline snapshot of the 20 demo company sites..."):
        run_observer_captured()

# ----------------------------------------------------------------------------- header

st.title(":material/radar: Daily Website Observer")
st.caption("Internal GTM tool (example seller: Clay). Monitors target-account websites, alerts the BDR only on "
           "commercially meaningful changes, and saves the trigger and a draft message in Attio.")

provider = config.llm_provider()
analysis_text = (f"Claude ({config.model_name()})" if provider == "claude"
                 else "mock heuristic stand-in (no API key set; not AI)")
alert_text = "Slack webhook" if slack.webhook_url() else "console fallback (no Slack webhook set)"
crm_text = "Attio" if attio.enabled() else "off (no ATTIO_API_KEY set)"
table_text = "Airtable" if airtable.enabled() else "off (no Airtable settings in .env)"
st.caption(f"Analysis and drafts: **{analysis_text}** · Alerts: **{alert_text}** · CRM: **{crm_text}** · "
           f"Working table: **{table_text}**")

if not (slack.webhook_url() or attio.enabled() or airtable.enabled()):
    st.info("**Safe demo mode.** Slack, Attio and Airtable are switched off, so nothing leaves this app. Alerts "
            "appear in the run log below, the decision maker comes from placeholder contacts, and drafts are kept "
            "locally. The analyzer is a rule-based stand-in, not an AI. The demo is shared: if the sites look "
            "already edited, press Reset demo to baseline in the sidebar.", icon=":material/shield:")

with st.sidebar:
    st.header("Demo helpers")
    st.caption("Edit the Acme AI dummy site by hand, or use these shortcuts. Serve the sites with "
               "`python -m http.server 8000 --directory demo_sites`.")
    labels = {s["id"]: scenarios.label(s) for s in scenarios.SCENARIOS}
    pick = st.selectbox("Scenario", list(labels), format_func=labels.get)
    st.caption(scenarios.BY_ID[pick]["story"])
    if st.button("Apply scenario", icon=":material/play_circle:", width="stretch"):
        ok, msg = scenarios.apply(pick)
        (st.success if ok else st.error)(msg)
    if st.button("Apply all demo scenarios", icon=":material/library_add:", width="stretch",
                 help="Every scenario except the original Acme noise one, which overlaps with the Acme product change."):
        failed = [f"{sid}: {msg}" for sid, ok, msg in scenarios.apply_bundle() if not ok]
        if failed:
            st.error("\n\n".join(failed))
        else:
            st.success("All demo scenarios applied. Now click Run observer now.")
    st.divider()
    confirm = st.checkbox("I understand reset wipes local history and the demo triggers, drafts and table rows "
                          "in Attio and Airtable")
    if st.button("Reset demo to baseline", icon=":material/restart_alt:", width="stretch", disabled=not confirm):
        ok, out = run_script("generate_demo_sites.py")
        db.DB_PATH.unlink(missing_ok=True)
        cleared = attio.clear_entries() if attio.enabled() else 0
        rows_cleared = airtable.clear_rows() if airtable.enabled() else 0
        counts, _ = run_observer_captured()
        extra = (f"{cleared} Attio entries" if attio.enabled() else "") + (
            " and " if attio.enabled() and airtable.enabled() else "") + (
            f"{rows_cleared} Airtable rows" if airtable.enabled() else "")
        st.success("Sites regenerated, " + (extra + " cleared, " if extra else "")
                   + f"baseline taken ({counts.get('new', 0)} pages).")

top = st.container(horizontal=True, vertical_alignment="center")
run_clicked = top.button("Run observer now", type="primary", icon=":material/play_arrow:")
top.caption("Fetches every monitored page, compares with the last snapshot, and alerts on meaningful changes.")

if run_clicked:
    with st.status("Running observer...", expanded=True) as status:
        counts, log = run_observer_captured()
        status.update(label="Run complete", state="complete")
        summary = " · ".join(f"{STATUS_LABEL.get(k, (k,))[0].lower()} {v}" if k in STATUS_LABEL else f"{k} {v}"
                             for k, v in sorted(counts.items()))
        st.write(summary)
        if log.strip():
            st.code(log.strip(), language="text")

# ----------------------------------------------------------------------------- KPIs

kpi = query("""SELECT
    (SELECT COUNT(*) FROM accounts WHERE active = 1) AS accounts,
    (SELECT COUNT(*) FROM pages) AS pages,
    (SELECT COUNT(*) FROM changes) AS changes,
    (SELECT COUNT(*) FROM changes WHERE status IN ('ignored_rule', 'ignored_llm')) AS ignored,
    (SELECT COUNT(*) FROM changes WHERE status = 'alerted') AS alerted,
    (SELECT COUNT(*) FROM crm_sync WHERE body IS NOT NULL) AS drafts,
    (SELECT COUNT(*) FROM crm_sync WHERE airtable_status = 'pushed') AS rows""")[0]
with st.container(horizontal=True):
    st.metric("Target accounts", kpi["accounts"], border=True)
    st.metric("Pages monitored", kpi["pages"], border=True)
    st.metric("Changes detected", kpi["changes"], border=True)
    st.metric("Ignored as noise", kpi["ignored"], border=True)
    st.metric("Alerts sent", kpi["alerted"], border=True)
    st.metric("Email drafts", kpi["drafts"], border=True)
    if airtable.enabled():
        st.metric("Rows in Airtable", kpi["rows"], border=True)

view = st.segmented_control("View", VIEWS, default=VIEWS[0], label_visibility="collapsed") or VIEWS[0]

# ----------------------------------------------------------------------------- change feed

if view == "Change feed":
    rows = query("""SELECT ch.id, ch.detected_at, ch.status, ch.reason, ch.added_blocks, ch.removed_blocks, ch.ignored,
                           p.url, p.page_type, a.company_name, a.owner, a.priority,
                           an.signal_type, an.confidence, an.change_summary, an.why_it_matters, an.outreach_angle,
                           an.evidence, an.model, cs.status AS crm_status, cs.company_url, cs.person_url,
                           cs.contact_name, cs.contact_title, cs.subject, cs.body, cs.model AS draft_model,
                           cs.error AS crm_error, cs.contact_email, cs.airtable_status, cs.airtable_url,
                           cs.airtable_error
                    FROM changes ch JOIN pages p ON p.id = ch.page_id JOIN accounts a ON a.id = p.account_id
                    LEFT JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id)
                    LEFT JOIN crm_sync cs ON cs.change_id = ch.id
                    ORDER BY ch.id DESC LIMIT 200""")
    if not rows:
        st.info("No changes yet. Take a baseline with **Run observer now**, edit a dummy site, then run again.")
    else:
        combined = query("""SELECT a.company_name AS company, GROUP_CONCAT(DISTINCT an.signal_type) AS signals
                            FROM changes ch JOIN pages p ON p.id = ch.page_id JOIN accounts a ON a.id = p.account_id
                            JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id)
                            WHERE ch.status = 'alerted' GROUP BY a.id HAVING COUNT(DISTINCT an.signal_type) >= 2""")
        if combined:
            with st.container(border=True):
                st.subheader("Combined growth signals")
                st.caption("Accounts with more than one kind of signal alerted: the strongest outreach moments.")
                for c in combined:
                    st.markdown(f"**{c['company']}**: " + " + ".join(c["signals"].split(",")))
        present = [s for s in STATUS_LABEL if any(r["status"] == s for r in rows)]
        chosen = st.pills("Show", present, selection_mode="multi", default=present,
                          format_func=lambda s: f"{STATUS_LABEL[s][0]} ({sum(r['status'] == s for r in rows)})")
        for r in rows:
            if r["status"] not in chosen:
                continue
            label, color = STATUS_LABEL.get(r["status"], (r["status"], "gray"))
            with st.container(border=True):
                head = st.container(horizontal=True, vertical_alignment="center")
                head.badge(label, color=color)
                if r["crm_status"] == "crm_failed":
                    head.badge("Attio retry pending", color="orange")
                if r["airtable_status"] in ("failed", "pending"):
                    head.badge("Airtable retry pending", color="orange")
                head.markdown(f"**{r['company_name']}** · {r['page_type']} page")
                head.caption(f"{r['detected_at'].replace('T', ' ')[:19]} UTC · {r['reason'] or ''}")
                if r["signal_type"] and r["status"] in ("alerted", "alert_failed", "review", "duplicate", "alert_ready"):
                    st.markdown(f"**{r['signal_type']}** ({r['confidence']}): {r['change_summary']}")
                with st.expander("Details"):
                    added, removed = json.loads(r["added_blocks"]), json.loads(r["removed_blocks"])
                    ignored = json.loads(r["ignored"])
                    if r["signal_type"]:
                        st.markdown(f"**Why it matters:** {r['why_it_matters']}")
                        st.markdown(f"**Suggested outreach angle:** {r['outreach_angle']}")
                        st.markdown(f"**Evidence:** “{r['evidence']}”")
                        st.caption(f"Analyzed by {r['model']} · source {r['url']}")
                    if r["airtable_status"]:
                        st.markdown("**Airtable**")
                        st.markdown(f"Status: `{r['airtable_status']}`")
                        if r["airtable_error"]:
                            st.caption(f"Detail: {r['airtable_error']}")
                        if r["airtable_url"]:
                            st.link_button("Row in Airtable", r["airtable_url"], icon=":material/open_in_new:")
                    if r["crm_status"]:
                        st.markdown("**Contact and draft**")
                        who = (f"{r['contact_name']}, {r['contact_title']}" if r["contact_name"]
                               else "no decision maker on file")
                        st.markdown(f"Status: `{r['crm_status']}` · Decision maker: {who}")
                        if r["crm_error"]:
                            st.caption(f"Detail: {r['crm_error']}")
                        links = st.container(horizontal=True)
                        if r["company_url"]:
                            links.link_button("Company in Attio", r["company_url"], icon=":material/open_in_new:")
                        if r["person_url"]:
                            links.link_button("Contact and draft in Attio", r["person_url"],
                                              icon=":material/open_in_new:")
                        if r["body"]:
                            st.caption(f"Draft by {r['draft_model']} (status Draft in Attio)")
                            st.code(f"Subject: {r['subject']}\n\n{r['body']}", language="text")
                    if added or removed:
                        st.markdown("**Content change that reached the analyzer**")
                        st.code("\n".join([f"- {b}" for b in removed] + [f"+ {b}" for b in added]), language="diff")
                    if ignored:
                        st.markdown("**Filtered out as noise**")
                        st.dataframe([{"Rule": i["rule"], "Side": i.get("side", ""), "Text": i["text"][:160]}
                                      for i in ignored], hide_index=True, alt="Noise filtered out for this change")
                    if r["status"] in ("alerted", "alert_failed"):
                        st.markdown("**Slack message**")
                        st.code(slack.format_alert({
                            "company": r["company_name"], "change_summary": r["change_summary"],
                            "signal_type": r["signal_type"], "why_it_matters": r["why_it_matters"],
                            "outreach_angle": r["outreach_angle"], "url": r["url"], "confidence": r["confidence"],
                            "owner": r["owner"], "priority": r["priority"], "crm_status": r["crm_status"],
                            "crm_error": r["crm_error"], "company_url": r["company_url"],
                            "person_url": r["person_url"], "contact_name": r["contact_name"],
                            "contact_title": r["contact_title"], "draft_subject": r["subject"],
                            "draft_body": r["body"], "airtable_status": r["airtable_status"],
                            "airtable_url": r["airtable_url"], "airtable_error": r["airtable_error"]}),
                                language="markdown")

# ----------------------------------------------------------------------------- outreach drafts

elif view == "Demo scenarios":
    latest = {}
    for r in query("""SELECT a.company_name AS company, p.page_type AS page, ch.status, an.signal_type
                      FROM changes ch JOIN pages p ON p.id = ch.page_id JOIN accounts a ON a.id = p.account_id
                      LEFT JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id)
                      ORDER BY ch.id"""):
        latest[(r["company"], r["page"])] = r                     # the most recent change on each page wins

    def last_result(s):
        if not scenarios.is_applied(s):
            return "Not applied"
        found = [latest[(s["company"], p)] for p in s["pages"] if (s["company"], p) in latest]
        if not found:
            return "Not run yet"
        return "; ".join(f"{STATUS_LABEL.get(r['status'], (r['status'],))[0]}"
                         + (f": {r['signal_type']}" if r["status"] in ("alerted", "duplicate") else "") for r in found)

    st.caption("Each scenario edits a different company's website. Pick one in the sidebar (or apply them all), "
               "click Run observer now, then compare the last result with what was expected.")
    st.dataframe([{
        "Scenario": s["title"], "Company": s["company"], "What changes": s["story"],
        "Expected": ("Alert: " + " + ".join(a[0] for a in s["alerts"])) if s["alerts"] else "Ignored, no alert",
        "Applied": "Yes" if scenarios.is_applied(s) else "No", "Last result": last_result(s)}
        for s in scenarios.SCENARIOS], hide_index=True,
        alt="Demo scenarios with the company each applies to, the expected result and the latest outcome")

elif view == "Outreach drafts":
    drafts = query("""SELECT cs.*, ch.detected_at, a.company_name, a.owner, an.signal_type
                      FROM crm_sync cs JOIN changes ch ON ch.id = cs.change_id
                      JOIN pages p ON p.id = ch.page_id JOIN accounts a ON a.id = p.account_id
                      LEFT JOIN analyses an ON an.id = (SELECT MAX(id) FROM analyses WHERE change_id = ch.id)
                      ORDER BY cs.id DESC LIMIT 100""")
    if not drafts:
        st.info("No drafts yet. A draft is created for each alert when Attio is configured.")
    for d in drafts:
        with st.container(border=True):
            head = st.container(horizontal=True, vertical_alignment="center")
            head.badge("Draft" if d["body"] else d["status"], color="blue" if d["body"] else "orange")
            head.markdown(f"**{d['company_name']}** · {d['signal_type']}")
            head.caption(f"{d['contact_name'] or 'no contact'}{', ' + d['contact_title'] if d['contact_title'] else ''}"
                         f" · account owner {d['owner']}")
            if d["body"]:
                st.code(f"Subject: {d['subject']}\n\n{d['body']}", language="text")
                st.caption(f"Drafted by {d['model']}. Edit, approve and mark Sent in Attio.")
            elif d["error"]:
                st.caption(f"Not created: {d['error']}")
            if d["person_url"]:
                st.link_button("Open in Attio", d["person_url"], icon=":material/open_in_new:")

# ----------------------------------------------------------------------------- accounts

elif view == "Accounts":
    accounts = query("""SELECT a.company_name AS Company, a.website_url AS Website, a.industry AS Industry,
                               a.owner AS Owner, a.priority AS Priority,
                               (SELECT COUNT(*) FROM pages p WHERE p.account_id = a.id) AS Pages,
                               (SELECT COUNT(*) FROM changes ch JOIN pages p ON p.id = ch.page_id
                                WHERE p.account_id = a.id AND ch.status = 'alerted') AS Alerts
                        FROM accounts a WHERE a.active = 1 ORDER BY a.id""")
    with st.container(border=True):
        st.subheader("Target accounts")
        st.dataframe(accounts, hide_index=True, alt="Target account list with owner, priority and alert counts")

    with st.container(border=True):
        st.subheader("Add an account")
        with st.form("add_account", clear_on_submit=True):
            c1, c2 = st.columns(2)
            company = c1.text_input("Company name")
            website = c2.text_input("Website URL", placeholder="http://localhost:8000/acme-ai/")
            c3, c4, c5 = st.columns(3)
            industry = c3.text_input("Industry")
            owner = c4.text_input("Account owner")
            priority = c5.selectbox("Priority", PRIORITIES)
            pages_text = st.text_area("Pages to monitor (one per line: type, URL)",
                                      placeholder="products, http://localhost:8000/acme-ai/products.html\n"
                                                  "pricing, http://localhost:8000/acme-ai/pricing.html")
            submitted = st.form_submit_button("Add account", type="primary")
        if submitted:
            pages = [tuple(p.strip() for p in line.split(",", 1)) for line in pages_text.splitlines() if "," in line]
            conn = db.connect()
            error = db.add_account(conn, company, website, industry, owner, priority, pages)
            conn.close()
            if error:
                st.error(error)
            else:
                st.success(f"Added {company.strip()} with {len(pages)} pages. Run the observer to take its baseline snapshot.")

# ----------------------------------------------------------------------------- pages and snapshots

elif view == "Pages and snapshots":
    pages = query("""SELECT p.id, p.url, p.page_type, p.last_checked_at, a.company_name FROM pages p
                     JOIN accounts a ON a.id = p.account_id ORDER BY a.company_name, p.id""")
    if not pages:
        st.info("No pages yet.")
    else:
        pick = st.selectbox("Page", pages, format_func=lambda p: f"{p['company_name']} · {p['page_type']}")
        snaps = query("SELECT id, fetched_at, content_hash, blocks FROM snapshots WHERE page_id = ? ORDER BY id DESC",
                      (pick["id"],))
        st.caption(f"{pick['url']} · last checked {pick['last_checked_at'] or 'never'} · {len(snaps)} snapshot(s)")
        if snaps:
            with st.container(border=True):
                st.subheader("Latest clean snapshot")
                st.caption("Text blocks after scripts, navigation, footer and cookie banners were removed.")
                st.code("\n".join(json.loads(snaps[0]["blocks"])), language="text")
            st.dataframe([{"Snapshot": s["id"], "Fetched (UTC)": s["fetched_at"], "Hash": s["content_hash"][:12]}
                          for s in snaps], hide_index=True, alt="Snapshot history for the selected page")

# ----------------------------------------------------------------------------- run log

else:
    runs = query("""SELECT id AS Run, started_at AS Started, finished_at AS Finished, pages_checked AS Pages,
                           new_pages AS New, changed AS Changed, errors AS Errors
                    FROM runs ORDER BY id DESC LIMIT 50""")
    if not runs:
        st.info("No runs yet.")
    else:
        st.dataframe(runs, hide_index=True, alt="History of observer runs")
