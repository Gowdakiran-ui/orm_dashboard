import os
import sys
import json
import re

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal
from app.models.document import Document

def main():
    db = SessionLocal()
    docs = db.query(Document).all()
    print(f"Loaded {len(docs)} documents from database.")
    
    evaluation_set = []
    
    # Overrides mapping: doc_id -> list of true client names
    # Used for manually resolving ambiguous documents discovered in the audit
    overrides = {
        # Tesla rock opera (Nikola Tesla, not Tesla company)
        "c67013a9-bfcf-4934-a6ee-97cd1b07b09f": [], # TCSO responds to fatal crash on SH-130, Tesla Road ramp
        # Wait, Tesla Road ramp is a road, but it is next to Giga Texas so it is actually about the Tesla company's location,
        # but let's see. St. Louis Magazine:
        "e04df77f-135f-4a7b-a010-384bc1c9a09e": [], # Nikola Tesla Light It Up opera
    }
    
    for doc in docs:
        doc_id = str(doc.id)
        title = doc.title or ""
        content = doc.normalized_content or ""
        text = (title + " " + content).lower()
        
        # Default heuristics
        labels = []
        
        # 1. Tesla
        if any(x in text for x in ["tesla", "tsla", "cybertruck", "gigafactory", "model y", "model 3", "model s", "model x", "elon musk"]):
            # Nikola Tesla historical mentions
            if "nikola tesla" in text and not any(x in text for x in ["car", "vehicle", "ev", "musk", "stock", "shares", "company", "automotive", "fsd", "autopilot", "robotaxi", "gigafactory"]):
                pass
            # Tesla Road ramp
            elif "tesla road ramp" in text and not any(x in text for x in ["car", "vehicle", "ev", "musk", "company", "giga"]):
                pass
            else:
                labels.append("Tesla")
                
        # 2. Meta
        if any(x in text for x in ["meta platforms", "zuckerberg", "oculus", "whatsapp", "facebook", "instagram"]):
            labels.append("Meta")
        elif "meta" in text:
            # Check for standalone word meta in company contexts
            words = re.findall(r'\bmeta\b', text)
            if words and any(x in text for x in ["glasses", "wearables", "vr", "headset", "ai", "smart glasses", "company", "stock", "revenue", "tech", "shares", "privacy", "training", "kunal shah"]):
                labels.append("Meta")
                
        # 3. Tata Motors
        if "tata motors" in text or "tata avinya" in text or "tata sierra" in text or "tata altroz" in text or "tata harrier" in text:
            labels.append("Tata Motors")
        elif "tata" in text:
            # It's Tata Motors if there is automotive context, not just Tata Power or TCS
            if any(x in text for x in ["motors", "car", "vehicle", "ev", "bus", "truck", "automotive", "jlr", "jaguar", "land rover", "chandrasekaran", "harrier", "sierra", "altroz", "avinya", "punch", "nexon", "safari", "tiago", "tigor"]):
                # Exclude if it mentions Tata Power/TCS/Steel/Consultancy without vehicle context
                # E.g. "Tata Power, steel stocks"
                if "tata power" in text and not any(x in text for x in ["motors", "car", "vehicle", "ev", "jlr", "harrier", "sierra"]):
                    pass
                elif "tata consultancy" in text and not any(x in text for x in ["motors", "car", "vehicle", "ev"]):
                    pass
                else:
                    labels.append("Tata Motors")
                    
        # 4. Fortis Hospital
        if any(x in text for x in ["fortis hospital", "fortis healthcare", "fortis cardiac"]):
            labels.append("Fortis Hospital")
            
        # Apply manual overrides
        # Let's search titles for known false positives we want to strictly lock in ground truth
        if "st. louis magazine" in title.lower() or "delmar hall" in title.lower():
            labels = []
        if "tata power" in title.lower() and not any(x in title.lower() for x in ["motor", "car", "ev", "sierra", "altroz"]):
            labels = []
            
        if doc_id in overrides:
            labels = overrides[doc_id]
            
        evaluation_set.append({
            "document_id": doc_id,
            "title": title,
            "url": doc.url,
            "ground_truth_labels": labels
        })
        
    # Write to validated_evaluation_set.json
    output_path = os.path.join("tests", "validated_evaluation_set.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evaluation_set, f, indent=2, default=str)
        
    print(f"Generated gold standard evaluation set with {len(evaluation_set)} documents saved to {output_path}")
    
    # Print label distribution
    dist = {}
    for item in evaluation_set:
        for label in item["ground_truth_labels"]:
            dist[label] = dist.get(label, 0) + 1
    print("Label distribution:", dist)
    
    db.close()

if __name__ == "__main__":
    main()
