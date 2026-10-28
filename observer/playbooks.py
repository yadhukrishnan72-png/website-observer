"""Email playbooks for the seller (Clay): one per kind of trigger.

Every first-touch email follows the same four beats:
  1. reference the specific change that was detected,
  2. say what it usually means for GTM, in one sentence,
  3. connect Clay to that problem or opportunity,
  4. close with one low-friction offer to show how Clay could support it.

Facts come only from the detected change (the evidence and the page text that was added or removed). Nothing is
invented: when a fact cannot be found the wording falls back to a cautious sentence. The Claude drafter gets the same
facts and the Clay angle as guidance; the stand-in drafter composes the email from these playbooks directly.
"""
import json
import re
import zlib

from . import seller

MIN_WORDS, MAX_WORDS = 70, 110

# Phrases that make a cold email read as templated, hyped or curiosity-bait. The validator rejects them.
BANNED = [
    "i hope this", "hope you're well", "i came across", "i wanted to", "reach out", "quick question", "quick chat",
    "quick call", "worth a quick", "worth a chat", "worth exploring", "15 minutes", "15 min", "hop on", "pick your brain",
    "touch base", "circle back", "just checking in", "curious", "game-changer", "game changer", "revolutionary",
    "cutting-edge", "cutting edge", "synergy", "supercharge", "unlock", "seamless", "best-in-class", "world-class",
    "leverage", "turnkey", "disrupt", "10x", "end-to-end", "holistic",
]

STOPWORDS = {"which", "their", "there", "about", "other", "these", "those", "would", "could", "should", "where",
             "while", "after", "before", "company", "page", "pages", "with", "across", "being", "using"}


# --------------------------------------------------------------------------- small helpers

def blocks(ctx, key):
    """The changed page text ('added' or 'removed') from either a list or the JSON stored in the database."""
    value = ctx.get(key)
    if value is None:
        raw = ctx.get(f"{key}_blocks")
        value = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return list(value)


def lens(title):
    """'build' for operators and builders, 'lead' for revenue and growth leaders. Changes the wording, not the facts."""
    t = (title or "").lower()
    return "lead" if any(k in t for k in ("chief", "growth", "vp", "vice president")) else "build"


def pick(options, seed):
    return options[zlib.crc32(seed.encode("utf-8")) % len(options)]


def indef(phrase):
    """'a' or 'an', by sound: 'an $18 million Series A', 'an $80 million round', 'a $30 million Series B'."""
    amount = re.match(r"\$\s?(\d+)", phrase)
    if amount:
        vowel = amount.group(1)[0] == "8" or amount.group(1) in ("11", "18")
    else:
        vowel = phrase[:1].lower() in "aeiou"
    return ("an " if vowel else "a ") + phrase


def poss(name):
    return name + ("'" if name.endswith("s") else "'s")


