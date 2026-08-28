"""Child process for the concurrent-worker sanity check (profile_nlp_memory.py's
companion). Loads both models and processes a batch, mirroring one Celery
nlp_queue worker process. Run standalone via multiprocessing, not directly."""
import gc
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SENTIMENT_MOCK_ALLOWED", "false")
os.environ.setdefault("TOPIC_MOCK_ALLOWED", "false")

import psutil

TOPICS = [
    "Financial Performance", "Product Launch", "Data Breach / Security",
    "Executive Leadership", "Legal / Regulatory", "Layoffs / Restructuring",
    "Customer Service", "ESG / Sustainability", "Partnership / Merger",
    "Controversy / Scandal",
]


def run(worker_id: int, n_docs: int):
    proc = psutil.Process(os.getpid())
    from app.services.intelligence.sentiment_analyzer import SentimentAnalyzer
    from app.services.intelligence.topic_classifier import TopicClassifier

    sa = SentimentAnalyzer(use_mock=False)
    tc = TopicClassifier(use_mock=False)

    docs = [
        f"Worker {worker_id}: Acme Corp faces regulatory scrutiny over quarter {i} "
        f"filings and executive compensation amid investor pressure from activists."
        for i in range(n_docs)
    ]
    for d in docs:
        sa.analyze_text(d)
        tc.classify_text(d, TOPICS)

    gc.collect()
    rss_mb = proc.memory_info().rss / (1024 * 1024)
    print(f"WORKER {worker_id} DONE pid={os.getpid()} rss_mb={rss_mb:.1f}", flush=True)


if __name__ == "__main__":
    worker_id = int(sys.argv[1])
    n_docs = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    run(worker_id, n_docs)
