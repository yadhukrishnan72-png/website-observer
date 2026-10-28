"""Turn an alert into a draft outreach email for the account's decision maker.

Each email follows one structure: reference the specific change, give the GTM implication in one sentence, connect
Clay to that problem, and close with one low-friction offer. The per-trigger wording lives in playbooks.py.

Same provider switch as the analyzer: Claude when ANTHROPIC_API_KEY is set, otherwise the playbook stand-in labelled
'mock-heuristic' (template-based, not an AI). Whatever writes the draft, it must pass validate() before it is saved.
Drafts are only ever created with status Draft; the BDR edits, approves and sends them.
"""
import csv
import json
import re
from pathlib import Path

from . import analyzer, attio, config, playbooks, seller

ROOT = Path(__file__).resolve().parent.parent
MIN_WORDS, MAX_WORDS = playbooks.MIN_WORDS, playbooks.MAX_WORDS
MAX_SUBJECT = 80

SYSTEM_PROMPT = f"""You write first-touch outbound emails for a BDR at {seller.NAME} to a decision maker at a target \
account. A change was detected on that account's website.

Structure, as four short paragraphs of plain text:
1. Reference the specific change, using the facts provided.
2. One concise sentence on what that usually means for go-to-market.
3. Connect {seller.NAME} directly to that problem or opportunity, using the Clay angle provided. Name {seller.NAME} \
and say what it does; do not hide the pitch. One or two sentences.
4. One low-friction call to action: offer to show how {seller.NAME} could support that specific initiative.

Rules:
- {playbooks.MIN_WORDS} to {playbooks.MAX_WORDS} words in total, including the greeting and sign-off. Conversational, \
specific and credible, like a person wrote it.
- Use only the facts provided. Never invent facts about the company or the contact. Where the evidence is thin, hedge \
("usually", "often", "if") instead of asserting.
- Write the call to action as an offer ("happy to show you ..."), not a question about availability. At most one \
question mark in the whole email. No exclamation marks.
- Never use these words or phrases: {", ".join(playbooks.BANNED)}.
- Do not put the source URL in the email.
- Address the contact by first name. Sign off as: Best, then the rep's first name, then {seller.NAME}, each on its own line.
- The subject line must be specific to the trigger, under 70 characters, with no hype.

Reply with ONLY a JSON object: {{"subject": "...", "body": "..."}}."""


# --------------------------------------------------------------------------- providers

def _claude_draft(ctx):
    import anthropic
    client = anthropic.Anthropic(timeout=45.0)
    user = f"Rep: {ctx.get('owner')}\n" + playbooks.guidance(ctx)
    resp = client.messages.create(
        model=config.model_name(), max_tokens=1200,
        system=SYSTEM_PROMPT + "\n\nSeller context: " + seller.prompt_context(),
        output_config={"effort": "low"}, messages=[{"role": "user", "content": user}])
    if resp.stop_reason == "refusal":
        raise RuntimeError("model refused")
    text = "".join(b.text for b in resp.content if b.type == "text")
    result = analyzer._parse_json(text)
    _, notes = playbooks.compose(ctx)
    if isinstance(result, dict) and isinstance(result.get("body"), str):
        notes["word_count"] = len(result["body"].split())
    return dict(result, notes=notes), config.model_name()


def draft(ctx):
    """Returns (draft dict with subject, body and internal notes, model label). Raises on provider failure."""
    if config.llm_provider() == "claude":
        try:
            return _claude_draft(ctx)
        except (ValueError, json.JSONDecodeError):          # bad JSON: one retry
            return _claude_draft(ctx)
    result, notes = playbooks.compose(ctx)
    return dict(result, notes=notes), "mock-heuristic"


# --------------------------------------------------------------------------- validation

