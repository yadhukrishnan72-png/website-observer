"""Generate the dummy world: 20 synthetic company sites + accounts.csv + pages.csv.

Deterministic: running it again restores every site to its baseline state.
Usage:  python demo_scripts/generate_demo_sites.py
Serve:  python -m http.server 8000 --directory demo_sites
"""
import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES = ROOT / "demo_sites"
BASE_URL = "http://localhost:8000"
PAGES = ["products", "pricing", "about", "news", "careers"]

# One routine posting that is the same everywhere: a single job is not a signal.
CAREERS_BODY = """<h1>Careers</h1>
<p>We are a small, focused team. Current openings are listed below.</p>
<h3>Customer Support Specialist</h3>
<p>Help customers get set up and answer their questions. Remote.</p>"""

# name, slug, industry, owner, priority
COMPANIES = [
    ("Acme AI", "acme-ai", "SaaS", "Yedhu", "High"),
    ("Northwind Analytics", "northwind-analytics", "SaaS", "Yedhu", "High"),
    ("Brightpath HR", "brightpath-hr", "SaaS", "Priya", "Medium"),
    ("Cloudloom", "cloudloom", "SaaS", "Priya", "High"),
    ("Datastream Labs", "datastream-labs", "SaaS", "Marco", "Medium"),
    ("Helix Support", "helix-support", "SaaS", "Marco", "Low"),
    ("Orbit CRM", "orbit-crm", "SaaS", "Yedhu", "Medium"),
    ("Pinecrest Software", "pinecrest-software", "SaaS", "Priya", "Low"),
    ("Quanta Security", "quanta-security", "SaaS", "Marco", "High"),
    ("Skyline DevOps", "skyline-devops", "SaaS", "Yedhu", "Medium"),
    ("Tandem Workflows", "tandem-workflows", "SaaS", "Priya", "Low"),
    ("Vertex Learning", "vertex-learning", "SaaS", "Marco", "Medium"),
    ("Ledgerly", "ledgerly", "Fintech", "Yedhu", "High"),
    ("PayHarbor", "payharbor", "Fintech", "Priya", "Medium"),
    ("Mintwise", "mintwise", "Fintech", "Marco", "Low"),
    ("Stackbank", "stackbank", "Fintech", "Yedhu", "Medium"),
    ("Greenfield Logistics", "greenfield-logistics", "Logistics", "Priya", "Medium"),
    ("Meridian Health Tech", "meridian-health-tech", "Healthcare", "Marco", "High"),
    ("Summit Retail Systems", "summit-retail-systems", "Retail Tech", "Yedhu", "Low"),
    ("Ironclad Manufacturing", "ironclad-manufacturing", "Manufacturing", "Priya", "Low"),
]

PRODUCT_POOL = {
    "SaaS": [("Insights Dashboard", "Real-time dashboards that turn raw usage data into decisions."),
             ("Workflow Automation", "Automate repetitive team processes with no-code rules."),
             ("Team Collaboration Hub", "One place for projects, files and conversations."),
             ("Reporting Suite", "Scheduled reports delivered to the people who need them.")],
    "Fintech": [("Payments Gateway", "Accept cards and bank transfers with a single integration."),
                ("Expense Management", "Control company spend with cards, limits and approvals."),
                ("Invoicing Platform", "Send invoices and get paid faster."),
                ("Treasury Tools", "Manage cash positions across accounts.")],
    "Logistics": [("Route Optimizer", "Plan delivery routes that cut fuel and time."),
                  ("Fleet Tracking", "Live location and status for every vehicle."),
                  ("Warehouse Manager", "Inventory visibility from dock to shelf.")],
    "Healthcare": [("Patient Scheduling", "Online booking that reduces no-shows."),
                   ("Records Platform", "Secure electronic records for clinics."),
                   ("Billing Assistant", "Claims preparation and tracking.")],
    "Retail Tech": [("Point of Sale", "Fast checkout for stores of any size."),
                    ("Inventory Sync", "Keep stock levels accurate across channels."),
                    ("Loyalty Program", "Reward repeat customers with simple tools.")],
    "Manufacturing": [("Production Planner", "Schedule lines and shifts with fewer conflicts."),
                      ("Quality Tracker", "Log and trend defects across plants."),
                      ("Maintenance Manager", "Preventive maintenance schedules and alerts.")],
}

TAGLINES = ["Built for teams that move fast.", "Simple tools for serious work.",
            "Everything you need, nothing you don't.", "Work smarter, grow steadily."]
FIRST = ["Alex", "Jordan", "Sam", "Riley", "Casey", "Morgan", "Taylor", "Jamie", "Avery", "Drew"]
LAST = ["Nguyen", "Okafor", "Silva", "Kowalski", "Haddad", "Bergstrom", "Iyer", "Moreau", "Tanaka", "Reyes"]
CITIES = ["Austin", "Toronto", "London", "Berlin", "Singapore", "Chicago", "Dublin", "Sydney"]

# Content that is deliberately identical across pages so the cleaner has real noise to strip.
def shell(company, slug, page, title, body):
    nav = "".join(
        f'<a href="{p}.html">{p.capitalize()}</a> ' for p in PAGES)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | {company}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 0 auto; padding: 0 16px; color: #1b1f27; }}
