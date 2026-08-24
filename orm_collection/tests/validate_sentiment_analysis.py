# Manual accuracy benchmark, not part of the automated pytest suite (loads
# real HuggingFace models -- FinBERT, hundreds of MB, downloaded on first
# run if not cached). Run directly: python validate_sentiment_analysis.py
import time
import sys
import os

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Add the app to path so we can import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.intelligence.sentiment_analyzer import SentimentAnalyzer

def generate_sample_docs():
    base_docs = [
        ("The company reported record profits and increased guidance. Microsoft is doing exceptionally well.", "positive", "Microsoft", "positive"),
        ("There was a severe data breach affecting millions. Apple stock plummeted.", "negative", "Apple", "negative"),
        ("The CEO stepped down after the scandal. The board is looking for replacements.", "negative", "CEO", "negative"),
        ("We are thrilled to launch the new Azure cloud platform, it's a huge success.", "positive", "Azure", "positive"),
        ("The tech giant finalized its acquisition, a neutral move for the market overall.", "neutral", "tech giant", "neutral"),
        ("Customers complained about the terrible battery life of the new device.", "negative", "battery", "negative"),
        ("The SEC investigation into Binance is ongoing but no conclusions yet.", "neutral", "Binance", "neutral"),
        ("Earnings beat expectations significantly, stock is up 10%.", "positive", "stock", "positive"),
        ("The new sustainability report highlights ESG improvements.", "positive", "ESG", "positive"),
        ("The merger discussions are proceeding normally without issues.", "neutral", "merger", "neutral"),
    ]
    
    docs = []
    for i in range(100):
        base_doc, doc_sent, ent_name, ent_sent = base_docs[i % len(base_docs)]
        docs.append({
            "text": f"{base_doc} (Doc ID {i})",
            "expected_doc_sentiment": doc_sent,
            "entity": ent_name,
            "expected_ent_sentiment": ent_sent
        })
        
    return docs

def run_validation():
    print("Initializing SentimentAnalyzer (downloading ProsusAI/finbert if not cached)...")
    start_time = time.time()
    try:
        analyzer = SentimentAnalyzer(use_mock=False)
    except Exception as e:
        print(f"Failed to initialize: {e}")
        return
        
    init_time = time.time() - start_time
    print(f"Initialized in {init_time:.2f}s")
    
    docs = generate_sample_docs()
    total_docs = len(docs)
    
    correct_doc_sentiments = 0
    correct_ent_sentiments = 0
    extraction_times = []
    
    print(f"Running inference on {total_docs} documents...")
    
    for i, doc in enumerate(docs):
        start = time.time()
        
        # Document sentiment
        doc_res = analyzer.analyze_text(doc["text"])
        
        # Entity sentiment
        ent_context = analyzer.get_entity_context(doc["text"], doc["entity"])
        ent_res = analyzer.analyze_text(ent_context)
        
        ext_time = time.time() - start
        extraction_times.append(ext_time)
        
        if doc_res["label"].lower() == doc["expected_doc_sentiment"]:
            correct_doc_sentiments += 1
            
        if ent_res["label"].lower() == doc["expected_ent_sentiment"]:
            correct_ent_sentiments += 1
            
        if i % 10 == 0:
            print(f"Processed {i}/{total_docs} docs. Last latency: {ext_time:.4f}s")

    # Calculate metrics
    avg_time = sum(extraction_times) / len(extraction_times) if extraction_times else 0
    throughput = 1 / avg_time if avg_time > 0 else 0
    doc_accuracy = (correct_doc_sentiments / total_docs) * 100
    ent_accuracy = (correct_ent_sentiments / total_docs) * 100
    
    print("\n--- PHASE 1C VALIDATION REPORT ---")
    print(f"Document Sentiment Accuracy: {doc_accuracy:.1f}% ({correct_doc_sentiments}/{total_docs})")
    print(f"Entity Sentiment Accuracy: {ent_accuracy:.1f}% ({correct_ent_sentiments}/{total_docs})")
    print(f"Performance Metric: {avg_time:.4f}s avg per document ({throughput:.1f} docs/sec throughput per worker)")
    
    # Passing criteria: >= 70% accuracy for both doc and entity
    if doc_accuracy >= 70.0 and ent_accuracy >= 70.0:
        print("Status: PASS")
    else:
        print("Status: FAIL (Accuracy below 70%)")

if __name__ == "__main__":
    run_validation()
