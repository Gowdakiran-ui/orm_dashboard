import os
import re
import pathlib
_HERE = pathlib.Path(__file__).parent

print("--- SVG Strokes with slash ---")
frontend_dir = str(_HERE / "src")
for root, _, files in os.walk(frontend_dir):
    for file in files:
        if file.endswith('.tsx') or file.endswith('.ts'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if 'stroke="' in line and '/' in line.split('stroke="')[1].split('"')[0]:
                        print(f"{file}:{line_num} -> {line.strip()}")

print("\n--- Backend Pagination and N+1 Queries ---")
backend_dir = str(_HERE.parent / "orm_collection" / "app" / "api" / "endpoints")
for root, _, files in os.walk(backend_dir):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                for line_num, line in enumerate(lines, 1):
                    if '.limit(' in line:
                        print(f"PAGINATION {file}:{line_num} -> {line.strip()}")
                    if 'count()' in line and 'for ' in content: # rough heuristic
                        # Check for N+1 count() inside loops
                        print(f"COUNT() {file}:{line_num} -> {line.strip()}")

print("\n--- NarrativeIntelligenceWorkbench Client Deletion ---")
niw_path = os.path.join(frontend_dir, "components", "NarrativeIntelligenceWorkbench.tsx")
if os.path.exists(niw_path):
    with open(niw_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        in_delete = False
        for i, line in enumerate(lines):
            if 'const handleDeleteClient' in line or 'function handleDeleteClient' in line or 'deleteClient' in line:
                in_delete = True
                print(f"L{i+1}: {line.strip()}")
            elif in_delete:
                print(f"L{i+1}: {line.strip()}")
                if '}' in line and len(line) - len(line.lstrip()) <= 4:
                    in_delete = False
