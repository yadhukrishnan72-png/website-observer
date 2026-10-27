# Daily Website Observer: ABM Trigger Intelligence

Pilot GTM automation for a portfolio/Build Week project, framed as an internal tool built by a GTM engineer at Clay (example seller, not real life). A BDR gives it target accounts; it watches 5 pages per account, ignores noise, alerts in Slack only on meaningful changes, saves the trigger in Attio, and drafts a message to the account's decision maker based on what Clay sells. It is a demo-able pilot, not a production system. Priorities: clear GTM value, understandable architecture, reliable live demo.

Read first: `plan.md` (design, section 15 = Attio addendum), `DECISIONS.md` (why), `HANDOFF.md` (current state and next steps).

## Run
- Python 3.12 on Windows. Use `python`, not `python3` (`python3` is a Windows Store alias that fails).
- Serve dummy sites: `python -m http.server 8000 --directory demo_sites`
- Dashboard: `streamlit run app.py` (ask the user before starting it)
- One pipeline run from the CLI: `python -m observer.pipeline`
- Reset demo: `python demo_scripts/reset_demo.py` (starts the site server itself if needed; clears local history and the Attio demo entries, re-baselines).
- Rehearse: `python demo_scripts/rehearse.py --times 3` (scenarios A-D, alerts to console; `--slack` posts to the real channel). Score detection: `python evaluate.py`.
- Demo scenarios: `scenario_a_noise.py` (expect 0 alerts), `scenario_b_signal.py` (new AI product, 1 alert), `scenario_c_hiring.py` (revenue operations and GTM hiring push, 1 alert), all in `demo_scripts/`. Seed Attio with `demo_scripts/seed_attio.py`. The full scenario list (14, one company each) lives in `demo_scripts/scenarios.py`; add new scenarios there, not as new standalone scripts. Live demo script: `DEMO.md`. Test them with `python demo_scripts/test_scenarios.py`.

## Architecture (one line each)
`fetcher` -> `cleaner` (text blocks, strips nav/footer/scripts/cookie) -> `differ` (block diff) -> `noise_rules` (named free rules) -> `analyzer` (Claude or mock, validated) -> `alerting` (dedupe, then `crm` -> `attio` + `outreach`, then deliver) -> `slack`. `seller.py` holds the example seller (Clay) and its pitch. `pipeline.run_observer()` orchestrates; `db.py` is SQLite (`observer.db`); `app.py` is the Streamlit dashboard.
Funnel: hash match (free) -> rule filter (free) -> LLM only on surviving changed blocks -> evidence check, confidence threshold, 30-day dedupe.

## Conventions
- Match existing code style: small modules, short docstrings, comments only for the non-obvious "why".
- Secrets live in `.env` (git-ignored): `ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL`, `ATTIO_API_KEY`. Never print, log, commit or paste them. When inspecting `.env`, mask values.
- `.env` is loaded by `observer/config.py`. Importing only `observer.slack` does NOT load it; import `config` first in ad-hoc scripts.
- LLM provider: `OBSERVER_LLM=auto|claude|mock`. Mock is a keyword heuristic labelled `mock-heuristic`; never present it as AI. Default model `claude-haiku-5-5` via `OBSERVER_MODEL`.
- LLM output is never trusted: validate signal type against the taxonomy and require evidence to appear verbatim in the changed text.
- An alert must never be lost: if Slack or the CRM fails, still print/send what we can and record the failure status (`crm_failed` is retried next run).
- Drafts are always status Draft; nothing is ever sent to a prospect. Seller claims come only from `seller.py` and must not include results or numbers.
- To test without posting to Slack, set `SLACK_WEBHOOK_URL=` (empty) in the process environment. Clean up test entries in Attio (`attio.clear_entries()`); never delete companies or people that the user did not ask to remove.
- Windows console is cp1252: set `PYTHONIOENCODING=utf-8` in test scripts that print emoji.
- Streamlit: follow the developing-with-streamlit skill (no custom CSS, `width="stretch"`, test with `st.testing.v1.AppTest`).

## Do not
- Do not commit or echo API keys or the webhook URL.
- Do not add real third-party scraping of live sites without being asked (demo uses local dummy sites).
- Do not delete `observer.db`, regenerate sites or clear Attio entries outside an explicit reset or a test that restores the baseline.
- Do not start the Streamlit app or send real Slack/CRM messages without the user knowing; a single test message after setup is fine when asked.
- Do not build ahead of the user's "start Phase N" instruction.
