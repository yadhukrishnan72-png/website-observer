# Handoff

**Last updated:** 2026-10-28. Read `CLAUDE.md` (rules), then this file. Reasons are in `DECISIONS.md`, the original design in `plan.md`, the live-demo script in `DEMO.md`, the day-by-day log in `sessions/`.

## Where we are
A finished, deployed portfolio demo. An internal tool framed as built by a GTM engineer at **Clay** (example seller). It watches 20 fictional company sites (5 pages each), filters noise, classifies buying signals, alerts in Slack, saves a trigger and a draft email in Attio, and saves one flat row per alert in an Airtable table (`Observer Triggers`). Nothing is ever sent to a prospect; Airtable is the end of the pipeline and Instantly is not connected. Runs on demand, no scheduler.

- **Code:** private GitHub repo `yadhukrishnan72-png/website-observer`, branch `main`, last pushed commit `51e4042` (this handoff is committed after it).
- **Hosted app:** https://website-observer-6nxxvf5rptxaqueul9kyxa.streamlit.app/ on Streamlit Community Cloud, running with the **real** Slack/Attio/Airtable keys by the user's choice (so anyone with the link can trigger posts and Reset).
- **Analysis and drafts** use the rule-based stand-in (`mock-heuristic`), not an AI. No `ANTHROPIC_API_KEY` yet; the Claude paths are written but have never run against the live API.
- **Local state:** demo sites and `observer.db` at a clean baseline (100 pages, 0 changes); Attio demo lists and Airtable table empty as of the last test run.

## What we did (whole session, 2026-10-26 to 28)
Built Phases 1-6 (sites, fetch/clean/diff, noise rules, analyzer, Slack, dashboard); added Attio (lists, 20 companies + placeholder contacts) and Airtable; Clay framing and personas; 14 scenarios, one company each; evaluation, reset, rehearsals; safe demo mode and Streamlit Cloud deployment; restyled the dashboard to match the user's `Design.png` of clay.com (locked light theme, `assets/clay.css`); rewrote email generation around per-trigger playbooks with a strict validator; banned quoted page text in emails; made the hosted app reload changed modules after a redeploy. Today's details: `sessions/2026-10-28.md`.

## What's next (in order)
1. **User, on the hosted app, after the last push:** Manage app > Reboot app, reload, then left rail > Reset demo > tick the box > Reset demo to baseline (clears the old Northwind test draft from the hosted DB, Attio and Airtable). Then Apply *Northwind Analytics: Funding announcement*, Run observer now, and check the Airtable email body has no "The page says" line.
2. If the hosted page still shows a red error, get the error text (now readable via `showErrorDetails = "full"`) and fix the real cause. The earlier `sqlite3.OperationalError` cause is unconfirmed.
3. Optional: get an Anthropic API key into the local `.env` (never into the hosted app unless the user decides), then run `python evaluate.py`, `python -m evaluation.test_playbooks` and `python demo_scripts/sample_emails.py` on the Claude path; the current 100% scores measure the rules.
4. Optional polish: mark older drafts as superseded when a combined draft is created for the same account; re-check the Clay wording in `observer/seller.py` and `observer/playbooks.py` against clay.com before presenting; Roobert only if the user has a license.

## Blockers and open questions for the user
- Whether to keep real keys on the public hosted app (accepted so far) or clear the Secrets / restrict viewers.
- Whether to add a scheduler (user chose on demand for now).
- Anthropic key: wanted or not.

## Leftover cleanup
- `Design.png` (user's Clay screenshot) sits in the project folder, gitignored on purpose; `gtm-systems-thinking-agent/` and `__MACOSX/` are unrelated cohort material, also gitignored. Leave them.
- Scratch files (screenshot helpers, splice scripts) live in the session scratchpad outside the repo.
- Nothing is left running; local port 8000 and the preview server were stopped.

## Gotchas
- Use `python`, not `python3`. Blank `SLACK_WEBHOOK_URL=` in the environment to test without posting to Slack.
- Streamlit is pinned to 1.66.1 because `assets/clay.css` depends on its structure. Hosted redeploys can leave old code in memory; the app now reloads changed modules, but Reboot app is still the reliable fix.
- Attio/Airtable reads lag writes by a second or two; Attio creates are not auto-retried (duplicate risk).
- Shell heredocs lose backslash escapes in long inline Python: write the script to a file with the editor tool.
- Claude Code may kill long background runs for low memory; do not restart them unasked.
- `git push` works when the user asks; `gh repo create` was blocked by the permission check.

## How to run and test
`python demo_scripts/reset_demo.py` then `streamlit run app.py` (see `DEMO.md`). Tests: `python evaluate.py`, `python -m evaluation.test_playbooks`, `python demo_scripts/test_scenarios.py`, `python demo_scripts/rehearse.py`, `python demo_scripts/sample_emails.py`.
