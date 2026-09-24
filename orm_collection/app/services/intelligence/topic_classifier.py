import os
import structlog
import numpy as np
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.core import nlp_cache
from app.models.document import Document
from app.models.topic import Topic, DocumentTopic
from app.models.system import ModelRun
from transformers import pipeline

logger = structlog.get_logger()

# BART-MNLI 17/17 calibration fix, 2026-09-15.
#
# "This document discusses {}." was tried here as a replacement for the
# pipeline's bare default ("This example is {}."), on the theory that framing
# the label as a topic being discussed (vs. a category match) would reduce
# over-firing. REVERTED after testing against two real production documents
# pulled read-only from the live DB:
#   - The actual reported 17/17 document (id f8f4fd56-..., a Reddit billing
#     complaint) fires 17/17 under BOTH templates (~0.96-0.98 either way) --
#     the new template did not help the failure it was meant to fix.
#   - A real, already-correctly-classified multi-topic document (id
#     514ec084-..., an OpenAI/Anthropic academic credit dispute) went from
#     7/17 firing under the old template (closely matching what's actually
#     written to document_topics: Innovation, Competition, Executive
#     Leadership, Legal Risk, Product Launch) to 15/17 under the new one --
#     a regression that breaks a document that was working.
# Kept the pipeline's own default rather than reintroducing a template this
# environment couldn't validate as an improvement.
HYPOTHESIS_TEMPLATE = "This example is {}."

# Bump this whenever HYPOTHESIS_TEMPLATE or the postprocessing logic below
# changes, so nlp_cache (keyed by text+labels+model, TTL 30 days) never
# serves scores computed under a stale template/logic under the old key.
TOPIC_SCORING_SCHEMA_VERSION = "dual-score-v1"

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

    def _run_dual_pass(self, text: str, candidate_labels: List[str]) -> Tuple[List[float], List[float]]:
        """
        Run ONE forward pass through the zero-shot pipeline and derive BOTH
        postprocessing variants from the same entailment/contradiction logits
        (transformers==5.12.1, ZeroShotClassificationPipeline.postprocess):

          - independent scores (multi_label=True's postprocessing): each
            label's own softmax vs. its own contradiction score, with zero
            competition between labels -- this is why a document can hit
            0.97+ on every one of 17 topics at once.
          - competing scores (multi_label=False's postprocessing): the
            entailment logits softmaxed across the WHOLE candidate label set,
            forcing labels to compete for probability mass.

        This mirrors ChunkPipeline.run_single up to (not including) its final
        postprocess() call, reusing the pipeline's own preprocess()/forward()
        so tokenization, truncation, device placement and no_grad handling
        are untouched -- only the last softmax step is duplicated (once each
        way) instead of a second full model forward pass.

        2026-09-20: label dimension is now batched into a single padded
        forward() call instead of one forward() call per label (previously
        17 sequential CPU passes/doc -- see PART_F forensics report §1.2).
        preprocess() still yields one unbatched (1, seq_len) example per
        label; we pad them together ourselves via the tokenizer's own
        public pad() API (the same padding tokenizer.pad_token_id /
        padding_side the pipeline's internal batching would use, see
        transformers.pipelines.base.pad_collate_fn) and run them through
        the model in one shot. Verified numerically equivalent (max abs
        diff ~1e-6, float32 noise) to the old per-label loop on real
        documents against the real model -- see
        scripts/verify_topic_batching_equivalence.py.
        """
        model_input_items = list(
            self.classifier.preprocess(
                text, candidate_labels=candidate_labels, hypothesis_template=HYPOTHESIS_TEMPLATE
            )
        )
        model_input_names = self.classifier.tokenizer.model_input_names
        encodings = [
            {name: item[name][0].tolist() for name in model_input_names}
            for item in model_input_items
        ]
        padded = self.classifier.tokenizer.pad(encodings, padding=True, return_tensors="pt")

        # candidate_label/sequence/is_last are required keys of _forward's
        # input contract but are only echoed back into its output, which we
        # never read below -- placeholder values are fine.
        batched_inputs = dict(padded)
        batched_inputs["candidate_label"] = candidate_labels[0]
        batched_inputs["sequence"] = text
        batched_inputs["is_last"] = True

        model_output = self.classifier.forward(batched_inputs)
        logits = model_output["logits"].float().numpy()
        n = len(candidate_labels)
        reshaped = logits.reshape((1, n, -1))[0]  # (n_labels, n_nli_classes)

        entailment_id = self.classifier.entailment_id
        contradiction_id = -1 if entailment_id == 0 else 0

        entail_contr = reshaped[:, [contradiction_id, entailment_id]]
        independent = np.exp(entail_contr) / np.exp(entail_contr).sum(-1, keepdims=True)
        independent_scores = independent[:, 1].tolist()

        entail_logits = reshaped[:, entailment_id]
        competing = np.exp(entail_logits) / np.exp(entail_logits).sum(-1, keepdims=True)
        competing_scores = competing.tolist()

        return independent_scores, competing_scores

    def classify_text(self, text: str, candidate_labels: List[str]) -> Dict[str, Any]:
        if self.use_mock:
            # Mock behavior for fast testing
            import random
            independent = [random.uniform(0.1, 0.9) for _ in candidate_labels]
            total = sum(independent) or 1.0
            return {
                "sequence": text,
                "labels": candidate_labels,
                "scores": independent,
                "competing_scores": [s / total for s in independent]
            }

        if not text or not candidate_labels:
            return {"sequence": text, "labels": [], "scores": [], "competing_scores": []}

        # Section 6: result depends on the text, the candidate label set (a
        # taxonomy change must miss, not serve a stale label set), the
        # hypothesis template and the postprocessing logic -- all go into the
        # key (labels sorted so their order doesn't affect the hash).
        cache_key = nlp_cache.make_key(
            "topic", self.model_name, text, "|".join(sorted(candidate_labels)),
            HYPOTHESIS_TEMPLATE, TOPIC_SCORING_SCHEMA_VERSION
        )
        cached = nlp_cache.get_cached(cache_key)
        if cached is not None:
            return cached

        independent_scores, competing_scores = self._run_dual_pass(text, candidate_labels)
        result = {
            "sequence": text,
            "labels": candidate_labels,
            "scores": independent_scores,
            "competing_scores": competing_scores
        }
        nlp_cache.set_cached(cache_key, result)
        return result

    def classify_batch(self, texts: List[str], candidate_labels: List[str], batch_size: int = 16) -> List[Dict[str, Any]]:
        if self.use_mock:
            import random
            results = []
            for text in texts:
                independent = [random.uniform(0.1, 0.9) for _ in candidate_labels]
                total = sum(independent) or 1.0
                results.append({
                    "sequence": text,
                    "labels": candidate_labels,
                    "scores": independent,
                    "competing_scores": [s / total for s in independent]
                })
            return results

        if not texts or not candidate_labels:
            return [{"sequence": text, "labels": [], "scores": [], "competing_scores": []} for text in texts]

        # NOTE: this no longer uses the pipeline's native multi-text batched
        # call. Getting both the independent AND competing score requires the
        # raw per-label logits (see _run_dual_pass/classify_text above), and
        # this method has no production caller today -- HardenedTopicClassifier
        # .process_batch (topic_classification_batch_processor.py) that calls
        # it is unreferenced by any Celery task -- so replicating
        # ChunkPipeline's native batched collation here wasn't justified.
        # batch_size is accepted for interface compatibility but unused.
        return [self.classify_text(text, candidate_labels) for text in texts]

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
