"""
"What AI says about you": ask a web-grounded AI the questions a buyer, investor or journalist would ask about a client and
store what it answered and which pages it cited.

Separate from Run Pipeline. A super admin starts it ("Run AI check"); it is OFF unless AI_CHECK_ENABLED=1. It reads nothing from
and writes nothing to any score, risk event, alert or report: it only fills ai_check_runs / ai_check_answers
(database/migrations/0018_add_ai_check.sql), which the Brand Equity card reads.

The web call is the same one the seeding uses (services/seeding/proposer.py: Claude Haiku 4.5 through OpenRouter with the web
plugin, temperature 0); only the number of results (5) and the answer shape (free text, not JSON) differ. A run is 8 questions
x 3 repeats = 24 calls, about $0.014 each; it stops before the cost would pass the per-client cap (AI_CHECK_COST_CAP_USD, 0.60).
"""
import datetime
import itertools
import os
import re
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.services.ai_check.prompts import PROMPT_DEFS, REPEATS, build_prompts
from app.services.ai_check.reliability import classify_domain, domain_of
from app.services.seeding.proposer import MODEL, OPENROUTER_URL

WEB_RESULTS = 5
MAX_TOKENS = 700
# Measured 2026-11-06 with this exact call (5 results, 700 tokens): $0.0133. Used only for the estimate and the cap guard.
EST_COST_PER_CALL = 0.0135
RUN_STALE_MINUTES = 20
MAX_CONSECUTIVE_FAILURES = 4


class AiCheckCallError(Exception):
    """One web call failed; the run goes on with the next question."""


def ai_check_enabled() -> bool:
    """Off unless AI_CHECK_ENABLED is 1/true/yes/on (read per call)."""
    return os.environ.get("AI_CHECK_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def cost_cap_usd() -> float:
    try:
        return float(os.environ.get("AI_CHECK_COST_CAP_USD", "0.60"))
    except (TypeError, ValueError):
        return 0.60


def estimate(prompt_count: int = len(PROMPT_DEFS), repeats: int = REPEATS) -> Dict[str, Any]:
    """`estimated_cost_usd` is the web calls only; the sentence triage that follows adds `triage_cost_usd` (small, cheap calls)."""
    from app.services.ai_check.triage import EST_COST_PER_TRIAGE_CALL, TRIAGE_CALLS_ESTIMATE
    calls = prompt_count * repeats
    web = round(calls * EST_COST_PER_CALL, 3)
    triage = round(TRIAGE_CALLS_ESTIMATE * EST_COST_PER_TRIAGE_CALL, 3)
    return {"calls": calls, "prompts": prompt_count, "repeats": repeats, "estimated_cost_usd": web,
            "triage_calls": TRIAGE_CALLS_ESTIMATE, "triage_cost_usd": triage, "total_estimate_usd": round(web + triage, 3),
            "cap_usd": cost_cap_usd(), "model": MODEL, "web_results": WEB_RESULTS}


# ---- the call -----------------------------------------------------------------------------------------------------------
def ask_with_web(prompt: str, api_key: str, post: Optional[Callable] = None, max_results: int = WEB_RESULTS,
                 max_tokens: int = MAX_TOKENS, timeout: float = 120.0) -> Dict[str, Any]:
    """{"text", "citations": [{"url", "title"}], "cost_usd", "prompt_tokens", "completion_tokens"}. Raises AiCheckCallError."""
    if post is None:
        import requests
        post = requests.post
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "usage": {"include": True},
        "plugins": [{"id": "web", "max_results": max_results}],
    }
    try:
        resp = post(OPENROUTER_URL, headers={"Authorization": "Bearer " + api_key}, json=body, timeout=timeout)
    except Exception as e:
        raise AiCheckCallError(f"web call failed: {e!r}"[:300])
    if getattr(resp, "status_code", 200) != 200:
        raise AiCheckCallError(f"web call returned HTTP {resp.status_code}: {str(getattr(resp, 'text', ''))[:200]}")
    try:
        data = resp.json()
        message = data["choices"][0]["message"]
        text = message.get("content") or ""
    except Exception as e:
        raise AiCheckCallError(f"web call response was malformed: {e!r}"[:300])
    if not text.strip():
        raise AiCheckCallError("web call returned an empty answer")
    cites: List[Dict[str, Optional[str]]] = []
    seen = set()
    for a in message.get("annotations") or []:
        c = (a or {}).get("url_citation") or a or {}
        url = c.get("url")
        if url and url not in seen:
            seen.add(url)
            cites.append({"url": url, "title": c.get("title")})
    usage = data.get("usage") or {}
    cost = usage.get("cost")
    return {
        "text": text, "citations": cites,
        "cost_usd": float(cost) if isinstance(cost, (int, float)) else 0.0,
        "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
    }


