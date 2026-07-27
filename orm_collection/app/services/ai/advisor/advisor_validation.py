import json
import structlog
from typing import Any, Dict, List, Set
from app.services.ai.advisor.advisor_schema import ReputationAdvisorResponse
from app.services.ai.advisor.advisor_exceptions import ValidationException

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
    """Extracts significant lowercase alphanumeric words from a string."""
    words = text.lower().replace(",", " ").replace(".", " ").replace(";", " ").replace(":", " ").split()
    return {w for w in words if w.isalnum() and w not in STOP_WORDS and len(w) > 2}

def verify_semantic_grounding(text: str, cited_objs: List[Dict[str, Any]]) -> bool:
    """
    A1: Semantic Grounding Verification.
    Verifies that at least one key keyword, entity, or topic mentioned in the text
    is present in the cited objects' titles, names, descriptions, or categories.
    """
    if not text:
        return True
    if not cited_objs:
        return False

    text_tokens = clean_and_tokenize(text)
    if not text_tokens:
        return True  # Nothing significant to ground

    # Build the corpus of the cited objects
    corpus_tokens: Set[str] = set()
    for obj in cited_objs:
        # Check standard fields across different model schemas
        for field in ["title", "narrative_name", "narrative_type", "summary_text", "executive_name", "competitor_name", "risk_level", "alert_type", "severity"]:
            val = obj.get(field)
            if val:
                corpus_tokens.update(clean_and_tokenize(str(val)))
        # Check list fields like risk factors
        for factor in obj.get("risk_factors", []):
            if isinstance(factor, dict):
                for val in factor.values():
                    corpus_tokens.update(clean_and_tokenize(str(val)))
            else:
                corpus_tokens.update(clean_and_tokenize(str(factor)))
                
    # We require at least one intersecting keyword for semantic grounding
    intersection = text_tokens.intersection(corpus_tokens)
    return len(intersection) > 0

