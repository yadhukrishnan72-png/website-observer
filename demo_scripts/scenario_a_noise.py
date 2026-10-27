"""Demo Scenario A: five website changes that should NOT produce a Slack alert.

Edits the Acme AI dummy site in place. Undo with generate_demo_sites.py.
"""
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "demo_sites" / "acme-ai"


def edit(page, old, new):
    path = SITE / page
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{page}: expected text not found (already edited? run generate_demo_sites.py)"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# products.html: footer year, cookie banner wording, navigation link, tracking script
edit("products.html", "&copy; 2025", "&copy; 2026")
edit("products.html", "We use cookies to improve your experience.", "This site uses cookies. Review your consent settings.")
edit("products.html", "<nav>", '<nav><a href="blog.html">Blog</a> ')
edit("products.html", "/* tracking placeholder */", "/* tracking placeholder v2 */ window.analyticsId = 'UA-2';")
# about.html: generic marketing reword (not caught by rules; the LLM decides in Phase 4)
edit("about.html", "cutting-edge AI tools", "innovative AI tools")
# news.html: 'last updated' stamp
edit("news.html", "<h1>News</h1>", "<h1>News</h1>\n<p>Last updated: March 2026</p>")
print("Scenario A applied to Acme AI: year, cookie banner, nav link, tracking script, tagline reword, last-updated stamp.")
