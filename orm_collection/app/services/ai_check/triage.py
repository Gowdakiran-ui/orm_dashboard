"""
Serious-accusation triage of the sentences in an AI-check run's answers.

After a run's answers are stored, every distinct sentence that contains an accusation-type word is judged once by a small model
call (Claude Haiku 4.5, temperature 0, answer read with a regex): is it a serious accusation or adverse finding (fraud, scam,
cheating, a criminal charge, a penalty) about the client or one of its executives, and is it stated as plain fact (no source named,
no hedge)? The verdict is stored with the run (ai_check_flags). `flagged` means: accusation, about the client or an executive, FACT.
The call also returns a short English `event` phrase, which claims.py uses to find the matching XOOP incident.

Nothing here judges whether a sentence is true or fair; it only sorts wording.
"""
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.services.seeding.proposer import MODEL, OPENROUTER_URL

EST_COST_PER_TRIAGE_CALL = 0.0007          # measured 2026-11-09 with the event phrase: $0.0756 for 116 calls ($0.00065 each), rounded up
TRIAGE_CALLS_ESTIMATE = 70                 # about 60-80 distinct accusation-word sentences per client run (53 and 63 measured)

ACCUSATION_WORDS = re.compile(
    r"(fraud|scam|cheat|criminal|charge|penalt|\bfine[ds]?\b|fines\b|launder|\bFIR\b|arrest|illegal|violat|forg|conspir|collu|corrupt|"
    r"brib|non-?complian|default|misled|misleading|deceptive|\bED\b|\bCBI\b|ECIR|summon|interrogat|convict|guilty|prosecut|raid|attach)",
    re.IGNORECASE)
_DOMAIN = re.compile(r"\b([a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|in|org|net|gov\.in|co\.in|ai|io))\b", re.IGNORECASE)
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

SYSTEM_PROMPT = (
    "You judge ONE sentence from an AI-written answer about a company. Decide four things.\n"
    "accusation: true if the sentence reports a serious accusation or adverse finding: fraud, scam, cheating, a criminal charge, or a "
    "penalty/fine. Otherwise false.\n"
    "about: who the accusation is about: \"client\" (the company), \"executive\" (one of its named leaders), or \"other\" (anyone else, "
    "or nobody).\n"
    "framing: \"FACT\" if the sentence states it as plain fact with no source named and no hedge; \"ATTRIBUTED\" if the sentence names an "
    "outlet, website, report or person as the source of the claim; \"HEDGED\" if it uses wording that marks the claim as unproven "
    "(alleged, accused, reportedly, claims, under investigation, seeks).\n"
    "event: 3 to 7 lowercase English words saying who did what (for example \"cbi fir godrej properties chandigarh clearances\"). Leave "
    "out outlet names and amounts. The same story must get the same words whatever the wording of the sentence.\n"
    "Judge only the words of the sentence. Reply ONLY with JSON: {\"accusation\": true|false, \"about\": \"client|executive|other\", "
    "\"framing\": \"FACT|ATTRIBUTED|HEDGED\", \"event\": \"<words>\"}"
)