def validate_advisor_response(response_dict: Dict[str, Any], context: Dict[str, Any]) -> ReputationAdvisorResponse:
    """
    Hardened Validation Pipeline:
    1. Schema Validation (Pydantic)
    2. Mandatory Citations Verification (A2)
    3. Grounding & Hallucination Checks (A1)
    4. Business Rule Consistency Checks (A3)
    5. Action Prioritization Calibration (A10)
    """
    # --- 1. Schema Validation ---
    try:
        validated_response = ReputationAdvisorResponse(**response_dict)
    except Exception as e:
        logger.error("advisor_validation_schema_failed", error=str(e))
        raise ValidationException(f"Advisor response failed schema validation: {e}")

    # --- 2. Mandatory Citations Verification (A2) ---
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
        logger.error("advisor_validation_missing_global_citations")
        raise ValidationException("Advisor response rejected: Global citations cannot be empty.")

    # Filter out any individual items that do not have any citations (A2)
    for list_name in ["major_risks", "positive_signals", "negative_signals", "executive_analysis", "competitor_position", "priority_actions_24h", "priority_actions_7d", "priority_actions_30d"]:
        items = getattr(validated_response, list_name, [])
        filtered_items = [item for item in items if has_any_citation(item.citations)]
        if len(items) != len(filtered_items):
            logger.info("advisor_validation_pruned_uncited_items", list=list_name, original_count=len(items), pruned_count=len(items) - len(filtered_items))
        setattr(validated_response, list_name, filtered_items)

    # --- 3. Grounding & Hallucination Checks (A1) ---
    # Extract all valid objects from context in O(1) maps
    doc_map = {str(d["id"]): d for d in context.get("documents", [])}
    narrative_map = {str(n["id"]): n for n in context.get("narratives", [])}
    risk_map = {str(r["id"]): r for r in context.get("risks", [])}
    alert_map = {str(a["id"]): a for a in context.get("alerts", [])}
    trend_map = {str(t["id"]): t for t in context.get("trends", [])}
    
    # Map for competitor & executive info
    exec_map = {str(er["id"]): er for er in context.get("executives", [])}
    bench_map = {str(b.get("competitor_name", "")): b for b in context.get("benchmarks", [])}

    def get_cited_objects(citations_obj) -> List[Dict[str, Any]]:
        objs = []
        for did in getattr(citations_obj, "document_ids", []):
            if did not in doc_map:
                raise ValidationException(f"Hallucinated document ID cited: {did}")
            objs.append(doc_map[did])
        for nid in getattr(citations_obj, "narrative_ids", []):
            if nid not in narrative_map:
                raise ValidationException(f"Hallucinated narrative ID cited: {nid}")
            objs.append(narrative_map[nid])
        for rid in getattr(citations_obj, "risk_ids", []):
            if rid not in risk_map:
                raise ValidationException(f"Hallucinated risk ID cited: {rid}")
            objs.append(risk_map[rid])
        for aid in getattr(citations_obj, "alert_ids", []):
            if aid not in alert_map:
                raise ValidationException(f"Hallucinated alert ID cited: {aid}")
            objs.append(alert_map[aid])
        for tid in getattr(citations_obj, "trend_ids", []):
            if tid not in trend_map:
                raise ValidationException(f"Hallucinated trend ID cited: {tid}")
            objs.append(trend_map[tid])
        return objs

    # Run Semantic Grounding Verification on all items
    for list_name in ["major_risks", "priority_actions_24h", "priority_actions_7d", "priority_actions_30d"]:
        items = getattr(validated_response, list_name, [])
        for i, item in enumerate(items):
            cited_objs = get_cited_objects(item.citations)
            text_to_ground = f"{item.action} {item.evidence_backing}"
            if not verify_semantic_grounding(text_to_ground, cited_objs):
                logger.error("advisor_validation_semantic_grounding_failed", list=list_name, index=i, text=text_to_ground)
                raise ValidationException(f"Recommendation at {list_name}[{i}] fails semantic grounding: Cited evidence does not support the statement.")

    # --- 4. Business Rule Consistency Checks (A3) ---
    # Rule A: If critical alerts exist, AI cannot recommend "No immediate action required" or similar low priority/no action text.
    has_critical_alerts = any(a["severity"] == "CRITICAL" for a in context.get("alerts", []))
    if has_critical_alerts:
        all_actions_text = " ".join([item.action.lower() for item in validated_response.priority_actions_24h])
        if "no immediate action" in all_actions_text or "no action" in all_actions_text or not validated_response.priority_actions_24h:
            logger.error("business_rule_violation_critical_alert_unaddressed")
            raise ValidationException("Business rule violation: Critical alerts exist, but the advisor recommends no immediate action.")

    # Rule B: If overall reputation sentiment is highly negative (e.g., < -0.25), AI cannot describe reputation as improving.
    reputation_data = context.get("reputation")
    if reputation_data:
        sentiment_comp = reputation_data.get("sentiment_component", 50.0)
        # sentiment_component ranges 0 to 100. < 40 indicates negative sentiment
        if sentiment_comp < 40.0:
            assessment_lower = validated_response.overall_assessment.lower()
            if "improving" in assessment_lower or "excellent" in assessment_lower or "stable" in assessment_lower:
                logger.error("business_rule_violation_reputation_trend_contradiction")
                raise ValidationException("Business rule violation: Reputation sentiment is negative, but advisor claims reputation is improving or stable.")

    # Rule C: If risk score is critical (> 75), AI cannot classify the situation as low priority.
    highest_risk = max([r["risk_score"] for r in context.get("risks", [])] + [0.0])
    if highest_risk > 75.0:
        # Verify we have at least one HIGH priority action in 24h or 7d
        all_priorities = [item.priority for item in validated_response.priority_actions_24h + validated_response.priority_actions_7d]
        if "HIGH" not in all_priorities:
            logger.error("business_rule_violation_high_risk_low_priority")
            raise ValidationException("Business rule violation: Critical risk exists, but no HIGH priority actions are recommended.")

    # Rule D: If coverage is LOW (< 50%), AI cannot make highly confident recommendations (confidence >= 0.8).
    context_meta = context.get("metadata", {})
    coverage_score = context_meta.get("data_coverage", {}).get("coverage_score", 0.0)
    if coverage_score < 50.0 and validated_response.confidence >= 0.8:
        logger.error("business_rule_violation_high_confidence_low_coverage")
        raise ValidationException("Business rule violation: Data coverage is low, but advisor confidence is set too high.")

    # --- 5. Action Prioritization Calibration (A10) ---
    # Enforce maximum 2 HIGH actions across 24h, demoting the rest to MEDIUM
    def calibrate_priorities(action_list: List[Any]):
        high_count = 0
        for item in action_list:
            if item.priority == "HIGH":
                high_count += 1
                if high_count > 2:
                    item.priority = "MEDIUM"

    def clean_action_verbs(action_list: List[Any]):
        import re
        for item in action_list:
            if item.action.lower().startswith("monitor "):
                item.action = "Analyze and address " + item.action[8:]
            else:
                item.action = re.sub(r"\bmonitor\b", "proactively address", item.action, flags=re.IGNORECASE)

    calibrate_priorities(validated_response.priority_actions_24h)
    calibrate_priorities(validated_response.priority_actions_7d)
    calibrate_priorities(validated_response.priority_actions_30d)

    clean_action_verbs(validated_response.priority_actions_24h)
    clean_action_verbs(validated_response.priority_actions_7d)
    clean_action_verbs(validated_response.priority_actions_30d)
    clean_action_verbs(validated_response.major_risks)

    return validated_response
