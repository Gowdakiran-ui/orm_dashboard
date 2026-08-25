import re
import structlog
from typing import Any, Dict, List, Set
from app.services.ai.crisis_planner.crisis_schema import CrisisPlanResponse
from app.services.ai.crisis_planner.crisis_exceptions import CrisisValidationException

logger = structlog.get_logger()

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at", "by", 
    "for", "with", "about", "against", "between", "into", "through", "during", 
    "before", "after", "above", "below", "to", "from", "up", "down", "in", "out", 
    "on", "off", "over", "under", "again", "further", "then", "once", "here", 
    "there", "all", "any", "both", "each", "few", "more", "most", "other", "some", 
    "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", 
    "s", "t", "can", "will", "just", "don", "should", "now"
}

def clean_and_tokenize(text: str) -> Set[str]:
    words = text.lower().replace(",", " ").replace(".", " ").replace(";", " ").replace(":", " ").split()
    return {w for w in words if w.isalnum() and w not in STOP_WORDS and len(w) > 2}

def verify_semantic_grounding(text: str, cited_objs: List[Dict[str, Any]]) -> bool:
    if not text:
        return True
    if not cited_objs:
        return False

    text_tokens = clean_and_tokenize(text)
    if not text_tokens:
        return True

    corpus_tokens: Set[str] = set()
    for obj in cited_objs:
        for field in ["title", "narrative_name", "narrative_type", "summary_text", "executive_name", "competitor_name", "risk_level", "alert_type", "severity"]:
            val = obj.get(field)
            if val:
                corpus_tokens.update(clean_and_tokenize(str(val)))
        for factor in obj.get("risk_factors", []):
            if isinstance(factor, dict):
                for val in factor.values():
                    corpus_tokens.update(clean_and_tokenize(str(val)))
            else:
                corpus_tokens.update(clean_and_tokenize(str(factor)))
                
    intersection = text_tokens.intersection(corpus_tokens)
    return len(intersection) > 0

def defensive_preprocess_crisis_json(data: Any) -> Dict[str, Any]:
    """Defensively cleans and coerces the raw LLM dict to prevent Pydantic validation failures."""
    if not isinstance(data, dict):
        logger.warning("crisis_validation_raw_data_not_dict_coercing")
        data = {}

    coerced = {}
    
    # String fields
    for field in ["executive_summary", "current_assessment", "business_impact", "executive_communication", "public_communication_strategy"]:
        val = data.get(field, "")
        if isinstance(val, (dict, list)):
            coerced[field] = str(val)
        else:
            coerced[field] = str(val) if val is not None else ""

    # Severity
    sev = str(data.get("severity", "MEDIUM")).upper().strip()
    if sev not in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        sev = "MEDIUM"
    coerced["severity"] = sev

    # Floats
    for field, default_val in [("confidence", 0.5), ("coverage", 0.0)]:
        val = data.get(field)
        try:
            coerced[field] = float(val) if val is not None else default_val
        except (ValueError, TypeError):
            coerced[field] = default_val

    # Lists
    for field in ["monitoring_priorities", "success_metrics"]:
        val = data.get(field, [])
        coerced[field] = [str(x) for x in val] if isinstance(val, list) else []

    # Citations helper
    def clean_citations(c_dict: Any) -> Dict[str, List[str]]:
        if not isinstance(c_dict, dict):
            c_dict = {}
        cleaned = {}
        for key in ["document_ids", "narrative_ids", "risk_ids", "alert_ids", "trend_ids"]:
            val = c_dict.get(key, [])
            cleaned[key] = [str(x) for x in val] if isinstance(val, list) else []
        return cleaned

    # Global citations
    coerced["citations"] = clean_citations(data.get("citations"))

    # Key Drivers list
    drivers = data.get("key_drivers", [])
    cleaned_drivers = []
    if isinstance(drivers, list):
        for d in drivers:
            if not isinstance(d, dict):
                continue
            cleaned_drivers.append({
                "driver": str(d.get("driver", "")),
                "impact_score": float(d.get("impact_score", 0.0)) if d.get("impact_score") is not None else 0.0,
                "description": str(d.get("description", "")),
                "citations": clean_citations(d.get("citations"))
            })
    coerced["key_drivers"] = cleaned_drivers

    # Action Lists
    for field in ["immediate_actions_24h", "short_term_actions_72h", "medium_term_actions_7d"]:
        actions = data.get(field, [])
        cleaned_actions = []
        if isinstance(actions, list):
            for a in actions:
                if not isinstance(a, dict):
                    continue
                cleaned_actions.append({
                    "action": str(a.get("action", "")),
                    "priority": str(a.get("priority", "MEDIUM")).upper(),
                    "evidence_backing": str(a.get("evidence_backing", "")),
                    "citations": clean_citations(a.get("citations"))
                })
        coerced[field] = cleaned_actions

    # Stakeholder Actions
    stakeholders = data.get("stakeholder_actions", [])
    cleaned_stakeholders = []
    if isinstance(stakeholders, list):
        for s in stakeholders:
            if not isinstance(s, dict):
                continue
            steps = s.get("action_steps", [])
            cleaned_stakeholders.append({
                "stakeholder_group": str(s.get("stakeholder_group", "")),
                "strategy": str(s.get("strategy", "")),
                "action_steps": [str(x) for x in steps] if isinstance(steps, list) else [],
                "citations": clean_citations(s.get("citations"))
            })
    coerced["stakeholder_actions"] = cleaned_stakeholders

    # Metadata
    meta = data.get("metadata", {})
    coerced["metadata"] = dict(meta) if isinstance(meta, dict) else {}

    return coerced