def validate(d, ctx):
    """Returns an error string, or None if the draft is acceptable."""
    if not isinstance(d, dict) or not isinstance(d.get("subject"), str) or not isinstance(d.get("body"), str):
        return "malformed draft (subject or body missing)"
    subject, body = d["subject"].strip(), d["body"].strip()
    if not subject or not body:
        return "empty subject or body"
    if len(subject) > MAX_SUBJECT:
        return "subject too long"
    words = len(body.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        return f"body has {words} words; expected {MIN_WORDS}-{MAX_WORDS}"
    low = (subject + " " + body).lower()
    if ctx["contact_name"].split()[0].lower() not in body.lower():
        return "draft does not address the contact by first name"
    if seller.NAME.lower() not in body.lower():
        return f"draft does not mention {seller.NAME}"
    rep = (ctx.get("owner") or "").split()[0].lower()
    if rep and rep not in body.lower():
        return "draft is not signed by the account owner"
    if re.search(r"[\[\]{}<>]", subject + body):
        return "draft contains placeholder-like characters"
    if "!" in subject + body:
        return "draft contains an exclamation mark"
    if body.count("?") > 1:
        return "draft has more than one call to action question"
    if len([p for p in body.split("\n\n") if p.strip()]) < 4:
        return "draft does not follow the reference / implication / Clay / offer structure"
    if re.search(r"[a-z0-9],\s+[A-Z][a-z]+ing\b", body):
        return "draft pastes page text into a sentence (capitalised fragment after a comma)"
    for phrase in playbooks.BANNED:
        if phrase in low:
            return f"draft uses a banned phrase ({phrase!r})"
    grounding = playbooks.grounding_words(ctx)
    if grounding and not any(w in body.lower() for w in grounding):
        return "draft does not reference the detected change"
    source = playbooks.source_text(ctx)
    for number in re.findall(r"\d[\d,.]*", subject + " " + body):
        if number.rstrip(",.") not in source:
            return f"draft contains a number not in the source ({number.rstrip(',.')}): possible invented fact"
    return None


# --------------------------------------------------------------------------- orchestration

def create_draft(alert, company=None):
    """alert: company, website_url, owner, signal_type, change_summary, why_it_matters, outreach_angle, evidence,
    url and the changed page text; optionally 'others' (other signals on the same account). company: the Attio
    company record if the caller already has it (id, web_url).
    Returns a dict with a 'status': drafted | no_contact | draft_failed | crm_failed."""
    try:
        company = company or attio.assert_company(alert["company"], attio.placeholder_domain(alert["website_url"]))
        contacts = attio.find_contacts(company["id"])
        if not contacts:
            return {"status": "no_contact", "company_url": company["web_url"]}
        contact = contacts[0]
        ctx = dict(alert, contact_name=contact["name"], contact_title=contact["title"])
        try:
            result, model = draft(ctx)
            error = validate(result, ctx)
        except Exception as e:                                        # provider down, refusal, bad JSON twice
            return {"status": "draft_failed", "error": f"{type(e).__name__}: {e}", "contact": contact,
                    "company_url": company["web_url"]}
        if error:
            return {"status": "draft_failed", "error": error, "contact": contact, "company_url": company["web_url"]}
        entry_id = attio.add_entry("outreach_messages", "people", contact["id"], {
            "subject": result["subject"].strip(), "message_body": result["body"].strip(), "status": "Draft",
            "signal": alert["signal_type"], "company": alert["company"], "account_owner": alert["owner"],
            "drafted_by": model})
        return {"status": "drafted", "contact": contact, "subject": result["subject"].strip(),
                "body": result["body"].strip(), "model": model, "entry_id": entry_id, "notes": result.get("notes"),
                "person_url": contact["web_url"], "company_url": company["web_url"]}
    except attio.AttioError as e:
        return {"status": "crm_failed", "error": str(e)}


def local_contact(company_name):
    """The placeholder decision maker from contacts.csv, used when Attio is not configured (safe demo mode)."""
    with open(ROOT / "contacts.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["company_name"] == company_name:
                return {"id": None, "web_url": None, "name": row["contact_name"], "title": row["job_title"],
                        "email": row["email"]}
    return None


def create_local_draft(alert):
    """create_draft for safe demo mode: contact from contacts.csv, nothing is saved outside the local database.
    Returns a dict with a 'status': drafted | no_contact | draft_failed."""
    contact = local_contact(alert["company"])
    if contact is None:
        return {"status": "no_contact"}
    ctx = dict(alert, contact_name=contact["name"], contact_title=contact["title"])
    try:
        result, model = draft(ctx)
        error = validate(result, ctx)
    except Exception as e:                                            # provider down, refusal, bad JSON twice
        return {"status": "draft_failed", "error": f"{type(e).__name__}: {e}", "contact": contact}
    if error:
        return {"status": "draft_failed", "error": error, "contact": contact}
    return {"status": "drafted", "contact": contact, "subject": result["subject"].strip(),
            "body": result["body"].strip(), "model": model, "notes": result.get("notes")}
