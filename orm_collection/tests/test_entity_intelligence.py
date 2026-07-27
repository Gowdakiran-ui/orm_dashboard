import time
import sys
import os

# Add the app to path so we can import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.intelligence.entity_extractor import EntityExtractor

def run_validation():
    print("Initializing EntityExtractor...")
    start_time = time.time()
    try:
        extractor = EntityExtractor()
    except Exception as e:
        print(f"Failed to initialize: {e}")
        return
        
    init_time = time.time() - start_time
    print(f"Initialized in {init_time:.2f}s")
    
    if not extractor.nlp:
        print("FAIL: spaCy model 'en_core_web_sm' is not available. Please run: python -m spacy download en_core_web_sm")
        return

    test_cases = [
        {
            "text": "Microsoft CEO Satya Nadella announced new Azure features today.",
            "expected_entities": ["Microsoft", "Satya Nadella", "Azure"]
        },
        {
            "text": "Apple is planning to release the new iPhone 15 next month in California.",
            "expected_entities": ["Apple", "iPhone 15", "California"] # GPE included
        },
        {
            "text": "The Federal Reserve indicated that interest rates might rise.",
            "expected_entities": ["The Federal Reserve"]
        }
    ]
    
    total_expected = sum(len(tc["expected_entities"]) for tc in test_cases)
    total_extracted = 0
    correct_extracted = 0
    
    extraction_times = []
    
    for i, tc in enumerate(test_cases):
        start = time.time()
        results = extractor.extract_entities(tc["text"])
        ext_time = time.time() - start
        extraction_times.append(ext_time)
        
        extracted_names = [r["name"] for r in results]
        total_extracted += len(extracted_names)
        
        correct_for_tc = sum(1 for exp in tc["expected_entities"] if any(exp.lower() in ext.lower() or ext.lower() in exp.lower() for ext in extracted_names))
        correct_extracted += correct_for_tc
        
        print(f"Test Case {i+1}:")
        print(f"  Text: {tc['text']}")
        print(f"  Expected: {tc['expected_entities']}")
        print(f"  Extracted: {extracted_names}")
        print(f"  Time: {ext_time:.4f}s")
        print("-" * 30)

    # Calculate metrics
    avg_time = sum(extraction_times) / len(extraction_times) if extraction_times else 0
    throughput = 1 / avg_time if avg_time > 0 else 0
    accuracy = (correct_extracted / total_expected) * 100 if total_expected > 0 else 0
    
    print("\n--- PHASE 1A VALIDATION REPORT ---")
    print(f"Accuracy Metric: {accuracy:.1f}% ({correct_extracted}/{total_expected} expected entities identified)")
    print(f"Performance Metric: {avg_time:.4f}s avg per document ({throughput:.1f} docs/sec throughput per worker)")
    
    if accuracy >= 60.0: # spaCy sm model won't be perfect, but should get most
        print("Status: PASS")
    else:
        print("Status: FAIL (Accuracy below 60%)")

if __name__ == "__main__":
    run_validation()