# ---- seeded names ---------------------------------------------------------------------------------------------------------
def seeded_names(db, client_id) -> Dict[str, List[str]]:
    """The client's active seeded executives and competitors, in rank order."""
    from app.models.seeded_entity import SeededEntity
    rows = db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.status == "active").order_by(
        SeededEntity.kind, SeededEntity.rank).all()
    return {
        "executives": [r.name for r in rows if r.kind == "executive"],
        "competitors": [r.name for r in rows if r.kind == "competitor"],
    }


def prompts_for(db, client) -> List[Dict[str, str]]:
    names = seeded_names(db, client.id)
    return build_prompts(client.name, names["executives"], names["competitors"])


# ---- a run ----------------------------------------------------------------------------------------------------------------
def running_run(db, client_id):
    """A run for this client that is still running (started within RUN_STALE_MINUTES), else None."""
    from app.models.ai_check import AiCheckRun
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=RUN_STALE_MINUTES)
    return db.query(AiCheckRun).filter(
        AiCheckRun.client_id == client_id, AiCheckRun.status == "running", AiCheckRun.started_at >= cutoff
    ).order_by(AiCheckRun.started_at.desc()).first()


def start_run(db, client_id, prompt_count: int = len(PROMPT_DEFS)):
    from app.models.ai_check import AiCheckRun
    est = estimate(prompt_count)
    run = AiCheckRun(id=uuid.uuid4(), client_id=client_id, status="running", model=MODEL, web_results=WEB_RESULTS,
                     repeats=REPEATS, prompt_count=prompt_count, estimated_cost_usd=est["estimated_cost_usd"], cost_usd=0.0)
    db.add(run)
    db.commit()
    return run


def execute_run(db, run, prompts: Sequence[Dict[str, str]], api_key: str, post: Optional[Callable] = None,
                cap_usd: Optional[float] = None, log: Optional[Callable[[str], None]] = None,
                client_name: Optional[str] = None, executives: Sequence[str] = ()):
    """Asks every prompt REPEATS times (repeat by repeat, so a stopped run still has balanced coverage), stores each answer as
    it arrives, and finishes the run row. Stops before a call that could take the cost past the cap."""
    from app.models.ai_check import AiCheckAnswer
    cap = cost_cap_usd() if cap_usd is None else cap_usd
    say = log or (lambda m: None)
    capped = False
    aborted = False
    consecutive_failures = 0
    last_error = None
    try:
        for rep, p in itertools.product(range(REPEATS), prompts):
            if run.cost_usd + EST_COST_PER_CALL > cap:
                capped = True
                break
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                aborted = True
                break
            try:
                r = ask_with_web(p["text"], api_key, post=post)
            except AiCheckCallError as e:
                run.calls_failed += 1
                consecutive_failures += 1
                last_error = str(e)
                db.commit()
                say(f"  FAILED {p['key']} #{rep + 1}: {last_error}")
                continue
            consecutive_failures = 0
            urls = r["citations"]
            domains = sorted({d for d in (domain_of(c["url"]) for c in urls) if d})
            db.add(AiCheckAnswer(
                id=uuid.uuid4(), run_id=run.id, client_id=run.client_id, prompt_key=p["key"], prompt_text=p["text"], repeat_index=rep,
                answer_text=r["text"], cited_urls=urls, cited_domains=domains, cost_usd=r["cost_usd"],
                tokens_prompt=r["prompt_tokens"], tokens_completion=r["completion_tokens"],
            ))
            run.calls_ok += 1
            run.cost_usd = (run.cost_usd or 0.0) + r["cost_usd"]
            db.commit()
            say(f"  ok {p['key']} #{rep + 1}  ${r['cost_usd']:.4f}  {len(urls)} pages  (run total ${run.cost_usd:.4f})")
        if aborted or run.calls_ok == 0:
            run.status = "failed"
        else:
            run.status = "stopped_at_cap" if capped else "completed"
        if run.calls_failed:
            run.error = (last_error or "a web call failed")[:1000]
        elif run.calls_ok == 0:
            run.error = "no answers"
    except Exception as e:                                   # never leave a run "running" forever
        db.rollback()
        run.status = "failed"
        run.error = repr(e)[:1000]
    run.finished_at = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    # Serious-accusation triage of the stored answers (triage.py). Only when the run produced answers and still has budget; a failure
    # here never changes the run's status or its answers.
    if run.calls_ok > 0 and not capped and not aborted:
        try:
            _triage(db, run, api_key, post, cap, say, client_name, executives)
        except Exception as e:
            db.rollback()
            say(f"  triage failed: {e!r}"[:300])
    return run


