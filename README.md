# Daily Website Observer: ABM Trigger Intelligence

An internal GTM tool, built as a portfolio example from the point of view of a GTM engineer at **Clay**
(Clay is only the example seller; edit `observer/seller.py` and `contacts.csv` to retarget it).

A BDR gives it a list of target accounts. It watches five pages per account, compares each to a stored snapshot,
filters out noise (copyright years, cookie banners, navigation, typo fixes, minor rewording), and for meaningful
changes it classifies the buying signal, explains why it matters, and alerts the BDR in Slack. It also saves the
trigger and a draft email for the account's decision maker in Attio, and one flat row per alert in Airtable, where a
sequencer such as Instantly could pick up approved drafts. Nothing is ever sent to a prospect.

## How it works
`fetch -> clean -> diff -> free noise rules -> analyzer -> evidence check -> dedupe -> Attio + Airtable -> Slack`

Three gates keep cost and noise down: a content hash (free), rule-based noise filters (free), then the analyzer
only on changes that survive. The analyzer is Claude when `ANTHROPIC_API_KEY` is set; otherwise a clearly labelled
rule-based stand-in (`mock-heuristic`), which is **not an AI**.

## Try it
```
pip install -r requirements.txt
streamlit run app.py
```
With no `.env`, the app starts in **safe demo mode**: it serves 20 fictional company sites itself, Slack, Attio and
Airtable are switched off, alerts show in the run log, and drafts use placeholder contacts. Pick a scenario in the
sidebar, click **Apply scenario**, then **Run observer now**. See `DEMO.md` for the 14 scenarios and a live script.

## Real integrations (optional)
Copy `.env.example` to `.env` and fill in any of `ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL`, `ATTIO_API_KEY`,
`AIRTABLE_TOKEN` / `AIRTABLE_BASE_ID` / `AIRTABLE_TABLE`. Never commit `.env`.

## Tests
```
python evaluate.py                       # scores detection on 24 labelled cases
python demo_scripts/test_scenarios.py    # applies all 14 demo scenarios and checks every outcome
python demo_scripts/rehearse.py          # failure paths: CRM down, table down, approval survives a retry
```

## Limits
Prospects, contacts and domains are fictional. The stand-in analyzer is rule-based, so its scores measure the rules,
not an AI; the Claude paths have not been tested against the live API. Runs happen on demand, not on a schedule.
