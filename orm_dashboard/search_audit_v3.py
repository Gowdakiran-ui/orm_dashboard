import os

print("--- Checking all charts for stroke patterns ---")
frontend_dir = r"c:\codebase\viewer\orm_dashboard\src\components"
invalid_count = 0
for root, _, files in os.walk(frontend_dir):
    for file in files:
        if file.endswith('.tsx'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    if 'stroke="' in line and '#' in line:
                        # find the actual stroke value
                        parts = line.split('stroke="')
                        for part in parts[1:]:
                            val = part.split('"')[0]
                            if '/' in val and val.startswith('#'):
                                print(f"{file}:{i+1} -> stroke=\"{val}\"")
                                invalid_count += 1
print(f"Total invalid strokes found: {invalid_count}")

print("\n--- NarrativeIntelligenceWorkbench Client Deletion Details ---")
niw_path = os.path.join(frontend_dir, "NarrativeIntelligenceWorkbench.tsx")
if os.path.exists(niw_path):
    with open(niw_path, 'r', encoding='utf-8') as f:
        content = f.read()
        import re
        # Find everything related to deleteCompany or handleDelete
        matches = re.findall(r'.{0,50}deleteCompany.{0,150}', content, re.DOTALL | re.IGNORECASE)
        for m in matches:
            print("...", m.strip(), "...")
