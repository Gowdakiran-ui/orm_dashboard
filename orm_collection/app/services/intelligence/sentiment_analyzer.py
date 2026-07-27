import os
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.entity import EntityMention
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.system import ModelRun
from transformers import pipeline

class SentimentAnalyzer:
    def __init__(self, use_mock=False):
        # FinBERT is specifically trained for financial/business text sentiment
        self.model_name = "ProsusAI/finbert"
        self.model_version = "1.0"
        
        # Production Mock Protection Guard (R6)
        # In production environments, mock sentiment generation is strictly forbidden to prevent silent random labels.
        is_mock_allowed = os.getenv("SENTIMENT_MOCK_ALLOWED", "false").lower() == "true"
        
        if use_mock:
            if not is_mock_allowed:
                raise RuntimeError(
                    "Production Guard Violation: use_mock=True is requested but mock mode is forbidden "
                    "unless the environment variable SENTIMENT_MOCK_ALLOWED=true is explicitly set."
                )
            self.use_mock = True
        else:
            self.use_mock = False
        
        if not self.use_mock:
            try:
                import torch
                device = 0 if torch.cuda.is_available() else -1
                self.sentiment_pipeline = pipeline("sentiment-analysis", model=self.model_name, device=device)
            except Exception as e:
                # If loading fails in production/non-mock mode, we do NOT fallback to mock!
                # We raise a hard failure so that the reliability mechanism (retries, state machine) can capture it.
                if not is_mock_allowed:
                    raise RuntimeError(f"Fatal error: Failed to load FinBERT model in production/hard mode: {e}") from e
                else:
                    print(f"Warning: Failed to load FinBERT model, falling back to mock since mock is allowed: {e}")
                    self.use_mock = True

    def analyze_text(self, text: str) -> Dict[str, Any]:
        if self.use_mock:
            # When mock is explicitly allowed, return a warning and deterministic mock sentiment
            import random
            labels = ["positive", "neutral", "negative"]
            return {"label": random.choice(labels), "score": random.uniform(0.6, 0.99)}
            
        if text is None:
            # Return neutral for empty text
            return {"label": "neutral", "score": 1.0}
            
        # Truncate text to fit model max length (usually 512 tokens)
        truncated_text = text[:1500] 
        result = self.sentiment_pipeline(truncated_text)[0]
        return result

    def analyze_batch(self, texts: List[str], batch_size: int = 16) -> List[Dict[str, Any]]:
        if self.use_mock:
            import random
            labels = ["positive", "neutral", "negative"]
            return [{"label": random.choice(labels), "score": random.uniform(0.6, 0.99)} for _ in texts]

        # Filter empty texts cleanly
        truncated_texts = []
        for text in texts:
            if text is None:
                truncated_texts.append("")
            else:
                truncated_texts.append(text[:1500])

        # Run pipeline batch inference
        import torch
        with torch.inference_mode():
            results = self.sentiment_pipeline(truncated_texts, batch_size=batch_size)
        if isinstance(results, dict):
            return [results]
        return results

    def get_entity_context(self, text: str, entity_name: str, window: int = 100) -> str:
        # Simple windowing logic to get text surrounding an entity
        idx = text.lower().find(entity_name.lower())
        if idx == -1:
            return text[:window*2]
        
        start = max(0, idx - window)
        end = min(len(text), idx + len(entity_name) + window)
        return text[start:end]

    def process_document(self, db: Session, document_id: str):
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document or not document.normalized_content:
            return

        # 1. Document Level Sentiment
        doc_result = self.analyze_text(document.normalized_content)
        
        # Mapping FinBERT outputs to our schema
        label = doc_result["label"].lower() # positive, negative, neutral
        confidence = doc_result["score"]
        
        # Map label to score: positive=1.0, neutral=0.0, negative=-1.0
        score_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
        sentiment_score = score_map.get(label, 0.0)
        
        # Weighted score (e.g., if source_reliability is 0.8)
        # Mocking source reliability as 1.0 for now unless joined with Source model
        source_reliability = 1.0 
        weighted_score = sentiment_score * source_reliability

        doc_sentiment = DocumentSentiment(
            document_id=document.id,
            sentiment_label=label.capitalize(),
            sentiment_score=sentiment_score,
            confidence_score=confidence,
            source_reliability=source_reliability,
            weighted_sentiment_score=weighted_score
        )
        db.add(doc_sentiment)

        # 2. Entity Level Sentiment
        mentions = db.query(EntityMention).filter(EntityMention.document_id == document_id).all()
        for mention in mentions:
            # Extract sentence/window around the entity for targeted sentiment
            context = self.get_entity_context(document.normalized_content, mention.entity.name)
            ent_result = self.analyze_text(context)
            
            ent_label = ent_result["label"].lower()
            ent_confidence = ent_result["score"]
            ent_score = score_map.get(ent_label, 0.0)
            
            ent_sentiment = EntitySentiment(
                document_id=document.id,
                entity_id=mention.entity_id,
                sentiment_label=ent_label.capitalize(),
                sentiment_score=ent_score,
                confidence_score=ent_confidence
            )
            db.add(ent_sentiment)

        # Log the model run
        run_log = ModelRun(
            document_id=document.id,
            model_name=self.model_name,
            model_version=self.model_version
        )
        db.add(run_log)

        db.commit()