def validate_crisis_response(response_dict: Dict[str, Any], context: Dict[str, Any]) -> CrisisPlanResponse:
    """
    Validates the Crisis Plan:
    1. Defensive Pre-processing (Self-Healing)
    2. Schema Validation (Pydantic)
    3. Mandatory Citations Verification
    4. Grounding & Hallucination Checks (Safe filtering of cited IDs)
    5. Business Rule Consistency Checks
    6. Action Prioritization, Deduplication, & Verb Cleaning
    """
    # 1. Defensive Pre-processing
    cleaned_dict = defensive_preprocess_crisis_json(response_dict)

    # 2. Schema Validation
    try:
        validated_response = CrisisPlanResponse(**cleaned_dict)
    except Exception as e:
        logger.error("crisis_validation_schema_failed", error=str(e))
        raise CrisisValidationException(f"Crisis response failed schema validation: {e}")

    # 3. Citation Verification Helper
    def has_any_citation(citations_obj) -> bool:
        if not citations_obj:
            return False
        return any([
            getattr(citations_obj, "document_ids", []),
            getattr(citations_obj, "narrative_ids", []),
            getattr(citations_obj, "risk_ids", []),
            getattr(citations_obj, "alert_ids", []),
            getattr(citations_obj, "trend_ids", [])
        ])
    # Check global citations
    if not has_any_citation(validated_response.citations):
        logger.error("crisis_validation_missing_global_citations")
        raise CrisisValidationException("Crisis response rejected: Global citations cannot be empty.")

    # 4. Grounding & Hallucination Checks (Safe Filtering)
    doc_map = {str(d["id"]): d for d in context.get("documents", [])}
    narrative_map = {str(n["id"]): n for n in context.get("narratives", [])}
    risk_map = {str(r["id"]): r for r in context.get("risks", [])}
    alert_map = {str(a["id"]): a for a in context.get("alerts", [])}
    trend_map = {str(t["id"]): t for t in context.get("trends", [])}

    # C5-F1: reject-and-fallback on a hallucinated citation ID, aligned with
    # the Advisor's get_cited_objects (advisor_validation.py) -- previously
    # this silently stripped the bad ID and logged a warning instead of
    # rejecting, inconsistent with the Advisor for the same failure mode.
    # crisis_planner.py's caller already has a safe "Insufficient evidence"
    # fallback on any CrisisValidationException (see its except Exception
    # block), so rejecting here does not leave a crisis call with no
    # response -- it degrades to that honest fallback instead of a plan
    # built on citations that don't actually exist.
    def get_cited_objects(citations_obj) -> List[Dict[str, Any]]:
        objs = []

        for did in getattr(citations_obj, "document_ids", []):
            if did not in doc_map:
                logger.error("crisis_validation_hallucinated_document_id", id=did)
                raise CrisisValidationException(f"Hallucinated document ID cited: {did}")
            objs.append(doc_map[did])

        for nid in getattr(citations_obj, "narrative_ids", []):
            if nid not in narrative_map:
                logger.error("crisis_validation_hallucinated_narrative_id", id=nid)
                raise CrisisValidationException(f"Hallucinated narrative ID cited: {nid}")
            objs.append(narrative_map[nid])

        for rid in getattr(citations_obj, "risk_ids", []):
            if rid not in risk_map:
                logger.error("crisis_validation_hallucinated_risk_id", id=rid)
                raise CrisisValidationException(f"Hallucinated risk ID cited: {rid}")
            objs.append(risk_map[rid])

        for aid in getattr(citations_obj, "alert_ids", []):
            if aid not in alert_map:
                logger.error("crisis_validation_hallucinated_alert_id", id=aid)
                raise CrisisValidationException(f"Hallucinated alert ID cited: {aid}")
            objs.append(alert_map[aid])

        for tid in getattr(citations_obj, "trend_ids", []):
            if tid not in trend_map:
                logger.error("crisis_validation_hallucinated_trend_id", id=tid)
                raise CrisisValidationException(f"Hallucinated trend ID cited: {tid}")
            objs.append(trend_map[tid])

        return objs

    # Verify citations on all items and verify semantic grounding
    for list_name in ["immediate_actions_24h", "short_term_actions_72h", "medium_term_actions_7d"]:
        items = getattr(validated_response, list_name, [])
        for i, item in enumerate(items):
            cited_objs = get_cited_objects(item.citations)
            if cited_objs:
                text_to_ground = f"{item.action} {item.evidence_backing}"
                if not verify_semantic_grounding(text_to_ground, cited_objs):
                    logger.error("crisis_validation_semantic_grounding_failed", list=list_name, index=i, text=text_to_ground)
                    raise CrisisValidationException(f"Recommendation at {list_name}[{i}] fails semantic grounding.")

    # Verify remaining lists
    for list_name in ["key_drivers", "stakeholder_actions"]:
        items = getattr(validated_response, list_name, [])
        for item in items:
            get_cited_objects(item.citations)

    # Verify global citations
    get_cited_objects(validated_response.citations)

    # Prune items with empty citations
    for list_name in ["immediate_actions_24h", "short_term_actions_72h", "medium_term_actions_7d", "key_drivers", "stakeholder_actions"]:
        items = getattr(validated_response, list_name, [])
        filtered_items = [item for item in items if has_any_citation(item.citations)]
        if len(items) != len(filtered_items):
            logger.info("crisis_validation_pruned_uncited_items", list=list_name, original_count=len(items), pruned_count=len(items) - len(filtered_items))
        setattr(validated_response, list_name, filtered_items)

    # Self-Healing: Aggregate global citations from all valid, filtered items
    global_docs = set(validated_response.citations.document_ids)
    global_narratives = set(validated_response.citations.narrative_ids)
    global_risks = set(validated_response.citations.risk_ids)
    global_alerts = set(validated_response.citations.alert_ids)
    global_trends = set(validated_response.citations.trend_ids)

    for list_name in ["immediate_actions_24h", "short_term_actions_72h", "medium_term_actions_7d", "key_drivers", "stakeholder_actions"]:
        for item in getattr(validated_response, list_name, []):
            global_docs.update(item.citations.document_ids)
            global_narratives.update(item.citations.narrative_ids)
            global_risks.update(item.citations.risk_ids)
            global_alerts.update(item.citations.alert_ids)
            global_trends.update(item.citations.trend_ids)

    validated_response.citations.document_ids = list(global_docs)
    validated_response.citations.narrative_ids = list(global_narratives)
    validated_response.citations.risk_ids = list(global_risks)
    validated_response.citations.alert_ids = list(global_alerts)
    validated_response.citations.trend_ids = list(global_trends)

    # Check global citations
    if not has_any_citation(validated_response.citations):
        logger.error("crisis_validation_missing_global_citations")
        raise CrisisValidationException("Crisis response rejected: Global citations cannot be empty.")

    # 5. Business Rule Consistency Checks
    # Severity Mapping: If critical alerts exist in context, severity must be HIGH or CRITICAL
    has_critical_alerts = any(a["severity"] == "CRITICAL" for a in context.get("alerts", []))
    if has_critical_alerts and validated_response.severity not in ["HIGH", "CRITICAL"]:
        logger.info("crisis_validation_escalating_severity_due_to_critical_alerts")
        validated_response.severity = "CRITICAL"

    # Sentiment Mapping: If overall sentiment component is highly negative (< 40.0), severity cannot be LOW
    reputation_data = context.get("reputation")
    if reputation_data:
        sentiment_comp = reputation_data.get("sentiment_component", 50.0)
        if sentiment_comp < 40.0 and validated_response.severity == "LOW":
            logger.info("crisis_validation_escalating_severity_due_to_negative_sentiment")
            validated_response.severity = "MEDIUM"

    # Confidence check: If coverage < 50%, confidence cannot be >= 0.8
    context_meta = context.get("metadata", {})
    coverage_score = context_meta.get("data_coverage", {}).get("coverage_score", 0.0)
    if coverage_score < 50.0 and validated_response.confidence >= 0.8:
        logger.info("crisis_validation_bounding_confidence_due_to_low_coverage")
        validated_response.confidence = 0.75

    # 6. Action Prioritization, Deduplication, & Verb Cleaning
    seen_actions: Set[str] = set()

    def deduplicate_and_clean_actions(action_list: List[Any]) -> List[Any]:
        unique_items = []
        for item in action_list:
            # Verb cleaning
            if item.action.lower().startswith("monitor "):
                item.action = "Analyze and address " + item.action[8:]
            else:
                item.action = re.sub(r"\bmonitor\b", "proactively address", item.action, flags=re.IGNORECASE)

            # Deduplication
            normalized_action = " ".join(item.action.lower().split())
            if normalized_action in seen_actions:
                logger.info("crisis_validation_duplicate_action_removed", action=item.action)
                continue
            seen_actions.add(normalized_action)
            unique_items.append(item)
        return unique_items

    # Deduplicate across lists in timeline order
    validated_response.immediate_actions_24h = deduplicate_and_clean_actions(validated_response.immediate_actions_24h)
    validated_response.short_term_actions_72h = deduplicate_and_clean_actions(validated_response.short_term_actions_72h)
    validated_response.medium_term_actions_7d = deduplicate_and_clean_actions(validated_response.medium_term_actions_7d)

    # Enforce maximum 2 HIGH actions in 24h
    high_count = 0
    for item in validated_response.immediate_actions_24h:
        if item.priority == "HIGH":
            high_count += 1
            if high_count > 2:
                item.priority = "MEDIUM"

    return validated_response

