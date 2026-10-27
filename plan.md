# Daily Website Observer: ABM Trigger Intelligence

**Pilot plan (v1).** Stack: Python + SQLite + Streamlit + Claude API + Slack webhook. Dummy sites served on localhost.

---

## 0. Where I'm challenging your brief

These are the places where I'd push back or tighten. Each one changes the design, so please read them before the rest.

| # | Your assumption | My challenge | Decision for the pilot |
|---|---|---|---|
| 1 | "20 synthetic accounts, monitored daily" | Synthetic accounts have no real websites, so there is nothing to fetch. | Generate 20 tiny dummy sites (4 pages each) and serve them from one local web server (`localhost:8000/<company>/...`). Acme AI is the one you edit live. The other 19 stay static and prove the system scales to a list without alerting on everything. |
| 2 | "Monitor real-world websites too" | Real sites are JS-rendered, block bots, A/B test, rotate banners and change constantly. That is a reliability risk on stage. | **No live third-party sites in the demo path.** Optionally add one "real site" in an appendix once the pilot works. |
| 3 | "Ask the LLM if the change is meaningful" | Sending every changed page to an LLM is slow, costly and noisy. Most changes are noise a rule can catch. | **Three-gate funnel**: hash match (free) → rule-based noise filter (free) → LLM judgement (only on what survives). The LLM sees only the *changed text blocks*, not the whole page. |
| 4 | "Compare against the previous snapshot" | Raw HTML diffs are useless (scripts, timestamps, CSRF tokens). | Diff **cleaned, block-level text** (headings, paragraphs, list items), not HTML. |
| 5 | "The LLM classifies and explains" | LLMs hallucinate changes and sound confident. A fabricated alert in front of a BDR destroys trust. | The LLM must return an **`evidence` quote** that exists verbatim in the diff. If it doesn't, the alert is dropped. |
| 6 | "If no meaningful change, do nothing" | Doing *nothing* is correct for Slack but terrible for a demo and for trust. You can't prove the filter works if ignored changes are invisible. | Slack stays silent, but every ignored change is **logged with a reason** and shown on the dashboard ("Ignored: copyright year"). This is your proof of noise rejection. |
| 7 | "Daily scheduling" | Scheduling is real-world plumbing and invisible in a demo. It is also the easiest part to get wrong on stage. | Build `run_observer` as a command and a **"Run observer now" button**. Document scheduling (Windows Task Scheduler) but don't depend on it. |
| 8 | "Slack alert for any meaningful change" | A medium-confidence alert is a guess. A BDR who gets 5 weak pings a day mutes the channel. | Slack gets **High and Medium** confidence only. Low goes to the dashboard "Review" tab. Dedupe so the same change never alerts twice. |
| 9 | "Outreach angle" | Generic angles ("congratulate them") are worthless. | The prompt is signal-type aware (a pricing change leads to a different angle than a leadership change) and must reference the *specific* detail found. |

---

## 1. Persona and problem

**Primary user: the BDR / SDR working an ABM list.** They own 20–50 named accounts and cannot visit 100+ pages a week. They need to know *when to reach out, and what to say*.

**Secondary users:** the AE (account context before calls), RevOps (who would later own the system).

**Problem statement:** meaningful changes on target accounts' websites (new product, pricing, leadership, funding, partnership, expansion, hiring) are the best timing hooks for outreach, but nobody checks consistently. Signals are discovered late or never.

**Value in one line:** *"Tell me when a target account does something worth a message, and give me the message."*

