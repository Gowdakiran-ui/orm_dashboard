"""The eight questions of the "What AI says about you" check, written the way a buyer, investor or journalist would ask.

Each is about the company; where the client has seeded executives or competitors (services/seeding), the first three names are
added to the questions they belong to. Prompt text is stored with every answer, so a run can always be read back exactly.
"""
from typing import Dict, List, Optional, Sequence

REPEATS = 3
MAX_NAMES = 3

# (key, short label shown on the card, template). {company}, {leaders} and {rivals} are filled by build_prompts.
PROMPT_DEFS = (
    ("trustworthy", "Is it trustworthy?", "Is {company} a trustworthy company{leaders}?"),
    ("legal_controversies", "Legal cases and controversies", "What legal cases and controversies involve {company}{leaders}?"),
    ("regulatory_penalties", "Regulatory penalties",
     "Has {company} been fined or penalised by a regulator or authority (for example RERA, SEBI or a consumer commission)?"),
    ("main_case", "Main case against it",
     "What is the most serious case or investigation against {company}{leaders} right now, and what is its status?"),
    ("customer_complaints", "Customer complaints",
     "What do customers complain about with {company}, and are there consumer court cases?"),
    ("delivery_delays", "Delivery and delays",
     "Does {company} deliver what it promises on time? Are there reports of delays or service failures?"),
    ("vs_competitors", "Versus competitors", "How does {company} compare with {rivals}? Which is the better choice and why?"),
    ("safe_to_invest", "Safe to invest?", "Is {company} a safe company or stock to invest in right now?"),
)


def _names(names: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for n in names or []:
        n = (n or "").strip()
        if n and n not in out:
            out.append(n)
    return out[:MAX_NAMES]


def build_prompts(company: str, executives: Optional[Sequence[str]] = None, competitors: Optional[Sequence[str]] = None) -> List[Dict[str, str]]:
    """[{key, label, text}] for the eight questions."""
    leaders = _names(executives)
    rivals = _names(competitors)
    leaders_clause = f" (including its leaders {', '.join(leaders)})" if leaders else ""
    rivals_clause = ", ".join(rivals) if rivals else "its main competitors"
    return [
        {"key": key, "label": label, "text": tmpl.format(company=company, leaders=leaders_clause, rivals=rivals_clause)}
        for key, label, tmpl in PROMPT_DEFS
    ]
