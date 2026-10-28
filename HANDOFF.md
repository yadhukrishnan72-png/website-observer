# Handoff

Last updated 2026-10-27. Read `CLAUDE.md` first, then this file. Design is in `plan.md`; reasons are in `DECISIONS.md`.

## What this is now
An internal tool for a GTM engineer at **Clay** (portfolio example, not real life). Clay's BDRs sell Clay to prospect companies. The tool watches each prospect's website, alerts in Slack only on meaningful changes, saves the trigger in Attio, and drafts a message to the prospect's decision maker based on what Clay sells. The 20 fictional company names stay; the decision makers are Clay's ICP personas (Head of Revenue Operations, Head of Sales Operations, Director of GTM Operations, GTM Systems Lead, GTM Engineer, Director of Growth, Chief Revenue Officer).

## Where we are
| Phase | Status |
|---|---|
| 1-6 Sites, fetch/clean, diff + noise rules, analyzer, Slack, Streamlit dashboard | Done |
| 8 Attio client + lists | Done: `observer/attio.py`; lists `gtm_triggers` (on Companies) and `outreach_messages` (on People); 20 companies + 20 placeholder contacts seeded |
| 9 Contacts + drafting | Done: `observer/outreach.py` |
| 10 Wire it together | Done 2026-10-27: `observer/crm.py`, `observer/seller.py`, Attio section in the Slack alert, `crm_sync` table, retry of failed Attio saves, careers page + Scenario C, dashboard (Outreach drafts view, Attio details, Drafts KPI, reset clears Attio demo entries) |
| Airtable push | Done 2026-10-27: `observer/airtable.py` creates the table `Observer Triggers` (21 fields) in the user's "Website Observer" base and upserts one row per alert keyed on Change ID; Slack alert, dashboard, reset and rehearsals cover it. Live-verified: `python demo_scripts/rehearse.py --times 3` passed all 18 checks (scenarios A-F). Two earlier runs each had one intermittent failure (Attio list-query lag; an Airtable row with empty Status, root cause not reproduced); both were hardened (settle-waits, 404-tolerant reset, Status set whenever empty, one retry on Airtable 5xx). If it recurs, the failure message now includes the recorded Airtable error. |
| Scenario expansion | Done 2026-10-27: 14 scenarios, each on a different company (`demo_scripts/scenarios.py` registry; originals Acme noise/product/hiring kept): funding, executive change, geographic expansion, pricing change, new ICP, strategic partnership, enterprise GTM push, combined growth signals, plus 3 ignored changes (Mintwise, Stackbank, PayHarbor). Dashboard: scenario picker, "Apply all", new Demo scenarios view, Combined growth signals panel. Slack alert gains an "Also on this account" line. Tests: `demo_scripts/test_scenarios.py` (bundle: 12 alerts across 9 companies, 3 ignored, Attio/Airtable match, duplicate blocked; also `--isolated`), `evaluate.py` now 24 cases. Live script: `DEMO.md`. |
| 7 Test set, evaluation, reset, rehearsals | Done 2026-10-27: `evaluate.py` + `evaluation/fixtures.py` (10 noise / 8 signal cases, 5 metrics, all pass on the mock), `demo_scripts/reset_demo.py`, `demo_scripts/rehearse.py` (scenarios A-D incl. Attio down/retry; 3 consecutive rehearsals passed against the real Attio workspace). |

## Flow
fetch -> clean -> diff -> noise rules -> analyzer (Claude or mock) -> dedupe -> **crm.sync_change** (company upsert, trigger entry, find decision maker, draft) -> Slack alert with Attio links and the draft. If Attio fails the alert still goes out, marked `crm_failed` and retried next run (`crm.retry_failed`). If a company has no contact, the trigger is saved and the alert says "no decision maker on file".

## State of the repo (at last update)
- Sites include a careers page: 20 companies x 5 pages = 100 monitored pages.
- Clean baseline after the last rehearsal: 100 pages, 0 changes, no demo entries in Attio, sites unmodified. Reset any time with `python demo_scripts/reset_demo.py` or the dashboard button (both also clear the Attio demo entries, never companies or people).
- `.env` has `SLACK_WEBHOOK_URL` and `ATTIO_API_KEY` set. `ANTHROPIC_API_KEY` is empty, so analysis and drafts use the labelled mock (`mock-heuristic`).
- the user's Attio workspace. 10 sample companies already existed there; leave them alone.

## How to run the demo
1. `python -m http.server 8000 --directory demo_sites`
2. `streamlit run app.py` (header should read "Alerts: Slack webhook", "CRM: Attio")
3. Scenario A (noise): 0 alerts. B (Acme Agents product): 1 alert, New Product Category. C (revenue operations and GTM engineering hiring push on the careers page): 1 alert, Hiring / Growth Signal.
4. Show: the short Slack alert (links to Attio and the Airtable row; the email draft is not repeated in Slack), then Attio (company, trigger list entry, Outreach Messages draft), then the dashboard Outreach drafts view.
5. Reset (see above). Dedupe blocks a repeat alert for 30 days otherwise.