**Pilot value hypothesis:** if a BDR gets 1–3 high-quality alerts a week instead of checking sites manually, they will open and act on them. (The pilot demonstrates the mechanism; it can't prove behaviour change.)

---

## 2. MVP scope

### In scope
1. Upload / edit an account list (CSV or dashboard table): company, URL, industry, owner, priority.
2. Per account, a configured list of 3–5 page URLs (Product, Pricing, About/Leadership, News, Careers).
3. Fetch → clean → snapshot storage (SQLite).
4. Hash check → block-level diff → noise filter → LLM analysis.
5. Signal classification into a fixed taxonomy (section 5).
6. Slack alert (webhook) with the format from your brief.
7. Streamlit dashboard: accounts, run button, change feed (alerted / ignored / review), snapshot viewer.
8. Demo kit: 20 dummy sites, two scenario scripts, reset script, labeled test set.

### Explicitly out of the MVP
- Crawling or auto-discovering pages (page URLs are configured by hand).
- JavaScript rendering (Playwright/Selenium). Dummy sites are static HTML.
- Real third-party sites in the demo path; proxy rotation; robots.txt/ToS handling beyond a note.
- CRM / HubSpot / Salesforce integration, enrichment (Apollo, Clay), contact finding.
- Auto-sending outreach emails. The system **suggests**; the human sends.
- Multi-user auth, roles, billing, multi-tenant anything.
- Slack interactivity (buttons, threads, feedback loops). Webhook, one-way only.
- Embeddings / vector DB / RAG. Not needed for diff analysis.
- Image, PDF, video change detection.
- Cloud deployment, queues, Docker, Airflow. Everything runs on your laptop.
- Account scoring/prioritisation beyond showing the `priority` field in the alert.

---

## 3. Architecture (flow)

```
INPUTS            PROCESSING                        DECISIONS                    OUTPUTS               GTM ACTION
─────────         ─────────────────────────         ───────────────────────      ───────────────       ─────────────
accounts.csv  ->  1 Fetch page (requests)      ->   D1 First time seen?     ->   Store baseline        (nothing)
page list         2 Clean (strip scripts,            yes: save, stop
(3-5 URLs/acct)     nav, footer, cookie)
                  3 Extract text blocks        ->   D2 Hash same as last?   ->   Log "unchanged"       (nothing)
                  4 Hash + compare                   yes: stop
                  5 Block-level diff           ->   D3 Only noise left?     ->   Log "ignored"+reason  (nothing)
                  6 Noise rules                      (year, cookie, nav)           shown on dashboard
                  7 LLM: judge+classify        ->   D4 meaningful=false?    ->   Log "ignored (LLM)"   (nothing)
                    +summarise+outreach
                                               ->   D5 evidence in diff?    ->   Drop + log "rejected"  (nothing)
                                                    confidence >= Medium?   ->   Dashboard "Review"     BDR checks it
                                                    not a duplicate?
                                                    yes to all              ->   Slack alert +          BDR sends the
                                                                                 dashboard record        tailored message
```

Visual version: open `diagram.html`.

### Component choices (all deliberately boring)

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Best for a beginner GTM engineer; every library below is mainstream. |
| Fetch | `requests` | Static dummy sites need nothing more. |
| Clean/parse | `beautifulsoup4` | Remove `script/style/nav/footer/header`, cookie banners, then extract text blocks. |
| Diff | `difflib` (stdlib) over lists of blocks | No dependency; block-level is readable and robust. |
| Storage | SQLite (single file `observer.db`) | Zero setup, inspectable, perfect for a pilot. |
| LLM | Claude API via `anthropic` SDK, structured JSON output, model set by env var (default a fast model such as `claude-haiku-5-5`; swap to `claude-sonnet-5-5` for better quality) | One call per surviving change. Cost for the whole pilot is cents. |
| Alerts | Slack Incoming Webhook (`requests.post`) | No bot, no OAuth, 10 lines of code. |
| UI | Streamlit | Accounts table, run button, change feed. |
| Scheduling | Manual button / CLI now; Windows Task Scheduler later | Keeps the demo deterministic. |
| Dummy sites | Static HTML in `demo_sites/`, served by `python -m http.server` | You edit a file; the observer sees it instantly. |

**Why LLM-for-judgement and not pure rules?** Rules can reliably reject noise (copyright year, cookie text). They cannot reliably tell that "Meet Atlas, our autonomous agent platform" is a product launch while "We empower teams with cutting-edge solutions" → "We empower teams with innovative solutions" is not. The funnel uses rules for the cheap 80% and the LLM for the ambiguous 20%.

---

## 4. Processing steps in detail

1. **Load targets.** Read accounts + page URLs from DB (seeded from `accounts.csv`).
2. **Fetch.** GET with a 10s timeout, a descriptive User-Agent, one retry. Record HTTP status. Failure → log and continue to the next page (never crash the run).
3. **Clean.** Remove `script, style, noscript, nav, header, footer, form, iframe`, elements whose id/class matches `cookie|consent|banner|popup|gdpr`. Normalise whitespace, lowercase for comparison only.
4. **Extract blocks.** Ordered list of text blocks from `h1–h4, p, li, td, th, blockquote`. Drop blocks under ~3 words.
5. **Hash.** SHA-256 of the joined blocks. If it equals the last snapshot hash → log `unchanged`, stop.
6. **Diff.** `difflib` between old and new block lists → `added[]`, `removed[]`. (Modified blocks appear as one removed + one added.)
7. **Noise rules (cheap filter).** Drop diff blocks that match: copyright/year lines, "© 20xx", cookie/consent text, "last updated" dates, pure whitespace/punctuation changes, strings that differ only by digits that look like timestamps or counters, and near-identical text (similarity ≥ 0.92 on a removed/added pair). If nothing remains → log `ignored` with the matched rule name.
8. **LLM analysis.** Send: company name, industry, page type, and *only the remaining added/removed blocks*. Receive structured JSON (section 6).
9. **Validate.** JSON parses; `signal_type` is in the taxonomy; `evidence` is a substring of the added text (case/whitespace-insensitive).
10. **Route.** meaningful + High/Medium → Slack + dashboard; meaningful + Low → dashboard "Review"; not meaningful → logged as `ignored (llm)` with the model's reason; invalid → `rejected`.
11. **Dedupe.** Fingerprint = hash(account + page + signal_type + normalised evidence). If seen in the last 30 days, don't re-alert.
12. **Save new snapshot** (always, so the next diff is against the latest state, even when ignored).

---

## 5. Signal taxonomy and what to look for

Keep it to a fixed list so classification is testable. Maps to your section 6.

| Signal type | Typical page | Example trigger | Outreach angle pattern |
|---|---|---|---|
| New Product Launch | Product, News | New product/feature section appears | Reference the launch; ask how they plan to take it to market / who they're targeting. |
| New Product Category | Product | Moves into a new category (e.g. adds "AI agents") | Reference the category shift; tie to the pain it creates (new buyer, new motion). |
| Pricing Change | Pricing | New tier, plan removed, usage-based shift | Reference the packaging change; ask how it affects deal size/sales cycle. |
| Leadership Change | About, Leadership | New CRO/CMO/CEO listed | Congratulate and reference the likely priorities of the new leader; new leaders re-evaluate vendors. |
| Funding Announcement | News, About | Series A/B/C, amount | Reference the round and the growth mandate that comes with it. |
| Major Partnership | News, Product | Named partner or integration | Reference the partnership; ask about joint GTM. |
| Market / Geographic Expansion | News, About, Careers | New region, new office, new vertical | Reference the market; ask about local ramp-up. |
| Strategic Initiative | News, About | Public initiative (sustainability, platform shift, acquisition) | Reference the initiative; tie to a business outcome. |
| Hiring / Growth Signal | Careers | Cluster of new roles in one function, or a new leader role | Reference the build-out; ask what they are scaling. |

**Single-job posting is not a signal; a cluster or a senior/new-function role is.** The prompt must say this.

---

## 6. LLM contract

**Input (per surviving change):**
```
company, industry, account_priority, page_type, url
added_blocks[], removed_blocks[]
```

**Required JSON output:**
```json
{
  "meaningful": true,
  "signal_type": "New Product Launch",
  "confidence": "High",
  "change_summary": "Acme AI launched a new AI Agents product.",
  "why_it_matters": "The company appears to be expanding into autonomous agents, which suggests a new buyer persona and GTM motion.",
  "outreach_angle": "Reference the AI Agents launch and ask how they plan to position it with existing customers vs. new buyers.",
  "evidence": "Introducing Acme Agents: autonomous agents that handle ...",
  "reason_if_not_meaningful": null
}
```

**Prompt rules (non-negotiable):**
- Judge only from the provided blocks. Do not use outside knowledge about the company.
- `evidence` must be copied verbatim from `added_blocks`.
- If the change is wording polish, formatting, navigation, legal boilerplate, or generic marketing language: `meaningful=false` and fill `reason_if_not_meaningful`.
- If unsure, lower the confidence; do not invent facts (amounts, names, dates) not in the text.
- Outreach angle: one or two sentences, must mention the specific detail, no flattery filler.

---

## 7. Data model (SQLite)

| Table | Key fields |
|---|---|
| `accounts` | id, company_name, website_url, industry, owner, priority, active |
| `pages` | id, account_id, page_type (product/pricing/about/news/careers), url |
| `snapshots` | id, page_id, fetched_at, http_status, content_hash, clean_text (blocks as JSON) |
| `changes` | id, page_id, old_snapshot_id, new_snapshot_id, detected_at, added_blocks, removed_blocks, status (`unchanged`/`ignored_rule`/`ignored_llm`/`rejected`/`review`/`alerted`), reason |
| `analyses` | id, change_id, meaningful, signal_type, confidence, summary, why_it_matters, outreach_angle, evidence, model, raw_json |
| `alerts` | id, change_id, fingerprint, channel, sent_at, success |
| `runs` | id, started_at, finished_at, pages_checked, changed, alerted, errors |

Relationship: accounts 1—N pages 1—N snapshots; pages 1—N changes 1—1 analyses; changes 1—0..1 alerts.

---

## 8. Integrations

| Integration | Setup | Failure fallback |
|---|---|---|
| **Claude API** | Get an API key at console.anthropic.com, store in `.env` as `ANTHROPIC_API_KEY`. Never commit it. | If the call fails or times out: mark change `review` with reason "LLM unavailable"; retry next run. |
| **Slack** (you have no workspace yet) | 1) slack.com → create a free workspace. 2) Create channel `#gtm-triggers` (private). 3) api.slack.com/apps → Create App → From scratch → Incoming Webhooks → On → Add New Webhook to Workspace → pick the channel. 4) Copy the URL into `.env` as `SLACK_WEBHOOK_URL`. | If missing or failing: print the formatted alert to the console and flag `alerts.success=0`. The demo still works. |
| **Dummy sites** | `python -m http.server 8000 --directory demo_sites` | If port busy, use 8001 (configurable base URL). |