def join_list(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def trim(text, words):
    parts = re.sub(r"\s+", " ", text or "").strip().split()
    return " ".join(parts[:words]).rstrip(",.;:— ")


def first(pattern, text, flags=0):
    m = re.search(pattern, text or "", flags)
    return m.group(1).strip() if m else None


def search(pattern, texts, flags=0):
    """First match in any one of the texts. Searching block by block keeps a match from running across two blocks."""
    return next((v for v in (first(pattern, x, flags) for x in texts) if v), None)


# --------------------------------------------------------------------------- which playbook, and the facts in it

SEGMENT_RE = re.compile(r"now serving|for (financial services|healthcare|regulated|enterprise teams)|built for "
                        r"(banks|enterprises?|healthcare|regulated)|new (vertical|segment|industry)", re.I)
GEO_RE = re.compile(r"expands?|expansion|new (office|market|region|headquarters)|\boffice\b", re.I)
ROLE_RE = re.compile(r"\b(manager|engineer|head of|director|lead|specialist|analyst|developer|architect|vp)\b", re.I)
GTM_RE = re.compile(r"revenue operations|revops|sales operations|gtm|go-to-market|sales development", re.I)


def key_for(signal_type, text):
    if signal_type in ("New Product Launch", "New Product Category"):
        return "product"
    if signal_type == "Market Expansion":
        return "icp" if SEGMENT_RE.search(text) and not GEO_RE.search(text) else "geo"
    if signal_type == "Strategic Initiative":
        return "enterprise" if re.search(r"\benterprise\b", text, re.I) else "initiative"
    return {"Pricing Change": "pricing", "Leadership Change": "exec", "Funding Announcement": "funding",
            "Major Partnership": "partnership", "Hiring / Growth Signal": "hiring"}.get(signal_type, "initiative")


def facts_for(key, company, evidence, added, removed):
    """The concrete details the email may use. Anything not found stays None."""
    evidence = evidence or ""
    text = " ".join([evidence] + added)
    f = {"quote": trim(evidence, 16)}
    if key == "hiring":
        f["area"] = first(r"hiring across (.+?)\.?$", evidence, re.I)
        roles = [b for b in added if len(b.split()) <= 6 and ROLE_RE.search(b)]
        f["role"] = roles[0] if roles else None
        f["gtm"] = bool(GTM_RE.search(text))
    elif key == "product":
        name = first(r"^(?:introducing|meet|announcing)\s+(.+?)(?:[:,.—]|$)", evidence, re.I)
        if not name:
            name = next((first(r"^(?:introducing|meet|announcing)\s+(.+?)(?:[:,.—]|$)", b, re.I) for b in added
                         if re.match(r"(?:introducing|meet|announcing)\s", b, re.I)), None)
        desc = search(r"^(?:introducing|meet|announcing)\s+[^:]+:\s*(.+)$", added, re.I)
        if not desc:
            desc = next((b for b in added if len(b.split()) > 6 and b != evidence), None)
        if desc:                                       # keep the claim, drop the trailing benefit clause
            desc = re.split(r"\s+(?:without|so that|so)\s+", desc)[0]
        f["name"], f["desc"] = name, (trim(desc, 16) if desc else None)
        f["heading"] = next((b for b in added if len(b.split()) <= 8), None)
    elif key == "funding":
        f["amount"] = first(r"(\$\s?\d[\d,.]*\s*(?:million|billion|m|b)\b)", evidence, re.I)
        f["round"] = first(r"(Series\s+[A-F]\b|seed round)", evidence, re.I)
    elif key == "exec":
        m = re.match(r"^([A-Z][\w'.-]+(?: [A-Z][\w'.-]+)+),\s*(.+)$", evidence)
        f["name"], f["title"] = (m.group(1), m.group(2).strip()) if m else (None, None)
        matches = (re.match(r"^([A-Z][\w'.-]+(?: [A-Z][\w'.-]+)+),\s*" + re.escape(f["title"]) + r"$", b)
                   for b in removed if f["title"])
        old = next((m for m in matches if m), None)
        f["old"] = old.group(1) if old else None
    elif key == "geo":
        f["place"] = first(r"(?:into|in)\s+([A-Z][\w]+(?: [A-Z][\w]+)*?)(?:\s+with|\.|,|$)", evidence)
        f["city"] = search(r"new\s+([A-Z][\w]+)\s+office", [evidence] + added)
    elif key == "pricing":
        money = re.compile(r"\$\s?\d[\d,.]*")
        unit = lambda b: first(r"\$\s?\d[\d,.]*\s*(per [a-z ]+?)(?:\.|,|$)", b)
        old_b = next((b for b in removed if money.search(b)), None)
        new_b = next((b for b in added if money.search(b) and (not old_b or unit(b) == unit(old_b))), None)
        f["old"], f["new"] = (money.search(old_b).group(0), money.search(new_b).group(0)) if old_b and new_b else (None, None)
        f["unit"] = unit(new_b) if new_b else None
        tier = next((added[i] for i in range(len(added) - 1) if len(added[i].split()) <= 3
                     and money.search(added[i + 1]) and added[i + 1] != new_b), None)
        f["tier"] = tier
        tier_p = next((money.search(added[i + 1]).group(0) for i in range(len(added) - 1) if added[i] == tier), None)
        f["tier_price"] = tier_p
    elif key == "icp":
        seg = first(r"\bfor ([A-Z][\w ]+)$", evidence)
        f["segment"] = seg.lower() if seg else None
        f["audience"] = search(r"built for ([^.]+?)(?:\.|$)", [evidence] + added)
        f["regulated"] = bool(re.search(r"regulated|compliance|audit", text, re.I))
    elif key == "partnership":
        f["partner"] = search(r"partnership with ([A-Z][\w&]*(?: [A-Z][\w&]*){0,3})(?:\.|,|$)", [evidence] + added)
    elif key == "enterprise":
        det = next((first(r"^((?:A|An|The)\s+.+?) will serve", b) for b in added if " will serve" in b), None)
        f["details"] = det[0].lower() + det[1:] if det else None
    return f


# --------------------------------------------------------------------------- the playbooks

def _hiring_ref(c, f):
    if f["area"]:
        role = f", including {indef(f['role'])}" if f["role"] else ""
        return f"Saw {c} is hiring across {f['area']}{role}."
    if f["role"]:
        return f"Saw {c} is hiring for {indef(f['role'])}."
    return f'Saw a hiring update on {poss(c)} careers page: "{f["quote"]}".'


def _product_ref(c, f):
    if f["name"]:
        return f"Saw {c} just introduced {f['name']}" + (f", {f['desc']}." if f["desc"] else ".")
    if f["heading"]:
        return f'Saw {c} add "{f["heading"]}" to its products page.'
    return f'Saw a product update on {poss(c)} site: "{f["quote"]}".'


def _funding_ref(c, f):
    if f["amount"] and f["round"]:
        return f"Saw {c} announced {indef(f['amount'] + ' ' + f['round'])}."
    if f["amount"]:
        return f"Saw {c} announced new funding of {f['amount']}."
    if f["round"]:
        return f"Saw {c} announced {indef(f['round'])}."
    return f"Saw {c} announced new funding."


def _exec_ref(c, f):
    if f["name"]:
        before = f", where {f['old']} was listed before" if f["old"] else ""
        return f"Saw {f['name']} is now listed as {f['title']} at {c}{before}."
    return f'Saw a leadership update on {poss(c)} About page: "{f["quote"]}".'


def _geo_ref(c, f):
    if f["place"] and f["city"]:
        return f"Saw {c} is expanding into {f['place']} with a new {f['city']} office."
    if f["place"]:
        return f"Saw {c} is expanding into {f['place']}."
    return f'Saw {c} announce an expansion: "{f["quote"]}".'


def _pricing_ref(c, f):
    parts = []
    if f["old"] and f["new"]:
        parts.append(f"one plan moved from {f['old']} to {f['new']}" + (f" {f['unit']}" if f["unit"] else ""))
    if f["tier"]:
        parts.append(f"a new {f['tier']} tier appeared" + (f" at {f['tier_price']}" if f["tier_price"] else ""))
    return f"Noticed {c} updated its pricing: {' and '.join(parts)}." if parts else f"Noticed {c} updated its pricing page."


def _icp_ref(c, f):
    if f["segment"] and f["audience"]:
        return f"Saw {c} added a {f['segment']} page, aimed at {f['audience']}."
    if f["segment"]:
        return f"Saw {c} added a page for {f['segment']}."
    return f'Saw a new segment page on {poss(c)} site: "{f["quote"]}".'


def _partner_ref(c, f):
    return f"Saw {c} announced a partnership with {f['partner']}." if f["partner"] else f"Saw {c} announce a new partnership."


def _enterprise_ref(c, f):
    if f["details"]:
        return f"Saw {c} announced an enterprise initiative, including {f['details']}."
    return f"Saw {c} announce an enterprise-focused initiative."


def _initiative_ref(c, f):
    return f'Saw {c} announce a strategic initiative: "{f["quote"]}".'


PLAYBOOKS = {
    "hiring": dict(
        label="Hiring push", ref=_hiring_ref,
        angle="GTM stack complexity grows with RevOps and GTM headcount; Clay is the build layer for data and agentic workflows.",
        impl=["That's usually when the GTM stack gets more complex: more data sources, more workflows, more plays to keep running.",
              "New RevOps and GTM hires often inherit a stack that grew tool by tool, with data in one place and workflows in another."],
        fit={"build": "That's where Clay fits: it gives GTM teams one place to build the data and agentic workflows behind those plays, so new hires inherit workflows instead of spreadsheets.",
             "lead": "That's where Clay fits: it helps GTM teams build the data and agentic workflows behind those motions without adding more manual work."},
        cta={"build": "If that's part of what you're building at {c}, happy to show you what that could look like.",
             "lead": "If that's part of the plan at {c}, happy to walk you through what it could look like for your team."},
        subject=lambda c, f: f"{poss(c)} {f['area']} hiring" if f["area"] else f"Hiring at {c}",
        short=lambda f: f"is hiring across {f['area']}" if f["area"] else "is hiring"),
    "product": dict(
        label="Product launch", ref=_product_ref,
        angle="A new product needs a new audience: Clay sources and enriches the accounts that fit it and tailors outreach with research agents.",
        impl=["A new product usually means a new audience to find and a new story to tell them, often before the target data exists.",
              "Launches tend to send reps after a new buyer, which means new account lists, new research and new messaging."],
        fit={"build": "Clay can help source and enrich the accounts that fit {name}, then use research agents to tailor outreach to each account's situation, all from one workflow.",
             "lead": "Clay helps GTM teams find the accounts that fit a new product and run plays on them from day one, without hand-built lists."},
        cta={"build": "If you're mapping who {name} is for, happy to show you how Clay could support that.",
             "lead": "If you're planning the go-to-market for {name}, happy to show how Clay could support it."},
        subject=lambda c, f: f"{f['name']} at {c}" if f["name"] else f"New product at {c}",
        short=lambda f: f"introduced {f['name']}" if f["name"] else "added a new product"),
    "funding": dict(
        label="Funding", ref=_funding_ref,
        angle="Funding raises pipeline targets faster than headcount; Clay enriches and scores accounts so reps start with the best fits and plays become repeatable.",
        impl=["Fresh funding usually brings bigger pipeline targets and pressure to hit them without scaling headcount at the same pace.",
              "After a raise, outbound usually has to grow quickly, and the data and process behind it get stretched first, with lists built for a smaller team."],
        fit={"build": "Clay helps GTM teams enrich and score target accounts so reps start with the best fits, then turn the plays that work into repeatable workflows.",
             "lead": "Clay helps GTM teams find and prioritize the right accounts and run repeatable plays on them, so scaling outbound doesn't depend on more manual research."},
        cta={"build": "If you're scaling outbound at {c}, happy to show you how Clay could fit into that plan.",
             "lead": "If scaling pipeline is the plan at {c}, happy to show you how Clay could help the team get there."},
        subject=lambda c, f: f"{poss(c)} {f['round']}" if f["round"] else f"{poss(c)} new funding",
        short=lambda f: "announced new funding" + (f" ({', '.join(x for x in (f['amount'], f['round']) if x)})" if f["amount"] or f["round"] else "")),
    "exec": dict(
        label="Executive change", ref=_exec_ref,
        angle="A new leader reviews pipeline data and tooling; Clay puts data, scoring and plays in one place so changes are edits, not rebuilds.",
        impl=["A new revenue leader often reviews pipeline data and tooling in the first few months, and the ops team gets asked for answers quickly.",
              "New leadership usually brings new questions about coverage, routing and reporting, and someone has to answer them fast."],
        fit={"build": "Clay lets GTM teams bring data, scoring and plays into one place, so changing how pipeline gets built means editing a workflow, not rebuilding the stack.",
             "lead": "Clay gives GTM teams one place for data, account scoring and plays, so a new leader can see how pipeline gets built and change it quickly."},
        cta={"build": "If a review of the stack is coming at {c}, happy to show you how Clay could help.",
             "lead": "If that's on the list at {c}, happy to walk through what Clay could look like for the team."},
        subject=lambda c, f: f"New {f['title']} at {c}" if f["title"] else f"Leadership update at {c}",
        short=lambda f: f"lists {f['name']} as {f['title']}" if f["name"] else "has a leadership update"),
    "geo": dict(
        label="Geographic expansion", ref=_geo_ref,
        angle="A new region needs account lists and local data coverage; Clay's multi-provider waterfall sources and enriches accounts there.",
        impl=["A new region usually means building account lists, contacts and local data coverage from scratch, which takes time away from selling.",
              "Entering a new market tends to start with a gap: who to target, and whether the data to reach them exists."],
        fit={"build": "Clay pulls from many data providers in one waterfall, so teams can source and enrich accounts in {place} without stitching lists together by hand.",
             "lead": "Clay helps GTM teams source and enrich accounts in a new region from many data providers at once, and start running plays on them quickly."},
        cta={"build": "If you're building the account list for {place}, happy to show how Clay could handle it.",
             "lead": "If {place} is a priority for the team at {c}, happy to show you how Clay could help."},
        subject=lambda c, f: f"{c} in {f['place']}" if f["place"] else f"{poss(c)} expansion",
        short=lambda f: f"is expanding into {f['place']}" if f["place"] else "announced an expansion"),
    "pricing": dict(
        label="Pricing change", ref=_pricing_ref,
        angle="Repackaging shifts which accounts fit which plan; Clay enriches and scores accounts against the new tiers and triggers upgrade plays.",
        impl=["Repackaging usually means re-segmenting accounts and working out who is ready to move up a tier.",
              "Pricing changes often shift which accounts fit which plan, and sales has to relearn that quickly."],
        fit={"build": "Clay can enrich and score your accounts against the new tiers, then trigger plays for the ones that look ready to upgrade.",
             "lead": "Clay helps GTM teams see which accounts fit each tier and run plays on the right ones, without rebuilding lists by hand."},
        cta={"build": "If you're working through that segmentation at {c}, happy to show how Clay could support it.",
             "lead": "If that's part of the rollout at {c}, happy to show what Clay could do for it."},
        subject=lambda c, f: f"{poss(c)} new pricing tiers" if f["tier"] else f"{poss(c)} pricing update",
        short=lambda f: "updated its pricing"),
    "icp": dict(
        label="New ICP", ref=_icp_ref,
        angle="A new segment needs a new target list and different qualification criteria; Clay sources the companies, researches the criteria and scores fit.",
        impl=["A new segment usually means a new target list, new buying personas and criteria you haven't scored before.",
              "Selling into a new segment often starts with research: which companies fit, and what makes them different."],
        fit={"build": "Clay can source companies in that segment, have research agents check the criteria that matter{reg}, and score them for your reps.",
             "lead": "Clay helps GTM teams build the target list for a new segment, research each account against what matters there, and hand reps the best fits."},
        cta={"build": "If you're building the list for {segment} at {c}, happy to show you how Clay could handle it.",
             "lead": "If {segment} is a focus for the team at {c}, happy to walk through how Clay could support it."},
        subject=lambda c, f: f"{c} for {f['segment']}" if f["segment"] else f"A new segment at {c}",
        short=lambda f: f"added a {f['segment']} page" if f["segment"] else "added a new segment page"),
    "partnership": dict(
        label="Strategic partnership", ref=_partner_ref,
        angle="A partnership needs shared-account identification and a handoff; Clay matches partner and customer accounts to CRM data and triggers plays on overlaps.",
        impl=["A partnership usually creates a new motion: shared accounts to identify, and a clear handoff between the two teams.",
              "Partnerships often depend on knowing which accounts overlap, and that list rarely exists on day one, so someone ends up building it by hand."],
        fit={"build": "Clay can match partner and customer accounts against your CRM data and trigger plays on the overlaps, so co-selling doesn't rest on manual list work.",
             "lead": "Clay helps GTM teams find the accounts where a partnership applies and run plays on them, with the data and workflows in one place."},
        cta={"build": "If joint outreach is part of the plan with {partner}, happy to show how Clay could support it.",
             "lead": "If that's part of the plan with {partner}, happy to walk through what Clay could look like for the team."},
        subject=lambda c, f: f"{c} and {f['partner']}" if f["partner"] else f"{poss(c)} new partnership",
        short=lambda f: f"announced a partnership with {f['partner']}" if f["partner"] else "announced a partnership"),
    "enterprise": dict(
        label="Enterprise GTM push", ref=_enterprise_ref,
        angle="Selling upmarket means researching accounts and mapping buying groups; Clay researches enterprise accounts, finds contacts and prioritizes by signals.",
        impl=["Selling upmarket usually means researching each target account and mapping the buying group, which doesn't scale by hand.",
              "Enterprise deals tend to involve many stakeholders per account, so research and contact data become the bottleneck."],
        fit={"build": "Clay can research enterprise accounts with AI agents, find and enrich contacts across the buying group, and prioritize accounts by signals.",
             "lead": "Clay helps GTM teams research enterprise accounts, find the right people at each, and prioritize where to start."},
        cta={"build": "If the new team is building its account plans, happy to show what that could look like in Clay.",
             "lead": "If that's part of the push at {c}, happy to walk through how Clay could support the team."},
        subject=lambda c, f: f"{poss(c)} enterprise push",
        short=lambda f: "announced an enterprise initiative"),
    "initiative": dict(
        label="Strategic initiative", ref=_initiative_ref,
        angle="Initiatives need go-to-market plans and data on where to start; Clay turns them into sourced, researched and launched plays.",
        impl=["Initiatives like that usually need a go-to-market plan behind them, and data on which accounts to start with.",
              "A new initiative often turns into new targets for sales, which means new lists and new research."],
        fit={"build": "Clay helps GTM teams turn an initiative into plays: source accounts, research them with AI agents and launch outreach from one workflow.",
             "lead": "Clay helps GTM teams turn a new initiative into plays on the right accounts, with the data and workflows in one place."},
        cta={"build": "If that's in motion at {c}, happy to show how Clay could support it.",
             "lead": "If that's a priority at {c}, happy to walk through what Clay could look like for the team."},
        subject=lambda c, f: f"{poss(c)} new initiative",
        short=lambda f: "announced a strategic initiative"),
    "combined": dict(
        label="Combined growth signals", ref=None,
        angle="Several growth moves at once scatter GTM data and workflows; Clay is one place for data, scoring and agentic workflows.",
        impl=["That mix usually means the GTM engine is being scaled and rebuilt at once, with more tools and processes to keep consistent.",
              "Several moves at once often leave GTM data and workflows spread across more tools than anyone planned."],
        fit={"build": "Clay gives GTM teams one place for data, scoring and agentic workflows, so the stack grows with the team instead of adding more tools.",
             "lead": "Clay gives GTM teams one place to run data, scoring and plays, so growth doesn't mean another tool for every new process."},
        cta={"build": "If that's the picture at {c}, happy to show you how Clay could be the backbone for it.",
             "lead": "If that's the plan at {c}, happy to walk through how Clay could support the team."},
        subject=None, short=None),
}

# Second wording for the Clay paragraph and the offer; compose() picks one of the two per account.
FIT_B = {
    "hiring": {"build": "Clay is built for that layer: one place to pull in data and run the agentic workflows behind each play, so the team isn't maintaining it all by hand.",
               "lead": "Clay helps GTM teams run the data and agentic workflows behind their plays in one place, so adding headcount doesn't mean adding more manual work."},
    "product": {"build": "Clay can source the companies that fit {name} and enrich them from many data providers, then research each one so outreach reflects their situation.",
                "lead": "Clay helps GTM teams build the account list for a new product and launch plays on it, with the data and research done in one workflow."},
    "funding": {"build": "Clay lets GTM teams source, enrich and score accounts in one workflow, so reps spend their time on the best-fit accounts and the plays that work get reused.",
                "lead": "Clay helps GTM teams prioritize accounts and run repeatable plays on them, so a bigger target doesn't mean proportionally more manual research."},
    "exec": {"build": "Clay brings account data, scoring and outreach plays onto one canvas, so when priorities shift the team edits a play instead of re-plumbing tools.",
             "lead": "Clay helps GTM teams see and adjust how pipeline gets built from one place, which keeps a stack review more straightforward."},
    "geo": {"build": "Clay checks many data providers in sequence, which usually gives better coverage when sourcing and enriching accounts in {place} than any single source.",
            "lead": "Clay helps GTM teams build account lists in a new region and start running plays on them, with data from many providers in one place."},
    "pricing": {"build": "Clay can enrich accounts with the firmographic data that matters for each tier, score them, and flag the ones worth a plan-change conversation.",
                "lead": "Clay helps GTM teams match accounts to the right plan and run plays on them, with the data and scoring in one place."},
    "icp": {"build": "Clay can build that list, enrich each company, and have research agents check what makes a segment different{reg}, so reps get scored accounts, not raw lists.",
            "lead": "Clay helps GTM teams stand up a target list for a new segment quickly, with research and scoring done per account rather than by hand."},
    "partnership": {"build": "Clay can pull in partner account data, match it against your CRM, and trigger plays on the overlaps, so shared accounts get worked, not just listed.",
                    "lead": "Clay helps GTM teams turn a partnership into plays on shared accounts, with the matching, data and workflows in one place."},
    "enterprise": {"build": "Clay can run AI research on each enterprise account, enrich the people across the buying group, and score accounts so the new team knows where to start.",
                   "lead": "Clay helps GTM teams research enterprise accounts, map the right contacts and decide where to start, without doing it account by account by hand."},
    "initiative": {"build": "Clay lets GTM teams source accounts, research them with AI agents and run outreach plays from one canvas.",
                   "lead": "Clay helps GTM teams put data and plays behind a new initiative, from sourcing accounts to launching outreach."},
    "combined": {"build": "Clay lets GTM teams run enrichment, scoring and agentic workflows in one place, so a growing team isn't managing a different tool for each step.",
                 "lead": "Clay helps GTM teams scale data, scoring and plays from one place, so growth doesn't mean another tool for every new process."},
}
CTA_B = {
    "hiring": {"build": "If you're the one building that out at {c}, happy to walk through what it could look like.",
               "lead": "If that's the direction at {c}, happy to show how Clay could support your team."},
    "product": {"build": "If you're working out who {name} is for, happy to show how Clay could help find them.",
                "lead": "If {name} is a priority for the team at {c}, happy to show what Clay could do for it."},
    "funding": {"build": "If outbound is expanding at {c}, happy to show how Clay could fit into the plan for the team.",
                "lead": "If growing pipeline is a priority at {c}, happy to walk through how Clay could help the team get there."},
    "exec": {"build": "If you're pulling together what a stack review would need at {c}, happy to show how Clay could help.",
             "lead": "If a review of how pipeline gets built is coming at {c}, happy to show you what Clay could do."},
    "geo": {"build": "If you're sourcing accounts for {place} at {c}, happy to show how Clay could handle that for the team.",
            "lead": "If {place} is on the plan at {c}, happy to walk through how Clay could support it."},
    "pricing": {"build": "If you're mapping accounts to the new tiers at {c}, happy to show how Clay could do that.",
                "lead": "If that's being worked out at {c}, happy to walk through how Clay could support it."},
    "icp": {"build": "If that list is on your plate at {c}, happy to show how Clay could build it.",
            "lead": "If that segment is part of the plan at {c}, happy to show what Clay could do for the team."},
    "partnership": {"build": "If shared-account lists are part of the work with {partner}, happy to show how Clay could help.",
                    "lead": "If joint selling with {partner} is the plan at {c}, happy to walk through how Clay could support the team."},
    "enterprise": {"build": "If the team is building account plans now, happy to show how that could work in Clay.",
                   "lead": "If upmarket is a priority at {c}, happy to walk through how Clay could support the team."},
    "initiative": {"build": "If that's moving forward at {c}, happy to show how Clay could help.",
                   "lead": "If that's a focus for the team at {c}, happy to show what Clay could do."},
    "combined": {"build": "If that's what's happening at {c}, happy to show you how Clay could hold it together.",
                 "lead": "If that matches the plan at {c}, happy to walk through how Clay could support the team."},
}
for _key, _pb in PLAYBOOKS.items():
    for _lens in ("build", "lead"):
        _pb["fit"][_lens] = [_pb["fit"][_lens], FIT_B[_key][_lens]]
        _pb["cta"][_lens] = [_pb["cta"][_lens], CTA_B[_key][_lens]]

LEAD_INS = ["Saw", "Noticed", "Spotted"]

COMBINED_LABEL = {"hiring": "hiring", "product": "a launch", "funding": "funding", "exec": "a leadership change",
                  "geo": "expansion", "pricing": "new pricing", "icp": "a new segment", "partnership": "a partnership",
                  "enterprise": "an enterprise push", "initiative": "a new initiative"}


# --------------------------------------------------------------------------- composing the email

def _signals(ctx):
    """[(key, facts)] for this change and any other signals already alerted for the same account."""
    company = ctx["company"]
    items = []
    for o in ctx.get("others") or []:
        ob, orm = blocks(o, "added"), blocks(o, "removed")
        k = key_for(o["signal_type"], " ".join([o.get("evidence") or ""] + ob + orm))
        items.append((k, facts_for(k, company, o.get("evidence"), ob, orm)))
    added, removed = blocks(ctx, "added"), blocks(ctx, "removed")
    k = key_for(ctx["signal_type"], " ".join([ctx.get("evidence") or ""] + added + removed))
    items.append((k, facts_for(k, company, ctx.get("evidence"), added, removed)))
    seen, unique = set(), []
    for k, f in items:                                  # one entry per kind of signal, oldest first
        if k not in seen:
            seen.add(k); unique.append((k, f))
    return unique


def compose(ctx, choice=None):
    """Returns ({'subject', 'body'}, notes). notes is the internal analysis: signal, Clay angle, evidence, source.
    choice=(implication, fit, offer, lens) forces one wording; tests use it to check every combination."""
    company, signals = ctx["company"], _signals(ctx)
    first_name = ctx["contact_name"].split()[0]
    rep = (ctx.get("owner") or "").split()[0] or "the team"
    lens_ = lens(ctx.get("contact_title"))
    if len(signals) > 1:
        key, facts = "combined", None
        phrases = [PLAYBOOKS[k]["short"](f) for k, f in signals]
        count = {2: "two", 3: "three"}.get(len(phrases), "several")
        ref = f"Saw {count} changes at {company} recently: it {join_list(phrases)}."
        labels = [COMBINED_LABEL[k] for k, _ in signals]
        subject = f"{company}: {join_list(labels)}"
        fill = {"c": company}
    else:
        key, facts = signals[0]
        pb = PLAYBOOKS[key]
        ref = pb["ref"](company, facts)
        subject = pb["subject"](company, facts)
        fill = {"c": company, "name": facts.get("name") or "the new product", "place": facts.get("place") or "that region",
                "segment": facts.get("segment") or "that segment", "partner": facts.get("partner") or "that partner",
                "reg": ", such as regulatory requirements" if facts.get("regulated") else ""}
    pb = PLAYBOOKS[key]
    seed = f"{company}|{key}"
    if choice:
        lens_ = choice[3]
        impl, fit, cta = pb["impl"][choice[0]], pb["fit"][lens_][choice[1]].format(**fill), pb["cta"][lens_][choice[2]].format(**fill)
    else:
        impl = pick(pb["impl"], seed)
        fit = pick(pb["fit"][lens_], seed + "|fit").format(**fill)
        cta = pick(pb["cta"][lens_], seed + "|cta").format(**fill)
    ref = re.sub(r"^(Saw|Noticed) ", pick(LEAD_INS, seed + "|lead") + " ", ref)
    body = f"Hi {first_name},\n\n{ref}\n\n{impl}\n\n{fit}\n\n{cta}\n\nBest,\n{rep}\n{seller.NAME}"
    notes = {"signal": ctx["signal_type"], "playbook": pb["label"], "persona_lens": lens_, "contact": ctx["contact_name"],
             "contact_title": ctx.get("contact_title"), "clay_angle": pb["angle"], "evidence": ctx.get("evidence"),
             "source_url": ctx.get("url"), "also_on_account": [s["signal_type"] for s in ctx.get("others") or []],
             "facts": {k: v for k, v in (facts or {}).items() if v and k not in ("quote", "heading")},
             "word_count": len(body.split())}
    return {"subject": subject, "body": body}, notes


def guidance(ctx):
    """Playbook guidance for the Claude drafter: the facts it may use and the Clay angle for this signal."""
    draft, notes = compose(ctx)
    lines = [f"Trigger: {notes['playbook']} ({ctx['signal_type']}) at {ctx['company']}",
             f"Contact: {ctx['contact_name']}, {ctx.get('contact_title')} (write for a {notes['persona_lens']}er's concerns)",
             f"Evidence from the page: {ctx.get('evidence')}", f"Facts you may use: {json.dumps(notes['facts'])}",
             f"Clay angle for this trigger: {notes['clay_angle']}"]
    if notes["also_on_account"]:
        lines.append("Other signals on this account (mention them together): " + ", ".join(notes["also_on_account"]))
    lines.append("Reference sentence to adapt, not copy: " + draft["body"].split("\n\n")[1])
    return "\n".join(lines)


def grounding_words(ctx):
    """Distinctive words from the detected change. A good email reuses at least one."""
    texts = [ctx.get("evidence") or ""] + blocks(ctx, "added")
    for o in ctx.get("others") or []:
        texts += [o.get("evidence") or ""] + blocks(o, "added")
    company_words = set(re.findall(r"[a-z]{4,}", ctx["company"].lower()))
    words = {w for t in texts for w in re.findall(r"[a-z]{5,}", t.lower())} - STOPWORDS - company_words
    return words


def source_text(ctx):
    """Everything an email's numbers and facts may legitimately come from."""
    parts = [ctx.get("evidence") or "", ctx.get("change_summary") or "", ctx.get("why_it_matters") or "",
             ctx.get("outreach_angle") or ""] + blocks(ctx, "added") + blocks(ctx, "removed")
    for o in ctx.get("others") or []:
        parts += [o.get("evidence") or ""] + blocks(o, "added") + blocks(o, "removed")
    return " ".join(parts)
