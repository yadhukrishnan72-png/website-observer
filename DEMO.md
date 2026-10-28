# Live demo guide

The pitch: *"I'm a GTM engineer at Clay. This internal tool watches our prospects' websites, ignores the noise, and
tells a BDR in Slack the moment a prospect shows a buying signal, with the contact, the reason and a draft email
already waiting in Attio and Airtable."* (Clay is the example seller; edit `observer/seller.py` to retarget it.)

## Set up (2 minutes)
1. `python demo_scripts/reset_demo.py` (clean sites, empty Attio and Airtable, fresh baseline)
2. Terminal 1: `python -m http.server 8000 --directory demo_sites`
3. Terminal 2: `streamlit run app.py`
4. Check the header: Alerts **Slack webhook**, CRM **Attio**, Working table **Airtable**.
   Open `#gtm-triggers`, the Attio workspace and the Airtable table "Observer Triggers" in other tabs.

## The 14 scenarios, one company each
| Company | Scenario | Expected |
|---|---|---|
| Acme AI | New product launch (AI agents) | Alert: New Product Category |
| Acme AI | Hiring push (revenue operations, GTM engineers) | Alert: Hiring / Growth Signal |
| Northwind Analytics | Funding announcement ($30M Series B) | Alert: Funding Announcement |
| Cloudloom | Executive change (new Chief Revenue Officer) | Alert: Leadership Change |
| Datastream Labs | Geographic expansion (Dublin office) | Alert: Market Expansion |
| Ledgerly | Pricing change (price up, new tier) | Alert: Pricing Change |
| Skyline DevOps | New ICP (regulated financial services) | Alert: Market Expansion |
| Helix Support | Strategic partnership | Alert: Major Partnership |
| Quanta Security | Enterprise GTM push | Alert: Strategic Initiative |
| Orbit CRM | Combined growth signals (funding + hiring + new CRO) | 3 alerts, "Also on this account" |
| Mintwise | Footer, cookie banner, nav tweaks | Ignored by rule |
| Stackbank | Date stamp and typo fix | Ignored by rule |
| PayHarbor | Marketing tagline reword | Ignored by analyzer |
| Acme AI | Routine site noise (original) | Ignored |

## Short demo (about 5 minutes)
1. Click **Run observer now**: baseline taken, 100 pages, no alerts.
2. Sidebar: pick *Mintwise: Footer, cookie banner and nav tweaks* then **Apply scenario**, then **Run observer now**.
   The change feed shows it detected and **Ignored by rule**. Nothing in Slack. This is the noise filter.
3. Pick *PayHarbor: Marketing tagline reword*, apply, run: **Ignored by analyzer** (the rules can't tell, the analyzer judges).
4. Pick *Northwind Analytics: Funding announcement*, apply, run. Show, in order:
   Slack alert, then the Attio trigger and draft, then the Airtable row (Status = Draft, email subject and body, what changed).
5. Open the **Scenarios** tab in the top bar to show each scenario, its company and the result.
6. Finish with the combined case: pick *Orbit CRM: Combined growth signals*, apply, run. Three alerts for one
   account; the last ones say **Also on this account**; the Change feed shows a **Combined growth signals** note.
7. In Airtable, set a row's Status to **Approved**. Say: "this is where a sequencer such as Instantly would pick it up;
   that connection is out of scope, nothing is ever sent."

## Full demo
Left rail: **Apply all demo scenarios**, then **Run observer now** (black button, top right). Expect 12 alerts across 9 companies, 3 ignored changes,
12 Attio triggers and drafts, 12 Airtable rows.

## Reset between runs
Left rail: open **Reset demo**, tick the box, then **Reset demo to baseline** (or `python demo_scripts/reset_demo.py`). A repeated alert is
blocked as a duplicate for 30 days, so reset before re-running a scenario.

## Safety net
`python demo_scripts/test_scenarios.py` checks all of the above in a few minutes without posting to Slack.
`python demo_scripts/rehearse.py` checks the failure paths (Attio down, Airtable down, approval survives a retry).