header, footer {{ padding: 16px 0; border-bottom: 1px solid #ddd; }}
footer {{ border-top: 1px solid #ddd; border-bottom: 0; margin-top: 40px; color: #666; font-size: 14px; }}
nav a {{ margin-right: 14px; }}
.cookie-banner {{ background: #f3f3f3; padding: 10px; font-size: 13px; }}
</style>
<script>window.dataLayer = window.dataLayer || []; /* tracking placeholder */</script>
</head>
<body>
<div class="cookie-banner" id="cookie-consent">We use cookies to improve your experience. <button>Accept</button></div>
<header>
<strong>{company}</strong>
<nav>{nav}</nav>
</header>
<main>
{body}
</main>
<footer>
<p>&copy; 2025 {company}. All rights reserved.</p>
<p><a href="#">Privacy</a> | <a href="#">Terms</a></p>
</footer>
</body>
</html>
"""


def build_company(rng, name, slug, industry):
    products = PRODUCT_POOL.get(industry, PRODUCT_POOL["SaaS"])
    k = min(3, len(products))
    chosen = rng.sample(products, k)
    tagline = rng.choice(TAGLINES)
    city = rng.choice(CITIES)
    founded = rng.randint(2012, 2021)
    ceo = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    cto = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    cro = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    base = rng.choice([19, 29, 39, 49])

    prod_items = "\n".join(f"<h3>{n}</h3>\n<p>{d}</p>" for n, d in chosen)
    products_body = f"""<h1>Products</h1>
<p>{name} offers a focused set of tools for {industry.lower()} teams.</p>
{prod_items}"""

    pricing_body = f"""<h1>Pricing</h1>
<p>Choose the plan that fits your team.</p>
<h3>Starter</h3>
<p>${base} per user per month. Core features for small teams.</p>
<h3>Growth</h3>
<p>${base * 2} per user per month. Advanced reporting and integrations.</p>
<h3>Enterprise</h3>
<p>Custom pricing. Dedicated support and security reviews.</p>"""

    about_body = f"""<h1>About {name}</h1>
<p>{name} was founded in {founded} and is headquartered in {city}. {tagline}</p>
<h2>Leadership</h2>
<ul>
<li>{ceo}, Chief Executive Officer</li>
<li>{cto}, Chief Technology Officer</li>
<li>{cro}, Chief Revenue Officer</li>
</ul>"""

    news_body = f"""<h1>News</h1>
<h3>{name} celebrates a milestone with customers</h3>
<p>We hosted our annual customer event in {city} with teams from across the region.</p>
<h3>Company update: how we work</h3>
<p>A short note from our team on how we plan and ship improvements each quarter.</p>"""

    return {"products": ("Products", products_body), "pricing": ("Pricing", pricing_body),
            "about": ("About", about_body), "news": ("News", news_body), "careers": ("Careers", CAREERS_BODY)}


def build_acme():
    """Acme AI: the hand-written live-demo company. Distinct, richer content."""
    name = "Acme AI"
    products = """<h1>Products</h1>
<p>Acme AI helps revenue teams turn data into decisions with machine learning.</p>
<h3>Acme Insights</h3>
<p>Predictive analytics that forecast pipeline and highlight at-risk deals.</p>
<h3>Acme Assist</h3>
<p>An AI copilot that drafts follow-ups and summarises customer calls.</p>
<h3>Acme Connect</h3>
<p>Native integrations with Salesforce, HubSpot and Slack.</p>"""
    pricing = """<h1>Pricing</h1>
<p>Simple plans that scale with your revenue team.</p>
<h3>Starter</h3>
<p>$49 per user per month. Insights for teams up to 10 people.</p>
<h3>Growth</h3>
<p>$99 per user per month. Acme Assist, advanced forecasting and integrations.</p>
<h3>Enterprise</h3>
<p>Custom pricing. SSO, audit logs and a dedicated success manager.</p>"""
    about = """<h1>About Acme AI</h1>
<p>Acme AI was founded in 2019 and is headquartered in Austin, Texas. We build cutting-edge AI tools that help B2B revenue teams work smarter.</p>
<h2>Leadership</h2>
<ul>
<li>Dana Whitfield, Chief Executive Officer</li>
<li>Rahul Mehta, Chief Technology Officer</li>
<li>Elena Brandt, Chief Marketing Officer</li>
</ul>
<p>Our mission is to make every revenue team more effective with trustworthy AI.</p>"""
    news = """<h1>News</h1>
<h3>Acme AI named a top workplace in Austin</h3>
<p>We were recognised by local business leaders for our team culture and flexible work policies.</p>
<h3>Customer spotlight: how Brightline cut forecasting time in half</h3>
<p>Brightline's sales operations team uses Acme Insights to review pipeline every Monday.</p>"""
    return {"products": ("Products", products), "pricing": ("Pricing", pricing),
            "about": ("About", about), "news": ("News", news), "careers": ("Careers", CAREERS_BODY)}


def main():
    SITES.mkdir(exist_ok=True)
    accounts, pages = [], []
    for i, (name, slug, industry, owner, priority) in enumerate(COMPANIES):
        content = build_acme() if slug == "acme-ai" else build_company(random.Random(i), name, slug, industry)
        d = SITES / slug
        d.mkdir(exist_ok=True)
        for page, (title, body) in content.items():
            (d / f"{page}.html").write_text(shell(name, slug, page, title, body), encoding="utf-8")
            pages.append([name, page, f"{BASE_URL}/{slug}/{page}.html"])
        (d / "index.html").write_text(
            shell(name, slug, "index", "Home", f"<h1>{name}</h1>\n<p>Welcome. See our <a href=\"products.html\">products</a>.</p>"),
            encoding="utf-8")
        accounts.append([name, f"{BASE_URL}/{slug}/", industry, owner, priority])

    with open(ROOT / "accounts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_name", "website_url", "industry", "account_owner", "priority"])
        w.writerows(accounts)
    with open(ROOT / "pages.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company_name", "page_type", "url"])
        w.writerows(pages)
    print(f"Generated {len(accounts)} sites, {len(pages)} monitored pages in {SITES}")


if __name__ == "__main__":
    main()
