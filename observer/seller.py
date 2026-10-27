"""Who is selling, and what they sell. This is the only place the example seller is defined.

The project is an internal tool for a GTM engineer at Clay, built as a portfolio example. The pitch uses
the wording Clay publishes about itself (clay.com) and makes no claims about results or numbers.
To point the tool at another seller, edit this file and contacts.csv.
"""

NAME = "Clay"

# Clay's own positioning, paraphrased from its website.
ONE_LINER = "Clay is infrastructure to get any data, run agentic workflows, and launch GTM plays."
CAPABILITIES = [
    "waterfall enrichment that pulls data from many providers",
    "AI research agents (Claygent) that research, score and personalise",
    "a visual canvas to build GTM plays",
    "signals tracking and account scoring",
]

# Personas Clay's own site and customer stories point to. Used for the placeholder contacts.
PERSONAS = [
    "Chief Revenue Officer", "Head of Revenue Operations", "Head of Sales Operations",
    "Director of GTM Operations", "GTM Systems Lead", "GTM Engineer", "Director of Growth",
]

# Mock drafter only: one sentence per signal tying the signal to what Clay does.
BRIDGES = {
    "New Product Launch": "A launch usually means new accounts to find and research quickly. Clay lets GTM teams source and enrich that audience without hand-built spreadsheets.",
    "New Product Category": "A new product area usually means a new audience to find and research. Clay lets GTM teams source and enrich that audience and turn it into a play.",
    "Pricing Change": "Repackaging usually means re-segmenting accounts. Clay can enrich and score your accounts against the new tiers.",
    "Leadership Change": "New leaders often rebuild the GTM stack. Clay gives GTM teams one place to get data, run agentic workflows and launch plays.",
    "Funding Announcement": "Fresh funding usually raises pipeline targets. Clay helps GTM teams get data and launch new plays fast.",
    "Major Partnership": "A partnership can become a play. Clay can find the right accounts, research them with AI agents and trigger outreach.",
    "Market Expansion": "A new market usually means building account lists from scratch. Clay sources and enriches them in one workflow.",
    "Strategic Initiative": "Big initiatives need GTM plays behind them. Clay helps teams get the data and run the workflows to launch them.",
    "Hiring / Growth Signal": "Hiring for revenue operations or GTM roles usually means the GTM stack is being built out, which is the work Clay is built for: getting data, running agentic workflows and launching plays.",
}


def prompt_context():
    """The seller facts the Claude drafter is allowed to use."""
    return (f"You write as a BDR at {NAME}. {ONE_LINER} Capabilities you may mention: "
            + "; ".join(CAPABILITIES) + ". Do not claim results, customer names, prices or numbers.")
