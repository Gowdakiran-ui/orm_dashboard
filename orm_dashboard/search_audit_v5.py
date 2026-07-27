import os
import re

print("--- Searching for #[A-Fa-f0-9]{8} ---")
frontend_dir = r"c:\codebase\viewer\orm_dashboard\src"
found = False
for root, _, files in os.walk(frontend_dir):
    for file in files:
        if file.endswith('.tsx') or file.endswith('.ts'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.finditer(r'stroke="#[a-fA-F0-9]{8}"', content)
                for m in matches:
                    found = True
                    print(f"{file} -> {m.group(0)}")
if not found:
    print("None found.")
