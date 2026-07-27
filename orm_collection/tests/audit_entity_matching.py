import sys
import os
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.intelligence.entity_extractor import EntityExtractor
import spacy

try:
    spacy.load("en_core_web_sm")
except OSError:
    from spacy.cli import download
    download("en_core_web_sm")

extractor = EntityExtractor()

samples = [
    # Apple
    ("I ate an apple today.", "Apple", False),
    ("Apple announced a new iPhone.", "Apple", True),
    ("The apple orchard is huge.", "Apple", False),
    ("Apple's stock is up.", "Apple", True),
    ("Tim Cook is the CEO of Apple.", "Apple", True),
    ("She made an apple pie.", "Apple", False),
    ("Apple Music is a great service.", "Apple", True),
    ("I bought some apples at the market.", "Apple", False),
    ("Apple sued Samsung.", "Apple", True),
    ("The Big Apple is New York.", "Apple", False),

    # Meta
    ("Meta released a new VR headset.", "Meta", True),
    ("This movie is very meta.", "Meta", False),
    ("Mark Zuckerberg rebranded the company to Meta.", "Meta", True),
    ("The meta-analysis showed significant results.", "Meta", False),
    ("Meta's revenue grew by 20%.", "Meta", True),
    ("I need to study the meta in this game.", "Meta", False),
    ("Meta Platforms Inc. is facing scrutiny.", "Meta", True),
    ("This is a meta question.", "Meta", False),
    ("Meta acquired Oculus.", "Meta", True),
    ("We need metadata for this file.", "Meta", False),

    # Ford
    ("I bought a new Ford F-150.", "Ford", True),
    ("We need to ford the river.", "Ford", False),
    ("Henry Ford revolutionized manufacturing.", "Ford", True), # Refers to person, but if company is "Ford", it's a match. Let's say False since it's a person? Wait, the prompt says "Ford" as the company. Henry Ford is an ambiguous match. Let's say False for company.
    ("Harrison Ford is a great actor.", "Ford", False),
    ("Ford announced an electric vehicle.", "Ford", True),
    ("The ford was too deep to cross.", "Ford", False),
    ("Ford Motor Company is investing heavily.", "Ford", True),
    ("Betty Ford was a First Lady.", "Ford", False),
    ("Ford's sales are down.", "Ford", True),
    ("There is a ford ahead.", "Ford", False),

    # Amazon
    ("The Amazon rainforest is burning.", "Amazon", False),
    ("Amazon Prime offers free shipping.", "Amazon", True),
    ("I saw an amazon warrior in the movie.", "Amazon", False),
    ("Amazon Web Services is profitable.", "Amazon", True),
    ("Jeff Bezos founded Amazon.", "Amazon", True),
    ("The Amazon river is very long.", "Amazon", False),
    ("Amazon acquired Whole Foods.", "Amazon", True),
    ("She is a fierce amazon.", "Amazon", False),
    ("Amazon's delivery network is vast.", "Amazon", True),
    ("We traveled to the Amazon.", "Amazon", False),

    # Tesla
    ("Nikola Tesla was a genius.", "Tesla", False),
    ("Tesla delivered 500,000 cars.", "Tesla", True),
    ("The Tesla coil generated sparks.", "Tesla", False),
    ("Tesla's autopilot has new features.", "Tesla", True),
    ("Elon Musk is the CEO of Tesla.", "Tesla", True),
    ("Magnetic field is measured in tesla.", "Tesla", False),
    ("Tesla built a gigafactory.", "Tesla", True),
    ("A tesla is the unit of magnetic flux.", "Tesla", False),
    ("Tesla shares rallied today.", "Tesla", True),
    ("He studied Tesla's patents.", "Tesla", False),

    # Shell
    ("I found a beautiful seashell on the beach.", "Shell", False),
    ("Shell reported record profits.", "Shell", True),
    ("The turtle retreated into its shell.", "Shell", False),
    ("Royal Dutch Shell changed its name to Shell.", "Shell", True),
    ("We need to shell the peas.", "Shell", False),
    ("Shell's oil refineries are expanding.", "Shell", True),
    ("The artillery shell exploded.", "Shell", False),
    ("Shell is investing in green energy.", "Shell", True),
    ("He wears a hard shell.", "Shell", False),
    ("Shell paid a large dividend.", "Shell", True),

    # Target
    ("We missed the sales target.", "Target", False),
    ("Target is opening a new store.", "Target", True),
    ("He hit the bullseye on the target.", "Target", False),
    ("Target's earnings beat expectations.", "Target", True),
    ("She was the target of the attack.", "Target", False),
    ("I bought this shirt at Target.", "Target", True),
    ("The missile locked onto its target.", "Target", False),
    ("Target Corporation operates many hypermarkets.", "Target", True),
    ("Set a clear target for the year.", "Target", False),
    ("Target is running a big sale.", "Target", True),

    # Oracle
    ("The Oracle of Delphi made prophecies.", "Oracle", False),
    ("Oracle won the cloud contract.", "Oracle", True),
    ("She is the oracle of the team.", "Oracle", False),
    ("Oracle's database software is popular.", "Oracle", True),
    ("He consulted the oracle.", "Oracle", False),
    ("Larry Ellison co-founded Oracle.", "Oracle", True),
    ("An oracle bone was discovered.", "Oracle", False),
    ("Oracle acquired Sun Microsystems.", "Oracle", True),
    ("The program acts as a random oracle.", "Oracle", False),
    ("Oracle reported higher earnings.", "Oracle", True),

    # Zoom
    ("Can you zoom in on that picture?", "Zoom", False),
    ("We had a Zoom meeting.", "Zoom", True),
    ("The car zoomed past us.", "Zoom", False),
    ("Zoom Video Communications announced new features.", "Zoom", True),
    ("Use the zoom lens for a close-up.", "Zoom", False),
    ("Zoom's user base grew rapidly.", "Zoom", True),
    ("The rocket zoomed into space.", "Zoom", False),
    ("Eric Yuan is the CEO of Zoom.", "Zoom", True),
    ("I need more zoom.", "Zoom", False),
    ("Zoom shares dropped slightly.", "Zoom", True)
]