---

## 9. Failure cases and handling

| Failure | Likely cause | Handling |
|---|---|---|
| Page returns 404/500/timeout | Server down, bad URL | Log error, keep old snapshot, don't diff, report in run summary. |
| Page returns empty / suspiciously short text | Block page, JS-only site | If new text < 30% of old length, flag `review: possible fetch problem`; don't alert. |
| First run for a page | No baseline | Save baseline, no diff, no alert. (Demo: run once before presenting.) |
| Noise slips through rules | New noise pattern | LLM returns `meaningful=false`; logged for tuning. |
| LLM hallucinates | Over-eager summarising | Evidence-substring check rejects it. |
| LLM returns invalid JSON | Rare | One retry, then `rejected`. |
| Duplicate alerts | Same change re-detected | Fingerprint dedupe. |
| Slack webhook fails | Wrong URL, network | Console fallback; error recorded. |
| Real meaningful change misclassified | Ambiguous text | Visible in dashboard; add to labeled test set. |
| Bulk change (redesign) | 40+ blocks change at once | If > N blocks changed, summarise top-N and flag `review`. Don't send a giant diff to the LLM. |
| API key leak | Committing `.env` | `.gitignore` from day one. |

---

## 10. Success metrics

**Pilot (what you can honestly measure):**

| Metric | Target | How |
|---|---|---|
| Noise rejection | 100% of planted noise changes produce **no Slack alert** | Test set of ~8 noise fixtures |
| Signal detection | ≥ 90% of planted meaningful changes produce an alert | Test set of ~8 signal fixtures |
| Classification accuracy | ≥ 85% correct `signal_type` | Compare against labels |
| Evidence validity | 100% of sent alerts have verifiable evidence | Automated check |
| Demo reliability | 3 consecutive clean end-to-end rehearsals | Checklist |
| Run time | < 60s for 20 accounts × 4 pages | Run log |
| Cost | < $1 total for the build and demo | API dashboard |