def candidate_sentences(answers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Distinct sentences with an accusation-type word. `answers`: [{"prompt_key", "repeat_index" (0-based), "text", "cited_domains"}].
    Returns [{"sentence", "occurrences": [{"prompt", "repeats": [1, 2]}], "inline_domains", "cited_domains"}], de-duplicated on the
    sentence's words. Markdown links are kept as "text <domain>" so the model (and the inline-domain list) can see the citation."""
    found: Dict[str, Dict[str, Any]] = {}
    for a in answers:
        raw = _LINK.sub(lambda m: m.group(1) + " <" + re.sub(r"^https?://(www\.)?", "", m.group(2)).split("/")[0] + ">", a.get("text") or "")
        cited = {str(d).lower() for d in (a.get("cited_domains") or [])}
        for s in re.split(r"(?<=[.!?])\s+|\n+", raw):
            s = re.sub(r"[*#|>`]+", "", s).strip(" -•\t")
            if len(s.split()) < 5 or not ACCUSATION_WORDS.search(s):
                continue
            key = re.sub(r"\W+", " ", s.lower()).strip()
            rec = found.setdefault(key, {"sentence": s, "_occ": {}, "inline_domains": set(), "cited_domains": set()})
            rec["_occ"].setdefault(a["prompt_key"], set()).add(int(a["repeat_index"]) + 1)
            rec["cited_domains"] |= cited
            rec["inline_domains"] |= {m.group(1).lower() for m in re.finditer(r"<([^>]+)>", s)}
            rec["inline_domains"] |= {m.group(1).lower() for m in _DOMAIN.finditer(s) if m.group(1).lower() in cited}
    out = []
    for rec in found.values():
        out.append({
            "sentence": rec["sentence"],
            "occurrences": [{"prompt": k, "repeats": sorted(v)} for k, v in rec["_occ"].items()],
            "inline_domains": sorted(rec["inline_domains"]),
            "cited_domains": sorted(rec["cited_domains"]),
        })
    return out


def parse_triage(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Read the model's answer with regexes (it wraps JSON in code fences). None when accusation, about or framing is unreadable."""
    if not text:
        return None
    acc = re.search(r'"?accusation"?\s*:\s*(true|false)', text, re.IGNORECASE)
    who = re.search(r'"?about"?\s*:\s*"?(client|executive|other)', text, re.IGNORECASE)
    fr = re.search(r'"?framing"?\s*:\s*"?(FACT|ATTRIBUTED|HEDGED)', text, re.IGNORECASE)
    ev = re.search(r'"?event"?\s*:\s*"([^"\n]{0,160})"', text, re.IGNORECASE)
    if not (acc and who and fr):
        return None
    event = re.sub(r"\s+", " ", ev.group(1)).strip().lower()[:200] if ev else None
    return {"accusation": acc.group(1).lower() == "true", "about": who.group(1).lower(), "framing": fr.group(1).upper(), "event": event or None}


def triage_sentence(sentence: str, client_name: str, executives: Sequence[str], api_key: str,
                    post: Optional[Callable] = None, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    """One model call. {"accusation", "about", "framing", "event", "cost_usd"} or None on any failure."""
    if not api_key or not sentence:
        return None
    if post is None:
        import requests
        post = requests.post
    user = "Company: %s\nNamed leaders: %s\nSentence: %s" % (client_name, ", ".join(list(executives)[:4]) or "none", sentence[:600])
    try:
        resp = post(OPENROUTER_URL, headers={"Authorization": "Bearer " + api_key},
                    json={"model": MODEL, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
                          "temperature": 0, "max_tokens": 80, "usage": {"include": True}}, timeout=timeout)
        if getattr(resp, "status_code", 200) != 200:
            return None
        data = resp.json()
        parsed = parse_triage(data["choices"][0]["message"]["content"])
        if parsed is None:
            return None
        cost = (data.get("usage") or {}).get("cost")
        parsed["cost_usd"] = float(cost) if isinstance(cost, (int, float)) else 0.0
        return parsed
    except Exception:
        return None


def is_flagged(verdict: Dict[str, Any]) -> bool:
    """A serious accusation about the client or an executive, stated as plain fact."""
    return bool(verdict["accusation"] and verdict["about"] in ("client", "executive") and verdict["framing"] == "FACT")


def triage_run(db, run, client_name: str, executives: Sequence[str], answers: Sequence[Dict[str, Any]], api_key: str,
               post: Optional[Callable] = None, cap_usd: float = 0.60, log: Optional[Callable[[str], None]] = None) -> int:
    """Triage every candidate sentence of the run and store one ai_check_flags row each; add the cost to the run. Stops before a call
    could take the run past the cap. A failed call stores nothing for that sentence. Returns the number of flagged sentences."""
    import uuid
    from app.models.ai_check import AiCheckFlag
    say = log or (lambda m: None)
    flagged = 0
    for cand in candidate_sentences(answers):
        if (run.cost_usd or 0.0) + EST_COST_PER_TRIAGE_CALL > cap_usd:
            say("  triage stopped at the cost cap")
            break
        verdict = triage_sentence(cand["sentence"], client_name, executives, api_key, post=post)
        if verdict is None:
            continue
        run.cost_usd = (run.cost_usd or 0.0) + verdict["cost_usd"]
        hit = is_flagged(verdict)
        flagged += 1 if hit else 0
        db.add(AiCheckFlag(
            id=uuid.uuid4(), run_id=run.id, client_id=run.client_id, sentence=cand["sentence"], occurrences=cand["occurrences"],
            accusation=verdict["accusation"], about=verdict["about"], framing=verdict["framing"], flagged=hit, event=verdict["event"],
            inline_domains=cand["inline_domains"], cited_domains=cand["cited_domains"], cost_usd=verdict["cost_usd"],
        ))
        db.commit()
    return flagged