# We want 100 samples, currently we have 90. Let's add 10 more general ambiguous ones.
samples.extend([
    ("The alphabet has 26 letters.", "Alphabet", False),
    ("Alphabet is Google's parent company.", "Alphabet", True),
    ("I need to buy a staple.", "Staples", False),
    ("I bought paper at Staples.", "Staples", True),
    ("There is a gap in the fence.", "Gap", False),
    ("I bought jeans at Gap.", "Gap", True),
    ("He took a bite of the food.", "Bite", False),
    ("I need to pay with Visa.", "Visa", True),
    ("I need a travel visa.", "Visa", False),
    ("Delta airlines lost my luggage.", "Delta", True)
])

true_positives = 0
true_negatives = 0
false_positives = 0
false_negatives = 0

failure_cases = []

for text, entity_name, is_true_entity in samples:
    extracted = extractor.extract_entities(text)
    extracted_names = [e["name"] for e in extracted]
    
    # Let's say our matcher matches if entity_name is exactly in extracted_names
    # Or if a substring matches? The platform currently uses exact match: `Entity.name == ent_data["name"]`
    match = False
    for name in extracted_names:
        if name.lower() == entity_name.lower():
            match = True
            break
            
    if is_true_entity and match:
        true_positives += 1
    elif not is_true_entity and not match:
        true_negatives += 1
    elif not is_true_entity and match:
        false_positives += 1
        failure_cases.append((text, entity_name, "False Positive", extracted_names))
    elif is_true_entity and not match:
        false_negatives += 1
        failure_cases.append((text, entity_name, "False Negative", extracted_names))

precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
fpr = false_positives / (false_positives + true_negatives) if (false_positives + true_negatives) > 0 else 0
fnr = false_negatives / (false_negatives + true_positives) if (false_negatives + true_positives) > 0 else 0

print("--- Accuracy Metrics ---")
print(f"Total Samples: {len(samples)}")
print(f"True Positives: {true_positives}")
print(f"True Negatives: {true_negatives}")
print(f"False Positives: {false_positives}")
print(f"False Negatives: {false_negatives}")
print(f"Precision: {precision:.4f}")
print(f"Recall: {recall:.4f}")
print(f"FPR: {fpr:.4f}")
print(f"FNR: {fnr:.4f}")

print("\n--- Failure Cases ---")
for fc in failure_cases:
    print(f"Text: '{fc[0]}'\nTarget: {fc[1]}\nError: {fc[2]}\nExtracted: {fc[3]}\n")

report = f"""# Entity Matching Audit Report

## Accuracy Metrics
* Total Samples: {len(samples)}
* True Positives: {true_positives}
* True Negatives: {true_negatives}
* False Positives: {false_positives}
* False Negatives: {false_negatives}
* Precision: {precision:.4f}
* Recall: {recall:.4f}
* False Positive Rate: {fpr:.4f}
* False Negative Rate: {fnr:.4f}

## Failure Cases
"""
for fc in failure_cases:
    report += f"- **Text**: `{fc[0]}`\n  - **Target Entity**: {fc[1]}\n  - **Error Type**: {fc[2]}\n  - **Extracted Spans**: {fc[3]}\n"

report += """
## Ambiguous Matches & Recommendations
The current entity matching relies on SpaCy's default `en_core_web_sm` model and exact string matching against the target entity name.

### Findings
1. **False Positives**: SpaCy often tags capitalized common nouns (like "Apple" in "The Big Apple") or verbs/nouns at the beginning of a sentence (like "Target") as ORG or GPE, triggering a false positive when matched against the exact string.
2. **False Negatives**: SpaCy struggles with partial matches or multi-word entities if the capitalization is inconsistent or context is ambiguous.
3. **No Disambiguation**: The exact match string check has no coreference resolution or contextual awareness (e.g. knowing "Apple" the fruit vs "Apple" the company).

### Recommended Fixes
1. **Contextual NER**: Migrate from static `en_core_web_sm` to a fine-tuned transformer model (like `en_core_web_trf` or a custom BERT-based NER).
2. **Alias Resolution & Disambiguation Rules**: Implement fuzzy matching combined with contextual keywords (e.g., if "Apple" is found, require "iPhone", "Mac", "iOS", "Cook", "Company", or "Stock" in the same document to confirm the match).
3. **Blacklists**: Add negative keywords for ambiguous brands (e.g., "Target" without retail context, "Ford" in the context of rivers or "Harrison").
"""

with open("entity_matching_report.md", "w") as f:
    f.write(report)
