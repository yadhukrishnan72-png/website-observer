# Daily Website Observer: ABM Trigger Intelligence

**Read `HANDOFF.md` first, every session.** Then `DECISIONS.md` (why) and `plan.md` (original design).

Portfolio pilot, framed as an internal tool built by a GTM engineer at Clay (example seller, not real life). A BDR gives it target accounts; it watches 5 pages per account, ignores noise, alerts in Slack only on meaningful changes, saves the trigger in Attio and a flat row in Airtable, and drafts an email to the account's decision maker based on what Clay sells. Demo-able pilot, not production. Priorities: clear GTM value, understandable architecture, reliable live demo.

## Run
- Windows, Python 3.12. Use `python`, not `python3` (a Store alias that fails).
- Reset demo: `python demo_scripts/reset_demo.py` (starts the site server, clears local history and the Attio/Airtable demo data, re-baselines).
- Dashboard: `streamlit run app.py` (ask the user before starting it). One CLI run: `python -m observer.pipeline`.
- Tests: `python evaluate.py`, `python -m evaluation.test_playbooks`, `python demo_scripts/test_scenarios.py` (`--isolated` for one at a time), `python demo_scripts/rehearse.py` (scenarios A-F incl. failure paths). Read the emails: `python demo_scripts/sample_emails.py`.
- The 14 scenarios live in `demo_scripts/scenarios.py`; add new ones there. Live demo script: `DEMO.md`.

## Architecture
`fetcher` -> `cleaner` -> `differ` -> `noise_rules` -> `analyzer` (Claude or mock) -> `alerting` (dedupe, then `crm` -> `attio` / `airtable` + `outreach`, then Slack). `playbooks.py` holds the per-trigger email wording, `seller.py` the Clay pitch, `db.py` SQLite, `app.py` the Streamlit dashboard.

## Conventions
- Match existing style: small modules, short docstrings, comments only for the non-obvious why.
- Secrets live in `.env` (git-ignored). Never print, log, commit or paste them; mask values when inspecting. Grep `.env` with `-c` or names only, never `-o` on a value.
- `.env` loads via `observer/config.py`; import it first in ad-hoc scripts. To test without posting to Slack, set `SLACK_WEBHOOK_URL=` (empty) in the process environment.
- Mock analyzer/drafter is rule-based and labelled `mock-heuristic`; never present it as AI. Its scores measure the rules, not a model.
- LLM and drafter output is never trusted: validate it. Emails state only facts from the detected change and never quote the page.
- An alert is never lost: Slack/CRM/Airtable failures are recorded and retried next run. Drafts are always status Draft; nothing is ever sent to a prospect.
- Seller claims come only from `seller.py`/`playbooks.py`: no results, prices or numbers about Clay.
- Look = `.streamlit/config.toml` (locked light theme) + `assets/clay.css`, which targets only keyed containers and our own classes. Streamlit is pinned to 1.66.1 so the CSS cannot break.
- Attio and Airtable list reads lag writes by a second or two: poll before asserting counts. Creates are not auto-retried after a network error (duplicate risk).
- Windows console is cp1252: set `PYTHONIOENCODING=utf-8` for scripts that print emoji.
- Long inline Python in a shell heredoc loses escapes (`\n`, quotes). Write the script to a file with the editor tool, then run it.

## Do not
- Do not delete `observer.db`, regenerate sites or clear Attio/Airtable demo data outside an explicit reset or a test that restores the baseline. Never delete companies or people.
- Do not start the app or send real Slack/CRM messages without the user knowing.
- Do not push unless the user asks (`git push` works; `gh repo create` was blocked by the permission check).
- Do not restart a background command that Claude Code killed for low memory unless the user asks.
- Do not build ahead of the user's instruction.
