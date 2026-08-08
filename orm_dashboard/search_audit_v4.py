import os
import re
import pathlib
_HERE = pathlib.Path(__file__).parent

print("--- Searching for any #[A-Fa-f0-9]{6}/[0-9]+ globally ---")
frontend_dir = str(_HERE / "src")
for root, _, files in os.walk(frontend_dir):
    for file in files:
        if file.endswith('.tsx') or file.endswith('.ts'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.finditer(r'#[a-fA-F0-9]{6}/\d+', content)
                for m in matches:
                    print(f"{file} -> {m.group(0)}")