**Business metrics the pilot can't prove but should define for a future version:** alert-to-action rate (BDR sends outreach within 48h), reply rate on signal-triggered outreach vs. baseline, precision as rated by BDRs (thumbs up/down), false-positive rate per week.

---

## 11. The demo

### Pre-demo state
- 20 dummy sites live on localhost, baseline snapshot taken (`run_observer` run once).
- Dashboard open on **Change feed**. Slack channel visible on a second window.
- `demo_scripts/` contains `scenario_a_noise.py` and `scenario_b_signal.py`, which edit Acme's files, plus `reset_demo.py`.

### Flow (≈ 6–8 min)
1. **Set the scene (45s).** "BDRs have 30 accounts and no time to watch their sites." Show the accounts table (20 accounts, owner, priority).
2. **Show the original Acme AI site** in a browser (Products + Pricing pages).
3. **Scenario A, the noise (90s).** Run `scenario_a_noise.py`: changes © year, adds a cookie banner, tweaks a nav link, and rewords a tagline ("cutting-edge" → "innovative"). Click **Run observer**. Show: pages changed ✔, **Slack silent**, dashboard shows each change as *Ignored* with reasons. *"Four website changes, zero alerts. That's the point."*
4. **Scenario B, the signal (2 min).** Edit the Products page live in your editor: add an "Introducing Acme Agents" section (and optionally a pricing tier or a new VP Sales on About). Save. Refresh the browser to show the change. Click **Run observer**.
5. **The result (90s).** Slack alert appears (🚨 New GTM Trigger — Acme AI, signal type, why it matters, outreach angle, source, confidence). Click through to the dashboard record showing the diff, the evidence quote, and the funnel path it took.
6. **The funnel recap (45s).** Show the diagram: "80 pages, N changed, 1 alert."
7. **GTM action (30s).** Copy the outreach angle into a draft message. Close with "what I'd do next".

