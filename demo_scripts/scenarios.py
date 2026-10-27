"""Registry of live-demo scenarios. Each one edits a different company's dummy site (pages in demo_sites/).

    python demo_scripts/scenarios.py list                 # what each scenario does and should produce
    python demo_scripts/scenarios.py apply <id> [<id>..]  # apply one or more
    python demo_scripts/scenarios.py apply all            # apply every scenario in the bundle
    (undo everything: python demo_scripts/reset_demo.py)

The three original Acme AI scenarios (noise, new product, hiring push) are kept and run from their own scripts.
Used by the dashboard (app.py), test_scenarios.py and rehearse.py.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES = ROOT / "demo_sites"


# --------------------------------------------------------------------------- edit helpers

def _file(slug, page):
    return SITES / slug / f"{page}.html"


def _read(slug, page):
    return _file(slug, page).read_text(encoding="utf-8")


def _write(slug, page, text):
    _file(slug, page).write_text(text, encoding="utf-8")


def add_to_main(slug, page, html):
    """Append content at the end of the page body (before </main>)."""
    text = _read(slug, page)
    assert "</main>" in text, f"{slug}/{page}: no <main> block"
    _write(slug, page, text.replace("</main>", html + "\n</main>", 1))


def replace(slug, page, old, new):
    text = _read(slug, page)
    assert old in text, f"{slug}/{page}: expected text not found ({old[:40]!r}); already applied? run reset_demo.py"
    _write(slug, page, text.replace(old, new, 1))


def sub(slug, page, pattern, repl):
    text = _read(slug, page)
    new, n = re.subn(pattern, repl, text, count=1)
    assert n == 1, f"{slug}/{page}: pattern not found ({pattern[:40]!r}); already applied? run reset_demo.py"
    _write(slug, page, new)


def replace_cro(slug, name):
    """Swap the Chief Revenue Officer on the About page for a new person (a real leadership change)."""
    sub(slug, "about", r"<li>[^<]*, Chief Revenue Officer</li>", f"<li>{name}, Chief Revenue Officer</li>")


# --------------------------------------------------------------------------- scenario edits

def northwind_funding():
    add_to_main("northwind-analytics", "news",
                "<h3>Northwind Analytics raises $30 million Series B</h3>\n"
                "<p>The new funding will accelerate product development and expand the sales team.</p>")


def cloudloom_exec():
    replace_cro("cloudloom", "Dana Okoye")


def datastream_expansion():
    add_to_main("datastream-labs", "news",
                "<h3>Datastream Labs expands into Europe with a new Dublin office</h3>\n"
                "<p>The new office will serve customers across the region.</p>")


def ledgerly_pricing():
    sub("ledgerly", "pricing", r"\$19 per user per month", "$24 per user per month")
    add_to_main("ledgerly", "pricing",
                "<h3>Scale</h3>\n<p>$59 per user per month. Priority onboarding and a dedicated success contact.</p>")


def skyline_icp():
    add_to_main("skyline-devops", "products",
                "<h3>Skyline DevOps for Financial Services</h3>\n"
                "<p>Now serving regulated financial institutions with audit-ready deployment controls built for "
                "banks and insurers.</p>")


def helix_partnership():
    add_to_main("helix-support", "news",
                "<h3>Helix Support announces a partnership with Northstar Cloud</h3>\n"
                "<p>The partnership brings Helix ticket data into Northstar workflows for shared customers.</p>")


def quanta_enterprise():
    add_to_main("quanta-security", "news",
                "<h3>Quanta Security launches an enterprise strategic initiative</h3>\n"
                "<p>A new enterprise sales team and a dedicated security review program will serve large customers.</p>")


def orbit_combined():
    add_to_main("orbit-crm", "news",
                "<h3>Orbit CRM raises $18 million Series A</h3>\n"
                "<p>The funding will support product development and customer growth.</p>")
    add_to_main("orbit-crm", "careers",
                "<h2>We're hiring across revenue operations and GTM engineering</h2>\n"
                "<h3>Revenue Operations Manager</h3>\n<p>Own revenue systems, reporting and data quality. Remote.</p>\n"
                "<h3>GTM Engineer</h3>\n<p>Build automations and enrichment workflows across the sales stack. Remote.</p>")
    replace_cro("orbit-crm", "Maya Fernandez")


def mintwise_chrome():
    replace("mintwise", "products", "&copy; 2025", "&copy; 2026")
    replace("mintwise", "products", "We use cookies to improve your experience.",
            "This site uses cookies. Review your consent settings.")
    replace("mintwise", "products", "<nav>", '<nav><a href="blog.html">Blog</a> ')


def stackbank_dates():
    replace("stackbank", "news", "<h1>News</h1>", "<h1>News</h1>\n<p>Last updated: October 2026</p>")
    replace("stackbank", "news", "ship improvements each quarter", "ship improvments each quarter")


def payharbor_reword():
    replace("payharbor", "about", "Simple tools for serious work.", "Practical tools for serious work.")


# --------------------------------------------------------------------------- registry
# alerts: for each alert this scenario should produce, the signal types that are acceptable
# marker: (page, text) present on the site once the scenario is applied

SCENARIOS = [
    # ---- the original three, kept as they were (Acme AI)
    dict(id="acme-noise", company="Acme AI", slug="acme-ai", title="Routine site noise", pages=["products", "about", "news"],
         kind="ignored", alerts=[], script="scenario_a_noise.py", bundle=False, marker=("products", "&copy; 2026"),
         story="Footer year, cookie banner, nav link, tracking script, a tagline reword and a 'last updated' stamp. Nothing here is a buying signal."),
    dict(id="acme-product", company="Acme AI", slug="acme-ai", title="New product launch", pages=["products"],
         kind="signal", alerts=[("New Product Category", "New Product Launch")], script="scenario_b_signal.py", bundle=True,
         marker=("products", "Introducing Acme Agents"),
         story="Acme adds 'Introducing Acme Agents', autonomous AI agents, to its products page."),
    dict(id="acme-hiring", company="Acme AI", slug="acme-ai", title="Hiring push", pages=["careers"],
         kind="signal", alerts=[("Hiring / Growth Signal",)], script="scenario_c_hiring.py", bundle=True,
         marker=("careers", "We're hiring"),
         story="Acme posts revenue operations and GTM engineering roles on its careers page."),

    # ---- new signal scenarios, one per company
    dict(id="northwind-funding", company="Northwind Analytics", slug="northwind-analytics", title="Funding announcement",
         pages=["news"], kind="signal", alerts=[("Funding Announcement",)], apply=northwind_funding, bundle=True,
         marker=("news", "raises $30 million"),
         story="Northwind announces a $30 million Series B on its news page."),
    dict(id="cloudloom-exec", company="Cloudloom", slug="cloudloom", title="Executive change", pages=["about"],
         kind="signal", alerts=[("Leadership Change",)], apply=cloudloom_exec, bundle=True,
         marker=("about", "Dana Okoye"),
         story="Cloudloom replaces its Chief Revenue Officer on the About page."),
    dict(id="datastream-expansion", company="Datastream Labs", slug="datastream-labs", title="Geographic expansion",
         pages=["news"], kind="signal", alerts=[("Market Expansion",)], apply=datastream_expansion, bundle=True,
         marker=("news", "new Dublin office"),
         story="Datastream Labs opens a Dublin office and expands into Europe."),
    dict(id="ledgerly-pricing", company="Ledgerly", slug="ledgerly", title="Pricing change", pages=["pricing"],
         kind="signal", alerts=[("Pricing Change",)], apply=ledgerly_pricing, bundle=True,
         marker=("pricing", "<h3>Scale</h3>"),
         story="Ledgerly raises its Starter price from $19 to $24 and adds a new $59 'Scale' tier."),
    dict(id="skyline-icp", company="Skyline DevOps", slug="skyline-devops", title="New ICP (financial services)",
         pages=["products"], kind="signal", alerts=[("Market Expansion",)], apply=skyline_icp, bundle=True,
         marker=("products", "Now serving regulated"),
         story="Skyline DevOps starts targeting regulated financial institutions, a new customer segment."),
    dict(id="helix-partnership", company="Helix Support", slug="helix-support", title="Strategic partnership",
         pages=["news"], kind="signal", alerts=[("Major Partnership",)], apply=helix_partnership, bundle=True,
         marker=("news", "partnership with Northstar Cloud"),
         story="Helix Support announces a partnership with Northstar Cloud."),
    dict(id="quanta-enterprise", company="Quanta Security", slug="quanta-security", title="Enterprise GTM push",
         pages=["news"], kind="signal", alerts=[("Strategic Initiative",)], apply=quanta_enterprise, bundle=True,
         marker=("news", "enterprise strategic initiative"),
         story="Quanta Security launches an enterprise initiative with a new enterprise sales team."),
    dict(id="orbit-combined", company="Orbit CRM", slug="orbit-crm", title="Combined growth signals",
         pages=["news", "careers", "about"], kind="signal",
         alerts=[("Funding Announcement",), ("Hiring / Growth Signal",), ("Leadership Change",)], apply=orbit_combined,
         bundle=True, marker=("news", "raises $18 million"),
         story="Orbit CRM raises $18M, hires revenue operations and GTM roles, and replaces its CRO, all in one go."),

    # ---- new insignificant changes that must be ignored
    dict(id="mintwise-noise", company="Mintwise", slug="mintwise", title="Footer, cookie banner and nav tweaks",
         pages=["products"], kind="ignored", alerts=[], apply=mintwise_chrome, bundle=True,
         marker=("products", "&copy; 2026"),
         story="Mintwise bumps the footer year, rewords the cookie banner and adds a nav link. Caught by the free rules."),
    dict(id="stackbank-noise", company="Stackbank", slug="stackbank", title="Date stamp and typo fix",
         pages=["news"], kind="ignored", alerts=[], apply=stackbank_dates, bundle=True,
         marker=("news", "Last updated: October 2026"),
         story="Stackbank adds a 'last updated' date and fixes a typo. Caught by the free rules."),
    dict(id="payharbor-noise", company="PayHarbor", slug="payharbor", title="Marketing tagline reword",
         pages=["about"], kind="ignored", alerts=[], apply=payharbor_reword, bundle=True,
         marker=("about", "Practical tools"),
         story="PayHarbor rewords its tagline. The rules cannot tell, so the analyzer judges it and finds no signal."),
]

BY_ID = {s["id"]: s for s in SCENARIOS}


def label(s):
    return f"{s['company']}: {s['title']}"


def is_applied(s):
    page, text = s["marker"]
    path = _file(s["slug"], page)
    return path.exists() and text in path.read_text(encoding="utf-8")


def apply(scenario_id):
    """Apply one scenario to the dummy sites. Returns (ok, message)."""
    s = BY_ID[scenario_id]
    try:
        if "script" in s:
            r = subprocess.run([sys.executable, str(ROOT / "demo_scripts" / s["script"])], capture_output=True,
                               text=True, cwd=ROOT)
            if r.returncode != 0:
                return False, (r.stderr.strip().splitlines() or ["failed"])[-1]
        else:
            s["apply"]()
    except AssertionError as e:
        return False, str(e)
    return True, f"Applied: {label(s)}"


def apply_bundle():
    """Apply every scenario flagged for the bundle. Returns a list of (id, ok, message)."""
    return [(s["id"], *apply(s["id"])) for s in SCENARIOS if s["bundle"]]


def expected_alerts(ids=None):
    return sum(len(s["alerts"]) for s in SCENARIOS if (s["id"] in ids if ids else s["bundle"]))


def _main():
    args = sys.argv[1:]
    if not args or args[0] == "list":
        for s in SCENARIOS:
            result = "no alert (ignored)" if not s["alerts"] else "alert: " + " + ".join(a[0] for a in s["alerts"])
            print(f"{s['id']:22} {s['company']:20} {s['title']:34} -> {result}")
        return
    if args[0] != "apply" or len(args) < 2:
        sys.exit(__doc__)
    ids = [s["id"] for s in SCENARIOS if s["bundle"]] if args[1] == "all" else args[1:]
    for sid in ids:
        if sid not in BY_ID:
            sys.exit(f"unknown scenario {sid!r}; run 'list'")
        ok, message = apply(sid)
        print(("OK    " if ok else "FAIL  ") + message)


if __name__ == "__main__":
    _main()
