"""Demo Scenario B: a meaningful change. Adds a new AI Agents product to the Acme AI products page.

Undo with generate_demo_sites.py.
"""
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "demo_sites" / "acme-ai" / "products.html"
text = path.read_text(encoding="utf-8")
anchor = "<p>Native integrations with Salesforce, HubSpot and Slack.</p>"
assert anchor in text, "anchor not found (already applied? run generate_demo_sites.py)"
new = anchor + """
<h3>Introducing Acme Agents</h3>
<p>Introducing Acme Agents: autonomous AI agents that research accounts, draft outreach and update your CRM without manual work.</p>"""
path.write_text(text.replace(anchor, new, 1), encoding="utf-8")
print("Scenario B applied: 'Introducing Acme Agents' added to the Acme AI products page.")
