"""Who is selling, and what they sell. This is the only place the example seller is defined.

The project is an internal tool for a GTM engineer at Clay, built as a portfolio example. The pitch uses
the wording Clay publishes about itself (clay.com) and makes no claims about results or numbers.
To point the tool at another seller, edit this file and contacts.csv.
"""

NAME = "Clay"

# Clay's own positioning, paraphrased from its website.
ONE_LINER = "Clay is infrastructure to get any data, run agentic workflows, and launch GTM plays."
CAPABILITIES = [
    "waterfall enrichment that pulls data from many providers in one workflow",
    "AI research agents (Claygent) that research, score and personalise",
    "a visual canvas to build GTM plays",
    "signals tracking, account and lead scoring",
    "TAM sourcing and CRM enrichment",
    "launching outreach through integrations with existing GTM tools",
]

# Personas Clay's own site and customer stories point to. Used for the placeholder contacts.
PERSONAS = [
    "Chief Revenue Officer", "Head of Revenue Operations", "Head of Sales Operations",
    "Director of GTM Operations", "GTM Systems Lead", "GTM Engineer", "Director of Growth",
]

def prompt_context():
    """The seller facts the Claude drafter is allowed to use. Per-trigger wording lives in playbooks.py."""
    return (f"You write as a BDR at {NAME}. {ONE_LINER} Capabilities you may mention: "
            + "; ".join(CAPABILITIES) + ". Do not claim results, customer names, prices or numbers.")