### Rehearsal and safety nets
- `reset_demo.py` restores all sites and the DB to the baseline in one command.
- Pre-record a 60s screen capture of the full flow as backup.
- Console fallback prints the alert even if Slack fails.
- Test the LLM call before presenting; keep a cached analysis for the Acme scenario as an emergency "replay" mode (clearly labelled).

---

## 12. Build plan (phases for Claude Code)

Each phase ends with something you can run and verify. Don't start phase N+1 until N passes.

| Phase | Deliverable | Done when |
|---|---|---|
| **1. Dummy world** | `demo_sites/` with 20 companies × 4 pages, served locally; Acme AI has distinct content | You can open `localhost:8000/acme-ai/products.html` |
| **2. Fetch + clean + store** | `fetcher`, `cleaner`, SQLite schema, seed from `accounts.csv` | Running twice produces 80 snapshots, no changes |
| **3. Diff + noise rules** | block diff, rule filter with named rules | Scenario A edits are all `ignored_rule` with reasons |
| **4. LLM analysis** | Prompt, JSON schema, validation, evidence check | Scenario B returns correct signal; noise-ish wording is `meaningful=false` |
| **5. Slack + dedupe** | Webhook sender, console fallback, fingerprinting | Alert appears in `#gtm-triggers`; second run doesn't re-alert |
| **6. Dashboard** | Streamlit: accounts, run button, change feed, snapshot/diff viewer | Everything in the demo flow is clickable |
| **7. Test set + demo kit** | ~16 labeled fixtures, `evaluate.py`, scenario and reset scripts | Metrics from section 10 print in one command; 3 clean rehearsals |

**Suggested repo layout**
```
GTM AGENT/
  plan.md  diagram.html
  accounts.csv
  .env  (never committed)   .gitignore
  observer/        fetcher.py  cleaner.py  differ.py  noise_rules.py
                   analyzer.py  slack.py  db.py  pipeline.py
  app.py           (Streamlit)
  demo_sites/      acme-ai/ ... (20 folders)
  demo_scripts/    scenario_a_noise.py  scenario_b_signal.py  reset_demo.py
  tests/fixtures/  (labeled changes)   evaluate.py
```

---

## 13. Decisions I made on your behalf (tell me if you disagree)

1. Page URLs per account are configured by hand, not discovered.
2. Slack gets High + Medium; Low goes to the dashboard only.
3. Dedupe window is 30 days.
4. The default LLM is a fast model, configurable by env var.
5. All 20 accounts are served from one local server rather than 20 separate ports.
6. The dashboard is a *viewer + trigger*, not an editor of rules.

