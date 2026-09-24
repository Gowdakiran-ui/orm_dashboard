"""
Equivalence check for the 2026-09-20 label-batching change to
TopicClassifier._run_dual_pass: compares the OLD (17 sequential forward()
calls, reimplemented here verbatim from git history) against the actual
NEW _run_dual_pass now shipped in topic_classifier.py (single padded
batched forward() call). Loads the REAL valhalla/distilbart-mnli-12-3
model (already cached locally) -- no mocks. Prints max abs/rel diff per doc
across both independent and competing scores.

Run: python scripts/verify_topic_batching_equivalence.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("TOPIC_MOCK_ALLOWED", "false")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

from app.services.intelligence.topic_classifier import TopicClassifier, HYPOTHESIS_TEMPLATE

TOPICS = [
    "Financial Performance", "Product Launch", "Data Breach / Security",
    "Executive Leadership", "Legal / Regulatory", "Layoffs / Restructuring",
    "Customer Service", "ESG / Sustainability", "Partnership / Merger",
    "Controversy / Scandal", "Innovation", "Competition", "Fraud",
    "Regulatory Action", "Employee Complaints", "Funding", "General News",
]
assert len(TOPICS) == 17

DOCS = [
    "The company announced massive layoffs today affecting 10,000 employees "
    "as part of a broader restructuring plan following disappointing quarterly results.",
    "A severe data breach compromised millions of user passwords after attackers "
    "exploited an unpatched vulnerability in the company's authentication service.",
    "Q3 earnings beat expectations, showing strong financial performance across "
    "every business segment, with revenue up 22% year over year and margins expanding.",
    "Short doc.",
    "We are thrilled to announce the launch of our new AI-powered product line, "
    "which the CEO says represents the biggest innovation in the company's history "
    "and positions it well against emerging competition in the space, while also "
    "addressing longstanding customer service complaints raised over the past year "
    "and reassuring investors amid ongoing regulatory scrutiny from multiple agencies "
    "following a series of executive leadership changes and a contested funding round.",
    "Employees are staging a walkout over unfair labor practices, alleging retaliation "
    "against whistleblowers who raised fraud concerns to regulators months ago.",
    "Ünïcödé tëxt wïth spëcïål chäräctërs and emoji 🚀📉 to stress the tokenizer's padding path.",
]


def old_run_dual_pass(classifier, text, candidate_labels):
    model_outputs = [
        classifier.forward(model_inputs)
        for model_inputs in classifier.preprocess(
            text, candidate_labels=candidate_labels, hypothesis_template=HYPOTHESIS_TEMPLATE
        )
    ]
    logits = np.concatenate([o["logits"].float().numpy() for o in model_outputs])
    n = len(candidate_labels)
    reshaped = logits.reshape((1, n, -1))[0]

    entailment_id = classifier.entailment_id
    contradiction_id = -1 if entailment_id == 0 else 0

    entail_contr = reshaped[:, [contradiction_id, entailment_id]]
    independent = np.exp(entail_contr) / np.exp(entail_contr).sum(-1, keepdims=True)
    independent_scores = independent[:, 1].tolist()

    entail_logits = reshaped[:, entailment_id]
    competing = np.exp(entail_logits) / np.exp(entail_logits).sum(-1, keepdims=True)
    competing_scores = competing.tolist()

    return independent_scores, competing_scores


def main():
    print("Loading real TopicClassifier (valhalla/distilbart-mnli-12-3, CPU)...")
    # NOTE: this local sandbox's torch/transformers pair (2.5.1 / 5.15.0) refuses
    # to torch.load() the cached pytorch_model.bin (CVE-2025-32434 guard) even
    # though a model.safetensors is also cached. Production pins
    # transformers==5.12.1 and is unaffected by this local-only loader quirk;
    # forcing safetensors here only works around it for this verification run.
    import transformers.pipelines as _pipelines_module
    _real_pipeline = _pipelines_module.pipeline

    def _pipeline_forcing_safetensors(*args, **kwargs):
        kwargs.setdefault("model_kwargs", {}).setdefault("use_safetensors", True)
        return _real_pipeline(*args, **kwargs)

    _pipelines_module.pipeline = _pipeline_forcing_safetensors
    import app.services.intelligence.topic_classifier as topic_classifier_module
    topic_classifier_module.pipeline = _pipeline_forcing_safetensors

    tc = TopicClassifier(use_mock=False)
    pipe = tc.classifier

    max_abs_diff_overall = 0.0
    max_rel_diff_overall = 0.0

    for i, doc in enumerate(DOCS):
        old_ind, old_comp = old_run_dual_pass(pipe, doc, TOPICS)
        new_ind, new_comp = tc._run_dual_pass(doc, TOPICS)

        old_all = np.array(old_ind + old_comp)
        new_all = np.array(new_ind + new_comp)

        abs_diff = np.abs(old_all - new_all)
        rel_diff = abs_diff / np.maximum(np.abs(old_all), 1e-12)

        max_abs = abs_diff.max()
        max_rel = rel_diff.max()
        max_abs_diff_overall = max(max_abs_diff_overall, max_abs)
        max_rel_diff_overall = max(max_rel_diff_overall, max_rel)

        status = "OK" if max_abs < 1e-4 else "MISMATCH"
        print(f"doc[{i}] len={len(doc):4d} max_abs_diff={max_abs:.3e} max_rel_diff={max_rel:.3e} -> {status}")
        if status == "MISMATCH":
            print("  old_independent:", [round(x, 6) for x in old_ind])
            print("  new_independent:", [round(x, 6) for x in new_ind])
            print("  old_competing:  ", [round(x, 6) for x in old_comp])
            print("  new_competing:  ", [round(x, 6) for x in new_comp])

    print()
    print(f"OVERALL max_abs_diff={max_abs_diff_overall:.3e} max_rel_diff={max_rel_diff_overall:.3e}")
    if max_abs_diff_overall < 1e-4:
        print("RESULT: EQUIVALENT (within float tolerance)")
    else:
        print("RESULT: NOT EQUIVALENT")


if __name__ == "__main__":
    main()
