"""Turn an alert into a draft outreach message for the account's decision maker, saved in Attio.

Same provider switch as the analyzer: Claude when ANTHROPIC_API_KEY is set, otherwise a template
stand-in labelled 'mock-heuristic'. Drafts are only ever created with status Draft; the BDR edits,
approves and sends them.
"""
import csv
import json
import re
from pathlib import Path

from . import analyzer, attio, config, seller

ROOT = Path(__file__).resolve().parent.parent
MAX_WORDS = 130
MAX_SUBJECT = 100

SYSTEM_PROMPT = """You write short first-touch outreach emails for a B2B sales development rep.

You are given a business signal detected on a target account's website and the decision maker to write to.

Rules:
- 60 to 100 words. Plain text, no markdown, no bullet points.
- Open with the specific signal (use the evidence wording), not with flattery or "I hope this finds you well".
- Tie it to what someone in the contact's role cares about, in one sentence.
- Mention the seller's product once, linking the signal to one capability from the seller context. No feature lists.
- End with one low-pressure question. No hard pitch, no meeting links, no invented urgency.
- Use only facts present in the input. Never invent numbers, customer names, results or claims about the \
contact beyond their name and title.
- Address the contact by first name and sign off with the rep's first name.

Reply with ONLY a JSON object: {"subject": "<under 70 characters>", "body": "<the email>"}."""


# --------------------------------------------------------------------------- providers

def _claude_draft(ctx):
    import anthropic
    client = anthropic.Anthropic(timeout=45.0)
    user = (f"Company: {ctx['company']}\nContact: {ctx['contact_name']}, {ctx['contact_title']}\n"
            f"Rep: {ctx['owner']}\nSignal type: {ctx['signal_type']}\n"
            f"What changed: {ctx['change_summary']}\nEvidence from the page: {ctx['evidence']}\n"
            f"Why it matters: {ctx['why_it_matters']}\nSuggested angle: {ctx['outreach_angle']}")
    resp = client.messages.create(
        model=config.model_name(), max_tokens=1000, system=SYSTEM_PROMPT + "\n\nSeller context: " + seller.prompt_context(),
        output_config={"effort": "low"}, messages=[{"role": "user", "content": user}])
    if resp.stop_reason == "refusal":
        raise RuntimeError("model refused")
    text = "".join(b.text for b in resp.content if b.type == "text")
    return analyzer._parse_json(text), config.model_name()


INTRO = re.compile(r"^(?:introducing|meet|announcing)\s+(.+?)(?:[:,.—]|$)", re.I)

# signal type -> (opening sentence, closing question, subject); {c}=company, {x}=what. The middle of the
# email comes from seller.BRIDGES, which ties the signal to what the seller does.
TEMPLATES = {
    "New Product Launch": ("I saw {c} just introduced {x}.",
                           "How are you planning to bring {x} to your existing customers?", "{x} at {c}"),
    "New Product Category": ("I saw {c} just introduced {x}.",
                             "How are you approaching positioning for {x} versus your existing buyers?",
                             "{x} at {c}"),
    "Pricing Change": ("I noticed {c} changed its pricing or packaging.",
                       "How is the new structure landing with prospects so far?", "{c}'s new pricing"),
    "Leadership Change": ("I saw the leadership update at {c}.",
                          "What is at the top of the list for the next couple of quarters?",
                          "Leadership news at {c}"),
    "Funding Announcement": ("I saw {c}'s funding news.",
                             "Where are you planning to invest first?", "{c}'s funding news"),
    "Major Partnership": ("I saw {c}'s partnership announcement.",
                          "How does this change your go-to-market plans?", "{c}'s new partnership"),
    "Market Expansion": ("I saw {c} is expanding.",
                         "How are you planning to ramp up in the new market?", "{c}'s expansion"),
    "Strategic Initiative": ("I saw {c}'s recent strategic announcement.",
                             "What outcome are you aiming for in the first year?", "{c}'s strategic move"),
    "Hiring / Growth Signal": ("I noticed {c} is building out the team.",
                               "What are you scaling first?", "Building out GTM at {c}"),
}


def _mock_draft(ctx):
    opening, question, subject = TEMPLATES.get(ctx["signal_type"], TEMPLATES["Strategic Initiative"])
    m = INTRO.match(ctx["evidence"] or "")
    fill = {"c": ctx["company"], "x": m.group(1).strip() if m else "this"}
    first, rep = ctx["contact_name"].split()[0], (ctx["owner"] or "").split()[0] or "the team"
    body = (f"Hi {first},\n\n{opening.format(**fill)} The page says: \"{ctx['evidence']}\"\n\n"
            f"As {ctx['contact_title']}, you may already be thinking about this. "
            f"{seller.BRIDGES.get(ctx['signal_type'], seller.ONE_LINER)} {question.format(**fill)}\n\n"
            f"Best,\n{rep}\n{seller.NAME}")
    return {"subject": subject.format(**fill), "body": body}, "mock-heuristic"


def draft(ctx):
    """Returns (draft dict with subject and body, model label). Raises on provider failure."""
    if config.llm_provider() == "claude":
        try:
            return _claude_draft(ctx)
        except (ValueError, json.JSONDecodeError):          # bad JSON: one retry
            return _claude_draft(ctx)
    return _mock_draft(ctx)


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
    if len(body.split()) > MAX_WORDS:
        return f"body longer than {MAX_WORDS} words"
    if ctx["contact_name"].split()[0].lower() not in body.lower():
        return "draft does not address the contact by first name"
    if re.search(r"[\[\]{}<>]", subject + body):
        return "draft contains placeholder-like characters"
    source = " ".join([ctx["evidence"] or "", ctx["change_summary"], ctx["why_it_matters"], ctx["outreach_angle"]])
    for number in re.findall(r"\d[\d,.]*", subject + " " + body):
        if number.rstrip(",.") not in source:
            return f"draft contains a number not in the source ({number.rstrip(',.')}): possible invented fact"
    return None


# --------------------------------------------------------------------------- orchestration

def create_draft(alert, company=None):
    """alert: company, website_url, owner, signal_type, change_summary, why_it_matters, outreach_angle,
    evidence. company: the Attio company record if the caller already has it (id, web_url).
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
                "body": result["body"].strip(), "model": model, "entry_id": entry_id,
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
            "body": result["body"].strip(), "model": model}