## 14. Open items to resolve before building
- Industry mix for the 20 synthetic accounts (suggest 12 SaaS, 4 fintech, 4 other). I can generate these.
- Your Anthropic API key and a Slack workspace (setup steps in section 8).
- Whether you want the optional "real website" appendix after the pilot works.

---

## 15. Addendum: Attio CRM and outreach drafting (group feedback)

Feedback from the group: use Attio as the CRM; every trigger is saved there and the Slack alert links to it; store the decision maker per target company; after a trigger, create an outreach message the BDR can edit and mark sent.

### New flow
```
alert_ready change
  -> (1) upsert Company in Attio (match on domain)
  -> (2) create a Trigger entry in Attio (signal, confidence, summary, why, angle, evidence, source URL)
  -> (3) look up the decision maker (Person linked to that Company, added by the BDR)
  -> (4) draft an outreach message (LLM, mock stand-in until a key exists) addressed to that person
  -> (5) save the draft in Attio as an Outreach Message entry, status = Draft
  -> (6) Slack alert includes the Attio link (trigger + draft)
BDR: opens the link, edits the draft, sets Approved, sends from their own email/LinkedIn, sets Sent.
```

### Attio data model (standard objects first, because custom objects need a paid plan)
| Attio item | Type | Purpose |
|---|---|---|
| Companies | standard object | one record per target account, matched on domain |
| People | standard object | decision makers, linked to a Company, with job title; added by the BDR by hand |
| GTM Triggers | list on Companies | one entry per alert: signal type, confidence, summary, why it matters, outreach angle, evidence, source URL, detected at |
| Outreach Messages | list on People | one entry per draft: subject, body, trigger link, status (Draft / Approved / Sent), owner |

### Decisions
- D6. Attio is the system of record for triggers, contacts and messages. SQLite stays as the observer's local snapshot/diff store.
- D7. The BDR adds the decision maker by hand. Auto-finding people from About pages is fragile and cannot find emails.
- D8. The AI drafts the message from the signal and the contact's title; the BDR edits and approves. Same provider switch as the analyzer (Claude when a key exists, labelled mock otherwise).
- D9. "Send" means status only. The BDR sends from their own inbox or LinkedIn; Attio tracks Draft, Approved, Sent. No email integration in the pilot.
- D10. Attio failure never loses an alert: Slack still goes out (without the link), the change is marked `crm_failed`, and a retry happens next run.
- D11. If no decision maker exists for the company, the trigger is still saved and alerted, and the Slack message says "no contact on file" instead of a draft.

### Build phases
- Phase 8: Attio setup + client (`observer/attio.py`): workspace, API key, create list attributes, upsert company, create trigger entry, return `web_url`. Test against the real workspace.
- Phase 9: contacts + message drafting (`observer/outreach.py`): decision-maker lookup, draft with Claude/mock, save to Outreach Messages.
- Phase 10: wire into the pipeline and Slack (link in the alert, `crm_failed` retry), dashboard additions (Attio link, draft preview), update the demo script.
- Then the original Phase 7 (test set, evaluate.py, reset, rehearsals), extended to check the CRM records.

### Open items
- Attio plan: confirm lists are available on the current plan (custom objects need Pro or higher; the design above avoids them).
- API key: create in Attio (Settings -> Developers) with record and list read/write plus object configuration read.
- Whether the BDR wants the draft in Slack too, or only in Attio.


### Update (Phase 10 built, Clay framing)
The project is now framed as an internal tool by a GTM engineer at Clay (example seller). The decision makers are Clay's ICP personas, and drafts are written from what Clay sells (`observer/seller.py`). Phases 8, 9 and 10 are built; see `HANDOFF.md` for status and `DECISIONS.md` D12-D18. Added: careers page (5 pages per company), Scenario C (hiring push), `crm_sync` table, Attio links and draft inside the Slack alert, Outreach drafts view in the dashboard.

---

## 16. Plan: push every trigger and its draft to Airtable (proposed, not built)

### Goal
One Airtable row per alert, holding everything a BDR needs in a single working table: who to contact, what changed on the website, why it matters, and the email draft. Airtable is added as a second destination; Attio stays the CRM.

