"""Decision D4/D5: is this change commercially meaningful, what is it, and what do we say?

Two interchangeable providers return the same JSON shape:
  - claude: the real LLM call (needs ANTHROPIC_API_KEY)
  - mock:   a keyword heuristic stand-in so the whole pipeline runs and demos without a key.
            It is NOT an AI; its output is labelled model='mock-heuristic'.
Everything after the provider call (validation, evidence check, routing) is shared.
"""
import json
import re

from . import config, db

SIGNAL_TYPES = [
    "New Product Launch", "New Product Category", "Pricing Change", "Leadership Change",
    "Funding Announcement", "Major Partnership", "Market Expansion", "Strategic Initiative",
    "Hiring / Growth Signal",
]
CONFIDENCE = ["High", "Medium", "Low"]
BULK_LIMIT = 25            # more changed blocks than this looks like a redesign, not a signal

SYSTEM_PROMPT = f"""You are a GTM signal analyst helping B2B sales development reps. You are given the text that \
changed on one page of a target account's website and must decide whether it is a commercially meaningful \
buying or business signal worth a sales outreach.

Rules:
- Judge ONLY from the provided added/removed text. Do not use outside knowledge about the company.
- Meaningful signals: {", ".join(SIGNAL_TYPES)}.
- NOT meaningful: wording polish, generic marketing language, formatting, navigation, legal boilerplate, \
copyright or date stamps, and a single routine job posting.
- Never invent facts (amounts, names, dates) that are not in the text.
- "evidence" must be copied verbatim from the added text (or the removed text for a pure removal).
- If unsure, lower the confidence rather than guessing.
- outreach_angle: one or two sentences, must reference the specific detail, no flattery filler.

Reply with ONLY a JSON object with these keys:
meaningful (bool), signal_type (one of the list above, or null), confidence ("High"|"Medium"|"Low"), \
change_summary (one sentence), why_it_matters (one or two sentences for a salesperson), outreach_angle (string), \
evidence (verbatim quote, or null), reason_if_not_meaningful (string or null)."""


# --------------------------------------------------------------------------- providers