def _triage(db, run, api_key, post, cap, say, client_name, executives) -> None:
    from app.models.ai_check import AiCheckAnswer
    from app.models.client import Client
    from app.services.ai_check.triage import triage_run
    name = client_name or (db.query(Client.name).filter(Client.id == run.client_id).scalar() or "the company")
    rows = db.query(AiCheckAnswer).filter(AiCheckAnswer.run_id == run.id).order_by(AiCheckAnswer.prompt_key, AiCheckAnswer.repeat_index).all()
    answers = [{"prompt_key": r.prompt_key, "repeat_index": r.repeat_index, "text": r.answer_text, "cited_domains": r.cited_domains} for r in rows]
    n = triage_run(db, run, name, list(executives), answers, api_key, post=post, cap_usd=cap, log=say)
    db.commit()
    say(f"  triage done: {n} sentences flagged (run total ${run.cost_usd:.4f})")


def run_in_background(run_id, client_id) -> None:
    """Entry point for FastAPI BackgroundTasks: its own DB session, the key from the environment."""
    from app.core.db import SessionLocal
    from app.models.ai_check import AiCheckRun
    from app.models.client import Client
    db = SessionLocal()
    try:
        run = db.query(AiCheckRun).filter(AiCheckRun.id == run_id).first()
        client = db.query(Client).filter(Client.id == client_id).first()
        if run is None or client is None:
            return
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            run.status, run.error, run.finished_at = "failed", "OPENROUTER_API_KEY is not set", datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            return
        execute_run(db, run, prompts_for(db, client), key, client_name=client.name, executives=seeded_names(db, client.id)["executives"])
    finally:
        db.close()


# ---- reading it back --------------------------------------------------------------------------------------------------------
def short_answer(text: Optional[str], limit: int = 320) -> str:
    """A plain one-paragraph digest of an answer: links and markdown removed, headings dropped, cut at a sentence end."""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text or "")
    t = re.sub(r"[*_`#>|]+", "", t)
    lines = [ln.strip(" -•\t") for ln in t.splitlines() if ln.strip(" -•\t")]
    body = [ln for ln in lines if len(ln.split()) > 6 or ln.endswith(".")]
    s = " ".join(body or lines).strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) <= limit:
        return s
    cut = s[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end >= limit * 0.5 else cut.rstrip() + "…")


def _url_sets(answers) -> List[frozenset]:
    return [frozenset(c.get("url") for c in (a.cited_urls or []) if c.get("url")) for a in answers]


def source_stability(answers) -> Dict[str, Any]:
    """Whether the repeats of one question cited the same pages. stable is None when there is only one answer."""
    sets = _url_sets(answers)
    n = len(sets)
    if n < 2:
        return {"stable": None, "shared": None, "text": "Only one run, so stability is unknown."}
    union = frozenset().union(*sets)
    inter = frozenset.intersection(*sets)
    shared = (len(inter) / len(union)) if union else 1.0
    if all(s == sets[0] for s in sets):
        return {"stable": True, "shared": 1.0, "text": f"Same pages cited in all {n} runs."}
    return {"stable": False, "shared": round(shared, 2), "text": f"Cited pages changed between the {n} runs ({round(shared * 100)}% of pages shared)."}


