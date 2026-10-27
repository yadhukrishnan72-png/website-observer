"""Labelled test set for evaluate.py: 10 changes that must NOT alert and 8 that must, with the expected signal.

Each fixture starts from a base page body and describes how the page changes:
  edits       [(old, new)] text replacements inside the page body
  add         HTML appended to the body
  shell_edits [(old, new)] replacements in the surrounding page (footer, cookie banner, nav, head)
"""

BASES = {
    "products": (
        "<h1>Products</h1><p>Northwind offers focused analytics tools for revenue teams.</p>"
        "<h3>Insights Dashboard</h3><p>Real-time dashboards that turn raw usage data into decisions.</p>"
        "<h3>Workflow Automation</h3><p>Automate repetitive team processes with no-code rules.</p>"),
    "pricing": (
        "<h1>Pricing</h1><p>Choose the plan that fits your team.</p>"
        "<h3>Starter</h3><p>$49 per user per month. Core features for small teams.</p>"
        "<h3>Growth</h3><p>$99 per user per month. Advanced reporting and integrations.</p>"),
    "about": (
        "<h1>About Northwind</h1><p>Northwind was founded in 2018 in Chicago. We build tools that help B2B "
        "revenue teams work smarter.</p><h2>Leadership</h2><ul><li>Dana Whitfield, Chief Executive Officer</li>"
        "<li>Rahul Mehta, Chief Technology Officer</li></ul>"),
    "news": (
        "<h1>News</h1><h3>Annual customer event</h3>"
        "<p>We hosted our annual customer event with teams from across the region.</p>"),
    "careers": (
        "<h1>Careers</h1><p>We are a small, focused team. Current openings are listed below.</p>"
        "<h3>Customer Support Specialist</h3><p>Help customers get set up and answer their questions. Remote.</p>"),
}

NOISE = "noise"
SIGNAL = "signal"

FIXTURES = [
    # ---- must NOT alert
    dict(id="n01_copyright_year", kind=NOISE, page="about", expect=None,
         shell_edits=[("&copy; 2025", "&copy; 2026")]),
    dict(id="n02_cookie_banner_text", kind=NOISE, page="products", expect=None,
         shell_edits=[("We use cookies to improve your experience.", "This site uses cookies to personalise content.")]),
    dict(id="n03_nav_link_added", kind=NOISE, page="pricing", expect=None,
         shell_edits=[("<nav>", '<nav><a href="blog.html">Blog</a> ')]),
    dict(id="n04_tracking_script", kind=NOISE, page="news", expect=None,
         shell_edits=[("/* tracking placeholder */", "/* tracking v2 */")]),
    dict(id="n05_last_updated_stamp", kind=NOISE, page="news", expect=None,
         add="<p>Last updated: March 2026</p>"),
    dict(id="n06_typo_fix", kind=NOISE, page="products", expect=None,
         edits=[("repetitive", "repetative")]),
    dict(id="n07_styling_change", kind=NOISE, page="pricing", expect=None,
         shell_edits=[("max-width: 860px", "max-width: 920px")]),
    dict(id="n08_formatting_only", kind=NOISE, page="products", expect=None,
         edits=[("Real-time dashboards that", "<strong>Real-time dashboards</strong> that")]),
    dict(id="n09_marketing_reword", kind=NOISE, page="about", expect=None,
         edits=[("tools that help", "innovative tools that help")]),
    dict(id="n10_single_routine_job", kind=NOISE, page="careers", expect=None,
         add="<h3>Office Manager</h3><p>Keep the office running smoothly. Austin.</p>"),
    dict(id="n11_footer_cookie_nav_together", kind=NOISE, page="products", expect=None,
         shell_edits=[("&copy; 2025", "&copy; 2026"),
                      ("We use cookies to improve your experience.", "This site uses cookies. Review your consent settings."),
                      ("<nav>", '<nav><a href="blog.html">Blog</a> ')]),
    dict(id="n12_date_stamp_and_typo", kind=NOISE, page="news", expect=None,
         edits=[("annual customer event", "anual customer event")], add="<p>Last updated: October 2026</p>"),
    dict(id="n13_tagline_reword", kind=NOISE, page="about", expect=None,
         edits=[("work smarter", "work more effectively")]),

    # ---- must alert, with this signal type
    dict(id="s01_ai_product", kind=SIGNAL, page="products", expect="New Product Category",
         add="<h3>Introducing Northwind Agents</h3><p>Introducing Northwind Agents: autonomous AI agents that "
             "research accounts and update your CRM without manual work.</p>"),
    dict(id="s02_product_launch", kind=SIGNAL, page="products", expect="New Product Launch",
         add="<h3>Introducing Route Planner</h3><p>Introducing Route Planner: plan delivery routes that cut fuel "
             "and time.</p>"),
    dict(id="s03_pricing_change", kind=SIGNAL, page="pricing", expect="Pricing Change",
         edits=[("$49 per user per month", "$59 per user per month")],
         add="<h3>Scale</h3><p>$199 per user per month. Dedicated support.</p>"),
    dict(id="s04_new_cro", kind=SIGNAL, page="about", expect="Leadership Change",
         edits=[("</ul>", "<li>Marta Silva, Chief Revenue Officer</li></ul>")]),
    dict(id="s05_funding", kind=SIGNAL, page="news", expect="Funding Announcement",
         add="<h3>Northwind raises $20 million Series B</h3><p>The funding will accelerate product development "
             "and hiring.</p>"),
    dict(id="s06_partnership", kind=SIGNAL, page="news", expect="Major Partnership",
         add="<h3>Northwind announces partnership with Helios Cloud</h3><p>The partnership brings warehouse data "
             "into Northwind dashboards.</p>"),
    dict(id="s07_expansion", kind=SIGNAL, page="news", expect="Market Expansion",
         add="<h3>Northwind expands into Europe with a new Berlin office</h3><p>The new office will serve "
             "customers across the region.</p>"),
    dict(id="s09_new_icp", kind=SIGNAL, page="products", expect="Market Expansion",
         add="<h3>Northwind for Financial Services</h3><p>Now serving regulated financial institutions with "
             "audit-ready controls built for banks and insurers.</p>"),
    dict(id="s10_enterprise_push", kind=SIGNAL, page="news", expect="Strategic Initiative",
         add="<h3>Northwind launches an enterprise strategic initiative</h3><p>A new enterprise sales team and a "
             "dedicated review program will serve large customers.</p>"),
    dict(id="s11_executive_replaced", kind=SIGNAL, page="about", expect="Leadership Change",
         edits=[("Rahul Mehta, Chief Technology Officer", "Priya Nair, Chief Technology Officer")]),
    dict(id="s08_gtm_hiring_push", kind=SIGNAL, page="careers", expect="Hiring / Growth Signal",
         add="<h2>We're hiring across revenue operations and GTM engineering</h2><h3>Head of Revenue Operations"
             "</h3><p>Own revenue systems and reporting.</p>"),
]
