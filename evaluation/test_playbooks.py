"""Tests for the email logic: facts are pulled from the detected change, every playbook produces a valid email, and the
validator rejects the failure modes it exists for.

    python -m evaluation.test_playbooks
"""
import sys

from observer import outreach, playbooks

COMPANY = "Acme AI"
CONTACT = {"contact_name": "Jordan Lee", "contact_title": "Head of Revenue Operations", "owner": "Yedhu"}
failures = []


def check(name, condition, detail=""):
    print(f"  {'PASS' if condition else 'FAIL'}  {name}" + (f": {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def ctx(signal, evidence, added=(), removed=(), **extra):
    return dict(company=COMPANY, url="http://localhost:8000/acme-ai/x.html", signal_type=signal, evidence=evidence,
                added=list(added) or [evidence], removed=list(removed), change_summary="s", why_it_matters="w",
                outreach_angle="a", **CONTACT, **extra)


CASES = {
    "hiring": ctx("Hiring / Growth Signal", "We're hiring across revenue operations and GTM engineering",
                  ["We're hiring across revenue operations and GTM engineering", "Head of Revenue Operations",
                   "Own revenue systems and reporting. Hybrid, Austin.", "GTM Engineer"]),
    "product": ctx("New Product Category", "Introducing Acme Agents",
                   ["Introducing Acme Agents", "Introducing Acme Agents: autonomous AI agents that research accounts, "
                    "draft outreach and update your CRM without manual work."]),
    "funding": ctx("Funding Announcement", "Acme AI raises $30 million Series B",
                   ["Acme AI raises $30 million Series B", "The funding will accelerate product development."]),
    "exec": ctx("Leadership Change", "Dana Okoye, Chief Revenue Officer", ["Dana Okoye, Chief Revenue Officer"],
                ["Casey Tanaka, Chief Revenue Officer"]),
    "geo": ctx("Market Expansion", "Acme AI expands into Europe with a new Dublin office",
               ["Acme AI expands into Europe with a new Dublin office", "The new office will serve customers."]),
    "pricing": ctx("Pricing Change", "$24 per user per month. Core features for small teams.",
                   ["$24 per user per month. Core features for small teams.", "Scale",
                    "$59 per user per month. Priority onboarding."], ["$19 per user per month. Core features for small teams."]),
    "icp": ctx("Market Expansion", "Acme AI for Financial Services",
               ["Acme AI for Financial Services", "Now serving regulated financial institutions with audit-ready "
                "controls built for banks and insurers."]),
    "partnership": ctx("Major Partnership", "Acme AI announces a partnership with Northstar Cloud",
                       ["Acme AI announces a partnership with Northstar Cloud", "The partnership brings data into workflows."]),
    "enterprise": ctx("Strategic Initiative", "Acme AI launches an enterprise strategic initiative",
                      ["Acme AI launches an enterprise strategic initiative", "A new enterprise sales team and a dedicated "
                       "security review program will serve large customers."]),
}

print("Facts are taken from the detected change")
facts = {k: playbooks.facts_for(k, COMPANY, c["evidence"], c["added"], c["removed"]) for k, c in CASES.items()}
check("hiring: area and first role", facts["hiring"]["area"] == "revenue operations and GTM engineering"
      and facts["hiring"]["role"] == "Head of Revenue Operations", str(facts["hiring"]))
check("product: name and description without the benefit clause", facts["product"]["name"] == "Acme Agents"
      and facts["product"]["desc"].endswith("update your CRM"), str(facts["product"]))
check("funding: amount and round", facts["funding"]["amount"] == "$30 million" and facts["funding"]["round"] == "Series B")
check("exec: new leader, title and previous listing", (facts["exec"]["name"], facts["exec"]["title"], facts["exec"]["old"])
      == ("Dana Okoye", "Chief Revenue Officer", "Casey Tanaka"), str(facts["exec"]))
check("geo: place and city", (facts["geo"]["place"], facts["geo"]["city"]) == ("Europe", "Dublin"), str(facts["geo"]))
check("pricing: old and new price, new tier", (facts["pricing"]["old"], facts["pricing"]["new"], facts["pricing"]["tier"],
      facts["pricing"]["tier_price"]) == ("$19", "$24", "Scale", "$59"), str(facts["pricing"]))
check("icp: segment and audience", (facts["icp"]["segment"], facts["icp"]["audience"]) == ("financial services",
      "banks and insurers"), str(facts["icp"]))
check("partnership: partner stops at the end of the name", facts["partnership"]["partner"] == "Northstar Cloud",
      str(facts["partnership"]))
check("enterprise: details keep their article", facts["enterprise"]["details"] ==
      "a new enterprise sales team and a dedicated security review program", str(facts["enterprise"]))

print("\nEvery playbook writes a valid, differentiated email")
bodies, fits = {}, set()
for k, c in CASES.items():
    d, notes = playbooks.compose(dict(c, contact_name=CONTACT["contact_name"], contact_title=CONTACT["contact_title"]))
    full = dict(c)
    error = outreach.validate(d, full)
    check(f"{k}: passes validation ({notes['word_count']} words)", error is None, str(error))
    bodies[k] = d["body"]
    fits.add(d["body"].split("\n\n")[3])
check("each trigger gets its own Clay paragraph", len(fits) == len(CASES), f"{len(fits)} distinct of {len(CASES)}")
check("each trigger gets its own subject", len({playbooks.compose(dict(c, **{k: v for k, v in CONTACT.items()}))[0]["subject"]
      for c in CASES.values()}) == len(CASES))

print("\nCombined growth signals")
combo = dict(CASES["hiring"], others=[{"signal_type": "Funding Announcement", "evidence": CASES["funding"]["evidence"],
                                       "added": CASES["funding"]["added"], "removed": []}])
d, notes = playbooks.compose(combo)
check("two signals produce one combined email", notes["playbook"] == "Combined growth signals"
      and "$30 million" in d["body"] and "hiring across" in d["body"], d["body"])
check("combined email passes validation", outreach.validate(d, combo) is None, str(outreach.validate(d, combo)))

print("\nThe validator rejects what it should")
good = dict(CASES["funding"])
base, _ = playbooks.compose(good)


def mutated(**changes):
    return dict(base, **changes)


check("invented number", outreach.validate(mutated(body=base["body"].replace("$30 million", "$300 million")), good) is not None)
check("too short", "words" in (outreach.validate(mutated(body="Hi Jordan,\n\nSaw the raise. Clay can help.\n\nBest,\nYedhu\nClay"), good) or ""))
check("too long", "words" in (outreach.validate(mutated(body=base["body"] + " " + "more words " * 30), good) or ""))
check("banned buzzword", "banned" in (outreach.validate(mutated(body=base["body"].replace("one workflow", "a seamless workflow")), good) or ""))
check("curiosity CTA", "banned" in (outreach.validate(mutated(body=base["body"].replace("happy to show", "curious if a quick chat works; happy to show")), good) or ""))
check("no Clay pitch", "Clay" in (outreach.validate(mutated(body=base["body"].replace("Clay", "we")), good) or ""))
check("two question marks", "question" in (outreach.validate(mutated(body=base["body"].replace("Best,", "Could we talk? Or not?\n\nBest,")), good) or ""))
check("exclamation mark", "exclamation" in (outreach.validate(mutated(body=base["body"].replace("Best,", "Great news!\n\nBest,")), good) or ""))
err = outreach.validate(dict(base, body=bodies["pricing"]), good)       # a good email, but about a different trigger
check("an email that ignores the detected change", err is not None and "reference the detected change" in err, str(err))
check("pasted headline fragment", "pastes" in (outreach.validate(mutated(body=base["body"].replace(
      "announced a $30 million Series B.", "announced a raise, Introducing the round.")), good) or ""))
check("wrong first name", outreach.validate(mutated(body=base["body"].replace("Jordan", "Sam")), good) is not None)
check("placeholder left in", outreach.validate(mutated(body=base["body"].replace("Jordan", "[name]")), good) is not None)

print("\nEvery wording combination stays within the length target")
import itertools  # noqa: E402

full = {k: dict(c, contact_name=CONTACT["contact_name"], contact_title=CONTACT["contact_title"]) for k, c in CASES.items()}
full["combined"] = dict(full["hiring"], others=[{"signal_type": "Funding Announcement", "evidence": CASES["funding"]["evidence"],
                                                 "added": CASES["funding"]["added"], "removed": []}])
for k, c in full.items():
    counts = {}
    for combo_ in itertools.product(range(2), range(2), range(2), ("build", "lead")):
        d, _ = playbooks.compose(c, choice=combo_)
        counts[combo_] = len(d["body"].split())
        err = outreach.validate(d, c)
        if err:
            failures.append(f"{k} {combo_}: {err}")
    low, high = min(counts.values()), max(counts.values())
    margin = 3                                   # a shorter company name or a different contact must not tip it under
    check(f"{k}: all 16 wordings between {playbooks.MIN_WORDS + margin} and {playbooks.MAX_WORDS - margin} words ({low}-{high})",
          playbooks.MIN_WORDS + margin <= low and high <= playbooks.MAX_WORDS - margin,
          str([c_ for c_, n in counts.items() if not playbooks.MIN_WORDS <= n <= playbooks.MAX_WORDS]))

print("\nWhen evidence is thin the wording stays cautious")
thin = ctx("Funding Announcement", "Acme AI news update", ["Acme AI news update"])
check("funding without an amount", "announced new funding." in playbooks.compose(dict(thin, **CONTACT))[0]["body"])
thin_exec = ctx("Leadership Change", "Our team is growing", ["Our team is growing"])
thin_body = playbooks.compose(dict(thin_exec, **CONTACT))[0]["body"]
check("exec without a name quotes the page instead of inventing one",
      '"Our team is growing"' in thin_body and "listed as" not in thin_body, thin_body.split("\n\n")[1])

print(f"\n{'All tests passed' if not failures else str(len(failures)) + ' failed: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
