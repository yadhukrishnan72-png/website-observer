# Decisions

Newest context first within each group. Full reasoning for the original design is in `plan.md` section 13; Attio decisions D6-D11 are also in section 15.

## Scope and product
- **Pilot, not production.** Optimise for clear GTM value, an understandable architecture and a reliable live demo.
- **Dummy sites on localhost.** 20 generated companies in `demo_sites/`, so the demo is controlled and repeatable. Real-website monitoring is a deferred appendix.
- **Careers page / hiring signal omitted** from the demo; the taxonomy still includes "Hiring / Growth Signal".
- **Do nothing when nothing meaningful changed.** No daily digest, no "all clear" message.

## Detection
- **Three-gate funnel.** Hash match (free), rule-based noise filter (free), LLM only on surviving changed blocks. Keeps cost near zero and makes behaviour explainable.
- **Diff cleaned text blocks, not raw HTML.** The cleaner drops script/style/nav/header/footer/form/iframe/svg and cookie/consent/banner/popup/gdpr elements. Stripped boilerplate is kept as `kind: text` entries so ignored noise can be logged with a reason.
- **Named noise rules, each with a reason:** copyright_year, last_updated_date, cookie_text, timestamp_only, formatting_only, typo_fix, cookie_banner, navigation_change, tracking_script, styling_change, footer_change.
- **A changed number is never noise.** Price changes must reach the analyzer.
- **Word swaps go to the LLM.** `near_identical` (similarity >= 0.92) was removed because it swallowed real rewordings; replaced by `typo_fix` (same word count, every changed word >= 0.8 similar) plus a number guard.
- **Bulk guard.** More than 25 changed blocks, or content shrinking below 30%, routes to `review` (looks like a redesign or broken fetch), not to the LLM.

## Analysis
- **Claude API as the real provider, with a labelled mock stand-in** because no API key existed. `OBSERVER_LLM=auto` uses Claude only when `ANTHROPIC_API_KEY` is set. The mock is a keyword heuristic, labelled `mock-heuristic` everywhere it appears.
- **Fixed 9-type signal taxonomy and a strict JSON contract** (meaningful, signal_type, confidence, change_summary, why_it_matters, outreach_angle, evidence, reason_if_not_meaningful).
- **Hallucination guard.** Reject unknown signal types and any evidence quote not found verbatim in the changed text.
- **Low confidence goes to `review`, not Slack.** LLM unavailable also goes to `review`, never a crash.
- **Model call settings.** Default `claude-haiku-5-5`, `output_config` effort "low", no temperature, no prefill; a refusal is treated as an error; one retry on bad JSON.

## Alerting
- **Dedupe fingerprint** = sha256(company | page_type | signal_type | normalised evidence), 30-day window, counting only successful alerts. Consequence: re-running Scenario B needs a reset.
- **Slack via Incoming Webhook** (plain mrkdwn text), not a bot token. No scopes needed.
- **Console fallback.** With no webhook, or if Slack fails, the alert prints as `[CONSOLE ALERT]`. An alert is never silently lost.
- **Alert format** is fixed: Change, Signal type, Why it matters, Suggested outreach angle, Source, Confidence, plus owner and priority.

## Stack
- **Python 3.12, SQLite, Streamlit.** Boring and local. Dependencies: requests, beautifulsoup4, anthropic, streamlit.
- **Tiny `.env` loader** in `observer/config.py` instead of python-dotenv.
- **Dashboard** has a one-click "Run observer now", scenario buttons and a confirmed reset, so the demo has a backup if live edits go wrong.

## Attio CRM and outreach (added after group feedback)
- **D6.** Attio is the system of record for triggers, contacts and messages. SQLite stays as the observer's snapshot/diff store.
- **D7.** The BDR adds the decision maker by hand. Auto-finding people from About pages is fragile and cannot find emails.
- **D8.** The AI drafts the outreach message from the signal and the contact's title; the BDR edits and approves. Same Claude/mock switch.
- **D9.** "Send" means status only (Draft, Approved, Sent). The BDR sends from their own inbox or LinkedIn. No email integration.
- **D10.** Attio failure never loses an alert: Slack still goes out without the link, the change is marked `crm_failed`, and it retries next run.
- **D11.** No decision maker on file: still save and alert the trigger, and say "no contact on file" instead of a draft.
- **Standard objects plus Lists, not custom objects.** Custom objects need a paid Attio plan and admin rights. Companies and People are standard; GTM Triggers and Outreach Messages are Lists. Fallback if Lists are blocked: Notes on the Company record.
- **Upsert by domain** (Attio "assert record" with a unique matching attribute) so repeat runs never duplicate companies. Use the `web_url` returned in record responses for the Slack link.

## Clay framing and Phase 10
- **D12. Frame as an internal tool by a GTM engineer at Clay, as a worked example.** A specific seller, buyers and reason for each trigger make the demo easier to follow. Company names stay fictional because the live demo needs sites we can edit. The seller is one config file (`observer/seller.py`) plus `contacts.csv`, so the code stays generic.
- **D13. Decision makers are Clay's ICP personas** (Head of Revenue Operations, Head of Sales Operations, Director of GTM Operations, GTM Systems Lead, GTM Engineer, Director of Growth, Chief Revenue Officer), taken from the personas on clay.com.
- **D14. Messaging depends on what Clay sells.** Each draft ties the detected signal to Clay's own published positioning ("infrastructure to get any data, run agentic workflows, and launch GTM plays"). No results, prices or numbers; a number not in the source text fails draft validation.
- **D15. The Slack alert carries the decision maker and links to Attio and the Airtable row, not the email draft.** (Changed 2026-10-27: the draft made the alert too long.) The draft lives in Airtable and Attio, where the BDR edits and approves it.
- **D16. Careers page and a hiring scenario were added back** because a company hiring revenue operations or GTM roles is a strong trigger for this seller. A single routine posting is still ignored.
- **D17. Reset clears the two demo lists in Attio** (never companies or people) so rehearsals do not pile up entries.
- **D18. Attio saves are retried, not blocking.** `crm_sync` records status per change; `crm_failed` is retried next run without re-sending Slack.

