import os
import structlog
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.topic import Topic, DocumentTopic
from app.models.system import ModelRun
from transformers import pipeline

logger = structlog.get_logger()

class TopicClassifier:
    def __init__(self, use_mock=False):
        # Using distilled BART MNLI for significantly faster CPU inference
        self.model_name = "valhalla/distilbart-mnli-12-3"
        self.model_version = "1.0"

        # Production Mock Protection Guard (C3-F1 / XC-F2), mirrors
        # SentimentAnalyzer's (R6): mock topic classification is strictly
        # forbidden in production to prevent silent random labels.
        is_mock_allowed = os.getenv("TOPIC_MOCK_ALLOWED", "false").lower() == "true"

        if use_mock:
            if not is_mock_allowed:
                raise RuntimeError(
                    "Production Guard Violation: use_mock=True is requested but mock mode is forbidden "
                    "unless the environment variable TOPIC_MOCK_ALLOWED=true is explicitly set."
                )
            self.use_mock = True
        else:
            self.use_mock = False

        if not self.use_mock:
            # In a real production scenario, this might run on a GPU or a dedicated inference server.
            # Using device=-1 for CPU, device=0 for GPU if available.
            try:
                import torch
                device = 0 if torch.cuda.is_available() else -1
                self.classifier = pipeline("zero-shot-classification", model=self.model_name, device=device)
            except Exception as e:
                # If loading fails in production/non-mock mode, we do NOT fallback to mock!
                # We raise a hard failure so that the reliability mechanism (retries, state machine) can capture it.
                if not is_mock_allowed:
                    raise RuntimeError(f"Fatal error: Failed to load BART topic classification model in production/hard mode: {e}") from e
                else:
                    logger.critical("topic_classifier_model_load_failed_falling_back_to_mock", error=str(e))
                    self.use_mock = True

    def classify_text(self, text: str, candidate_labels: List[str]) -> Dict[str, Any]:
        if self.use_mock:
            # Mock behavior for fast testing
            import random
            return {
                "sequence": text,
                "labels": candidate_labels,
                "scores": [random.uniform(0.1, 0.9) for _ in candidate_labels]
            }

        if not text or not candidate_labels:
            return {"sequence": text, "labels": [], "scores": []}

        # The pipeline supports multi_label=True so a document can have multiple independent topics
        result = self.classifier(text, candidate_labels, multi_label=True)
        return result

    def classify_batch(self, texts: List[str], candidate_labels: List[str], batch_size: int = 16) -> List[Dict[str, Any]]:
        if self.use_mock:
            import random
            return [
                {
                    "sequence": text,
                    "labels": candidate_labels,
                    "scores": [random.uniform(0.1, 0.9) for _ in candidate_labels]
                }
                for text in texts
            ]

        if not texts or not candidate_labels:
            return [{"sequence": text, "labels": [], "scores": []} for text in texts]

        # Use native HuggingFace pipeline batching
        results = self.classifier(texts, candidate_labels, multi_label=True, batch_size=batch_size)
        if isinstance(results, dict):
            return [results]
        return results

    def process_document(self, db: Session, document_id: str, threshold: float = 0.5):
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document or not document.normalized_content:
            return

        # Fetch active topics from the taxonomy
        active_topics = db.query(Topic).filter(Topic.is_active == True).all()
        if not active_topics:
            return

        topic_names = [t.name for t in active_topics]
        topic_map = {t.name: t.id for t in active_topics}

        # Classify the document text
        results = self.classify_text(document.normalized_content, topic_names)
        
        # Store multiple topics per document if they exceed the threshold
        for label, score in zip(results["labels"], results["scores"]):
            if score >= threshold:
                doc_topic = DocumentTopic(
                    document_id=document.id,
                    topic_id=topic_map[label],
                    confidence_score=score
                )
                db.add(doc_topic)

        # Log the model run
        run_log = ModelRun(
            document_id=document.id,
            model_name=self.model_name,
            model_version=self.model_version
        )
        db.add(run_log)

        # Update document status
        document.processing_status = "COMPLETED" # simplified for this phase alone
        
        db.commit()