## Hosting (Streamlit Cloud, safe demo mode)
- Vercel cannot run Streamlit (needs a long-running server and writable disk), so the live dashboard targets Streamlit Community Cloud. A Vercel static page would only be a showcase.
- Safe demo mode = no `.env` / secrets on the host. The app serves the 20 dummy sites itself (`start_site_server` in `app.py`), takes a baseline on first start, uses the rule-based analyzer, prints alerts in the run log, and takes the decision maker from `contacts.csv` with the draft kept in the local database (`crm._sync_local`, status `local`). Verified from a fresh clone: 12 alerts, 12 drafts, reset works.
- Never put Slack, Attio, Airtable or Anthropic secrets in the hosted app: any visitor could trigger posts and resets. The hosted demo is shared by all visitors (one site folder, one database); Reset demo to baseline fixes it.
- The repo excludes `.env`, `observer.db`, `demo_sites/` (regenerated) and the unrelated `gtm-systems-thinking-agent/` and `__MACOSX/` folders.

## Email generation
- `observer/playbooks.py` (per-trigger playbooks and fact extraction), `observer/outreach.py` (drafting and validation). Review the output with `python demo_scripts/sample_emails.py` (add `--scenarios acme-hiring` for a single-signal email); test with `python -m evaluation.test_playbooks` (46 checks, including every wording combination staying within 70-110 words). See DECISIONS D30-D34.
- The Claude drafting path (rewritten prompt plus playbook guidance) has never run against the live API; the stand-in writes the emails today and is labelled `mock-heuristic`.
- Not yet done: nothing marks an older draft as superseded when a later combined draft is created for the same account.

## Look and feel
- The dashboard follows a screenshot of clay.com the user supplied (`Design.png`, kept out of the repo): floating nav bar with a black "Run observer now" button, left rail with letter-spaced labels, hairline stat cells and a two-column card grid with outlined tags. Locked light theme in `.streamlit/config.toml` (Figtree font; Clay's Roobert is licensed) plus `assets/clay.css`, which targets only keyed containers and its own classes. `streamlit==1.66.1` is pinned so the CSS cannot break on an upgrade. See DECISIONS D27-D29.
- Tab names in the top bar are shortened (Scenarios, Drafts, Snapshots); the underlying view names are unchanged.

## Next steps
1. **User:** get an Anthropic API key into `.env` (`ANTHROPIC_API_KEY=...`), then run `python evaluate.py` and `python demo_scripts/rehearse.py` again. Claude analysis and Claude drafting have never been tested against the real API; the current 100% scores measure the keyword stand-in against cases written alongside it.
2. Walk through the dashboard in a real browser (only headless-tested so far).
3. Optional: README and demo script wording for the Clay framing ("example seller modelled on a GTM data platform; edit `seller.py` and `contacts.csv` to retarget").

## Known gaps and risks
- Claude paths untested (no key). The mock is keyword/template based and is not AI.
- Placeholder contacts and the `<slug>.example.com` company domains are demo data that exist only in Attio.
- Clay pitch lines in `seller.py` paraphrase clay.com's own wording; no results or numbers are claimed. Re-check them against the site before presenting.
- Draft status moves (Approved, Sent) are manual in Attio; nothing is sent by this tool.
- Dashboard tested headlessly (AppTest) only.

## Attio facts verified against the live API
- Companies match on `domains`, people on `email_addresses`; records return `web_url`. Attio rejects the bare `.example` TLD; matching uses the full subdomain, so `<slug>.example.com` keeps companies separate. Upserts are idempotent.
- Lists support text, select and timestamp attributes; `created_at` already exists on every list. Entries take plain strings for text and select values.
- People filter by company works in `POST /objects/people/records/query` with `{"company": {"target_object": "companies", "target_record_id": ...}}`.

## Airtable notes
- `.env`: `AIRTABLE_BASE_ID` is the bare `app...` id and `AIRTABLE_TABLE=Observer Triggers`. The base also holds Airtable's website-monitor template tables (Trigger Outreach, Checks, Incidents); they are untouched and safe to delete.
- Attio and Airtable list reads can lag behind writes and deletes: wait/poll before judging counts, and treat a 404 on delete as already deleted.
- `.env` `AIRTABLE_BASE_ID` may hold a pasted Airtable URL; `airtable.ids()` extracts the `app...` base id and `tbl...` table id.
- Row key is `Change ID` (upsert). `Status` is set to Draft only when a row is created, so a retry never overwrites an Approved status. Fields are created by `airtable.ensure_schema()`; the primary field is renamed `Trigger`.
- The Airtable token was printed once into the session transcript by mistake; regenerate it at airtable.com/create/tokens and update `.env`.

## Gotchas learned
- `python3` is a Windows Store alias that fails; use `python`.
- Importing `observer.slack` alone does not load `.env`; import `observer.config` first (importing `attio` or `pipeline` does).
- To test without posting to Slack, set `SLACK_WEBHOOK_URL=` (empty) in the process environment; the loader will not override it.
- Windows console is cp1252: set `PYTHONIOENCODING=utf-8` for scripts that print emoji.
- Deleting `observer.db` fails if a connection is still open.
- Background `pip install` can re-apply later and duplicate edits; install in the foreground.
- The streamlit skill's `discover.py` fails under the `python3` alias; read its SKILL.md and references directly.
- The auto-mode command checker fails intermittently; retrying the identical command works.
- Re-running `generate_demo_sites.py` is the site reset; it is deterministic.
