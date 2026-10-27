"""Put the demo back to a clean starting state.

Regenerates the dummy sites, wipes observer.db, clears the demo triggers and drafts in Attio (never
companies or people), and takes a fresh baseline snapshot of all 100 pages.

    python demo_scripts/reset_demo.py
"""
import _demo

with _demo.site_server():
    cleared = _demo.reset()
print(f"Demo reset: sites regenerated, {cleared} Attio demo entries cleared, baseline taken "
      f"({_demo.EXPECTED_PAGES} pages). Ready for the live demo.")