def _claude_analyze(ctx):
    import anthropic
    client = anthropic.Anthropic(timeout=45.0)
    user = (f"Company: {ctx['company']} ({ctx['industry']}, priority {ctx['priority']})\n"
            f"Page: {ctx['page_type']} - {ctx['url']}\n\n"
            f"ADDED TEXT:\n" + "\n".join(f"- {b}" for b in ctx["added"]) +
            "\n\nREMOVED TEXT:\n" + "\n".join(f"- {b}" for b in ctx["removed"]))
    resp = client.messages.create(
        model=config.model_name(), max_tokens=2000, system=SYSTEM_PROMPT,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": user}])
    if resp.stop_reason == "refusal":
        raise RuntimeError("model refused")
    text = "".join(b.text for b in resp.content if b.type == "text")
    return _parse_json(text), config.model_name()


def _parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


ROLE = re.compile(r"\b(chief [a-z]+ officer|ceo|cto|cro|cmo|cfo|coo|vp\b|vice president|head of|"
                  r"general manager|president)\b", re.I)
FUNDING = re.compile(r"\b(raises?|raised|funding|series\s+[a-f]\b|seed round|investment|venture)\b", re.I)
PARTNER = re.compile(r"\b(partner(?:s|ship|ed)?|alliance|integrat(?:es|ion|ions)\b|collaborat)", re.I)
EXPAND = re.compile(r"\b(expands?|expansion|new (?:office|market|region|headquarters)|opens? (?:an? )?office|"
                    r"launch(?:es|ed)? in|enters?|now available in)\b", re.I)
INITIATIVE = re.compile(r"\b(acquir\w+|acquisition|strategic|initiative|rebrand\w*|reorgani[sz]\w*)\b", re.I)
HIRING = re.compile(r"\b(we'?re hiring|now hiring|open roles?|join our team|building out|hiring)\b", re.I)
INTRO = re.compile(r"\b(introducing|announcing|launch(?:es|ed|ing)?|unveil\w*|new:|now available|meet)\b", re.I)
AGENTS = re.compile(r"\b(ai agents?|agents?|autonomous|copilot)\b", re.I)
SEGMENT = re.compile(r"\b(now serving|now supports?|built for (?:banks|enterprises?|healthcare|regulated)|"
                     r"new (?:vertical|segment|industry)|for (?:financial services|healthcare|regulated \w+|"
                     r"enterprise teams))\b", re.I)
MONEY = re.compile(r"\$\s?\d")
GTM_ROLE = re.compile(r"\b(revenue operations|revops|sales operations|gtm|go-to-market|sales development)\b", re.I)


def _first(blocks, pattern):
    return next((b for b in blocks if pattern.search(b)), None)


def _mock_analyze(ctx):
    company, page, added, removed = ctx["company"], ctx["page_type"], ctx["added"], ctx["removed"]
    text_blocks = added or removed

    def result(signal, confidence, evidence, summary, why, angle):
        return {"meaningful": True, "signal_type": signal, "confidence": confidence, "change_summary": summary,
                "why_it_matters": why, "outreach_angle": angle, "evidence": evidence,
                "reason_if_not_meaningful": None}

    ev = _first(added, FUNDING)
    if ev and (page == "news" or MONEY.search(ev)):
        return result("Funding Announcement", "High" if MONEY.search(ev) else "Medium", ev,
                      f"{company} announced new funding.",
                      "Fresh capital usually comes with a growth mandate and new budget for tooling and headcount.",
                      f"Reference the funding announcement and ask which growth priorities the new capital is funding.")
    if page in ("about", "news"):
        ev = _first(added, ROLE)
        if ev:
            return result("Leadership Change", "High", ev,
                          f"{company} added a new leader: {ev}",
                          "New leaders typically re-evaluate vendors and priorities in their first months.",
                          f"Reference the appointment ({ev}) and ask what the new leader's first priorities are.")
    ev = _first(added, PARTNER)
    if ev and page in ("news", "products"):
        return result("Major Partnership", "Medium", ev, f"{company} announced a partnership or integration.",
                      "Partnerships signal a new go-to-market channel or product direction.",
                      "Reference the partnership and ask how it changes their go-to-market plans.")
    ev = _first(added, EXPAND)
    if ev:
        return result("Market Expansion", "Medium", ev, f"{company} announced an expansion.",
                      "Expansion creates new teams, processes and tooling needs in the new market.",
                      "Reference the expansion and ask how they plan to ramp up locally.")
    ev = _first(added, SEGMENT)
    if ev:
        return result("Market Expansion", "Medium", ev, f"{company} is targeting a new customer segment.",
                      "A new target segment means new buyer personas, compliance needs and messaging, and usually a "
                      "new go-to-market motion.",
                      "Reference the new segment and ask how they plan to reach and win those buyers.")
    ev = _first(added, HIRING)
    if ev:
        if any(GTM_ROLE.search(b) for b in added):
            return result("Hiring / Growth Signal", "High", ev, f"{company} is hiring for revenue operations and GTM roles.",
                          "Hiring revenue operations and GTM roles shows the company is investing in its go-to-market "
                          "stack, data and processes.",
                          "Reference the hiring push and ask what GTM systems and workflows they are building out.")
        return result("Hiring / Growth Signal", "Medium", ev, f"{company} is signalling hiring or growth.",
                      "A hiring push shows where the company is investing.",
                      "Reference the hiring push and ask what they are scaling.")
    ev = _first(added, INITIATIVE)
    if ev and page == "news":
        return result("Strategic Initiative", "Medium", ev, f"{company} announced a strategic initiative.",
                      "Strategic initiatives tend to unlock budget and executive attention.",
                      "Reference the initiative and tie your offer to its business outcome.")
    if page == "pricing" and (any(MONEY.search(b) for b in added + removed) or (added and removed) or added):
        ev = _first(added, MONEY) or (added[0] if added else removed[0])
        return result("Pricing Change", "High" if added and removed else "Medium", ev,
                      f"{company} changed its pricing or packaging.",
                      "Pricing and packaging changes affect deal size, sales cycle and how buyers compare vendors.",
                      "Reference the packaging change and ask how it is affecting deal size and the sales cycle.")
    if page == "products" and added:
        intro = _first(added, INTRO)
        heading = next((b for b in added if len(b.split()) <= 8), added[0])
        name = next((m for m in (re.match(r"(?:introducing|meet|announcing)\s+(.+?)(?:[:,.—]|$)", b, re.I)
                                 for b in added) if m), None)
        label = name.group(1).strip() if name else heading
        category = AGENTS.search(" ".join(added))
        if intro or len(added) >= 2:
            return result("New Product Category" if category else "New Product Launch",
                          "High" if intro else "Medium", intro or added[0],
                          f"{company} launched {label}." if intro else f"{company} added new product content: {label}.",
                          "The company appears to be expanding its product portfolio" +
                          (" into autonomous AI agents, which suggests a new buyer persona and GTM motion." if category
                           else ", which may signal a new buyer persona and GTM motion."),
                          f"Reference the launch of {label} and ask how they plan to position it with existing customers "
                          f"versus new buyers.")
    return {"meaningful": False, "signal_type": None, "confidence": "Medium", "change_summary": "",
            "why_it_matters": "", "outreach_angle": "", "evidence": None,
            "reason_if_not_meaningful": "No commercial signal found; looks like wording or presentation change."}


# --------------------------------------------------------------------------- validation + routing

def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def validate(result, ctx):
    """Returns an error string, or None if the result is acceptable."""
    if not isinstance(result, dict) or not isinstance(result.get("meaningful"), bool):
        return "malformed result (meaningful missing)"
    if not result["meaningful"]:
        return None
    if result.get("signal_type") not in SIGNAL_TYPES:
        return f"unknown signal_type {result.get('signal_type')!r}"
    if result.get("confidence") not in CONFIDENCE:
        return f"invalid confidence {result.get('confidence')!r}"
    for key in ("change_summary", "why_it_matters", "outreach_angle"):
        if not result.get(key):
            return f"missing {key}"
    evidence = _norm(result.get("evidence"))
    if not evidence or not any(evidence in _norm(b) for b in ctx["added"] + ctx["removed"]):
        return "evidence not found in the changed text (possible hallucination)"
    return None


def analyze(ctx):
    """Returns (result, model_label). Raises on provider failure."""
    if config.llm_provider() == "claude":
        try:
            return _claude_analyze(ctx)
        except (ValueError, json.JSONDecodeError):          # bad JSON: one retry
            return _claude_analyze(ctx)
    return _mock_analyze(ctx), "mock-heuristic"


def route(result, error):
    """Returns (status, reason) for a validated analysis."""
    if error:
        return "rejected", error
    if not result["meaningful"]:
        return "ignored_llm", result.get("reason_if_not_meaningful") or "judged not meaningful"
    if result["confidence"] == "Low":
        return "review", "meaningful but low confidence: " + result["signal_type"]
    return "alert_ready", f"{result['signal_type']} ({result['confidence']})"


def process_pending(conn):
    """Analyze every change with status 'pending_llm'. Returns {status: count}."""
    rows = conn.execute(
        "SELECT ch.*, p.url, p.page_type, a.company_name, a.industry, a.priority FROM changes ch "
        "JOIN pages p ON p.id = ch.page_id JOIN accounts a ON a.id = p.account_id "
        "WHERE ch.status = 'pending_llm' ORDER BY ch.id").fetchall()
    counts = {}
    for row in rows:
        ctx = {"company": row["company_name"], "industry": row["industry"], "priority": row["priority"],
               "page_type": row["page_type"], "url": row["url"],
               "added": json.loads(row["added_blocks"]), "removed": json.loads(row["removed_blocks"])}
        if len(ctx["added"]) + len(ctx["removed"]) > BULK_LIMIT:
            status, reason = "review", f"bulk change ({len(ctx['added'])} added / {len(ctx['removed'])} removed): likely a redesign"
        else:
            try:
                result, model = analyze(ctx)
            except Exception as e:                                   # provider down, refusal, bad JSON twice
                status, reason = "review", f"LLM unavailable: {type(e).__name__}: {e}"
            else:
                status, reason = route(result, validate(result, ctx))
                db.save_analysis(conn, row["id"], result, model)
        db.set_change_status(conn, row["id"], status, reason)
        counts[status] = counts.get(status, 0) + 1
        print(f"  {status.upper():12} {row['url']}  [{reason}]")
    conn.commit()
    return counts
