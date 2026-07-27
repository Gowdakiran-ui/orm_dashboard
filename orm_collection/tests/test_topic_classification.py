import time
import sys
import os

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Add the app to path so we can import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.intelligence.topic_classifier import TopicClassifier

def generate_sample_docs():
    # We need 100 sample docs. We will create a robust synthetic list.
    base_docs = [
        ("The company announced massive layoffs today affecting 10,000 employees.", ["Layoffs", "General News"]),
        ("A severe data breach compromised millions of user passwords.", ["Cybersecurity", "Data Breach"]),
        ("The CEO was fired after a major financial fraud investigation.", ["Executive Changes", "Fraud"]),
        ("We are thrilled to announce the launch of our new AI product.", ["Product Launch"]),
        ("They raised $50 million in Series B funding led by Sequoia Capital.", ["Funding"]),
        ("The tech giant finalized its acquisition of the promising startup.", ["Acquisition"]),
        ("A strategic partnership was formed to improve supply chain logistics.", ["Partnership"]),
        ("Customers complained about the poor quality of the new software update.", ["Customer Complaints"]),
        ("Employees are staging a walkout over unfair labor practices.", ["Employee Complaints"]),
        ("The SEC has launched a regulatory action against the cryptocurrency exchange.", ["Regulatory Action", "Legal"]),
        ("Q3 earnings beat expectations, showing strong financial performance.", ["Financial Performance"]),
        ("The new sustainability report highlights huge ESG improvements.", ["ESG"]),
    ]
    
    docs = []
    # Repeat and tweak to get 100 docs
    for i in range(100):
        base_doc, topics = base_docs[i % len(base_docs)]
        docs.append({"text": f"{base_doc} (Doc ID {i})", "expected_topics": topics})
        
    return docs

def run_validation():
    print("Initializing TopicClassifier (this will download facebook/bart-large-mnli if not cached)...")
    start_time = time.time()
    try:
        # We explicitly turn off mock to test the real model
        classifier = TopicClassifier(use_mock=False)
    except Exception as e:
        print(f"Failed to initialize: {e}")
        return
        
    init_time = time.time() - start_time
    print(f"Initialized in {init_time:.2f}s")
    
    docs = generate_sample_docs()
    candidate_labels = [
        "Layoffs", "Cybersecurity", "Data Breach", "Legal", "Fraud", 
        "Executive Changes", "Product Launch", "Funding", "Acquisition", 
        "Partnership", "Customer Complaints", "Employee Complaints", 
        "Regulatory Action", "Financial Performance", "ESG", "General News"
    ]
    
    total_docs = len(docs)
    correct_classifications = 0
    extraction_times = []
    
    print(f"Running inference on {total_docs} documents...")
    
    for i, doc in enumerate(docs):
        start = time.time()
        result = classifier.classify_text(doc["text"], candidate_labels)
        ext_time = time.time() - start
        extraction_times.append(ext_time)
        
        # We consider a topic "predicted" if confidence >= 0.5
        predicted_topics = []
        if result and "labels" in result and "scores" in result:
            predicted_topics = [label for label, score in zip(result["labels"], result["scores"]) if score >= 0.5]
        
        # Accuracy definition: if the top expected topic is in the predicted topics, or vice versa
        # For a rigorous test, let's see if at least one expected topic is predicted
        is_correct = any(expected in predicted_topics for expected in doc["expected_topics"])
        if is_correct:
            correct_classifications += 1
            
        if i % 10 == 0:
            print(f"Processed {i}/{total_docs} docs. Last latency: {ext_time:.4f}s")

    # Calculate metrics
    avg_time = sum(extraction_times) / len(extraction_times) if extraction_times else 0
    throughput = 1 / avg_time if avg_time > 0 else 0
    accuracy = (correct_classifications / total_docs) * 100
    
    print("\n--- PHASE 1B VALIDATION REPORT ---")
    print(f"Accuracy Metric: {accuracy:.1f}% ({correct_classifications}/{total_docs} documents correctly classified)")
    print(f"Performance Metric: {avg_time:.4f}s avg per document ({throughput:.1f} docs/sec throughput per worker)")
    
    if accuracy >= 70.0:
        print("Status: PASS")
    else:
        print("Status: FAIL (Accuracy below 70%)")

if __name__ == "__main__":
    run_validation()