## Scenario expansion (2026-10-27)
- **D19. One data-driven scenario registry** (`demo_scripts/scenarios.py`) shared by the dashboard, the tests and the CLI. Each scenario edits a different existing company's pages using that company's own generated text, so no new data was created. The original Acme scenarios (noise, new product, hiring push) are kept and run from their original scripts.
- **D20. "New ICP" is classified as Market Expansion**, like geographic expansion, with its own summary and angle. Adding a tenth signal type would have meant changing the select options in Attio and Airtable, which are created once.
- **D21. "Combined growth signals" needs no new storage.** The Slack alert lists other signals already alerted for the same account within 30 days ("Also on this account"), and the dashboard groups alerted signals by company. The strongest case is Orbit CRM (funding + hiring + new CRO).
- **D22. The stand-in analyzer got one new rule for new customer segments.** The stand-in is rule-based and shaped to these scenarios; the scores in `evaluate.py` and `test_scenarios.py` measure the rules, not an AI. Real validation needs a Claude key.
- **D23. `acme-noise` is outside the "Apply all" bundle** because it edits the same Acme products page as the product launch scenario.

## Visual design (2026-10-28)
- **D24. The dashboard is themed after clay.com through Streamlit's own theme file** (`.streamlit/config.toml`, light and dark), with no custom CSS. The identity colors were sampled from the rendered site: black buttons, the lime accent (#cbd810), cream panels (#f4f3f0) and the deep hero green (#01533c). Status colors use Clay's palette tokens. Light mode is white and cream with black buttons; dark mode is deep green. An earlier version used Clay's blueberry as the main accent and read as generic blue, so it was replaced. Every text, link, button and badge pair meets 4.5:1.
- **D24a. Dark-mode buttons use a green, not lime**, because Streamlit puts white text on primary buttons and white on lime is unreadable. The cost is that selected pills in dark mode are a little dimmer.
- **D25. Clay's fonts (Roobert, Canela) are licensed, so they are not embedded.** The theme uses Inter (which clay.com also uses), DM Sans for headings and DM Mono for code, loaded from Google Fonts.
- **D26. In the scenarios table the result columns come first**, ahead of the long "What changes" description, so they stay visible without scrolling.

- **D27. The dashboard follows a screenshot of clay.com supplied by the user** (`Design.png`, kept out of the repo): a floating white nav bar with a black call-to-action, a left rail with letter-spaced labels and outlined inputs, hairline-separated stat cells, a two-column card grid with outlined tags, and Clay's exact grey, cream and blue tokens. The theme is locked to light so it always matches; the dark theme was dropped.
- **D28. This look uses a small stylesheet (`assets/clay.css`)**, an exception to "theme file only" because the layout cannot be done through theme options. It targets only keyed containers (`st.container(key=...)`) and its own classes, and `requirements.txt` pins `streamlit==1.66.1` so the styling cannot break on a new release.
- **D29. Clay's typeface (Roobert) is licensed, so Figtree is used as the closest free font.** If a Roobert license is available, add the font files and a `[[theme.fontFaces]]` entry in `.streamlit/config.toml`.

## Email generation (2026-10-28)
- **D30. Every first email follows four beats:** reference the specific detected change, one sentence on the usual GTM implication, a direct Clay pitch for that problem, and one low-friction offer to show how Clay could support it. The pitch is never hidden. Wording lives in `observer/playbooks.py`, one playbook per trigger: hiring, product launch, funding, executive change, geographic expansion, pricing change, new ICP, strategic partnership, enterprise GTM push, plus a combined-signals playbook. Each has its own Clay value proposition.
- **D31. Facts come only from the detected change.** The evidence and the added or removed page text are parsed for names, amounts, places, prices and roles. When a fact is missing the wording falls back to a cautious sentence or quotes the page; it never fills a gap. The source URL, evidence and Clay angle are stored as internal notes (`crm_sync.draft_notes`) and shown under "Why this message" in the dashboard, not put in the email body.
- **D32. A draft must pass a strict validator before it is saved**, whoever wrote it: 70-110 words, at least four paragraphs, names Clay, signed by the account owner, one offer (at most one question mark, no exclamation marks), a banned list of buzzwords and curiosity-bait CTAs, reuses words from the detected change, and every number must appear in the source text.
- **D33. Variety without randomness.** Two wordings each for the implication, the Clay paragraph and the offer, three opening words, and a persona lens (operators and builders versus revenue and growth leaders). A stable hash of company and trigger picks them, so the same account always gets the same email.
- **D34. Several signals on one account produce a combined email** (funding, hiring and a new leader together), built from the other alerts in the last 30 days. Because drafts are created as each alert fires, the latest draft for an account supersedes the earlier, narrower ones; the BDR should send the newest.

## Deferred or rejected
- Real email sending, LinkedIn automation: out of scope for the pilot.
- Auto-discovery of decision makers: rejected for now (D7).
- JavaScript-rendered page monitoring, authenticated pages: out of scope.
