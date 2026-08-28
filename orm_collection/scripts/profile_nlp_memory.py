"""
profile_nlp_memory.py — Part 2 of the cross-client-leak / NLP-sizing task.

Measures the real RSS memory footprint of loading FinBERT (sentiment) and
distilbart-mnli-12-3 (topic, zero-shot) in a single process, mirroring
exactly how app/workers/intelligence_tasks.py loads them at module import
time (both instantiated once per worker process, use_mock=False).

Reports RSS at four points:
    1. baseline (python + transformers/torch imported, before either model loads)
    2. after SentimentAnalyzer() loads FinBERT
    3. after TopicClassifier() loads distilbart-mnli-12-3
    4. after running both models over a batch of ~20 realistic documents
       (memory can grow under load from tokenizer buffers / attention
       matrices scaling with the longest sequence in a batch, not just at
       load time)

Run from orm_collection/ with the project venv:
    venv\\Scripts\\python.exe scripts\\profile_nlp_memory.py
"""
import gc
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil

# Same env guards intelligence_tasks.py relies on -- keep both models real,
# never mock, since the whole point is measuring the real footprint.
os.environ.setdefault("SENTIMENT_MOCK_ALLOWED", "false")
os.environ.setdefault("TOPIC_MOCK_ALLOWED", "false")

proc = psutil.Process(os.getpid())


def rss_mb() -> float:
    gc.collect()
    return proc.memory_info().rss / (1024 * 1024)


def report(label: str, start: float):
    now = rss_mb()
    print(f"{label:40s} RSS={now:8.1f} MB   (+{now - start:7.1f} MB since baseline)")
    return now


# ~20 realistic documents, mirroring the "20 clients" target scale for
# Part 2's under-load measurement -- varied length financial/business news
# snippets (short headlines through multi-sentence bodies), the same shape
# SentimentAnalyzer.analyze_text / TopicClassifier.classify_text see live
# (truncated to 1500 chars there; none of these need truncation).
SAMPLE_DOCS = [
    "Acme Corp reported record quarterly revenue, beating analyst expectations by 12%.",
    "The CEO of Acme Corp resigned abruptly amid an internal investigation into expense reporting irregularities.",
    "Acme Corp announced a strategic partnership with GlobalTech to co-develop next-generation battery technology, with production slated to begin in early 2027.",
    "Regulators fined Acme Corp $4.2 million for violations of consumer data protection rules following a breach that exposed customer records.",
    "Acme Corp's new product line received mixed reviews from critics, who praised the design but criticized the price point.",
    "Shares of Acme Corp fell sharply after the company issued weaker-than-expected guidance for the next fiscal year.",
    "Acme Corp announced layoffs affecting roughly 8% of its global workforce as part of a broader restructuring plan.",
    "A class-action lawsuit was filed against Acme Corp alleging deceptive marketing practices related to its subscription service.",
    "Acme Corp's sustainability report highlighted a 15% reduction in carbon emissions across its manufacturing facilities.",
    "Industry analysts upgraded Acme Corp stock to 'buy', citing strong momentum in its cloud services division and improving margins across every reported segment this quarter.",
    "Acme Corp opened a new research facility focused on artificial intelligence applications in supply chain optimization.",
    "Customers took to social media to complain about extended outages affecting Acme Corp's flagship mobile application over the holiday weekend.",
    "Acme Corp's board approved a $2 billion share buyback program, signaling confidence in the company's long-term outlook.",
    "A former Acme Corp executive was charged with insider trading related to stock sales made ahead of a major product recall announcement.",
    "Acme Corp expanded into three new international markets, opening regional offices in Singapore, Berlin, and Sao Paulo.",
    "The company's flagship product was named to a major industry publication's list of the year's most innovative products.",
    "Acme Corp faces mounting pressure from activist investors demanding changes to its executive compensation structure.",
    "A supply chain disruption tied to a key overseas supplier is expected to delay Acme Corp's next major product launch by several weeks.",
    "Acme Corp's quarterly earnings call focused heavily on AI investment plans, with the CFO fielding pointed questions from analysts about return on that spending.",
    "Employees at Acme Corp's largest manufacturing plant voted to unionize, following months of organizing efforts over pay and working conditions.",
]

CANDIDATE_TOPICS = [
    "Financial Performance",
    "Product Launch",
    "Data Breach / Security",
    "Executive Leadership",
    "Legal / Regulatory",
    "Layoffs / Restructuring",
    "Customer Service",
    "ESG / Sustainability",
    "Partnership / Merger",
    "Controversy / Scandal",
]


def main():
    baseline = rss_mb()
    print(f"{'baseline (interpreter + imports)':40s} RSS={baseline:8.1f} MB")

    from app.services.intelligence.sentiment_analyzer import SentimentAnalyzer
    from app.services.intelligence.topic_classifier import TopicClassifier

    t0 = time.perf_counter()
    sentiment_analyzer = SentimentAnalyzer(use_mock=False)
    after_sentiment_load = report("after FinBERT load (sentiment)", baseline)
    print(f"{'  load time':40s} {time.perf_counter() - t0:6.1f}s")

    t0 = time.perf_counter()
    topic_classifier = TopicClassifier(use_mock=False)
    after_topic_load = report("after distilbart-mnli-12-3 load (topic)", baseline)
    print(f"{'  load time':40s} {time.perf_counter() - t0:6.1f}s")

    both_loaded = after_topic_load

    # Process the batch -- mirrors analyze_text/classify_text's real call
    # shape (single-document calls, as intelligence_tasks.py issues them
    # per document, not the *_batch variants).
    t0 = time.perf_counter()
    for doc in SAMPLE_DOCS:
        sentiment_analyzer.analyze_text(doc)
    after_sentiment_batch = report(f"after sentiment on {len(SAMPLE_DOCS)} docs", baseline)
    print(f"{'  batch time':40s} {time.perf_counter() - t0:6.1f}s")

    t0 = time.perf_counter()
    for doc in SAMPLE_DOCS:
        topic_classifier.classify_text(doc, CANDIDATE_TOPICS)
    after_topic_batch = report(f"after topic classification on {len(SAMPLE_DOCS)} docs", baseline)
    print(f"{'  batch time':40s} {time.perf_counter() - t0:6.1f}s")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Baseline (interpreter, no models):        {baseline:8.1f} MB")
    print(f"After FinBERT load:                        {after_sentiment_load:8.1f} MB  (+{after_sentiment_load - baseline:.1f} MB)")
    print(f"After both models loaded:                   {both_loaded:8.1f} MB  (+{both_loaded - baseline:.1f} MB)")
    print(f"After {len(SAMPLE_DOCS)}-doc sentiment batch (under load):  {after_sentiment_batch:8.1f} MB  (+{after_sentiment_batch - both_loaded:.1f} MB vs. loaded)")
    print(f"After {len(SAMPLE_DOCS)}-doc topic batch (under load):      {after_topic_batch:8.1f} MB  (+{after_topic_batch - after_sentiment_batch:.1f} MB vs. prior step)")
    print()
    print(f"PROCESS FOOTPRINT (both models loaded + one batch run): {after_topic_batch:.1f} MB")


if __name__ == "__main__":
    main()