### Row design (table "Trigger Outreach")
| Airtable field | Source in the project |
|---|---|
| First name, Last name | `crm_sync.contact_name`, split on the first space |
| Title | `crm_sync.contact_title` |
| Company | `accounts.company_name` |
| Trigger type | `analyses.signal_type` |
| Trigger reason | `analyses.why_it_matters` |
| What changed on the website | `analyses.change_summary`, then the added and removed text from `changes` (before and after, capped at ~1,500 characters) |
| Evidence | `analyses.evidence` |
| Source page | `pages.url` |
| Confidence | `analyses.confidence` |
| Suggested angle | `analyses.outreach_angle` |
| Email subject | `crm_sync.subject` |
| Email body | `crm_sync.body` |
| Status | Draft / Approved / Sent (BDR changes it in Airtable) |
| Account owner, Detected at | `accounts.owner`, `changes.detected_at` |
| Attio link | `crm_sync.person_url` |
| Change ID | `changes.id`, used as the unique key so a retry updates the row instead of duplicating it |

### Build steps
1. **Setup (you).** Airtable account, a base, a personal access token with record read/write (and schema access if we want the tool to create the fields), the base ID. Put `AIRTABLE_TOKEN`, `AIRTABLE_BASE_ID` and `AIRTABLE_TABLE` in `.env`.
2. **Verify the API (me).** Confirm the current upsert call, field types, limits and rate limit against Airtable's docs before writing code. Test auth read-only first.
3. **Client (me).** `observer/airtable.py`: check the table has the fields above (create missing ones if the token allows, otherwise list what to add), upsert one row by Change ID, return the row URL.
4. **Wire in (me).** Push the row right after the Attio save, inside the same sync step. Add `airtable_status`, row ID and URL to the sync record. A failed push never blocks the Slack alert and is retried next run, like Attio.
5. **Surface it (me).** Add the Airtable row link to the Slack alert and the dashboard.
6. **Prove it (me).** Extend `rehearse.py` (scenario B and C write exactly one row; Airtable down then recovered) and run three rehearsals. Reset also clears the demo rows.

### Decisions I need from you
- **Attio and Airtable, or Airtable instead?** I assumed both. If you want Airtable only, say so and I will drop the Attio step.
- **One flat table, or a Contacts table plus a Triggers table?** I recommend one flat table for the demo.
- **One-way only.** Changing Status in Airtable will not flow back into the tool.

### Risks
- Two places holding the same data. Mitigation: Attio is the CRM record, Airtable is the BDR's working list, and the roles are stated in the README.
- Free-plan limits (record count, API calls). Fine for a demo of a handful of rows.

### Why the table exists: handoff to a sequence (clarified by the user)
The Airtable row is the trigger point for starting an outreach sequence. Airtable does not send email; a sequencer or automation does.
- Extra row fields: contact email, sequence/campaign name, "Ready to send" flag (true only when Status = Approved and an email exists).
- Status flow: Draft (tool creates) -> Approved (BDR reviews and edits) -> Sent (set by the sequencer or BDR). Only Approved rows start a sequence.
- This supersedes decision D9 ("send is a status only") once the user confirms the sequencer.
- The 20 demo contacts use fake `@...example.com` emails and must never be sequenced; the demo stops at Approved, or uses an inbox the user owns.
- Real prospects need an unsubscribe link and a legal basis for contact (normally provided by the sequencer).
- Open: which tool starts the sequence (Instantly / other / Airtable automation + Gmail), and whether it starts automatically on Approved or by a BDR button.

### Scope decision (final): the project ends at the Airtable row
- Instantly is the narrative only. We do NOT connect Airtable to Instantly or any sequencer, and nothing is sent. The README/demo says: "this table is what a sequencer such as Instantly would pick up next."
- Status values are Draft and Approved. There is no Sent state, no "Ready to send" flag and no sequence field in the build.
- Attio stays as the CRM; Airtable is added as the BDR's flat working table (assumed, since no objection was raised).
- Closes the open items above: no sequencer choice and no auto-start are needed. D9 ("send is a status only") stays in force.
- Build steps 1-6 above are unchanged and are the whole remaining scope.
