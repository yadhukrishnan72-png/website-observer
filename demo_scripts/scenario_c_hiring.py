"""Demo Scenario C: a hiring push. Adds revenue operations and GTM engineering roles to the Acme AI careers page.

Undo with generate_demo_sites.py.
"""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "demo_sites" / "acme-ai" / "careers.html"
text = path.read_text(encoding="utf-8")
anchor = "<p>Help customers get set up and answer their questions. Remote.</p>"
assert anchor in text, "anchor not found (run generate_demo_sites.py first)"
assert "We're hiring" not in text, "already applied (run generate_demo_sites.py to reset)"
new = anchor + """
<h2>We're hiring across revenue operations and GTM engineering</h2>
<h3>Head of Revenue Operations</h3>
<p>Own our revenue systems, data quality and reporting. Hybrid, Austin.</p>
<h3>GTM Engineer</h3>
<p>Build automations and enrichment workflows across our sales and marketing stack. Remote.</p>
<h3>Sales Operations Manager</h3>
<p>Own territory planning, lead routing and forecasting. Hybrid, Austin.</p>"""
path.write_text(text.replace(anchor, new, 1), encoding="utf-8")
print("Scenario C applied: revenue operations and GTM engineering roles added to the Acme AI careers page.")