def _report_run(run) -> Dict[str, Any]:
    def iso(d):
        return d.isoformat() if d else None
    return {
        "id": str(run.id), "status": run.status, "started_at": iso(run.started_at), "finished_at": iso(run.finished_at),
        "cost_usd": run.cost_usd, "estimated_cost_usd": run.estimated_cost_usd, "calls_ok": run.calls_ok,
        "calls_failed": run.calls_failed, "repeats": run.repeats, "prompt_count": run.prompt_count, "model": run.model,
        "web_results": run.web_results, "error": run.error,
    }


def latest_report(db, client, is_admin: bool = False) -> Dict[str, Any]:
    """What the Brand Equity card shows: the client's latest run, per question a short answer, its cited domains with their
    reliability, a stability marker, and the cited pages from low-reliability outlets. The same pages also come back as
    `removal_candidates`, for super admins only (internal, needs legal review)."""
    from app.models.ai_check import AiCheckAnswer, AiCheckRun
    run = db.query(AiCheckRun).filter(AiCheckRun.client_id == client.id).order_by(AiCheckRun.started_at.desc()).first()
    if run is None:
        return {"enabled": True, "run": None, "prompts": [], "low_reliability_pages": [], "removal_candidates": [], "claim_checks": []}
    answers = db.query(AiCheckAnswer).filter(AiCheckAnswer.run_id == run.id).order_by(
        AiCheckAnswer.prompt_key, AiCheckAnswer.repeat_index).all()
    by_key: Dict[str, list] = {}
    for a in answers:
        by_key.setdefault(a.prompt_key, []).append(a)

    pages: Dict[str, Dict[str, Any]] = {}
    prompts_out = []
    for key, label, _ in PROMPT_DEFS:
        group = by_key.get(key)
        if not group:
            continue
        domain_runs: Dict[str, set] = {}
        for a in group:
            for c in a.cited_urls or []:
                url = c.get("url")
                d = domain_of(url)
                if not d:
                    continue
                domain_runs.setdefault(d, set()).add(a.repeat_index)
                cls = classify_domain(d, client.name)
                if cls["low_reliability"]:
                    pg = pages.setdefault(url, {"url": url, "title": c.get("title"), "domain": d, "tier": cls["tier"],
                                                "reliability": cls["label"], "proposed": cls["proposed"], "questions": [], "_runs": set()})
                    if label not in pg["questions"]:
                        pg["questions"].append(label)
                    pg["_runs"].add((key, a.repeat_index))
                    if not pg.get("title") and c.get("title"):
                        pg["title"] = c.get("title")
        sources = []
        for d, reps in sorted(domain_runs.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            cls = classify_domain(d, client.name)
            sources.append({"domain": d, "tier": cls["tier"], "reliability": cls["label"], "low_reliability": cls["low_reliability"],
                            "proposed": cls["proposed"], "cited_in_runs": len(reps)})
        stab = source_stability(group)
        prompts_out.append({
            "key": key, "label": label, "question": group[0].prompt_text, "runs": len(group),
            "short_answer": short_answer(group[0].answer_text),
            "sources": sources, "stable": stab["stable"], "stability": stab["text"], "pages_shared": stab["shared"],
        })

    low_pages = []
    for pg in pages.values():
        pg["cited_in_answers"] = len(pg.pop("_runs"))
        low_pages.append(pg)
    low_pages.sort(key=lambda p: (-p["cited_in_answers"], p["domain"], p["url"]))
    claim_checks = []
    if is_admin:
        from app.models.ai_check import AiCheckFlag
        from app.services.ai_check import claims
        flags = db.query(AiCheckFlag).filter(AiCheckFlag.run_id == run.id, AiCheckFlag.flagged.is_(True)).order_by(AiCheckFlag.created_at).all()
        claim_checks = claims.build_claim_checks(db, client, flags, {k: label for k, label, _ in PROMPT_DEFS})
    return {
        "enabled": True,
        "run": _report_run(run),
        "prompts": prompts_out,
        "low_reliability_pages": low_pages,
        "removal_candidates": list(low_pages) if is_admin else [],
        "claim_checks": claim_checks,
    }
